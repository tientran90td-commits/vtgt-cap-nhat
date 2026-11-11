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
FILLS = {"face": "🎯 Cắt đầy khung, bám theo khuôn mặt nhân vật (khuyên dùng cho TikTok)",
         "blur": "Nền mờ (blur) lấp khoảng trống", "crop": "Cắt cúp giữa khung cho đầy", "pad": "Viền đen"}
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


def _delogo(box, sw: int, sh: int) -> str:
    """Che mờ logo/watermark cố định của nguồn (box = tỉ lệ x0,y0,x1,y1)."""
    if not box or not sw or not sh:
        return ""
    x0, y0 = int(box[0] * sw), int(box[1] * sh)
    x1, y1 = int(box[2] * sw), int(box[3] * sh)
    x0, y0 = max(1, x0), max(1, y0)
    x1, y1 = min(sw - 2, x1), min(sh - 2, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return ""
    return f"delogo=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0},"


def _video_chain(W: int, H: int, fill: str, speed: float, fps: int, src: str = "[0:v]", pre_filter: str = "",
                 face_crop: str = "") -> str:
    pre = pre_filter + (f"setpts=PTS/{speed:.4f}," if abs(speed - 1) > 0.001 else "")
    if fill == "face" and face_crop:
        core = f"{src}{pre}{face_crop}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    elif fill in ("crop", "face"):
        core = f"{src}{pre}scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    elif fill == "pad":
        core = (f"{src}{pre}scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black")
    else:
        bw, bh = max(2, W // 4 // 2 * 2), max(2, H // 4 // 2 * 2)
        core = (f"{src}{pre}split=2[bgs][fgs];"
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


HARDSUB_MODES = {
    "blur": "Làm mờ dải phụ đề gốc (khuyên dùng)",
    "vsr": "🧠 Xóa sạch bằng AI (video-subtitle-remover, cần cài VSR)",
    "bar": "Phủ dải tối lên phụ đề gốc",
    "crop": "Cắt bỏ phần dưới chứa phụ đề gốc",
    "avoid": "Giữ nguyên, chỉ đưa phụ đề của app lên trên để không đè",
    "none": "Không xử lý",
}


def _hardsub_filters(hs: dict | None, mode: str, sw: int, sh: int, src: str) -> tuple[str, str, str]:
    """Trả về (đồ thị lọc phụ, nhãn nguồn mới, bộ lọc thêm vào chuỗi) để che/cắt dải phụ đề in cứng."""
    if not hs or mode in ("none", "avoid", "vsr", "", None) or not sw or not sh:
        return "", src, ""
    y = max(0, int(hs["y0"] * sh) // 2 * 2)
    hh = max(2, min(sh - y, int((hs["y1"] - hs["y0"]) * sh)) // 2 * 2)
    if mode == "crop" and hs["y1"] > 0.8 and y > sh * 0.6:
        return "", src, f"crop=iw:{y}:0:0,"
    if mode == "bar" or (mode == "crop"):
        return "", src, f"drawbox=x=0:y={y}:w=iw:h={hh}:color=black@0.88:t=fill,"
    graph = (f"{src}split=2[hs0][hs1];[hs1]crop=iw:{hh}:0:{y},gblur=sigma=18:steps=2,eq=brightness=-0.12[hsb];"
             f"[hs0][hsb]overlay=0:{y}[hsrc];")
    return graph, "[hsrc]", ""


def plan_fit(voice_s: float, clips: list[tuple[int, float]], target: float) -> dict:
    """Lên kế hoạch ép video vừa thời lượng mục tiêu.

    voice_s: tổng thời lượng các đoạn thuyết minh; clips: [(chỉ số đoạn, giây)] các đoạn giữ thoại gốc.
    Thứ tự ưu tiên: co/giãn đoạn thoại gốc (0.5x-1.6x) -> tăng/giảm tốc độ đọc (0.88x-1.2x) -> bỏ bớt đoạn thoại gốc.
    Trả về {"clip_k", "tempo", "drop": [chỉ số], "estimate"}."""
    clip_s = sum(d for _i, d in clips)
    total = voice_s + clip_s
    plan = {"clip_k": 1.0, "tempo": 1.0, "drop": [], "before": round(total, 1), "estimate": round(total, 1)}
    if target <= 0 or total <= 0 or abs(total - target) <= max(2.0, 0.02 * target):
        return plan
    k = 1.0
    if clip_s > 0:
        k = max(0.5, min(1.6, (target - voice_s) / clip_s)) if target > voice_s else 0.5
    rest = target - clip_s * k
    tempo = 1.0
    if voice_s > 0:
        tempo = max(0.88, min(1.2, voice_s / rest)) if rest > 0 else 1.2
        if abs(tempo - 1.0) < 0.01:
            tempo = 1.0
    est = voice_s / tempo + clip_s * k
    drop = []
    if est > target + 2:  # vẫn dài: bỏ đoạn thoại gốc dài nhất trước (giữ đoạn đầu & cuối)
        for i, d in sorted(clips[1:-1] if len(clips) > 2 else [], key=lambda x: -x[1]):
            if est <= target + 2:
                break
            drop.append(i)
            est -= d * k
    plan.update(clip_k=round(k, 3), tempo=round(tempo, 3), drop=sorted(drop), estimate=round(est, 1))
    return plan


def _tempo_voice(voice: Path, tempo: float, out_dir: Path) -> Path:
    """Đổi tốc độ giọng đọc (giữ nguyên cao độ)."""
    if not voice or abs(tempo - 1.0) < 0.005:
        return voice
    out = out_dir / f"{Path(voice).stem}_t{int(round(tempo * 1000))}.wav"
    if not out.exists() or out.stat().st_size < 1000:
        run_ffmpeg(["-i", str(voice), "-af", f"atempo={tempo:.3f}", "-ac", "1", "-ar", "48000", str(out)])
    return out


def render(script: dict, video: str, info: MediaInfo, voices: list, opts: dict, out_path: Path, work_dir: Path,
           transcript: list[dict] | None, log, progress, cancel, blocked=None, watermark=None,
           hardsub: dict | None = None, episodes: list | None = None) -> Path:
    """voices[i] = đường dẫn WAV giọng đọc của đoạn i, hoặc None nếu đoạn giữ âm thanh gốc.
    blocked: các khoảng không được dùng (quảng cáo chèn, OP/ED, đoạn người dùng bỏ).
    watermark: {"box": [...]} logo cố định của nguồn để che mờ."""
    from .footage import Footage, sentence_durations, valid_sentences

    segs = script["segments"]
    # blocked: [[start, end, loại]] loại = overlay (quảng cáo chèn) | opening | ending | user
    use_blocked = [r for r in (blocked or []) if opts.get("avoid_overlays", True) or (len(r) < 3 or r[2] != "overlay")]
    footage = Footage(info.duration, use_blocked, no_reuse=opts.get("no_reuse", True))
    pre_filter = _delogo((watermark or {}).get("box"), info.width, info.height) if opts.get("delogo", True) else ""
    hs_mode = opts.get("hardsub_mode", "blur") if hardsub else "none"
    if hardsub and hs_mode != "none":
        log(f"Phụ đề gốc in cứng: {HARDSUB_MODES.get(hs_mode, hs_mode)}")
    vsr_ok = hs_mode == "vsr"
    synced = 0
    W, H = output_size(info, opts.get("aspect", "16:9"), int(opts.get("height", 1080)))
    fps_opt = opts.get("fps", 30)
    if str(fps_opt) == "source":  # giữ nhịp khung hình gốc (làm tròn về chuẩn gần nhất)
        src_fps = info.fps or 30
        fps = min((24, 25, 30, 50, 60), key=lambda f: abs(f - src_fps)) if src_fps else 30
    else:
        fps = int(fps_opt)
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
    if hardsub and opts.get("hardsub_mode", "blur") == "avoid" and style["position"] == "bottom":
        style["position"] = "top"  # né phụ đề gốc nằm ở dưới
    max_chars = int(opts.get("sub_max_chars", 42))
    if W < H:
        max_chars = min(max_chars, 28)
    gap = float(opts.get("gap", 0.25))
    logo = opts.get("logo") or ""
    if logo and not Path(logo).exists():
        log(f"Không thấy logo {logo} - bỏ qua.", level="warn")
        logo = ""
    # Ép vừa thời lượng thành phẩm
    fit = {"clip_k": 1.0, "tempo": 1.0, "drop": []}
    target_s = float(opts.get("_target_seconds") or 0)
    if opts.get("fit_duration") and target_s > 0:
        v_s, clips = 0.0, []
        for i, seg in enumerate(segs):
            v = voices[i] if i < len(voices) else None
            if v:
                v_s += media_duration(v) + gap + 0.1
            else:
                clips.append((i, max(1.0, min(90.0, float(seg["end"]) - float(seg["start"])))))
        fit = plan_fit(v_s, clips, target_s)
        if fit["estimate"] != fit["before"]:
            log(f"Ép thời lượng {fit['before'] / 60:.1f} → {fit['estimate'] / 60:.1f} phút (mục tiêu "
                f"{target_s / 60:.1f}): tốc độ đọc x{fit['tempo']:g}, đoạn thoại gốc x{fit['clip_k']:g}"
                + (f", bỏ {len(fit['drop'])} đoạn thoại gốc" if fit["drop"] else ""))
        if abs(fit["estimate"] - target_s) > max(5.0, 0.1 * target_s):
            log(f"Kịch bản {'quá dài' if fit['estimate'] > target_s else 'quá ngắn'} so với mục tiêu - video sẽ dài "
                f"~{fit['estimate'] / 60:.1f} phút. Muốn khớp hơn: Bước 2 → viết lại kịch bản với độ dài mới.",
                level="warn")
    all_subs: list[dict] = []
    t_global = 0.0
    part_files = []
    timeline: list[list] = []  # [chỉ số đoạn, giây bắt đầu trong video xuất, thời lượng]
    jobs: list[tuple] = []  # (chỉ số đoạn, tham số ffmpeg, thời lượng) - dựng sau vòng lặp
    last_ep = None
    for i, seg in enumerate(segs):
        if cancel.is_set():
            raise Cancelled()
        if i in fit["drop"]:
            continue
        progress(i / len(segs), f"Dựng đoạn {i + 1}/{len(segs)}")
        voice = voices[i] if i < len(voices) else None
        if voice and fit["tempo"] != 1.0:
            voice = _tempo_voice(voice, fit["tempo"], parts_dir)
        src_start = float(seg["start"])
        src_end = float(seg["end"])
        speed = 1.0
        sents = valid_sentences(seg) if (voice and opts.get("sentence_sync", True)) else None
        sent_durs = None
        if voice:
            vdur = media_duration(voice)
            dur = vdur + gap + 0.1
            if sents:
                # Khớp tiếng-hình theo câu: mỗi câu chiếu đúng khoảnh khắc nó kể
                speech = sentence_durations(str(voice), [x["text"] for x in sents], vdur)
                sent_durs = list(speech)
                sent_durs[0] += 0.1   # giọng bắt đầu trễ 0.1s
                sent_durs[-1] += gap  # khoảng nghỉ cuối đoạn
                pieces = []
                for sx, d in zip(sents, sent_durs):
                    a = float(sx.get("start", src_start))
                    b = float(sx.get("end", a + d))
                    pieces.append((footage.place(a, d, b), d))
                synced += 1
            else:
                if opts.get("fit") == "speed":
                    speed = max(0.75, min(1.5, (src_end - src_start) / dur))
                need = dur * speed
                pieces = [(footage.place(src_start, need, src_end), need)]
        else:
            vdur = 0.0
            dur = max(1.0, min(90.0, src_end - src_start)) * fit["clip_k"]
            pieces = [(footage.place(src_start, dur, src_end), dur)]
        src_start = pieces[0][0]
        need = sum(d for _a, d in pieces)
        # Phụ đề của đoạn (thời gian tính từ đầu đoạn)
        subs: list[dict] = []
        if opts.get("subtitles", True):
            if voice and sents and sent_durs:
                off = 0.1
                for sx, d in zip(sents, speech):
                    subs += timed_chunks(sx["text"], d, max_chars, offset=off)
                    off += d
            elif voice and seg.get("narration"):
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
        # recap nhiều tập: hiện "Tập N" khi câu chuyện chuyển sang tập mới
        if episodes and len(episodes) > 1 and opts.get("episode_labels", True):
            ep = next((e for e in episodes if e["start"] - 0.5 <= src_start < e["end"]), None)
            if ep and ep.get("index") != last_ep:
                last_ep = ep.get("index")
                if title is None:
                    title = {"text": ep["title"], "start": 0.0, "end": min(dur, 2.5)}
        for s in subs:
            all_subs.append({"start": s["start"] + t_global, "end": s["end"] + t_global, "text": s["text"]})

        # Nguồn hình của từng cảnh: phim gốc, hoặc bản đã được AI (VSR) xóa phụ đề
        srcs = [(video, a) for a, _d in pieces]
        seg_hs = hs_mode
        if hs_mode == "vsr":
            seg_hs = "blur"
            if vsr_ok:
                from . import vsr
                try:
                    srcs = [(str(vsr.clean_clip(video, a, d + 0.2, hardsub, opts.get("vsr_mode", "sttn-auto"),
                                                opts.get("vsr_dir", ""), work_dir, log, cancel)), 0.0)
                            for a, d in pieces]
                    seg_hs = "vsr"
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    vsr_ok = False
                    log(f"Không xóa được phụ đề bằng AI ({e}) - chuyển sang làm mờ dải phụ đề.", level="warn")
        # Cắt khung bám khuôn mặt (khi tỉ lệ khung đích khác phim gốc)
        face_crop, fkeys = "", None
        if opts.get("fill") == "face" and info.width and info.height and \
                abs(info.width / info.height - W / H) > 0.05:
            from . import reframe
            try:
                fkeys = reframe.concat_keys(
                    [(reframe.track(video, a, d + 0.2, info.width, info.height, parts_dir / "reframe"), d)
                     for a, d in pieces], speed)
                face_crop = reframe.crop_filter(fkeys, W, H)
            except Exception as e:  # noqa: BLE001
                log(f"Không dò được khuôn mặt ({e}) - cắt giữa khung.", level="warn")
        key = hashlib.sha1(json.dumps([seg, str(voice), voice and Path(voice).stat().st_size, pieces, need, dur, fkeys,
                                       pre_filter, hardsub, seg_hs, srcs,
                                       speed, W, H, fps, enc, opts.get("fill"), style, subs, title, logo,
                                       opts.get("logo_position"), opts.get("logo_scale"),
                                       opts.get("orig_volume_voice"), opts.get("orig_volume_clip"),
                                       opts.get("voice_volume"), opts.get("transition", "fade"), video],
                                      ensure_ascii=False,
                                      default=str).encode()).hexdigest()[:12]
        part = parts_dir / f"seg_{i:03d}_{key}.mp4"
        part_files.append(part)
        timeline.append([i, round(t_global, 2), round(dur, 2)])
        t_global += dur
        if part.exists() and part.stat().st_size > 1000:
            log(f"Đoạn {i + 1}: dùng lại bản đã dựng.", level="debug")
            continue
        for old in parts_dir.glob(f"seg_{i:03d}_*.mp4"):
            old.unlink(missing_ok=True)

        args = []
        for (sv, sa), (_a, d) in zip(srcs, pieces):
            args += ["-ss", f"{sa:.3f}", "-t", f"{d + 0.2:.3f}", "-i", sv]
        idx = len(pieces)
        voice_idx = logo_idx = None
        if voice:
            args += ["-i", str(voice)]
            voice_idx = idx
            idx += 1
        if logo:
            args += ["-i", logo]
            logo_idx = idx
            idx += 1
        # có dùng tiếng phim gốc trong đoạn này không (tắt hẳn khi thuyết minh -> không ghép tiếng gốc)
        use_orig_audio = info.has_audio and ((voice and float(opts.get("orig_volume_voice", 0.0)) > 0) or not voice)
        if len(pieces) > 1:  # ghép các cảnh của từng câu thành 1 đoạn
            fc = ""
            for k, (_a, d) in enumerate(pieces):
                fc += f"[{k}:v]trim=duration={d:.3f},setpts=PTS-STARTPTS,fps={fps},setsar=1[pv{k}];"
                if use_orig_audio:
                    fc += f"[{k}:a]atrim=duration={d:.3f},asetpts=PTS-STARTPTS,aresample=48000[pa{k}];"
            if use_orig_audio:
                fc += "".join(f"[pv{k}][pa{k}]" for k in range(len(pieces))) + \
                    f"concat=n={len(pieces)}:v=1:a=1[cv][ca];"
            else:
                fc += "".join(f"[pv{k}]" for k in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=0[cv];"
            vsrc, asrc = "[cv]", "[ca]"
        else:
            fc, vsrc, asrc = "", "[0:v]", "[0:a]"
        pf = pre_filter
        if pf and hardsub and seg_hs == "blur":  # che logo trước, rồi mới làm mờ dải phụ đề
            fc += f"{vsrc}{pf.rstrip(',')}[dl];"
            vsrc, pf = "[dl]", ""
        hs_graph, vsrc, hs_extra = _hardsub_filters(hardsub, seg_hs, info.width, info.height, vsrc)
        fc += hs_graph
        fc += _video_chain(W, H, opts.get("fill", "blur"), speed, fps, vsrc, pf + hs_extra, face_crop)
        ass_name = None
        if subs or title:
            ass_name = f"seg_{i:03d}.ass"
            write_ass(subs, parts_dir / ass_name, W, H, style, title)
        if logo_idx is not None:
            lw = max(16, int(W * float(opts.get("logo_scale", 0.12))) // 2 * 2)
            fc += f"[vb];[{logo_idx}:v]scale={lw}:-1,format=rgba[lg];[vb][lg]overlay={_logo_xy(opts.get('logo_position'))}"
        if ass_name:
            fc += f",subtitles=filename={ass_name}"
        if opts.get("transition", "fade") == "fade" and dur > 1.0:  # chuyển cảnh mềm giữa các đoạn
            fd = 0.12
            fc += f",fade=t=in:st=0:d={fd},fade=t=out:st={max(0.0, dur - fd):.3f}:d={fd}"
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
                fc += (f";{asrc}{tempo}aresample=48000,volume={ov_voice:.3f},apad[oa];{vchain};"
                       f"[oa][va]amix=inputs=2:normalize=0:duration=longest[a]")
            else:
                fc += f";{vchain.replace('[va]', '[a]')}"
        else:
            if info.has_audio:
                fc += f";{asrc}{tempo}aresample=48000,volume={ov_clip:.3f},afade=t=in:d=0.15,apad[a]"
            else:
                fc += ";anullsrc=r=48000:cl=stereo[a]"
        args += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", *enc,
                 "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                 part.name]
        jobs.append((i, args, dur))

    # Dựng các đoạn (song song nhiều đoạn cùng lúc nếu bật - tận dụng CPU nhiều luồng + bộ mã hóa GPU)
    workers = max(1, min(6, int(opts.get("parallel", 1) or 1)))
    if workers <= 1 or len(jobs) <= 1:
        for i, args, dur in jobs:
            run_ffmpeg(args, cancel=cancel, cwd=str(parts_dir), log=log, total=dur,
                       on_progress=lambda p, i=i: progress((i + p) / len(segs), f"Dựng đoạn {i + 1}/{len(segs)}"))
    elif jobs:
        from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait

        log(f"Dựng {len(jobs)} đoạn, {workers} đoạn song song...")
        done_n = [0]

        def one(job):
            _i, args, _d = job
            run_ffmpeg(args, cancel=cancel, cwd=str(parts_dir), log=log)
            done_n[0] += 1
            progress(done_n[0] / len(jobs) * 0.95, f"Dựng đoạn {done_n[0]}/{len(jobs)} ({workers} song song)")
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(one, j) for j in jobs]
            finished, _pending = wait(futs, return_when=FIRST_EXCEPTION)
            for f in finished:
                if f.exception():
                    cancel.set()  # dừng các đoạn còn lại rồi báo lỗi
                    for g in futs:
                        g.cancel()
                    raise f.exception()

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
    # cân bằng âm lượng tổng về chuẩn -16 LUFS (to đều, không lúc to lúc nhỏ)
    norm = ",loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000" if opts.get("loudnorm", True) else ""
    if music and Path(music).exists():
        progress(0.98, "Trộn nhạc nền")
        mv = float(opts.get("music_volume", 0.15))
        fade_st = max(0.0, t_global - 3)
        run_ffmpeg(["-i", str(joined), "-stream_loop", "-1", "-i", music, "-filter_complex",
                    f"[1:a]aresample=48000,volume={mv:.3f},afade=t=in:d=1.5,afade=t=out:st={fade_st:.2f}:d=3[m];"
                    f"[0:a][m]amix=inputs=2:normalize=0:duration=first{norm}[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{t_global:.3f}", "-movflags", "+faststart", str(out_path)], cancel=cancel, log=log)
    elif norm:
        progress(0.98, "Cân bằng âm lượng")
        run_ffmpeg(["-i", str(joined), "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", norm.lstrip(","),
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)], cancel=cancel, log=log)
    else:
        run_ffmpeg(["-i", str(joined), "-c", "copy", "-movflags", "+faststart", str(out_path)], cancel=cancel, log=log)
    joined.unlink(missing_ok=True)
    if all_subs:
        write_srt(all_subs, out_path.with_suffix(".srt"))
    st = footage.stats
    qa = {"segments": len(segs), "sentence_synced_segments": synced, "pieces": st["pieces"],
          "reused_seconds": round(st["reused_s"], 1), "blocked_seconds_used": round(st["blocked_s"], 1),
          "moved_to_fresh_footage": st["moved"], "duration": round(t_global, 1), "delogo": bool(pre_filter),
          "hardsub": hs_mode if hardsub else "none",
          "fit": {k: fit[k] for k in ("clip_k", "tempo", "drop")}, "timeline": timeline}
    if opts.get("final_qa", True):
        progress(0.99, "Kiểm tra chất lượng video")
        try:
            from .qa import check_output

            fq = check_output(str(out_path), opts.get("_target_seconds"))
            qa["final"] = fq
            for w in fq["warnings"]:
                log("⚠️ QA: " + w, level="warn")
            if fq["ok"]:
                log(f"✅ QA video: không màn hình đen/đứng hình bất thường · âm lượng {fq['loudness_lufs']} LUFS")
        except Exception as e:  # noqa: BLE001
            log(f"Bỏ qua kiểm tra chất lượng ({e}).", level="warn")
    (work_dir / "render_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        out_path.with_suffix(".qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    log(f"QA dựng: {synced}/{len(segs)} đoạn khớp hình theo câu · {st['pieces']} cảnh · lặp cảnh {st['reused_s']:.0f}s"
        f" · dính đoạn bị chặn {st['blocked_s']:.0f}s" + (" · đã che logo nguồn" if pre_filter else ""))
    progress(1.0, "Hoàn tất")
    log(f"✅ Đã xuất video: {out_path}  ({t_global:.1f} giây)")
    return out_path


def clear_render_cache(work_dir: Path) -> None:
    shutil.rmtree(work_dir / "render_parts", ignore_errors=True)
