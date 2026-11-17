"""Kiểm tra chất lượng video thành phẩm: màn hình đen, cảnh đứng hình lâu (dễ bị coi là 'slideshow'),
độ to âm thanh, độ dài so với mục tiêu."""
from __future__ import annotations

import re
import subprocess

from .ffmpeg_utils import _no_window_kwargs, ffmpeg_exe, probe


def check_output(path: str, target_seconds: float | None = None) -> dict:
    info = probe(path)
    dur = info.duration or 1.0
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(path),
           "-vf", "scale=320:-2,blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-55dB:d=2.5",
           "-af", "ebur128=peak=true", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         **_no_window_kwargs()).stderr
    black = sum(float(x) for x in re.findall(r"black_duration:\s*([\d.]+)", out))
    freeze = sum(float(x) for x in re.findall(r"freeze_duration:\s*([\d.]+)", out))
    m = re.findall(r"I:\s*(-?[\d.]+)\s*LUFS", out)
    lufs = float(m[-1]) if m else None
    warnings = []
    if black / dur > 0.03:
        warnings.append(f"Màn hình đen {black:.1f}s ({black / dur:.0%}) - nên đổi cảnh ở những chỗ đó.")
    if freeze / dur > 0.10:
        warnings.append(f"Hình đứng yên {freeze:.1f}s ({freeze / dur:.0%}) - video dễ bị coi là trình chiếu ảnh.")
    if lufs is not None and (lufs < -24 or lufs > -9):
        warnings.append(f"Âm lượng tổng {lufs:.1f} LUFS chưa chuẩn (nên khoảng -16 LUFS).")
    if target_seconds and abs(dur - target_seconds) > max(30.0, target_seconds * 0.35):
        warnings.append(f"Độ dài {dur / 60:.1f} phút lệch xa mục tiêu {target_seconds / 60:.1f} phút.")
    return {"duration": round(dur, 1), "black_s": round(black, 1), "freeze_s": round(freeze, 1),
            "loudness_lufs": lufs, "warnings": warnings, "ok": not warnings}
