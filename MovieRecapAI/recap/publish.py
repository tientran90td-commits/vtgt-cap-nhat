"""Chuẩn bị đăng video: ảnh thumbnail + tiêu đề, mô tả, hashtag, mốc chương YouTube.

Thumbnail: chấm điểm các khung hình trong những cảnh được dùng (độ nét, khuôn mặt to & rõ, độ tương phản, màu sắc,
tránh khung tối/nhòe), chọn khung đẹp nhất rồi chèn tiêu đề chữ to viền đậm.
  -> <video>_thumb.jpg (1280x720) · <video>_thumb_doc.jpg (1080x1920) · 2 phương án phụ <video>_thumb_2/3.jpg

Thông tin đăng: AI viết 3 tiêu đề gây tò mò, mô tả, hashtag, tag và đặt tên chương; mốc chương lấy đúng thời điểm
trong video đã xuất (chuẩn YouTube: bắt đầu 00:00, >= 3 chương, mỗi chương >= 10 giây).
  -> <video>.youtube.txt (sao chép dán thẳng) + <video>.publish.json
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .config import Settings
from .ffmpeg_utils import _no_window_kwargs, ffmpeg_exe

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/tahomabd.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def fmt_chapter(t: float) -> str:
    t = int(round(t))
    h, m, s = t // 3600, t % 3600 // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ------------------------------------------------------------------ thumbnail
def _frame(video: str, t: float, width: int = 960):
    import numpy as np

    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, t):.2f}", "-i", str(video),
           "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    r = subprocess.run(cmd, capture_output=True, **_no_window_kwargs())
    if not r.stdout:
        return None
    # chiều cao: suy ra từ kích thước dữ liệu
    h = len(r.stdout) // (width * 3)
    if h < 10:
        return None
    return np.frombuffer(r.stdout[: width * h * 3], np.uint8).reshape(h, width, 3)


def score_frame(rgb, band: dict | None = None) -> tuple[float, dict]:
    """Điểm đẹp của 1 khung (càng cao càng hợp làm thumbnail)."""
    import cv2
    import numpy as np

    from .reframe import faces

    h, w = rgb.shape[:2]
    if band:  # bỏ dải phụ đề in cứng khỏi phần chấm điểm
        rgb = rgb[: max(10, int(band["y0"] * h))]
        h = rgb.shape[0]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mean = float(gray.mean())
    if mean < 28 or mean > 235:
        return -10.0, {"dark": mean}
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    contrast = float(gray.std())
    r, g, b = (rgb[..., i].astype(np.float32) for i in range(3))
    rg, yb = r - g, 0.5 * (r + g) - b
    color = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    fs = faces(cv2.resize(gray, (480, int(480 * h / w))) if w > 480 else gray)
    scale = 480 / w if w > 480 else 1.0
    face_area = max((f[2] * f[3] for f in fs), default=0) / ((w * scale) * (h * scale))
    face_x = None
    if fs:
        f = max(fs, key=lambda f: f[2] * f[3])
        face_x = (f[0] + f[2] / 2) / (w * scale)
    # mặt chiếm 3-25% khung là đẹp nhất (cận cảnh nhân vật)
    face_s = 0.0 if not fs else (min(face_area, 0.25) / 0.25) * 3.0 + 1.0
    s = (min(np.log1p(sharp) / np.log1p(800), 1.2) * 2.0 + min(contrast / 60, 1.2) * 1.2 + min(color / 60, 1.2)
         + face_s - (1.0 if mean < 50 else 0.0))
    return float(s), {"sharp": round(sharp, 1), "contrast": round(contrast, 1), "color": round(color, 1),
                      "face": round(face_area, 3), "face_x": face_x}


def candidate_times(script: dict, n: int = 36) -> list[float]:
    segs = (script or {}).get("segments") or []
    ts: list[float] = []
    for seg in segs:
        sents = [x for x in seg.get("sentences") or [] if isinstance(x, dict) and "start" in x]
        if sents:
            ts += [float(x["start"]) + 0.6 for x in sents]
        a, b = float(seg.get("start", 0)), float(seg.get("end", 0))
        if b > a:
            ts += [a + (b - a) * k for k in (0.25, 0.5, 0.75)]
    if len(ts) > n:
        step = len(ts) / n
        ts = [ts[int(i * step)] for i in range(n)]
    return sorted(set(round(t, 2) for t in ts))


def pick_frames(video: str, script: dict, log=None, band: dict | None = None, k: int = 3) -> list[dict]:
    """k khung đẹp nhất, cách nhau >= 20 giây."""
    scored = []
    for t in candidate_times(script):
        fr = _frame(video, t)
        if fr is None:
            continue
        s, det = score_frame(fr, band)
        scored.append({"t": t, "score": s, **det})
    scored.sort(key=lambda x: -x["score"])
    out: list[dict] = []
    for c in scored:
        if all(abs(c["t"] - o["t"]) >= 20 for o in out):
            out.append(c)
        if len(out) >= k:
            break
    if log and out:
        log(f"Thumbnail: chọn khung {fmt_chapter(out[0]['t'])} (điểm {out[0]['score']:.1f}"
            + (", có khuôn mặt" if out[0].get("face") else "") + f") trong {len(scored)} khung")
    return out


def _font(size: int):
    from PIL import ImageFont

    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def compose(video: str, t: float, text: str, out: Path, size: tuple[int, int], face_x: float | None = None,
            band: dict | None = None) -> Path:
    """Khung hình tại t + tiêu đề chữ to (vàng/trắng viền đen) + nền tối dần phía dưới chữ."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

    W, H = size
    fr = _frame(video, t, width=1920)
    if fr is None:
        raise RuntimeError(f"Không lấy được khung hình tại {t:.1f}s")
    img = Image.fromarray(fr)
    if band:  # cắt bỏ dải phụ đề in cứng
        img = img.crop((0, 0, img.width, max(10, int(band["y0"] * img.height))))
    # cắt theo tỉ lệ đích, ưu tiên giữ khuôn mặt
    ar = W / H
    iw, ih = img.size
    if iw / ih > ar:
        cw = int(ih * ar)
        cx = (face_x if face_x is not None else 0.5) * iw
        x0 = int(max(0, min(iw - cw, cx - cw / 2)))
        img = img.crop((x0, 0, x0 + cw, ih))
    else:
        ch = int(iw / ar)
        y0 = max(0, (ih - ch) // 3)
        img = img.crop((0, y0, iw, y0 + ch))
    img = img.resize((W, H), Image.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(1.18)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=60))
    text = (text or "").strip().upper()
    if text:
        vertical = H > W
        # nền tối dần ở vùng chữ
        grad = Image.new("L", (1, 256))
        for y in range(256):
            grad.putpixel((0, y), int(min(255, max(0, (y - 70) * 1.35))))
        area_h = int(H * (0.42 if not vertical else 0.36))
        mask = grad.resize((W, area_h))
        if vertical:
            mask = mask.transpose(Image.FLIP_TOP_BOTTOM)
        dark = Image.new("RGB", (W, area_h), (0, 0, 0))
        top = 0 if vertical else H - area_h
        img.paste(dark, (0, top), mask.point(lambda v: int(v * 0.85)))
        draw = ImageDraw.Draw(img)
        max_w = int(W * 0.9)
        size_px = int(min(W, H) * (0.15 if not vertical else 0.11))
        while True:
            font = _font(size_px)
            lines = _wrap(draw, text, font, max_w)
            if len(lines) <= 3 or size_px <= 28:
                break
            size_px = int(size_px * 0.88)
        lh = int(size_px * 1.12)
        block = lh * len(lines)
        y = int(H * 0.08) if vertical else H - block - int(H * 0.07)
        stroke = max(3, size_px // 11)
        for i, line in enumerate(lines):
            tw = draw.textlength(line, font=font)
            x = (W - tw) / 2
            color = (255, 222, 0) if i == 0 else (255, 255, 255)
            draw.text((x, y + i * lh), line, font=font, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "JPEG", quality=92)
    return out


def make_thumbnails(video_src: str, script: dict, out_video: Path, text: str, log=None,
                    band: dict | None = None) -> list[Path]:
    picks = pick_frames(video_src, script, log, band)
    if not picks:
        raise RuntimeError("Không chọn được khung hình cho thumbnail.")
    base = Path(out_video)
    stem = base.with_suffix("")
    out = [compose(video_src, picks[0]["t"], text, Path(f"{stem}_thumb.jpg"), (1280, 720), picks[0].get("face_x"), band),
           compose(video_src, picks[0]["t"], text, Path(f"{stem}_thumb_doc.jpg"), (1080, 1920), picks[0].get("face_x"),
                   band)]
    for i, p in enumerate(picks[1:3], start=2):
        out.append(compose(video_src, p["t"], text, Path(f"{stem}_thumb_{i}.jpg"), (1280, 720), p.get("face_x"), band))
    if log:
        log(f"🖼 Đã tạo {len(out)} ảnh thumbnail cạnh video.")
    return out


# ------------------------------------------------------------------ tiêu đề, mô tả, chương
META_SYSTEM = """You are a YouTube/TikTok growth editor for movie recap channels.
Given a movie recap script, write publishing metadata in the requested language. Return ONLY JSON:
{"titles": [3 catchy, curiosity-driven titles, max 90 chars, no clickbait lies, may include the film name],
 "thumb_text": "2-5 word punchy hook for the thumbnail (no film name if long)",
 "description": "2 short paragraphs hooking the viewer + 1 line credit noting this is a recap/review of the film",
 "hashtags": [8-12 hashtags without spaces, starting with #],
 "tags": [10-15 search tags],
 "chapters": [{"seg": <segment index where the chapter starts>, "title": "short chapter title"}]}
Chapters: 4-8 chapters following the story arc; the first chapter must start at seg 0."""


def _fallback_meta(script: dict, film: dict | None, lang: str) -> dict:
    title = (script or {}).get("title") or (film or {}).get("title") or "Tóm tắt phim"
    ft = (film or {}).get("title") or title
    words = [w for w in re.sub(r"[^\w\s]", " ", ft).split() if len(w) > 1][:3]
    tag_name = "#" + "".join(w.capitalize() for w in words) if words else ""
    segs = (script or {}).get("segments") or []
    chapters = []
    if segs:
        step = max(1, len(segs) // 5)
        for i in range(0, len(segs), step):
            first = (segs[i].get("narration") or segs[i].get("scene") or "").strip()
            chapters.append({"seg": i, "title": (" ".join(first.split()[:6]) or f"Phần {len(chapters) + 1}")})
    return {"titles": [title, f"Tóm tắt phim {ft} trong vài phút", f"{ft} - Toàn bộ câu chuyện"],
            "thumb_text": " ".join(title.split()[:5]),
            "description": (script or {}).get("description") or f"Tóm tắt nội dung phim {ft}.",
            "hashtags": [h for h in (tag_name, "#tomtatphim", "#reviewphim", "#recap", "#phimhay", "#movierecap") if h],
            "tags": [ft, "tóm tắt phim", "review phim", "recap phim", "phim hay"], "chapters": chapters}


def chapters_from(meta_chapters: list[dict], timeline: list, total: float) -> list[tuple[float, str]]:
    """Ghép chương AI chọn với mốc thời gian thật; đảm bảo chuẩn YouTube."""
    starts = {int(i): float(t) for i, t, _d in timeline}
    seg_ids = sorted(starts)
    out: list[tuple[float, str]] = []
    for ch in meta_chapters or []:
        try:
            si = int(ch.get("seg", 0))
        except (TypeError, ValueError):
            continue
        si = min((x for x in seg_ids if x >= si), default=None) if si not in starts else si
        if si is None:
            continue
        t = 0.0 if not out else starts[si]
        title = str(ch.get("title") or "").strip()[:60] or f"Phần {len(out) + 1}"
        if out and (t - out[-1][0] < 10 or total - t < 10):
            continue
        out.append((t, title))
    if out:
        out[0] = (0.0, out[0][1])
    return out if len(out) >= 3 else []


def make_metadata(script: dict, film: dict | None, timeline: list, total: float, settings: Settings, log=None) -> dict:
    sc = settings.section("script")
    lang = sc.get("language", "Tiếng Việt")
    meta = None
    pid = sc.get("provider", "gemini")
    if pid not in ("none", "web"):
        from .llm import PROVIDERS, chat, extract_json, resolve_model

        model = sc.get("model") or (PROVIDERS[pid]["models"] or [""])[0]
        try:
            if model in ("", "auto"):
                model = resolve_model(pid, "auto", settings, log)
            segs = (script or {}).get("segments") or []
            lines = [f"[{i}] " + ((s.get("narration") or s.get("scene") or "").strip()[:220]) for i, s in enumerate(segs)]
            f = film or {}
            user = (f"Language: {lang}\nFilm: {f.get('title') or ''} ({f.get('original_title') or ''}, {f.get('year') or ''})\n"
                    f"Recap title: {(script or {}).get('title') or ''}\nVideo length: {fmt_chapter(total)}\n\n"
                    "Segments:\n" + "\n".join(lines)[:24000])
            meta = extract_json(chat(pid, model, META_SYSTEM, user, settings, json_mode=True, max_tokens=3000, log=log))
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"AI chưa viết được tiêu đề/mô tả ({e}) - dùng mẫu có sẵn.", level="warn")
    base = _fallback_meta(script, film, lang)
    if not isinstance(meta, dict):
        meta = base
    for k, v in base.items():
        if not meta.get(k):
            meta[k] = v
    meta["hashtags"] = [h if str(h).startswith("#") else "#" + str(h).replace(" ", "") for h in meta["hashtags"]][:15]
    meta["chapter_marks"] = chapters_from(meta.get("chapters") or base["chapters"], timeline, total) or \
        chapters_from(base["chapters"], timeline, total)
    return meta


def metadata_text(meta: dict) -> str:
    parts = ["=== TIÊU ĐỀ (chọn 1) ==="] + [f"{i + 1}. {t}" for i, t in enumerate(meta.get("titles", []))]
    parts += ["", "=== CHỮ TRÊN THUMBNAIL ===", meta.get("thumb_text", ""), "", "=== MÔ TẢ (dán vào YouTube) ===",
              meta.get("description", "").strip()]
    if meta.get("chapter_marks"):
        parts += ["", "⏱ Mốc thời gian:"] + [f"{fmt_chapter(t)} {name}" for t, name in meta["chapter_marks"]]
    parts += ["", " ".join(meta.get("hashtags", [])), "", "=== TAG (YouTube Studio → Thẻ) ===",
              ", ".join(meta.get("tags", []))]
    return "\n".join(parts).strip() + "\n"


def prepare(project, out_video: Path, log=None, thumbs: bool = True, meta: bool = True) -> dict:
    """Tạo thumbnail + thông tin đăng cho video vừa xuất."""
    out_video = Path(out_video)
    qa = {}
    qf = out_video.with_suffix(".qa.json")
    if qf.exists():
        try:
            qa = json.loads(qf.read_text(encoding="utf-8"))
        except ValueError:
            qa = {}
    timeline = qa.get("timeline") or []
    total = float((qa.get("final") or {}).get("duration") or qa.get("duration") or 0)
    res: dict = {"thumbs": [], "meta": None}
    m = None
    if meta:
        m = make_metadata(project.script, project.film, timeline, total, project.settings, log)
        txt = metadata_text(m)
        out_video.with_suffix(".youtube.txt").write_text(txt, encoding="utf-8")
        out_video.with_suffix(".publish.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        res["meta"], res["text"] = m, txt
        if log:
            log(f"📝 Đã viết tiêu đề, mô tả, hashtag, {len(m['chapter_marks'])} mốc chương → "
                f"{out_video.with_suffix('.youtube.txt').name}")
    if thumbs:
        text = (m or {}).get("thumb_text") or (project.script or {}).get("title") or ""
        band = (project.overlays or {}).get("hardsub")
        res["thumbs"] = [str(p) for p in make_thumbnails(project.video, project.script, out_video, text, log, band)]
    return res
