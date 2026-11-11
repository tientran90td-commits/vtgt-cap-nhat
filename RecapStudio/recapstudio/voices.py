"""Giọng đọc thuyết minh: nhiều công cụ, online lẫn offline. Mọi giọng ra file WAV 48kHz đã chuẩn hóa.

Giọng online (Edge, OpenAI, ElevenLabs, Gemini, gTTS) đọc nhiều đoạn cùng lúc; giọng offline (VieNeu, Piper,
Windows) đọc lần lượt.
"""
from __future__ import annotations

import asyncio
import base64
import os
import re
import subprocess
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from .config import Settings, app_home
from .media import Cancelled, duration, no_window, run

ENGINES = {
    "edge": {"name": "Microsoft Edge - miễn phí, 400+ giọng (cần mạng)", "online": True},
    "vieneu": {"name": "⭐ VieNeu - giọng Việt AI offline (Ngọc Huyền, Hải Đăng...)", "online": False},
    "gtts": {"name": "Google Translate - miễn phí", "online": True},
    "openai": {"name": "OpenAI TTS (cần key)", "online": True, "key": "openai"},
    "elevenlabs": {"name": "ElevenLabs - giọng siêu thật (cần key)", "online": True, "key": "elevenlabs"},
    "gemini": {"name": "Google Gemini TTS (cần key Gemini)", "online": True, "key": "gemini"},
    "piper": {"name": "Piper - offline, nhẹ", "online": False},
    "sapi": {"name": "Giọng có sẵn của Windows - offline", "online": False},
}
SAMPLE = "Xin chào! Đây là giọng đọc thử cho video tóm tắt phim của bạn."

_EDGE_DEFAULT = [("vi-VN-HoaiMyNeural", "Hoài My · nữ · tiếng Việt"), ("vi-VN-NamMinhNeural", "Nam Minh · nam · tiếng Việt"),
                 ("en-US-AndrewMultilingualNeural", "Andrew · nam · đa ngôn ngữ"),
                 ("en-US-AvaMultilingualNeural", "Ava · nữ · đa ngôn ngữ"), ("en-US-GuyNeural", "Guy · nam · English"),
                 ("en-US-JennyNeural", "Jenny · nữ · English")]
_VIENEU = [("Ngọc Huyền", "Ngọc Huyền · nữ · miền Bắc · tự nhiên, hoạt ngôn"), ("Hải Đăng", "Hải Đăng · nam · miền Bắc"),
           ("Trúc Ly", "Trúc Ly · nữ · miền Bắc"), ("Thiện Minh", "Thiện Minh · nam · kể chuyện"),
           ("Mai Anh", "Mai Anh · nữ · tin tức"), ("Ngọc Linh", "Ngọc Linh · nữ · kể chuyện"),
           ("Thùy Dung", "Thùy Dung · nữ · miền Nam"), ("Thái Sơn", "Thái Sơn · nam · miền Nam · kể chuyện"),
           ("Quang Sơn", "Quang Sơn · nam · miền Trung"), ("Mỹ Duyên", "Mỹ Duyên · nữ · miền Nam · đọc truyện"),
           ("Đức Trí", "Đức Trí · nam · miền Nam · đọc truyện"), ("Adam bựa", "Adam bựa · nam · hài hước")]
_OPENAI = ["alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"]
_GEMINI = ["Kore", "Puck", "Charon", "Zephyr", "Fenrir", "Leda", "Orus", "Aoede", "Sulafat", "Achird", "Despina",
           "Gacrux", "Iapetus", "Rasalgethi", "Vindemiatrix"]
_PIPER = [("vi_VN-vais1000-medium", "Tiếng Việt · vais1000 (khuyên dùng)"), ("vi_VN-25hours_single-low", "Tiếng Việt · 25hours"),
          ("vi_VN-vivos-x_low", "Tiếng Việt · vivos"), ("en_US-lessac-medium", "English · Lessac"),
          ("en_US-ryan-high", "English · Ryan")]


class TTSError(RuntimeError):
    pass


_EDGE_CACHE: list | None = None
_OFFLINE_LOCK = threading.Lock()
_VIENEU_MODEL = None


