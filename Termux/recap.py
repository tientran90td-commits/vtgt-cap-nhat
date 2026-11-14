"""Review / tóm tắt phim thành video ngắn (dùng lõi VietDub): lời gốc -> AI viết kịch bản (hook, kể theo trình tự,
đúng tên nhân vật) -> giọng đọc -> dựng từng cảnh (che phụ đề gốc, khung 9:16, phụ đề lời kể, tiêu đề) -> nối lại."""
from __future__ import annotations

import json
import re
import wave
from pathlib import Path

from vietdub import render, voices
from vietdub.ai import extract_json
from vietdub.media import Cancelled, encoder_args, is_android, run

CPS = 14.5  # ký tự tiếng Việt đọc mỗi giây

NAME_RULES = """Quy tắc tên riêng (quan trọng nhất):
- Trước hết tự nhận ra đây là phim / anime / truyện nào (dựa vào TÊN VIDEO, hashtag và lời thoại).
- Anime / truyện Nhật, Hàn, phương Tây được kể lại bằng tiếng Trung (rất hay gặp ở video review Trung Quốc): dùng TÊN GỐC mà fan Việt quen gọi, KHÔNG phiên âm Hán-Việt từ chữ Trung. Ví dụ: 路飞 → Luffy, 鸣人 → Naruto, 佐助 → Sasuke, 炭治郎 → Tanjiro, 五条悟 → Gojo Satoru.
- Phim / truyện gốc Trung Quốc (cổ trang, tiên hiệp, phim Trung): đọc Hán-Việt. Ví dụ: 林动 → Lâm Động, 萧炎 → Tiêu Viêm.
- Tên Hàn / Nhật viết theo cách quen dùng ở Việt Nam. Tên phương Tây giữ nguyên.
- Thuật ngữ riêng của phim (sức mạnh, chủng tộc, cấp bậc, địa danh) dùng đúng từ fan Việt hay dùng."""

STYLES = {
    "hap_dan": "Kể chuyện cuốn hút, kịch tính như kênh review phim triệu view",
    "hai_huoc": "Hài hước, dí dỏm, bình luận vui nhưng vẫn kể đủ cốt truyện",
    "nghiem_tuc": "Nghiêm túc, sâu sắc, phân tích nhân vật và ý nghĩa",
    "co_trang": "Giọng kể cổ trang, kiếm hiệp, tiên hiệp (ta, ngươi, huynh, đệ...)",
}


