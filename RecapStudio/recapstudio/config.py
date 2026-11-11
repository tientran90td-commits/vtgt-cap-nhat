"""Cài đặt của app: lưu ở %APPDATA%/RecapStudio/settings.json (Windows) hoặc ~/.recapstudio."""
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
    "offline": True,               # chỉ dùng công cụ chạy trên máy: không cần mạng, không cần API key
    "ai": {
        "provider": "ollama",      # ollama (offline) | gemini | claude | openai | groq | openrouter | deepseek | none
        "model": "qwen2.5:7b",
        "style": "review",
        "mode": "narrate",         # narrate (thuyết minh) | mixed (thuyết minh + vài câu thoại gốc)
        "language": "Tiếng Việt",
        "minutes": 5.0,
        "extra": "",
        "ollama_url": "http://localhost:11434",
        "fallback": True,          # AI lỗi / quá tải -> tự chuyển AI khác đã có key
    },
    "speech": {"engine": "auto", "whisper_model": "large-v3-turbo", "language": "auto"},
    "voice": {"engine": "vieneu", "voice": "Ngọc Huyền", "speed": 0, "volume": 100},
    "video": {
        "aspect": "16:9", "height": 1080, "fill": "blur",
        "subtitles": True, "sub_size": 54, "sub_position": "bottom",
        "cover": "none", "cover_height": 14,      # che phụ đề gốc: none | blur | zoom | bar ; % chiều cao
        "orig_volume": 0.0, "voice_volume": 1.0,
        "music": "", "music_volume": 0.15,
        "encoder": "auto", "quality": 21, "parallel": 2, "keep_srt": False,
    },
    "paths": {"output": "", "ffmpeg": ""},
    "net": {"proxy": ""},
}


def app_home() -> Path:
    env = os.environ.get("RECAPSTUDIO_HOME")
    if env:
        p = Path(env)
    elif sys.platform.startswith("win"):
        p = Path(os.environ.get("APPDATA", Path.home())) / "RecapStudio"
    else:
        p = Path.home() / ".recapstudio"
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
    def offline(self) -> bool:
        return bool(self.data.get("offline", True))

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
        p = Path(self.get("paths", "output") or (Path.home() / "Videos" / "RecapStudio"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def proxies(self) -> dict | None:
        p = (self.get("net", "proxy") or "").strip()
        return {"http": p, "https": p} if p else None
