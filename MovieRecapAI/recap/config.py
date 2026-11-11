"""Lưu / đọc cấu hình ứng dụng và API key.

File cấu hình nằm ở:
  Windows : %APPDATA%/MovieRecapAI/settings.json
  macOS   : ~/Library/Application Support/MovieRecapAI/settings.json
  Linux   : ~/.config/MovieRecapAI/settings.json
Có thể đặt biến môi trường MOVIE_RECAP_HOME để đổi vị trí (bản portable).
"""
from __future__ import annotations

import copy
import json
import os
import sys
import threading
from pathlib import Path

DEFAULTS: dict = {
    "api": {
        # LLM
        "openai_key": "",
        "openai_base": "https://api.openai.com/v1",
        "anthropic_key": "",
        "gemini_key": "",
        "groq_key": "",
        "deepseek_key": "",
        "openrouter_key": "",
        "xai_key": "",
        "mistral_key": "",
        "qwen_key": "",
        "ollama_url": "http://localhost:11434/v1",
        "lmstudio_url": "http://localhost:1234/v1",
        "custom_base": "",
        "custom_key": "",
        # Giọng đọc (TTS)
        "elevenlabs_key": "",
        "azure_key": "",
        "azure_region": "southeastasia",
        "google_tts_key": "",
        "fpt_key": "",
        # Dữ liệu phim (tùy chọn) - themoviedb.org
        "tmdb_key": "",
        # HuggingFace token (tùy chọn) - để tải giọng/model từ repo cần đăng nhập
        "hf_token": "",
        # Mạng
        "proxy": "",
    },
    "paths": {
        "ffmpeg": "",
        "workspace": "",
        "output": "",
        "models": "",
    },
    "transcribe": {
        "engine": "faster_whisper",
        "model": "auto",
        "language": "auto",
        "device": "auto",
        "wcpp_dir": "",  # thư mục whisper.cpp (whisper-cli.exe) tự chọn
        "wcpp_url": "",  # link tải bản dựng whisper.cpp Vulkan khác (để trống = mặc định)
        "use_scenes": True,
    },
    "script": {
        "provider": "gemini",
        "model": "auto",
        "style": "review",
        "language": "Tiếng Việt",
        "target_minutes": 5.0,
        "spoiler": True,
        "custom": "",
        "max_chars": 150000,
        "web_max_chars": 60000,
        "web_inapp": True,       # chế độ web: mở trang AI ngay trong app (đăng nhập 1 lần)  # chế độ bản web: số ký tự tối đa mỗi lần dán
        "auto_fallback": True,
        "perspective": "omniscient",  # góc nhìn người kể
        "focus_character": "",
        "candidates": 1,          # số phương án kịch bản (AI chấm & chọn bản hay nhất)
        "style_ref": None,        # phong cách học từ video mẫu   # AI chính hết tiền/quá tải -> tự chuyển sang AI khác đã nhập key
        "identify": True,        # tự nhận diện phim (tên, nhân vật) trước khi viết kịch bản
        "visual": False,         # AI xem hình ảnh các cảnh để chọn cảnh chính xác hơn
        "mode": "narrate",
    },
    "voice": {
        "engine": "edge",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": 0,       # % (-50..+100)
        "pitch": 0,      # nửa cung (-12..+12)
        "volume": 0,     # % (-50..+50)
        "model": "",
        "style": "",
        "xtts_ref": "",
        "xtts_model_dir": "",
        "read_style": "natural",  # cách đọc chung
        "read_custom": "",        # mô tả cách đọc tự viết
        "tone_auto": True,        # mỗi đoạn đổi cách đọc theo cảm xúc AI gán
        "consistent": True,       # giữ 1 giọng đồng nhất cả video (cảm xúc từng đoạn chỉ chỉnh nhẹ tốc độ)
        "normalize": True,       # chuẩn hóa số, ngày, đơn vị, viết tắt trước khi đọc
        "ai_pron": False,        # nhờ AI soát lại câu cho dễ đọc
        "transliterate": False,  # phiên âm tên nước ngoài sang tiếng Việt
    },
    "render": {
        "aspect": "16:9",
        "fill": "blur",
        "height": 1080,
        "fps": 30,
        "encoder": "auto",
        "quality": 21,
        "orig_volume_voice": 0.0,  # tắt tiếng phim khi đang thuyết minh (không lẫn lời thoại nhân vật)
        "orig_volume_clip": 1.0,
        "voice_volume": 1.0,
        "fit": "extend",
        "music": "",
        "music_volume": 0.15,
        "subtitles": True,
        "sub_font": "Arial",
        "sub_size": 52,
        "sub_color": "#FFFFFF",
        "sub_outline_color": "#000000",
        "sub_outline": 3,
        "sub_position": "bottom",
        "sub_bold": True,
        "sub_max_chars": 42,
        "sub_original": True,
        "title_text": "",
        "title_seconds": 4.0,
        "logo": "",
        "logo_position": "top-right",
        "logo_scale": 0.12,
        "gap": 0.25,
        "sentence_sync": True,   # khớp tiếng-hình theo từng câu
        "no_reuse": True,        # không lặp lại cảnh đã chiếu
        "avoid_overlays": True,  # tránh đoạn có quảng cáo/chữ chèn cứng của web phim
        "delogo": True,          # che mờ logo/watermark cố định của nguồn
        "hardsub_mode": "blur",  # phụ đề gốc in cứng: blur | vsr | bar | crop | avoid | none
        "vsr_dir": "",  # thư mục video-subtitle-remover (xóa phụ đề bằng AI)
        "vsr_mode": "sttn-auto",
        "fit_duration": True,  # ép video thành phẩm vừa thời lượng mục tiêu
        "open_folder_after": True,  # xuất xong tự mở thư mục chứa video
        "only_video": True,  # thư mục xuất chỉ để lại video (file phụ cất riêng, xem ở nút 📣)
        "publish_thumbs": True,  # xuất xong tự tạo ảnh thumbnail
        "publish_meta": True,  # xuất xong AI viết tiêu đề, mô tả, hashtag, mốc chương
        "transition": "fade",    # cut | fade - chuyển cảnh mềm giữa các đoạn
        "loudnorm": True,        # cân bằng âm lượng tổng (-16 LUFS)
        "final_qa": True,        # kiểm tra màn hình đen / đứng hình / âm lượng sau khi xuất
    },
    "ui": {"last_dir": "", "auto_install": True, "preload": True,
           "update_repo": "tientran90td-commits/vtgt-cap-nhat", "update_branch": "claude/movie-summary-app-0q90dq"},
    "config_version": 4,
}


