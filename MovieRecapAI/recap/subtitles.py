"""Đọc phụ đề SRT/VTT/ASS, chia câu và xuất file phụ đề SRT/ASS."""
from __future__ import annotations

import html
import re
from pathlib import Path

from .ffmpeg_utils import fmt_ts

_TS = r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})"


def _ts_to_sec(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\{[^}]*\}", "", text)
    text = text.replace("\\N", " ").replace("\\n", " ")
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def parse_subtitle_file(path: str | Path) -> list[dict]:
    path = Path(path)
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1258", "cp1252", "latin-1"):
        try:
            txt = raw.decode(enc)
            if "\x00" in txt and enc != "utf-16":
                continue
            break
        except UnicodeDecodeError:
            continue
    if path.suffix.lower() in (".ass", ".ssa"):
        return _parse_ass(txt)
    return _parse_srt_vtt(txt)


def _parse_srt_vtt(txt: str) -> list[dict]:
    segs = []
    blocks = re.split(r"\r?\n\s*\r?\n", txt.replace("\r\n", "\n"))
    pat = re.compile(_TS.replace(r"(\d+):", r"(?:(\d+):)?", 1) + r"\s*-->\s*" + _TS.replace(r"(\d+):", r"(?:(\d+):)?", 1))
    for b in blocks:
        lines = [ln for ln in b.strip().split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            m = pat.search(ln)
            if m:
                g = m.groups()
                st = _ts_to_sec(g[0] or 0, g[1], g[2], g[3])
                en = _ts_to_sec(g[4] or 0, g[5], g[6], g[7])
                text = _clean(" ".join(lines[i + 1:]))
                if text:
                    segs.append({"start": st, "end": en, "text": text})
                break
    segs.sort(key=lambda s: s["start"])
    return _dedupe(segs)


def _parse_ass(txt: str) -> list[dict]:
    segs = []
    fmt = None
    for ln in txt.splitlines():
        if ln.startswith("Format:") and fmt is None and "Start" in ln:
            fmt = [x.strip().lower() for x in ln[7:].split(",")]
        if ln.startswith("Dialogue:") and fmt:
            parts = ln[9:].split(",", len(fmt) - 1)
            d = dict(zip(fmt, parts))
            try:
                st = _ass_ts(d["start"])
                en = _ass_ts(d["end"])
            except Exception:
                continue
            text = _clean(d.get("text", ""))
            if text:
                segs.append({"start": st, "end": en, "text": text})
    segs.sort(key=lambda s: s["start"])
    return _dedupe(segs)


def _ass_ts(s: str) -> float:
    h, m, rest = s.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def _dedupe(segs: list[dict]) -> list[dict]:
    """Phụ đề auto (YouTube) hay lặp dòng - gộp các dòng trùng liên tiếp."""
    out: list[dict] = []
    for s in segs:
        if out and s["text"] == out[-1]["text"]:
            out[-1]["end"] = max(out[-1]["end"], s["end"])
            continue
        if out and out[-1]["text"] and s["text"].startswith(out[-1]["text"]) and s["start"] - out[-1]["end"] < 0.5:
            out[-1]["text"] = s["text"]
            out[-1]["end"] = s["end"]
            continue
        out.append(dict(s))
    return out


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[\.\!\?…。！？;])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Chia đoạn văn thành các cụm ngắn <= max_chars (ưu tiên ngắt ở dấu câu)."""
    out: list[str] = []
    for sent in split_sentences(text):
        while len(sent) > max_chars:
            cut = max(sent.rfind(",", 0, max_chars), sent.rfind(" ", 0, max_chars))
            if cut <= max_chars // 3:
                cut = max_chars
            out.append(sent[:cut + 1].strip().rstrip(","))
            sent = sent[cut + 1:].strip()
        if sent:
            out.append(sent)
    return out


def wrap_line(text: str, max_chars: int) -> str:
    """Ngắt thành tối đa 2 dòng cân đối."""
    if len(text) <= max_chars:
        return text
    words = text.split(" ")
    best, best_diff = text, 10 ** 9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        diff = abs(len(a) - len(b))
        if diff < best_diff:
            best, best_diff = a + "\n" + b, diff
    return best


def timed_chunks(text: str, duration: float, max_chars: int = 42, offset: float = 0.0) -> list[dict]:
    """Rải các cụm phụ đề theo thời lượng giọng đọc (tỷ lệ theo số ký tự)."""
    chunks = chunk_text(text, max_chars * 2)
    if not chunks or duration <= 0:
        return []
    weights = [max(4, len(c)) for c in chunks]
    total = float(sum(weights))
    t = offset
    out = []
    for c, w in zip(chunks, weights):
        d = duration * w / total
        out.append({"start": t, "end": t + d, "text": wrap_line(c, max_chars)})
        t += d
    return out


# ---------------------------------------------------------------- Xuất file
def _srt_ts(sec: float) -> str:
    sec = max(0.0, sec)
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(items: list[dict], path: str | Path) -> None:
    lines = []
    for i, it in enumerate(items, 1):
        lines += [str(i), f"{_srt_ts(it['start'])} --> {_srt_ts(it['end'])}", it["text"], ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    h = (hex_color or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ass_ts_out(sec: float) -> str:
    sec = max(0.0, sec)
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def write_ass(items: list[dict], path: str | Path, width: int, height: int, style: dict,
              title: dict | None = None) -> None:
    """style: font, size (tính theo chiều cao 1080), color, outline_color, outline, position, bold."""
    scale = min(width, height) / 1080.0
    size = int(style.get("size", 52) * scale)
    pos = style.get("position", "bottom")
    align = {"bottom": 2, "middle": 5, "top": 8}.get(pos, 2)
    margin_v = int((70 if pos != "middle" else 0) * scale)
    if width < height:  # video dọc: nhấc phụ đề lên tránh nút của TikTok/Shorts
        margin_v = int(height * 0.18) if pos == "bottom" else margin_v
    bold = -1 if style.get("bold", True) else 0
    outline = max(0, float(style.get("outline", 3))) * scale
    font = style.get("font") or "Arial"
    primary = _ass_color(style.get("color", "#FFFFFF"))
    outline_c = _ass_color(style.get("outline_color", "#000000"))
    back = _ass_color("#000000", 0x80)
    tsize = int(size * 1.35)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{primary},{primary},{outline_c},{back},{bold},0,0,0,100,100,0,0,1,{outline:.1f},{1.5 * scale:.1f},{align},{int(60 * scale)},{int(60 * scale)},{margin_v},1
Style: Title,{font},{tsize},&H0000E5FF,&H0000E5FF,{outline_c},{back},-1,0,0,0,100,100,0,0,1,{outline * 1.4:.1f},{2 * scale:.1f},8,{int(60 * scale)},{int(60 * scale)},{int(height * 0.08)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    if title and title.get("text"):
        fade = "{\\fad(300,400)}"
        events.append(f"Dialogue: 1,{_ass_ts_out(title.get('start', 0))},{_ass_ts_out(title['end'])},Title,,0,0,0,,"
                      f"{fade}{_ass_escape(title['text'])}")
    for it in items:
        events.append(f"Dialogue: 0,{_ass_ts_out(it['start'])},{_ass_ts_out(it['end'])},Default,,0,0,0,,"
                      f"{_ass_escape(it['text'])}")
    Path(path).write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def transcript_to_text(segments: list[dict], merge_seconds: float = 8.0) -> str:
    """Gộp các câu thoại ngắn thành dòng có mốc thời gian để gửi cho AI."""
    lines = []
    cur_start, cur_end, buf = None, 0.0, []
    for s in segments:
        if cur_start is None:
            cur_start = s["start"]
        buf.append(s["text"])
        cur_end = s["end"]
        if cur_end - cur_start >= merge_seconds:
            lines.append(f"[{fmt_ts(cur_start)} - {fmt_ts(cur_end)}] {' '.join(buf)}")
            cur_start, buf = None, []
    if buf and cur_start is not None:
        lines.append(f"[{fmt_ts(cur_start)} - {fmt_ts(cur_end)}] {' '.join(buf)}")
    return "\n".join(lines)
