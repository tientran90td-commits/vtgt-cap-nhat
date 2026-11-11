"""Dùng AI đọc lời thoại phim và viết kịch bản tóm tắt + chọn cảnh minh họa."""
from __future__ import annotations

import json

from .config import Settings
from .ffmpeg_utils import Cancelled, fmt_ts, parse_ts
from .llm import PROVIDERS, chat, extract_json
from .scenes import snap
from .subtitles import transcript_to_text

STYLES: dict[str, dict] = {
    "review": {
        "name": "Review phim kiểu TikTok/YouTube (kịch tính, cuốn hút)",
        "prompt": "Viral movie-recap narrator style: a strong hook in the first sentence, short punchy sentences, "
                  "suspense, rhetorical questions, cliffhangers between segments. Refer to characters by simple "
                  "nicknames (e.g. 'anh chàng', 'cô gái', 'gã trùm') when names are unclear.",
    },
    "summary": {
        "name": "Tóm tắt nghiêm túc, đầy đủ nội dung",
        "prompt": "Clear, neutral, informative summary narration that covers the full plot in order.",
    },
    "funny": {
        "name": "Hài hước, bựa, chém gió",
        "prompt": "Funny, witty, slightly sarcastic narration with jokes and playful comments, but keep the plot clear.",
    },
    "emotional": {
        "name": "Kể chuyện cảm xúc, sâu lắng",
        "prompt": "Emotional storytelling narration, warm and touching, focusing on characters' feelings and relationships.",
    },
    "horror": {
        "name": "Kinh dị / bí ẩn, giọng trầm",
        "prompt": "Dark, mysterious, creepy narration that builds tension and dread.",
    },
    "analysis": {
        "name": "Phân tích, giải thích ý nghĩa phim",
        "prompt": "Analytical narration: summarize the plot and explain hidden meanings, symbolism and themes.",
    },
    "kids": {
        "name": "Kể chuyện cho thiếu nhi",
        "prompt": "Simple, friendly, gentle storytelling suitable for children.",
    },
}

TONES = ["natural", "funny", "lively", "serious", "dramatic", "horror", "sad", "excited", "warm", "angry", "kids"]
# phong cách kịch bản -> cách đọc mặc định
STYLE_TONE = {"review": "dramatic", "summary": "serious", "funny": "funny", "emotional": "warm", "horror": "horror",
              "analysis": "serious", "kids": "kids"}

MODES = {
    "narrate": "Thuyết minh AI (lồng tiếng đọc tóm tắt)",
    "highlight": "Cắt highlight giữ thoại gốc (không lồng tiếng)",
    "mixed": "Kết hợp: thuyết minh + giữ vài câu thoại đắt giá",
}

OUTPUT_LANGUAGES = ["Tiếng Việt", "English", "中文", "日本語", "한국어", "ไทย", "Bahasa Indonesia", "Español",
                    "Français", "Deutsch", "Português", "Русский", "हिन्दी"]

# số "từ" đọc mỗi giây (ước lượng): tiếng Việt ~ 3 âm tiết/giây
_WPS = {"Tiếng Việt": 3.0, "English": 2.5, "中文": 4.5, "日本語": 6.0, "한국어": 4.0, "ไทย": 4.0}

SYSTEM = """You are a professional movie-recap scriptwriter and video editor.
You receive the timestamped dialogue transcript of a long film. Your job: write a SHORT RECAP VIDEO script that
retells the story, and for every narration segment choose the exact time range of the original film to show on screen.

Return ONLY a JSON object with this exact schema:
{
  "title": "catchy video title",
  "description": "1-2 sentence description for the video post",
  "segments": [
    {"start": "HH:MM:SS", "end": "HH:MM:SS", "narration": "text read by the voice-over", "scene": "short note of what is on screen",
     "tone": "how this line should be read: one of natural|funny|lively|serious|dramatic|horror|sad|excited|warm|angry|kids"}
  ]
}
Rules:
- Segments must follow the story in chronological order of the film (start times increasing).
- "start"/"end" MUST be inside the film duration and point to the moments that best illustrate the narration
  (use the dialogue timestamps to locate events). Each clip should be 6-25 seconds long.
- Do not reuse the same time range twice. Spread clips over the whole film (beginning, middle, ending).
- Narration must be fluent, natural spoken language for a voice-over (no emojis, no markdown, no stage directions,
  no timestamps inside the narration). Write numbers as words when natural.
- Each narration should take about as long to read as its clip (around 2.5-3 words per second).
- If FILM INFO is given, use the exact character names and facts from it; never invent names.
- Choose "tone" per segment to match the emotion of that moment and the requested style
  (e.g. a funny recap mostly "funny", but a death scene can be "sad", a chase "dramatic").
"""


