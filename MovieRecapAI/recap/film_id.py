"""Nhận diện phim chính xác + AI "xem" hình ảnh các cảnh.

1. identify(): đoán phim từ tên file + khung hình + đoạn lời thoại (AI có thị giác: Gemini, Claude, GPT...).
2. (tùy chọn) Tra TMDB (themoviedb.org) để lấy tên phim, năm, nội dung, tên nhân vật CHUẨN.
3. visual_notes(): AI mô tả các khung hình rải khắp phim -> giúp viết kịch bản & chọn cảnh đúng hơn.

Thông tin phim được dùng để: gợi ý Whisper nghe đúng tên riêng, và để AI viết kịch bản đúng tên nhân vật.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from .config import Settings
from .ffmpeg_utils import Cancelled, fmt_ts, run_ffmpeg
from .llm import PROVIDERS, LLMError, chat, extract_json

VISION_PROVIDERS = {"gemini", "anthropic", "openai", "openrouter", "xai", "custom", "ollama", "lmstudio"}

_JUNK = re.compile(
    r"\b(2160p|1080p|720p|480p|4k|uhd|hdr10?|dv|web-?dl|webrip|bluray|brrip|bdrip|hdtv|dvdrip|x26[45]|h\.?26[45]|"
    r"hevc|avc|aac\d?(\.\d)?|ddp?\d?(\.\d)?|atmos|10bit|8bit|vietsub|thuyết minh|thuyet minh|lồng tiếng|long tieng|"
    r"full|hd|sd|extended|remastered|proper|repack|yify|rarbg|psa|amzn|nf|dsnp|hmax)\b", re.I)


def clean_filename(name: str) -> tuple[str, str]:
    """'The.Dark.Knight.2008.1080p.BluRay.x264' -> ('The Dark Knight', '2008')."""
    stem = Path(name).stem
    stem = re.sub(r"\[[^\]]*\]|\([^)]*(?:rip|1080|720|sub)[^)]*\)", " ", stem, flags=re.I)
    year = ""
    m = re.search(r"(?<!\d)(19[2-9]\d|20[0-4]\d)(?!\d)", stem)
    if m:
        year = m.group(1)
        stem = stem[:m.start()] or stem
    stem = re.sub(r"[._]+", " ", stem)
    stem = _JUNK.sub(" ", stem)
    stem = re.sub(r"\s*[-–]\s*$", "", re.sub(r"\s+", " ", stem)).strip(" -")
    return stem, year


def grab_frames(video: str, times: list[float], out_dir: Path, width: int = 640, cancel=None) -> list[tuple[float, bytes]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for t in times:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        f = out_dir / f"f_{int(t):06d}_{width}.jpg"
        if not f.exists():
            try:
                run_ffmpeg(["-ss", f"{t:.2f}", "-i", video, "-frames:v", "1", "-vf", f"scale={width}:-2",
                            "-q:v", "5", str(f)])
            except Exception:
                continue
        if f.exists() and f.stat().st_size > 500:
            frames.append((t, f.read_bytes()))
    return frames


def _excerpt(transcript: list[dict], limit: int = 7000) -> str:
    if not transcript:
        return ""
    lines = [f"[{fmt_ts(s['start'])}] {s['text']}" for s in transcript]
    if sum(len(x) for x in lines) <= limit:
        return "\n".join(lines)
    n = len(lines)
    pick = lines[: n // 8] + ["..."] + lines[n // 2: n // 2 + n // 12] + ["..."] + lines[-n // 12:]
    out, size = [], 0
    for ln in pick:
        if size + len(ln) > limit:
            break
        out.append(ln)
        size += len(ln) + 1
    return "\n".join(out)


ID_SYSTEM = """You are a film expert. Identify which movie or TV episode this video is, using the file name,
the screenshots and the dialogue excerpt. Be honest about uncertainty.
Return ONLY JSON:
{"title": "best known title (Vietnamese title if it has an official one, else original)",
 "original_title": "original title", "year": "YYYY or empty", "type": "movie|tv|unknown",
 "country": "", "genre": "", "confidence": 0.0-1.0,
 "characters": [{"name": "character name as used in the film", "description": "who they are, actor if known"}],
 "premise": "2-3 sentence premise WITHOUT inventing details you are not sure about",
 "whisper_hint": "one short line listing the film title and main character names for a speech recognizer"}
