"""Kiểm tra & tự cài các thành phần app cần: thư viện Python, FFmpeg, model AI.

Dùng trong mục "🧩 Thành phần & sửa lỗi" và tự gọi khi người dùng chọn một công cụ chưa cài.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

from .config import Settings, app_home
from .ffmpeg_utils import Cancelled

# key -> mô tả. kind: pip | ffmpeg | model
COMPONENTS: dict[str, dict] = {
    "ffmpeg": {"name": "FFmpeg (cắt ghép video, phụ đề)", "kind": "ffmpeg", "required": True},
    "edge_tts": {"name": "Edge TTS - giọng đọc miễn phí", "kind": "pip", "module": "edge_tts",
                 "pip": ["edge-tts>=7.2"], "required": True, "upgrade": True},
    "faster_whisper": {"name": "Whisper offline - nhận dạng lời thoại", "kind": "pip", "module": "faster_whisper",
                       "pip": ["faster-whisper>=1.1"], "required": True},
    "scenedetect": {"name": "PySceneDetect - dò chuyển cảnh", "kind": "pip", "module": "scenedetect",
                    "pip": ["scenedetect>=0.6.4", "opencv-python-headless>=4.8"], "required": True},
    "yt_dlp": {"name": "yt-dlp - tải phim từ link", "kind": "pip", "module": "yt_dlp", "pip": ["yt-dlp"],
               "required": True, "upgrade": True},
    "anthropic": {"name": "Anthropic SDK - kết nối Claude", "kind": "pip", "module": "anthropic",
                  "pip": ["anthropic>=2.8"], "required": True},
    "num2words": {"name": "num2words - đọc số (ngôn ngữ khác)", "kind": "pip", "module": "num2words",
                  "pip": ["num2words>=0.5.13"], "required": True},
    "gtts": {"name": "gTTS - giọng Google Translate", "kind": "pip", "module": "gtts", "pip": ["gTTS>=2.5"]},
    "vieneu": {"name": "⭐ VieNeu-TTS - giọng Việt AI phát âm chuẩn", "kind": "pip", "module": "vieneu",
               "pip": ["vieneu>=3.8"], "recommended": True},
    "piper": {"name": "Piper - giọng offline nhẹ", "kind": "pip", "module": "piper", "pip": ["piper-tts>=1.2"]},
    "pyttsx3": {"name": "Giọng hệ điều hành (pyttsx3)", "kind": "pip", "module": "pyttsx3", "pip": ["pyttsx3>=2.98"]},
    "xtts": {"name": "Coqui XTTS - nhân bản giọng (nặng ~2GB)", "kind": "pip", "module": "TTS", "pip": ["coqui-tts"]},
    "whisper_model": {"name": "Model Whisper (theo cấu hình)", "kind": "model", "needs": ["faster_whisper"],
                      "recommended": True},
    "vieneu_model": {"name": "Model VieNeu-TTS", "kind": "model", "needs": ["vieneu"], "recommended": True},
    "piper_vi": {"name": "Giọng Piper tiếng Việt (vais1000)", "kind": "model", "needs": ["piper"]},
}

ENGINE_NEEDS = {"edge": ["edge_tts"], "gtts": ["gtts"], "vieneu": ["vieneu"], "piper": ["piper"],
                "sapi": ["pyttsx3"], "xtts": ["xtts"]}
STT_NEEDS = {"faster_whisper": ["faster_whisper"]}


class InstallError(RuntimeError):
    pass


def python_exe() -> str:
    """Python để chạy pip / tiến trình phụ (không dùng pythonw.exe vì không có console)."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def _nowin() -> dict:
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def is_module(mod: str) -> bool:
    importlib.invalidate_caches()
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


# ------------------------------------------------------------------ FFmpeg
def ffmpeg_dir() -> Path:
    return app_home() / "ffmpeg" / "bin"


def ffmpeg_status() -> tuple[bool, str]:
    from .ffmpeg_utils import ffmpeg_exe, ffprobe_exe

    try:
        exe = ffmpeg_exe()
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=30,
                             encoding="utf-8", errors="replace", **_nowin()).stdout
    except Exception as e:  # noqa: BLE001
        return False, f"Không chạy được {exe}: {e}"
    if " subtitles " not in out:
        return False, f"{exe} thiếu libass (không chèn được phụ đề) - nên tải bản đầy đủ."
    if not ffprobe_exe():
        return True, f"{exe} (thiếu ffprobe - vẫn chạy được)"
    return True, exe


