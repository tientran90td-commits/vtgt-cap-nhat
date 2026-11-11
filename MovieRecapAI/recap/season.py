"""Recap cả season: gộp nhiều tập thành 1 nguồn duy nhất (giữ mốc từng tập) để làm 1 video recap chung."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .ffmpeg_utils import Cancelled, probe, run_ffmpeg


def natural_key(p) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", Path(p).name)]


def episode_title(path: str, i: int) -> str:
    stem = Path(path).stem
    m = re.search(r"(?:tập|tap|ep(?:isode)?|e)\s*0*(\d{1,3})", stem, re.I)
    return f"Tập {m.group(1)}" if m else f"Tập {i + 1}"


def build_season(files: list[str], out_dir: Path, skip_op: float, skip_ed: float, log, progress, cancel) -> dict:
    files = sorted(files, key=natural_key)
    infos = []
    for i, f in enumerate(files):
        if cancel.is_set():
            raise Cancelled()
        infos.append(probe(f))
        progress(0.05 * (i + 1) / len(files), f"Đọc tập {i + 1}/{len(files)}")
    out_dir.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\-]+", "_", Path(files[0]).stem)[:40] + f"_season_{len(files)}tap.mp4"
    out = out_dir / name
    total = sum(x.duration for x in infos)
    lst = out_dir / (out.stem + ".txt")
    lst.write_text("".join("file '{}'\n".format(str(Path(f).resolve()).replace("'", "'\\''")) for f in files),
                   encoding="utf-8")
    same = len({(x.width, x.height, round(x.fps or 0, 2), x.has_audio) for x in infos}) == 1
    if not out.exists() or out.stat().st_size < 1000:
        ok = False
        if same:
            try:
                log(f"Gộp {len(files)} tập (sao chép nhanh, không mã hóa lại)...")
                run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-map", "0:v:0", "-map", "0:a:0?",
                            "-movflags", "+faststart", str(out)], cancel=cancel, total=total, log=log,
                           on_progress=lambda p: progress(0.05 + 0.9 * p, "Gộp các tập"))
                ok = abs(probe(out).duration - total) < max(5.0, total * 0.01)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Gộp nhanh lỗi ({e}) - chuyển sang mã hóa lại.", level="warn")
        if not ok:
            W = max(x.width for x in infos) or 1920
            H = max(x.height for x in infos) or 1080
            log(f"Các tập khác định dạng - mã hóa lại về {W}x{H} (lâu hơn)...")
            args, fc = [], ""
            for i, f in enumerate(files):
                args += ["-i", f]
                fc += (f"[{i}:v:0]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                       f"setsar=1,fps=25[v{i}];")
                fc += (f"[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo[a{i}];" if infos[i].has_audio else
                       f"anullsrc=r=48000:cl=stereo,atrim=duration={infos[i].duration:.2f}[a{i}];")
            fc += "".join(f"[v{i}][a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=1:a=1[v][a]"
            run_ffmpeg([*args, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset",
                        "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)],
                       cancel=cancel, total=total, log=log, on_progress=lambda p: progress(0.05 + 0.9 * p, "Gộp các tập"))
    episodes, t = [], 0.0
    for i, (f, x) in enumerate(zip(files, infos)):
        episodes.append({"index": i + 1, "title": episode_title(f, i), "file": str(f), "start": round(t, 3),
                         "end": round(t + x.duration, 3)})
        t += x.duration
    exclusions = []
    for ep in episodes:
        if skip_op > 0:
            exclusions.append([ep["start"], min(ep["end"], ep["start"] + skip_op)])
        if skip_ed > 0:
            exclusions.append([max(ep["start"], ep["end"] - skip_ed), ep["end"]])
    meta = {"episodes": episodes, "exclusions": exclusions, "skip_op": skip_op, "skip_ed": skip_ed}
    out.with_suffix(".season.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(1.0, "Đã gộp xong")
    log(f"📚 Đã gộp {len(files)} tập ({total / 60:.0f} phút) -> {out.name}")
    return {"video": str(out), **meta}


def load_season_meta(video: str) -> dict | None:
    f = Path(video).with_suffix(".season.json")
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    return None
