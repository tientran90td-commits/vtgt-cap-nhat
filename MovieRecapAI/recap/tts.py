"""Giọng đọc (Text-to-Speech) - nhiều engine, online lẫn offline.

  vieneu      VieNeu-TTS (pnnbao97/VieNeu-TTS) - OFFLINE, AI tiếng Việt phát âm chuẩn, 25 giọng, nhân bản giọng
  edge        Microsoft Edge TTS (rany2/edge-tts)  - MIỄN PHÍ, 400+ giọng, 140+ ngôn ngữ (có Hoài My, Nam Minh)
  gtts        Google Translate TTS (pndurette/gTTS) - miễn phí, nhiều ngôn ngữ/giọng vùng miền
  openai      OpenAI TTS (tts-1, tts-1-hd, gpt-4o-mini-tts có điều khiển cảm xúc)
  elevenlabs  ElevenLabs - giọng siêu thật, giọng nhân bản trong tài khoản
  gemini      Google Gemini TTS - 30 giọng, điều khiển cảm xúc bằng lời
  google      Google Cloud Text-to-Speech (Neural2, WaveNet, Chirp3-HD...)
  azure       Azure AI Speech - 500+ giọng neural, có phong cách (vui, buồn, giận...)
  fpt         FPT.AI - giọng tiếng Việt 3 miền Bắc/Trung/Nam
  piper       Piper (rhasspy/piper) - OFFLINE, mã nguồn mở, có giọng tiếng Việt
  sapi        Giọng có sẵn trong Windows/macOS/Linux (pyttsx3) - OFFLINE
  xtts        Coqui XTTS-v2 / viXTTS - OFFLINE, nhân bản giọng từ file mẫu 6-30 giây
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

from . import textnorm
from .config import Settings, app_home
from .ffmpeg_utils import run_ffmpeg
from .subtitles import chunk_text


@dataclass
class Voice:
    id: str
    name: str
    lang: str = ""
    gender: str = ""
    engine: str = ""
    desc: str = ""
    extra: dict = field(default_factory=dict)

    def label(self) -> str:
        g = {"Female": "Nữ", "Male": "Nam", "FEMALE": "Nữ", "MALE": "Nam", "female": "Nữ", "male": "Nam"}.get(
            self.gender, self.gender)
        parts = [self.name]
        if self.lang:
            parts.append(self.lang)
        if g:
            parts.append(g)
        if self.desc:
            parts.append(self.desc)
        return " · ".join(parts)


ENGINES: dict[str, dict] = {
    "vieneu": {"name": "⭐ VieNeu-TTS - AI giọng Việt phát âm chuẩn, nhân bản giọng (offline)", "offline": True,
               "key": None, "rate": False, "pitch": False, "models": ["v3turbo", "v3nano"]},
    "edge": {"name": "Microsoft Edge TTS - miễn phí, 400+ giọng", "offline": False, "key": None,
             "rate": True, "pitch": True, "models": []},
    "gtts": {"name": "Google Translate TTS - miễn phí", "offline": False, "key": None,
             "rate": False, "pitch": False, "models": []},
    "openai": {"name": "OpenAI TTS", "offline": False, "key": "openai_key", "rate": True, "pitch": False,
               "models": ["gpt-4o-mini-tts", "tts-1-hd", "tts-1"], "style": True},
    "elevenlabs": {"name": "ElevenLabs - giọng siêu thật", "offline": False, "key": "elevenlabs_key",
                   "rate": False, "pitch": False,
                   "models": ["eleven_multilingual_v2", "eleven_v3", "eleven_flash_v2_5", "eleven_turbo_v2_5"]},
    "gemini": {"name": "Google Gemini TTS - 30 giọng cảm xúc", "offline": False, "key": "gemini_key",
               "rate": False, "pitch": False,
               "models": ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"], "style": True},
    "google": {"name": "Google Cloud TTS (WaveNet/Neural2/Chirp)", "offline": False, "key": "google_tts_key",
               "rate": True, "pitch": False, "models": []},
    "azure": {"name": "Azure AI Speech - 500+ giọng, có cảm xúc", "offline": False, "key": "azure_key",
              "rate": True, "pitch": True, "models": [], "style": True},
    "fpt": {"name": "FPT.AI - giọng Việt 3 miền", "offline": False, "key": "fpt_key",
            "rate": False, "pitch": False, "models": []},
    "piper": {"name": "Piper - offline, mã nguồn mở", "offline": True, "key": None,
              "rate": True, "pitch": False, "models": []},
    "sapi": {"name": "Giọng hệ điều hành (Windows SAPI/pyttsx3) - offline", "offline": True, "key": None,
             "rate": True, "pitch": False, "models": []},
    "xtts": {"name": "Coqui XTTS-v2 / viXTTS - nhân bản giọng (offline, GPU)", "offline": True, "key": None,
             "rate": True, "pitch": False, "models": []},
}

# Mã ngôn ngữ cho các engine cần biết ngôn ngữ (XTTS...)
LANG_CODES = {"Tiếng Việt": "vi", "English": "en", "中文": "zh-cn", "日本語": "ja", "한국어": "ko", "ไทย": "th",
              "Bahasa Indonesia": "id", "Español": "es", "Français": "fr", "Deutsch": "de", "Português": "pt",
              "Русский": "ru", "हिन्दी": "hi"}


# ======================================================================= CÁCH ĐỌC (cảm xúc)
# rate/pitch: chỉnh nhịp & cao độ cho các engine không điều khiển được cảm xúc bằng lời
# azure: style SSML · el: (stability, style) cho ElevenLabs · tag: thẻ cảm xúc ElevenLabs v3
READ_STYLES: dict[str, dict] = {
    "natural": {"name": "🙂 Tự nhiên", "vi": "tự nhiên, rõ ràng, truyền cảm",
                "en": "natural, clear and engaging storyteller", "rate": 0, "pitch": 0,
                "azure": "", "el": (0.45, 0.25), "tag": ""},
    "funny": {"name": "😂 Hài hước, vui nhộn", "vi": "hài hước, tinh nghịch, vui nhộn, nhấn nhá như đang kể chuyện cười",
              "en": "funny, playful and witty, with comedic timing", "rate": 10, "pitch": 1,
              "azure": "cheerful", "el": (0.3, 0.7), "tag": "[playfully]"},
    "serious": {"name": "🎙️ Nghiêm túc, tin tức", "vi": "nghiêm túc, điềm tĩnh, rõ ràng như phát thanh viên thời sự",
                "en": "serious, calm and authoritative like a news anchor", "rate": -4, "pitch": -1,
                "azure": "newscast", "el": (0.8, 0.0), "tag": ""},
    "dramatic": {"name": "🎬 Kịch tính, hồi hộp", "vi": "kịch tính, hồi hộp, nhấn mạnh, ngắt nghỉ như lồng tiếng trailer phim",
                 "en": "dramatic and suspenseful, like a movie trailer narrator", "rate": 3, "pitch": -2,
                 "azure": "serious", "el": (0.35, 0.6), "tag": "[dramatically]"},
    "horror": {"name": "👻 Kinh dị, rùng rợn", "vi": "trầm, chậm, thì thầm rùng rợn, đầy bí ẩn",
               "en": "dark, slow, creepy and whispery", "rate": -10, "pitch": -3,
               "azure": "whispering", "el": (0.5, 0.5), "tag": "[whispers]"},
    "sad": {"name": "😢 Buồn, cảm động", "vi": "buồn, xúc động, nhẹ nhàng và chậm rãi",
            "en": "sad, emotional, soft and slow", "rate": -8, "pitch": -1,
            "azure": "sad", "el": (0.5, 0.45), "tag": "[sad]"},
    "excited": {"name": "🔥 Sôi nổi, hào hứng", "vi": "sôi nổi, hào hứng, năng lượng cao",
                "en": "excited and energetic, high energy", "rate": 15, "pitch": 2,
                "azure": "excited", "el": (0.3, 0.65), "tag": "[excited]"},
    "warm": {"name": "☕ Kể chuyện ấm áp", "vi": "ấm áp, thân mật, chậm rãi như kể chuyện bên tách trà",
             "en": "warm, intimate, relaxed storytelling", "rate": -5, "pitch": 0,
             "azure": "narration-relaxed", "el": (0.55, 0.3), "tag": ""},
    "angry": {"name": "😠 Gay gắt, phẫn nộ", "vi": "gay gắt, phẫn nộ, dồn dập",
              "en": "angry, intense and forceful", "rate": 8, "pitch": 0,
              "azure": "angry", "el": (0.3, 0.6), "tag": "[angry]"},
    "kids": {"name": "🧸 Dễ thương (thiếu nhi)", "vi": "dễ thương, vui tươi, đơn giản như kể chuyện cho trẻ em",
             "en": "cute, cheerful and simple, for children", "rate": -3, "pitch": 2,
             "azure": "cheerful", "el": (0.45, 0.5), "tag": "[cheerfully]"},
    "custom": {"name": "✏️ Tự mô tả...", "vi": "", "en": "", "rate": 0, "pitch": 0, "azure": "", "el": (0.45, 0.3),
               "tag": ""},
}
TONE_KEYS = [k for k in READ_STYLES if k != "custom"]
# engine điều khiển cảm xúc bằng lời/SSML (không cần chỉnh nhịp-cao độ để "giả" cảm xúc)
EXPRESSIVE = {"openai", "gemini", "azure", "elevenlabs"}


def apply_read_style(engine: str, opts: dict) -> dict:
    """Áp cách đọc (opts['tone'] của đoạn, hoặc opts['read_style'] chung) cho từng engine."""
    o = dict(opts)
    key = o.get("tone") or o.get("read_style") or "natural"
    st = READ_STYLES.get(key, READ_STYLES["natural"])
    custom = (o.get("read_custom") or "").strip() if key == "custom" else ""
    desc_vi = custom or st["vi"]
    desc_en = custom or st["en"]
    if engine == "openai":
        if desc_en:
            o["style"] = f"Voice and tone: {desc_en}. Speak with correct, native pronunciation."
    elif engine == "gemini":
        if desc_vi and key != "natural":
            o["style"] = f"Đọc với giọng {desc_vi}"
    elif engine == "azure":
        if key == "custom" and custom and " " not in custom:
            o["style"] = custom
        else:
            o["style"] = st["azure"]
    elif engine == "elevenlabs":
        o["el_settings"] = st["el"]
        o["el_tag"] = st["tag"]
    if engine not in EXPRESSIVE and key != "custom":
        o["rate"] = float(o.get("rate", 0) or 0) + st["rate"]
        o["pitch"] = float(o.get("pitch", 0) or 0) + st["pitch"]
    return o


class TTSError(RuntimeError):
    pass


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    p = (settings.get("api", "proxy") or "").strip()
    if p:
        s.proxies = {"http": p, "https": p}
    return s


def _key(engine: str, settings: Settings) -> str:
    k = ENGINES[engine].get("key")
    if not k:
        return ""
    val = (settings.get("api", k) or "").strip()
    if not val:
        raise TTSError(f"Chưa nhập API key cho {ENGINES[engine]['name']} (mục 🔑 API & Cài đặt).")
    return val


def _cache_file(name: str) -> Path:
    d = app_home() / "cache"
    d.mkdir(exist_ok=True)
    return d / name


# ======================================================================= DANH SÁCH GIỌNG
def list_voices(engine: str, settings: Settings, refresh: bool = False) -> list[Voice]:
    fn = globals().get(f"_voices_{engine}")
    if not fn:
        return []
    return fn(settings, refresh)


def _cached(name: str, refresh: bool, loader):
    f = _cache_file(name)
    if f.exists() and not refresh:
        try:
            return [Voice(**v) for v in json.loads(f.read_text(encoding="utf-8"))]
        except Exception:
            pass
    voices = loader()
    if voices:
        f.write_text(json.dumps([asdict(v) for v in voices], ensure_ascii=False), encoding="utf-8")
    return voices


_EDGE_FALLBACK = [
    ("vi-VN-HoaiMyNeural", "Female"), ("vi-VN-NamMinhNeural", "Male"),
    ("en-US-AriaNeural", "Female"), ("en-US-GuyNeural", "Male"), ("en-US-JennyNeural", "Female"),
    ("en-US-ChristopherNeural", "Male"), ("en-US-AndrewMultilingualNeural", "Male"),
    ("en-US-AvaMultilingualNeural", "Female"), ("en-US-BrianMultilingualNeural", "Male"),
    ("en-US-EmmaMultilingualNeural", "Female"), ("en-GB-SoniaNeural", "Female"), ("en-GB-RyanNeural", "Male"),
    ("zh-CN-XiaoxiaoNeural", "Female"), ("zh-CN-YunxiNeural", "Male"), ("ja-JP-NanamiNeural", "Female"),
    ("ja-JP-KeitaNeural", "Male"), ("ko-KR-SunHiNeural", "Female"), ("ko-KR-InJoonNeural", "Male"),
    ("th-TH-PremwadeeNeural", "Female"), ("th-TH-NiwatNeural", "Male"), ("fr-FR-DeniseNeural", "Female"),
    ("fr-FR-HenriNeural", "Male"), ("de-DE-KatjaNeural", "Female"), ("de-DE-ConradNeural", "Male"),
    ("es-ES-ElviraNeural", "Female"), ("es-ES-AlvaroNeural", "Male"), ("id-ID-GadisNeural", "Female"),
    ("id-ID-ArdiNeural", "Male"), ("ru-RU-SvetlanaNeural", "Female"), ("ru-RU-DmitryNeural", "Male"),
]


def _voices_edge(settings, refresh):
    def load():
        import edge_tts

        async def go():
            return await edge_tts.list_voices(proxy=settings.proxy())
        out = []
        for d in asyncio.run(go()):
            tag = d.get("VoiceTag") or {}
            pers = ", ".join(tag.get("VoicePersonalities") or [])
            name = d["ShortName"].split("-", 2)[-1].replace("Neural", "")
            out.append(Voice(id=d["ShortName"], name=name, lang=d.get("Locale", ""), gender=d.get("Gender", ""),
                             engine="edge", desc=pers))
        out.sort(key=lambda v: (not v.lang.startswith("vi"), v.lang, v.name))
        return out
    try:
        return _cached("edge_voices.json", refresh, load)
    except Exception:
        # Không có mạng: dùng danh sách giọng phổ biến dựng sẵn (không lưu cache)
        return [Voice(id=v, name=v.split("-", 2)[-1].replace("Neural", ""), lang="-".join(v.split("-")[:2]),
                      gender=g, engine="edge") for v, g in _EDGE_FALLBACK]


_VIENEU_FALLBACK = {
    "v3turbo": [("Hải Đăng", "male", "Nam · Bắc · Phong cách tự nhiên"), ("Trúc Ly", "female", "Nữ · Bắc · Phong cách tự nhiên"),
                ("Thiện Minh", "male", "Nam · Bắc · Phong cách kể chuyện"), ("Mai Anh", "female", "Nữ · Bắc · Phong cách tin tức"),
                ("Adam bựa", "male", "Nam · Bắc · Phong cách tự nhiên"), ("Thùy Dung", "female", "Nữ · Nam · Phong cách tin tức"),
                ("Thiền Tâm Đức", "male", "Nam · Bắc · Phong cách kể chuyện"), ("Ngọc Huyền", "female", "Nữ · Bắc · Giọng đọc tự nhiên"),
                ("Quang Sơn", "male", "Nam · Trung · Phong cách tự nhiên"), ("Ngọc Trân", "female", "Nữ · Trung · Phong cách tự nhiên"),
                ("Thái Sơn", "male", "Nam · Nam · Phong cách kể chuyện"), ("Ngọc Linh", "female", "Nữ · Bắc · Phong cách kể chuyện"),
                ("Mỹ Duyên", "female", "Nữ · Nam · Phong cách đọc truyện"), ("Đức Trí", "male", "Nam · Nam · Phong cách đọc truyện")],
    "v3nano": [("Minh Quân", "male", "Nam · Bắc · Phong cách tự nhiên"), ("Ái Hân", "female", "Nữ · Nam · Phong cách tin tức"),
               ("Mai Anh", "female", "Nữ · Bắc · Phong cách tin tức"), ("Anh Khôi", "male", "Nam · Bắc · Phong cách kể chuyện"),
               ("Trúc Ly", "female", "Nữ · Bắc · Phong cách tự nhiên"), ("Mỹ Duyên", "female", "Nữ · Bắc · Phong cách đọc truyện")],
}


def _vieneu_desc(d: str) -> str:
    """'Nam · Bắc · Phong cách tự nhiên' -> 'miền Bắc · Phong cách tự nhiên' (giới tính đã có cột riêng)."""
    parts = [x.strip() for x in re.split(r"\s*·\s*", d or "") if x.strip()]
    if parts and parts[0] in ("Nam", "Nữ"):
        parts = parts[1:]
    if parts and parts[0] in ("Bắc", "Trung", "Nam"):
        parts[0] = "miền " + parts[0]
    return " · ".join(parts)


def _voices_vieneu(settings, refresh):
    """Đọc danh sách giọng có sẵn từ file voices_*.json đi kèm gói vieneu (không cần nạp model)."""
    mode = settings.get("voice", "model") or "v3turbo"
    mode = mode if mode in _VIENEU_FALLBACK else "v3turbo"
    items = []
    try:
        import importlib.util

        spec = importlib.util.find_spec("vieneu")
        f = Path(spec.origin).parent / "assets" / f"voices_{mode.replace('v3', 'v3_')}.json" if spec else None
        if f and f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            presets = data.get("presets", {})
            order = sorted(presets.items(), key=lambda kv: (kv[1].get("featured") is None, kv[1].get("featured") or 0))
            items = [(n, v.get("gender", ""), v.get("description", "")) for n, v in order]
    except Exception:
        items = []
    if not items:
        items = _VIENEU_FALLBACK[mode]
    out = [Voice(id="clone", name="🎤 Nhân bản giọng từ file mẫu 3-8 giây", lang="vi-VN", engine="vieneu",
                 desc="chọn file mẫu bên dưới")]
    out += [Voice(id=n, name=n, lang="vi-VN", gender=g.capitalize(), engine="vieneu", desc=_vieneu_desc(d))
            for n, g, d in items]
    return out


_GTTS_ACCENTS = {
    "en": [("com", "Mỹ"), ("co.uk", "Anh"), ("com.au", "Úc"), ("ca", "Canada"), ("co.in", "Ấn Độ"),
           ("ie", "Ireland"), ("co.za", "Nam Phi"), ("com.ng", "Nigeria")],
    "fr": [("fr", "Pháp"), ("ca", "Canada")],
    "pt": [("com.br", "Brazil"), ("pt", "Bồ Đào Nha")],
    "es": [("es", "Tây Ban Nha"), ("com.mx", "Mexico"), ("us", "Mỹ")],
    "zh-CN": [("com", "Đại lục")], "zh-TW": [("com", "Đài Loan")],
}


def _voices_gtts(settings, refresh):
    try:
        from gtts.lang import tts_langs

        langs = tts_langs()
    except Exception:
        langs = {"vi": "Vietnamese", "en": "English"}
    out = []
    for code, name in sorted(langs.items(), key=lambda x: (x[0] != "vi", x[0])):
        for tld, accent in _GTTS_ACCENTS.get(code, [("com", "")]):
            out.append(Voice(id=f"{code}|{tld}", name=f"{name}" + (f" ({accent})" if accent else ""),
                             lang=code, engine="gtts"))
        out.append(Voice(id=f"{code}|com|slow", name=f"{name} (đọc chậm)", lang=code, engine="gtts"))
    return out


_OPENAI_VOICES = [("alloy", "Neutral"), ("ash", "Male"), ("ballad", "Male"), ("coral", "Female"),
                  ("echo", "Male"), ("fable", "Male"), ("nova", "Female"), ("onyx", "Male"), ("sage", "Female"),
                  ("shimmer", "Female"), ("verse", "Male"), ("marin", "Female"), ("cedar", "Male")]


def _voices_openai(settings, refresh):
    return [Voice(id=v, name=v.capitalize(), lang="đa ngôn ngữ", gender=g, engine="openai")
            for v, g in _OPENAI_VOICES]


_GEMINI_VOICES = [
    ("Zephyr", "Female", "Tươi sáng"), ("Puck", "Male", "Sôi nổi"), ("Charon", "Male", "Truyền tải thông tin"),
    ("Kore", "Female", "Chắc chắn"), ("Fenrir", "Male", "Hào hứng"), ("Leda", "Female", "Trẻ trung"),
    ("Orus", "Male", "Chắc chắn"), ("Aoede", "Female", "Nhẹ nhàng"), ("Callirrhoe", "Female", "Thoải mái"),
    ("Autonoe", "Female", "Tươi sáng"), ("Enceladus", "Male", "Thì thầm"), ("Iapetus", "Male", "Rõ ràng"),
    ("Umbriel", "Male", "Thoải mái"), ("Algieba", "Male", "Mượt mà"), ("Despina", "Female", "Mượt mà"),
    ("Erinome", "Female", "Rõ ràng"), ("Algenib", "Male", "Khàn"), ("Rasalgethi", "Male", "Truyền cảm"),
    ("Laomedeia", "Female", "Sôi nổi"), ("Achernar", "Female", "Mềm mại"), ("Alnilam", "Male", "Chắc nịch"),
    ("Schedar", "Male", "Đều đặn"), ("Gacrux", "Female", "Trưởng thành"), ("Pulcherrima", "Female", "Thẳng thắn"),
    ("Achird", "Male", "Thân thiện"), ("Zubenelgenubi", "Male", "Bình thường"), ("Vindemiatrix", "Female", "Dịu dàng"),
    ("Sadachbia", "Male", "Sống động"), ("Sadaltager", "Male", "Hiểu biết"), ("Sulafat", "Female", "Ấm áp"),
]


def _voices_gemini(settings, refresh):
    return [Voice(id=v, name=v, lang="đa ngôn ngữ", gender=g, engine="gemini", desc=d) for v, g, d in _GEMINI_VOICES]


def _voices_elevenlabs(settings, refresh):
    def load():
        key = _key("elevenlabs", settings)
        r = _session(settings).get("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key}, timeout=30)
        if r.status_code >= 400:
            raise TTSError(f"ElevenLabs lỗi {r.status_code}: {r.text[:200]}")
        out = []
        for v in r.json().get("voices", []):
            lb = v.get("labels") or {}
            desc = ", ".join(x for x in (lb.get("accent"), lb.get("age"), lb.get("description"),
                                         lb.get("use_case"), v.get("category")) if x)
            out.append(Voice(id=v["voice_id"], name=v.get("name", ""), lang=lb.get("language", "đa ngôn ngữ"),
                             gender=(lb.get("gender") or "").capitalize(), engine="elevenlabs", desc=desc))
        return out
    return _cached("elevenlabs_voices.json", refresh, load)


def _voices_google(settings, refresh):
    def load():
        key = _key("google", settings)
        r = _session(settings).get("https://texttospeech.googleapis.com/v1/voices", params={"key": key}, timeout=30)
        if r.status_code >= 400:
            raise TTSError(f"Google TTS lỗi {r.status_code}: {r.text[:200]}")
        out = []
        for v in r.json().get("voices", []):
            lang = (v.get("languageCodes") or [""])[0]
            out.append(Voice(id=v["name"], name=v["name"], lang=lang,
                             gender=(v.get("ssmlGender") or "").capitalize(), engine="google"))
        out.sort(key=lambda v: (not v.lang.startswith("vi"), v.lang, v.name))
        return out
    return _cached("google_voices.json", refresh, load)


def _azure_host(settings) -> str:
    region = (settings.get("api", "azure_region") or "southeastasia").strip()
    return f"https://{region}.tts.speech.microsoft.com"


def _voices_azure(settings, refresh):
    def load():
        key = _key("azure", settings)
        r = _session(settings).get(_azure_host(settings) + "/cognitiveservices/voices/list",
                                   headers={"Ocp-Apim-Subscription-Key": key}, timeout=30)
        if r.status_code >= 400:
            raise TTSError(f"Azure lỗi {r.status_code}: {r.text[:200]}")
        out = []
        for v in r.json():
            styles = v.get("StyleList") or []
            out.append(Voice(id=v["ShortName"], name=v.get("LocalName") or v.get("DisplayName"),
                             lang=v.get("Locale", ""), gender=v.get("Gender", ""), engine="azure",
                             desc=("phong cách: " + ", ".join(styles[:6])) if styles else "",
                             extra={"styles": styles}))
        out.sort(key=lambda v: (not v.lang.startswith("vi"), v.lang, v.name))
        return out
    return _cached("azure_voices.json", refresh, load)


_FPT_VOICES = [("banmai", "Ban Mai", "Female", "Miền Bắc"), ("thuminh", "Thu Minh", "Female", "Miền Bắc"),
               ("leminh", "Lê Minh", "Male", "Miền Bắc"), ("myan", "Mỹ An", "Female", "Miền Trung"),
               ("giahuy", "Gia Huy", "Male", "Miền Trung"), ("ngoclam", "Ngọc Lam", "Female", "Miền Trung"),
               ("lannhi", "Lan Nhi", "Female", "Miền Nam"), ("linhsan", "Linh San", "Female", "Miền Nam"),
               ("minhquang", "Minh Quang", "Male", "Miền Nam")]


def _voices_fpt(settings, refresh):
    return [Voice(id=i, name=n, lang="vi-VN", gender=g, engine="fpt", desc=d) for i, n, g, d in _FPT_VOICES]


def piper_dir(settings: Settings) -> Path:
    d = settings.models_dir() / "piper"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _voices_piper(settings, refresh):
    out = []
    for onnx in sorted(piper_dir(settings).glob("*.onnx")):
        cfg = onnx.with_suffix(".onnx.json")
        lang, n_spk, spk_map = "", 1, {}
        if cfg.exists():
            try:
                c = json.loads(cfg.read_text(encoding="utf-8"))
                lang = (c.get("language") or {}).get("code", "")
                n_spk = int(c.get("num_speakers", 1))
                spk_map = c.get("speaker_id_map") or {}
            except Exception:
                pass
        if n_spk > 1:
            names = {v: k for k, v in spk_map.items()} if spk_map else {}
            for sid in range(n_spk):
                out.append(Voice(id=f"{onnx.name}#{sid}", name=f"{onnx.stem} · {names.get(sid, sid)}",
                                 lang=lang, engine="piper"))
        else:
            out.append(Voice(id=onnx.name, name=onnx.stem, lang=lang, engine="piper"))
    return out


def piper_catalog(settings: Settings, refresh: bool = False) -> dict:
    """Danh sách tất cả giọng Piper trên HuggingFace (rhasspy/piper-voices)."""
    f = _cache_file("piper_voices.json")
    if f.exists() and not refresh:
        return json.loads(f.read_text(encoding="utf-8"))
    r = _session(settings).get("https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json", timeout=60)
    r.raise_for_status()
    f.write_text(r.text, encoding="utf-8")
    return r.json()


def piper_download(key: str, entry: dict, settings: Settings, progress=None) -> Path:
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    dest = piper_dir(settings)
    s = _session(settings)
    files = [p for p in entry.get("files", {}) if p.endswith((".onnx", ".onnx.json"))]
    for path in files:
        target = dest / Path(path).name
        with s.get(base + path, stream=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            done = 0
            tmp = target.with_suffix(target.suffix + ".part")
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 16):
                    fh.write(chunk)
                    done += len(chunk)
                    if progress and total:
                        progress(done / total, f"Tải {target.name}")
            os.replace(tmp, target)
    return dest / f"{key}.onnx"


def _voices_sapi(settings, refresh):
    try:
        out = subprocess.run(worker_cmd("list"), capture_output=True, text=True, encoding="utf-8",
                             timeout=60, **_nowin())
        data = json.loads(out.stdout.strip().splitlines()[-1]) if out.stdout.strip() else []
    except Exception:
        data = []
    return [Voice(id=d["id"], name=d["name"], lang=d.get("lang", ""), gender=d.get("gender", ""), engine="sapi")
            for d in data]


_XTTS_SPEAKERS = ["Claribel Dervla", "Daisy Studious", "Gracie Wise", "Tammie Ema", "Alison Dietlinde",
                  "Ana Florence", "Annmarie Nele", "Asya Anara", "Brenda Stern", "Gitta Nikolina",
                  "Henriette Usha", "Sofia Hellen", "Tammy Grit", "Tanja Adelina", "Vjollca Johnnie",
                  "Andrew Chipper", "Badr Odhiambo", "Dionisio Schuyler", "Royston Min", "Viktor Eka",
                  "Abrahan Mack", "Adde Michal", "Baldur Sanjin", "Craig Gutsy", "Damien Black",
                  "Gilberto Mathias", "Ilkin Urbano", "Kazuhiko Atallah", "Ludvig Milivoj", "Suad Qasim",
                  "Torcull Diarmuid", "Viktor Menelaos", "Zacharie Aimilios"]


def _voices_xtts(settings, refresh):
    out = [Voice(id="clone", name="🎤 Nhân bản giọng từ file mẫu", lang="đa ngôn ngữ", engine="xtts",
                 desc="chọn file mẫu bên dưới")]
    out += [Voice(id=s, name=s, lang="đa ngôn ngữ", engine="xtts", desc="giọng mẫu XTTS") for s in _XTTS_SPEAKERS]
    return out


# ======================================================================= TỔNG HỢP GIỌNG
def synthesize(engine: str, text: str, voice: str, out_wav: str | Path, opts: dict, settings: Settings,
               cancel=None, log=None) -> Path:
    """Đọc `text` bằng giọng `voice`, lưu WAV 48kHz stereo đã xử lý tốc độ/cao độ/âm lượng.

    opts: rate (%), pitch (nửa cung), volume (%), model, read_style, read_custom, tone (cách đọc của đoạn),
          lang_code, xtts_ref, xtts_model_dir, normalize
    File chỉ được ghi khi tạo thành công và có âm thanh thật (không để lại file rỗng/hỏng trong cache).
    """
    text = (text or "").strip()
    if not opts.get("raw"):
        text = speak_text(text, opts)
    if not text:
        raise TTSError("Văn bản rỗng")
    opts = apply_read_style(engine, opts)
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    info = ENGINES[engine]
    fn = globals()[f"_synth_{engine}"]
    limit = {"google": 1500, "fpt": 2000, "openai": 3500, "gemini": 3000, "azure": 3000,
             "elevenlabs": 4000, "gtts": 4000}.get(engine, 6000)
    pieces = chunk_text(text, limit) if len(text) > limit else [text]
    tmp_dir = out_wav.parent / (out_wav.stem + "_parts")
    tmp_dir.mkdir(exist_ok=True)
    raw_files = []
    try:
        for i, piece in enumerate(pieces):
            if cancel is not None and cancel.is_set():
                from .ffmpeg_utils import Cancelled

                raise Cancelled()
            base = tmp_dir / f"p{i:03d}"
            f = Path(fn(piece, voice, base, opts, settings))
            if not f.exists() or f.stat().st_size < 200:
                raise TTSError(f"{info['name']}: không nhận được âm thanh (file rỗng). "
                               "Kiểm tra mạng/API key hoặc thử giọng khác.")
            raw_files.append(f)
        tmp_out = out_wav.with_name(out_wav.stem + ".tmp.wav")
        _post_process(raw_files, tmp_out, info, opts, cancel, log, trim=True)
        if _duration_or_zero(tmp_out) < 0.25:
            # Lọc khoảng lặng cắt mất cả câu (giọng quá nhỏ) -> làm lại không cắt
            _post_process(raw_files, tmp_out, info, opts, cancel, log, trim=False)
        if _duration_or_zero(tmp_out) < 0.1:
            raise TTSError(f"{info['name']}: âm thanh tạo ra bị rỗng. Thử giọng hoặc công cụ khác.")
        os.replace(tmp_out, out_wav)
    finally:
        for f in raw_files:
            try:
                f.unlink()
            except OSError:
                pass
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
    return out_wav


def _duration_or_zero(path: Path) -> float:
    try:
        if not path.exists() or path.stat().st_size < 1000:
            return 0.0
        from .ffmpeg_utils import media_duration

        return media_duration(path)
    except Exception:
        return 0.0


def _post_process(raw_files, out, info, opts, cancel, log, trim=True):
    """Ghép các mảnh + chỉnh tốc độ/cao độ/âm lượng + cắt khoảng lặng đầu/cuối."""
    rate = float(opts.get("rate", 0) or 0)
    pitch = float(opts.get("pitch", 0) or 0)
    vol = float(opts.get("volume", 0) or 0)
    tempo = 1.0 if info["rate"] else 1.0 + rate / 100.0
    filters = []
    if pitch and not info["pitch"]:
        p = 2 ** (pitch / 12.0)
        filters.append(f"asetrate={int(48000 * p)},aresample=48000")
        tempo = tempo / p
    if abs(tempo - 1.0) > 0.01:
        filters += _atempo_chain(tempo)
    if vol:
        filters.append(f"volume={max(0.05, 1 + vol / 100.0):.3f}")
    if trim:
        filters.append("silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.05")
        filters.append("areverse,silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08,areverse")
    args = []
    if len(raw_files) == 1:
        args += ["-i", str(raw_files[0])]
        pre = "[0:a]aresample=48000"
    else:
        for f in raw_files:
            args += ["-i", str(f)]
        pre = "".join(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}];" for i in range(len(raw_files)))
        pre += "".join(f"[a{i}]" for i in range(len(raw_files))) + f"concat=n={len(raw_files)}:v=0:a=1"
    chain = ",".join(filters + ["aformat=sample_rates=48000:channel_layouts=stereo"])
    args += ["-filter_complex", pre + "," + chain + "[out]", "-map", "[out]", "-c:a", "pcm_s16le", "-f", "wav", str(out)]
    run_ffmpeg(args, cancel=cancel, log=log)


def _atempo_chain(f: float) -> list[str]:
    out = []
    while f > 2.0:
        out.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        out.append("atempo=0.5")
        f /= 0.5
    out.append(f"atempo={f:.4f}")
    return out


def _signed(v: float, unit: str) -> str:
    return f"{'+' if v >= 0 else '-'}{abs(int(round(v)))}{unit}"


def _synth_edge(text, voice, base: Path, opts, settings):
    import edge_tts

    out = base.with_suffix(".mp3")
    rate = _signed(float(opts.get("rate", 0) or 0), "%")
    pitch = _signed(float(opts.get("pitch", 0) or 0) * 8, "Hz")  # ~8Hz mỗi nửa cung

    async def go():
        last = None
        for attempt in range(3):
            try:
                c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, proxy=settings.proxy())
                await c.save(str(out))
                if out.exists() and out.stat().st_size > 0:
                    return
            except Exception as e:  # mạng chập chờn
                last = e
            await asyncio.sleep(1.5 * (attempt + 1))
        raise TTSError(f"Edge TTS lỗi: {last}")
    asyncio.run(go())
    return out


def _synth_gtts(text, voice, base: Path, opts, settings):
    from gtts import gTTS

    parts = voice.split("|")
    lang = parts[0]
    tld = parts[1] if len(parts) > 1 else "com"
    slow = len(parts) > 2 and parts[2] == "slow"
    out = base.with_suffix(".mp3")
    p = settings.proxy()
    old = {k: os.environ.get(k) for k in ("HTTPS_PROXY", "HTTP_PROXY")}
    if p:
        os.environ["HTTPS_PROXY"] = os.environ["HTTP_PROXY"] = p
    try:
        gTTS(text=text, lang=lang, tld=tld, slow=slow).save(str(out))
    except Exception as e:
        raise TTSError(f"gTTS lỗi: {e}") from e
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return out


def _synth_openai(text, voice, base: Path, opts, settings):
    key = _key("openai", settings)
    api = (settings.get("api", "openai_base") or "https://api.openai.com/v1").rstrip("/")
    model = opts.get("model") or "gpt-4o-mini-tts"
    speed = max(0.25, min(4.0, 1 + float(opts.get("rate", 0) or 0) / 100.0))
    body = {"model": model, "input": text, "voice": voice, "speed": speed, "response_format": "mp3"}
    if model.startswith("gpt-"):
        lang = {v: k for k, v in LANG_CODES.items()}.get(opts.get("lang_code") or "", "")
        body["instructions"] = opts.get("style") or (
            f"Đọc bằng {lang} chuẩn, phát âm rõ ràng, tự nhiên như người dẫn chuyện phim." if lang == "Tiếng Việt"
            else "Speak naturally and clearly with correct native pronunciation, like a movie narrator.")
    r = _session(settings).post(f"{api}/audio/speech", headers={"Authorization": f"Bearer {key}"}, json=body,
                                timeout=180)
    if r.status_code >= 400:
        raise TTSError(f"OpenAI TTS lỗi {r.status_code}: {r.text[:300]}")
    out = base.with_suffix(".mp3")
    out.write_bytes(r.content)
    return out


def _synth_elevenlabs(text, voice, base: Path, opts, settings):
    key = _key("elevenlabs", settings)
    model = opts.get("model") or "eleven_multilingual_v2"
    stab, sty = opts.get("el_settings") or (0.45, 0.25)
    if model == "eleven_v3" and opts.get("el_tag"):
        text = f"{opts['el_tag']} {text}"
    body = {"text": text, "model_id": model,
            "voice_settings": {"stability": stab, "similarity_boost": 0.8, "style": sty, "use_speaker_boost": True}}
    r = _session(settings).post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                                params={"output_format": "mp3_44100_128"},
                                headers={"xi-api-key": key, "Accept": "audio/mpeg"}, json=body, timeout=180)
    if r.status_code >= 400:
        raise TTSError(f"ElevenLabs lỗi {r.status_code}: {r.text[:300]}")
    out = base.with_suffix(".mp3")
    out.write_bytes(r.content)
    return out


def _synth_gemini(text, voice, base: Path, opts, settings):
    key = _key("gemini", settings)
    model = opts.get("model") or "gemini-2.5-flash-preview-tts"
    style = (opts.get("style") or "").strip()
    prompt = f"{style}: {text}" if style else text
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    for attempt in range(4):
        r = _session(settings).post(url, params={"key": key}, json=body, timeout=180)
        if r.status_code in (429, 500, 503):
            time.sleep(4 * (attempt + 1))
            continue
        break
    if r.status_code >= 400:
        raise TTSError(f"Gemini TTS lỗi {r.status_code}: {r.text[:300]}")
    try:
        part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError):
        raise TTSError(f"Gemini TTS trả về lạ: {r.text[:300]}")
    pcm = base64.b64decode(part["data"])
    rate = 24000
    mt = part.get("mimeType", "")
    if "rate=" in mt:
        try:
            rate = int(mt.split("rate=")[1].split(";")[0])
        except ValueError:
            pass
    out = base.with_suffix(".wav")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out


def _synth_google(text, voice, base: Path, opts, settings):
    key = _key("google", settings)
    lang = "-".join(voice.split("-")[:2])
    rate = max(0.25, min(4.0, 1 + float(opts.get("rate", 0) or 0) / 100.0))
    body = {"input": {"text": text}, "voice": {"languageCode": lang, "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": rate}}
    r = _session(settings).post("https://texttospeech.googleapis.com/v1/text:synthesize", params={"key": key},
                                json=body, timeout=120)
    if r.status_code >= 400:
        raise TTSError(f"Google TTS lỗi {r.status_code}: {r.text[:300]}")
    out = base.with_suffix(".mp3")
    out.write_bytes(base64.b64decode(r.json()["audioContent"]))
    return out


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _synth_azure(text, voice, base: Path, opts, settings):
    key = _key("azure", settings)
    lang = "-".join(voice.split("-")[:2])
    rate = _signed(float(opts.get("rate", 0) or 0), "%")
    pitch = _signed(float(opts.get("pitch", 0) or 0), "st")
    inner = f'<prosody rate="{rate}" pitch="{pitch}">{_xml_escape(text)}</prosody>'
    style = (opts.get("style") or "").strip()
    if style and " " not in style:
        inner = f'<mstts:express-as style="{_xml_escape(style)}">{inner}</mstts:express-as>'
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang}">'
            f'<voice name="{voice}">{inner}</voice></speak>')
    r = _session(settings).post(_azure_host(settings) + "/cognitiveservices/v1",
                                headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                                         "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                                         "User-Agent": "MovieRecapAI"},
                                data=ssml.encode("utf-8"), timeout=120)
    if r.status_code >= 400:
        raise TTSError(f"Azure TTS lỗi {r.status_code}: {r.text[:300]}")
    out = base.with_suffix(".mp3")
    out.write_bytes(r.content)
    return out


def _synth_fpt(text, voice, base: Path, opts, settings):
    key = _key("fpt", settings)
    s = _session(settings)
    r = s.post("https://api.fpt.ai/hmi/tts/v5", data=text.encode("utf-8"),
               headers={"api-key": key, "voice": voice, "speed": "0", "format": "mp3"}, timeout=60)
    if r.status_code >= 400:
        raise TTSError(f"FPT.AI lỗi {r.status_code}: {r.text[:300]}")
    data = r.json()
    url = data.get("async")
    if not url:
        raise TTSError(f"FPT.AI: {data.get('message', data)}")
    out = base.with_suffix(".mp3")
    for _ in range(60):  # file âm thanh sẵn sàng sau vài giây
        time.sleep(2)
        g = s.get(url, timeout=60)
        if g.status_code == 200 and len(g.content) > 1000:
            out.write_bytes(g.content)
            return out
    raise TTSError("FPT.AI: quá thời gian chờ file âm thanh.")


_VIENEU: dict = {}


def _synth_vieneu(text, voice, base: Path, opts, settings):
    try:
        from vieneu import Vieneu
    except ImportError as e:
        raise TTSError("Chưa cài VieNeu-TTS: pip install vieneu  (lần đầu sẽ tự tải model từ HuggingFace)") from e
    mode = opts.get("model") or "v3turbo"
    mode = mode if mode in ("v3turbo", "v3nano") else "v3turbo"
    tts = _VIENEU.get(mode)
    if tts is None:
        tts = Vieneu(mode=mode)
        _VIENEU[mode] = tts
    if voice == "clone":
        ref = opts.get("xtts_ref") or ""
        if not ref or not Path(ref).exists():
            raise TTSError("Chọn file giọng mẫu (3-8 giây, giọng rõ) để nhân bản.")
        audio = tts.infer(text, ref_audio=ref)
    else:
        audio = tts.infer(text, voice=voice)
    out = base.with_suffix(".wav")
    tts.save(audio, str(out))
    return out


_PIPER_CACHE: dict = {}


def _synth_piper(text, voice, base: Path, opts, settings):
    try:
        from piper import PiperVoice
    except ImportError as e:
        raise TTSError("Chưa cài Piper: pip install piper-tts") from e
    name, _, sid = voice.partition("#")
    model = piper_dir(settings) / name
    if not model.exists():
        raise TTSError(f"Chưa tải giọng Piper {name}. Bấm 'Tải giọng Piper'.")
    pv = _PIPER_CACHE.get(str(model))
    if pv is None:
        pv = PiperVoice.load(str(model))
        _PIPER_CACHE[str(model)] = pv
    length_scale = 1.0 / max(0.3, 1 + float(opts.get("rate", 0) or 0) / 100.0)
    out = base.with_suffix(".wav")
    speaker = int(sid) if sid else None
    with wave.open(str(out), "wb") as wf:
        if hasattr(pv, "synthesize_wav"):  # piper-tts >= 1.3
            from piper import SynthesisConfig

            cfg = SynthesisConfig(speaker_id=speaker, length_scale=length_scale)
            pv.synthesize_wav(text, wf, syn_config=cfg)
        else:  # piper-tts 1.2
            pv.synthesize(text, wf, speaker_id=speaker, length_scale=length_scale)
    return out


def _synth_sapi(text, voice, base: Path, opts, settings):
    out = base.with_suffix(".wav")
    txt_file = base.with_suffix(".txt")
    txt_file.write_text(text, encoding="utf-8")
    rate = int(180 * (1 + float(opts.get("rate", 0) or 0) / 100.0))
    r = subprocess.run(worker_cmd("say", voice, str(txt_file), str(out), str(rate)), capture_output=True,
                       text=True, encoding="utf-8", timeout=300, **_nowin())
    txt_file.unlink(missing_ok=True)
    if not out.exists() or out.stat().st_size < 100:
        # macOS lưu dạng AIFF dù đuôi .wav
        alt = [p for p in base.parent.glob(base.name + "*") if p.suffix in (".aiff", ".aif")]
        if alt:
            return alt[0]
        raise TTSError("Giọng hệ điều hành lỗi: " + (r.stderr or r.stdout)[-300:])
    return out


_XTTS = {}


def _synth_xtts(text, voice, base: Path, opts, settings):
    lang = opts.get("lang_code") or "en"
    ref = opts.get("xtts_ref") or ""
    model_dir = (opts.get("xtts_model_dir") or "").strip()
    speed = max(0.5, min(2.0, 1 + float(opts.get("rate", 0) or 0) / 100.0))
    out = base.with_suffix(".wav")
    try:
        import torch
    except ImportError as e:
        raise TTSError("XTTS cần cài thêm: pip install coqui-tts torch torchaudio") from e
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if model_dir:  # viXTTS hoặc model XTTS tinh chỉnh
        if voice != "clone" or not ref:
            raise TTSError("Model XTTS tùy chỉnh cần chọn giọng 'Nhân bản' và file giọng mẫu.")
        key = "custom:" + model_dir
        if key not in _XTTS:
            from TTS.tts.configs.xtts_config import XttsConfig
            from TTS.tts.models.xtts import Xtts

            cfg = XttsConfig()
            cfg.load_json(os.path.join(model_dir, "config.json"))
            m = Xtts.init_from_config(cfg)
            m.load_checkpoint(cfg, checkpoint_dir=model_dir, use_deepspeed=False)
            m.to(dev)
            _XTTS[key] = m
        m = _XTTS[key]
        lat, emb = m.get_conditioning_latents(audio_path=[ref])
        res = m.inference(text, lang, lat, emb, speed=speed, temperature=0.7, enable_text_splitting=True)
        import numpy as np

        wav_data = (np.clip(np.asarray(res["wav"]), -1, 1) * 32767).astype("int16")
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(wav_data.tobytes())
        return out
    if "std" not in _XTTS:
        from TTS.api import TTS

        os.environ.setdefault("COQUI_TOS_AGREED", "1")
        _XTTS["std"] = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(dev)
    tts = _XTTS["std"]
    kw = {"speaker_wav": ref} if voice == "clone" else {"speaker": voice}
    if voice == "clone" and not ref:
        raise TTSError("Chọn file giọng mẫu (6-30 giây, sạch tiếng ồn) để nhân bản.")
    tts.tts_to_file(text=text, language=lang, file_path=str(out), speed=speed, **kw)
    return out


# ======================================================================= Worker giọng hệ điều hành
def _nowin() -> dict:
    return {"creationflags": 0x08000000} if os.name == "nt" else {}


def worker_cmd(*args: str) -> list[str]:
    """Chạy pyttsx3 ở tiến trình riêng (tránh treo COM/SAPI trong luồng giao diện)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--sapi-worker", *args]
    from .components import python_exe

    main = Path(__file__).resolve().parent.parent / "main.py"
    return [python_exe(), str(main), "--sapi-worker", *args]