# ------------------------------------------------------------------ danh sách giọng
def list_voices(engine: str, settings: Settings) -> list[tuple[str, str]]:
    global _EDGE_CACHE
    if engine == "edge":
        if _EDGE_CACHE is None:
            try:
                import edge_tts

                vs = asyncio.run(edge_tts.list_voices())
                vs.sort(key=lambda v: (not v["ShortName"].startswith("vi-"), v["Locale"], v["ShortName"]))
                _EDGE_CACHE = [(v["ShortName"], f"{v['ShortName'].split('-')[-1].replace('Neural', '')} · "
                                f"{'nữ' if v.get('Gender') == 'Female' else 'nam'} · {v['Locale']}") for v in vs]
            except Exception:  # noqa: BLE001 - không có mạng: dùng danh sách có sẵn, lần sau thử lại
                return _EDGE_DEFAULT
        return _EDGE_CACHE
    if engine == "vieneu":
        return _VIENEU
    if engine == "gtts":
        return [("vi", "Tiếng Việt"), ("en", "English"), ("zh-CN", "中文"), ("ja", "日本語"), ("ko", "한국어"),
                ("th", "ไทย"), ("fr", "Français"), ("es", "Español")]
    if engine == "openai":
        return [(v, v) for v in _OPENAI]
    if engine == "gemini":
        return [(v, v) for v in _GEMINI]
    if engine == "elevenlabs":
        key = settings.key("elevenlabs")
        if key:
            try:
                r = requests.get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}, timeout=20,
                                 proxies=settings.proxies())
                if r.ok:
                    return [(v["voice_id"], v["name"]) for v in r.json().get("voices", [])]
            except requests.RequestException:
                pass
        return [("21m00Tcm4TlvDq8ikWAM", "Rachel"), ("pNInz6obpgDQGcFmaJgB", "Adam")]
    if engine == "piper":
        return _PIPER
    if engine == "sapi":
        return _sapi_voices()
    return []


def _sapi_voices() -> list[tuple[str, str]]:
    if os.name != "nt":
        return []
    ps = ("Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer)"
          ".GetInstalledVoices() | % { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                           timeout=30, **no_window())
        return [(ln.split("|")[0], ln.replace("|", " · ")) for ln in r.stdout.splitlines() if "|" in ln]
    except (OSError, subprocess.SubprocessError):
        return []


# ------------------------------------------------------------------ đọc số tiếng Việt (cho giọng offline)
_DIG = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read3(n: int, full: bool) -> str:
    h, t, u = n // 100, n // 10 % 10, n % 10
    out = []
    if h or full:
        out += [_DIG[h], "trăm"]
    if t == 0:
        if u and (h or full):
            out.append("linh")
    elif t == 1:
        out.append("mười")
    else:
        out += [_DIG[t], "mươi"]
    if u:
        if t >= 2 and u == 1:
            out.append("mốt")
        elif t >= 1 and u == 5:
            out.append("lăm")
        elif t >= 2 and u == 4:
            out.append("tư")
        else:
            out.append(_DIG[u])
    return " ".join(out)


def vi_number(n: int) -> str:
    if n == 0:
        return "không"
    units = ["", "nghìn", "triệu", "tỷ"]
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    out = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        out.append(_read3(g, full=i < len(groups) - 1) + (" " + units[min(i, 3)] if i else ""))
    return " ".join(out).strip()


def vi_normalize(text: str) -> str:
    def num(m):
        s = m.group(0)
        pct = s.endswith("%")
        s = s.rstrip("%")
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")
        if "," in s:
            a, b = s.split(",", 1)
            words = vi_number(int(a)) + " phẩy " + " ".join(_DIG[int(c)] for c in b if c.isdigit())
        else:
            words = vi_number(int(s))
        return words + (" phần trăm" if pct else "")
    return re.sub(r"\d{1,3}(?:\.\d{3})+%?|\d+(?:,\d+)?%?", num, text)


# ------------------------------------------------------------------ từng công cụ
def _edge(text, voice, out: Path, speed: int, settings) -> Path:
    import edge_tts

    mp3 = out.with_suffix(".mp3")

    async def go():
        c = edge_tts.Communicate(text, voice, rate=f"{speed:+d}%", proxy=(settings.get("net", "proxy") or None))
        await c.save(str(mp3))
    last = None
    for _ in range(3):
        try:
            asyncio.run(go())
            if mp3.exists() and mp3.stat().st_size > 500:
                return mp3
        except Exception as e:  # noqa: BLE001 - mạng chập chờn
            last = e
    raise TTSError(f"Edge TTS lỗi: {last}")


def _gtts(text, voice, out: Path, settings) -> Path:
    from gtts import gTTS

    mp3 = out.with_suffix(".mp3")
    gTTS(text=text, lang=voice or "vi").save(str(mp3))
    return mp3


def _openai(text, voice, out: Path, speed: int, settings) -> Path:
    body = {"model": "gpt-4o-mini-tts", "input": text, "voice": voice or "nova", "response_format": "mp3",
            "speed": max(0.25, min(4.0, 1 + speed / 100)),
            "instructions": "Đọc tự nhiên, rõ ràng, truyền cảm như người dẫn chuyện phim."}
    r = requests.post("https://api.openai.com/v1/audio/speech", json=body, timeout=180, proxies=settings.proxies(),
                      headers={"Authorization": f"Bearer {settings.key('openai')}"})
    if r.status_code >= 400:
        raise TTSError(f"OpenAI TTS lỗi {r.status_code}: {r.text[:200]}")
    mp3 = out.with_suffix(".mp3")
    mp3.write_bytes(r.content)
    return mp3


def _elevenlabs(text, voice, out: Path, settings) -> Path:
    body = {"text": text, "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.25, "use_speaker_boost": True}}
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}", json=body, timeout=180,
                      params={"output_format": "mp3_44100_128"}, proxies=settings.proxies(),
                      headers={"xi-api-key": settings.key("elevenlabs"), "Accept": "audio/mpeg"})
    if r.status_code >= 400:
        raise TTSError(f"ElevenLabs lỗi {r.status_code}: {r.text[:200]}")
    mp3 = out.with_suffix(".mp3")
    mp3.write_bytes(r.content)
    return mp3


