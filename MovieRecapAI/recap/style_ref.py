"""Học phong cách từ 1 video recap mẫu (vd 1 video review đang viral mà bạn thích).

Đo: tốc độ đọc (từ/giây), số từ mỗi câu, độ dài trung bình mỗi cảnh (nhịp cắt), độ dài video; lấy 1 đoạn lời
mẫu để AI bắt chước giọng văn/cách mở đầu (không chép nội dung).
"""
from __future__ import annotations

import re
import tempfile
import threading
from pathlib import Path

from .config import Settings
from .ffmpeg_utils import probe


def analyze(video: str, settings: Settings, log, progress, cancel=None) -> dict:
    from .scenes import detect_scenes
    from .transcribe import transcribe

    cancel = cancel or threading.Event()
    info = probe(video)
    t = settings.section("transcribe")
    engine = t.get("engine", "faster_whisper")
    if engine in ("subtitle", "embedded"):
        engine = "faster_whisper"
    work = Path(tempfile.mkdtemp(prefix="style_ref_"))
    log(f"Phân tích video mẫu: {Path(video).name} ({info.duration:.0f}s)")
    segs = transcribe(video, work, settings, engine, log, lambda p, m="": progress(p * 0.7, m), cancel,
                      model=t.get("model", "auto"), language=t.get("language", "auto"), device=t.get("device", "auto"))
    try:
        cuts = detect_scenes(video, log, lambda p, m="": progress(0.7 + p * 0.3, m), cancel)
    except Exception:  # noqa: BLE001
        cuts = []
    text = " ".join(s["text"] for s in segs)
    words = len(text.split())
    speech = sum(max(0.0, s["end"] - s["start"]) for s in segs) or 1.0
    sentences = [x for x in re.split(r"(?<=[.!?…])\s+", text) if x.strip()] or [text]
    ref = {
        "name": Path(video).name,
        "duration": round(info.duration, 1),
        "wps": round(words / speech, 2),
        "words_per_sentence": round(words / max(1, len(sentences)), 1),
        "avg_cut": round(info.duration / max(1, len(cuts)), 1),
        "cuts_per_min": round(len(cuts) / max(1.0, info.duration / 60), 1),
        "sample": text[:1800],
        "target_minutes": round(info.duration / 60, 1),
    }
    progress(1.0, "Đã phân tích video mẫu")
    log(f"🎯 Phong cách mẫu: {ref['wps']} từ/giây · {ref['words_per_sentence']} từ/câu · "
        f"cảnh trung bình {ref['avg_cut']}s · dài {ref['target_minutes']} phút")
    return ref
