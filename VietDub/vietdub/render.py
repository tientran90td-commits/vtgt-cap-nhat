"""Xuất video Việt hóa: 1 lượt FFmpeg cho cả video - che phụ đề gốc, in phụ đề Việt, trộn thuyết minh.

Không cần vẽ gì lên hình (chỉ thuyết minh, không in phụ đề) -> giữ nguyên hình gốc (chép thẳng), xuất cực nhanh.
"""
from __future__ import annotations

from pathlib import Path

from .media import MediaError, MediaInfo, encoder_args, run

ASPECTS = {"source": "Giữ như video gốc", "16:9": "Ngang 16:9 (YouTube)", "9:16": "Dọc 9:16 (TikTok, Reels, Shorts)",
           "1:1": "Vuông 1:1"}
FILLS = {"blur": "Nền mờ lấp chỗ trống", "crop": "Cắt giữa cho đầy khung"}
BACKGROUNDS = {"separate": "🎵 AI tách: bỏ giọng gốc, giữ nhạc nền & tiếng động",
               "duck": "Giữ tiếng gốc nhỏ (thuyết minh kiểu truyền thống)", "mute": "Tắt hẳn tiếng gốc"}
OUTPUTS = {"both": "🎙️ Thuyết minh + phụ đề Việt", "dub": "🎙️ Chỉ thuyết minh (lồng tiếng Việt)",
           "sub": "💬 Chỉ phụ đề tiếng Việt (giữ tiếng gốc)"}
COVERS = {"auto": "⚡ Xóa thông minh: tự dò, chỉ xóa đúng chỗ & đúng lúc có chữ", "none": "Không che",
          "blur": "Làm mờ phụ đề gốc ở dưới", "zoom": "Phóng to để đẩy phụ đề gốc ra ngoài",
          "bar": "Phủ dải đen lên phụ đề gốc"}
POSITIONS = {"bottom": "Dưới", "middle": "Giữa", "top": "Trên"}
COLORS = {"white": ("Trắng", "&H00FFFFFF", "#FFFFFF"), "yellow": ("Vàng", "&H0000E6FF", "#FFE600"),
          "cyan": ("Xanh nhạt", "&H00FFE08A", "#8AE0FF")}


def even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def output_size(info: MediaInfo, aspect: str, res: int) -> tuple[int, int]:
    if aspect == "source" and info.width and info.height and min(info.width, info.height) <= res:
        return even(info.width), even(info.height)  # không phóng to video nhỏ
    if aspect == "9:16":
        return res, even(res * 16 / 9)
    if aspect == "1:1":
        return res, res
    if aspect == "source" and info.width and info.height:
        sc = res / min(info.width, info.height)
        return even(info.width * sc), even(info.height * sc)
    return even(res * 16 / 9), res


# ------------------------------------------------------------------ phụ đề ASS
def _wrap(text: str, max_chars: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def chunks(text: str, total: float, max_chars: int, offset: float = 0.15) -> list[tuple[float, float, str]]:
    """Chia lời thuyết minh thành các dòng phụ đề (tối đa 2 dòng/lần), thời gian theo độ dài chữ."""
    lines = _wrap(text, max_chars)
    groups = [lines[i:i + 2] for i in range(0, len(lines), 2)]
    n_chars = sum(len(" ".join(g)) for g in groups) or 1
    out, t = [], offset
    span = max(0.5, total - offset)
    for g in groups:
        d = span * len(" ".join(g)) / n_chars
        out.append((t, t + d, "\\N".join(g)))
        t += d
    return out


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def write_ass(path: Path, items: list[tuple[float, float, str]], W: int, H: int, size: int, position: str,
              font: str = "Arial", color: str = "white") -> None:
    primary = COLORS.get(color, COLORS["white"])[1]
    scale = min(W, H) / 1080
    fs = max(14, int(size * scale * (1.25 if W < H else 1.0)))  # video dọc: chữ to hơn cho dễ đọc
    align = {"bottom": 2, "middle": 5, "top": 8}.get(position, 2)
    margin = int((H * 0.16 if W < H else 60 * scale)) if position != "middle" else 0
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font},{fs},{primary},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
            f"{max(1.5, 3 * scale):.1f},{max(0.5, 1.2 * scale):.1f},{align},{int(50 * scale)},{int(50 * scale)},{margin},1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    body = "".join(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Default,,0,0,0,,{t}\n" for a, b, t in items)
    path.write_text(head + body, encoding="utf-8")