def _mode_rules(mode: str) -> str:
    if mode == "highlight":
        return ("MODE: HIGHLIGHT CUT. Do NOT write voice-over. Set \"narration\" to an empty string for every segment. "
                "Pick the most important / iconic moments with their ORIGINAL dialogue so that watching the clips in "
                "order tells the whole story. Clips may be 8-40 seconds.")
    if mode == "mixed":
        return ("MODE: MIXED. Mostly voice-over narration segments, but for 2-5 of the most iconic lines of dialogue add "
                "a segment with empty \"narration\" so the original audio plays (clip 4-12 seconds around that line).")
    return "MODE: VOICE-OVER NARRATION for every segment."


def build_user_prompt(transcript_text: str, duration: float, opts: dict, notes: bool = False,
                      film_ctx: str = "", visual: str = "") -> str:
    target = float(opts.get("target_minutes", 5)) * 60
    lang = opts.get("language", "Tiếng Việt")
    wps = _WPS.get(lang, 2.6)
    n_seg = max(3, int(round(target / 16)))
    style = STYLES.get(opts.get("style", "review"), STYLES["review"])["prompt"]
    spoiler = ("Tell the ENDING of the film clearly." if opts.get("spoiler", True)
               else "Do NOT reveal the ending; finish with a suspenseful question inviting viewers to watch the film.")
    custom = (opts.get("custom") or "").strip()
    src = "SUMMARIZED TIMELINE NOTES" if notes else "TRANSCRIPT"
    return f"""Film duration: {fmt_ts(duration)} ({int(duration)} seconds).
Target recap video length: about {int(target)} seconds -> about {n_seg} segments, total narration about {int(target * wps)} words.
Write the narration in: {lang}.
Style: {style}
{spoiler}
{_mode_rules(opts.get('mode', 'narrate'))}
{('Extra instructions from the user: ' + custom) if custom else ''}

{film_ctx}

=== {src} (timestamps refer to the original film) ===
{transcript_text}
{('=== VISUAL NOTES (what is on screen at these times; use them to pick accurate clips) ===' + chr(10) + visual) if visual else ''}
"""


CHUNK_SYSTEM = """You help summarize a long film for a recap video. You receive one PART of the timestamped transcript.
Write a concise chronological timeline of the important events in this part. Each line:
[HH:MM:SS - HH:MM:SS] what happens (who, what, why), plus any iconic line of dialogue in quotes.
Keep timestamps from the transcript. Write in English. Max 40 lines. Return plain text, no JSON."""


