"""Tự dò phụ đề cứng (Vietsub in sẵn trong hình) để che đúng chỗ.

Lấy ~36 khung hình rải đều cả phim, tìm các hàng điểm ảnh có "dáng chữ phụ đề": nhiều chỗ chuyển gắt giữa
điểm rất sáng (chữ trắng/vàng) và điểm rất tối (viền đen), lặp lại ở cùng một vị trí trong nhiều khung hình.
Trả về dải (trên, dưới) tính theo tỉ lệ chiều cao khung hình, hoặc None nếu phim không có phụ đề cứng.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .media import MediaInfo, frames

W = 320


def _row_scores(f):
    import numpy as np

    f = f.astype(np.int16)
    bright, dark = f > 185, f < 70
    trans = (bright[:, 1:] & dark[:, :-1]) | (dark[:, 1:] & bright[:, :-1])
    # chuyển sáng<->tối cách 1 điểm (viền chữ mảnh khi đã thu nhỏ)
    trans2 = (bright[:, 2:] & dark[:, :-2]) | (dark[:, 2:] & bright[:, :-2])
    return (trans.sum(1) + trans2.sum(1)) / f.shape[1]


def _band(freq, H: int):
    """Dải liên tục dài nhất có tần suất 'giống chữ' cao."""
    import numpy as np

    base = float(np.median(freq))
    thr = max(0.22, base + 0.18)
    hot = freq >= thr
    best, cur = None, None
    gap = 0
    for y in range(H):
        if hot[y]:
            if cur is None:
                cur = [y, y]
            else:
                cur[1] = y
            gap = 0
        elif cur is not None:
            gap += 1
            if gap > 3:
                if best is None or (cur[1] - cur[0]) * freq[cur[0]:cur[1] + 1].mean() > \
                        (best[1] - best[0]) * freq[best[0]:best[1] + 1].mean():
                    best = cur
                cur, gap = None, 0
    if cur is not None and (best is None or (cur[1] - cur[0]) * freq[cur[0]:cur[1] + 1].mean() >
                            (best[1] - best[0]) * freq[best[0]:best[1] + 1].mean()):
        best = cur
    return best


def detect(video: str, info: MediaInfo, work: Path, cancel=None, log=None, samples: int = 36):
    cache = Path(work) / "hardsub.json"
    st = os.stat(video)
    sig = [str(video), st.st_size, int(st.st_mtime)]
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("sig") == sig:
                return tuple(d["band"]) if d.get("band") else None
        except (ValueError, KeyError):
            pass
    import numpy as np

    if not info.width or not info.height or info.duration < 2:
        return None
    H = max(2, int(round(W * info.height / info.width / 2)) * 2)
    dur = info.duration
    times = [dur * (0.04 + 0.92 * i / max(1, samples - 1)) for i in range(samples)]

    def grab(t):
        fr = frames(video, t, None, W, H, count=1, cancel=cancel)
        return fr[0] if fr else None
    with ThreadPoolExecutor(max_workers=4) as ex:
        imgs = [f for f in ex.map(grab, times) if f is not None]
    band = None
    if len(imgs) >= 6:
        texty = np.stack([_row_scores(f) > 0.035 for f in imgs])  # [khung, hàng]
        freq = texty.mean(0)
        # phụ đề chỉ ở dải dưới (55%..98%) hoặc dải trên (2%..22%) của khung hình
        allowed = np.zeros(H, bool)
        allowed[int(H * 0.55):int(H * 0.98)] = True
        allowed[int(H * 0.02):int(H * 0.22)] = True
        b = _band(np.where(allowed, freq, 0.0), H)
        if b is not None:
            y0, y1 = b[0] / H, (b[1] + 1) / H
            if 0.02 <= y1 - y0 <= 0.3:
                pad = 0.018
                band = (round(max(0.0, y0 - pad), 4), round(min(1.0, y1 + pad), 4))
    cache.write_text(json.dumps({"sig": sig, "band": band}), encoding="utf-8")
    if log:
        log(f"Phụ đề cứng: {'có, ở ' + format(band[0] * 100, '.0f') + '–' + format(band[1] * 100, '.0f') + '% chiều cao' if band else 'không thấy'}.")
    return band
