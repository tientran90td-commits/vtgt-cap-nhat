"""Lời thoại gốc của video: phụ đề có sẵn (file cạnh phim / nhúng trong video) hoặc nhận dạng giọng nói.

Chế độ "auto" chọn cách nhanh nhất đang dùng được: phụ đề cạnh video -> phụ đề nhúng -> (có mạng + key) Groq /
OpenAI Whisper -> Whisper card đồ họa (whisper.cpp Vulkan) -> Whisper CPU. Cách nào lỗi thì tự chuyển cách kế tiếp,
kể cả từ trên máy sang online và ngược lại.
"""
from __future__ import annotations

import html
import re
import threading
from pathlib import Path

import requests

from . import hybrid
from .config import Settings
from .media import Cancelled, extract_audio, probe, run

ENGINES = {
    "auto": "⚡ Tự động (phụ đề có sẵn → cách nhanh nhất đang có)",
    "subtitle": "Dùng file phụ đề gốc (.srt / .vtt / .ass)",
    "ocr": "🔤 Đọc phụ đề cứng trên hình (OCR, theo khung phụ đề)",
    "groq": "Groq Whisper API (rất nhanh, có gói miễn phí)",
    "openai": "OpenAI Whisper API",
    "local": "Whisper offline trên máy (faster-whisper, CPU)",
    "gpu": "Whisper bằng card đồ họa AMD/Intel/NVIDIA (whisper.cpp Vulkan, offline)",
}
WCPP_URL = ("https://github.com/tientran90td-commits/vtgt-cap-nhat/releases/download/whisper-vulkan-v1.9.5/"
            "whisper-vulkan-win-x64.zip")
GGML_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
GGML_NAMES = {"large-v3-turbo": "large-v3-turbo-q8_0", "large-v3": "large-v3-q5_0", "medium": "medium-q8_0",
              "small": "small-q8_0", "base": "base-q8_0", "tiny": "tiny-q8_0"}
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}


class TranscriptError(RuntimeError):
    pass


# ------------------------------------------------------------------ đọc phụ đề
def _ts(s: str) -> float:
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(s)
    except ValueError:
        return 0.0


def _clean(text: str) -> str:
    text = re.sub(r"\{[^}]*\}", "", text)          # thẻ ASS {\i1}
    text = re.sub(r"<[^>]+>", "", text)            # thẻ HTML <i>
    text = text.replace("\\N", " ").replace("\\n", " ")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_subtitles(path: str | Path) -> list[dict]:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1258", "latin-1"):
        try:
            txt = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    out = []
    if "[Events]" in txt:  # ASS / SSA
        fmt = None
        for line in txt.splitlines():
            if line.startswith("Format:") and fmt is None and "Start" in line:
                fmt = [x.strip().lower() for x in line[7:].split(",")]
            elif line.startswith("Dialogue:") and fmt:
                vals = line[9:].split(",", len(fmt) - 1)
                d = dict(zip(fmt, vals))
                t = _clean(d.get("text", ""))
                if t:
                    out.append({"start": _ts(d.get("start", "0")), "end": _ts(d.get("end", "0")), "text": t})
    else:  # SRT / VTT
        blocks = re.split(r"\n\s*\n", txt.replace("\r", ""))
        for b in blocks:
            m = re.search(r"(\d[\d:.,]*)\s*-->\s*(\d[\d:.,]*)", b)
            if not m:
                continue
            body = b[m.end():].strip()
            t = _clean(" ".join(body.splitlines()))
            if t:
                out.append({"start": _ts(m.group(1)), "end": _ts(m.group(2)), "text": t})
    out.sort(key=lambda x: x["start"])
    return out


def find_sidecar(video: str) -> Path | None:
    v = Path(video)
    for ext in (".srt", ".vtt", ".ass", ".ssa"):
        for cand in [v.with_suffix(ext), *sorted(v.parent.glob(v.stem + ".*" + ext))]:
            if cand.exists():
                return cand
    return None


def embedded(video: str, work: Path, cancel=None) -> list[dict]:
    info = probe(video)
    subs = [s for s in info.subtitles if s["codec"] in TEXT_SUB_CODECS]
    if not subs:
        return []
    pick = next((s for s in subs if s["lang"].lower() in ("vie", "vi")), None) or \
        next((s for s in subs if s["lang"].lower() in ("eng", "en")), None) or subs[0]
    out = work / "embedded.srt"
    run(["-i", video, "-map", f"0:s:{pick['index']}", str(out)], cancel=cancel)
    return parse_subtitles(out)