def sapi_worker(argv: list[str]) -> int:
    import pyttsx3

    eng = pyttsx3.init()
    if argv and argv[0] == "list":
        res = []
        for v in eng.getProperty("voices"):
            langs = []
            for lg in getattr(v, "languages", []) or []:
                langs.append(lg.decode(errors="ignore") if isinstance(lg, bytes) else str(lg))
            g = getattr(v, "gender", "") or ""
            res.append({"id": v.id, "name": v.name, "lang": ",".join(langs), "gender": str(g)})
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if argv and argv[0] == "say":
        voice, txt, out, rate = argv[1], argv[2], argv[3], int(argv[4])
        eng.setProperty("voice", voice)
        eng.setProperty("rate", rate)
        eng.save_to_file(Path(txt).read_text(encoding="utf-8"), out)
        eng.runAndWait()
        return 0
    return 1


def speak_text(text: str, opts: dict) -> str:
    """Văn bản thực sự được đọc: từ điển phát âm + chuẩn hóa số/ngày/đơn vị/viết tắt."""
    return textnorm.prepare(text, opts.get("lang_code") or "vi", normalize=opts.get("normalize", True))


def voice_cache_key(engine: str, voice: str, text: str, opts: dict) -> str:
    keys = ("rate", "pitch", "volume", "model", "style", "lang_code", "xtts_ref", "xtts_model_dir", "normalize",
            "ai_pron", "transliterate", "read_style", "read_custom", "tone")
    payload = json.dumps([engine, voice, text, {k: opts.get(k) for k in keys}, textnorm.load_dict()],
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
