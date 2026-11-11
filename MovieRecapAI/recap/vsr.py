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


SKIP_DIRS = {"site-packages", "Lib", "lib", "models", "__pycache__", ".git", "node_modules", "include", "share",
             "test", "design", "docker", "inpaint", "interface"}
PY_NAMES = ("python.exe", "python", "python3")


def _walk(base: Path, depth: int = 4):
    """Duyệt thư mục VSR (giới hạn độ sâu, bỏ thư mục thư viện/model rất lớn)."""
    stack = [(base, 0)]
    while stack:
        d, lv = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        yield d, entries
        if lv < depth:
            stack += [(Path(e.path), lv + 1) for e in entries if e.is_dir() and e.name not in SKIP_DIRS]


def find(vsr_dir: str) -> tuple[Path, Path, Path]:
    """Tìm (python, thư mục gốc VSR, file backend/main.py|.pyc) trong thư mục VSR người dùng chọn.

    Hỗ trợ: bản cài Setup.exe, bản giải nén .7z (QPT), bản chạy từ mã nguồn (venv)."""
    if not vsr_dir:
        raise VSRError("Chưa chọn thư mục video-subtitle-remover (VSR) trong mục Dựng video.")
    base = Path(vsr_dir.strip().strip('"'))
    if base.is_file():  # chọn nhầm file .exe -> lấy thư mục chứa nó
        base = base.parent
    if not base.is_dir():
        raise VSRError(f"Không thấy thư mục VSR: {vsr_dir}")
    mains, pythons, exes = [], [], []
    for d, entries in _walk(base):
        names = {e.name for e in entries}
        if d.name == "backend" and ("main.py" in names or "main.pyc" in names):
            mains.append(d / ("main.py" if "main.py" in names else "main.pyc"))
        for n in PY_NAMES:
            if n in names and (d / n).is_file():
                pythons.append(d / n)
                break
        exes += [d / n for n in names if n.lower().endswith(".exe") and not n.lower().startswith(("python", "unins"))]
    env_py = os.environ.get("MOVIE_RECAP_VSR_PYTHON")
    if env_py and Path(env_py).is_file():
        pythons.insert(0, Path(env_py))
    if not mains:
        hint = ""
        if exes:
            hint = (f"\n\nThư mục chỉ có chương trình đóng gói ({exes[0].name}), không có mã nguồn backend\\main.py nên "
                    "app không gọi tự động được. Cách khác: mở VSR, xóa phụ đề cả phim bằng giao diện của VSR (Mở → Chạy), "
                    "rồi đưa file *_no_sub.mp4 vào Movie Recap AI và chọn 'Không xử lý' ở mục phụ đề gốc.")
        raise VSRError(f"Không thấy backend\\main.py của VSR trong {base}.{hint}")
    main = mains[0]
    root = main.parent.parent
    if not pythons:
        raise VSRError(f"Thấy mã nguồn VSR ({root}) nhưng không thấy Python đi kèm. Hãy mở VSR một lần cho cài xong, "
                       "hoặc cài VSR theo hướng dẫn chạy từ mã nguồn (thư mục videoEnv).")

    def score(py: Path) -> tuple:  # ưu tiên Python nằm cùng thư mục VSR, gần gốc nhất
        try:
            rel = py.relative_to(root)
            return (0, len(rel.parts))
        except ValueError:
            return (1, len(py.parts))
    return sorted(pythons, key=score)[0], root, main


def check(vsr_dir: str) -> str:
    py, root, main = find(vsr_dir)
    return f"VSR: {root}\nMã chạy: {main}\nPython: {py}"


def _band_coords(band: dict, w: int, h: int) -> list[str]:
    y0 = max(0, int(band["y0"] * h))
    y1 = min(h, int(band["y1"] * h + 0.999))
    return [str(y0), str(y1), "0", str(w)]


def clean_clip(video: str, start: float, dur: float, band: dict, mode: str, vsr_dir: str, work_dir: Path,
               log, cancel) -> Path:
    """Cắt đoạn [start, start+dur] của phim, xóa phụ đề trong dải `band` bằng VSR, trả về file sạch (bắt đầu từ 0s)."""
    py, root, main = find(vsr_dir)
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
    cmd = [str(py), str(main), "-i", str(clip), "-o", str(tmp),
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
