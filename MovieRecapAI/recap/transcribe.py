"""Nhận dạng lời thoại (Speech-to-Text) trong phim.

Engine:
  faster_whisper : offline, mã nguồn mở (SYSTRAN/faster-whisper), chạy CPU hoặc GPU NVIDIA.
  openai         : OpenAI Whisper API (whisper-1).
  groq           : Groq Whisper large-v3 (rất nhanh, có gói miễn phí).
  subtitle       : dùng file phụ đề có sẵn (.srt/.vtt/.ass).
  embedded       : trích phụ đề nhúng sẵn trong file video (MKV/MP4).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import requests

from .config import Settings
from .ffmpeg_utils import Cancelled, extract_audio, media_duration, run_ffmpeg
from .subtitles import parse_subtitle_file

ENGINES = {
    "faster_whisper": "Whisper offline (faster-whisper) - miễn phí",
    "groq": "Groq Whisper API - nhanh, có gói free",
    "openai": "OpenAI Whisper API",
    "subtitle": "Dùng file phụ đề có sẵn (.srt/.vtt/.ass)",
    "embedded": "Lấy phụ đề nhúng trong video",
}

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "distil-large-v3"]

LANGUAGES = {
    "auto": "Tự nhận diện", "vi": "Tiếng Việt", "en": "English", "zh": "中文", "ja": "日本語",
    "ko": "한국어", "th": "ไทย", "fr": "Français", "es": "Español", "de": "Deutsch", "ru": "Русский",
    "hi": "हिन्दी", "id": "Bahasa Indonesia", "pt": "Português", "it": "Italiano",
}


def transcribe(video: str, work_dir: Path, settings: Settings, engine: str, log, progress, cancel,
               subtitle_file: str | None = None, model: str = "small", language: str = "auto",
               device: str = "auto") -> list[dict]:
    work_dir.mkdir(parents=True, exist_ok=True)
    lang = None if language in ("", "auto", None) else language
    if engine == "subtitle":
        if not subtitle_file:
            raise RuntimeError("Hãy chọn file phụ đề.")
        segs = parse_subtitle_file(subtitle_file)
        log(f"Đã đọc {len(segs)} dòng phụ đề từ {Path(subtitle_file).name}")
        return segs
    if engine == "embedded":
        return _embedded(video, work_dir, log, cancel)

    duration = media_duration(video)
    if engine == "faster_whisper":
        wav = work_dir / "audio_16k.wav"
        if not wav.exists():
            log("Đang tách âm thanh...")
            extract_audio(video, str(wav), cancel=cancel, total=duration,
                          on_progress=lambda p: progress(p * 0.1, "Tách âm thanh"))
        return _faster_whisper(str(wav), duration, settings, model, lang, device, log, progress, cancel)
    if engine in ("openai", "groq"):
        return _api_whisper(video, work_dir, duration, settings, engine, lang, log, progress, cancel)
    raise RuntimeError(f"Engine không hợp lệ: {engine}")


def _embedded(video, work_dir, log, cancel) -> list[dict]:
    from .ffmpeg_utils import probe

    info = probe(video)
    text_codecs = {"subrip", "ass", "ssa", "mov_text", "webvtt", "text", ""}
    streams = [s for s in info.subtitle_streams if s.get("codec") in text_codecs]
    if not streams:
        raise RuntimeError("Video không có phụ đề nhúng dạng chữ (phụ đề hình ảnh PGS/VobSub không đọc được).")
    # ưu tiên tiếng Việt > tiếng Anh > đầu tiên
    pick = streams[0]
    for pref in ("vie", "vi", "eng", "en"):
        for s in streams:
            if s.get("lang", "").lower() == pref:
                pick = s
                break
        else:
            continue
        break
    idx = streams.index(pick)
    out = work_dir / "embedded.srt"
    log(f"Trích phụ đề nhúng #{idx} ({pick.get('lang') or '?'})...")
    run_ffmpeg(["-i", video, "-map", f"0:s:{idx}", str(out)], cancel=cancel)
    return parse_subtitle_file(out)


def _faster_whisper(wav, duration, settings, model, lang, device, log, progress, cancel) -> list[dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("Chưa cài faster-whisper. Chạy: pip install faster-whisper") from e
    dev, ctype = "cpu", "int8"
    if device in ("auto", "cuda"):
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                dev, ctype = "cuda", "float16"
        except Exception:
            pass
        if device == "cuda" and dev != "cuda":
            log("Không thấy GPU CUDA, chuyển sang CPU.", level="warn")
    log(f"Tải model Whisper '{model}' ({dev}). Lần đầu sẽ tải về vài trăm MB...")
    progress(0.1, f"Tải model Whisper {model}")
    try:
        wm = WhisperModel(model, device=dev, compute_type=ctype,
                          download_root=str(settings.models_dir() / "whisper"))
    except Exception as e:
        if dev == "cuda":
            log(f"GPU lỗi ({e}) - chuyển sang CPU.", level="warn")
            wm = WhisperModel(model, device="cpu", compute_type="int8",
                              download_root=str(settings.models_dir() / "whisper"))
        else:
            raise RuntimeError(f"Không tải được model Whisper '{model}' (lần đầu cần Internet tới huggingface.co). "
                               f"Có thể dùng engine Groq/OpenAI Whisper API thay thế.\nChi tiết: {e}") from e
    segments, info = wm.transcribe(wav, language=lang, vad_filter=True, beam_size=5,
                                   condition_on_previous_text=False)
    log(f"Ngôn ngữ nhận diện: {info.language} ({info.language_probability:.0%})")
    out = []
    for s in segments:
        if cancel.is_set():
            raise Cancelled()
        text = s.text.strip()
        if text:
            out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": text})
        progress(0.1 + 0.9 * min(1.0, s.end / max(duration, 1)), f"Nhận dạng thoại {int(s.end)}/{int(duration)}s")
    return out


def _api_whisper(video, work_dir, duration, settings, engine, lang, log, progress, cancel) -> list[dict]:
    if engine == "openai":
        key = settings.get("api", "openai_key")
        base = (settings.get("api", "openai_base") or "https://api.openai.com/v1").rstrip("/")
        model = "whisper-1"
    else:
        key = settings.get("api", "groq_key")
        base = "https://api.groq.com/openai/v1"
        model = "whisper-large-v3-turbo"
    if not key:
        raise RuntimeError(f"Chưa nhập API key {engine.upper()} (mục 🔑 API & Cài đặt).")
    # Giới hạn 25MB/lần gửi -> chia file 10 phút, mp3 mono 48kbps (~3.6MB/đoạn)
    chunk = 600.0
    n = max(1, math.ceil(duration / chunk))
    sess = requests.Session()
    proxy = (settings.get("api", "proxy") or "").strip()
    if proxy:
        sess.proxies = {"http": proxy, "https": proxy}
    out: list[dict] = []
    cache_dir = work_dir / f"stt_{engine}"
    cache_dir.mkdir(exist_ok=True)
    for i in range(n):
        if cancel.is_set():
            raise Cancelled()
        start = i * chunk
        cache = cache_dir / f"part_{i:03d}.json"
        if cache.exists():
            out.extend(json.loads(cache.read_text(encoding="utf-8")))
            continue
        mp3 = cache_dir / f"part_{i:03d}.mp3"
        run_ffmpeg(["-ss", f"{start:.2f}", "-t", f"{chunk:.2f}", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "libmp3lame", "-b:a", "48k", str(mp3)], cancel=cancel)
        progress(i / n, f"Gửi đoạn âm thanh {i + 1}/{n} lên {engine}")
        data = {"model": model, "response_format": "verbose_json", "timestamp_granularities[]": "segment"}
        if lang:
            data["language"] = lang
        for attempt in range(4):
            with open(mp3, "rb") as f:
                r = sess.post(f"{base}/audio/transcriptions", headers={"Authorization": f"Bearer {key}"},
                              data=data, files={"file": (mp3.name, f, "audio/mpeg")}, timeout=600)
            if r.status_code in (429, 500, 502, 503):
                import time

                log(f"API bận ({r.status_code}), thử lại...", level="warn")
                time.sleep(5 * (attempt + 1))
                continue
            break
        if r.status_code >= 400:
            raise RuntimeError(f"Lỗi nhận dạng giọng nói {r.status_code}: {r.text[:300]}")
        res = r.json()
        part = []
        for s in res.get("segments", []):
            t = (s.get("text") or "").strip()
            if t:
                part.append({"start": round(start + s["start"], 2), "end": round(start + s["end"], 2), "text": t})
        cache.write_text(json.dumps(part, ensure_ascii=False), encoding="utf-8")
        try:
            os.remove(mp3)
        except OSError:
            pass
        out.extend(part)
    progress(1.0, "Xong nhận dạng thoại")
    return out
