"""Quét phụ đề cứng (chữ in sẵn trên hình) của video gốc -> lời gốc có mốc thời gian, bằng OCR mã nguồn mở
RapidOCR (model PaddleOCR PP-OCRv6 chạy trên onnxruntime).

Nhanh vì không đọc chữ mọi khung hình:
1. Đọc 4 khung/giây, chỉ phần trong khung phụ đề (ảnh nhỏ).
2. Dò "có chữ không" + "chữ có đổi không" bằng dấu vân tay nét chữ (chữ sáng viền tối) -> gom thành từng câu.
3. Mỗi câu chỉ OCR 1 khung đẹp nhất (nhiều chữ nhất) -> ghép câu trùng nhau liền kề.
"""
from __future__ import annotations

import difflib
import json
import os
import subprocess
from pathlib import Path

from .media import Cancelled, MediaInfo, ffmpeg_exe, no_window

# ngôn ngữ chữ trên hình -> loại model RapidOCR (None = model đa ngôn ngữ có sẵn: Trung, Anh, Nhật, Latin, Việt)
LANGS = {
    "auto": ("Tự nhận (Trung, Anh, Nhật, Indonesia, Tây Ban Nha...)", None),
    "zh": ("Tiếng Trung (giản thể)", None), "zh_tw": ("Tiếng Trung (phồn thể)", "CHINESE_CHT"),
    "en": ("Tiếng Anh", None), "ja": ("Tiếng Nhật", None), "ko": ("Tiếng Hàn", "KOREAN"),
    "th": ("Tiếng Thái", "TH"), "ru": ("Tiếng Nga", "CYRILLIC"), "hi": ("Tiếng Hindi", "DEVANAGARI"),
    "ar": ("Tiếng Ả Rập", "ARABIC"), "latin": ("Chữ Latin khác (Pháp, Đức, Indonesia...)", "LATIN"),
}
FPS = 4.0
MAX_W = 960
_ENGINES: dict = {}


class OCRError(RuntimeError):
    pass


def available() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("rapidocr") is not None
    except (ImportError, ValueError):
        return False


def engine(lang: str = "auto"):
    """RapidOCR theo ngôn ngữ (model ngôn ngữ chưa có thì tự tải lần đầu)."""
    if not available():
        raise OCRError("Chưa cài bộ đọc chữ (bấm 📦 Thư viện → Tải tất cả, hoặc chạy lại install.bat).")
    kind = LANGS.get(lang, LANGS["auto"])[1]
    if kind not in _ENGINES:
        from rapidocr import LangRec, RapidOCR

        params = {"Global.log_level": "error"}
        if kind:
            params["Rec.lang_type"] = getattr(LangRec, kind)
        try:
            import onnxruntime as ort

            if os.name == "nt" and "DmlExecutionProvider" in ort.get_available_providers():
                params["EngineConfig.onnxruntime.use_dml"] = True
        except ImportError:
            pass
        try:
            _ENGINES[kind] = RapidOCR(params=params)
        except Exception as e:  # noqa: BLE001
            if params.pop("EngineConfig.onnxruntime.use_dml", None):
                _ENGINES[kind] = RapidOCR(params=params)
            else:
                raise OCRError(f"Không nạp được model đọc chữ ({LANGS.get(lang, ('?',))[0]}): {e}") from e
    return _ENGINES[kind]


def read_image(img, lang: str = "auto", min_score: float = 0.6) -> str:
    """Đọc chữ trong 1 ảnh (numpy BGR/xám) -> 1 dòng (nhiều dòng chữ nối theo thứ tự trên -> dưới)."""
    import numpy as np

    if img.ndim == 2:
        img = np.repeat(img[:, :, None], 3, axis=2)
    r = engine(lang)(img)
    if not r or not r.txts:
        return ""
    items = []
    for box, txt, sc in zip(r.boxes, r.txts, r.scores):
        if sc >= min_score and txt.strip():
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            items.append((round(sum(ys) / len(ys) / 12), min(xs), txt.strip()))
    items.sort()
    items = [(a, b, _clean(t)) for a, b, t in items]
    items = [x for x in items if x[2]]
    cjk = any("぀" <= ch <= "鿿" or "가" <= ch <= "힯" for _, _, t in items for ch in t)
    return _clean(("" if cjk else " ").join(t for _, _, t in items))


def _clean(t: str) -> str:
    """Bỏ ký hiệu lạ (emoji, hình vẽ) OCR hay đọc nhầm từ nền."""
    import unicodedata

    import re

    t = "".join(ch for ch in t if unicodedata.category(ch) not in ("So", "Sk", "Co", "Cn"))
    return re.sub(r"([，。！？、,.!?;；:：…])\1+", r"\1", t).strip()