FFMPEG_URLS = [
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
]


def install_ffmpeg(settings: Settings, log, progress, cancel) -> str:
    if not sys.platform.startswith("win"):
        raise InstallError("Trên Linux/macOS hãy cài bằng: sudo apt install ffmpeg  /  brew install ffmpeg")
    dest = ffmpeg_dir()
    dest.mkdir(parents=True, exist_ok=True)
    zpath = dest.parent / "ffmpeg.zip"
    last = None
    for url in FFMPEG_URLS:
        try:
            log(f"Tải FFmpeg: {url}")
            _download(url, zpath, settings, progress, cancel, "Tải FFmpeg")
            with zipfile.ZipFile(zpath) as z:
                got = 0
                for n in z.namelist():
                    base = n.rsplit("/", 1)[-1].lower()
                    if base in ("ffmpeg.exe", "ffprobe.exe"):
                        with z.open(n) as src, open(dest / base, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        got += 1
            zpath.unlink(missing_ok=True)
            if got >= 1:
                from .ffmpeg_utils import set_ffmpeg_path

                settings.set("paths", "ffmpeg", str(dest / "ffmpeg.exe"))
                settings.save()
                set_ffmpeg_path(str(dest / "ffmpeg.exe"))
                log(f"✅ Đã cài FFmpeg vào {dest}")
                return str(dest / "ffmpeg.exe")
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"Không tải được từ nguồn này: {e}", level="warn")
    raise InstallError(f"Không tải được FFmpeg: {last}")