def _gemini(text, voice, out: Path, settings) -> Path:
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice or "Kore"}}}}}
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
    for attempt in range(4):
        r = requests.post(url, params={"key": settings.key("gemini")}, json=body, timeout=180,
                          proxies=settings.proxies())
        if r.status_code in (429, 500, 503) and attempt < 3:
            threading.Event().wait(5 * (attempt + 1))
            continue
        break
    if r.status_code >= 400:
        raise TTSError(f"Gemini TTS lỗi {r.status_code}: {r.text[:200]}")
    try:
        part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError) as e:
        raise TTSError("Gemini TTS trả về lạ.") from e
    rate = int(re.search(r"rate=(\d+)", part.get("mimeType", "rate=24000")).group(1))
    wav = out.with_suffix(".raw.wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(base64.b64decode(part["data"]))
    return wav


def _vieneu(text, voice, out: Path, settings) -> Path:
    global _VIENEU_MODEL
    try:
        from vieneu import Vieneu
    except ImportError as e:
        raise TTSError("Chưa cài VieNeu: chạy install.bat (hoặc pip install vieneu). Lần đầu tự tải model.") from e
    with _OFFLINE_LOCK:
        if _VIENEU_MODEL is None:
            _VIENEU_MODEL = Vieneu(mode="v3turbo")
        audio = _VIENEU_MODEL.infer(text, voice=voice or "Ngọc Huyền")
        wav = out.with_suffix(".raw.wav")
        _VIENEU_MODEL.save(audio, str(wav))
    return wav


def piper_model(name: str, settings: Settings, log=None) -> Path:
    d = app_home() / "piper"
    d.mkdir(parents=True, exist_ok=True)
    onnx = d / f"{name}.onnx"
    if onnx.exists() and (d / f"{name}.onnx.json").exists():
        return onnx
    lang_region, voice, quality = name.split("-", 2)
    base = (f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang_region.split('_')[0]}/{lang_region}/"
            f"{voice}/{quality}/{name}")
    if log:
        log(f"Tải giọng Piper {name} (lần đầu)...")
    for suffix in (".onnx", ".onnx.json"):
        r = requests.get(base + suffix, timeout=300, proxies=settings.proxies())
        if r.status_code != 200:
            raise TTSError(f"Tải giọng Piper lỗi HTTP {r.status_code}")
        (d / f"{name}{suffix}").write_bytes(r.content)
    return onnx


def _piper(text, voice, out: Path, speed: int, settings, log=None) -> Path:
    try:
        from piper import PiperVoice
    except ImportError as e:
        raise TTSError("Chưa cài Piper: pip install piper-tts") from e
    model = piper_model(voice or _PIPER[0][0], settings, log)
    wav = out.with_suffix(".raw.wav")
    with _OFFLINE_LOCK:
        pv = PiperVoice.load(str(model))
        with wave.open(str(wav), "wb") as wf:
            if hasattr(pv, "synthesize_wav"):
                from piper import SynthesisConfig

                pv.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=1 / max(0.3, 1 + speed / 100)))
            else:
                pv.synthesize(text, wf, length_scale=1 / max(0.3, 1 + speed / 100))
    return wav


