"""🚀 Turbo: dùng thiết lập MẠNH NHẤT của máy để làm video NHANH NHẤT.

Dò phần cứng rồi chọn: nhận dạng thoại nhanh nhất có thể (phụ đề có sẵn > Groq API > GPU NVIDIA > card AMD/Intel
qua whisper.cpp Vulkan > CPU), bộ mã hóa video bằng GPU, dựng nhiều đoạn song song, đọc giọng nhiều luồng, quét
quảng cáo nhanh, và bỏ các bước phụ tốn thời gian (dò chuyển cảnh, AI xem cảnh, nhiều phương án kịch bản,
AI soát phát âm, xóa phụ đề bằng AI, kiểm tra video cuối). Thiết lập cũ được cất lại để khôi phục bằng 1 nút.
"""
from __future__ import annotations

import os
import sys

from .config import Settings


def _has_subtitle(project) -> bool:
    if project is None:
        return False
    from pathlib import Path

    v = Path(project.video)
    if any(v.with_suffix(ext).exists() for ext in (".srt", ".vtt", ".ass")):
        return True
    return any(s.get("codec") in ("subrip", "ass", "ssa", "mov_text", "webvtt")
               for s in (project.info.subtitle_streams or []))


def plan(settings: Settings, project=None) -> list[tuple[str, str, object, str]]:
    """Danh sách thay đổi (mục, khóa, giá trị, giải thích) cho chế độ Turbo trên máy này."""
    from .transcribe import has_cuda

    threads = os.cpu_count() or 4
    cuda = has_cuda()
    ch: list[tuple[str, str, object, str]] = []
    # 1) Nhận dạng thoại - bước lâu nhất
    if settings.get("transcribe", "engine") in ("subtitle", "embedded") and _has_subtitle(project):
        pass  # đã dùng phụ đề có sẵn - nhanh nhất rồi
    elif (settings.get("api", "groq_key") or "").strip():
        ch.append(("transcribe", "engine", "groq", "Nhận dạng thoại: Groq Whisper API (phim 2 tiếng ~1-3 phút)"))
    elif cuda:
        ch.append(("transcribe", "engine", "faster_whisper", "Nhận dạng thoại: Whisper trên GPU NVIDIA"))
        ch.append(("transcribe", "device", "auto", ""))
    elif sys.platform.startswith("win"):
        ch.append(("transcribe", "engine", "whisper_gpu",
                   "Nhận dạng thoại: Whisper bằng card đồ họa AMD/Intel (whisper.cpp Vulkan)"))
    else:
        ch.append(("transcribe", "engine", "faster_whisper", f"Nhận dạng thoại: Whisper CPU {threads} luồng"))
    ch.append(("transcribe", "model", "large-v3-turbo", "Model large-v3-turbo (chính xác cao, nhanh nhất họ large)"))
    ch.append(("transcribe", "use_scenes", False, "Bỏ dò chuyển cảnh (khớp hình theo câu vẫn hoạt động)"))
    # 2) AI viết kịch bản
    ch.append(("script", "candidates", 1, "Kịch bản: 1 phương án (không viết nhiều bản rồi chấm)"))
    ch.append(("script", "visual", False, "Bỏ AI xem hình ảnh từng cảnh"))
    # 3) Giọng đọc
    ch.append(("voice", "ai_pron", False, "Bỏ AI soát phát âm (vẫn đọc đúng số, ngày tháng, từ điển)"))
    ch.append(("voice", "parallel", 4, "Giọng online đọc 4 đoạn cùng lúc"))
    # 4) Dựng video
    ch.append(("render", "encoder", "auto", "Mã hóa video bằng GPU (AMD AMF / NVIDIA NVENC / Intel QSV nếu có)"))
    par = 3 if threads >= 12 else 2 if threads >= 4 else 1
    ch.append(("render", "parallel", par, f"Dựng {par} đoạn video song song (CPU {threads} luồng)"))
    ch.append(("render", "fast_scan", True, "Quét quảng cáo/logo/phụ đề cứng nhanh (chỉ đọc khung chính)"))
    if settings.get("render", "hardsub_mode") == "vsr":
        ch.append(("render", "hardsub_mode", "blur", "Phụ đề in cứng: làm mờ thay vì xóa bằng AI (VSR rất chậm)"))
    ch.append(("render", "final_qa", False, "Bỏ bước kiểm tra lại video sau khi xuất"))
    # bỏ các thay đổi không làm khác đi gì
    out, seen = [], set()
    for sec, key, val, why in ch:
        if (sec, key) in seen:
            continue
        seen.add((sec, key))
        if settings.get(sec, key) != val:
            out.append((sec, key, val, why))
    return out


def apply(settings: Settings, changes) -> int:
    """Áp dụng Turbo; cất giá trị cũ để khôi phục."""
    backup = dict(settings.get("ui", "turbo_backup") or {})
    for sec, key, val, _why in changes:
        k = f"{sec}.{key}"
        if k not in backup:
            backup[k] = settings.get(sec, key)
        settings.set(sec, key, val)
    settings.set("ui", "turbo_backup", backup)
    settings.set("ui", "turbo", True)
    settings.save()
    return len(changes)


def restore(settings: Settings) -> int:
    backup = settings.get("ui", "turbo_backup") or {}
    for k, v in backup.items():
        sec, key = k.split(".", 1)
        settings.set(sec, key, v)
    settings.set("ui", "turbo_backup", {})
    settings.set("ui", "turbo", False)
    settings.save()
    return len(backup)


def is_on(settings: Settings) -> bool:
    return bool(settings.get("ui", "turbo"))