def write_srt(path: Path, items: list[tuple[float, float, str]]) -> None:
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"
    path.write_text("".join(f"{i + 1}\n{ts(a)} --> {ts(b)}\n{t.replace(chr(92) + 'N', chr(10))}\n\n"
                            for i, (a, b, t) in enumerate(items)), encoding="utf-8")


# ------------------------------------------------------------------ bộ lọc hình
def smart_cover(src_w: int, src_h: int, band: tuple, boxes: list, t_offset: float = 0.0,
                length: float | None = None) -> str:
    """Xóa phụ đề gốc 'thông minh': chỉ vùng có chữ, chỉ lúc có chữ (delogo nội suy từ viền xung quanh).
    Gom các lần xuất hiện có bề rộng gần nhau thành nhóm -> ít bộ lọc, nhanh."""
    y0 = max(1, int(src_h * band[0]))
    h = max(4, min(src_h - y0 - 1, int(src_h * (band[1] - band[0]))))
    groups: dict = {}
    for a, b, x0, x1 in boxes:
        a, b = a - t_offset, b - t_offset
        if b <= 0 or (length is not None and a >= length):
            continue
        k = (round(x0 * 20) / 20, round(x1 * 20 + 0.49) / 20)  # làm tròn 5% (luôn phủ đủ)
        groups.setdefault(k, []).append((max(0.0, a), b))
    parts = []
    for (x0, x1), spans in sorted(groups.items()):
        x = max(1, int(src_w * max(0.0, x0)))
        w = max(4, min(src_w - x - 1, int(src_w * (min(1.0, x1) - x0))))
        en = "+".join(f"between(t\\,{a:.2f}\\,{b:.2f})" for a, b in spans)
        parts.append(f"delogo=x={x}:y={y0}:w={w}:h={h}:enable='{en}'")
    return ",".join(parts)


def video_filter(W: int, H: int, fill: str, cover: str, cover_pct: float, fps: int, src_w: int, src_h: int,
                 band: tuple | None = None, center: tuple = (0.5, 0.5), dur: float = 0.0, boxes: list | None = None,
                 t_offset: float = 0.0, length: float | None = None) -> str:
    """Đồ thị lọc từ [0:v] -> [vb] (đã che phụ đề gốc + đúng khung).

    band: dải phụ đề gốc (trên, dưới) theo tỉ lệ chiều cao (tự dò); không có thì dùng `cover_pct` % dưới cùng.
    center: vị trí nhân vật (đầu đoạn, cuối đoạn) cho kiểu lấp khung 'face'."""
    if cover == "auto":
        cover = ("smart" if boxes else "blur") if band else "none"
    if cover == "smart" and not (band and boxes):
        cover = "blur" if band else "none"
    if not band:
        p = max(0.03, min(0.4, cover_pct / 100))
        band = (1 - p, 1.0)
    y0, y1 = float(band[0]), float(band[1])
    g, cur = "", "[0:v]"
    if cover == "smart":
        sc = smart_cover(src_w, src_h, band, boxes, t_offset, length)
        if sc:
            g += f"{cur}{sc}[cv];"
            cur = "[cv]"
    elif cover == "zoom":
        if y0 >= 0.5:   # phụ đề ở dưới: giữ phần trên
            keep, top = y0, 0.0
        else:           # phụ đề ở trên: giữ phần dưới
            keep, top = 1 - y1, y1
        g += f"{cur}crop=iw*{keep:.4f}:ih*{keep:.4f}:iw*{(1 - keep) / 2:.4f}:ih*{top:.4f}[cz];"
        cur = "[cz]"
    elif cover == "blur":
        g += (f"{cur}split=2[c0][c1];[c1]crop=iw:ih*{y1 - y0:.4f}:0:ih*{y0:.4f},gblur=sigma=22:steps=2,"
              f"eq=brightness=-0.1[cb];[c0][cb]overlay=0:H*{y0:.4f}[cv];")
        cur = "[cv]"
    elif cover == "bar":
        g += f"{cur}drawbox=x=0:y=ih*{y0:.4f}:w=iw:h=ih*{y1 - y0:.4f}:color=black@0.9:t=fill[cv];"
        cur = "[cv]"
    wide_src = src_w and src_h and src_w / src_h > W / H + 0.02
    if fill == "face" and wide_src:
        a, b = (float(center[0]), float(center[1])) if center else (0.5, 0.5)
        cx = f"{a:.3f}" if abs(b - a) < 1e-3 or dur <= 0 else f"({a:.3f}+({b - a:.3f})*min(1\\,t/{dur:.2f}))"
        g += (f"{cur}crop=w=trunc(ih*{W}/{H}/2)*2:h=ih:x='max(0\\,min(iw-ow\\,{cx}*iw-ow/2))':y=0,"
              f"scale={W}:{H}[fit];")
    elif fill in ("crop", "face"):
        g += f"{cur}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[fit];"
    else:
        bw, bh = even(W / 4), even(H / 4)
        g += (f"{cur}split=2[f0][f1];[f1]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
              f"boxblur=8:2,scale={W}:{H},eq=brightness=-0.08[bg];"
              f"[f0]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[fit];")
    g += f"[fit]setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration=5[vb]"
    return g


