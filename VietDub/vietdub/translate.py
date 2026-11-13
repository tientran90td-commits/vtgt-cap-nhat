"""Dịch lời thoại sang tiếng Việt chuẩn, tự nhiên, đọc kịp thời gian (để lồng tiếng / làm phụ đề).

Quy trình (AI theo chuỗi dự phòng online <-> trên máy, xem hybrid.py):
1. Đọc lướt cả video -> bảng tên riêng (Hán-Việt cho tên Trung, giữ tên Tây...), xưng hô giữa các nhân vật,
   thể loại. Mọi phần dịch sau dùng chung bảng này nên tên & xưng hô nhất quán từ đầu đến cuối.
2. Dịch từng lô 30 câu (giữ đúng số câu), kèm vài câu trước đó để mạch văn liền; câu nào cũng có giới hạn số
   chữ theo thời gian nói để giọng đọc kịp, không bị tua nhanh.
3. Kiểm tra: câu thiếu / chưa dịch (còn chữ Hán, Nhật, Hàn...) -> dịch lại.
4. Tối ưu cho thuyết minh: câu đọc quá nhanh -> AI rút gọn, đo lại, còn dài thì rút chặt hơn (tối đa 3 vòng).
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from . import ai, hybrid
from .ai import PROVIDERS, chat, extract_json
from .config import Settings
from .media import Cancelled

CPS = 16.0          # số ký tự tiếng Việt đọc được mỗi giây (tốc độ nói bình thường, thoải mái)
BATCH = 30          # 30 câu / lô: AI giữ mạch tốt, ít sót câu
MAX_CPS = 20.0      # đọc nhanh hơn mức này là quá tải -> rút gọn (đo lại sau khi rút, tối đa 3 vòng)

STYLES = {
    "natural": ("Tự nhiên, đời thường (phim hiện đại)",
                "Modern natural spoken Vietnamese, like a professional Vietnamese dubbing studio. Everyday pronouns "
                "chosen from relationships (anh/em, tôi/cậu, mày/tao when rude, con/bố mẹ...)."),
    "ancient": ("Cổ trang, kiếm hiệp, tiên hiệp",
                "Vietnamese wuxia/historical drama register: ta – ngươi, huynh – đệ, tỷ – muội, sư phụ – đồ nhi, "
                "bổn cung, thần, bệ hạ, cô nương, công tử, tiểu thư; Sino-Vietnamese (Hán-Việt) names and titles."),
    "youth": ("Trẻ trung, vui nhộn (vlog, TikTok)",
              "Lively, youthful Vietnamese as used by Vietnamese young people on social media; playful but clean."),
    "formal": ("Trang trọng (tin tức, tài liệu, giáo dục)",
               "Clear, neutral, formal Vietnamese as in documentaries and news; precise terminology."),
    "kids": ("Hoạt hình, thiếu nhi", "Simple, warm, expressive Vietnamese for children's cartoons."),
}

GLOSSARY_SYSTEM = (
    "You prepare a translation brief for dubbing a video into Vietnamese. You get the video title (often with "
    "hashtags naming the show) and the transcript (any language). First identify the work: which anime, manga, "
    "donghua, drama, film, game or novel this is, and whether it is a narrator recap (third-person storytelling) "
    "or character dialogue. Reply ONLY with JSON: {\"work\": \"title of the work as known in Vietnam + origin "
    "(e.g. anime Nhật, phim Trung), or empty if unknown\", \"genre\": \"short genre\", \"narration\": true/false, "
    "\"names\": {\"original name or term\": \"Vietnamese form\"}, \"pronouns\": \"1-3 sentences: who is who and how "
    "they address each other in Vietnamese (xưng hô); for a recap, how the narrator refers to characters\"}.\n"
    "Name rules (most important):\n"
    "- If the work is a known Japanese/Korean/Western franchise retold in Chinese (very common in Chinese recap "
    "videos), use the ORIGINAL names and terms Vietnamese fans use, NOT a Sino-Vietnamese reading of the Chinese "
    "transliteration. E.g. 路飞 -> Luffy, 鸣人 -> Naruto, 佐助 -> Sasuke, 炭治郎 -> Tanjiro, 五条悟 -> Gojo Satoru.\n"
    "- Chinese-origin works (donghua, xianxia, Chinese dramas/novels): Sino-Vietnamese (Hán-Việt) reading "
    "(e.g. 林动 -> Lâm Động, 萧炎 -> Tiêu Viêm, 斗气 -> đấu khí).\n"
    "- Korean/Japanese names -> common Vietnamese spelling (김민준 -> Kim Min Jun, 田中 -> Tanaka). "
    "Western names unchanged.\n"
    "- Include special terms of the work (powers, races, ranks, places) with their usual Vietnamese fan terms.\n"
    "- If unsure of a name, leave it out rather than guess. At most 50 entries.")

SYSTEM = (
    "You are an expert Vietnamese subtitle translator and dubbing adapter. Translate every numbered line into "
    "standard, fluent, natural Vietnamese with full diacritics.\n"
    "Rules:\n"
    "- Translate meaning, tone and emotion, not word by word; adapt idioms and jokes so Vietnamese viewers get them.\n"
    "- Use the given names and pronouns (xưng hô) consistently.\n"
    "- Each line must be speakable within its time slot: stay within its max characters. Be concise, drop filler.\n"
    "- Keep one Vietnamese line per id. Never merge, split, skip or add ids. Do not translate the id numbers.\n"
    "- Output only Vietnamese text: no notes, no romanization, no original script, no quotes around lines.\n"
    "- Sound effects or music lines (♪, [laughs]) -> empty string.\n"
    "Reply ONLY with JSON: {\"lines\": {\"<id>\": \"<Vietnamese>\", ...}}")

SHORTEN_SYSTEM = (
    "You shorten Vietnamese dubbing lines so a voice actor can say them in the given time. Keep the key meaning, "
    "names and tone; natural Vietnamese with full diacritics; drop filler words, merge clauses, use shorter "
    "synonyms. Each line MUST be at most its max characters. Reply ONLY with JSON: "
    "{\"lines\": {\"<id>\": \"<shorter Vietnamese>\"}}")
SHORTEN_STRICT = ("\nSTRICT: these lines were already shortened once and are STILL too long. Cut harder: keep only "
                  "the essential meaning in as few words as possible. Never exceed max characters.")

_FOREIGN = re.compile(r"[぀-ヿ㐀-鿿가-힯฀-๿Ѐ-ӿ]")


def max_chars(line: dict, nxt: dict | None) -> int:
    """Số ký tự tối đa để đọc kịp trong khoảng từ đầu câu tới đầu câu sau (hoặc hết câu + 1 giây)."""
    slot = (nxt["start"] if nxt else line["end"] + 1.0) - line["start"]
    slot = max(line["end"] - line["start"], min(slot, line["end"] - line["start"] + 1.5))
    return max(8, int(slot * CPS))


def speak_seconds(text: str) -> float:
    return len(text or "") / CPS


def parse_glossary(text: str) -> dict:
    out = {}
    for ln in (text or "").splitlines():
        if "=" in ln:
            a, b = ln.split("=", 1)
            if a.strip() and b.strip():
                out[a.strip()] = b.strip()
    return out


def _brief_text(brief: dict, settings: Settings) -> str:
    opts = settings.section("translate")
    style = STYLES.get(opts.get("style", "natural"), STYLES["natural"])[1]
    names = {**(brief.get("names") or {}), **parse_glossary(opts.get("glossary", ""))}  # tên người dùng nhập được ưu tiên
    parts = [f"STYLE: {style}"]
    if brief.get("title"):
        parts.append(f"VIDEO TITLE: {brief['title']}")
    if brief.get("work"):
        parts.append(f"WORK: {brief['work']}")
    if brief.get("narration"):
        parts.append("FORMAT: narrator recap - keep the storyteller voice (third person: 'Ichigo đẩy cửa...'), "
                     "lines in quotes are characters speaking")
    if brief.get("genre"):
        parts.append(f"GENRE: {brief['genre']}")
    if opts.get("context"):
        parts.append(f"CONTEXT FROM USER: {opts['context']}")
    if opts.get("safe"):
        parts.append("PLATFORM SAFETY (TikTok/YouTube): soften profanity and slurs, avoid graphic gore/sexual "
                     "wording, no drug/weapon/gambling promotion, no brand names, prices, links or calls to buy/sell; "
                     "keep the story meaning with milder Vietnamese words")
    if brief.get("pronouns"):
        parts.append(f"PRONOUNS: {brief['pronouns']}")
    if names:
        parts.append("NAMES/TERMS (always use these):\n" + "\n".join(f"{k} = {v}" for k, v in list(names.items())[:80]))
    return "\n".join(parts)


def source_lang(lines: list[dict]) -> str:
    """Đoán chữ viết của lời gốc: zh / ja / ko / other."""
    t = "".join(x.get("text", "") for x in lines[:200])
    kana = len(re.findall(r"[぀-ヿ]", t))
    han = len(re.findall(r"[㐀-鿿]", t))
    hangul = len(re.findall(r"[가-힯]", t))
    n = max(1, len(re.sub(r"\s", "", t)))
    if hangul / n > 0.2:
        return "ko"
    if kana / n > 0.05:
        return "ja"
    if han / n > 0.2:
        return "zh"
    return "other"


def make_brief(lines: list[dict], settings: Settings, log, cancel, title: str = "") -> dict:
    text = "\n".join(x["text"] for x in lines)
    limit = 12000 if (hybrid.ai_chain(settings) or ["ollama"])[0] == "ollama" else 60000
    if len(text) > limit:  # lấy đều đầu - giữa - cuối
        k = limit // 3
        mid = len(text) // 2
        text = text[:k] + "\n...\n" + text[mid - k // 2: mid + k // 2] + "\n...\n" + text[-k:]
    try:
        user = (f"VIDEO TITLE: {title}\n\nTRANSCRIPT:\n{text}" if title else text)
        d = extract_json(chat(settings, GLOSSARY_SYSTEM, user, json_mode=True, max_tokens=3000, log=log,
                              cancel=cancel))
    except Cancelled:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"Không lập được bảng tên riêng ({e}) - vẫn dịch tiếp.", "warn")
        return {"title": title[:200]}
    names = d.get("names") if isinstance(d.get("names"), dict) else {}
    brief = {"title": title[:200], "work": str(d.get("work") or "")[:120],
             "narration": d.get("narration") in (True, "true", "yes", 1),
             "genre": str(d.get("genre") or "")[:80], "pronouns": str(d.get("pronouns") or "")[:600],
             "names": {str(k): str(v) for k, v in names.items() if str(k).strip() and str(v).strip()}}
    if brief["work"]:
        log(f"AI nhận ra phim: {brief['work']}")
    if brief["names"]:
        log("Tên riêng: " + ", ".join(f"{k} → {v}" for k, v in list(brief["names"].items())[:8])
            + (" ..." if len(brief["names"]) > 8 else ""))
    return brief


def _lines_block(lines: list[dict], idx: list[int]) -> str:
    out = []
    for i in idx:
        ln = lines[i]
        out.append(f"{i + 1} | {ln['end'] - ln['start']:.1f}s | max {ln['_max']} chars | {ln['text']}")
    return "\n".join(out)


def _ask(settings, system, user, ids, log, cancel) -> dict[int, str]:
    raw = chat(settings, system, user, json_mode=True, max_tokens=min(16000, 400 + 120 * len(ids)), log=log,
               cancel=cancel)
    d = extract_json(raw)
    got = d.get("lines", d) if isinstance(d, dict) else {}
    out = {}
    if isinstance(got, list):  # vài model trả về danh sách
        got = {str(x.get("id")): x.get("vi") or x.get("text") for x in got if isinstance(x, dict)}
    for k, v in (got or {}).items():
        m = re.match(r"\d+", str(k))
        if m and isinstance(v, str):
            out[int(m.group(0)) - 1] = " ".join(v.split()).strip().strip('"“”')
    return out


def _bad(src: str, vi: str | None) -> bool:
    if vi is None:
        return True
    if not vi:  # để trống chỉ hợp lệ với tiếng động / nhạc: [cười], (music), ♪...
        t = src.strip()
        return not (re.fullmatch(r"[\[(（【♪♫].*", t) or not re.search(r"\w", t))
    return bool(_FOREIGN.search(vi)) or (vi.strip().lower() == src.strip().lower() and len(src) > 3)


def translate(lines: list[dict], settings: Settings, log, progress, cancel, brief: dict | None = None,
              title: str = "", on_brief=None) -> list[dict]:
    """lines: [{start, end, text}] -> [{start, end, text, vi}]"""
    if not lines:
        return []
    chain = hybrid.ai_chain(settings, log)
    if not chain:
        raise RuntimeError("Không có AI nào để dịch: mở Ollama (AI trên máy) hoặc nhập API key trong ⚙️ Cài đặt.")
    log("AI dịch: " + " → ".join(PROVIDERS[p]["name"].split(" (")[0].split(" - ")[0] for p in chain))
    lang = source_lang(lines)
    ai.USED.clear()
    ai.OLLAMA_OVERRIDE = ai.better_local_model(settings, lang, log) if "ollama" in chain else None
    try:
        out = _translate(lines, settings, log, progress, cancel, brief, title, chain, on_brief)
    finally:
        ai.OLLAMA_OVERRIDE = None
    if ai.USED.get("ollama") and (lang in ("zh", "ja", "ko") or len(chain) > 1):
        online = [p for p in chain if p != "ollama"]
        why = (f"AI online ({', '.join(PROVIDERS[p]['name'].split(' (')[0] for p in online)}) bị lỗi - xem dòng 🔀 ở trên"
               if online else "chưa nhập key AI online nào")
        log(f"⚠ Bản dịch này do AI trên máy làm ({why}). AI trên máy yếu hơn nhiều, dễ dịch sai nội dung và tên "
            "nhân vật (nhất là phim Trung/Nhật/Hàn). Để dịch chuẩn: nhập key DeepSeek hoặc Gemini/Groq (miễn phí) "
            "trong ⚙️ Cài đặt rồi bấm 🌐 AI dịch lại.", "warn")
    return out


def _translate(lines, settings, log, progress, cancel, brief, title, chain, on_brief=None) -> list[dict]:
    lines = [dict(x) for x in lines]
    for i, ln in enumerate(lines):
        ln["_max"] = max_chars(ln, lines[i + 1] if i + 1 < len(lines) else None)
    if brief is None:
        progress(0.03, "AI đọc lướt video: tên riêng, xưng hô")
        brief = make_brief(lines, settings, log, cancel, title=title)
        if on_brief:
            on_brief(brief)
    head = _brief_text(brief, settings)
    local = chain[0] == "ollama"
    size = 25 if local else BATCH
    batches = [list(range(a, min(len(lines), a + size))) for a in range(0, len(lines), size)]
    result: dict[int, str] = {}
    done = [0]

    def run_batch(idx: list[int]) -> dict[int, str]:
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        prev = [lines[j] for j in range(max(0, idx[0] - 4), idx[0])]
        ctx = ("PREVIOUS LINES (context only, do not translate):\n" + "\n".join(p["text"] for p in prev) + "\n\n") \
            if prev else ""
        user = f"{head}\n\n{ctx}LINES TO TRANSLATE (id | duration | max chars | text):\n{_lines_block(lines, idx)}"
        try:
            got = _ask(settings, SYSTEM, user, idx, log, cancel)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"Lô câu {idx[0] + 1}-{idx[-1] + 1} lỗi ({e}) - sẽ dịch lại.", "warn")
            got = {}
        done[0] += 1
        progress(0.08 + 0.8 * done[0] / len(batches), f"Dịch {min(len(lines), done[0] * size)}/{len(lines)} câu")
        return {i: v for i, v in got.items() if i in idx}

    with ThreadPoolExecutor(max_workers=1 if local else 4) as ex:
        for got in ex.map(run_batch, batches):
            result.update(got)
    # câu thiếu / chưa dịch -> dịch lại theo lô nhỏ
    for rnd in range(2):
        miss = [i for i in range(len(lines)) if _bad(lines[i]["text"], result.get(i))]
        if not miss:
            break
        log(f"Dịch lại {len(miss)} câu bị sót (lần {rnd + 1})...", "warn")
        for a in range(0, len(miss), 15):
            idx = miss[a:a + 15]
            try:
                user = (f"{head}\n\nLINES TO TRANSLATE (id | duration | max chars | text):\n"
                        f"{_lines_block(lines, idx)}")
                result.update({i: v for i, v in _ask(settings, SYSTEM, user, idx, log, cancel).items() if i in idx})
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Dịch lại lỗi ({e}).", "warn")
    # tối ưu cho thuyết minh: câu đọc quá nhanh -> rút gọn, ĐO LẠI, còn dài thì rút chặt hơn (tối đa 3 vòng)
    if settings.get("translate", "shorten", True):
        _shorten_loop(lines, result, settings, log, progress, cancel, local)
    out = []
    left = 0
    for i, ln in enumerate(lines):
        vi = result.get(i)
        if vi is None:
            left += 1
            vi = ""
        out.append({"start": ln["start"], "end": ln["end"], "text": ln["text"], "vi": vi})
    if left:
        log(f"Còn {left} câu chưa dịch được - sửa tay trong bảng rồi xuất lại.", "warn")
    progress(1.0, "Đã dịch xong")
    return out


def too_fast(line: dict, vi: str | None) -> bool:
    """Câu dịch đọc nhanh hơn MAX_CPS (quá tải cho giọng đọc)."""
    return bool(vi) and len(vi) > line["_max"] * MAX_CPS / CPS


def _shorten_loop(lines, result, settings, log, progress, cancel, local, rounds: int = 3) -> None:
    for rnd in range(rounds):
        long_ = [i for i in range(len(lines)) if too_fast(lines[i], result.get(i))]
        if not long_:
            if rnd:
                log("✅ Tối ưu thuyết minh xong: mọi câu đều đọc kịp thời gian.")
            return
        log(f"⚡ Tối ưu thuyết minh: {len(long_)} câu đọc quá nhanh (>{MAX_CPS:.0f} ký tự/giây) → AI rút gọn "
            f"(vòng {rnd + 1}/{rounds}{', yêu cầu chặt hơn' if rnd else ''})...")
        progress(0.9 + 0.03 * rnd, f"Rút gọn {len(long_)} câu cho kịp thời gian (vòng {rnd + 1})")
        tighten = 1.0 - 0.1 * rnd  # vòng sau đặt giới hạn thấp hơn để AI cắt mạnh tay hơn
        system = SHORTEN_SYSTEM + (SHORTEN_STRICT if rnd else "")
        groups = [long_[a:a + 30] for a in range(0, len(long_), 30)]

        def run(idx):
            body = "\n".join(f"{i + 1} | max {max(6, int(lines[i]['_max'] * tighten))} chars | "
                             f"original: {lines[i]['text']} | now: {result[i]}" for i in idx)
            try:
                return _ask(settings, system, body, idx, log, cancel)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Rút gọn lỗi ({e}) - giữ bản dịch hiện tại.", "warn")
                return {}

        with ThreadPoolExecutor(max_workers=1 if local else 4) as ex:
            for idx, got in zip(groups, ex.map(run, groups)):
                for i, v in got.items():
                    if i in idx and v and len(v) < len(result[i]) and not _FOREIGN.search(v):
                        result[i] = v
    left = sum(too_fast(lines[i], result.get(i)) for i in range(len(lines)))
    if left:
        log(f"Còn {left} câu hơi dài - giọng đọc sẽ tự nói nhanh lên một chút (tối đa ×1.35).", "warn")


def to_srt(lines: list[dict], key: str = "vi") -> str:
    def ts(t):
        ms = int(round(max(0.0, t) * 1000))
        return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"
    rows = [x for x in lines if (x.get(key) or "").strip()]
    return "".join(f"{i + 1}\n{ts(x['start'])} --> {ts(x['end'])}\n{x[key].strip()}\n\n" for i, x in enumerate(rows))


def save_json(path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
