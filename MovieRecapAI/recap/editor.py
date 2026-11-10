"""Dựng video tóm tắt bằng FFmpeg: cắt cảnh, ghép giọng đọc, phụ đề, nhạc nền, logo, khung dọc/ngang."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .ffmpeg_utils import Cancelled, MediaInfo, media_duration, run_ffmpeg
from .subtitles import timed_chunks, wrap_line, write_ass, write_srt

ASPECTS = {
    "16:9": "Ngang 16:9 (YouTube)",
    "9:16": "Dọc 9:16 (TikTok, Reels, Shorts)",
    "1:1": "Vuông 1:1 (Facebook/Instagram)",
    "4:5": "Dọc 4:5 (Instagram feed)",
    "original": "Giữ tỉ lệ gốc của phim",
}
FILLS = {"blur": "Nền mờ (blur) lấp khoảng trống", "crop": "Cắt cúp cho đầy khung", "pad": "Viền đen"}
ENCODERS = {
    "auto": "Tự động (dùng GPU nếu có: NVIDIA/AMD/Intel)",
    "libx264": "CPU - H.264 (tương thích nhất)",
    "h264_nvenc": "GPU NVIDIA - NVENC",
    "h264_qsv": "GPU Intel - QuickSync",
    "h264_amf": "GPU AMD - AMF",
    "libx265": "CPU - H.265/HEVC (file nhỏ hơn)",
}
FITS = {"extend": "Lấy cảnh theo đúng độ dài giọng đọc (tự nhiên)",
        "speed": "Co giãn tốc độ cảnh cho khớp đoạn AI chọn (0.75x-1.5x)"}


def output_size(info: MediaInfo, aspect: str, res: int) -> tuple[int, int]:
    """res = cạnh ngắn (720/1080/1440/2160)."""
    def even(x):
        return int(round(x / 2.0)) * 2
    if aspect == "16:9":
        return even(res * 16 / 9), res
    if aspect == "9:16":
        return res, even(res * 16 / 9)
    if aspect == "1:1":
        return res, res
    if aspect == "4:5":
        return res, even(res * 5 / 4)
    w, h = info.width or 1920, info.height or 1080
    if w >= h:
        return even(w * res / h), res
    return res, even(h * res / w)


_BEST_ENCODER: str | None = None


def best_encoder(log=None) -> str:
    """Thử lần lượt NVENC (NVIDIA) -> AMF (AMD) -> QuickSync (Intel); không được thì dùng CPU."""
    global _BEST_ENCODER
    if _BEST_ENCODER is None:
        from .ffmpeg_utils import encoder_works

        _BEST_ENCODER = "libx264"
        for e in ("h264_nvenc", "h264_amf", "h264_qsv"):
            if encoder_works(e):
                _BEST_ENCODER = e
                break
        if log:
            log(f"Bộ mã hóa video: {ENCODERS.get(_BEST_ENCODER, _BEST_ENCODER)}")
    return _BEST_ENCODER


def encoder_args(enc: str, quality: int) -> list[str]:
    if enc == "auto":
        enc = best_encoder()
    q = str(int(quality))
    if enc == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", q, "-b:v", "0"]
    if enc == "h264_qsv":
        return ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", q]
    if enc == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", q, "-qp_p", q]
    if enc == "libx265":
        return ["-c:v", "libx265", "-preset", "fast", "-crf", str(int(quality) + 3), "-tag:v", "hvc1"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", q]


def _video_chain(W: int, H: int, fill: str, speed: float, fps: int) -> str:
    pre = f"setpts=PTS/{speed:.4f}," if abs(speed - 1) > 0.001 else ""
    if fill == "crop":
        core = f"[0:v]{pre}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    elif fill == "pad":
        core = (f"[0:v]{pre}scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
    else:
        bw, bh = max(2, W // 4 // 2 * 2), max(2, H // 4 // 2 * 2)
        core = (f"[0:v]{pre}split=2[bgs][fgs];"
                f"[bgs]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},boxblur=8:2,"
                f"scale={W}:{H},eq=brightness=-0.08[bg];"
                f"[fgs]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
    # tpad: nếu cảnh ở cuối phim hơi ngắn thì giữ khung cuối, tránh lệch tiếng/hình khi ghép
    return core + f",setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration=3"


def _logo_xy(pos: str) -> str:
    m = 24
    return {
        "top-left": f"{m}:{m}", "top-right": f"W-w-{m}:{m}",
        "bottom-left": f"{m}:H-h-{m}", "bottom-right": f"W-w-{m}:H-h-{m}",
    }.get(pos, f"W-w-{m}:{m}")


def render(script: dict, video: str, info: MediaInfo, voices: list, opts: dict, out_path: Path, work_dir: Path,
           transcript: list[dict] | None, log, progress, cancel) -> Path:
    """voices[i] = đường dẫn WAV giọng đọc của đoạn i, hoặc None nếu đoạn giữ âm thanh gốc."""
    segs = script["segments"]
    W, H = output_size(info, opts.get("aspect", "16:9"), int(opts.get("height", 1080)))
    fps = int(opts.get("fps", 30))
    if opts.get("encoder", "auto") == "auto":
        best_encoder(log)
    enc = encoder_args(opts.get("encoder", "auto"), int(opts.get("quality", 21)))
    parts_dir = work_dir / "render_parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    style = {
        "font": opts.get("sub_font", "Arial"), "size": opts.get("sub_size", 52), "color": opts.get("sub_color"),
        "outline_color": opts.get("sub_outline_color"), "outline": opts.get("sub_outline", 3),
        "position": opts.get("sub_position", "bottom"), "bold": opts.get("sub_bold", True),
    }
    max_chars = int(opts.get("sub_max_chars", 42))
    if W < H:
        max_chars = min(max_chars, 28)
    gap = float(opts.get("gap", 0.25))
    logo = opts.get("logo") or ""
    if logo and not Path(logo).exists():
        log(f"Không thấy logo {logo} - bỏ qua.", level="warn")
        logo = ""
    all_subs: list[dict] = []
    t_global = 0.0
    part_files = []
    for i, seg in enumerate(segs):
        if cancel.is_set():
            raise Cancelled()
        progress(i / len(segs), f"Dựng đoạn {i + 1}/{len(segs)}")
        voice = voices[i] if i < len(voices) else None
        src_start = float(seg["start"])
        src_end = float(seg["end"])
        speed = 1.0
        if voice:
            vdur = media_duration(voice)
            dur = vdur + gap + 0.1
            if opts.get("fit") == "speed":
                speed = max(0.75, min(1.5, (src_end - src_start) / dur))
            need = dur * speed
        else:
            vdur = 0.0
            dur = max(1.0, min(90.0, src_end - src_start))
            need = dur
        if src_start + need > info.duration:
            src_start = max(0.0, info.duration - need - 0.05)
        # Phụ đề của đoạn (thời gian tính từ đầu đoạn)
        subs: list[dict] = []
        if opts.get("subtitles", True):
            if voice and seg.get("narration"):
                subs = timed_chunks(seg["narration"], vdur, max_chars, offset=0.1)
            elif not voice and transcript and opts.get("sub_original", True):
                for t in transcript:
                    if t["end"] > src_start and t["start"] < src_start + need:
                        subs.append({"start": max(0.0, t["start"] - src_start),
                                     "end": min(dur, t["end"] - src_start), "text": wrap_line(t["text"], max_chars)})
        title = None
        if i == 0 and (opts.get("title_text") or "").strip():
            title = {"text": opts["title_text"].strip(), "start": 0.0,
                     "end": min(dur, float(opts.get("title_seconds", 4)))}
        for s in subs:
            all_subs.append({"start": s["start"] + t_global, "end": s["end"] + t_global, "text": s["text"]})

        key = hashlib.sha1(json.dumps([seg, str(voice), voice and Path(voice).stat().st_size, src_start, need, dur,
                                       speed, W, H, fps, enc, opts.get("fill"), style, subs, title, logo,
                                       opts.get("logo_position"), opts.get("logo_scale"),
                                       opts.get("orig_volume_voice"), opts.get("orig_volume_clip"),
                                       opts.get("voice_volume"), video], ensure_ascii=False,
                                      default=str).encode()).hexdigest()[:12]
        part = parts_dir / f"seg_{i:03d}_{key}.mp4"
        part_files.append(part)
        t_global += dur
        if part.exists() and part.stat().st_size > 1000:
            log(f"Đoạn {i + 1}: dùng lại bản đã dựng.", level="debug")
            continue
        for old in parts_dir.glob(f"seg_{i:03d}_*.mp4"):
            old.unlink(missing_ok=True)

        args = ["-ss", f"{src_start:.3f}", "-t", f"{need + 0.2:.3f}", "-i", video]
        idx = 1
        voice_idx = logo_idx = None
        if voice:
            args += ["-i", str(voice)]
            voice_idx = idx
            idx += 1
        if logo:
            args += ["-i", logo]
            logo_idx = idx
            idx += 1
        fc = _video_chain(W, H, opts.get("fill", "blur"), speed, fps)
        ass_name = None
        if subs or title:
            ass_name = f"seg_{i:03d}.ass"
            write_ass(subs, parts_dir / ass_name, W, H, style, title)
        if logo_idx is not None:
            lw = max(16, int(W * float(opts.get("logo_scale", 0.12))) // 2 * 2)
            fc += f"[vb];[{logo_idx}:v]scale={lw}:-1,format=rgba[lg];[vb][lg]overlay={_logo_xy(opts.get('logo_position'))}"
        if ass_name:
            fc += f",subtitles=filename={ass_name}"
        fc += ",format=yuv420p[v]"
        # Âm thanh
        ov_voice = float(opts.get("orig_volume_voice", 0.12))
        ov_clip = float(opts.get("orig_volume_clip", 1.0))
        vv = float(opts.get("voice_volume", 1.0))
        tempo = ""
        if abs(speed - 1) > 0.001:
            tempo = f"atempo={speed:.4f},"
        if voice_idx is not None:
            vchain = f"[{voice_idx}:a]adelay=100|100,volume={vv:.3f},apad[va]"
            if info.has_audio and ov_voice > 0:
                fc += (f";[0:a]{tempo}aresample=48000,volume={ov_voice:.3f},apad[oa];{vchain};"
                       f"[oa][va]amix=inputs=2:normalize=0:duration=longest[a]")
            else:
                fc += f";{vchain.replace('[va]', '[a]')}"
        else:
            if info.has_audio:
                fc += f";[0:a]{tempo}aresample=48000,volume={ov_clip:.3f},afade=t=in:d=0.15,apad[a]"
            else:
                fc += ";anullsrc=r=48000:cl=stereo[a]"
        args += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", *enc,
                 "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                 part.name]
        run_ffmpeg(args, cancel=cancel, cwd=str(parts_dir), log=log, total=dur,
                   on_progress=lambda p, i=i: progress((i + p) / len(segs), f"Dựng đoạn {i + 1}/{len(segs)}"))

    # Ghép các đoạn
    progress(0.97, "Ghép video")
    list_file = parts_dir / "concat.txt"
    list_file.write_text("".join(f"file '{p.name}'\n" for p in part_files), encoding="utf-8")
    joined = parts_dir / "joined.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", list_file.name, "-c", "copy", joined.name],
               cancel=cancel, cwd=str(parts_dir), log=log)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    music = opts.get("music") or ""
    if music and Path(music).exists():
        progress(0.98, "Trộn nhạc nền")
        mv = float(opts.get("music_volume", 0.15))
        fade_st = max(0.0, t_global - 3)
        run_ffmpeg(["-i", str(joined), "-stream_loop", "-1", "-i", music, "-filter_complex",
                    f"[1:a]aresample=48000,volume={mv:.3f},afade=t=in:d=1.5,afade=t=out:st={fade_st:.2f}:d=3[m];"
                    f"[0:a][m]amix=inputs=2:normalize=0:duration=first[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{t_global:.3f}", "-movflags", "+faststart", str(out_path)], cancel=cancel, log=log)
    else:
        run_ffmpeg(["-i", str(joined), "-c", "copy", "-movflags", "+faststart", str(out_path)], cancel=cancel, log=log)
    joined.unlink(missing_ok=True)
    if all_subs:
        write_srt(all_subs, out_path.with_suffix(".srt"))
    progress(1.0, "Hoàn tất")
    log(f"✅ Đã xuất video: {out_path}  ({t_global:.1f} giây)")
    return out_path


def clear_render_cache(work_dir: Path) -> None:
    shutil.rmtree(work_dir / "render_parts", ignore_errors=True)
