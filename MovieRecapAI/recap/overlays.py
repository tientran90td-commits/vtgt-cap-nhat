"""Phát hiện chữ/quảng cáo chèn cứng (của web phim) và logo cố định.

Ý tưởng: lớp chèn cứng (quảng cáo, banner, logo web) đứng yên từng điểm ảnh trong khi hình phim bên dưới
thay đổi. Lấy 3 khung hình cách nhau vài giây mà nội dung phim đã đổi khác: những điểm "cạnh" (edge) trùng
nhau và cùng màu ở cả 3 khung chính là lớp chèn. Phụ đề cứng đổi mỗi vài giây nên không bị bắt nhầm.

- Lớp chèn xuất hiện có thời hạn (quảng cáo) -> trả về các khoảng thời gian để tránh khi chọn cảnh.
- Lớp chèn có mặt gần như suốt phim (logo/watermark) -> trả về vùng để che mờ khi dựng.
"""
from __future__ import annotations

import subprocess

from .ffmpeg_utils import Cancelled, _no_window_kwargs, ffmpeg_exe

SAMPLE_EVERY = 2.0       # giây giữa 2 khung lấy mẫu
WIDTH = 320              # phân tích ở độ phân giải thấp cho nhanh
STEP = 2                 # khung i, i+2, i+4 -> cách nhau 8 giây
MIN_CHANGE = 12.0        # nội dung phim phải đổi đủ nhiều
COLOR_TOL = 18
MIN_STATIC_RATIO = 0.002  # tỉ lệ điểm ảnh "đứng yên có cạnh" để coi là có lớp chèn
PERSISTENT_SHARE = 0.4    # điểm đứng yên ở >= 40% bộ khung -> logo cố định


def detect(video: str, duration: float, width: int, height: int, log, progress, cancel) -> dict:
    import numpy as np

    try:
        import cv2
    except ImportError:
        log("Thiếu OpenCV - bỏ qua bước lọc quảng cáo chèn.", level="warn")
        return {"ranges": [], "watermark": None}
    if not width or not height or duration < 30:
        return {"ranges": [], "watermark": None}
    w = WIDTH
    h = max(2, int(round(height * w / width / 2)) * 2)
    fsize = w * h * 3
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-i", video, "-an", "-sn",
           "-vf", f"fps=1/{SAMPLE_EVERY},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **_no_window_kwargs())
    frames = []  # (t, rgb int16, gray, edges)
    triplets = []  # (t0, t2, packed static mask)
    counts = np.zeros((h, w), np.int32)
    n_total = max(1, int(duration / SAMPLE_EVERY))
    idx = 0
    try:
        while True:
            if cancel.is_set():
                proc.kill()
                raise Cancelled()
            buf = proc.stdout.read(fsize)
            if not buf or len(buf) < fsize:
                break
            rgb = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 80, 160) > 0
            frames.append((idx * SAMPLE_EVERY, rgb.astype(np.int16), gray.astype(np.int16), edges))
            if len(frames) > 2 * STEP + 1:
                frames.pop(0)
            if len(frames) == 2 * STEP + 1:
                a, b, c = frames[0], frames[STEP], frames[2 * STEP]
                if (np.abs(a[2] - c[2]).mean() >= MIN_CHANGE and np.abs(a[2] - b[2]).mean() >= MIN_CHANGE * 0.6
                        and np.abs(b[2] - c[2]).mean() >= MIN_CHANGE * 0.6):
                    same = (np.abs(a[1] - b[1]).max(axis=2) < COLOR_TOL) & (np.abs(a[1] - c[1]).max(axis=2) < COLOR_TOL)
                    static = a[3] & b[3] & c[3] & same
                    counts += static
                    triplets.append((a[0], c[0], np.packbits(static)))
            idx += 1
            if idx % 25 == 0:
                progress(min(0.99, idx / n_total), f"Lọc quảng cáo chèn {int(idx * SAMPLE_EVERY)}/{int(duration)}s")
    finally:
        try:
            proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        proc.wait()
    if not triplets:
        progress(1.0, "Xong lọc quảng cáo")
        return {"ranges": [], "watermark": None}
    persistent = counts >= max(3, PERSISTENT_SHARE * len(triplets))
    watermark = None
    if persistent.sum() >= 30:
        ys, xs = np.where(persistent)
        # khung bao vùng logo (bỏ điểm lẻ: lấy phân vị 2-98)
        x0, x1 = np.percentile(xs, [2, 98])
        y0, y1 = np.percentile(ys, [2, 98])
        pad = 4
        box = [max(0, x0 - pad) / w, max(0, y0 - pad) / h, min(w, x1 + pad) / w, min(h, y1 + pad) / h]
        if (box[2] - box[0]) * (box[3] - box[1]) < 0.15:  # logo nhỏ ở góc - che được; quá to thì chỉ báo
            watermark = {"box": [float(round(float(v), 4)) for v in box], "pixels": int(persistent.sum())}
    keep = ~persistent
    ranges = []
    for t0, t2, packed in triplets:
        static = np.unpackbits(packed)[: h * w].reshape(h, w).astype(bool) & keep
        if static.mean() >= MIN_STATIC_RATIO:
            ranges.append([max(0.0, t0 - 1.0), min(duration, t2 + 1.0)])
    from .footage import merge_ranges

    ranges = merge_ranges(ranges, gap=2.0)
    if len(triplets) and sum(e - s for s, e in ranges) > 0.6 * duration:
        log("Lớp chèn xuất hiện gần như suốt phim - không chặn cảnh (chỉ che logo nếu có).", level="warn")
        ranges = []
    progress(1.0, "Xong lọc quảng cáo")
    total = sum(e - s for s, e in ranges)
    log(f"Lọc quảng cáo chèn: {len(ranges)} đoạn (~{total:.0f}s) sẽ được tránh"
        + (" · phát hiện logo/watermark cố định -> sẽ che mờ" if watermark else ""))
    return {"ranges": [[round(s, 2), round(e, 2)] for s, e in ranges], "watermark": watermark}
