"""Chọn đoạn phim cho từng câu/đoạn thuyết minh.

- Không lặp lại cảnh đã chiếu (theo dõi các khoảng đã dùng).
- Tránh các khoảng bị chặn: quảng cáo chèn cứng, OP/ED anime, đoạn người dùng muốn bỏ.
- Chia file giọng đọc của 1 đoạn thành từng câu, bám vào khoảng lặng thật giữa các câu.
"""
from __future__ import annotations

import re
import subprocess

from .ffmpeg_utils import _no_window_kwargs, ffmpeg_exe


def merge_ranges(ranges, gap: float = 0.0) -> list[list[float]]:
    out: list[list[float]] = []
    for s, e in sorted([float(r[0]), float(r[1])] for r in ranges if float(r[1]) > float(r[0])):
        if out and s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def _overlap(a0, a1, ranges) -> float:
    return sum(max(0.0, min(a1, e) - max(a0, s)) for s, e in ranges)


class Footage:
    def __init__(self, duration: float, blocked=None, no_reuse: bool = True):
        self.duration = float(duration)
        self.blocked = merge_ranges(blocked or [])
        self.used: list[list[float]] = []
        self.no_reuse = no_reuse
        self.stats = {"pieces": 0, "reused_s": 0.0, "blocked_s": 0.0, "moved": 0}

    def place(self, want: float, length: float, window_end: float | None = None) -> float:
        """Trả về điểm bắt đầu cho đoạn dài `length`, càng gần `want` càng tốt, không trùng cảnh đã dùng
        & không rơi vào khoảng bị chặn. Tìm trong cửa sổ [want - 2s, max(window_end, want+length) + slack]."""
        length = max(0.1, min(length, self.duration))
        want = max(0.0, min(float(want), self.duration - length))
        lo = max(0.0, want - max(8.0, length))
        avoid = merge_ranges(self.blocked + (self.used if self.no_reuse else []))
        hi_end = max(window_end or 0.0, want + length) + max(20.0, length * 2)
        # khoảng bị chặn dài (vd quảng cáo 20s) -> nới cửa sổ tìm để nhảy qua được
        hi_end += sum(e - s for s, e in avoid if e > lo and s < hi_end)
        cands = [want] + [e for s, e in avoid if e >= lo] + [s - length for s, e in avoid if s - length >= lo] + [lo]
        best, best_cost = None, None
        for c in sorted(set(round(x, 3) for x in cands)):
            if c < lo or c + length > min(hi_end, self.duration):
                continue
            ov = _overlap(c, c + length, avoid)
            # ưu tiên tiến về sau (đúng mạch phim) hơn là lùi lại trước
            cost = ov * 100 + ((want - c) * 2.0 if c < want else (c - want))
            if best_cost is None or cost < best_cost:
                best, best_cost = c, cost
            if ov == 0 and c >= want:
                break
        if best is None:  # không có chỗ trống -> chấp nhận lặp, nhưng vẫn tránh quảng cáo/OP/ED nếu được
            best = want
            for c in [want] + [e for s, e in self.blocked if e >= want]:
                if c + length <= self.duration and _overlap(c, c + length, self.blocked) == 0:
                    best = c
                    break
        best = max(0.0, min(best, self.duration - length))
        self.stats["pieces"] += 1
        self.stats["reused_s"] += _overlap(best, best + length, self.used)
        self.stats["blocked_s"] += _overlap(best, best + length, self.blocked)
        if abs(best - want) > 0.5:
            self.stats["moved"] += 1
        self.used = merge_ranges(self.used + [[best, best + length]])
        return best


# ------------------------------------------------------------------ chia giọng đọc theo câu
def silences(wav: str, noise_db: float = -35.0, min_d: float = 0.12) -> list[tuple[float, float]]:
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(wav), "-af",
                          f"silencedetect=n={noise_db}dB:d={min_d}", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", **_no_window_kwargs())
    res, start = [], None
    for line in out.stderr.splitlines():
        m = re.search(r"silence_start:\s*([\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and start is not None:
            res.append((start, float(m.group(1))))
            start = None
    return res


def sentence_durations(wav: str, texts: list[str], total: float, lead: float = 0.0) -> list[float]:
    """Độ dài (giây) của từng câu trong file giọng đọc: lấy mốc theo tỉ lệ số ký tự rồi kéo về khoảng lặng
    thật gần nhất (ranh giới tự nhiên giữa 2 câu)."""
    n = len(texts)
    if n <= 1 or total <= 0:
        return [total]
    weights = [max(3, len(t)) for t in texts]
    tot_w = float(sum(weights))
    targets, acc = [], 0.0
    for w in weights[:-1]:
        acc += w
        targets.append(total * acc / tot_w)
    try:
        sil = [((a + b) / 2) for a, b in silences(wav) if a > 0.05 and b < total - 0.05]
    except Exception:  # noqa: BLE001
        sil = []
    avg = total / n
    bounds, prev = [], 0.0
    for t in targets:
        near = [c for c in sil if c > prev + 0.25 and abs(c - t) <= max(0.6, avg * 0.35)]
        b = min(near, key=lambda c: abs(c - t)) if near else t
        b = max(prev + 0.25, min(b, total - 0.25 * (n - len(bounds) - 1)))
        bounds.append(b)
        prev = b
    edges = [0.0] + bounds + [total]
    return [max(0.2, edges[k + 1] - edges[k]) for k in range(n)]


def norm_text(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def valid_sentences(seg: dict) -> list[dict] | None:
    """Danh sách câu (có mốc phim riêng) còn khớp với lời thuyết minh; người dùng sửa lời thì bỏ."""
    sents = seg.get("sentences") or []
    if len(sents) < 2 or not (seg.get("narration") or "").strip():
        return None
    if norm_text(" ".join(x.get("text", "") for x in sents)) != norm_text(seg["narration"]):
        return None
    return sents
