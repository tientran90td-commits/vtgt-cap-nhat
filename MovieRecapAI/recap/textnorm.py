"""Chuẩn hóa văn bản trước khi đọc để giọng AI phát âm chuẩn.

Ba lớp xử lý (theo thứ tự):
  1. Từ điển phát âm của người dùng (tên riêng, từ nước ngoài, từ hay đọc sai...).
  2. Chuẩn hóa tự động: số, số thập phân, phần trăm, tiền tệ, ngày tháng, giờ, khoảng,
     đơn vị đo, số La Mã, ký hiệu, chữ viết tắt phổ biến.
  3. (tùy chọn) AI soát phát âm: nhờ LLM viết lại câu cho "dễ đọc" - đọc số thành chữ,
     phiên âm tên nước ngoài... nhưng giữ nguyên nội dung.

Phụ đề vẫn dùng câu gốc (vd "25%"), chỉ giọng đọc dùng câu đã chuẩn hóa ("hai mươi lăm phần trăm").
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config import Settings, app_home

# ============================================================== ĐỌC SỐ TIẾNG VIỆT
_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def _read_triple(n: int, full: bool) -> str:
    """Đọc số 0..999. full=True: luôn đọc hàng trăm (vd 'không trăm linh năm')."""
    h, t, u = n // 100, (n // 10) % 10, n % 10
    out: list[str] = []
    if h or full:
        out += [_DIGITS[h], "trăm"]
    if t == 0:
        if u:
            if h or full:
                out.append("linh")
            out.append(_DIGITS[u])
    elif t == 1:
        out.append("mười")
        if u == 5:
            out.append("lăm")
        elif u:
            out.append(_DIGITS[u])
    else:
        out += [_DIGITS[t], "mươi"]
        if u == 1:
            out.append("mốt")
        elif u == 4:
            out.append("tư")
        elif u == 5:
            out.append("lăm")
        elif u:
            out.append(_DIGITS[u])
    return " ".join(out)


def read_number_vi(n: int) -> str:
    if n < 0:
        return "âm " + read_number_vi(-n)
    if n < 10:
        return _DIGITS[n]
    if n >= 10 ** 18:
        return " ".join(_DIGITS[int(c)] for c in str(n))
    units = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ", "triệu tỷ"]
    groups = []
    while n:
        groups.append(n % 1000)
        n //= 1000
    parts = []
    top = len(groups) - 1
    for i in range(top, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        txt = _read_triple(g, full=(i != top))
        parts.append((txt + " " + units[i]).strip())
    return " ".join(parts)


def read_digits_vi(s: str) -> str:
    return " ".join(_DIGITS[int(c)] for c in s if c.isdigit())


def read_decimal_vi(int_part: str, frac: str) -> str:
    lead = read_number_vi(int(int_part or "0"))
    if frac.startswith("0") or len(frac) > 3:
        return f"{lead} phẩy {read_digits_vi(frac)}"
    return f"{lead} phẩy {read_number_vi(int(frac))}"


def _ordinal_vi(n: int) -> str:
    return {1: "nhất", 4: "tư"}.get(n, read_number_vi(n))


def _month_vi(m: int) -> str:
    return {4: "tư"}.get(m, read_number_vi(m))


# ============================================================== TỪ VIẾT TẮT & ĐƠN VỊ
ABBREV_VI: dict[str, str] = {
    "TP.HCM": "thành phố Hồ Chí Minh", "TP HCM": "thành phố Hồ Chí Minh", "TPHCM": "thành phố Hồ Chí Minh",
    "HCM": "Hồ Chí Minh", "TP.": "thành phố", "Tp.": "thành phố",
    "VN": "Việt Nam", "USD": "đô la Mỹ", "VND": "đồng", "VNĐ": "đồng", "EUR": "ơ rô",
    "Mr.": "mít-tơ", "Mrs.": "mít-sơ", "Ms.": "mít", "Dr.": "tiến sĩ", "GS.": "giáo sư", "PGS.": "phó giáo sư",
    "TS.": "tiến sĩ", "ThS.": "thạc sĩ", "BS.": "bác sĩ",
    "v.v.": "vân vân", "v.v": "vân vân", "vs": "đối đầu", "VS": "đối đầu", "vs.": "đối đầu",
    "CEO": "xi i ô", "FBI": "ép bi ai", "CIA": "xi ai ây", "KGB": "ca giê bê", "NASA": "na-sa",
    "AI": "ây ai", "UFO": "iu ép ô", "DNA": "đi en ây", "ADN": "a đê nờ", "GPS": "gi pi ét",
    "TV": "ti vi", "MC": "em xi", "VIP": "víp", "OK": "ô kê", "ok": "ô kê", "Ok": "ô kê",
    "SOS": "ét ô ét", "iPhone": "ai phôn", "Facebook": "phây-búc", "YouTube": "diu-túp", "TikTok": "tích-tóc",
    "Google": "gu-gồ", "Netflix": "nét-phờ-lích", "Marvel": "ma-vồ", "DC": "đi xi",
    "km/h": "ki lô mét trên giờ", "m/s": "mét trên giây",
}

UNITS_VI: dict[str, str] = {
    "km/h": "ki lô mét trên giờ", "km": "ki lô mét", "cm": "xen ti mét", "mm": "mi li mét", "m2": "mét vuông",
    "m²": "mét vuông", "m3": "mét khối", "m": "mét", "kg": "ki lô gam", "g": "gam", "mg": "mi li gam",
    "tấn": "tấn", "l": "lít", "ml": "mi li lít", "°C": "độ C", "°F": "độ F", "°": "độ", "h": "giờ",
    "ph": "phút", "s": "giây", "GB": "ghi ga bai", "MB": "mê ga bai", "TB": "tê ra bai", "Hz": "héc",
    "kW": "ki lô oát", "W": "oát", "V": "vôn", "mph": "dặm trên giờ", "ft": "phít", "inch": "inh",
}

CURRENCY_PREFIX = {"$": "đô la", "€": "ơ rô", "£": "bảng Anh", "¥": "yên", "₩": "won", "₫": "đồng"}
CURRENCY_SUFFIX = {"đ": "đồng", "₫": "đồng", "đồng": "đồng", "vnd": "đồng", "vnđ": "đồng", "usd": "đô la Mỹ",
                   "$": "đô la", "€": "ơ rô", "k": "nghìn", "tr": "triệu", "củ": "triệu"}

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(s: str) -> int | None:
    total, prev = 0, 0
    for ch in reversed(s):
        v = _ROMAN.get(ch)
        if v is None:
            return None
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total if 0 < total < 4000 else None


# ============================================================== CHUẨN HÓA TIẾNG VIỆT
def _num(s: str) -> int:
    return int(re.sub(r"[.,\s]", "", s))


def _read_amount(s: str) -> str:
    """'1.500.000' -> số nguyên; '3,5' / '3.5' -> thập phân."""
    s = s.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        return read_number_vi(_num(s))
    if re.fullmatch(r"\d{1,3}(,\d{3}){2,}", s):
        return read_number_vi(_num(s))
    m = re.fullmatch(r"(\d+)[.,](\d+)", s)
    if m:
        return read_decimal_vi(m.group(1), m.group(2))
    if len(s) > 1 and s.startswith("0"):  # số điện thoại, mã số: đọc từng chữ số
        return read_digits_vi(s)
    return read_number_vi(int(s))


_AMOUNT = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"


def normalize_vi(text: str) -> str:
    t = " " + text + " "
    # ngày tháng năm: 12/05/2023, 12-5-2023 (không lặp chữ "ngày" nếu câu đã có)
    t = re.sub(r"(?:\b([Nn]gày|[Mm]ùng)\s+)?(?<![\d/])(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?![\d/])",
               lambda m: f"{m[1] or 'ngày'} {read_number_vi(int(m[2]))} tháng {_month_vi(int(m[3]))} "
                         f"năm {read_number_vi(int(m[4]))}"
               if 1 <= int(m[2]) <= 31 and 1 <= int(m[3]) <= 12 else m[0], t)
    # tháng/năm: 05/2023
    t = re.sub(r"(?<![\d/])(\d{1,2})/(\d{4})(?![\d/])",
               lambda m: f"tháng {_month_vi(int(m[1]))} năm {read_number_vi(int(m[2]))}"
               if 1 <= int(m[1]) <= 12 else m[0], t)
    # ngày/tháng: 30/4
    t = re.sub(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])",
               lambda m: f"{read_number_vi(int(m[1]))} tháng {_month_vi(int(m[2]))}"
               if 1 <= int(m[1]) <= 31 and 1 <= int(m[2]) <= 12 else m[0], t)
    # "tháng 4", "thứ 2", "hạng 1"
    t = re.sub(r"\b([Tt]háng)\s+(\d{1,2})\b", lambda m: f"{m[1]} {_month_vi(int(m[2]))}", t)
    t = re.sub(r"\b([Tt]hứ|[Hh]ạng|[Ll]ần thứ)\s+(\d{1,3})\b", lambda m: f"{m[1]} {_ordinal_vi(int(m[2]))}", t)
    # giờ: 10h30, 10:30, 10h
    t = re.sub(r"(?<![\d:])(\d{1,2})(?:h|g|:)(\d{2})(?:p|ph|')?(?![\d:])",
               lambda m: f"{read_number_vi(int(m[1]))} giờ {read_number_vi(int(m[2]))} phút"
               if int(m[1]) < 24 and int(m[2]) < 60 else m[0], t)
    t = re.sub(r"(?<![\w])(\d{1,2})\s?h(?![\w])", lambda m: f"{read_number_vi(int(m[1]))} giờ", t)
    # số La Mã sau các từ chỉ thứ tự
    t = re.sub(r"\b([Pp]hần|[Tt]ập|[Cc]hương|[Hh]ồi|[Tt]hế kỷ|[Tt]hế chiến|[Ss]ố|[Kk]hóa)\s+([IVXLCDM]{1,6})\b",
               lambda m: f"{m[1]} {read_number_vi(_roman_to_int(m[2]))}" if _roman_to_int(m[2]) else m[0], t)
    # tiền tệ đứng trước: $5, $1.5 triệu
    t = re.sub(r"([$€£¥₩])\s?(" + _AMOUNT + r")(\s?(?:nghìn|ngàn|triệu|tỷ|k))?",
               lambda m: f"{_read_amount(m[2])}{' ' + m[3].strip() if m[3] else ''} {CURRENCY_PREFIX[m[1]]}", t)
    # tiền tệ đứng sau: 5.000đ, 50k, 2tr, 100 USD
    t = re.sub(r"(?<![\w.,])(" + _AMOUNT + r")\s?(đồng|vnđ|vnd|đ|₫|usd|\$|€|k|tr|củ)(?![\wà-ỹ])",
               lambda m: f"{_read_amount(m[1])} {CURRENCY_SUFFIX[m[2].lower()]}", t, flags=re.IGNORECASE)
    # phần trăm
    t = re.sub(r"(" + _AMOUNT + r")\s?%", lambda m: f"{_read_amount(m[1])} phần trăm", t)
    # tỷ số: thắng 3-1
    t = re.sub(r"\b([Tt]hắng|[Tt]hua|[Hh]òa|[Hh]oà|[Tt]ỷ số|[Tt]ỉ số)\s+(\d{1,2})\s?[-–:]\s?(\d{1,2})(?!\d)",
               lambda m: f"{m[1]} {read_number_vi(int(m[2]))} {read_number_vi(int(m[3]))}", t)
    # khoảng: 2010-2015, 5-7 người
    t = re.sub(r"(?<![\d/.,])(\d+)\s?[-–]\s?(\d+)(?![\d/])",
               lambda m: f"{read_number_vi(int(m[1]))} đến {read_number_vi(int(m[2]))}", t)
    # số âm (-5°C)
    t = re.sub(r"(?<![\w\d])-(\d+(?:[.,]\d+)?)", lambda m: "âm " + m[1], t)
    # đơn vị đo sau số
    units = sorted(UNITS_VI, key=len, reverse=True)
    unit_re = "|".join(re.escape(u) for u in units)
    t = re.sub(r"(" + _AMOUNT + r")\s?(" + unit_re + r")(?![\wà-ỹ/])",
               lambda m: f"{_read_amount(m[1])} {UNITS_VI[m[2]]}", t)
    # mọi số còn lại
    t = re.sub(r"(?<![\w])(" + _AMOUNT + r")(?![\w])", lambda m: _read_amount(m[1]), t)
    t = re.sub(r"(\d+)", lambda m: " " + (read_number_vi(int(m[1])) if len(m[1]) < 16 else read_digits_vi(m[1])) + " ",
               t)
    # ký hiệu
    t = t.replace("&", " và ").replace("+", " cộng ").replace("=", " bằng ").replace("@", " a còng ")
    t = t.replace("…", "...").replace("–", ", ").replace("—", ", ")
    t = re.sub(r"[\"“”«»*_#~^|<>\[\]{}]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def normalize_generic(text: str, lang_code: str) -> str:
    """Ngôn ngữ khác: dùng num2words nếu có (en, fr, de, es, ja, ko, ...)."""
    try:
        from num2words import num2words
    except ImportError:
        return text
    lang = {"zh-cn": "zh", "en": "en"}.get(lang_code, lang_code)

    def conv(m):
        s = m.group(0).replace(",", "")
        try:
            return num2words(float(s) if "." in s else int(s), lang=lang)
        except Exception:
            return m.group(0)
    text = re.sub(r"(\d+)\s?%", lambda m: m[1] + (" percent" if lang == "en" else " %"), text)
    return re.sub(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", conv, text)


# ============================================================== TỪ ĐIỂN PHÁT ÂM
def dict_path() -> Path:
    return app_home() / "pronunciation.json"


DEFAULT_DICT = [
    {"from": "Batman", "to": "Bát-men"}, {"from": "Superman", "to": "Siêu-pơ-men"},
    {"from": "Spider-Man", "to": "Xpai-đơ-men"}, {"from": "Iron Man", "to": "Ai-ơn Men"},
    {"from": "Harry Potter", "to": "Ha-ri Pót-tơ"}, {"from": "John", "to": "Giôn"},
    {"from": "Joker", "to": "Giô-cơ"}, {"from": "Thanos", "to": "Tha-nốt"},
]


def load_dict() -> list[dict]:
    p = dict_path()
    if p.exists():
        try:
            return [e for e in json.loads(p.read_text(encoding="utf-8")) if e.get("from")]
        except Exception:
            pass
    return list(DEFAULT_DICT)


def save_dict(entries: list[dict]) -> None:
    dict_path().write_text(json.dumps([e for e in entries if e.get("from")], ensure_ascii=False, indent=2),
                           encoding="utf-8")


def apply_dict(text: str, entries: list[dict]) -> str:
    for e in sorted(entries, key=lambda x: len(x.get("from", "")), reverse=True):
        src, dst = e.get("from", "").strip(), e.get("to", "")
        if not src:
            continue
        flags = 0 if e.get("case") else re.IGNORECASE
        text = re.sub(r"(?<![\wÀ-ỹ])" + re.escape(src) + r"(?![\wÀ-ỹ])", lambda _m: dst, text, flags=flags)
    return text


def apply_abbrev(text: str, lang_code: str) -> str:
    if lang_code != "vi":
        return text
    for k in sorted(ABBREV_VI, key=len, reverse=True):
        text = re.sub(r"(?<![\wÀ-ỹ])" + re.escape(k) + r"(?![\wÀ-ỹ])", ABBREV_VI[k], text)
    return text


# ============================================================== TỔNG HỢP
def prepare(text: str, lang_code: str = "vi", normalize: bool = True, entries: list[dict] | None = None) -> str:
    """Văn bản thực sự gửi cho TTS."""
    out = apply_dict(text, entries if entries is not None else load_dict())
    if normalize:
        out = apply_abbrev(out, lang_code)
        out = normalize_vi(out) if lang_code == "vi" else normalize_generic(out, lang_code)
    return out


AI_SYSTEM = """You prepare voice-over text for a text-to-speech engine so that it is pronounced perfectly.
You receive a JSON list of narration lines. Rewrite EACH line into fully speakable {lang}:
- write every number, date, time, money amount, percentage, unit, score and year as words, the way a native
  narrator would read them aloud;