def fmt(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 3600}:{t // 60 % 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60:02d}:{t % 60:02d}"


def transcript_text(lines: list[dict], limit: int = 60000) -> str:
    """Lời thoại có mốc thời gian; phim dài thì gộp theo khoảng thời gian và cắt bớt cho vừa giới hạn."""
    if not lines:
        return ""
    window = 0.0
    while True:
        buckets: list[list] = []
        for ln in lines:
            if not buckets or ln["start"] - buckets[-1][0] >= window:
                buckets.append([ln["start"], []])
            buckets[-1][1].append(str(ln["text"]).strip())
        cap = max(40, limit // len(buckets) - 10)
        out = "\n".join(f"[{fmt(t)}] {' '.join(ts)[:cap]}" for t, ts in buckets)
        if len(out) <= limit or window >= 640:
            return out[:limit]
        window = 10.0 if window == 0 else window * 2


def prompt(title: str, duration: float, lines: list[dict], target: int, style: str, glossary: str = "") -> str:
    target = max(30, min(target, int(duration * 0.9)))
    n = max(4, min(80, target // 11))
    g = "\n".join(x.strip() for x in (glossary or "").splitlines() if "=" in x)
    return f"""Bạn là biên kịch kênh REVIEW PHIM tiếng Việt trên TikTok / YouTube. Dưới đây là lời thoại (có mốc thời gian) của video "{title}" dài {fmt(duration)}. Hãy viết kịch bản review / tóm tắt bằng tiếng Việt chuẩn, có dấu đầy đủ.

{NAME_RULES}

Yêu cầu kịch bản:
- Văn phong: {STYLES.get(style, STYLES['hap_dan'])}. Ngôi thứ ba, câu ngắn, dễ đọc thành tiếng, không ký hiệu lạ, không emoji, không chú thích.
- Đoạn đầu là câu "hook" gây tò mò. Sau đó kể theo đúng trình tự thời gian, đủ các tình tiết chính, có cao trào và kết thúc.
- Tổng lời kể khoảng {int(target * CPS)} ký tự (đọc khoảng {target // 60} phút {target % 60} giây), chia thành khoảng {n} đoạn, mỗi đoạn 1–3 câu (80–250 ký tự).
- Mỗi đoạn gắn với cảnh minh họa đúng nội dung đó: "start" là số giây trong video (lấy theo mốc thời gian lời thoại). Các đoạn có "start" tăng dần và rải đều từ đầu tới cuối video.
{('Tên riêng BẮT BUỘC dùng:' + chr(10) + g) if g else ''}

Chỉ trả lời JSON, không giải thích:
{{"title": "tiêu đề video review hấp dẫn, tối đa 70 ký tự", "segments": [{{"start": 12.5, "text": "lời kể..."}}]}}

LỜI THOẠI:
{transcript_text(lines)}"""


_FOREIGN = re.compile(r"[぀-ヿ㐀-鿿가-힯฀-๿]")


def parse(text: str, duration: float) -> tuple[str, list[dict]]:
    d = extract_json(text)
    segs = []
    for s in d.get("segments") or []:
        t = str((s or {}).get("text") or "").strip()
        if not t or _FOREIGN.search(t):
            continue
        try:
            start = float(s.get("start") or 0)
        except (TypeError, ValueError):
            start = 0.0
        segs.append({"start": max(0.0, min(start, max(0.0, duration - 1.0))), "text": t})
    if not segs:
        raise ValueError("Kịch bản rỗng")
    segs.sort(key=lambda s: s["start"])
    return str(d.get("title") or "").strip(), segs


def wav_seconds(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _ass(path: Path, W: int, H: int, cues: list[tuple[float, float, str]], title: str, title_y: int, font: str) -> None:
    def ts(t: float) -> str:
        cs = int(round(max(0.0, t) * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

    size = int(min(W, H) * 0.058)
    tsize = int(min(W, H) * 0.072)
    rows = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Sub,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(2, size // 12)},1,2,{W // 20},{W // 20},{int(H * 0.12)},1",
        f"Style: Title,{font},{tsize},&H0040D6FF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(2, tsize // 10)},2,5,{W // 16},{W // 16},0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for a, b, t in cues:
        rows.append(f"Dialogue: 0,{ts(a)},{ts(b)},Sub,,0,0,0,,{t.replace(chr(10), ' ')}")
    if title and title_y > 0:
        end = max([b for _a, b, _t in cues] + [1.0])
        rows.append(f"Dialogue: 1,{ts(0)},{ts(end + 1)},Title,,0,0,0,,{{\\pos({W // 2},{title_y})}}{title}")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def render_recap(video: str, info, segs: list[dict], title: str, settings, work: Path, out: Path, log, progress,
                 cancel) -> Path:
    """Đọc giọng từng đoạn -> dựng từng cảnh thành 1 file (có giọng + phụ đề) -> nối lại không mã hóa lại."""
    work.mkdir(parents=True, exist_ok=True)
    vopt = settings.section("video")
    vo = settings.section("voice")
    engine, voice = vo.get("engine") or "edge", vo.get("voice") or ""
    aspect = vopt.get("aspect", "9:16")
    W, H = render.output_size(info, aspect, int(vopt.get("height", 720)))
    band = tuple(vopt.get("band") or ()) or None
    cover = vopt.get("cover", "auto")
    if cover == "auto":
        cover = "blur" if band else "none"
    fill = vopt.get("fill", "blur")
    android = is_android()
    font = "Roboto" if android else "Arial"
    fonts = ":fontsdir=/system/fonts" if android else ""
    bg = float(vopt.get("recap_bg", 0.12))
    max_chars = 28 if H > W else 44
    # khung video gốc trong khung thành phẩm (để đặt tiêu đề ở phần trên)
    sc = min(W / info.width, H / info.height) if fill != "crop" else max(W / info.width, H / info.height)
    v_top = (H - info.height * sc) / 2
    title_y = int(v_top / 2) if (H > W and fill != "crop" and v_top > H * 0.08) else 0

    tts_dir = work / "tts"
    tts_dir.mkdir(exist_ok=True)
    items = [(s["text"], tts_dir / f"s{i:03d}.wav") for i, s in enumerate(segs)]
    log(f"Đọc giọng {len(items)} đoạn ({voices.ENGINES.get(engine, {}).get('name', engine)})...")
    voices.synth_many(engine, items, voice, settings, log, lambda p, m="": progress(0.05 + 0.3 * p, m), cancel)

    enc = encoder_args(vopt.get("encoder", "auto"), int(vopt.get("quality", 23)))
    parts = []
    prev_end = 0.0
    for i, (s, (_t, wav)) in enumerate(zip(segs, items)):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        speak = wav_seconds(wav)
        d = speak + 0.35
        start = s["start"]
        if start < prev_end and prev_end + d <= info.duration:
            start = prev_end  # không lặp lại cảnh vừa chiếu
        start = max(0.0, min(start, info.duration - d))
        prev_end = start + d
        cues = [(a + 0.15, b + 0.15, t) for a, b, t in render.chunks(s["text"], speak, max_chars, 0.0)]
        ass = work / f"p{i:03d}.ass"
        _ass(ass, W, H, cues, title, title_y, font)
        g = render.video_filter(W, H, fill, cover, float(vopt.get("cover_height", 14)), 30, info.width, info.height,
                                band=band)
        g += f";[vb]trim=duration={d:.3f},setpts=PTS-STARTPTS,subtitles=filename={ass.name}{fonts},format=yuv420p[v]"
        fmt_a = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
        if info.has_audio and bg > 0:
            g += (f";[0:a]atrim=duration={d:.3f},asetpts=PTS-STARTPTS,{fmt_a},volume={bg:.2f},apad=whole_dur={d:.3f}[b]"
                  f";[1:a]{fmt_a},adelay=150:all=1[n];[b][n]amix=inputs=2:duration=first:normalize=0,"
                  f"alimiter=limit=0.95[a]")
        else:
            g += f";[1:a]{fmt_a},adelay=150:all=1,apad=whole_dur={d:.3f},atrim=duration={d:.3f}[a]"
        part = work / f"p{i:03d}.mp4"
        run(["-ss", f"{start:.3f}", "-t", f"{d + 0.5:.3f}", "-i", str(video), "-i", str(wav), "-filter_complex", g,
             "-map", "[v]", "-map", "[a]", *enc, "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
             "-t", f"{d:.3f}", str(part)], cancel=cancel, cwd=str(work))
        parts.append(part)
        progress(0.35 + 0.6 * (i + 1) / len(segs), f"Dựng cảnh {i + 1}/{len(segs)}")
    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    run(["-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", "-movflags", "+faststart", str(tmp)],
        cancel=cancel, cwd=str(work))
    tmp.replace(out)
    for p in parts:
        p.unlink(missing_ok=True)
    (work / "script.json").write_text(json.dumps({"title": title, "segments": segs}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    log(f"✅ Video review: {out.name} ({fmt(sum(wav_seconds(w) + 0.35 for _t, w in items))})")
    return out
