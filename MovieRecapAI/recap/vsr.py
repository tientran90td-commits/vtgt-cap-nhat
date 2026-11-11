"""Xóa phụ đề in cứng bằng AI qua video-subtitle-remover (VSR - github.com/YaoFANGUK/video-subtitle-remover,
giấy phép Apache-2.0). VSR chạy như CÔNG CỤ NGOÀI (bộ cài riêng của VSR, có sẵn Python + model AI), app chỉ gọi
dòng lệnh `backend/main.py -i ... -o ... -c ymin ymax xmin xmax --inpaint-mode ...`.

Chỉ những đoạn phim THỰC SỰ được dùng trong video recap mới được xử lý (vài phút thay vì cả bộ phim 2 tiếng),
kết quả được lưu lại để lần dựng sau dùng lại ngay.
"""
from __future__ import annotations

import hashlib
import os
import re
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


def _clip_key(video: str, start: float, dur: float, band: dict, mode: str) -> str:
    st = os.stat(video)
    return hashlib.sha1(repr((str(video), st.st_size, int(st.st_mtime), round(start, 3), round(dur, 3),
                              band.get("y0"), band.get("y1"), mode)).encode()).hexdigest()[:14]


def cached(video: str, start: float, dur: float, band: dict, mode: str, work_dir: Path) -> Path | None:
    mode = mode if mode in MODES else "sttn-auto"
    out = Path(work_dir) / "vsr" / f"clean_{_clip_key(video, start, dur, band, mode)}.mp4"
    return out if out.exists() and out.stat().st_size > 1000 else None


def _prepare(vsr_dir: str, settings, log):
    py, root, main = find(resolve_dir(vsr_dir, settings))
    if str(root) not in _patched:
        _patched.add(str(root))
        if _py_ver(str(py)) not in ("3.12", "3.13", "3.14"):
            n = compat_patch(root)
            if n:
                log(f"Đã vá {n} dòng mã VSR cho tương thích Python {_py_ver(str(py))}.", level="debug")
    return py, root, main


def _run_vsr(py, root, main, src: Path, dst: Path, band: dict, mode: str, total: float, log, cancel, progress=None):
    info = probe(src)
    dst.unlink(missing_ok=True)
    cmd = [str(py), str(main), "-i", str(src), "-o", str(dst),
           "-c", *_band_coords(band, info.width, info.height), "--inpaint-mode", mode]
    env = dict(os.environ, PYTHONPATH=str(root) + os.pathsep + os.environ.get("PYTHONPATH", ""),
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    t0 = time.time()
    proc = subprocess.Popen(cmd, cwd=str(root), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, **_no_window_kwargs())
    tail: list[str] = []
    beat = 30.0
    import queue
    import threading

    q: queue.Queue = queue.Queue()

    def reader():  # đọc kết quả VSR ở luồng phụ để vòng chính luôn kiểm tra được nút Hủy
        try:
            for raw in iter(proc.stdout.readline, b""):
                q.put(raw)
        finally:
            q.put(None)
    threading.Thread(target=reader, daemon=True).start()
    try:
        while True:
            try:
                raw = q.get(timeout=1.0)
            except queue.Empty:
                raw = b""
            if raw is None:
                break
            line = raw.decode("utf-8", "replace").strip()
            if line:
                tail = (tail + [line])[-12:]
                m = re.search(r"(\d{1,3})%\|", line) or re.search(r"[Pp]rogress[^0-9]*(\d{1,3})", line)
                if m and progress:
                    progress(min(0.99, int(m.group(1)) / 100), f"AI xóa phụ đề {int(m.group(1))}%")
            el = time.time() - t0
            if el > beat:
                beat += 30.0
                log(f"⏳ VSR đang xóa phụ đề {total:.0f}s phim... {int(el)}s")
            if cancel is not None and cancel.is_set():
                proc.kill()
                raise Cancelled()
            if el > 900 + total * 60:
                proc.kill()
                raise VSRError("VSR chạy quá lâu - đã dừng.")
    finally:
        try:
            proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        proc.wait()
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size < 1000:
        raise VSRError("VSR lỗi (mã %s):\n%s" % (proc.returncode, "\n".join(tail[-6:])))
    try:
        if probe(dst).duration < total * 0.8:
            raise VSRError("VSR trả về video ngắn bất thường.")
    except VSRError:
        raise
    except Exception as e:  # noqa: BLE001
        raise VSRError(f"Video VSR trả về bị hỏng: {e}") from e
    return time.time() - t0


_ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-ac", "2"]


def clean_batch(video: str, clips: list[tuple[float, float]], band: dict, mode: str, vsr_dir: str, work_dir: Path,
                log, cancel, settings=None, progress=None) -> dict:
    """Xóa phụ đề NHIỀU đoạn trong MỘT lần chạy VSR (chỉ nạp model AI 1 lần - nhanh hơn rất nhiều so với
    chạy riêng từng đoạn). Trả về {(start, dur): file sạch}."""
    mode = mode if mode in MODES else "sttn-auto"
    out_dir = Path(work_dir) / "vsr"
    out_dir.mkdir(parents=True, exist_ok=True)
    res, todo = {}, []
    for a, d in dict.fromkeys((round(a, 3), round(d, 3)) for a, d in clips):
        c = cached(video, a, d, band, mode, work_dir)
        if c:
            res[(a, d)] = c
        else:
            todo.append((a, d))
    if not todo:
        return res
    py, root, main = _prepare(vsr_dir, settings, log)
    total = sum(d for _a, d in todo)
    log(f"🧽 AI xóa phụ đề {len(todo)} đoạn ({total:.0f}s phim) trong 1 lần chạy VSR {mode}...")
    tag = hashlib.sha1(repr(todo).encode()).hexdigest()[:10]
    pieces, offsets, off = [], [], 0.0
    for k, (a, d) in enumerate(todo):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        f = out_dir / f"in_{tag}_{k:03d}.mp4"
        run_ffmpeg(["-ss", f"{max(0.0, a):.3f}", "-t", f"{d:.3f}", "-i", str(video), "-map", "0:v:0", "-map", "0:a:0?",
                    *_ENC, str(f)], cancel=cancel)
        dd = probe(f).duration or d
        pieces.append(f)
        offsets.append((off, dd))
        off += dd
    lst = out_dir / f"in_{tag}.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in pieces), encoding="utf-8")
    batch_in, batch_out = out_dir / f"batch_{tag}.mp4", out_dir / f"batch_{tag}_clean.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", batch_in.name], cancel=cancel,
               cwd=str(out_dir))
    took = _run_vsr(py, root, main, batch_in, batch_out, band, mode, off, log, cancel, progress)
    for (a, d), (o, dd) in zip(todo, offsets):
        dest = out_dir / f"clean_{_clip_key(video, a, d, band, mode)}.mp4"
        tmp = dest.with_name(dest.stem + "_tmp.mp4")
        run_ffmpeg(["-ss", f"{o:.3f}", "-t", f"{dd:.3f}", "-i", str(batch_out), *_ENC, str(tmp)], cancel=cancel)
        os.replace(tmp, dest)
        res[(a, d)] = dest
    for f in [*pieces, lst, batch_in, batch_out]:
        Path(f).unlink(missing_ok=True)
    log(f"VSR xong {len(todo)} đoạn trong {took:.0f}s.")
    return res


