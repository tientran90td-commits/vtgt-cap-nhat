"""Recap cả season: gộp nhiều tập thành 1 nguồn duy nhất (giữ mốc từng tập) để làm 1 video recap chung."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .ffmpeg_utils import Cancelled, _no_window_kwargs, ffmpeg_exe, probe, run_ffmpeg

# ------------------------------------------------------------------ tự dò OP / ED
# Nhạc mở đầu (OP) và kết thúc (ED) của phim bộ / anime LẶP LẠI y hệt ở mọi tập. Lấy "dấu vân tay âm thanh"
# (kiểu Haitsma-Kalker) của vài phút đầu & cuối mỗi tập, so từng cặp tập để tìm đoạn nhạc trùng nhau.
SR = 8000
HOP = 0.25          # giây giữa 2 khung vân tay
HEAD_S = 420.0      # tìm OP trong 7 phút đầu (có tập mở bằng cảnh mở màn rồi mới vào OP)
TAIL_S = 300.0      # tìm ED trong 5 phút cuối
MIN_SONG_S = 20.0   # đoạn trùng phải dài >= 20 giây mới coi là OP/ED
_POP = None


def _audio(path: str, start: float, dur: float, from_end: bool = False):
    import numpy as np

    pos = ["-sseof", f"-{dur:.1f}"] if from_end else ["-ss", f"{max(0.0, start):.2f}", "-t", f"{dur:.1f}"]
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", *pos, "-i", str(path), "-vn", "-sn",
           "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True, **_no_window_kwargs())
    return np.frombuffer(r.stdout, np.float32)


def fingerprint(x):
    """Mỗi khung 0.25s -> số 15 bit (dấu của độ chênh năng lượng giữa các dải tần theo thời gian)."""
    import numpy as np

    win, hop = 4096, int(SR * HOP)
    if len(x) < win + hop * 4:
        return np.zeros(0, np.int32)
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    spec = np.abs(np.fft.rfft(x[idx] * np.hanning(win), axis=1)) ** 2
    freqs = np.fft.rfftfreq(win, 1 / SR)
    edges = np.logspace(np.log10(300), np.log10(3000), 17)
    bands = np.stack([spec[:, (freqs >= edges[b]) & (freqs < edges[b + 1])].sum(axis=1) for b in range(16)], axis=1)
    bands = np.log1p(bands)
    d = bands[:, :-1] - bands[:, 1:]
    bits = (d[1:] - d[:-1]) > 0
    return (bits * (1 << np.arange(15))).sum(axis=1).astype(np.int32)


def _ber(a, b):
    import numpy as np

    global _POP
    if _POP is None:
        _POP = np.array([bin(i).count("1") for i in range(1 << 15)], np.int8)
    return _POP[np.bitwise_xor(a, b) & 0x7FFF] / 15.0


def match(fa, fb, min_len: float = MIN_SONG_S):
    """Đoạn âm thanh trùng nhau dài nhất giữa 2 dãy vân tay -> ((a0, a1), (b0, b1)) theo giây, hoặc None."""
    import numpy as np
    from collections import Counter, defaultdict

    if len(fa) < 10 or len(fb) < 10:
        return None
    where = defaultdict(list)
    for i, v in enumerate(fa.tolist()):
        if len(where[v]) < 12:
            where[v].append(i)
    votes = Counter()
    for j, v in enumerate(fb.tolist()):
        for i in where.get(v, ()):
            votes[i - j] += 1
    min_frames = int(min_len / HOP)
    best = None
    for off, _n in votes.most_common(5):
        j0, j1 = max(0, -off), min(len(fb), len(fa) - off)
        if j1 - j0 < min_frames:
            continue
        ber = _ber(fa[j0 + off:j1 + off], fb[j0:j1])
        sm = np.convolve(ber, np.ones(9) / 9, mode="same")
        good = sm < 0.3
        # đoạn "khớp" dài nhất (cho phép hở ngắn <= 2 giây)
        runs, s0, gap = [], None, 0
        for k, g in enumerate(good):
            if g:
                if s0 is None:
                    s0 = k
                gap = 0
            elif s0 is not None:
                gap += 1
                if gap > int(2 / HOP):
                    runs.append((s0, k - gap))
                    s0, gap = None, 0
        if s0 is not None:
            runs.append((s0, len(good) - 1 - gap))
        for s_, e_ in runs:
            if e_ - s_ >= min_frames and (best is None or e_ - s_ > best[1] - best[0]):
                best = (s_ + j0, e_ + j0, off)
    if not best:
        return None
    b0, b1, off = best
    # +1 khung vì vân tay khung k so khung k với k-1
    t = lambda k: round((k + 1) * HOP, 2)  # noqa: E731
    return (t(b0 + off), t(b1 + off)), (t(b0), t(b1))


def detect_op_ed(files: list[str], durations: list[float], log, progress, cancel) -> list[dict]:
    """Tự dò OP/ED từng tập (giây tính trong tập). [{'op': [s, e] | None, 'ed': [s, e] | None}]"""
    n = len(files)
    heads, tails = [], []
    for i, f in enumerate(files):
        if cancel.is_set():
            raise Cancelled()
        progress(0.05 + 0.25 * i / max(1, n), f"Nghe nhạc mở đầu/kết thúc tập {i + 1}/{n}")
        heads.append(fingerprint(_audio(f, 0, min(HEAD_S, durations[i] * 0.6))))
        tail_s = min(TAIL_S, durations[i] * 0.45)
        tails.append((fingerprint(_audio(f, 0, tail_s, from_end=True)), durations[i] - tail_s))
    res = [{"op": None, "ed": None} for _ in files]

    def best_for(i, kind):
        found = []
        for j in [k for k in (i + 1, i - 1, i + 2, i - 2) if 0 <= k < n]:
            if kind == "op":
                m = match(heads[i], heads[j])
                if m:
                    found.append(m[0])
            else:
                m = match(tails[i][0], tails[j][0])
                if m:
                    found.append((m[0][0] + tails[i][1], m[0][1] + tails[i][1]))
            if len(found) >= 2:
                break
        if not found:
            return None
        s0, e0 = max(found, key=lambda r: r[1] - r[0])
        return [round(max(0.0, s0 - 0.5), 2), round(min(durations[i], e0 + 0.5), 2)]
    for i in range(n):
        if cancel.is_set():
            raise Cancelled()
        res[i]["op"] = best_for(i, "op")
        res[i]["ed"] = best_for(i, "ed")
    found_op = sum(1 for r in res if r["op"])
    found_ed = sum(1 for r in res if r["ed"])
    log(f"🎵 Tự dò: OP ở {found_op}/{n} tập, ED ở {found_ed}/{n} tập.")
    return res


def natural_key(p) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", Path(p).name)]


def episode_title(path: str, i: int) -> str:
    stem = Path(path).stem
    m = re.search(r"(?:tập|tap|ep(?:isode)?|e)\s*0*(\d{1,3})", stem, re.I)
    return f"Tập {m.group(1)}" if m else f"Tập {i + 1}"


def op_ed_ranges(files, infos, skip_op, skip_ed, auto_detect, log, progress, cancel) -> list[dict]:
    """OP/ED từng tập: tự dò bằng âm thanh, tập nào không dò được thì dùng số giây cố định."""
    det = [{"op": None, "ed": None} for _ in files]
    if auto_detect and len(files) >= 2:
        try:
            det = detect_op_ed(files, [x.duration for x in infos], log, progress, cancel)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"Không tự dò được OP/ED ({e}) - dùng số giây cố định.", level="warn")
    out = []
    for d, x in zip(det, infos):
        op = d.get("op") or ([0.0, min(x.duration, float(skip_op))] if skip_op > 0 else None)
        ed = d.get("ed") or ([max(0.0, x.duration - float(skip_ed)), x.duration] if skip_ed > 0 else None)
        out.append({"op": op, "ed": ed, "op_auto": bool(d.get("op")), "ed_auto": bool(d.get("ed"))})
    return out


def join_episodes(files: list[str], out: Path, skip_op: float, skip_ed: float, log, progress, cancel,
                  auto_detect: bool = True, exact: bool = False, encoder: list[str] | None = None) -> dict:
    """Nối các tập thành 1 video dài, bỏ OP/ED (không tóm tắt)."""
    files = sorted(files, key=natural_key)
    infos = [probe(f) for f in files]
    cuts = op_ed_ranges(files, infos, skip_op, skip_ed, auto_detect, log, lambda p, m="": progress(p * 0.3, m), cancel)
    ranges = []  # (file, start, end)
    for f, x, c in zip(files, infos, cuts):
        keep = [[0.0, x.duration]]
        for cut in (c["op"], c["ed"]):
            if not cut:
                continue
            nk = []
            for a, b in keep:
                if cut[1] <= a or cut[0] >= b:
                    nk.append([a, b])
                    continue
                if cut[0] - a > 1:
                    nk.append([a, cut[0]])
                if b - cut[1] > 1:
                    nk.append([cut[1], b])
            keep = nk
        ranges += [(f, a, b) for a, b in keep if b - a > 1]
    total = sum(b - a for _f, a, b in ranges)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    same = len({(x.width, x.height, round(x.fps or 0, 2), x.has_audio, Path(x.path).suffix.lower())
                for x in infos}) == 1
    log(f"🔗 Nối {len(files)} tập → {total / 60:.0f} phút (đã bỏ {sum(x.duration for x in infos) / 60 - total / 60:.0f} "
        "phút OP/ED)" + ("" if (same and not exact) else " · mã hóa lại"))
    prog = lambda p: progress(0.3 + 0.7 * p, "Nối các tập")  # noqa: E731
    if same and not exact:
        lst = out.with_suffix(".concat.txt")
        lst.write_text("".join("file '{}'\ninpoint {:.3f}\noutpoint {:.3f}\n".format(
            str(Path(f).resolve()).replace("'", "'\\''"), a, b) for f, a, b in ranges), encoding="utf-8")
        try:
            run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-map", "0:v:0", "-map", "0:a:0?",
                        "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", str(out)], cancel=cancel,
                       total=total, log=log, on_progress=prog)
        finally:
            lst.unlink(missing_ok=True)
    else:
        W = max(x.width for x in infos) or 1920
        H = max(x.height for x in infos) or 1080
        args, fc = [], ""
        for k, (f, a, b) in enumerate(ranges):
            x = infos[files.index(f)]
            args += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", f]
            fc += (f"[{k}:v:0]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                   f"setsar=1,fps=25[v{k}];")
            fc += (f"[{k}:a:0]aresample=48000,aformat=channel_layouts=stereo[a{k}];" if x.has_audio else
                   f"anullsrc=r=48000:cl=stereo,atrim=duration={b - a:.2f}[a{k}];")
        fc += "".join(f"[v{k}][a{k}]" for k in range(len(ranges))) + f"concat=n={len(ranges)}:v=1:a=1[v][a]"
        enc = encoder or ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        run_ffmpeg([*args, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *enc, "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(out)], cancel=cancel, total=total, log=log, on_progress=prog)
    progress(1.0, "Đã nối xong")
    return {"video": str(out), "duration": round(total, 1), "cuts": cuts, "joined": True}


def build_season(files: list[str], out_dir: Path, skip_op: float, skip_ed: float, log, progress, cancel,
                 auto_detect: bool = True) -> dict:
    files = sorted(files, key=natural_key)
    infos = []
    for i, f in enumerate(files):
        if cancel.is_set():
            raise Cancelled()
        infos.append(probe(f))
        progress(0.05 * (i + 1) / len(files), f"Đọc tập {i + 1}/{len(files)}")
    cuts = op_ed_ranges(files, infos, skip_op, skip_ed, auto_detect, log,
                        lambda p, m="": progress(0.05 + 0.25 * p, m), cancel)
    progress = (lambda prog: (lambda p, m="": prog(0.3 + 0.7 * p, m)))(progress)
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
    for ep, c in zip(episodes, cuts):
        ep["op"], ep["ed"] = c["op"], c["ed"]
        for cut in (c["op"], c["ed"]):
            if cut:
                exclusions.append([round(ep["start"] + cut[0], 2), round(ep["start"] + cut[1], 2)])
    meta = {"episodes": episodes, "exclusions": exclusions, "skip_op": skip_op, "skip_ed": skip_ed,
            "auto_detected": sum(1 for c in cuts if c["op_auto"] or c["ed_auto"])}
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
