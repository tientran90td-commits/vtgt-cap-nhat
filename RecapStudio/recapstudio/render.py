"""Dựng video recap: mỗi đoạn = cảnh phim + giọng thuyết minh + phụ đề; dựng nhiều đoạn cùng lúc rồi ghép."""
from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .media import Cancelled, MediaInfo, duration, encoder_args, run

ASPECTS = {"16:9": "Ngang 16:9 (YouTube)", "9:16": "Dọc 9:16 (TikTok, Reels, Shorts)", "1:1": "Vuông 1:1",
           "source": "Giữ như phim gốc"}
FILLS = {"face": "Cắt đầy khung, bám theo nhân vật", "blur": "Nền mờ lấp chỗ trống", "crop": "Cắt giữa cho đầy khung"}
COVERS = {"auto": "⚡ Tự dò phụ đề gốc (Vietsub) & làm mờ", "none": "Không che",
          "blur": "Làm mờ phụ đề gốc ở dưới", "zoom": "Phóng to để đẩy phụ đề gốc ra ngoài",
          "bar": "Phủ dải đen lên phụ đề gốc"}
POSITIONS = {"bottom": "Dưới", "middle": "Giữa", "top": "Trên"}


def even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


def output_size(info: MediaInfo, aspect: str, res: int) -> tuple[int, int]:
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
              font: str = "Arial") -> None:
    scale = min(W, H) / 1080
    fs = max(14, int(size * scale * (1.25 if W < H else 1.0)))  # video dọc: chữ to hơn cho dễ đọc
    align = {"bottom": 2, "middle": 5, "top": 8}.get(position, 2)
    margin = int((H * 0.16 if W < H else 60 * scale)) if position != "middle" else 0
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n"
            f"Style: Default,{font},{fs},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,"
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
def video_filter(W: int, H: int, fill: str, cover: str, cover_pct: float, fps: int, src_w: int, src_h: int,
                 band: tuple | None = None, center: tuple = (0.5, 0.5), dur: float = 0.0) -> str:
    """Đồ thị lọc từ [0:v] -> [vb] (đã che phụ đề gốc + đúng khung).

    band: dải phụ đề gốc (trên, dưới) theo tỉ lệ chiều cao (tự dò); không có thì dùng `cover_pct` % dưới cùng.
    center: vị trí nhân vật (đầu đoạn, cuối đoạn) cho kiểu lấp khung 'face'."""
    if cover == "auto":
        cover = "blur" if band else "none"
    if not band:
        p = max(0.03, min(0.4, cover_pct / 100))
        band = (1 - p, 1.0)
    y0, y1 = float(band[0]), float(band[1])
    g, cur = "", "[0:v]"
    if cover == "zoom":
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