# ------------------------------------------------------------------ xuất video
DUCK = "sidechaincompress=threshold=0.015:ratio=8:attack=10:release=400"


def subtitle_items(lines: list[dict], W: int, H: int, offset: float = 0.0, length: float | None = None) -> list:
    max_chars = 28 if W < H else 44
    items = []
    for ln in lines:
        vi = (ln.get("vi") or "").strip()
        if not vi:
            continue
        a, b = ln["start"] - offset, ln["end"] - offset
        if b <= 0 or (length is not None and a >= length):
            continue
        for x, y, t in chunks(vi, max(0.6, b - a), max_chars, offset=0.0):
            items.append((max(0.0, a + x), a + y, t))
    return items


def render_video(video: str, info: MediaInfo, lines: list[dict], dub_wav: Path | None, opts: dict, out: Path,
                 work: Path, log, progress, cancel, band: tuple | None = None, boxes: list | None = None,
                 start: float = 0.0, length: float | None = None, bg_audio: Path | None = None) -> Path:
    W, H = output_size(info, opts.get("aspect", "source"), int(opts.get("height", 1080)))
    mode = opts.get("output", "both")
    use_dub = mode in ("both", "dub") and dub_wav is not None
    burn = mode in ("both", "sub") and opts.get("burn_subs", True)
    cover = opts.get("cover", "none")
    if cover == "auto" and not band:
        cover = "none"
    resized = (W, H) != (even(info.width), even(info.height))
    preview = length is not None
    need_vf = burn or cover != "none" or resized or preview
    work.mkdir(parents=True, exist_ok=True)
    total = length if length is not None else info.duration
    items = subtitle_items(lines, W, H, start, length)
    soft = opts.get("soft_subs", True) and items and not preview
    args = []
    if start:
        args += ["-ss", f"{start:.3f}"]
    if length is not None:
        args += ["-t", f"{length:.3f}"]
    args += ["-i", video]
    n = 1
    if use_dub:
        args += ["-i", str(dub_wav)]
        dub_i, n = n, n + 1
    bg_mode = opts.get("background", "duck")
    use_bg = use_dub and bg_mode == "separate" and bg_audio is not None and Path(bg_audio).exists()
    if use_bg:
        if start:
            args += ["-ss", f"{start:.3f}"]
        if length is not None:
            args += ["-t", f"{length:.3f}"]
        args += ["-i", str(bg_audio)]
        bg_i, n = n, n + 1
    if soft:
        srt = work / "vi.srt"
        write_srt(srt, items)
        args += ["-i", str(srt)]
        sub_i = n
    fc = []
    if need_vf:
        g = video_filter(W, H, opts.get("fill", "blur"), cover, float(opts.get("cover_height", 14)), 30 if preview
                         else max(24, min(60, round(info.fps or 30))), info.width, info.height, band=band,
                         boxes=boxes, t_offset=start, length=length)
        g = g.replace(",tpad=stop_mode=clone:stop_duration=5", "")
        if burn and items:
            write_ass(work / "vi.ass", items, W, H, int(opts.get("sub_size", 54)), opts.get("sub_position", "bottom"),
                      color=opts.get("sub_color", "white"))
            g = g.replace("[vb]", "[vs]") + ";[vs]subtitles=filename=vi.ass[vb]"
        fc.append(g + ";[vb]format=yuv420p[v]")
    ov, vv = float(opts.get("orig_volume", 0.3) or 0.0), float(opts.get("voice_volume", 1.0) or 1.0)
    src = "0:a"
    duck = DUCK
    if use_bg:  # nhạc nền đã bỏ giọng gốc: giữ to, chỉ hạ nhẹ lúc đang đọc
        src, ov, duck = f"{bg_i}:a", float(opts.get("bg_volume", 1.0) or 1.0), \
            "sidechaincompress=threshold=0.02:ratio=3:attack=20:release=500"
    elif bg_mode == "mute":
        ov = 0.0
    if use_dub and (info.has_audio or use_bg) and ov > 0:
        mix = (f"[{src}]aresample=48000,aformat=channel_layouts=stereo,volume={ov:.2f}[o];"
               f"[{dub_i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vv:.2f}")
        if opts.get("duck", True):
            mix += f",asplit=2[d1][d2];[o][d1]{duck}[od];[od][d2]"
        else:
            mix += "[d2];[o][d2]"
        fc.append(mix + "amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[a]")
    elif use_dub:
        fc.append(f"[{dub_i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={vv:.2f},"
                  "alimiter=limit=0.95[a]")
    maps = ["-map", "[v]" if need_vf else "0:v:0"]
    if use_dub:
        maps += ["-map", "[a]"]
    elif info.has_audio:
        maps += ["-map", "0:a:0"]
    if soft:
        maps += ["-map", f"{sub_i}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=vie",
                 "-metadata:s:s:0", "title=Tiếng Việt"]
    tail = [*maps, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{total:.3f}", "-movflags", "+faststart"]
    if fc:
        tail = ["-filter_complex", ";".join(fc), *tail]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".tmp.mp4")
    enc = encoder_args(opts.get("encoder", "auto"), int(opts.get("quality", 21)))
    what = ("thuyết minh" + (" trên nhạc nền đã tách giọng" if use_bg else "") if use_dub else "") + (" + phụ đề Việt" if burn else "") + \
        ((" + xóa phụ đề gốc thông minh" if boxes else " + che phụ đề gốc") if cover != "none" else "")
    log(f"Xuất video {W}x{H}: {what.strip(' +') or 'giữ hình gốc'}"
        + (" (giữ nguyên hình gốc - rất nhanh)" if not need_vf else "") + "...")

    def go(vcodec):
        run([*args, *tail, *vcodec, str(tmp)], cancel=cancel, total=total, cwd=str(work),
            on_progress=lambda p: progress(p, f"Xuất video {int(p * 100)}%"))
    if need_vf:
        go([*enc, "-pix_fmt", "yuv420p"])
    else:
        try:
            go(["-c:v", "copy"])
        except MediaError:
            log("Không chép thẳng được hình gốc - mã hóa lại.", "warn")
            go([*enc, "-pix_fmt", "yuv420p"])
    tmp.replace(out)
    if opts.get("keep_srt") and items and not preview:
        write_srt(out.with_suffix(".srt"), items)
    progress(1.0, "Xong")
    return out
