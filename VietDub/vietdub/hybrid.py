"""Chế độ lai: mỗi bước tự chọn chạy trên máy hay qua mạng, cái nào có sẵn & nhanh thì dùng, lỗi thì chuyển cách kia.

- Kiểm tra mạng (có lưu kết quả 45 giây để không làm chậm app).
- Kiểm tra Ollama (AI trên máy): đang chạy chưa, đã tải model chưa; đã cài mà chưa mở thì tự mở.
- Lập "chuỗi dự phòng" cho AI dịch, nhận dạng lời thoại và giọng đọc theo chế độ:
  auto (Tự động) · offline (Chỉ trên máy) · online (Ưu tiên online).
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from .config import Settings
from .media import no_window

NET_URLS = ("https://www.gstatic.com/generate_204", "https://cloudflare.com/cdn-cgi/trace", "https://api.github.com")
_NET: dict = {"t": 0.0, "ok": False}
_NET_LOCK = threading.Lock()


def net_ok(settings: Settings | None = None, force: bool = False) -> bool:
    """Có mạng không (kết quả giữ 45 giây)."""
    with _NET_LOCK:
        if not force and time.time() - _NET["t"] < 45:
            return _NET["ok"]
        ok = False
        for u in NET_URLS:
            try:
                r = requests.get(u, timeout=4, proxies=settings.proxies() if settings else None)
                if r.status_code < 500:
                    ok = True
                    break
            except requests.RequestException:
                continue
        _NET.update(t=time.time(), ok=ok)
        return ok


def set_net(ok: bool) -> None:
    """Ghi đè kết quả kiểm tra mạng (dùng khi kiểm thử / người dùng bấm Kiểm tra lại)."""
    with _NET_LOCK:
        _NET.update(t=time.time(), ok=bool(ok))


def online_allowed(settings: Settings) -> bool:
    return settings.mode != "offline" and net_ok(settings)


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# ------------------------------------------------------------------ Ollama
def ollama_exe() -> str | None:
    from .config import app_dir

    for p in (app_dir() / "tools" / "ollama" / "ollama.exe", app_dir() / "tools" / "ollama" / "ollama"):
        if p.exists():  # Ollama cài cùng ổ với app (install.bat)
            return str(p)
    found = shutil.which("ollama")
    if found:
        return found
    if os.name == "nt":
        for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", "")):
            for sub in ("Programs/Ollama/ollama.exe", "Ollama/ollama.exe"):
                p = Path(base) / sub
                if base and p.exists():
                    return str(p)
    return None


def ollama_has(models: list[str], model: str) -> bool:
    return any(m == model or m == model + ":latest" or m.split(":")[0] == model for m in models)


def ollama_model(settings: Settings) -> str:
    return (settings.get("ai", "ollama_model") or "qwen2.5:7b").strip()


def ensure_ollama(settings: Settings, log=None, wait: float = 15.0) -> tuple[bool, list[str]]:
    """Ollama đã cài nhưng chưa mở -> tự mở (chạy ẩn) và đợi tối đa `wait` giây."""
    from .ai import ollama_status

    ok, models = ollama_status(settings)
    if ok or not settings.get("ai", "auto_start_ollama", True):
        return ok, models
    exe = ollama_exe()
    if not exe:
        return False, []
    if log:
        log("Đang mở Ollama (AI trên máy)...")
    try:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, **no_window())
    except OSError:
        return False, []
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(0.7)
        ok, models = ollama_status(settings)
        if ok:
            return ok, models
    return False, []


# ------------------------------------------------------------------ chuỗi dự phòng
def online_ai(settings: Settings) -> list[str]:
    """Các AI online dùng được ngay (có mạng + có key), theo thứ tự ưu tiên."""
    from .ai import FALLBACK_ORDER, PROVIDERS

    if not online_allowed(settings):
        return []
    return [p for p in FALLBACK_ORDER if settings.key(PROVIDERS[p]["key"])]


def ai_chain(settings: Settings, log=None) -> list[str]:
    """Thứ tự AI sẽ thử. [] = không dùng AI."""
    pref = settings.get("ai", "provider") or "auto"
    if pref == "none":
        return []
    mode = settings.mode
    if mode == "offline":
        return ["ollama"]
    online = online_ai(settings)
    ok, models = ensure_ollama(settings, log, wait=8.0) if pref == "ollama" else (False, [])
    local_ready = ok and ollama_has(models, ollama_model(settings))
    if pref not in ("auto", "ollama") and pref in online:
        online.remove(pref)
        online.insert(0, pref)
    if pref == "ollama" and local_ready:
        chain = ["ollama", *online]
    elif pref == "ollama" or mode == "online" or pref != "auto":
        chain = [*online, "ollama"]
    else:  # auto: online nhanh & viết dài tốt hơn -> trước; không có key / mạng -> AI trên máy
        chain = [*online, "ollama"] if online else ["ollama"]
    if pref not in ("auto", "ollama") and pref not in chain and log:
        log(f"Không dùng được AI đã chọn ({pref}: chưa có key hoặc mất mạng) - tự chọn AI khác.", "warn")
    if not settings.get("ai", "fallback", True):
        chain = chain[:1]
    return list(dict.fromkeys(chain))


ONLINE_STT = ("groq", "openai")


def stt_online(settings: Settings) -> list[str]:
    return [p for p in ONLINE_STT if settings.key(p)] if online_allowed(settings) else []


LOCAL_VOICES = ("vieneu", "piper", "sapi")
ONLINE_VOICES = ("edge", "gtts")


def voice_ready(engine: str, settings: Settings) -> bool:
    from .voices import ENGINES

    e = ENGINES.get(engine)
    if not e:
        return False
    if e.get("online"):
        if not online_allowed(settings) or (e.get("key") and not settings.key(e["key"])):
            return False
    mod = {"vieneu": "vieneu", "piper": "piper", "edge": "edge_tts", "gtts": "gtts"}.get(engine)
    if mod and not has_module(mod):
        return False
    if engine == "sapi" and not sys.platform.startswith("win"):
        return False
    return True


def voice_chain(settings: Settings, engine: str) -> list[str]:
    """Giọng đã chọn trước; không dùng được thì giọng dự phòng (trên máy <-> online)."""
    chain = [engine]
    if settings.get("voice", "fallback", True):
        local = list(LOCAL_VOICES)
        online = [] if settings.offline else list(ONLINE_VOICES)
        chain += (online + local) if settings.mode == "online" else (local + online)
    chain = list(dict.fromkeys(chain))
    ready = [e for e in chain if voice_ready(e, settings)]
    return ready or [engine]


# ------------------------------------------------------------------ trạng thái cho giao diện
def status(settings: Settings, force: bool = False) -> dict:
    """Kiểm tra nhanh mọi thành phần (chạy ở luồng nền)."""
    from .ai import PROVIDERS, ollama_status

    net = net_ok(settings, force=force) if settings.mode != "offline" else False
    ok, models = ollama_status(settings)
    keys = [p for p in PROVIDERS if PROVIDERS[p]["key"] and settings.key(PROVIDERS[p]["key"])]
    return {
        "mode": settings.mode, "net": net, "ollama": ok, "ollama_installed": ok or bool(ollama_exe()),
        "ollama_models": models, "ollama_model": ollama_model(settings),
        "ollama_ready": ok and ollama_has(models, ollama_model(settings)),
        "keys": keys, "ytdlp": has_module("yt_dlp"), "cv2": has_module("cv2"), "pil": has_module("PIL"),
        "vieneu": has_module("vieneu"), "whisper_cpu": has_module("faster_whisper"),
        "whisper_gpu": os.name == "nt",
    }


def describe(st: dict) -> list[tuple[str, bool, str]]:
    """[(tên, tốt?, giải thích)] để hiện đèn trạng thái."""
    out = []
    if st["mode"] != "offline":
        out.append(("Mạng", st["net"], "Có mạng: dùng được AI / giọng online" if st["net"] else
                    "Không có mạng: app tự dùng công cụ trên máy"))
    if st["ollama_ready"]:
        out.append(("AI trên máy", True, f"Ollama đang chạy · {st['ollama_model']}"))
    elif st["ollama"]:
        out.append(("AI trên máy", False, f"Ollama đang chạy nhưng chưa tải {st['ollama_model']} (⚙️ Cài đặt)"))
    else:
        out.append(("AI trên máy", False, "Chưa mở/cài Ollama" + (" (app sẽ tự mở khi cần)"
                                                                   if st["ollama_installed"] else "")))
    if st["mode"] != "offline":
        out.append(("AI online", bool(st["keys"]) and st["net"],
                    ("Có key: " + ", ".join(st["keys"])) if st["keys"] else "Chưa nhập API key nào"))
    return out