def clean_clip(video: str, start: float, dur: float, band: dict, mode: str, vsr_dir: str, work_dir: Path,
               log, cancel, settings=None) -> Path:
    """Xóa phụ đề 1 đoạn [start, start+dur] (bắt đầu từ 0s)."""
    return clean_batch(video, [(start, dur)], band, mode, vsr_dir, work_dir, log, cancel, settings)[
        (round(start, 3), round(dur, 3))]


# ------------------------------------------------------------------ tự cài VSR từ mã nguồn
def accelerator() -> str:
    """cuda (card NVIDIA) | directml (Windows: card AMD/Intel) | cpu"""
    if shutil.which("nvidia-smi"):
        return "cuda"
    return "directml" if os.name == "nt" else "cpu"


def _py_ver(py: str) -> str:
    try:
        return subprocess.run([py, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"], capture_output=True,
                              text=True, timeout=60, **_no_window_kwargs()).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _base_python(accel: str, log) -> str:
    """VSR cần Python 3.12 (mã nguồn dùng cú pháp f-string mới; torch-directml chỉ có tới 3.12)."""
    from .components import pip_install, python_exe

    py = python_exe()
    if _py_ver(py) == "3.12":
        return py
    if shutil.which("py"):  # trình khởi chạy py của Windows: có sẵn Python 3.12 không
        try:
            r = subprocess.run(["py", "-3.12", "-c", "import sys;print(sys.executable)"], capture_output=True,
                               text=True, timeout=60, **_no_window_kwargs())
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    # tự tải Python 3.12 độc lập bằng uv (không đụng tới Python của máy)
    try:
        log("Tải Python 3.12 riêng cho VSR (qua uv)...")
        pip_install(["uv"], log)
        uv = [python_exe(), "-m", "uv"]
        subprocess.run(uv + ["python", "install", "3.12"], check=True, capture_output=True, timeout=1800,
                       **_no_window_kwargs())
        r = subprocess.run(uv + ["python", "find", "3.12"], capture_output=True, text=True, timeout=120,
                           **_no_window_kwargs())
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[-1]
    except Exception as e:  # noqa: BLE001
        log(f"Không tải được Python 3.12 ({e}) - dùng Python hiện có, app sẽ tự vá mã VSR cho tương thích.",
            level="warn")
    return py


def compat_patch(root: Path) -> int:
    """Vá cú pháp f-string kiểu Python 3.12 (f'..{x['k']}..') để VSR chạy được trên Python 3.10/3.11."""
    import re

    fixed = 0
    pat = re.compile(r"\{([^{}'\"]*)\['([^'\"]+)'\]([^{}]*)\}")
    for f in (Path(root) / "backend").rglob("*.py"):
        try:
            src = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out = []
        changed = False
        for line in src.splitlines(keepends=True):
            if "f'" in line and "['" in line:
                i = line.find("f'")
                head, tail = line[:i], line[i:]
                new = pat.sub(lambda m: "{" + m.group(1) + '["' + m.group(2) + '"]' + m.group(3) + "}", tail)
                if new != tail:
                    line, changed = head + new, True
                    fixed += 1
            out.append(line)
        if changed:
            f.write_text("".join(out), encoding="utf-8")
    return fixed


_patched: set = set()


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
    if ver not in ("3.12", "3.13", "3.14"):
        compat_patch(root)
    settings.set("render", "vsr_dir", str(root))
    progress(1.0, "Đã cài VSR")
    log(f"✅ Đã cài video-subtitle-remover ({'DirectML - dùng card đồ họa' if accel == 'directml' else accel.upper()}) "
        f"tại {root}")
    return str(root)