def _sig(f):
    """Dấu vân tay nét chữ: điểm sáng sát điểm tối (chữ trắng/vàng viền đen), thu nhỏ 4 lần."""
    import numpy as np

    g = f.astype(np.int16)
    b, d = g > 175, g < 80
    t = np.zeros_like(b)
    t[:, 1:] |= (b[:, 1:] & d[:, :-1]) | (d[:, 1:] & b[:, :-1])
    t[1:, :] |= (b[1:, :] & d[:-1, :]) | (d[1:, :] & b[:-1, :])
    h, w = t.shape
    small = t[: h // 4 * 4, : w // 4 * 4].reshape(h // 4, 4, w // 4, 4).any(axis=(1, 3))
    return small, float(t.mean())


def _similar(a, b) -> float:
    import numpy as np

    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 1.0


def region_crop(info: MediaInfo, region: tuple) -> tuple[int, int, int, int, int, int]:
    """(x, y, w, h) trên video gốc + kích thước ảnh đọc (W, H) cho khung (x0, y0, x1, y1) tỉ lệ."""
    x0, y0, x1, y1 = region
    x, y = int(info.width * x0) // 2 * 2, int(info.height * y0) // 2 * 2
    w = max(16, int(info.width * (x1 - x0)) // 2 * 2)
    h = max(16, int(info.height * (y1 - y0)) // 2 * 2)
    W = min(MAX_W, w) // 2 * 2
    H = max(16, int(round(h * W / w)) // 2 * 2)
    return x, y, w, h, W, H


def grab(video: str, info: MediaInfo, region: tuple, t: float):
    """1 khung (BGR) trong khung phụ đề lúc t giây - để thử đọc ngay."""
    import numpy as np

    x, y, w, h, W, H = region_crop(info, region)
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video),
           "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y},scale={W}:{H},format=bgr24", "-f", "rawvideo", "-"]
    r = subprocess.run(cmd, capture_output=True, **no_window())
    if len(r.stdout) < W * H * 3:
        raise OCRError("Không lấy được khung hình.")
    return np.frombuffer(r.stdout[: W * H * 3], np.uint8).reshape(H, W, 3).copy()


def scan(video: str, info: MediaInfo, region: tuple, work: Path, lang: str = "auto", log=None, progress=None,
         cancel=None) -> list[dict]:
    """Quét cả video -> [{start, end, text}] (có lưu lại để làm lại nhanh)."""
    import numpy as np

    st = os.stat(video)
    sig = [str(video), st.st_size, int(st.st_mtime), [round(v, 4) for v in region], lang]
    cache = Path(work) / "ocr.json"
    if cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            if d.get("sig") == sig:
                return d["lines"]
        except (ValueError, KeyError):
            pass
    eng = engine(lang)  # nạp model trước (báo lỗi sớm)
    del eng
    x, y, w, h, W, H = region_crop(info, region)
    vf = f"fps={FPS},crop={w}:{h}:{x}:{y},scale={W}:{H},format=bgr24"
    size = W * H * 3
    total = max(1, int(info.duration * FPS))
    if log:
        log(f"Quét phụ đề cứng ({LANGS.get(lang, LANGS['auto'])[0]}), khung {w}x{h}...")
    events = []           # [bắt đầu, kết thúc, ảnh đẹp nhất, độ đậm chữ, vân tay]
    cur = None
    k = 0
    for hw in (["-hwaccel", "auto"], []):
        cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", *hw, "-i", str(video), "-an", "-sn",
               "-vf", vf, "-f", "rawvideo", "-"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **no_window())
        events, cur, k = [], None, 0
        try:
            while True:
                if cancel is not None and cancel.is_set():
                    proc.kill()
                    raise Cancelled()
                raw = proc.stdout.read(size)
                if len(raw) < size:
                    break
                img = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
                gray = img.mean(axis=2)
                s, dens = _sig(gray)
                t = k / FPS
                has = dens > 0.004 and s.sum() > 12
                if has and cur is not None and _similar(cur[4], s) > 0.55 and t - cur[1] <= 1.6 / FPS:
                    cur[1] = t
                    if dens > cur[3]:
                        cur[2], cur[3] = img.copy(), dens
                    cur[4] = np.logical_or(cur[4], s) if _similar(cur[4], s) > 0.8 else s
                elif has:
                    if cur is not None:
                        events.append(cur)
                    cur = [t, t, img.copy(), dens, s]
                elif cur is not None and t - cur[1] > 1.6 / FPS:
                    events.append(cur)
                    cur = None
                k += 1
                if progress and k % 20 == 0:
                    progress(0.6 * k / total, f"Quét khung hình {int(t)}/{int(info.duration)}s")
        finally:
            proc.stdout.close()
            proc.wait()
        if k >= max(1, int(total * 0.8)):
            break
    if cur is not None:
        events.append(cur)
    lines: list[dict] = []
    for i, (a, b, img, _d, _s) in enumerate(events):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if b - a < 0.2:  # chớp qua 1 khung: bỏ (thường là nhiễu)
            continue
        txt = read_image(img, lang)
        if progress:
            progress(0.6 + 0.4 * (i + 1) / max(1, len(events)), f"Đọc chữ {i + 1}/{len(events)} câu")
        if not txt:
            continue
        a2, b2 = round(max(0.0, a - 0.5 / FPS), 2), round(b + 1.0 / FPS, 2)
        if lines and difflib.SequenceMatcher(None, lines[-1]["text"], txt).ratio() > 0.85 and \
                a2 - lines[-1]["end"] < 0.8:
            lines[-1]["end"] = b2
            if len(txt) > len(lines[-1]["text"]):
                lines[-1]["text"] = txt
            continue
        lines.append({"start": a2, "end": b2, "text": txt})
    cache.write_text(json.dumps({"sig": sig, "lines": lines}, ensure_ascii=False), encoding="utf-8")
    if log:
        log(f"Đọc được {len(lines)} câu phụ đề cứng.")
    return lines
