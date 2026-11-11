"""Xóa phụ đề in cứng bằng AI qua video-subtitle-remover (VSR - github.com/YaoFANGUK/video-subtitle-remover,
giấy phép Apache-2.0). VSR chạy như CÔNG CỤ NGOÀI (bộ cài riêng của VSR, có sẵn Python + model AI), app chỉ gọi
dòng lệnh `backend/main.py -i ... -o ... -c ymin ymax xmin xmax --inpaint-mode ...`.

Chỉ những đoạn phim THỰC SỰ được dùng trong video recap mới được xử lý (vài phút thay vì cả bộ phim 2 tiếng),
kết quả được lưu lại để lần dựng sau dùng lại ngay.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

from .ffmpeg_utils import Cancelled, _no_window_kwargs, probe, run_ffmpeg

RELEASES_URL = "https://github.com/YaoFANGUK/video-subtitle-remover/releases"
MODES = {
    "sttn-auto": "STTN tự dò (nhanh, khuyên dùng)",
    "sttn-det": "STTN theo vùng chữ (nhanh, giữ nền tốt hơn)",
    "lama": "LaMa (đẹp hơn, chậm)",
    "propainter": "ProPainter (đẹp nhất, rất chậm, cần GPU mạnh)",
    "opencv": "OpenCV (nhanh nhất, chất lượng thấp)",
}


class VSRError(RuntimeError):
    pass


def _python_candidates(root: Path):
    names = ["python.exe", "python"] if os.name == "nt" else ["python", "python3", "python.exe"]
    for sub in ("Python", "python", "runtime", ".venv/Scripts", "venv/Scripts", "videoEnv/Scripts",
                ".venv/bin", "venv/bin", "videoEnv/bin", "Python/bin", ""):
        for n in names:
            yield root / sub / n


def find(vsr_dir: str) -> tuple[Path, Path]:
    """Tìm (python, thư mục gốc chứa backend/main.py) trong thư mục VSR người dùng chọn."""
    if not vsr_dir:
        raise VSRError("Chưa chọn thư mục video-subtitle-remover (VSR) trong mục Dựng video.")
    base = Path(vsr_dir)
    if not base.is_dir():
        raise VSRError(f"Không thấy thư mục VSR: {vsr_dir}")
    roots = [base] + [p for p in base.iterdir() if p.is_dir()]
    roots += [q for p in roots[1:] for q in p.iterdir() if q.is_dir()] if not (base / "backend" / "main.py").exists() else []
    root = next((r for r in roots if (r / "backend" / "main.py").exists()), None)
    if root is None:
        raise VSRError(f"Thư mục {vsr_dir} không có backend/main.py - hãy chọn thư mục đã giải nén của VSR.")
    for cand in [*_python_candidates(root), *(_python_candidates(base) if base != root else [])]:
        if cand.is_file():
            return cand, root
    env_py = os.environ.get("MOVIE_RECAP_VSR_PYTHON")
    if env_py and Path(env_py).is_file():
        return Path(env_py), root
    raise VSRError(f"Không thấy Python đi kèm VSR trong {root} (thư mục Python\\python.exe). Hãy mở VSR một lần "
                   "bằng file khởi động của nó cho cài xong, rồi thử lại.")


def check(vsr_dir: str) -> str:
    py, root = find(vsr_dir)
    return f"VSR: {root}\nPython: {py}"


def _band_coords(band: dict, w: int, h: int) -> list[str]:
    y0 = max(0, int(band["y0"] * h))
    y1 = min(h, int(band["y1"] * h + 0.999))
    return [str(y0), str(y1), "0", str(w)]


def clean_clip(video: str, start: float, dur: float, band: dict, mode: str, vsr_dir: str, work_dir: Path,
               log, cancel) -> Path:
    """Cắt đoạn [start, start+dur] của phim, xóa phụ đề trong dải `band` bằng VSR, trả về file sạch (bắt đầu từ 0s)."""
    py, root = find(vsr_dir)
    mode = mode if mode in MODES else "sttn-auto"
    st = os.stat(video)
    key = hashlib.sha1(repr((str(video), st.st_size, int(st.st_mtime), round(start, 3), round(dur, 3),
                             band.get("y0"), band.get("y1"), mode)).encode()).hexdigest()[:14]
    out_dir = Path(work_dir) / "vsr"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"clean_{key}.mp4"
    if out.exists() and out.stat().st_size > 1000:
        return out
    clip = out_dir / f"in_{key}.mp4"
    run_ffmpeg(["-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}", "-i", str(video), "-map", "0:v:0", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", str(clip)], cancel=cancel)
    info = probe(clip)
    tmp = out_dir / f"tmp_{key}.mp4"
    tmp.unlink(missing_ok=True)
    cmd = [str(py), str(root / "backend" / "main.py"), "-i", str(clip), "-o", str(tmp),
           "-c", *_band_coords(band, info.width, info.height), "--inpaint-mode", mode]
    env = dict(os.environ, PYTHONPATH=str(root) + os.pathsep + os.environ.get("PYTHONPATH", ""),
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    log(f"AI xóa phụ đề (VSR {mode}) đoạn {start:.0f}s-{start + dur:.0f}s...", level="debug")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=str(root), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, **_no_window_kwargs())
    tail: list[str] = []
    try:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if line:
                tail = (tail + [line])[-12:]
            if cancel is not None and cancel.is_set():
                proc.kill()
                raise Cancelled()
            if time.time() - t0 > 600 + dur * 120:
                proc.kill()
                raise VSRError("VSR chạy quá lâu - đã dừng.")
    finally:
        try:
            proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        proc.wait()
    if proc.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1000:
        raise VSRError("VSR lỗi (mã %s):\n%s" % (proc.returncode, "\n".join(tail[-6:])))
    try:
        if probe(tmp).duration < dur * 0.8:
            raise VSRError("VSR trả về video ngắn bất thường.")
    except VSRError:
        raise
    except Exception as e:  # noqa: BLE001
        raise VSRError(f"Video VSR trả về bị hỏng: {e}") from e
    os.replace(tmp, out)
    clip.unlink(missing_ok=True)
    log(f"VSR xong đoạn {start:.0f}s ({time.time() - t0:.0f}s xử lý).", level="debug")
    return out
