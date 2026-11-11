"""AI viết kịch bản recap: chọn cảnh + lời thuyết minh, ĐÚNG thời lượng bạn chọn."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .ai import PROVIDERS, chat, extract_json
from .config import Settings
from .media import Cancelled
from .transcript import _ts, fmt, to_prompt_text

STYLES = {
    "review": ("🔥 Review phim kịch tính (TikTok/YouTube)",
               "punchy movie-review narrator: strong hook in the first sentence, suspense, rhetorical questions, "
               "cliffhangers between scenes"),
    "summary": ("📖 Tóm tắt rõ ràng, dễ hiểu", "clear, calm storyteller who explains who is who and why things happen"),
    "funny": ("😂 Hài hước, lầy lội", "witty, playful narrator with light jokes and funny comparisons"),
    "horror": ("👻 Kinh dị, rùng rợn", "dark, tense narrator building dread and mystery"),
    "emotional": ("💔 Cảm động, sâu lắng", "warm, emotional narrator focusing on feelings and relationships"),
    "explain": ("🧠 Giải thích ý nghĩa, ẩn ý", "analytical narrator explaining hidden meanings and symbolism"),
}
MODES = {"narrate": "Thuyết minh AI toàn bộ", "mixed": "Thuyết minh + giữ vài câu thoại gốc đắt giá"}
LANGS = ["Tiếng Việt", "English", "中文", "日本語", "한국어", "ไทย", "Bahasa Indonesia", "Español", "Français"]
WPS = {"Tiếng Việt": 3.0, "English": 2.5, "中文": 4.5, "日本語": 6.0, "한국어": 4.0, "ไทย": 4.0}

SYSTEM = """You are a professional movie-recap scriptwriter and editor.
You get the timestamped dialogue of a long film and write the script of a SHORT recap video: a sequence of
segments, each = one clip of the film (start-end time) + the narration read over it.
Return ONLY JSON:
{"title": "catchy video title", "description": "1-2 sentence description",
 "segments": [{"start": "HH:MM:SS", "end": "HH:MM:SS", "narration": "text read aloud over this clip",
               "keep_original": false}]}