# ------------------------------------------------------------------ dựng
def render(segments: list[dict], voices: list, video: str, info: MediaInfo, opts: dict, out: Path, work: Path,
           log, progress, cancel, band: tuple | None = None) -> Path:
    """segments[i] + voices[i] (file WAV hoặc None khi giữ tiếng gốc) -> video hoàn chỉnh tại `out`.
    band: dải phụ đề gốc đã dò (cho kiểu che 'auto')."""
    W, H = output_size(info, opts.get("aspect", "16:9"), int(opts.get("height", 1080)))
    fps = 30
    enc = encoder_args(opts.get("encoder", "auto"), int(opts.get("quality", 21)))
    parts_dir = work / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    max_chars = 28 if W < H else 44
    fill_mode = opts.get("fill", "blur")
    spans = []
    for i, seg in enumerate(segments):
        voice = voices[i] if i < len(voices) else None
        dur = duration(voice) + 0.35 if voice else max(1.5, min(30.0, seg["end"] - seg["start"]))
        start = seg["start"]
        if start + dur > info.duration:
            start = max(0.0, info.duration - dur - 0.1)
        spans.append((start, dur))
    centers = [(0.5, 0.5)] * len(spans)
    if fill_mode == "face" and info.width and info.height and info.width / info.height > W / H + 0.02:
        from . import reframe

        if reframe.available():
            log("Bám theo nhân vật cho khung " + ("dọc" if W < H else "vuông") + "...")
            centers = reframe.track(video, info, spans, work, cancel, log,
                                    lambda p, m="": progress(0.15 * p, m))
        else:
            log("Chưa cài OpenCV - cắt giữa khung (pip install opencv-python-headless).", "warn")
    jobs, parts, all_subs, t_global = [], [], [], 0.0
    for i, seg in enumerate(segments):
        voice = voices[i] if i < len(voices) else None
        start, dur = spans[i]
        vf = video_filter(W, H, fill_mode, opts.get("cover", "none"), float(opts.get("cover_height", 14)),
                          fps, info.width, info.height, band=band, center=centers[i], dur=dur)
        subs = chunks(seg["narration"], dur - 0.2, max_chars) if (voice and opts.get("subtitles", True)) else []
        all_subs += [(a + t_global, b + t_global, t) for a, b, t in subs]
        t_global += dur
        key = hashlib.sha1(json.dumps([video, round(start, 2), round(dur, 2), str(voice),
                                       voice and os.path.getsize(voice), W, H, vf, enc, subs,
                                       opts.get("sub_size"), opts.get("sub_position"), opts.get("orig_volume"),
                                       opts.get("voice_volume")], default=str).encode()).hexdigest()[:12]
        part = parts_dir / f"p{i:03d}_{key}.mp4"
        parts.append(part)
        if part.exists() and part.stat().st_size > 1000:
            continue
        for old in parts_dir.glob(f"p{i:03d}_*.mp4"):
            old.unlink(missing_ok=True)
        args = ["-ss", f"{start:.3f}", "-t", f"{dur + 0.3:.3f}", "-i", video]
        fc = vf
        if subs:
            ass = f"p{i:03d}.ass"
            write_ass(parts_dir / ass, subs, W, H, int(opts.get("sub_size", 54)), opts.get("sub_position", "bottom"))
            fc = fc.replace("[vb]", "[vs]") + f";[vs]subtitles=filename={ass}[vb]"
        fc += ";[vb]format=yuv420p[v]"
        ov = float(opts.get("orig_volume", 0.0) or 0.0)
        if voice:
            args += ["-i", str(voice)]
            vchain = f"[1:a]adelay=150|150,volume={float(opts.get('voice_volume', 1.0)):.2f},apad"
            if info.has_audio and ov > 0:
                fc += (f";[0:a]aresample=48000,volume={ov:.2f},apad[oa];{vchain}[va];"
                       "[oa][va]amix=inputs=2:normalize=0:duration=longest[a]")
            else:
                fc += f";{vchain}[a]"
        elif info.has_audio:
            fc += ";[0:a]aresample=48000,afade=t=in:d=0.1,apad[a]"
        else:
            fc += ";anullsrc=r=48000:cl=stereo[a]"
        args += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", *enc, "-pix_fmt", "yuv420p",
                 "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", part.name]
        jobs.append((i, args, dur))
    workers = max(1, min(6, int(opts.get("parallel", 2) or 1)))
    if jobs:
        log(f"Dựng {len(jobs)} đoạn video" + (f" ({workers} đoạn cùng lúc)" if workers > 1 else "") + "...")
    done = [0]

    def one(job):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        run(job[1], cancel=cancel, cwd=str(parts_dir))
        done[0] += 1
        progress(0.15 + 0.75 * done[0] / len(jobs), f"Dựng đoạn {done[0]}/{len(jobs)}")
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(one, j) for j in jobs]
            try:
                for f in futs:
                    f.result()
            except BaseException:
                if cancel is not None:
                    cancel.set()
                raise
    progress(0.92, "Ghép video")
    lst = parts_dir / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    joined = parts_dir / "joined.mp4"
    run(["-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", joined.name], cancel=cancel, cwd=str(parts_dir))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    norm = "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000"
    music = opts.get("music") or ""
    progress(0.96, "Cân bằng âm lượng" + (" + nhạc nền" if music else ""))
    if music and Path(music).exists():
        mv = float(opts.get("music_volume", 0.15))
        run(["-i", str(joined), "-stream_loop", "-1", "-i", music, "-filter_complex",
             f"[1:a]aresample=48000,volume={mv:.2f},afade=t=out:st={max(0.0, t_global - 3):.2f}:d=3[m];"
             f"[0:a][m]amix=inputs=2:normalize=0:duration=first,{norm}[a]", "-map", "0:v", "-map", "[a]",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{t_global:.3f}", "-movflags", "+faststart",
             str(out)], cancel=cancel)
    else:
        run(["-i", str(joined), "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", norm, "-c:a", "aac",
             "-b:a", "192k", "-movflags", "+faststart", str(out)], cancel=cancel)
    joined.unlink(missing_ok=True)
    if opts.get("keep_srt") and all_subs:
        write_srt(out.with_suffix(".srt"), all_subs)
    progress(1.0, "Xong")
    log(f"✅ Đã xuất video: {out} ({t_global / 60:.1f} phút)")
    return out
