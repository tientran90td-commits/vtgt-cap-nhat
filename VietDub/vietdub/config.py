"""Cài đặt của app: lưu ở %APPDATA%/VietDub/settings.json (Windows) hoặc ~/.vietdub."""
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


def app_home() -> Path:
    env = os.environ.get("VIETDUB_HOME")
    if env:
        p = Path(env)
    elif sys.platform.startswith("win"):
        p = Path(os.environ.get("APPDATA", Path.home())) / "VietDub"
    else:
        p = Path.home() / ".vietdub"
    p.mkdir(parents=True, exist_ok=True)
    return p


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
        p = Path(self.get("paths", "output") or (Path.home() / "Videos" / "VietDub"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def downloads_dir(self) -> Path:
        p = Path(self.get("paths", "downloads") or (Path.home() / "Videos" / "VietDub" / "Tải về"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def proxies(self) -> dict | None:
        p = (self.get("net", "proxy") or "").strip()
        return {"http": p, "https": p} if p else None
