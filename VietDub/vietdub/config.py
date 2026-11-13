"""Cài đặt của app: lưu trong thư mục app (data/settings.json) - mọi thứ ở cùng ổ với app, không dùng ổ C."""
from __future__ import annotations

import copy
import json
import os
import sys
import threading
from pathlib import Path

DEFAULTS: dict = {
    "keys": {"gemini": "", "openai": "", "claude": "", "groq": "", "openrouter": "", "deepseek": "",
             "elevenlabs": ""},
    # auto: mỗi bước tự chọn chạy trên máy hay qua mạng (cái nào có sẵn & nhanh), lỗi thì tự chuyển cách kia
    # offline: chỉ dùng công cụ chạy trên máy · online: ưu tiên dịch vụ online, máy là dự phòng
    "mode": "auto",
    "ai": {
        "provider": "auto",        # auto | ollama | gemini | claude | openai | groq | openrouter | deepseek
        "model": "auto",           # model của AI online đã chọn
        "ollama_model": "qwen2.5:7b",
        "ollama_url": "http://localhost:11434",
        "fallback": True,          # AI lỗi / quá tải -> tự chuyển AI khác (online <-> trên máy)
        "auto_start_ollama": True, # Ollama đã cài nhưng chưa mở -> app tự mở
    },
    "speech": {"engine": "auto", "whisper_model": "large-v3-turbo", "language": "auto", "ocr_lang": "auto"},
    "translate": {
        "style": "natural",        # xem translate.STYLES
        "glossary": "",            # "林动 = Lâm Động" mỗi dòng 1 tên / thuật ngữ
        "context": "",             # vài câu giới thiệu video (thể loại, nhân vật, quan hệ) giúp dịch đúng xưng hô
        "shorten": True,           # câu dịch dài quá thời gian nói -> AI rút gọn
        "safe": False,             # tránh từ ngữ vi phạm chính sách TikTok / YouTube
    },
    "voice": {"engine": "vieneu", "voice": "Ngọc Huyền", "speed": 0, "volume": 100, "fallback": True,
              "max_speed": 1.35},
    "video": {
        "output": "both",          # both (thuyết minh + phụ đề) | dub (chỉ thuyết minh) | sub (chỉ phụ đề)
        "background": "separate",  # tiếng gốc khi thuyết minh: separate (AI tách: bỏ giọng gốc, giữ nhạc nền)
                                   # | duck (giữ tiếng gốc nhỏ) | mute (tắt hẳn)
        "bg_volume": 1.0,          # nhạc nền đã tách
        "orig_volume": 0.30,       # tiếng gốc (kiểu duck)
        "duck": True,              # tự giảm tiếng gốc lúc đang đọc thuyết minh
        "voice_volume": 1.0,
        "burn_subs": True,         # in phụ đề Việt lên hình
        "soft_subs": True,         # kèm phụ đề Việt bật/tắt được trong file MP4
        "sub_size": 54, "sub_position": "bottom", "sub_color": "white",
        "cover": "auto", "cover_height": 14,      # che phụ đề gốc: auto | none | blur | zoom | bar ; % chiều cao
        "aspect": "source", "height": 1080, "fill": "blur",
        "encoder": "auto", "quality": 21, "keep_srt": False,
    },
    "publish": {"thumbnail": True, "info": True, "save_next_to_video": False},
    "paths": {"output": "", "ffmpeg": "", "downloads": ""},
    "net": {"proxy": ""},
    "update": {"repo": "tientran90td-commits/vtgt-cap-nhat", "branch": "claude/movie-summary-app-0q90dq",
               "auto_check": True},
}
MODES = {"auto": "⚡ Tự động (máy + mạng)", "offline": "🔒 Chỉ trên máy", "online": "🌐 Ưu tiên online"}


def app_dir() -> Path:
    """Thư mục cài app (chứa main.py)."""
    return Path(__file__).resolve().parent.parent


def app_home() -> Path:
    """Dữ liệu của app (cài đặt, dự án, model, giọng...): nằm NGAY TRONG thư mục app (vd D:\\VietDub\\data) để
    mọi thứ ở cùng ổ với app - không ghi gì vào ổ C."""
    env = os.environ.get("VIETDUB_HOME")
    p = Path(env) if env else app_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


def old_home() -> Path:
    """Chỗ để dữ liệu của bản 1.0 - 1.2 (thường ở ổ C)."""
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home())) / "VietDub"
    return Path.home() / ".vietdub"


def fix_std_streams(log_dir: Path | None = None) -> Path | None:
    """Mở bằng pythonw.exe (run.bat, không cửa sổ đen) thì sys.stdout/stderr = None: thư viện nào in ra
    (VieNeu, thanh tiến độ tải model...) sẽ lỗi "'NoneType' object has no attribute 'write'".
    Chuyển chúng vào data/logs/app.log (giữ tối đa ~5 MB) để không bao giờ lỗi vì thế nữa."""
    if sys.stdout is not None and sys.stderr is not None:
        return None
    if log_dir is None:
        home = Path(os.environ["VIETDUB_HOME"]) if os.environ.get("VIETDUB_HOME") else app_dir() / "data"
        log_dir = home / "logs"
    path = log_dir / "app.log"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
            path.replace(log_dir / "app.old.log")
        f = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        f, path = open(os.devnull, "w", encoding="utf-8"), None
    for name in ("stdout", "stderr", "__stdout__", "__stderr__"):
        if getattr(sys, name, None) is None:
            setattr(sys, name, f)
    return path