def app_home() -> Path:
    env = os.environ.get("MOVIE_RECAP_HOME")
    if env:
        p = Path(env)
    elif sys.platform.startswith("win"):
        p = Path(os.environ.get("APPDATA", Path.home())) / "MovieRecapAI"
    elif sys.platform == "darwin":
        p = Path.home() / "Library" / "Application Support" / "MovieRecapAI"
    else:
        p = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "MovieRecapAI"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    """Cấu hình dạng dict lồng nhau, an toàn đa luồng, tự lưu ra JSON."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else app_home() / "settings.json"
        self._lock = threading.RLock()
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.data = _merge(DEFAULTS, raw)
                if int(raw.get("config_version", 1)) < 2:  # bản 1.0 -> 1.1: dùng chế độ tự động mới
                    if self.data["render"].get("encoder") == "libx264":
                        self.data["render"]["encoder"] = "auto"
                    if self.data["transcribe"].get("model") == "small":
                        self.data["transcribe"]["model"] = "auto"
                    self.data["config_version"] = 2
                if int(raw.get("config_version", 1)) < 3:  # 1.1 -> 1.2: Google ngừng gemini-2.5-flash
                    sc = self.data["script"]
                    if sc.get("provider") == "gemini" and str(sc.get("model", "")).startswith(("gemini-2.5", "gemini-2.0",
                                                                                               "gemini-1.5")):
                        sc["model"] = "auto"
                    vo = self.data["voice"]
                    if vo.get("engine") == "gemini" and str(vo.get("model", "")).startswith("gemini-2.5"):
                        vo["model"] = ""
                    self.data["config_version"] = 3
                if int(raw.get("config_version", 1)) < 4:  # 1.6 -> 1.7: sửa lỗi video có 2 giọng
                    if abs(float(self.data["render"].get("orig_volume_voice", 0) or 0) - 0.12) < 1e-6:
                        self.data["render"]["orig_volume_voice"] = 0.0
                    self.data["voice"]["consistent"] = True
                    self.data["config_version"] = 4
            except Exception:
                self.data = copy.deepcopy(DEFAULTS)

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def get(self, section: str, key: str, default=None):
        with self._lock:
            return self.data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value) -> None:
        with self._lock:
            self.data.setdefault(section, {})[key] = value

    def section(self, name: str) -> dict:
        with self._lock:
            return copy.deepcopy(self.data.get(name, {}))

    # Các thư mục làm việc -------------------------------------------------
    def workspace(self) -> Path:
        p = Path(self.get("paths", "workspace") or (app_home() / "projects"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def output_dir(self) -> Path:
        p = Path(self.get("paths", "output") or (Path.home() / "Videos" / "MovieRecapAI"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def models_dir(self) -> Path:
        p = Path(self.get("paths", "models") or (app_home() / "models"))
        p.mkdir(parents=True, exist_ok=True)
        return p

    def proxy(self) -> str | None:
        p = (self.get("api", "proxy") or "").strip()
        if p:
            return p
        return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
