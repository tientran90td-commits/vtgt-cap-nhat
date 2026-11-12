"""Khung dọc / vuông bám theo nhân vật: phim ngang 16:9 -> 9:16 mà không cắt mất người đang nói.

Với mỗi đoạn: lấy 2 khung/giây (ảnh nhỏ, xám), dò khuôn mặt bằng OpenCV (Haar, mặt thẳng + nghiêng).
Không thấy mặt -> bám vùng nhiều chi tiết + chuyển động nhất. Kết quả: vị trí giữa khung (0..1) đầu và cuối đoạn;
khung cắt lia nhẹ từ điểm đầu tới điểm cuối nên không bị giật. Không có OpenCV thì cắt giữa khung.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .media import Cancelled, frames

WIDTH = 320
_local = threading.local()


def available() -> bool:
    try:
        import cv2

        return hasattr(cv2, "CascadeClassifier")
    except ImportError:
        return False


def _detectors():
    if getattr(_local, "det", None) is None:
        import cv2

        base = Path(cv2.data.haarcascades)
        det = [cv2.CascadeClassifier(str(base / n)) for n in
               ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
        _local.det = [d for d in det if not d.empty()]
    return _local.det


def _faces(gray):
    import cv2

    h = gray.shape[0]
    g = cv2.equalizeHist(gray)
    ms = (max(14, h // 14),) * 2
    out = []
    for i, c in enumerate(_detectors()):
        out += [tuple(int(v) for v in f) for f in c.detectMultiScale(g, 1.15, 5, minSize=ms)]
        if i == 1:
            fl = c.detectMultiScale(cv2.flip(g, 1), 1.15, 5, minSize=ms)
            out += [(g.shape[1] - int(x) - int(w), int(y), int(w), int(hh)) for x, y, w, hh in fl]
    return out


def _subject(gray, prev):
    """Cột có nhiều chi tiết + chuyển động nhất (0..1)."""
    import cv2
    import numpy as np

    e = cv2.Canny(gray, 60, 140).astype(np.float32)
    if prev is not None:
        e += 2.0 * cv2.absdiff(gray, prev).astype(np.float32)
    col = e.sum(0)
    if col.sum() <= 0:
        return None
    k = max(3, gray.shape[1] // 8)
    col = np.convolve(col, np.ones(k) / k, mode="same")
    return float(np.argmax(col)) / gray.shape[1]


def centers(gray_frames) -> list[float]:
    out, prev = [], None
    for g in gray_frames:
        fs = _faces(g)
        if fs:
            x, _y, w, _h = max(fs, key=lambda f: f[2] * f[3])
            out.append((x + w / 2) / g.shape[1])
        else:
            s = _subject(g, prev)
            out.append(0.5 if s is None else 0.5 + (s - 0.5) * 0.6)  # không có mặt: kéo dần về giữa
        prev = g
    return out


def _median(v):
    v = sorted(v)
    return v[len(v) // 2] if v else 0.5


def track(video: str, info, spans: list[tuple[float, float]], work: Path, cancel=None, log=None,
          progress=None) -> list[tuple[float, float]]:
    """[(giữa khung lúc đầu, lúc cuối)] cho từng đoạn (start, dur). Có lưu lại để làm lại nhanh."""
    if not available() or not info.width:
        return [(0.5, 0.5)] * len(spans)
    cache_f = Path(work) / "faces.json"
    try:
        cache = json.loads(cache_f.read_text(encoding="utf-8")) if cache_f.exists() else {}
    except ValueError:
        cache = {}
    H = max(2, int(round(WIDTH * info.height / info.width / 2)) * 2)
    done = [0]

    def one(span):
        key = f"{video}|{span[0]:.2f}|{span[1]:.2f}"
        if key in cache:
            return tuple(cache[key])
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        fr = frames(video, span[0], span[1], WIDTH, H, fps=2, cancel=cancel)
        c = centers(fr)
        if not c:
            res = (0.5, 0.5)
        else:
            half = max(1, len(c) // 2)
            a, b = _median(c[:half]), _median(c[half:] or c[:half])
            res = (round(a, 3), round(b if abs(b - a) > 0.12 else a, 3))
        cache[key] = list(res)
        done[0] += 1
        if progress:
            progress(done[0] / max(1, len(spans)), f"Bám nhân vật {done[0]}/{len(spans)}")
        return res
    with ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(one, spans))
    cache_f.write_text(json.dumps(cache), encoding="utf-8")
    if log:
        log(f"Bám nhân vật: xong {len(spans)} đoạn.")
    return res
