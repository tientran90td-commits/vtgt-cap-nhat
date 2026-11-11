"""Xóa phụ đề in cứng bằng AI qua video-subtitle-remover (VSR - github.com/YaoFANGUK/video-subtitle-remover,
giấy phép Apache-2.0). VSR chạy như CÔNG CỤ NGOÀI (bộ cài riêng của VSR, có sẵn Python + model AI), app chỉ gọi
dòng lệnh `backend/main.py -i ... -o ... -c ymin ymax xmin xmax --inpaint-mode ...`.

Chỉ những đoạn phim THỰC SỰ được dùng trong video recap mới được xử lý (vài phút thay vì cả bộ phim 2 tiếng),
kết quả được lưu lại để lần dựng sau dùng lại ngay.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .ffmpeg_utils import Cancelled, _no_window_kwargs, probe, run_ffmpeg

RELEASES_URL = "https://github.com/YaoFANGUK/video-subtitle-remover/releases"
VSR_TAG = "1.4.0"
SOURCE_ZIP = f"https://codeload.github.com/YaoFANGUK/video-subtitle-remover/zip/refs/tags/{VSR_TAG}"
NAME_HINTS = ("字幕", "subtitle", "vsr")
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


def managed_dir(settings) -> Path:
    """Nơi app tự cài VSR (từ mã nguồn, kèm môi trường Python riêng)."""
    return settings.models_dir() / "vsr"


def _registry_dirs() -> list[Path]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    out = []
    keys = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall")]
    for hive, path in keys:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                k = winreg.OpenKey(root, winreg.EnumKey(root, i))
                name = str(winreg.QueryValueEx(k, "DisplayName")[0])
            except OSError:
                continue
            if not any(h in name.lower() for h in NAME_HINTS):
                continue
            for val in ("InstallLocation", "DisplayIcon", "UninstallString"):
                try:
                    v = str(winreg.QueryValueEx(k, val)[0]).split(",")[0].strip().strip('"')
                except OSError:
                    continue
                if v:
                    pth = Path(v)
                    out.append(pth if pth.is_dir() else pth.parent)
    return out


def candidates(settings=None) -> list[Path]:
    """Các thư mục có thể chứa VSR: bản app tự cài, bản Setup.exe (registry), thư mục ở gốc các ổ đĩa."""
    found: list[Path] = []
    if settings is not None:
        found.append(managed_dir(settings))
    found += _registry_dirs()
    roots = []
    if os.name == "nt":
        roots = [Path(f"{c}:\\") for c in "CDEFGHIJ"]
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            if os.environ.get(env):
                roots.append(Path(os.environ[env]) / ("Programs" if env == "LOCALAPPDATA" else ""))
    roots += [Path.home(), Path.home() / "Desktop", Path.home() / "Downloads"]
    for r in roots:
        try:
            for e in os.scandir(r):
                if e.is_dir() and any(h in e.name.lower() for h in NAME_HINTS):
                    found.append(Path(e.path))
        except OSError:
            continue
    seen, out = set(), []
    for f in found:
        k = str(f).lower()
        if k not in seen and f.is_dir():
            seen.add(k)
            out.append(f)
    return out


def autodetect(settings=None) -> tuple[str, str]:
    """Tự tìm VSR dùng được trên máy. Trả về (thư mục, lỗi của ứng viên đầu tiên nếu không dùng được)."""
    first_err = ""
    for c in candidates(settings):
        try:
            find(str(c))
            return str(c), ""
        except VSRError as e:
            first_err = first_err or str(e)
    return "", first_err


def resolve_dir(vsr_dir: str, settings=None) -> str:
    """Thư mục VSR dùng thật: cái người dùng chọn (nếu dùng được), không thì tự tìm."""
    if vsr_dir:
        try:
            find(vsr_dir)
            return vsr_dir
        except VSRError:
            pass
    found, _err = autodetect(settings)
    return found or vsr_dir


def check(vsr_dir: str) -> str:
    py, root, main = find(vsr_dir)
    return f"VSR: {root}\nMã chạy: {main}\nPython: {py}"


def _band_coords(band: dict, w: int, h: int) -> list[str]:
    y0 = max(0, int(band["y0"] * h))
    y1 = min(h, int(band["y1"] * h + 0.999))
    return [str(y0), str(y1), "0", str(w)]


def clean_clip(video: str, start: float, dur: float, band: dict, mode: str, vsr_dir: str, work_dir: Path,
               log, cancel, settings=None) -> Path:
    """Cắt đoạn [start, start+dur] của phim, xóa phụ đề trong dải `band` bằng VSR, trả về file sạch (bắt đầu từ 0s)."""
    py, root, main = find(resolve_dir(vsr_dir, settings))
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


# ------------------------------------------------------------------ tự cài VSR từ mã nguồn
def accelerator() -> str:
    """cuda (card NVIDIA) | directml (Windows: card AMD/Intel) | cpu"""
    if shutil.which("nvidia-smi"):
        return "cuda"
    return "directml" if os.name == "nt" else "cpu"


def _base_python(accel: str, log) -> str:
    from .components import python_exe

    py = python_exe()
    ver = subprocess.run([py, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"], capture_output=True,
                         text=True, **_no_window_kwargs()).stdout.strip()
    if accel == "directml" and ver not in ("3.10", "3.11", "3.12") and shutil.which("py"):
        # torch-directml chỉ có cho Python 3.10-3.12 -> thử Python 3.12 qua trình khởi chạy py của Windows
        r = subprocess.run(["py", "-3.12", "-c", "import sys;print(sys.executable)"], capture_output=True, text=True,
                           **_no_window_kwargs())
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        log(f"Python {ver} chưa có bản DirectML - VSR sẽ chạy bằng CPU (cài Python 3.12 để dùng card AMD).",
            level="warn")
    return py


def install(settings, log, progress, cancel, accel: str = "auto") -> str:
    """Tải mã nguồn VSR + tạo môi trường Python riêng + cài thư viện (DirectML cho card AMD). Trả về thư mục VSR."""
    import io
    import zipfile

    import requests

    from .components import pip_install

    accel = accelerator() if accel == "auto" else accel
    base = managed_dir(settings)
    root = base / f"video-subtitle-remover-{VSR_TAG}"
    if not (root / "backend" / "main.py").exists():
        log(f"Tải mã nguồn video-subtitle-remover {VSR_TAG} (kèm model AI, khoảng 800 MB)...")
        sess = requests.Session()
        proxy = (settings.get("api", "proxy") or "").strip()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        buf = io.BytesIO()
        with sess.get(SOURCE_ZIP, stream=True, timeout=120) as r:
            if r.status_code != 200:
                raise VSRError(f"Tải VSR lỗi HTTP {r.status_code}")
            total = int(r.headers.get("content-length") or 0)
            for chunk in r.iter_content(1 << 20):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                buf.write(chunk)
                mb = buf.tell() / 1e6
                progress(min(0.4, 0.4 * buf.tell() / total) if total else min(0.4, mb / 2000),
                         f"Tải VSR {mb:.0f} MB")
        progress(0.42, "Giải nén VSR")
        base.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(buf) as z:
            for m in z.infolist():
                dest = (base / m.filename).resolve()
                if base.resolve() not in dest.parents and dest != base.resolve():
                    continue  # bỏ đường dẫn lạ trong file nén
                z.extract(m, base)
        found = next((p.parent.parent for p in base.glob("*/backend/main.py")), None)
        if found is None:
            raise VSRError("File tải về không có backend/main.py")
        if found != root:
            found.rename(root)
    env = root / "videoEnv"
    py = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        progress(0.45, "Tạo môi trường Python cho VSR")
        r = subprocess.run([_base_python(accel, log), "-m", "venv", str(env)], capture_output=True, text=True,
                           **_no_window_kwargs())
        if r.returncode != 0:
            raise VSRError("Tạo môi trường Python lỗi:\n" + (r.stderr or r.stdout)[-500:])
    ver = subprocess.run([str(py), "-c", "import sys;print('%d.%d' % sys.version_info[:2])"], capture_output=True,
                         text=True, **_no_window_kwargs()).stdout.strip()
    if accel == "directml" and ver not in ("3.10", "3.11", "3.12"):
        accel = "cpu"

    def pip(pk, frac, msg):
        progress(frac, msg)
        pip_install(pk, log, None, cancel, python=str(py))
    pip(["--upgrade", "pip"], 0.47, "Cập nhật pip")
    pip(["paddlepaddle==3.0.0"], 0.5, "Cài PaddlePaddle (dò chữ)")
    if accel == "directml":
        pip(["torch_directml==0.2.5.dev240914"], 0.6, "Cài PyTorch DirectML (card AMD/Intel)")
    elif accel == "cuda":
        pip(["torch==2.7.0", "torchvision==0.22.0", "--index-url", "https://download.pytorch.org/whl/cu126"], 0.6,
            "Cài PyTorch CUDA (card NVIDIA)")
    else:
        # Windows/macOS: bản trên PyPI vốn là bản CPU; Linux thì lấy bản CPU riêng cho nhẹ
        extra = ["--index-url", "https://download.pytorch.org/whl/cpu"] if sys.platform.startswith("linux") else []
        pip(["torch==2.7.0", "torchvision==0.22.0", *extra], 0.6, "Cài PyTorch (CPU)")
    pip(["-r", str(root / "requirements.txt")], 0.8, "Cài thư viện của VSR")
    if accel == "directml":
        pip(["onnxruntime-directml==1.20.1"], 0.9, "Cài ONNX Runtime DirectML")
    settings.set("render", "vsr_dir", str(root))
    progress(1.0, "Đã cài VSR")
    log(f"✅ Đã cài video-subtitle-remover ({'DirectML - dùng card đồ họa' if accel == 'directml' else accel.upper()}) "
        f"tại {root}")
    return str(root)
