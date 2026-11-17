"""Nhận dạng thoại bằng CARD ĐỒ HỌA bất kỳ (AMD / Intel / NVIDIA) qua whisper.cpp (MIT) dựng với Vulkan.

faster-whisper chỉ dùng được GPU NVIDIA (CUDA); với card AMD như RX 5700 XT nó phải chạy CPU (phim 2 tiếng
mất 40-70 phút). whisper.cpp bản Vulkan chạy thẳng trên card AMD, nhanh gấp nhiều lần.

- Chương trình: thư mục có whisper-cli.exe (tự tải bản dựng sẵn, hoặc bạn chọn thư mục whisper.cpp của mình).
- Model: ggml-*.bin từ huggingface.co/ggerganov/whisper.cpp (tự tải lần đầu).
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import requests

from .config import Settings
from .ffmpeg_utils import Cancelled, _no_window_kwargs

WHISPER_TAG = "v1.9.5"
RELEASE_TAG = f"whisper-vulkan-{WHISPER_TAG}"
ASSET = "whisper-vulkan-win-x64.zip"
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{name}.bin"
# tên model của app -> file ggml (bản lượng tử hóa q8_0: gần như không giảm độ chính xác, nhẹ & nhanh hơn)
MODEL_FILES = {
    "large-v3-turbo": "large-v3-turbo-q8_0", "large-v3": "large-v3-q5_0", "medium": "medium-q8_0",
    "small": "small-q8_0", "base": "base-q8_0", "tiny": "tiny-q8_0", "distil-large-v3": "large-v3-turbo-q8_0",
}
EXE_NAMES = ("whisper-cli.exe", "whisper-cli", "main.exe")


class WhisperGPUError(RuntimeError):
    pass


def bin_url(settings: Settings) -> str:
    custom = (settings.get("transcribe", "wcpp_url") or "").strip()
    if custom:
        return custom
    repo = (settings.get("ui", "update_repo") or "tientran90td-commits/vtgt-cap-nhat").strip().strip("/")
    return f"https://github.com/{repo}/releases/download/{RELEASE_TAG}/{ASSET}"


def tool_dir(settings: Settings) -> Path:
    return settings.models_dir() / "whisper.cpp"


def find_exe(settings: Settings) -> Path | None:
    """whisper-cli: thư mục người dùng chọn -> bản app đã tải -> PATH."""
    dirs = []
    if settings.get("transcribe", "wcpp_dir"):
        dirs.append(Path(settings.get("transcribe", "wcpp_dir")))
    dirs.append(tool_dir(settings))
    for d in dirs:
        if d.is_file() and d.name.lower() in EXE_NAMES:
            return d
        if d.is_dir():
            for n in EXE_NAMES:
                for c in (d / n, *d.glob(f"*/{n}"), *d.glob(f"*/*/{n}")):
                    if c.is_file():
                        return c
    w = shutil.which("whisper-cli")
    return Path(w) if w else None


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    p = (settings.get("api", "proxy") or "").strip()
    if p:
        s.proxies = {"http": p, "https": p}
    return s


def _download(settings, url, log, progress, cancel, lo, hi, label) -> bytes:
    s = _session(settings)
    buf = io.BytesIO()
    with s.get(url, stream=True, timeout=60, allow_redirects=True) as r:
        if r.status_code != 200:
            raise WhisperGPUError(f"Tải {label} lỗi HTTP {r.status_code}: {url}")
        total = int(r.headers.get("content-length") or 0)
        for chunk in r.iter_content(1 << 20):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            buf.write(chunk)
            if total:
                progress(lo + (hi - lo) * buf.tell() / total, f"Tải {label} {buf.tell() / 1e6:.0f}/{total / 1e6:.0f} MB")
    return buf.getvalue()


def ensure_exe(settings: Settings, log, progress, cancel) -> Path:
    exe = find_exe(settings)
    if exe:
        return exe
    if os.name != "nt":
        raise WhisperGPUError("Chưa có whisper-cli. Trên Linux/macOS hãy tự dựng whisper.cpp (cmake -DGGML_VULKAN=ON "
                              "hoặc Metal) rồi chọn thư mục ở mục Nhận dạng thoại.")
    url = bin_url(settings)
    log(f"Tải whisper.cpp bản Vulkan (chạy bằng card đồ họa) từ {url} ...")
    try:
        data = _download(settings, url, log, progress, cancel, 0.0, 0.05, "whisper.cpp")
    except WhisperGPUError as e:
        raise WhisperGPUError(f"{e}\n\nChưa có bản whisper.cpp Vulkan dựng sẵn. Bạn có thể tải/dựng whisper.cpp bản "
                              "Vulkan rồi chọn thư mục chứa whisper-cli.exe ở mục Nhận dạng thoại.") from e
    d = tool_dir(settings)
    d.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for m in z.infolist():
            dest = (d / m.filename).resolve()
            if d.resolve() in dest.parents:
                z.extract(m, d)
    exe = find_exe(settings)
    if not exe:
        raise WhisperGPUError("Bản tải về không có whisper-cli.exe")
    log(f"Đã cài whisper.cpp tại {exe.parent}")
    return exe


def ensure_model(settings: Settings, model: str, log, progress, cancel) -> Path:
    name = MODEL_FILES.get(model, model)
    d = settings.models_dir() / "whisper.cpp" / "models"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"ggml-{name}.bin"
    if f.exists() and f.stat().st_size > 10_000_000:
        return f
    log(f"Tải model Whisper ggml-{name} (lần đầu, vài trăm MB)...")
    url = MODEL_URL.format(name=name)
    s = _session(settings)
    tmp = f.with_suffix(".part")
    with s.get(url, stream=True, timeout=60) as r:
        if r.status_code != 200:
            raise WhisperGPUError(f"Tải model lỗi HTTP {r.status_code} ({url}). Cần Internet tới huggingface.co.")
        total = int(r.headers.get("content-length") or 0)
        got = 0
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                fh.write(chunk)
                got += len(chunk)
                if total:
                    progress(0.05 + 0.1 * got / total, f"Tải model {got / 1e6:.0f}/{total / 1e6:.0f} MB")
    os.replace(tmp, f)
    return f


def parse_json(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8", errors="replace"))
    out = []
    for seg in data.get("transcription", []):
        off = seg.get("offsets") or {}
        text = (seg.get("text") or "").strip()
        if not text or text in ("[BLANK_AUDIO]", "[Music]", "(music)"):
            continue
        st, en = float(off.get("from", 0)) / 1000, float(off.get("to", 0)) / 1000
        out.append({"start": round(st, 2), "end": round(max(en, st + 0.2), 2), "text": text})
    return out


def transcribe(wav: str, duration: float, settings: Settings, model: str, lang: str | None, log, progress, cancel,
               prompt: str = "", work_dir: Path | None = None) -> list[dict]:
    exe = ensure_exe(settings, log, progress, cancel)
    mfile = ensure_model(settings, model, log, progress, cancel)
    out_base = Path(work_dir or Path(wav).parent) / "whisper_gpu"
    out_json = out_base.with_suffix(".json")
    out_json.unlink(missing_ok=True)
    threads = max(2, min(8, (os.cpu_count() or 4) - 2))
    cmd = [str(exe), "-m", str(mfile), "-f", str(wav), "-l", lang or "auto", "-oj", "-of", str(out_base),
           "-t", str(threads), "-pp", "-mc", "64", "-sns"]
    if prompt:
        cmd += ["--prompt", prompt[:220]]
    if settings.get("transcribe", "device", "auto") == "cpu":
        cmd.append("-ng")
    log(f"Nhận dạng thoại bằng whisper.cpp ({mfile.stem.replace('ggml-', '')}) ...")
    proc = subprocess.Popen(cmd, cwd=str(exe.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, **_no_window_kwargs())
    tail: list[str] = []
    gpu = None
    no_gpu = False
    try:
        for raw in iter(proc.stdout.readline, b""):
            if cancel is not None and cancel.is_set():
                proc.kill()
                raise Cancelled()
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            tail = (tail + [line])[-15:]
            m = re.search(r"progress\s*=\s*(\d+)%", line)
            if m:
                pct = min(100, int(m.group(1)))
                progress(0.15 + 0.85 * pct / 100, f"Nhận dạng thoại {pct}% ({int(duration * pct / 100)}/{int(duration)}s)")
                continue
            if gpu is None and re.match(r"ggml_vulkan:\s*\d+\s*=", line):
                gpu = line.split("=", 1)[1].split("|")[0].strip()
                log(f"🎮 Dùng card đồ họa: {gpu}")
            if "No devices found" in line or "no GPU found" in line.lower():
                no_gpu = True
    finally:
        try:
            proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        proc.wait()
    if no_gpu and not gpu:
        log("whisper.cpp không thấy card đồ họa (Vulkan) - đã chạy bằng CPU. Hãy cập nhật driver card đồ họa.",
            level="warn")
    if proc.returncode != 0 or not out_json.exists():
        raise WhisperGPUError("whisper.cpp lỗi (mã %s):\n%s" % (proc.returncode, "\n".join(tail[-6:])))
    segs = parse_json(out_json)
    progress(1.0, "Xong nhận dạng thoại")
    log(f"Nhận dạng được {len(segs)} câu thoại.")
    return segs
