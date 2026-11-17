"""Review / tóm tắt phim thành video ngắn (dùng lõi VietDub): lời gốc -> AI viết kịch bản (hook, 3 hồi, đúng tên
nhân vật) -> giọng đọc -> dựng từng đoạn -> nối lại.

Cơ chế học từ các dự án mã nguồn mở (chỉ học ý tưởng, code tự viết):
- movie-narrator: khớp lời kể với điểm CẮT CẢNH (không bắt đầu giữa cảnh), mỗi đoạn lời kể ghép nhiều cảnh ngắn
  (tránh 1 cảnh tĩnh kéo dài kiểu "trình chiếu ảnh"), bỏ cảnh đen / đoạn đầu - cuối phim, kịch bản chia 3 hồi.
- opensource-clipping (MIT): phụ đề karaoke (chữ đổi màu theo giọng đọc), tiêu đề "hook" lớn ở đầu video, nhạc nền
  tự nhỏ khi có giọng đọc (sidechain ducking).
- MovieShort-AI (MIT): rải cảnh đều cả phim.
"""
from __future__ import annotations

import json
import re
import subprocess
import wave
from pathlib import Path

from vietdub import render, voices
from vietdub.ai import extract_json
from vietdub.media import Cancelled, encoder_args, ffmpeg_exe, is_android, no_window, run

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
    "nhan_vat": "Ngôi thứ nhất: nhân vật chính tự kể lại câu chuyện của mình (xưng tôi)",
    "tham_tu": "Như thám tử phân tích: đặt câu hỏi, gợi bí ẩn, hé lộ manh mối dần dần",
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
- Đoạn 1 là "hook": 1–2 câu gây tò mò, lấy từ khoảnh khắc kịch tính nhất (cảnh của đoạn này có thể ở giữa / cuối phim).
- Từ đoạn 2 kể theo đúng trình tự thời gian, chia 3 hồi: mở đầu (~25%), diễn biến & xung đột (~50%), cao trào & kết (~25%).
- Tránh cảnh mở đầu / danh đề / credit cuối phim; mỗi đoạn một cảnh khác nhau, không lặp lại.
- Tổng lời kể khoảng {int(target * CPS)} ký tự (đọc khoảng {target // 60} phút {target % 60} giây), chia thành khoảng {n} đoạn, mỗi đoạn 1–3 câu (80–250 ký tự).
- Mỗi đoạn gắn với cảnh minh họa đúng nội dung đó: "start" là số giây trong video (lấy theo mốc thời gian lời thoại). Từ đoạn 2 trở đi "start" tăng dần và rải đều từ đầu tới cuối video.
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
        lo, hi = duration * 0.02, max(duration * 0.02, duration * 0.95 - 1.0)
        segs.append({"start": round(max(lo, min(start, hi)), 2), "text": t})
    if not segs:
        raise ValueError("Kịch bản rỗng")
    segs = segs[:1] + sorted(segs[1:], key=lambda s: s["start"])  # đoạn hook (cảnh cao trào) giữ ở đầu
    return str(d.get("title") or "").strip(), segs


# ------------------------------------------------------------------ cảnh (shot) - khớp lời kể với điểm cắt cảnh
CUT_SCORE = 12.0    # điểm đổi cảnh của scdet (0-100)
DARK_Y = 22.0       # độ sáng trung bình dưới mức này = cảnh đen / chuyển cảnh
MAX_SHOT = 3.6      # mỗi cảnh dùng tối đa vài giây -> hình thay đổi liên tục như kênh review
MIN_SHOT = 0.8


def analyze(video: str, a: float, length: float) -> list[tuple[float, float, float]]:
    """Khung (thời điểm, điểm đổi cảnh, độ sáng) trong [a, a+length] - 6 khung/giây, ảnh nhỏ nên rất nhanh."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-ss", f"{max(0.0, a):.3f}", "-t", f"{length:.3f}", "-i", str(video),
           "-an", "-sn", "-vf", "fps=6,scale=96:-2,signalstats,scdet=threshold=0,metadata=mode=print", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", **no_window())
    frames, t, y, sc = [], None, 128.0, 0.0
    for ln in r.stderr.splitlines():
        if "pts_time:" in ln:
            if t is not None:
                frames.append((t, sc, y))
            t, y, sc = max(0.0, a) + float(ln.rsplit("pts_time:", 1)[1].split()[0]), 128.0, 0.0
        elif "lavfi.signalstats.YAVG=" in ln:
            y = float(ln.rsplit("=", 1)[1])
        elif "lavfi.scd.score=" in ln:
            sc = float(ln.rsplit("=", 1)[1])
    if t is not None:
        frames.append((t, sc, y))
    return frames


def shots(frames: list[tuple[float, float, float]], end: float) -> list[tuple[float, float, float]]:
    """Cắt chuỗi khung thành các cảnh (bắt đầu, kết thúc, độ sáng trung bình)."""
    out, cur, ys = [], None, []
    for t, sc, y in frames:
        if cur is None:
            cur, ys = t, [y]
        elif sc >= CUT_SCORE:
            out.append((cur, t, sum(ys) / len(ys)))
            cur, ys = t, [y]
        else:
            ys.append(y)
    if cur is not None and end > cur:
        out.append((cur, end, sum(ys) / len(ys)))
    return out


def plan_pieces(sh: list[tuple[float, float, float]], start: float, need: float, limit: float) -> list[tuple[float, float]]:
    """Chọn các mẩu cảnh từ `start` đủ `need` giây: bắt đầu ở điểm cắt cảnh, bỏ cảnh đen / quá ngắn, mỗi cảnh tối đa
    MAX_SHOT giây. Thiếu thì lấy tiếp liền mạch. Trả về [(bắt đầu, độ dài)]."""
    pieces: list[tuple[float, float]] = []
    got = 0.0
    for a, b, y in sh:
        if got >= need - 0.05:
            break
        if b <= start or y < DARK_Y or b - a < MIN_SHOT:
            continue
        a2 = max(a, start)
        take = min(b - a2, MAX_SHOT, need - got)
        if take < MIN_SHOT and need - got > MIN_SHOT:
            continue
        pieces.append((a2, take))
        got += take
    if got < need - 0.05:  # hết cảnh trong cửa sổ: lấy tiếp liền mạch sau mẩu cuối
        a = pieces[-1][0] + pieces[-1][1] if pieces else start
        a = min(a, max(0.0, limit - (need - got)))
        pieces.append((a, need - got))
    merged: list[tuple[float, float]] = []
    for a, d in pieces:  # gộp mẩu liền nhau (đỡ phải cắt)
        if merged and abs(merged[-1][0] + merged[-1][1] - a) < 0.02:
            merged[-1] = (merged[-1][0], merged[-1][1] + d)
        else:
            merged.append((a, d))
    return merged


def karaoke(text: str, dur: float) -> str:
    """Phụ đề karaoke ASS: mỗi chữ đổi màu đúng lúc giọng đọc tới (thời gian theo độ dài chữ)."""
    lines = [ln.split() for ln in text.split("\\N")]
    words = [w for ln in lines for w in ln]
    total = sum(len(w) + 1 for w in words) or 1
    cs = max(1, int(dur * 100))
    out, used = [], 0
    for li, ln in enumerate(lines):
        if li:
            out.append("\\N")
        for wi, w in enumerate(ln):
            k = int(round(cs * (len(w) + 1) / total))
            used += k
            out.append(f"{{\\k{k}}}{w}" + (" " if wi < len(ln) - 1 else ""))
    return "".join(out)


def wav_seconds(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _ass(path: Path, W: int, H: int, cues: list[tuple[float, float, str]], title: str, title_y: int, font: str,
         kara: bool = True, hook: str = "") -> None:
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
        # karaoke: chữ trắng (Secondary) -> vàng (Primary) đúng lúc được đọc
        f"Style: Sub,{font},{size},{'&H0040D6FF' if kara else '&H00FFFFFF'},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,"
        "100,100,0,0,1,"
        f"{max(2, size // 12)},1,2,{W // 20},{W // 20},{int(H * 0.12)},1",
        f"Style: Title,{font},{tsize},&H0040D6FF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(2, tsize // 10)},2,5,{W // 16},{W // 16},0,1",
        f"Style: Hook,{font},{int(tsize * 1.25)},&H0040D6FF,&H00FFFFFF,&H00000000,&HA0000000,-1,0,0,0,100,100,0,0,1,"
        f"{max(3, tsize // 8)},3,5,{W // 14},{W // 14},0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for a, b, t in cues:
        t = t.replace(chr(10), " ")
        rows.append(f"Dialogue: 0,{ts(a)},{ts(b)},Sub,,0,0,0,,{karaoke(t, b - a) if kara else t}")
    if hook:  # tiêu đề lớn giữa màn hình 2.6 giây đầu video
        rows.append(f"Dialogue: 2,{ts(0)},{ts(2.6)},Hook,,0,0,0,,{{\\fad(150,350)\\pos({W // 2},{int(H * 0.42)})}}{hook}")
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
    kara = bool(vopt.get("karaoke", True))
    multi = bool(vopt.get("multi_shot", True))
    fmt_a = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    parts = []
    used_end = 0.0
    starts = [s["start"] for s in segs]
    for i, (s, (_t, wav)) in enumerate(zip(segs, items)):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        speak = wav_seconds(wav)
        d = speak + 0.35
        start = s["start"]
        if i > 0 and start < used_end:
            start = used_end  # không chiếu lại cảnh vừa dùng
        start = max(0.0, min(start, info.duration - d - 0.5))
        # cửa sổ cảnh cho đoạn này: tới đầu đoạn kể sau (AI gợi ý), đủ rộng để chọn nhiều cảnh
        nxt = [x for x in starts[i + 1:] if x > start + d]
        win = max(d + 2.0, min(d * 3.0, (nxt[0] - start) if nxt else d * 3.0, 45.0))
        win = min(win, info.duration - start)
        if multi:
            sh = shots(analyze(video, start - 0.5, win + 0.5), start + win)
            pieces = plan_pieces(sh, start, d, info.duration)
        else:
            pieces = [(start, d)]
        if i > 0:
            used_end = max(a + l for a, l in pieces)
        ws = min(a for a, _l in pieces)
        we = max(a + l for a, l in pieces)
        cues = [(a + 0.15, b + 0.15, t) for a, b, t in render.chunks(s["text"], speak, max_chars, 0.0)]
        ass = work / f"p{i:03d}.ass"
        _ass(ass, W, H, cues, title, title_y, font, kara=kara, hook=title if (i == 0 and vopt.get("hook_title", True)) else "")
        k = len(pieces)
        g = ""
        if k > 1:  # ghép các mẩu cảnh (hình + tiếng nền) trong 1 lần đọc file
            g += f"[0:v]split={k}" + "".join(f"[s{j}]" for j in range(k)) + ";"
            for j, (a, l) in enumerate(pieces):
                g += f"[s{j}]trim=start={a - ws:.3f}:duration={l:.3f},setpts=PTS-STARTPTS[t{j}];"
            g += "".join(f"[t{j}]" for j in range(k)) + f"concat=n={k}:v=1:a=0[vin];"
            vin = "[vin]"
        else:
            vin = "[0:v]"
        vf = render.video_filter(W, H, fill, cover, float(vopt.get("cover_height", 14)), 30, info.width, info.height,
                                 band=band)
        g += vf.replace("[0:v]", vin, 1)
        g += f";[vb]trim=duration={d:.3f},setpts=PTS-STARTPTS,subtitles=filename={ass.name}{fonts},format=yuv420p[v]"
        if info.has_audio and bg > 0:
            if k > 1:
                g += f";[0:a]asplit={k}" + "".join(f"[u{j}]" for j in range(k))
                for j, (a, l) in enumerate(pieces):
                    g += f";[u{j}]atrim=start={a - ws:.3f}:duration={l:.3f},asetpts=PTS-STARTPTS[w{j}]"
                g += ";" + "".join(f"[w{j}]" for j in range(k)) + f"concat=n={k}:v=0:a=1[ain]"
                ain = "[ain]"
            else:
                ain = "[0:a]"
            g += (f";{ain}atrim=duration={d:.3f},asetpts=PTS-STARTPTS,{fmt_a},volume={bg:.2f},apad=whole_dur={d:.3f}[b]"
                  f";[1:a]{fmt_a},adelay=150:all=1[n];[b][n]amix=inputs=2:duration=first:normalize=0,"
                  f"alimiter=limit=0.95[a]")
        else:
            g += f";[1:a]{fmt_a},adelay=150:all=1,apad=whole_dur={d:.3f},atrim=duration={d:.3f}[a]"
        part = work / f"p{i:03d}.mp4"
        run(["-ss", f"{ws:.3f}", "-t", f"{we - ws + 0.5:.3f}", "-i", str(video), "-i", str(wav), "-filter_complex", g,
             "-map", "[v]", "-map", "[a]", *enc, "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
             "-t", f"{d:.3f}", str(part)], cancel=cancel, cwd=str(work))
        parts.append(part)
        log(f"Đoạn {i + 1}/{len(segs)}: {len(pieces)} cảnh, {d:.1f}s")
        progress(0.35 + 0.6 * (i + 1) / len(segs), f"Dựng đoạn {i + 1}/{len(segs)}")
    lst = work / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    joined = work / "joined.mp4"
    run(["-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", "-movflags", "+faststart", str(joined)],
        cancel=cancel, cwd=str(work))
    bgm = str(vopt.get("bgm") or "")
    if bgm and Path(bgm).exists():  # nhạc nền: lặp cho đủ dài, tự nhỏ lại khi có giọng đọc
        vol = float(vopt.get("bgm_volume", 0.25))
        log(f"Thêm nhạc nền: {Path(bgm).name}")
        run(["-i", str(joined), "-stream_loop", "-1", "-i", bgm, "-filter_complex",
             f"[1:a]{fmt_a},volume={vol:.2f}[m];[0:a]asplit=2[sc][o];"
             "[m][sc]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400[md];"
             "[o][md]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
             "-movflags", "+faststart", str(tmp)], cancel=cancel, cwd=str(work))
        joined.unlink(missing_ok=True)
    else:
        joined.replace(tmp)
    tmp.replace(out)
    for p in parts:
        p.unlink(missing_ok=True)
    (work / "script.json").write_text(json.dumps({"title": title, "segments": segs}, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    log(f"✅ Video review: {out.name} ({fmt(sum(wav_seconds(w) + 0.35 for _t, w in items))})")
    return out