If you cannot identify the film, set confidence below 0.3, leave title empty and describe characters by role
("the detective", "the girl") from what you see and hear."""


def identify(video: str, duration: float, transcript: list[dict], settings: Settings, work_dir: Path,
             log, progress, cancel, use_frames: bool = True) -> dict:
    pid = settings.get("script", "provider", "gemini")
    model = settings.get("script", "model") or (PROVIDERS.get(pid, {}).get("models") or [""])[0]
    guess, year = clean_filename(video)
    info: dict = {"title": guess, "original_title": guess, "year": year, "confidence": 0.0, "characters": [],
                  "premise": "", "source": "filename"}
    if pid != "none":
        images = []
        if use_frames and pid in VISION_PROVIDERS and duration > 0:
            progress(0.1, "Lấy khung hình để AI nhận diện")
            times = [duration * x for x in (0.06, 0.18, 0.3, 0.45, 0.6, 0.75, 0.88)]
            images = [(f"Screenshot at {fmt_ts(t)}:", b) for t, b in grab_frames(video, times, work_dir / "frames",
                                                                                   640, cancel)]
        user = (f"File name: {Path(video).name}\nCleaned guess: {guess} {year}\nDuration: {fmt_ts(duration)}\n\n"
                f"Dialogue excerpt:\n{_excerpt(transcript) or '(not transcribed yet)'}")
        progress(0.4, f"AI nhận diện phim ({PROVIDERS[pid]['name']})")
        try:
            raw = chat(pid, model, ID_SYSTEM, user, settings, json_mode=True, max_tokens=4000, log=log,
                       images=images or None)
        except LLMError as e:
            if not images:
                raise
            log(f"Model không nhận ảnh ({e}) - thử lại chỉ bằng chữ.", level="warn")
            raw = chat(pid, model, ID_SYSTEM, user, settings, json_mode=True, max_tokens=4000, log=log)
        data = extract_json(raw)
        info.update({k: v for k, v in data.items() if v not in (None, "", [])})
        info["source"] = "ai"
        try:
            info["confidence"] = float(info.get("confidence") or 0)
        except (TypeError, ValueError):
            info["confidence"] = 0.0
    if (settings.get("api", "tmdb_key") or "").strip():
        progress(0.75, "Đối chiếu TMDB")
        try:
            t = tmdb_lookup(info.get("original_title") or info.get("title") or guess,
                            str(info.get("year") or year), settings, info.get("type"))
            if t:
                info.update(t)
                info["source"] = "tmdb"
                info["confidence"] = max(float(info.get("confidence") or 0), 0.9)
                log(f"TMDB: {t.get('title')} ({t.get('year')}) - {len(t.get('characters', []))} nhân vật")
        except Exception as e:  # noqa: BLE001
            log(f"Tra TMDB lỗi: {e}", level="warn")
    progress(1.0, "Đã nhận diện phim")
    log(f"🎬 Nhận diện: {info.get('title') or '(chưa rõ)'} {info.get('year') or ''} "
        f"· độ tin cậy {float(info.get('confidence') or 0):.0%}")
    return info


# ------------------------------------------------------------------ TMDB
def _tmdb(path: str, settings: Settings, **params) -> dict:
    key = (settings.get("api", "tmdb_key") or "").strip()
    headers = {"accept": "application/json"}
    if key.startswith("eyJ"):  # "API Read Access Token" (v4)
        headers["Authorization"] = f"Bearer {key}"
    else:  # "API Key" (v3)
        params["api_key"] = key
    s = requests.Session()
    proxy = (settings.get("api", "proxy") or "").strip()
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    r = s.get(f"https://api.themoviedb.org/3/{path}", params=params, headers=headers, timeout=30)
    if r.status_code == 401:
        raise LLMError("TMDB key không hợp lệ.")
    r.raise_for_status()
    return r.json()


def tmdb_lookup(title: str, year: str, settings: Settings, kind: str | None = None) -> dict | None:
    if not title:
        return None
    res = _tmdb("search/multi", settings, query=title, language="vi-VN", include_adult="false").get("results", [])
    res = [x for x in res if x.get("media_type") in ("movie", "tv")]
    if kind in ("movie", "tv"):
        res = sorted(res, key=lambda x: x.get("media_type") != kind)
    if year:
        same = [x for x in res if (x.get("release_date") or x.get("first_air_date") or "").startswith(year)]
        res = same or res
    if not res:
        return None
    best = res[0]
    mt, mid = best["media_type"], best["id"]
    d = _tmdb(f"{mt}/{mid}", settings, language="vi-VN", append_to_response="credits")
    overview = d.get("overview") or ""
    if not overview:
        overview = _tmdb(f"{mt}/{mid}", settings, language="en-US").get("overview", "")
    cast = (d.get("credits") or {}).get("cast", [])[:15]
    chars = [{"name": c.get("character") or c.get("name"), "description": f"do {c.get('name')} đóng"}
             for c in cast if c.get("character")]
    return {
        "title": d.get("title") or d.get("name") or title,
        "original_title": d.get("original_title") or d.get("original_name") or title,
        "year": (d.get("release_date") or d.get("first_air_date") or "")[:4],
        "type": mt,
        "genre": ", ".join(g["name"] for g in d.get("genres", [])),
        "premise": overview,
        "characters": chars,
        "tmdb_id": mid,
        "whisper_hint": ", ".join([d.get("original_title") or d.get("original_name") or title]
                                  + [c["name"] for c in chars[:10]]),
    }


# ------------------------------------------------------------------ AI xem cảnh
VIS_SYSTEM = """You watch screenshots taken from a film at the given timestamps.
For EACH screenshot write one short factual line: who is on screen (use character names from the film info when you
recognize them), what they are doing, place/mood. Do not invent plot. Return ONLY JSON:
{"frames": [{"t": "HH:MM:SS", "desc": "..."}]} in the same order."""


def visual_notes(video: str, duration: float, film: dict | None, settings: Settings, work_dir: Path, log, progress,
                 cancel, max_frames: int = 48) -> list[dict]:
    pid = settings.get("script", "provider", "gemini")
    model = settings.get("script", "model") or (PROVIDERS.get(pid, {}).get("models") or [""])[0]
    if pid not in VISION_PROVIDERS:
        log(f"{PROVIDERS.get(pid, {}).get('name', pid)} không xem được ảnh - bỏ qua bước AI xem cảnh.", level="warn")
        return []
    step = max(45.0, duration / max_frames)
    times = [step / 2 + i * step for i in range(int(duration // step))][:max_frames]
    progress(0.05, f"Lấy {len(times)} khung hình")
    frames = grab_frames(video, times, work_dir / "frames", 448, cancel)
    ctx = film_context(film)
    notes: list[dict] = []
    batch = 12
    for i in range(0, len(frames), batch):
        if cancel.is_set():
            raise Cancelled()
        part = frames[i:i + batch]
        progress(0.1 + 0.9 * i / max(1, len(frames)), f"AI xem cảnh {i + 1}-{i + len(part)}/{len(frames)}")
        imgs = [(f"[{fmt_ts(t)}]", b) for t, b in part]
        try:
            raw = chat(pid, model, VIS_SYSTEM, (ctx or "") + f"\nDescribe these {len(part)} screenshots.", settings,
                       json_mode=True, max_tokens=4000, log=log, images=imgs)
            items = extract_json(raw).get("frames") or []
        except Exception as e:  # noqa: BLE001
            log(f"AI xem cảnh lỗi ({e}) - bỏ qua nhóm này.", level="warn")
            continue
        for (t, _b), it in zip(part, items):
            d = (it.get("desc") if isinstance(it, dict) else str(it)) or ""
            if d.strip():
                notes.append({"t": round(t, 1), "desc": d.strip()})
    log(f"AI đã xem {len(notes)} khung hình.")
    return notes


def film_context(film: dict | None) -> str:
    """Khối thông tin phim đưa vào prompt viết kịch bản."""
    if not film or not (film.get("title") or film.get("characters") or film.get("premise") or film.get("notes")):
        return ""
    lines = ["=== FILM INFO" + (" (verified from TMDB)" if film.get("source") == "tmdb" else "") + " ==="]
    if film.get("title"):
        t = film["title"]
        if film.get("original_title") and film["original_title"] != t:
            t += f" / {film['original_title']}"
        lines.append(f"Title: {t} {('(' + str(film['year']) + ')') if film.get('year') else ''}".strip())
    if film.get("genre"):
        lines.append(f"Genre: {film['genre']}")
    if film.get("premise"):
        lines.append(f"Premise: {film['premise']}")
    chars = film.get("characters") or []
    if chars:
        lines.append("Main characters (use these exact names): " + "; ".join(
            f"{c.get('name')}" + (f" - {c.get('description')}" if c.get("description") else "")
            for c in chars[:15] if isinstance(c, dict) and c.get("name")))
    if film.get("notes"):
        lines.append(f"Notes from the user (trust these): {film['notes']}")
    return "\n".join(lines)


def whisper_hint(film: dict | None) -> str:
    if not film:
        return ""
    hint = film.get("whisper_hint") or ""
    if not hint:
        names = [c.get("name") for c in (film.get("characters") or []) if isinstance(c, dict) and c.get("name")]
        hint = ", ".join([film.get("title") or ""] + names[:10]).strip(", ")
    return hint[:400]


def save(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