def _download(url: str, dest: Path, settings: Settings, progress, cancel, label: str) -> None:
    s = requests.Session()
    p = (settings.get("api", "proxy") or "").strip()
    if p:
        s.proxies = {"http": p, "https": p}
    with s.get(url, stream=True, timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        done = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                fh.write(chunk)
                done += len(chunk)
                if total:
                    progress(done / total, f"{label} {done / 1e6:.0f}/{total / 1e6:.0f} MB")
        os.replace(tmp, dest)


# ------------------------------------------------------------------ pip
def pip_install(packages: list[str], log, progress=None, cancel=None, upgrade: bool = False) -> None:
    if getattr(sys, "frozen", False):
        raise InstallError("Bản .exe đóng gói sẵn không cài thêm thư viện được - hãy dùng bản chạy bằng Python.")
    cmd = [python_exe(), "-m", "pip", "install", "--disable-pip-version-check"]
    if upgrade:
        cmd.append("--upgrade")
    cmd += packages
    log("$ pip install " + " ".join(packages))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", **_nowin())
    tail = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail = (tail + [line])[-20:]
        if line.startswith(("Collecting", "Downloading", "Installing", "Successfully", "ERROR")):
            log("   " + line[:160])
            if progress:
                progress(0.5, line[:80])
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise Cancelled()
    proc.wait()
    importlib.invalidate_caches()
    if proc.returncode != 0:
        raise InstallError("Cài thư viện lỗi:\n" + "\n".join(tail[-8:]))


# ------------------------------------------------------------------ model
def whisper_model_name(settings: Settings) -> str:
    from .transcribe import resolve_model

    return resolve_model(settings.get("transcribe", "model", "auto"), settings.get("transcribe", "device", "auto"))


def whisper_model_ready(settings: Settings) -> bool:
    root = settings.models_dir() / "whisper"
    name = whisper_model_name(settings)
    return any(root.glob(f"models--*faster-whisper-{name}*/snapshots/*/model.bin")) or \
        any(root.glob(f"models--*{name}*/snapshots/*/model.bin"))


def download_whisper(settings: Settings, log, progress, cancel) -> None:
    from faster_whisper.utils import download_model

    name = whisper_model_name(settings)
    log(f"Tải model Whisper '{name}' (vài trăm MB - vài GB)...")
    progress(0.1, f"Tải model Whisper {name}")
    download_model(name, cache_dir=str(settings.models_dir() / "whisper"))
    log(f"✅ Model Whisper '{name}' đã sẵn sàng.")


def vieneu_model_ready(settings: Settings) -> bool:
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return any(hub.glob("models--pnnbao*VieNeu*")) if hub.exists() else False


def download_vieneu(settings: Settings, log, progress, cancel) -> None:
    from .tts import _VIENEU

    mode = settings.get("voice", "model") or "v3turbo"
    mode = mode if mode in ("v3turbo", "v3nano") else "v3turbo"
    log(f"Tải & nạp model VieNeu-TTS ({mode})... lần đầu có thể mất vài phút.")
    progress(0.2, "Tải model VieNeu-TTS")
    from vieneu import Vieneu

    _VIENEU[mode] = Vieneu(mode=mode)
    log("✅ Model VieNeu-TTS đã sẵn sàng.")


def piper_vi_ready(settings: Settings) -> bool:
    from .tts import piper_dir

    return (piper_dir(settings) / "vi_VN-vais1000-medium.onnx").exists()


def download_piper_vi(settings: Settings, log, progress, cancel) -> None:
    from .tts import piper_catalog, piper_download

    cat = piper_catalog(settings)
    key = "vi_VN-vais1000-medium"
    if key not in cat:
        key = next((k for k in cat if k.startswith("vi_VN")), None)
        if not key:
            raise InstallError("Không thấy giọng tiếng Việt trong kho Piper.")
    piper_download(key, cat[key], settings, progress)
    log(f"✅ Đã tải giọng Piper {key}")


# ------------------------------------------------------------------ trạng thái & cài
def status(key: str, settings: Settings) -> tuple[bool, str]:
    c = COMPONENTS[key]
    if c["kind"] == "ffmpeg":
        return ffmpeg_status()
    if c["kind"] == "pip":
        ok = is_module(c["module"])
        return ok, "đã cài" if ok else "chưa cài"
    if any(not is_module(COMPONENTS[n]["module"]) for n in c.get("needs", [])):
        return False, "cần cài thư viện trước"
    ready = {"whisper_model": whisper_model_ready, "vieneu_model": vieneu_model_ready,
             "piper_vi": piper_vi_ready}[key](settings)
    extra = f" ({whisper_model_name(settings)})" if key == "whisper_model" else ""
    return ready, ("đã tải" if ready else "chưa tải") + extra


def install(key: str, settings: Settings, log, progress, cancel) -> None:
    c = COMPONENTS[key]
    for dep in c.get("needs", []):
        if not status(dep, settings)[0]:
            install(dep, settings, log, progress, cancel)
    if c["kind"] == "ffmpeg":
        install_ffmpeg(settings, log, progress, cancel)
    elif c["kind"] == "pip":
        pip_install(c["pip"], log, progress, cancel, upgrade=c.get("upgrade", False))
        if not is_module(c["module"]):
            raise InstallError(f"Đã chạy pip nhưng vẫn chưa nạp được {c['module']}. Hãy khởi động lại app.")
        log(f"✅ Đã cài {c['name']}")
    else:
        {"whisper_model": download_whisper, "vieneu_model": download_vieneu,
         "piper_vi": download_piper_vi}[key](settings, log, progress, cancel)


def missing_for(settings: Settings, engine: str | None = None, stt: str | None = None,
                include_models: bool = False) -> list[str]:
    """Các thành phần còn thiếu cho engine giọng / nhận dạng đang chọn."""
    keys = ["ffmpeg"] + ENGINE_NEEDS.get(engine or "", []) + STT_NEEDS.get(stt or "", [])
    if include_models:
        if stt == "faster_whisper":
            keys.append("whisper_model")
        if engine == "vieneu":
            keys.append("vieneu_model")
    out = []
    for k in dict.fromkeys(keys):
        try:
            ok, _ = status(k, settings)
        except Exception:
            ok = False
        if not ok:
            out.append(k)
    return out


def install_many(keys: list[str], settings: Settings, log, progress, cancel) -> list[str]:
    """Cài lần lượt; trả về danh sách lỗi (không dừng giữa chừng)."""
    errors = []
    for i, k in enumerate(keys):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        sub = (lambda p, m="", i=i: progress((i + max(0.0, min(1.0, p))) / len(keys), m))
        log(f"▶ [{i + 1}/{len(keys)}] {COMPONENTS[k]['name']}")
        try:
            install(k, settings, log, sub, cancel)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            errors.append(f"{COMPONENTS[k]['name']}: {e}")
            log(f"❌ {COMPONENTS[k]['name']}: {e}", level="error")
    progress(1.0, "Xong")
    return errors


def logs_dir() -> Path:
    d = app_home() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
