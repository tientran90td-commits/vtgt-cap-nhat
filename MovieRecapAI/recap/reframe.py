"""Cắt khung thông minh (vd phim ngang 16:9 -> video dọc 9:16): khung cắt BÁM THEO KHUÔN MẶT / nhân vật.

- Lấy mẫu 2 khung/giây ở độ phân giải thấp, dò khuôn mặt (OpenCV Haar: mặt chính diện + nghiêng).
- Không có mặt: bám vùng nhiều chi tiết/chuyển động nhất (thường là nhân vật), kéo dần về giữa.
- Làm mượt (trung vị + lọc mũ), giới hạn tốc độ lia để không giật, rồi tạo biểu thức crop theo thời gian cho ffmpeg.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .ffmpeg_utils import _no_window_kwargs, ffmpeg_exe

SAMPLE_FPS = 2.0
WIDTH = 320
MAX_SPEED = 0.18   # tỉ lệ chiều rộng khung gốc tối đa được lia mỗi giây
MAX_KEYS = 40

_cascades = None


def _detectors():
    global _cascades
    if _cascades is None:
        import cv2

        if not hasattr(cv2, "CascadeClassifier"):  # OpenCV 5 bỏ Haar -> chỉ bám vùng chi tiết/chuyển động
            _cascades = []
            return _cascades
        base = Path(cv2.data.haarcascades)
        _cascades = [cv2.CascadeClassifier(str(base / n)) for n in
                     ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml")]
        _cascades = [c for c in _cascades if not c.empty()]
    return _cascades


def faces(gray) -> list[tuple[int, int, int, int]]:
    """Khuôn mặt (x, y, w, h) trong ảnh xám; bỏ mặt quá nhỏ (người đứng xa / nhiễu)."""
    import cv2

    h = gray.shape[0]
    out = []
    g = cv2.equalizeHist(gray)
    for i, c in enumerate(_detectors()):
        found = c.detectMultiScale(g, scaleFactor=1.15, minNeighbors=5, minSize=(max(14, h // 14),) * 2)
        out += [tuple(int(v) for v in f) for f in found]
        if i == 1:  # mặt nghiêng quay sang phải: lật ảnh để dò
            fl = c.detectMultiScale(cv2.flip(g, 1), scaleFactor=1.15, minNeighbors=5, minSize=(max(14, h // 14),) * 2)
            out += [(g.shape[1] - int(x) - int(w), int(y), int(w), int(hh)) for x, y, w, hh in fl]
    return out


def _subject_x(gray, prev_gray) -> float | None:
    """Vùng có nhiều chi tiết + chuyển động nhất (tỉ lệ 0..1 theo chiều ngang)."""
    import cv2
    import numpy as np

    edges = cv2.Canny(gray, 60, 140).astype(np.float32)
    w = edges.sum(axis=0)
    if prev_gray is not None:
        w = w + 3.0 * np.abs(gray.astype(np.float32) - prev_gray.astype(np.float32)).sum(axis=0) / 40.0
    if w.sum() <= 1e-6:
        return None
    w = np.convolve(w, np.ones(15) / 15, mode="same")
    return float(np.argmax(w) / max(1, len(w) - 1))


def track(video: str, start: float, dur: float, src_w: int, src_h: int, cache_dir: Path | None = None,
          detector=None) -> list[tuple[float, float]]:
    """[(t, cx)] tâm khung theo chiều ngang (0..1) trong đoạn [start, start+dur] (t tính từ 0)."""
    key = hashlib.sha1(repr((video, round(start, 2), round(dur, 2), src_w, src_h, detector is None)).encode()).hexdigest()[:14]
    cf = Path(cache_dir) / f"rf_{key}.json" if cache_dir else None
    if cf and cf.exists():
        try:
            return [tuple(x) for x in json.loads(cf.read_text())]
        except (ValueError, OSError):
            pass
    import numpy as np
    import importlib.util

    if importlib.util.find_spec("cv2") is None:
        return [(0.0, 0.5)]
    w = WIDTH
    h = max(2, int(round(src_h * w / max(1, src_w) / 2)) * 2)
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}",
           "-t", f"{max(0.5, dur):.3f}", "-i", str(video), "-an", "-sn",
           "-vf", f"fps={SAMPLE_FPS},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.run(cmd, capture_output=True, **_no_window_kwargs())
    raw = proc.stdout
    n = len(raw) // (w * h)
    det = detector or faces
    pts: list[tuple[float, float, float]] = []  # (t, cx, độ tin cậy)
    prev = None
    for i in range(n):
        g = np.frombuffer(raw[i * w * h:(i + 1) * w * h], np.uint8).reshape(h, w)
        t = i / SAMPLE_FPS
        fs = det(g)
        if len(fs):
            # mặt to nhất là nhân vật chính; nhiều mặt cỡ ngang nhau -> lấy tâm của nhóm
            fs = sorted(fs, key=lambda f: -f[2] * f[3])
            big = [f for f in fs if f[2] * f[3] >= 0.45 * fs[0][2] * fs[0][3]]
            cx = sum((f[0] + f[2] / 2) * f[2] * f[3] for f in big) / sum(f[2] * f[3] for f in big) / w
            pts.append((t, cx, 1.0))
        else:
            sx = _subject_x(g, prev)
            if sx is not None:
                pts.append((t, 0.5 + (sx - 0.5) * 0.6, 0.3))
        prev = g
    keys = smooth(pts, dur)
    if cf:
        try:
            cf.parent.mkdir(parents=True, exist_ok=True)
            cf.write_text(json.dumps(keys))
        except OSError:
            pass
    return keys


def smooth(pts: list[tuple[float, float, float]], dur: float) -> list[tuple[float, float]]:
    if not pts:
        return [(0.0, 0.5)]
    import numpy as np

    n = max(2, int(dur * SAMPLE_FPS) + 1)
    ts = np.arange(n) / SAMPLE_FPS
    xs = np.full(n, np.nan)
    ws = np.zeros(n)
    for t, x, c in pts:
        i = min(n - 1, int(round(t * SAMPLE_FPS)))
        xs[i], ws[i] = x, c
    # điền chỗ trống bằng giá trị gần nhất
    good = ~np.isnan(xs)
    xs = np.interp(ts, ts[good], xs[good]) if good.any() else np.full(n, 0.5)
    # trung vị trượt (bỏ phát hiện nhầm lẻ tẻ) rồi trung bình có trọng số độ tin cậy
    med = np.array([np.median(xs[max(0, i - 2):i + 3]) for i in range(n)])
    wsm = np.clip(ws, 0.15, 1.0)
    k = 3
    sm = np.array([np.average(med[max(0, i - k):i + k + 1], weights=wsm[max(0, i - k):i + k + 1]) for i in range(n)])
    # giới hạn tốc độ lia
    step = MAX_SPEED / SAMPLE_FPS
    for i in range(1, n):
        sm[i] = sm[i - 1] + max(-step, min(step, sm[i] - sm[i - 1]))
    keys = [(round(float(t), 3), round(float(min(1.0, max(0.0, x))), 4)) for t, x in zip(ts, sm)]
    if len(keys) > MAX_KEYS:
        idx = np.linspace(0, len(keys) - 1, MAX_KEYS).round().astype(int)
        keys = [keys[i] for i in sorted(set(idx))]
    # bỏ khóa thừa khi gần như đứng yên
    out = [keys[0]]
    for kf in keys[1:]:
        if abs(kf[1] - out[-1][1]) > 0.004:
            out.append(kf)
    if out[-1][0] != keys[-1][0]:
        out.append(keys[-1])
    return out


def expr(keys: list[tuple[float, float]]) -> str:
    """Biểu thức tâm khung theo t (ffmpeg), nội suy tuyến tính giữa các khóa."""
    if len(keys) == 1 or all(abs(k[1] - keys[0][1]) < 0.004 for k in keys):
        return f"{keys[0][1]:.4f}"
    e = f"{keys[-1][1]:.4f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(keys, keys[1:]))):
        slope = (x1 - x0) / max(1e-3, t1 - t0)
        e = f"if(lt(t\\,{t1:.3f})\\,{x0:.4f}+{slope:.5f}*(t-{t0:.3f})\\,{e})"
    return f"if(lt(t\\,{keys[0][0]:.3f})\\,{keys[0][1]:.4f}\\,{e})"


def crop_filter(keys: list[tuple[float, float]], W: int, H: int) -> str:
    """crop theo tỉ lệ khung đích, tâm ngang bám theo keys; đặt TRƯỚC bước scale."""
    cx = expr(keys)
    ar = W / H
    # (dấu phẩy trong biểu thức được thoát bằng \\, để không bị hiểu là ngăn cách bộ lọc)
    return (f"crop=w=min(iw\\,ih*{ar:.5f}):h=min(ih\\,iw/{ar:.5f}):"
            f"x=max(0\\,min(iw-ow\\,({cx})*iw-ow/2)):y=(ih-oh)/2,")


def concat_keys(per_piece: list[tuple[list[tuple[float, float]], float]], speed: float = 1.0) -> list[tuple[float, float]]:
    """Ghép khóa của nhiều cảnh nối tiếp nhau (đổi cảnh -> nhảy khung ngay, không lia)."""
    out: list[tuple[float, float]] = []
    off = 0.0
    for keys, d in per_piece:
        for t, x in keys:
            if t <= d + 1e-3:
                tt = (off + t) / speed
                if out and tt <= out[-1][0]:
                    tt = out[-1][0] + 0.001
                out.append((round(tt, 3), x))
        off += d
    return out or [(0.0, 0.5)]
