"""Dò điểm chuyển cảnh (bộ lọc scene của FFmpeg, chỉ đọc khung hình khóa nên rất nhanh) và khớp đầu đoạn vào đó.

Mỗi đoạn recap bắt đầu đúng lúc chuyển cảnh, nên không bị lọt nửa giây cuối của cảnh trước.
"""
from __future__ import annotations

import bisect
import json
import os
import re
from pathlib import Path

from .media import MediaError, run


def _sig(video: str) -> list:
    st = os.stat(video)
    return [str(video), st.st_size, int(st.st_mtime)]


def _cached(work: Path, sig: list) -> dict | None:
    f = Path(work) / "scenes.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("sig") == sig:
                return d
        except ValueError:
            pass
    return None


def detect(video: str, work: Path, cancel=None, log=None, full: bool = False) -> list[float]:
    """Mốc chuyển cảnh (giây), có lưu lại trong thư mục dự án.

    full=False: chỉ đọc khung hình khóa (vài giây cho cả bộ phim; phim thật hầu như luôn có khung khóa ở chỗ cắt cảnh).
    full=True : đọc mọi khung hình ở độ phân giải thấp (giải mã bằng GPU nếu có, ưu tiên thấp) - chính xác hơn."""
    sig = _sig(video)
    d = _cached(work, sig)
    if d and (d.get("full") or not full):
        return d["cuts"]
    sel = "scale=160:-2,select='gt(scene\\,{th})',showinfo"
    if full:
        base = ["-skip_frame", "noref", "-i", video, "-an", "-sn", "-dn", "-vf", sel.format(th=0.3),
                "-fps_mode", "passthrough", "-f", "null", "-"]
        try:
            txt = run(["-hwaccel", "auto", *base], cancel=cancel, low_priority=True)
        except MediaError:
            txt = run(base, cancel=cancel, low_priority=True)
    else:
        txt = run(["-skip_frame", "nokey", "-i", video, "-an", "-sn", "-dn", "-vf", sel.format(th=0.15),
                   "-fps_mode", "passthrough", "-f", "null", "-"], cancel=cancel)
    cuts = sorted({round(float(m.group(1)), 3) for m in re.finditer(r"pts_time:\s*([\d.]+)", txt)})
    (Path(work) / "scenes.json").write_text(json.dumps({"sig": sig, "cuts": cuts, "full": full}), encoding="utf-8")
    if log:
        log(f"Dò chuyển cảnh{' (chi tiết)' if full else ''}: {len(cuts)} điểm.")
    return cuts


def snap(t: float, cuts: list[float], window: float = 1.5) -> float:
    """Kéo mốc về điểm chuyển cảnh gần nhất (nếu cách không quá `window` giây)."""
    if not cuts:
        return t
    i = bisect.bisect_left(cuts, t)
    best, best_d = t, window + 1
    for j in (i - 1, i):
        if 0 <= j < len(cuts):
            d = abs(cuts[j] - t)
            if d < best_d:
                best, best_d = cuts[j], d
    return round(best + 0.04, 3) if best_d <= window else t


def snap_segments(segments: list[dict], cuts: list[float], window: float = 1.5) -> list[dict]:
    out = []
    for s in segments:
        st = snap(s["start"], cuts, window)
        out.append({**s, "start": st, "end": max(s["end"] + (st - s["start"]), st + 1.0)})
    return out