def write_script(transcript: list[dict], duration: float, settings: Settings, opts: dict, log, progress, cancel,
                 scene_cuts: list[float] | None = None, film: dict | None = None,
                 visual: list[dict] | None = None) -> dict:
    pid = opts.get("provider", "gemini")
    model = opts.get("model") or (PROVIDERS[pid]["models"] or [""])[0]
    if pid == "none":
        return auto_script(transcript, duration, opts, scene_cuts)
    if not transcript:
        raise RuntimeError("Chưa có lời thoại. Hãy chạy bước nhận dạng thoại hoặc nạp phụ đề trước.")
    if model in ("", "auto"):
        from .llm import resolve_model

        model = resolve_model(pid, "auto", settings, log)
    full_text = transcript_to_text(transcript)
    max_chars = int(opts.get("max_chars") or PROVIDERS[pid].get("max_chars") or 150000)
    max_chars = min(max_chars, PROVIDERS[pid].get("max_chars", max_chars))
    if pid == "web":  # bản web: mỗi lần dán tối đa bao nhiêu ký tự (người dùng chỉnh được)
        max_chars = int(opts.get("web_max_chars") or 60000)
    from .film_id import film_context
    from .llm import TooLarge

    vis = "\n".join(f"[{fmt_ts(v['t'])}] {v['desc']}" for v in (visual or []))
    for _try in range(4):
        try:
            text, notes = full_text, False
            if len(text) > max_chars:
                # Phim quá dài so với ngữ cảnh/hạn mức của model -> tóm tắt từng phần trước (map-reduce)
                parts = _split_lines(text, max_chars // 2)
                log(f"Transcript dài {len(text):,} ký tự > giới hạn {max_chars:,}. Tóm tắt trước {len(parts)} phần...")
                summaries = []
                for i, part in enumerate(parts):
                    if cancel.is_set():
                        raise Cancelled()
                    progress(0.7 * i / len(parts), f"AI đọc phần {i + 1}/{len(parts)}")
                    summaries.append(chat(pid, model, CHUNK_SYSTEM, film_context(film) + "\n\n" + part, settings,
                                          json_mode=False, max_tokens=4000, log=log))
                text = "\n".join(summaries)
                notes = True
            if cancel.is_set():
                raise Cancelled()
            progress(0.75, f"AI ({PROVIDERS[pid]['name']} / {model}) đang viết kịch bản...")
            log(f"Gửi {len(text):,} ký tự cho AI {model}...")
            raw = chat(pid, model, SYSTEM, build_user_prompt(text, duration, opts, notes, film_context(film), vis),
                       settings, json_mode=True, log=log)
            break
        except TooLarge as e:
            # ~3 ký tự/token cho tiếng Việt/Anh trộn, chừa chỗ cho prompt & câu trả lời
            cur = min(max_chars, len(full_text))
            new_max = cur // 2
            if e.limit_tokens:
                new_max = min(new_max, int(e.limit_tokens * 3 * 0.5))
            max_chars = max(3000, new_max)
            log(f"{e} -> chia nhỏ lời thoại (mỗi phần ≤ {max_chars:,} ký tự) rồi thử lại.", level="warn")
            if _try == 3:
                raise
            import time

            time.sleep(20)  # đợi hạn mức token/phút hồi lại
    data = extract_json(raw)
    script = normalize_script(data, duration, scene_cuts, opts.get("mode", "narrate"))
    progress(1.0, "Đã có kịch bản")
    log(f"Kịch bản: {len(script['segments'])} đoạn - '{script.get('title', '')}'")
    return script


def _split_lines(text: str, size: int) -> list[str]:
    parts, cur, n = [], [], 0
    for ln in text.splitlines():
        if n + len(ln) > size and cur:
            parts.append("\n".join(cur))
            cur, n = [], 0
        cur.append(ln)
        n += len(ln) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts


def normalize_script(data: dict, duration: float, scene_cuts=None, mode: str = "narrate") -> dict:
    segs_in = data.get("segments") or data.get("scenes") or []
    out = []
    for s in segs_in:
        if not isinstance(s, dict):
            continue
        st = parse_ts(s.get("start", 0))
        en = parse_ts(s.get("end", st + 10))
        st = max(0.0, min(st, duration - 1))
        if en <= st:
            en = st + 10
        en = min(en, duration)
        if scene_cuts:
            st2 = snap(st, scene_cuts)
            if st2 < en - 2:
                st = st2
        narr = str(s.get("narration") or s.get("text") or "").strip()
        if mode == "highlight":
            narr = ""
        tone = str(s.get("tone") or "").strip().lower()
        out.append({
            "start": round(st, 2),
            "end": round(en, 2),
            "narration": narr,
            "scene": str(s.get("scene") or s.get("note") or "").strip(),
            "tone": tone if tone in TONES else "",
        })
    if not out:
        raise RuntimeError("AI không trả về đoạn nào. Thử lại hoặc đổi model.")
    return {
        "title": str(data.get("title") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "segments": out,
    }


def auto_script(transcript: list[dict], duration: float, opts: dict, scene_cuts=None) -> dict:
    """Không dùng AI: chia đều phim, mỗi phần lấy đoạn có nhiều thoại nhất, giữ âm thanh gốc."""
    target = float(opts.get("target_minutes", 5)) * 60
    clip = 15.0
    n = max(3, int(target // clip))
    out = []
    for i in range(n):
        a = duration * i / n
        b = duration * (i + 1) / n
        best_t, best_score = a, -1
        t = a
        while t + clip <= b:
            score = sum(min(s["end"], t + clip) - max(s["start"], t)
                        for s in transcript if s["end"] > t and s["start"] < t + clip)
            if score > best_score:
                best_t, best_score = t, score
            t += 5
        st = snap(best_t, scene_cuts or [])
        out.append({"start": round(st, 2), "end": round(min(duration, st + clip), 2), "narration": "",
                    "scene": f"Phần {i + 1}/{n}"})
    return {"title": "", "description": "", "segments": out}


def script_to_text(script: dict) -> str:
    lines = [script.get("title", ""), script.get("description", ""), ""]
    for i, s in enumerate(script.get("segments", []), 1):
        lines.append(f"[{i}] {fmt_ts(s['start'])} - {fmt_ts(s['end'])}")
        lines.append(s.get("narration") or "(giữ thoại gốc)")
        lines.append("")
    return "\n".join(lines)


def save_script(script: dict, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)


def load_script(path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
