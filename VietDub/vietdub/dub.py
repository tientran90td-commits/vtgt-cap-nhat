"""Ghép giọng thuyết minh thành 1 track âm thanh khớp thời gian video.

- Mỗi câu đặt đúng lúc nhân vật bắt đầu nói.
- Câu đọc dài hơn khoảng trống tới câu sau -> tăng tốc nhẹ (tối đa `max_speed`, giữ cao độ bằng atempo);
  vẫn dài -> lùi câu sau một chút (không bao giờ đọc chồng lên nhau).
- Ghép bằng numpy (nhanh, không giới hạn số câu), ra WAV 48 kHz mono.
"""
from __future__ import annotations

import wave
from pathlib import Path

from .media import Cancelled, run

SR = 48000
GAP = 0.06


def _read(path: Path):
    import numpy as np

    with wave.open(str(path), "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw != 2 or sr != SR:
        raise ValueError(f"WAV lạ ({sr} Hz, {sw * 8} bit): {path.name}")
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a


def _speed(src: Path, factor: float, cancel) -> Path:
    out = src.with_name(f"{src.stem}_x{factor:.3f}.wav")
    if not out.exists():
        run(["-i", str(src), "-af", f"atempo={factor:.4f}", "-ac", "1", "-ar", str(SR), str(out)], cancel=cancel)
    return out


def build(lines: list[dict], files: list, total: float, out: Path, max_speed: float = 1.35, offset: float = 0.0,
          cancel=None, log=None) -> dict:
    """lines[i] (start, end) + files[i] (WAV hoặc None) -> out. offset: giây bắt đầu (khi dựng thử 1 đoạn)."""
    import numpy as np

    buf = np.zeros(int((total + 1.0) * SR), np.float32)
    cursor = 0.0
    sped, late, placed = 0, 0.0, 0
    order = sorted(range(len(lines)), key=lambda i: lines[i]["start"])
    for k, i in enumerate(order):
        f = files[i] if i < len(files) else None
        if not f:
            continue
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        ln = lines[i]
        nxt = next((lines[j]["start"] for j in order[k + 1:] if j < len(files) and files[j]), None)
        start = ln["start"] - offset
        slot_end = (nxt - offset) if nxt is not None else max(ln["end"] - offset + 1.5, start + 0.5)
        a = _read(Path(f))
        dur = len(a) / SR
        avail = max(0.3, slot_end - max(start, cursor) - GAP)
        if dur > avail * 1.02:
            factor = min(max_speed, dur / avail)
            if factor > 1.02:
                a = _read(_speed(Path(f), factor, cancel))
                dur = len(a) / SR
                sped += 1
        t = max(start, cursor)
        late = max(late, t - start)
        s0 = int(t * SR)
        if s0 >= len(buf):
            continue
        seg = a[: len(buf) - s0]
        buf[s0:s0 + len(seg)] += seg
        cursor = t + dur + GAP
        placed += 1
    peak = float(np.abs(buf).max()) if len(buf) else 0.0
    if peak > 0.99:
        buf *= 0.99 / peak
    pcm = (np.clip(buf[: int(total * SR)], -1, 1) * 32767).astype(np.int16)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    stats = {"placed": placed, "sped": sped, "max_late": round(late, 2)}
    if log:
        log(f"Ghép thuyết minh: {placed} câu" + (f", {sped} câu đọc nhanh hơn chút cho kịp" if sped else "")
            + (f", lệch tối đa {late:.1f}s" if late > 0.3 else "") + ".")
    return stats
