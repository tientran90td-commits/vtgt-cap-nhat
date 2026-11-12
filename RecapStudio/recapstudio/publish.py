"""Chuẩn bị đăng video: ảnh bìa (thumbnail) + tiêu đề, mô tả, hashtag.

- Ảnh bìa: chọn khung hình đẹp nhất trong các đoạn recap (nét, đủ sáng, có mặt người), tăng màu, chữ tiêu đề to
  có viền, đúng khung video (16:9 / 9:16 / 1:1). Dùng Pillow + numpy (OpenCV nếu có để ưu tiên khung có mặt người).
- Tiêu đề / mô tả / hashtag: AI viết (theo chuỗi dự phòng online <-> trên máy); không có AI thì tự tạo từ kịch bản.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from .config import Settings
from .media import Cancelled, MediaInfo, frames

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/tahomabd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

INFO_SYSTEM = (
    "You write metadata for a short movie-recap video for YouTube/TikTok/Facebook. Reply ONLY with JSON: "
    '{"titles": [3 catchy titles, max 90 chars each, no hashtags], "description": "3-5 sentences hook + summary, '
    'no spoilers of the ending", "hashtags": [10-15 hashtags starting with #, no spaces], '
    '"tags": [10 short search keywords]}. Write in the requested language.')


def _font(size: int):
    from PIL import ImageFont

    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


# ------------------------------------------------------------------ chọn khung hình
def _score(rgb) -> float:
    import numpy as np

    g = rgb.mean(2)
    lap = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    sharp = float(lap.var()) ** 0.5
    bright = float(g.mean())
    sat = float((rgb.max(2).astype(int) - rgb.min(2).astype(int)).mean())
    light = 1.0 - min(1.0, abs(bright - 120) / 120)
    return sharp * (0.4 + light) * (0.6 + sat / 120)


def _faces(rgb) -> list:
    try:
        from . import reframe

        if not reframe.available():
            return []
        import numpy as np

        return reframe._faces(np.ascontiguousarray(rgb.mean(2).astype("uint8")))
    except Exception:  # noqa: BLE001
        return []


def pick_frame(video: str, info: MediaInfo, segments: list[dict], cancel=None):
    """(ảnh numpy RGB lớn, tâm x 0..1) của khung đẹp nhất."""
    import numpy as np

    segs = [s for s in segments if s.get("narration")] or segments
    if not segs:
        segs = [{"start": info.duration * 0.3, "end": info.duration * 0.3 + 5}]
    step = max(1, len(segs) // 10)
    times = [(s["start"] + min(s["end"], s["start"] + 8)) / 2 for s in segs[::step]][:12]
    w = 640
    h = max(2, int(round(w * info.height / max(1, info.width) / 2)) * 2)
    best, best_t, best_cx = -1.0, times[0], 0.5
    for t in times:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        fr = frames(video, t, None, w, h, pix="rgb24", count=1)
        if not fr:
            continue
        f = fr[0]
        sc = _score(f[: int(h * 0.85)])  # bỏ dải dưới (hay có phụ đề)
        fs = _faces(f)
        cx = 0.5
        if fs:
            x, _y, fw, fh = max(fs, key=lambda q: q[2] * q[3])
            sc *= 1.6 + min(1.0, fw * fh / (w * h) * 12)
            cx = (x + fw / 2) / w
        if sc > best:
            best, best_t, best_cx = sc, t, cx
    W = 1280
    H = max(2, int(round(W * info.height / max(1, info.width) / 2)) * 2)
    big = frames(video, best_t, None, W, H, pix="rgb24", count=1)
    if not big:
        raise RuntimeError("Không lấy được khung hình cho ảnh bìa.")
    return np.ascontiguousarray(big[0]), best_cx


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def make_thumbnail(video: str, info: MediaInfo, segments: list[dict], title: str, out: Path, aspect: str = "16:9",
                   cancel=None) -> Path:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

    rgb, cx = pick_frame(video, info, segments, cancel)
    img = Image.fromarray(rgb)
    TW, TH = {"9:16": (1080, 1920), "1:1": (1080, 1080)}.get(aspect, (1280, 720))
    sw, sh = img.size
    if sw / sh > TW / TH:  # cắt ngang, bám nhân vật
        cw = int(sh * TW / TH)
        x = int(max(0, min(sw - cw, cx * sw - cw / 2)))
        img = img.crop((x, 0, x + cw, sh))
    else:
        ch = int(sw * TH / TW)
        y = max(0, (sh - ch) // 3)
        img = img.crop((0, y, sw, y + ch))
    img = img.resize((TW, TH), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Color(img).enhance(1.25)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=60))
    # dải tối phía dưới cho chữ dễ đọc
    grad = Image.new("L", (1, TH))
    for y in range(TH):
        grad.putpixel((0, y), int(max(0, (y - TH * 0.45) / (TH * 0.55)) ** 1.4 * 215))
    shade = Image.new("RGB", (TW, TH), (0, 0, 0))
    img = Image.composite(shade, img, grad.resize((TW, TH)))
    draw = ImageDraw.Draw(img)
    text = (title or "").strip().upper()
    if text:
        size = int(TW * (0.085 if TW < TH else 0.072))
        while True:
            font = _font(size)
            lines = _wrap(draw, text, font, int(TW * 0.9))
            if len(lines) <= 3 or size < 30:
                break
            size = int(size * 0.88)
        lines = lines[:3]
        lh = int(size * 1.18)
        y = TH - int(TH * 0.06) - lh * len(lines)
        for i, ln in enumerate(lines):
            w = draw.textlength(ln, font=font)
            color = (255, 214, 10) if i == 0 else (255, 255, 255)
            draw.text(((TW - w) / 2, y + i * lh), ln, font=font, fill=color, stroke_width=max(3, size // 12),
                      stroke_fill=(0, 0, 0))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=92)
    return out


# ------------------------------------------------------------------ tiêu đề, mô tả, hashtag
def _slug_tag(s: str) -> str:
    s = re.sub(r"[^\w]+", "", s or "", flags=re.U)
    return "#" + s if s else ""


def fallback_info(script: dict, film: str, lang: str = "Tiếng Việt") -> dict:
    title = (script.get("title") or film or "Tóm tắt phim").strip()
    narr = " ".join(s.get("narration", "") for s in script.get("segments", [])[:3]).strip()
    vi = lang.startswith("Tiếng Việt")
    base = ["#reviewphim", "#tomtatphim", "#phimhay", "#recap", "#movierecap"] if vi else \
        ["#movierecap", "#moviereview", "#recap", "#film", "#movie"]
    tag = _slug_tag(film)
    return {"titles": [title, f"{title} | Tóm tắt phim" if vi else f"{title} | Movie Recap"],
            "description": (narr[:400] + ("..." if len(narr) > 400 else "")) or title,
            "hashtags": [h for h in [tag, *base] if h], "tags": [film, "review phim" if vi else "movie recap"]}


def make_info(script: dict, film: str, settings: Settings, log=None, cancel=None) -> dict:
    from . import hybrid
    from .ai import chat, extract_json

    lang = settings.get("ai", "language", "Tiếng Việt")
    if not hybrid.ai_chain(settings):
        return fallback_info(script, film, lang)
    story = " ".join(s.get("narration", "") for s in script.get("segments", []))[:6000]
    user = (f"Language: {lang}\nFilm file name: {film}\nWorking title: {script.get('title', '')}\n"
            f"Recap narration:\n{story}")
    try:
        d = extract_json(chat(settings, INFO_SYSTEM, user, json_mode=True, max_tokens=2000, log=log, cancel=cancel))
    except Cancelled:
        raise
    except Exception as e:  # noqa: BLE001
        if log:
            log(f"AI viết tiêu đề/hashtag lỗi ({e}) - dùng bản tự tạo.", "warn")
        return fallback_info(script, film, lang)
    fb = fallback_info(script, film, lang)
    titles = [str(t).strip() for t in d.get("titles") or [] if str(t).strip()] or fb["titles"]
    tags = [("#" + str(h).lstrip("#")).replace(" ", "") for h in d.get("hashtags") or [] if str(h).strip()]
    return {"titles": titles[:5], "description": str(d.get("description") or fb["description"]).strip(),
            "hashtags": list(dict.fromkeys(tags or fb["hashtags"]))[:20],
            "tags": [str(t) for t in d.get("tags") or fb["tags"]][:15]}


def text_block(info: dict) -> str:
    return (info["titles"][0] + "\n\n" + info["description"] + "\n\n" + " ".join(info["hashtags"])).strip()


def open_path(p: Path) -> None:
    import subprocess

    if sys.platform.startswith("win"):
        os.startfile(str(p))  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