def setup_env() -> None:
    """Gọi đầu tiên khi mở app: mọi bộ nhớ đệm / file tạm / model của thư viện đi kèm đều về ổ chứa app."""
    if os.environ.get("VIETDUB_HOME"):
        home = Path(os.environ["VIETDUB_HOME"])
    else:
        home = app_dir() / "data"
    tmp = home / "tmp"
    for d in (home, tmp, home / "cache"):
        d.mkdir(parents=True, exist_ok=True)
    env = {
        "TEMP": tmp, "TMP": tmp, "TMPDIR": tmp,                      # file tạm (Python, pip, ffmpeg...)
        "HF_HOME": home / "huggingface",                              # model Whisper, VieNeu (HuggingFace)
        "XDG_CACHE_HOME": home / "cache",                             # yt-dlp, thư viện khác
        "NUMBA_CACHE_DIR": home / "cache" / "numba",                  # librosa (giọng VieNeu)
        "TORCH_HOME": home / "cache" / "torch",
        "OLLAMA_MODELS": home / "ollama-models",                      # model AI trên máy (Ollama do app mở)
        "UV_CACHE_DIR": home / "cache" / "uv",
        "PIP_NO_CACHE_DIR": "1",
    }
    for k, v in env.items():
        if k == "OLLAMA_MODELS" and os.environ.get(k):  # người dùng đã tự chọn chỗ để model
            continue
        os.environ[k] = str(v)
    import tempfile

    tempfile.tempdir = str(tmp)


def disk_info(path: Path | None = None) -> tuple[str, float, float]:
    """(ổ đĩa, GB còn trống, GB tổng) của ổ chứa `path` (mặc định: ổ chứa app)."""
    import shutil

    p = Path(path or app_dir())
    u = shutil.disk_usage(p)
    return (p.drive or p.anchor or "/"), u.free / 1e9, u.total / 1e9


def on_system_drive() -> bool:
    """App đang nằm ở ổ C (ổ hệ thống)?"""
    if not sys.platform.startswith("win"):
        return False
    sysdrive = (os.environ.get("SystemDrive") or "C:").upper()
    return app_dir().drive.upper() == sysdrive


def needs_migration() -> bool:
    old = old_home()
    return not os.environ.get("VIETDUB_HOME") and old.exists() and old.resolve() != app_home().resolve() and \
        any(old.iterdir())


def migrate_old_home(log=lambda *_a, **_k: None, progress=lambda *_a, **_k: None, cancel=None) -> int:
    """Chuyển dữ liệu bản cũ từ ổ C về thư mục app (chuyển xong thì xóa bên C để giải phóng chỗ)."""
    import shutil

    old, new = old_home(), app_home()
    items = [p for p in old.iterdir()]
    moved = 0
    for i, src in enumerate(items):
        if cancel is not None and cancel.is_set():
            break
        dst = new / src.name
        progress(i / max(1, len(items)), f"Chuyển {src.name} sang {new.drive or new}")
        try:
            if dst.exists():
                if src.is_dir() and dst.is_dir():  # gộp thư mục
                    for f in src.rglob("*"):
                        t = dst / f.relative_to(src)
                        if f.is_file() and not t.exists():
                            t.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(f), str(t))
                    shutil.rmtree(src, ignore_errors=True)
                elif src.is_file() and src.name != "settings.json":
                    src.unlink()
                else:
                    continue
            else:
                shutil.move(str(src), str(dst))
            moved += 1
        except OSError as e:
            log(f"Không chuyển được {src.name}: {e}", "warn")
    if (old / "settings.json").exists() and not (new / "settings.json").exists():
        shutil.move(str(old / "settings.json"), str(new / "settings.json"))
    try:
        if not any(old.iterdir()):
            old.rmdir()
    except OSError:
        pass
    progress(1.0, "Đã chuyển dữ liệu")
    log(f"✅ Đã chuyển dữ liệu cũ từ {old} sang {new}.")
    return moved


def _merge(base: dict, data: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (data or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else app_home() / "settings.json"
        self._lock = threading.RLock()
        data = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        self.data = _merge(DEFAULTS, data)

    def get(self, sec: str, key: str, default=None):
        with self._lock:
            return self.data.get(sec, {}).get(key, default)

    @property
    def mode(self) -> str:
        m = self.data.get("mode") or "auto"
        return m if m in MODES else "auto"

    @property
    def offline(self) -> bool:
        return self.mode == "offline"

    def set(self, sec: str, key: str, value) -> None:
        with self._lock:
            self.data.setdefault(sec, {})[key] = value

    def section(self, sec: str) -> dict:
        with self._lock:
            return copy.deepcopy(self.data.get(sec, {}))

    def key(self, provider: str) -> str:
        return (self.get("keys", provider) or "").strip()

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def output_dir(self) -> Path:
        p = Path(self.get("paths", "output") or (app_dir() / "Video xuất"))   # cùng ổ với app (không về ổ C)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def downloads_dir(self) -> Path:
        p = Path(self.get("paths", "downloads") or (app_dir() / "Video tải về"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def proxies(self) -> dict | None:
        p = (self.get("net", "proxy") or "").strip()
        return {"http": p, "https": p} if p else None
