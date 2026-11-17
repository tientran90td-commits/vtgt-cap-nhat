"""Nhận dạng lời thoại (Speech-to-Text) trong phim.

Engine:
  faster_whisper : offline, mã nguồn mở (SYSTRAN/faster-whisper), chạy CPU hoặc GPU NVIDIA.
  whisper_gpu    : offline, whisper.cpp bản Vulkan - chạy trên card AMD/Intel/NVIDIA.
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
    "whisper_gpu": "⚡ Whisper bằng card đồ họa AMD/Intel/NVIDIA (whisper.cpp Vulkan)",
    "groq": "Groq Whisper API - nhanh, có gói free",
    "openai": "OpenAI Whisper API",
    "subtitle": "Dùng file phụ đề có sẵn (.srt/.vtt/.ass)",
    "embedded": "Lấy phụ đề nhúng trong video",
}

WHISPER_MODELS = {
    "auto": "Tự chọn theo máy (khuyên dùng)",
    "large-v3-turbo": "large-v3-turbo - chính xác cao, nhanh",
    "large-v3": "large-v3 - chính xác nhất (chậm trên CPU)",
    "medium": "medium",
    "small": "small - nhanh",
    "base": "base",
    "tiny": "tiny - siêu nhanh, kém chính xác",
    "distil-large-v3": "distil-large-v3 (chỉ tiếng Anh)",
}


def has_cuda() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolve_model(model: str, device: str = "auto") -> str:
    """'auto': GPU NVIDIA -> large-v3-turbo; CPU >= 8 luồng -> large-v3-turbo (int8); máy yếu -> small."""
    if model and model != "auto":
        return model
    if device != "cpu" and has_cuda():
        return "large-v3-turbo"
    return "large-v3-turbo" if (os.cpu_count() or 4) >= 8 else "small"

LANGUAGES = {
    "auto": "Tự nhận diện", "vi": "Tiếng Việt", "en": "English", "zh": "中文", "ja": "日本語",
    "ko": "한국어", "th": "ไทย", "fr": "Français", "es": "Español", "de": "Deutsch", "ru": "Русский",
    "hi": "हिन्दी", "id": "Bahasa Indonesia", "pt": "Português", "it": "Italiano",
}


def transcribe(video: str, work_dir: Path, settings: Settings, engine: str, log, progress, cancel,
               subtitle_file: str | None = None, model: str = "auto", language: str = "auto",
               device: str = "auto", prompt: str = "") -> list[dict]:
    """prompt: gợi ý cho Whisper (tên phim, tên nhân vật) để nghe đúng tên riêng."""
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
    if engine in ("faster_whisper", "whisper_gpu"):
        wav = work_dir / "audio_16k.wav"
        if not wav.exists():
            log("Đang tách âm thanh...")
            extract_audio(video, str(wav), cancel=cancel, total=duration,
                          on_progress=lambda p: progress(p * 0.1, "Tách âm thanh"))
        if engine == "whisper_gpu":
            from . import whisper_gpu

            m = model if model and model != "auto" else "large-v3-turbo"
            try:
                return whisper_gpu.transcribe(str(wav), duration, settings, m, lang, log, progress, cancel, prompt,
                                              work_dir=work_dir)
            except whisper_gpu.WhisperGPUError as e:
                log(f"Whisper GPU chưa dùng được ({e}) - chuyển sang faster-whisper (CPU).", level="warn")
        return _faster_whisper(str(wav), duration, settings, resolve_model(model, device), lang, device, log,
                               progress, cancel, prompt)
    if engine in ("openai", "groq"):
        return _api_whisper(video, work_dir, duration, settings, engine, lang, log, progress, cancel, prompt)
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


def _faster_whisper(wav, duration, settings, model, lang, device, log, progress, cancel, prompt="") -> list[dict]:
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
            log("Không thấy GPU NVIDIA (CUDA) - chạy bằng CPU. Card AMD/Intel không dùng được cho Whisper.",
                level="warn")
    threads = os.cpu_count() or 4
    log(f"Nạp model Whisper '{model}' ({dev}{'' if dev == 'cuda' else f', {threads} luồng CPU'}). "
        "Lần đầu sẽ tải về vài trăm MB...")
    progress(0.1, f"Tải model Whisper {model}")
    try:
        wm = WhisperModel(model, device=dev, compute_type=ctype, cpu_threads=0 if dev == "cuda" else threads,
                          download_root=str(settings.models_dir() / "whisper"))
    except Exception as e:
        if dev == "cuda":
            log(f"GPU lỗi ({e}) - chuyển sang CPU.", level="warn")
            wm = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads,
                              download_root=str(settings.models_dir() / "whisper"))
        else:
            raise RuntimeError(f"Không tải được model Whisper '{model}' (lần đầu cần Internet tới huggingface.co). "
                               f"Có thể dùng engine Groq/OpenAI Whisper API thay thế.\nChi tiết: {e}") from e
    if prompt:
        log(f"Gợi ý cho Whisper: {prompt[:120]}")
    segments, info = wm.transcribe(wav, language=lang, vad_filter=True, beam_size=5,
                                   initial_prompt=prompt or None,
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


def _api_whisper(video, work_dir, duration, settings, engine, lang, log, progress, cancel, prompt="") -> list[dict]:
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
        if prompt:
            data["prompt"] = prompt[:800]
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
