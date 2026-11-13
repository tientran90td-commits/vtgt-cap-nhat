"""Cập nhật trực tiếp trong app: bấm 1 nút -> tải bản mới từ GitHub -> chép đè -> khởi động lại.

- Thư mục cài bằng git -> `git pull`.
- Thư mục cài từ file zip -> tải bản mới nhất, sao lưu file cũ vào _backup/<phiên bản>/, chép đè mã nguồn mới
  (KHÔNG đụng tới .venv, cài đặt, dự án, model - chúng nằm ngoài thư mục mã nguồn), cài thêm thư viện mới nếu có.
- Lỗi giữa chừng: file cũ vẫn còn trong _backup, bấm "Quay lại bản cũ" để khôi phục.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

from . import VERSION
from .config import Settings
from .media import Cancelled, no_window

SUBDIR = "VietDub"
KEEP = {".venv", "venv", "_backup", "build", "dist", "__pycache__", ".git"}  # không bao giờ ghi đè/xóa
CODE_DIRS = ("vietdub", "ui", "tests")  # file .py không còn ở bản mới sẽ được dọn


class UpdateError(RuntimeError):
    pass


def app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def source(settings: Settings) -> tuple[str, str]:
    repo = (settings.get("update", "repo") or "tientran90td-commits/vtgt-cap-nhat").strip().strip("/")
    branch = (settings.get("update", "branch") or "claude/movie-summary-app-0q90dq").strip()
    return repo, branch


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    if settings.proxies():
        s.proxies = settings.proxies()
    s.headers["User-Agent"] = "VietDub-updater"
    return s


def vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4]) or (0,)


def check(settings: Settings) -> dict:
    """{'current', 'latest', 'newer', 'branch', 'repo', 'changes': [..]}"""
    repo, branch = source(settings)
    s = _session(settings)
    last_err = None
    for br in dict.fromkeys([branch, "main"]):
        url = f"https://raw.githubusercontent.com/{repo}/{br}/{SUBDIR}/vietdub/__init__.py"
        try:
            r = s.get(url, timeout=15)
        except requests.RequestException as e:
            last_err = e
            continue
        if r.status_code == 200:
            m = re.search(r'VERSION\s*=\s*"([^"]+)"', r.text)
            latest = m.group(1) if m else "0"
            changes = []
            try:
                c = s.get(f"https://api.github.com/repos/{repo}/commits",
                          params={"sha": br, "path": SUBDIR, "per_page": 8}, timeout=15)
                if c.status_code == 200:
                    changes = [x["commit"]["message"].splitlines()[0] for x in c.json()]
            except (requests.RequestException, ValueError, KeyError):
                pass
            return {"current": VERSION, "latest": latest, "newer": vtuple(latest) > vtuple(VERSION),
                    "branch": br, "repo": repo, "changes": changes}
        last_err = f"HTTP {r.status_code}"
    raise UpdateError(f"Không kiểm tra được bản mới ({last_err}). Kiểm tra mạng rồi thử lại.")


def _git_root(path: Path) -> Path | None:
    for p in (path, *path.parents):
        if (p / ".git").exists():
            return p
    return None


def update(settings: Settings, log, progress, cancel, force: bool = False) -> dict:
    if getattr(sys, "frozen", False):
        raise UpdateError("Bản .exe đóng gói sẵn không tự cập nhật được - hãy tải bản mới.")
    progress(0.02, "Kiểm tra bản mới")
    info = check(settings)
    if not info["newer"] and not force:
        log(f"Đang dùng bản mới nhất ({VERSION}).")
        return {**info, "updated": False}
    root = app_dir()
    groot = _git_root(root)
    if groot and shutil.which("git"):
        log(f"Cập nhật bằng git ({groot})...")
        progress(0.3, "git pull")
        r = subprocess.run(["git", "-C", str(groot), "pull", "--ff-only", "origin", info["branch"]],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window())
        if r.returncode != 0:
            raise UpdateError("git pull lỗi (bạn đã sửa file trong thư mục app?):\n" + (r.stderr or r.stdout)[-600:])
        log(r.stdout.strip()[-400:])
    else:
        data = _download(info, settings, log, progress, cancel)
        apply_zip(data, root, info["latest"], log, progress)
    _install_requirements(root, log, progress, cancel)
    progress(1.0, "Đã cập nhật")
    log(f"✅ Đã cập nhật {VERSION} → {info['latest']}. Khởi động lại app để dùng bản mới.")
    return {**info, "updated": True}


def _download(info: dict, settings: Settings, log, progress, cancel) -> bytes:
    url = f"https://codeload.github.com/{info['repo']}/zip/refs/heads/{info['branch']}"
    log(f"Tải bản {info['latest']} từ GitHub...")
    buf = io.BytesIO()
    with _session(settings).get(url, stream=True, timeout=120) as r:
        if r.status_code != 200:
            raise UpdateError(f"Tải bản cập nhật lỗi HTTP {r.status_code}.")
        total = int(r.headers.get("content-length") or 0)
        for chunk in r.iter_content(1 << 16):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            buf.write(chunk)
            progress(0.05 + (0.5 * buf.tell() / total if total else 0.2), f"Tải bản cập nhật {buf.tell() / 1e6:.1f} MB")
    return buf.getvalue()


def apply_zip(data: bytes, root: Path, version: str, log, progress=lambda *_a: None) -> int:
    """Chép mã nguồn trong file zip (thư mục VietDub/) đè lên `root`. Trả về số file đã đổi."""
    z = zipfile.ZipFile(io.BytesIO(data))
    names = z.namelist()
    prefix = next((n for n in names if re.search(rf"(^|/){SUBDIR}/$", n)), None)
    if not prefix:
        raise UpdateError(f"Bản tải về không có thư mục {SUBDIR}.")
    files = {n[len(prefix):]: n for n in names if n.startswith(prefix) and not n.endswith("/") and n[len(prefix):]}
    if "main.py" not in files or "vietdub/__init__.py" not in files:
        raise UpdateError("Bản tải về không hợp lệ (thiếu main.py).")
    from . import VERSION as cur

    backup = root / "_backup" / cur
    changed = 0
    items = sorted(files.items())
    for i, (rel, zname) in enumerate(items):
        if rel.split("/", 1)[0] in KEEP:
            continue
        blob = z.read(zname)
        dest = root / rel
        if dest.exists() and dest.read_bytes() == blob:
            continue
        if dest.exists():
            b = backup / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, b)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".new")
        tmp.write_bytes(blob)
        os.replace(tmp, dest)
        changed += 1
        if i % 10 == 0:
            progress(0.55 + 0.3 * i / len(items), f"Chép {rel}")
    new_set = set(files)
    for d in CODE_DIRS:
        for f in (root / d).rglob("*.py") if (root / d).exists() else []:
            rel = f.relative_to(root).as_posix()
            if rel not in new_set and "__pycache__" not in rel:
                b = backup / rel
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), b)
                changed += 1
    (root / ".version.json").write_text(json.dumps({"version": version}, ensure_ascii=False), encoding="utf-8")
    log(f"Đã cập nhật {changed} file (bản cũ sao lưu tại {backup}).")
    return changed


def _install_requirements(root: Path, log, progress, cancel) -> None:
    req = root / "requirements.txt"
    if not req.exists():
        return
    progress(0.9, "Cài thư viện mới (nếu có)")
    log("Cài thư viện mới (nếu có)...")
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(req)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
                           **no_window())
        if r.returncode != 0:
            log("Cài thư viện mới lỗi - có thể chạy lại install.bat:\n" + (r.stderr or r.stdout)[-500:], "warn")
    except (OSError, subprocess.SubprocessError) as e:
        log(f"Cài thư viện mới lỗi ({e}) - có thể chạy lại install.bat.", "warn")


def rollback(log) -> str:
    """Khôi phục bản sao lưu gần nhất."""
    bdir = app_dir() / "_backup"
    vers = sorted((p for p in bdir.iterdir() if p.is_dir()), key=lambda p: vtuple(p.name)) if bdir.exists() else []
    if not vers:
        raise UpdateError("Chưa có bản sao lưu nào.")
    last = vers[-1]
    for f in last.rglob("*"):
        if f.is_file():
            dest = app_dir() / f.relative_to(last)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)
    shutil.rmtree(last, ignore_errors=True)
    log(f"Đã khôi phục bản {last.name}. Khởi động lại app.")
    return last.name


def restart_command() -> list[str]:
    exe = sys.executable
    w = Path(exe).with_name("pythonw.exe")
    if os.name == "nt" and w.exists():
        exe = str(w)
    return [exe, str(app_dir() / "main.py")]