- expand abbreviations and symbols; remove emojis, markdown, brackets and stage directions;
- fix obvious typos and missing diacritics;
{translit}
- do NOT add, remove or reorder information, do NOT summarize, keep the same tone and punctuation for pauses.
Return ONLY JSON: {{"items": ["line 1", "line 2", ...]}} with exactly the same number of items."""

_TRANSLIT = ("- write foreign personal names, place names and brand names as Vietnamese phonetic spelling "
             "(e.g. 'Batman' -> 'Bát-men', 'Joker' -> 'Giô-cơ', 'New York' -> 'Niu-oóc'), except very common ones;")


def ai_speakable(lines: list[str], lang: str, settings: Settings, transliterate: bool = False, log=None,
                 cache_dir: Path | None = None) -> list[str]:
    """Nhờ AI (nhà cung cấp chọn ở bước kịch bản) viết lại các câu cho dễ đọc. Có cache."""
    from .llm import PROVIDERS, chat, extract_json

    pid = settings.get("script", "provider", "gemini")
    model = settings.get("script", "model") or (PROVIDERS.get(pid, {}).get("models") or [""])[0]
    if pid == "none" or not lines:
        return lines
    cache_dir = cache_dir or (app_home() / "cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps([pid, model, lang, transliterate, lines], ensure_ascii=False).encode()).hexdigest()[:16]
    cf = cache_dir / f"ai_pron_{key}.json"
    if cf.exists():
        try:
            return json.loads(cf.read_text(encoding="utf-8"))
        except Exception:
            pass
    sys_prompt = AI_SYSTEM.format(lang=lang, translit=_TRANSLIT if transliterate and lang == "Tiếng Việt" else "")
    out: list[str] = []
    for i in range(0, len(lines), 40):
        batch = lines[i:i + 40]
        try:
            raw = chat(pid, model, sys_prompt, json.dumps({"items": batch}, ensure_ascii=False), settings,
                       json_mode=True, max_tokens=16000, log=log)
            items = extract_json(raw).get("items") or []
            if len(items) != len(batch) or not all(isinstance(x, str) and x.strip() for x in items):
                raise ValueError("số câu trả về không khớp")
            out += [x.strip() for x in items]
        except Exception as e:  # noqa: BLE001
            if log:
                log(f"AI soát phát âm lỗi ({e}) - dùng chuẩn hóa tự động cho nhóm câu này.", level="warn")
            out += batch
    cf.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out