# ------------------------------------------------------------------ nhận dạng giọng nói
def _api_whisper(video: str, work: Path, duration: float, settings: Settings, provider: str, language: str,
                 prompt: str, log, progress, cancel) -> list[dict]:
    key = settings.key(provider)
    if not key:
        raise TranscriptError(f"Chưa nhập API key {provider.capitalize()} (Cài đặt & API).")
    url = {"groq": "https://api.groq.com/openai/v1/audio/transcriptions",
           "openai": "https://api.openai.com/v1/audio/transcriptions"}[provider]
    model = "whisper-large-v3-turbo" if provider == "groq" else "whisper-1"
    chunk = 20 * 60.0  # 20 phút/phần (giới hạn 25MB của API)
    segs: list[dict] = []
    n = max(1, int((duration + chunk - 1) // chunk))
    for k in range(n):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        st = k * chunk
        progress(k / n, f"Nhận dạng thoại phần {k + 1}/{n} ({provider})")
        mp3 = work / f"stt_{k:02d}.mp3"
        extract_audio(video, mp3, 16000, cancel, bitrate="32k", start=st, length=min(chunk, duration - st))
        data = {"model": model, "response_format": "verbose_json"}
        if language and language != "auto":
            data["language"] = language
        if prompt:
            data["prompt"] = prompt[:400]
        for attempt in range(4):
            with open(mp3, "rb") as fh:
                r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, data=data,
                                  files={"file": (mp3.name, fh, "audio/mpeg")}, timeout=600,
                                  proxies=settings.proxies())
            if r.status_code in (429, 500, 502, 503) and attempt < 3:
                log(f"{provider} bận ({r.status_code}) - thử lại sau {10 * (attempt + 1)}s...", "warn")
                _wait(10 * (attempt + 1), cancel)
                continue
            break
        if r.status_code >= 400:
            raise TranscriptError(f"{provider} Whisper lỗi {r.status_code}: {r.text[:300]}")
        for s in r.json().get("segments", []):
            t = (s.get("text") or "").strip()
            if t:
                segs.append({"start": round(st + float(s["start"]), 2), "end": round(st + float(s["end"]), 2),
                             "text": t})
        mp3.unlink(missing_ok=True)
    return segs


def _local_whisper(video: str, work: Path, duration: float, settings: Settings, language: str, prompt: str,
                   log, progress, cancel) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptError("Chưa cài Whisper offline (pip install faster-whisper) - hoặc nhập key Groq "
                              "miễn phí để nhận dạng nhanh hơn.") from e
    import os

    wav = work / "audio16k.wav"
    if not wav.exists():
        progress(0.02, "Tách âm thanh")
        extract_audio(video, wav, 16000, cancel)
    name = settings.get("speech", "whisper_model") or "small"
    log(f"Nạp Whisper '{name}' (lần đầu sẽ tự tải model)...")
    try:
        model = WhisperModel(name, device="auto", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    except Exception:  # noqa: BLE001 - không có GPU phù hợp
        model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
    segments, _info = model.transcribe(str(wav), language=None if language in ("", "auto") else language,
                                       vad_filter=True, initial_prompt=prompt or None,
                                       condition_on_previous_text=False)
    out = []
    for s in segments:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        t = s.text.strip()
        if t:
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": t})
        progress(min(0.99, s.end / max(1.0, duration)), f"Nhận dạng thoại {int(s.end)}/{int(duration)}s")
    return out


def _download(url: str, dest: Path, settings: Settings, label: str, progress, cancel) -> Path:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=(15, 300), proxies=settings.proxies()) as r:
        if r.status_code != 200:
            raise TranscriptError(f"Tải {label} lỗi HTTP {r.status_code}")
        total = int(r.headers.get("content-length") or 0)
        got = 0
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                fh.write(chunk)
                got += len(chunk)
                if total:
                    progress(got / total * 0.1, f"Tải {label} {got / 1e6:.0f}/{total / 1e6:.0f} MB (một lần)")
    tmp.replace(dest)
    return dest


def gpu_assets(settings: Settings, progress=lambda *_a: None, cancel=None):
    """Tải (1 lần) chương trình whisper.cpp Vulkan + model ggml. Trả về (whisper-cli.exe, model)."""
    import zipfile

    from .config import app_home

    tool = app_home() / "whisper-gpu"
    exe = next(iter(tool.glob("**/whisper-cli.exe")), None)
    if exe is None:
        tool.mkdir(parents=True, exist_ok=True)
        z = _download(WCPP_URL, tool / "whisper.zip", settings, "Whisper GPU", progress, cancel)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(tool)
        z.unlink(missing_ok=True)
        exe = next(iter(tool.glob("**/whisper-cli.exe")), None)
        if exe is None:
            raise TranscriptError("Bản tải về không có whisper-cli.exe")
    name = GGML_NAMES.get(settings.get("speech", "whisper_model") or "large-v3-turbo", "large-v3-turbo-q8_0")
    model = tool / f"ggml-{name}.bin"
    if not model.exists():
        _download(GGML_URL.format(name=name), model, settings, f"model {name}", progress, cancel)
    return exe, model


def _gpu_whisper(video: str, work: Path, duration: float, settings: Settings, language: str, prompt: str,
                 log, progress, cancel) -> list[dict]:
    """whisper.cpp bản Vulkan: nhận dạng thoại bằng card đồ họa (cả card AMD như RX 5700 XT)."""
    import json as _json
    import os
    import subprocess

    from .media import no_window

    if os.name != "nt":
        raise TranscriptError("Whisper bằng card đồ họa hiện có bản dựng sẵn cho Windows.")
    exe, model = gpu_assets(settings, progress, cancel)
    wav = work / "audio16k.wav"
    if not wav.exists():
        extract_audio(video, wav, 16000, cancel)
    out = work / "wgpu"
    cmd = [str(exe), "-m", str(model), "-f", str(wav), "-l", language if language not in ("", "auto") else "auto",
           "-oj", "-of", str(out), "-t", str(max(2, (os.cpu_count() or 4) - 2)), "-pp", "-mc", "64", "-sns"]
    if prompt:
        cmd += ["--prompt", prompt[:200]]
    log("Nhận dạng thoại bằng card đồ họa (whisper.cpp)...")
    proc = subprocess.Popen(cmd, cwd=str(exe.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, **no_window())
    for raw in iter(proc.stdout.readline, b""):
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise Cancelled()
        line = raw.decode("utf-8", "replace")
        m = re.search(r"progress\s*=\s*(\d+)%", line)
        if m:
            pct = min(100, int(m.group(1)))
            progress(0.1 + 0.9 * pct / 100, f"Nhận dạng thoại {pct}% (card đồ họa)")
        elif re.match(r"ggml_vulkan:\s*\d+\s*=", line):
            log("🎮 Card đồ họa: " + line.split("=", 1)[1].split("|")[0].strip())
    proc.wait()
    f = out.with_suffix(".json")
    if proc.returncode != 0 or not f.exists():
        raise TranscriptError(f"whisper.cpp lỗi (mã {proc.returncode})")
    segs = []
    for seg in _json.loads(f.read_text(encoding="utf-8", errors="replace")).get("transcription", []):
        t = (seg.get("text") or "").strip()
        off = seg.get("offsets") or {}
        if t and not t.startswith("[") and not t.startswith("("):
            segs.append({"start": off.get("from", 0) / 1000, "end": off.get("to", 0) / 1000, "text": t})
    return segs


def _wait(sec: float, cancel) -> None:
    ev = cancel or threading.Event()
    if ev.wait(sec):
        raise Cancelled()


def transcribe(video: str, work: Path, settings: Settings, log, progress, cancel, subtitle_file: str = "",
               prompt: str = "") -> tuple[list[dict], str]:
    """Trả về (danh sách câu thoại, nguồn đã dùng)."""
    work.mkdir(parents=True, exist_ok=True)
    engine = settings.get("speech", "engine") or "auto"
    lang = settings.get("speech", "language") or "auto"
    duration = probe(video).duration
    if subtitle_file:
        return parse_subtitles(subtitle_file), f"file phụ đề {Path(subtitle_file).name}"
    if engine == "subtitle":
        side = find_sidecar(video)
        if not side:
            raise TranscriptError("Chọn file phụ đề (.srt/.vtt/.ass) cho video.")
        return parse_subtitles(side), f"file phụ đề {side.name}"
    if engine == "auto":
        side = find_sidecar(video)
        if side:
            return parse_subtitles(side), f"phụ đề cạnh video ({side.name})"
        emb = embedded(video, work, cancel)
        if len(emb) >= 10:
            return emb, "phụ đề nhúng trong video"
    # chuỗi dự phòng: online (nhanh, nếu có mạng + key) <-> trên máy
    online = hybrid.stt_online(settings)
    if engine in ("groq", "openai"):
        chain = [engine, *[p for p in online if p != engine], "gpu", "local"]
    elif engine in ("gpu", "local"):
        chain = [engine, *(["local"] if engine == "gpu" else []), *online]
    elif settings.mode == "offline":
        chain = ["gpu", "local"]
    else:
        chain = [*online, "gpu", "local"]
    chain = list(dict.fromkeys(chain))
    last: Exception | None = None
    for i, eng in enumerate(chain):
        if eng in ("groq", "openai") and not (settings.key(eng) and hybrid.online_allowed(settings)):
            continue
        if eng == "gpu":
            import os

            if os.name != "nt":
                continue
        try:
            if eng in ("groq", "openai"):
                return _api_whisper(video, work, duration, settings, eng, lang, prompt, log, progress, cancel), \
                    f"{eng.capitalize()} Whisper (online)"
            if eng == "gpu":
                return _gpu_whisper(video, work, duration, settings, lang, prompt, log, progress, cancel), \
                    "Whisper card đồ họa (trên máy)"
            return _local_whisper(video, work, duration, settings, lang, prompt, log, progress, cancel), \
                "Whisper trên máy (CPU)"
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            if i + 1 < len(chain):
                log(f"{ENGINES.get(eng, eng)} lỗi ({e}) - tự chuyển cách khác.", "warn")
    raise TranscriptError(f"Không lấy được lời thoại: {last}")


# câu "ảo" Whisper hay tự thêm khi đoạn im lặng / có nhạc
JUNK = re.compile(
    r"(字幕(由|提供|制作|志愿者)|Amara\.org|请不吝点赞|点赞.*订阅|订阅.*转发|明镜与点点|"
    r"thanks? (you )?for watching|subtitles? by|subscribe to|ご視聴ありがとうございました|"
    r"시청해 ?주셔서 감사합니다|MBC 뉴스|Sous-titrage|Untertitel)", re.I)


def clean_lines(segs: list[dict]) -> list[dict]:
    """Bỏ câu rác, câu lặp do Whisper; gộp mẩu câu quá ngắn liền nhau cho dịch & đọc tự nhiên hơn."""
    out: list[dict] = []
    for s in sorted(segs, key=lambda x: x["start"]):
        t = " ".join((s.get("text") or "").split())
        if not t or JUNK.search(t) or re.fullmatch(r"[\W_]*", t):
            continue
        st, en = float(s["start"]), max(float(s["end"]), float(s["start"]) + 0.3)
        if out and out[-1]["text"].endswith(t) and st - out[-1]["end"] < 1.0:  # Whisper lặp lại câu vừa nói
            out[-1]["end"] = en
            continue
        if out:
            p = out[-1]
            short = (p["end"] - p["start"] < 1.2 or len(p["text"]) < 12) and not re.search(r"[.!?。！？…]$", p["text"])
            if short and st - p["end"] < 0.35 and en - p["start"] < 7 and len(p["text"]) + len(t) < 90:
                p["text"] = (p["text"] + ("" if _cjk(p["text"]) else " ") + t).strip()
                p["end"] = en
                continue
        out.append({"start": round(st, 2), "end": round(en, 2), "text": t})
    for a, b in zip(out, out[1:]):  # không chồng lên nhau
        if a["end"] > b["start"]:
            a["end"] = round(max(a["start"] + 0.3, b["start"]), 2)
    return out


def _cjk(t: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]$", t))


def fmt(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def to_prompt_text(segs: list[dict]) -> str:
    return "\n".join(f"[{fmt(s['start'])}] {s['text']}" for s in segs)