def _sapi(text, voice, out: Path, speed: int, settings) -> Path:
    if os.name != "nt":
        raise TTSError("Giọng Windows chỉ dùng được trên Windows.")
    txt = out.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    wav = out.with_suffix(".raw.wav")
    rate = max(-10, min(10, int(speed / 10)))
    ps = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          + (f"$s.SelectVoice('{voice}'); " if voice else "")
          + f"$s.Rate = {rate}; $s.SetOutputToWaveFile('{wav}'); "
          f"$s.Speak([IO.File]::ReadAllText('{txt}', [Text.Encoding]::UTF8)); $s.Dispose()")
    with _OFFLINE_LOCK:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=600, **no_window())
    txt.unlink(missing_ok=True)
    if not wav.exists():
        raise TTSError("Giọng Windows không đọc được.")
    return wav


# ------------------------------------------------------------------ chung
def synth(engine: str, text: str, voice: str, out: str | Path, settings: Settings, log=None) -> Path:
    """Đọc 1 đoạn -> WAV 48kHz mono đã chỉnh tốc độ/âm lượng."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    v = settings.section("voice")
    speed = int(v.get("speed", 0) or 0)
    text = " ".join((text or "").split())
    if not text:
        raise TTSError("Không có chữ để đọc.")
    if engine in ("vieneu", "piper", "sapi", "gtts"):
        text = vi_normalize(text)
    k = ENGINES.get(engine, {}).get("key")
    if k and not settings.key(k):
        raise TTSError(f"Chưa nhập API key cho {ENGINES[engine]['name']} (⚙️ Cài đặt & API).")
    if engine == "edge":
        raw, applied = _edge(text, voice, out, speed, settings), True
    elif engine == "gtts":
        raw, applied = _gtts(text, voice, out, settings), False
    elif engine == "openai":
        raw, applied = _openai(text, voice, out, speed, settings), True
    elif engine == "elevenlabs":
        raw, applied = _elevenlabs(text, voice, out, settings), False
    elif engine == "gemini":
        raw, applied = _gemini(text, voice, out, settings), False
    elif engine == "vieneu":
        raw, applied = _vieneu(text, voice, out, settings), False
    elif engine == "piper":
        raw, applied = _piper(text, voice, out, speed, settings, log), True
    elif engine == "sapi":
        raw, applied = _sapi(text, voice, out, speed, settings), True
    else:
        raise TTSError(f"Không có công cụ giọng '{engine}'")
    af = [f"volume={max(0.1, float(v.get('volume', 100) or 100) / 100):.2f}"]
    if not applied and speed:
        af.insert(0, f"atempo={max(0.5, min(2.0, 1 + speed / 100)):.3f}")
    tmp = out.with_suffix(".tmp.wav")
    run(["-i", str(raw), "-af", ",".join(af), "-ac", "1", "-ar", "48000", str(tmp)])
    if raw != tmp and raw.exists():
        raw.unlink(missing_ok=True)
    if duration(tmp) < 0.3:
        tmp.unlink(missing_ok=True)
        raise TTSError("Giọng đọc trả về rỗng - thử lại hoặc chọn giọng khác.")
    os.replace(tmp, out)
    return out


def synth_many(engine: str, items: list[tuple[str, Path]], voice: str, settings: Settings, log, progress,
               cancel) -> None:
    """Đọc nhiều đoạn: giọng online 4 đoạn cùng lúc, giọng offline lần lượt."""
    todo = [(t, p) for t, p in items if not (Path(p).exists() and Path(p).stat().st_size > 1000)]
    if not todo:
        return
    workers = 4 if ENGINES.get(engine, {}).get("online") else 1
    done = [0]
    lock = threading.Lock()

    def one(item):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        text, path = item
        for attempt in range(2):
            try:
                synth(engine, text, voice, path, settings, log)
                break
            except TTSError:
                if attempt == 1:
                    raise
        with lock:
            done[0] += 1
            progress(done[0] / len(todo), f"Đọc giọng {done[0]}/{len(todo)}")
    log(f"Đọc {len(todo)} đoạn giọng ({ENGINES[engine]['name'].split(' - ')[0]}"
        + (f", {workers} đoạn cùng lúc" if workers > 1 else "") + ")...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for f in [ex.submit(one, it) for it in todo]:
            f.result()


def default_voice(engine: str) -> str:
    return {"edge": "vi-VN-HoaiMyNeural", "vieneu": "Ngọc Huyền", "gtts": "vi", "openai": "nova", "gemini": "Kore",
            "elevenlabs": "21m00Tcm4TlvDq8ikWAM", "piper": _PIPER[0][0], "sapi": ""}.get(engine, "")

