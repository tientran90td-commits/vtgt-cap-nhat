"""📦 Thư viện & model: kiểm tra và tải về máy 1 lần tất cả những gì app cần để chạy không cần mạng.

- Giọng VieNeu (Ngọc Huyền, Hải Đăng...) - chạy trên máy.
- Đọc chữ trên hình (OCR) cho mọi ngôn ngữ: Trung, Anh, Nhật, Hàn, Thái, Nga, Hindi, Ả Rập, Latin.
- Whisper (nghe lời gốc) bản CPU và bản card đồ họa (Windows).
- Model tách nhạc nền UVR, giọng Piper tiếng Việt.
pip cài vào đúng môi trường của app, file tạm để trên cùng ổ với app, không lưu cache (đỡ tốn ổ C).
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

from .config import Settings, app_home
from .media import Cancelled, no_window

ITEMS = {
    "vieneu": ("🎙️ Giọng VieNeu: Ngọc Huyền, Hải Đăng... (trên máy)", "~1 GB"),
    "ocr": ("🔤 Đọc phụ đề cứng (OCR) - tất cả ngôn ngữ", "~200 MB"),
    "whisper": ("🎧 Whisper nghe lời gốc (CPU)", "~1.6 GB"),
    "whisper_gpu": ("🎮 Whisper bằng card đồ họa (Windows)", "~0.9 GB"),
    "uvr": ("🎵 Tách nhạc nền khỏi giọng gốc (UVR)", "~70 MB"),
    "piper": ("🗣️ Giọng Piper tiếng Việt (dự phòng khi mất mạng)", "~60 MB"),
}
PIP = {"vieneu": ["vieneu"], "ocr": ["rapidocr"], "whisper": ["faster-whisper"],
       "uvr": ["onnxruntime"], "piper": ["piper-tts"]}
MODULE = {"vieneu": "vieneu", "ocr": "rapidocr", "whisper": "faster_whisper", "uvr": "onnxruntime", "piper": "piper"}


def _marker() -> Path:
    return app_home() / "models" / "components.json"


def _done() -> dict:
    try:
        return json.loads(_marker().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _mark(cid: str, info=True) -> None:
    d = _done()
    d[cid] = info
    _marker().parent.mkdir(parents=True, exist_ok=True)
    _marker().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def status() -> dict[str, bool]:
    done = _done()
    out = {}
    for cid in ITEMS:
        mod = MODULE.get(cid)
        out[cid] = bool(done.get(cid)) and (mod is None or has_module(mod))
    if os.name != "nt":
        out.pop("whisper_gpu", None)
    return out


def app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def pip_install(pkgs: list[str], log, cancel=None) -> None:
    env = dict(os.environ)
    tmp = app_dir() / ".tmp"
    tmp.mkdir(exist_ok=True)
    env.update(TEMP=str(tmp), TMP=str(tmp), PIP_NO_CACHE_DIR="1", PYTHONIOENCODING="utf-8")
    log("Cài thư viện: " + " ".join(pkgs))
    proc = subprocess.Popen([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *pkgs],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, **no_window())
    tail = []
    for raw in iter(proc.stdout.readline, b""):
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise Cancelled()
        line = raw.decode("utf-8", "replace").rstrip()
        tail = (tail + [line])[-12:]
        if line.startswith(("Collecting", "Installing", "Successfully")):
            log("  " + line[:150])
    proc.wait()
    importlib.invalidate_caches()
    if proc.returncode != 0:
        msg = "\n".join(tail)
        if "No space left" in msg or "Errno 28" in msg:
            raise RuntimeError("Ổ đĩa hết chỗ - dọn bớt rồi thử lại.")
        raise RuntimeError("Cài thư viện lỗi:\n" + msg[-800:])


def ensure_directml(log=lambda *_a, **_k: None) -> None:
    """Windows: dùng bản onnxruntime DirectML (chạy model bằng card AMD/NVIDIA/Intel; vẫn chạy CPU được)."""
    if os.name != "nt":
        return
    try:
        import onnxruntime as ort

        if "DmlExecutionProvider" in ort.get_available_providers():
            return
    except ImportError:
        pass
    try:
        pip_install(["--no-deps", "--force-reinstall", "onnxruntime-directml"], log)
    except Exception as e:  # noqa: BLE001
        log(f"Không bật được chạy bằng card đồ họa ({e}) - dùng CPU.", "warn")


def install(cid: str, settings: Settings, log, progress, cancel) -> None:
    mod = MODULE.get(cid)
    if mod and not has_module(mod) and cid in PIP:
        progress(0.05, f"Cài {ITEMS[cid][0]}")
        pip_install(PIP[cid], log, cancel)
        if cid in ("vieneu", "uvr", "ocr"):
            ensure_directml(log)
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if cid == "vieneu":
        from . import voices

        progress(0.3, "Tải model giọng VieNeu (lần đầu)")
        m = voices.vieneu_model()
        vid = voices.vieneu_voice_id(m, "Ngọc Huyền")
        test = app_home() / "models" / "vieneu_test.wav"
        m.save(m.infer("Xin chào, tôi là Ngọc Huyền.", voice=vid), str(test))
        test.unlink(missing_ok=True)
        log(f"✅ Giọng VieNeu sẵn sàng (giọng mặc định: {vid}).")
        _mark(cid, {"voice": vid})
    elif cid == "ocr":
        from . import ocr

        langs = list(ocr.LANGS)
        for i, lang in enumerate(langs):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            progress(0.1 + 0.9 * i / len(langs), f"Tải model đọc chữ: {ocr.LANGS[lang][0]}")
            try:
                ocr.engine(lang)
            except Exception as e:  # noqa: BLE001
                log(f"OCR {ocr.LANGS[lang][0]}: chưa tải được ({e}) - sẽ thử lại khi dùng.", "warn")
        log("✅ Đọc chữ trên hình: đủ các ngôn ngữ.")
        _mark(cid)
    elif cid == "whisper":
        from faster_whisper.utils import download_model

        name = settings.get("speech", "whisper_model") or "large-v3-turbo"
        progress(0.2, f"Tải Whisper {name} (lần đầu, khá lâu)")
        download_model(name)
        log(f"✅ Whisper {name} sẵn sàng.")
        _mark(cid, {"model": name})
    elif cid == "whisper_gpu":
        from . import transcript

        transcript.gpu_assets(settings, progress, cancel)
        log("✅ Whisper card đồ họa sẵn sàng.")
        _mark(cid)
    elif cid == "uvr":
        from . import separate

        separate.model_path(settings, log, progress, cancel)
        log("✅ Model tách nhạc nền sẵn sàng.")
        _mark(cid)
    elif cid == "piper":
        from . import voices

        voices.piper_model(voices._PIPER[0][0], settings, log)
        log("✅ Giọng Piper tiếng Việt sẵn sàng.")
        _mark(cid)
    progress(1.0, "Xong")


def install_all(settings: Settings, log, progress, cancel, only: list[str] | None = None) -> dict:
    """Tải lần lượt mọi thành phần chưa có. Thành phần lỗi không làm dừng các thành phần khác."""
    st = status()
    todo = [c for c in (only or list(st)) if not st.get(c)]
    res = {}
    for i, cid in enumerate(todo):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        log(f"▶ {ITEMS[cid][0]} ({ITEMS[cid][1]})")
        try:
            install(cid, settings, log, lambda p, m="", i=i: progress((i + p) / max(1, len(todo)), m), cancel)
            res[cid] = "ok"
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            res[cid] = str(e)
            log(f"❌ {ITEMS[cid][0]}: {e}", "error")
    progress(1.0, "Đã tải xong thư viện")
    return res