Rules:
- Tell the WHOLE story in chronological order, from setup to the ending, covering the entire film.
- Each clip must show what its narration talks about; clip length about the time needed to read the narration.
- Narration: natural spoken language, full sentences, no timestamps, no stage directions, numbers in words.
- Refer to characters by name when known."""


def wps(lang: str) -> float:
    return WPS.get(lang, 2.6)


def build_prompt(text: str, duration: float, opts: dict, summarized: bool = False) -> str:
    target = float(opts.get("minutes", 5) or 5) * 60
    w = wps(opts.get("language", "Tiếng Việt"))
    n_seg = max(3, int(round(target / 15)))
    style = STYLES.get(opts.get("style", "review"), STYLES["review"])[1]
    mode = ""
    if opts.get("mode") == "mixed":
        mode = ('\nAlso keep 2-4 iconic lines of ORIGINAL dialogue: for those segments set "keep_original": true, '
                'empty narration, and a clip of 3-8 seconds exactly around that line.')
    extra = (opts.get("extra") or "").strip()
    return (f"Language of the narration: {opts.get('language', 'Tiếng Việt')}\n"
            f"Narrator style: {style}\n"
            f"Film length: {fmt(duration)}\n"
            f"TARGET VIDEO LENGTH: about {int(target)} seconds = about {n_seg} segments and about "
            f"{int(target * w)} words of narration in total (each segment 2-4 full sentences, ~{int(15 * w)} words). "
            f"Do NOT write less.{mode}\n"
            + (f"Extra requests: {extra}\n" if extra else "")
            + ("The dialogue below was SUMMARIZED per part (timestamps kept).\n" if summarized else "")
            + "\n=== DIALOGUE ===\n" + text)


CHUNK_SYSTEM = """Summarize this part of a film's dialogue as a list of key story events in chronological order,
one line each, keeping the timestamp of the moment: "[HH:MM:SS] event". Be specific (names, actions)."""


def _split(text: str, size: int) -> list[str]:
    parts, cur = [], []
    n = 0
    for line in text.splitlines():
        if n + len(line) > size and cur:
            parts.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += len(line) + 1
    if cur:
        parts.append("\n".join(cur))
    return parts


def estimate_seconds(script: dict, lang: str = "Tiếng Việt") -> float:
    w = wps(lang)
    total = 0.0
    for s in script.get("segments", []):
        if s.get("narration"):
            total += len(s["narration"].split()) / w + 0.3
        else:
            total += min(30.0, max(1.0, s["end"] - s["start"]))
    return total


def normalize(data: dict, duration: float) -> dict:
    segs = []
    for s in data.get("segments") or []:
        if not isinstance(s, dict):
            continue
        st = _ts(str(s.get("start", 0))) if not isinstance(s.get("start"), (int, float)) else float(s["start"])
        en = _ts(str(s.get("end", 0))) if not isinstance(s.get("end"), (int, float)) else float(s["end"])
        st = max(0.0, min(st, max(0.0, duration - 2)))
        if en <= st + 1:
            en = st + 6
        en = min(en, duration)
        narr = " ".join(str(s.get("narration") or "").split())
        keep = bool(s.get("keep_original")) and not narr
        if not narr and not keep:
            continue
        segs.append({"start": round(st, 2), "end": round(en, 2), "narration": narr, "keep_original": keep})
    segs.sort(key=lambda x: x["start"])
    if not segs:
        raise RuntimeError("AI không viết được đoạn nào hợp lệ - hãy thử lại.")
    return {"title": str(data.get("title") or "").strip(), "description": str(data.get("description") or "").strip(),
            "segments": segs}


def auto_highlights(transcript: list[dict], duration: float, minutes: float) -> dict:
    """Không dùng AI: cắt các cảnh có nhiều thoại rải đều cả phim, giữ tiếng gốc."""
    target = minutes * 60
    n = max(3, int(target / 10))
    step = duration / n
    segs = []
    for k in range(n):
        a, b = k * step, (k + 1) * step
        lines = [t for t in transcript if a <= t["start"] < b]
        st = lines[0]["start"] if lines else a + step * 0.4
        segs.append({"start": round(st, 2), "end": round(min(duration, st + target / n), 2), "narration": "",
                     "keep_original": True})
    return {"title": "Highlight", "description": "", "segments": segs}


def write(transcript: list[dict], duration: float, settings: Settings, log, progress, cancel) -> dict:
    opts = settings.section("ai")
    provider = "ollama" if (settings.offline and opts.get("provider") != "none") else opts.get("provider", "ollama")
    if provider == "none":
        return auto_highlights(transcript, duration, float(opts.get("minutes", 5)))
    if not transcript:
        raise RuntimeError("Chưa có lời thoại của phim.")
    text = to_prompt_text(transcript)
    max_chars = PROVIDERS[provider]["max_chars"]
    summarized = False
    if len(text) > max_chars:
        parts = _split(text, max_chars // 2)
        log(f"Lời thoại dài ({len(text):,} ký tự) - AI tóm tắt trước {len(parts)} phần (song song)...")
        progress(0.1, f"AI đọc {len(parts)} phần phim")
        with ThreadPoolExecutor(max_workers=1 if provider == "ollama" else min(4, len(parts))) as ex:
            text = "\n".join(ex.map(lambda p: chat(settings, CHUNK_SYSTEM, p, json_mode=False, max_tokens=4000,
                                                   log=log, cancel=cancel), parts))
        summarized = True
    target = float(opts.get("minutes", 5) or 5) * 60
    tokens = int(max(8000, min(32000, 5000 + target / 60 * 1800)))
    progress(0.4, "AI đang viết kịch bản")
    log(f"Gửi {len(text):,} ký tự lời thoại cho AI · mục tiêu {target / 60:g} phút...")
    prompt = build_prompt(text, duration, opts, summarized)
    script = normalize(extract_json(chat(settings, SYSTEM, prompt, max_tokens=tokens, log=log, cancel=cancel)),
                       duration)
    # kiểm tra độ dài: AI hay viết quá ngắn -> yêu cầu viết lại dài hơn (tối đa 2 lần)
    est = estimate_seconds(script, opts.get("language", "Tiếng Việt"))
    for rnd in range(2):
        if est >= 0.75 * target:
            break
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        log(f"Kịch bản AI viết chỉ ~{est / 60:.1f} phút (mục tiêu {target / 60:g}) → yêu cầu viết dài thêm "
            f"(lần {rnd + 1})...", "warn")
        progress(0.7, "AI viết dài thêm cho đủ thời lượng")
        words = sum(len(s["narration"].split()) for s in script["segments"])
        more = (f"\n\n=== YOUR PREVIOUS SCRIPT WAS FAR TOO SHORT ===\nIt had {len(script['segments'])} segments and "
                f"{words} words (~{est:.0f}s). The video MUST be ~{int(target)}s = ~{int(target * wps(opts.get('language', '')))}"
                " words. Rewrite the COMPLETE script: more events, more segments over the whole film, 2-4 full "
                "sentences per segment. Do not stop early.")
        try:
            s2 = normalize(extract_json(chat(settings, SYSTEM, prompt + more, max_tokens=tokens, log=log,
                                             cancel=cancel)), duration)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"Viết dài thêm lỗi ({e}) - giữ bản hiện có.", "warn")
            break
        e2 = estimate_seconds(s2, opts.get("language", "Tiếng Việt"))
        if e2 > est:
            script, est = s2, e2
    log(f"Kịch bản: {len(script['segments'])} đoạn · ước tính ~{est / 60:.1f} phút · '{script['title']}'")
    progress(1.0, "Đã có kịch bản")
    return script
