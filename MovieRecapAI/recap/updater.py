"""Cập nhật tool trực tiếp từ GitHub (không cần tải zip & giải nén tay).

- Cài bằng git clone -> `git pull`.
- Cài bằng file zip -> tải bản mới nhất, sao lưu file cũ vào _backup/<phiên bản>/, chép đè mã nguồn mới
  (KHÔNG đụng tới .venv, ffmpeg, dữ liệu & cài đặt của bạn - chúng nằm ở %APPDATA%), rồi cài thư viện mới nếu có.
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

from . import APP_VERSION
from .config import Settings
from .ffmpeg_utils import Cancelled

DEFAULT_REPO = "tientran90td-commits/vtgt-cap-nhat"
DEFAULT_BRANCH = "claude/movie-summary-app-0q90dq"
SUBDIR = "MovieRecapAI"
KEEP = {".venv", "venv", "ffmpeg", "_backup", "build", "dist", "__pycache__", ".git"}  # không bao giờ ghi đè/xóa
CODE_DIRS = ("recap", "gui", "tests")  # file .py không còn trong bản mới sẽ được dọn


class UpdateError(RuntimeError):
    pass


def app_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def source(settings: Settings) -> tuple[str, str]:
    repo = (settings.get("ui", "update_repo") or DEFAULT_REPO).strip().strip("/")
    branch = (settings.get("ui", "update_branch") or DEFAULT_BRANCH).strip()
    return repo, branch


def _session(settings: Settings) -> requests.Session:
    s = requests.Session()
    p = (settings.get("api", "proxy") or "").strip()
    if p:
        s.proxies = {"http": p, "https": p}
    s.headers["User-Agent"] = "MovieRecapAI-updater"
    return s


def vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:3]) or (0,)


def check(settings: Settings) -> dict:
    """{'current', 'latest', 'newer', 'branch', 'changes': [..]}"""
    repo, branch = source(settings)
    s = _session(settings)
    last_err = None
    for br in dict.fromkeys([branch, "main"]):
        url = f"https://raw.githubusercontent.com/{repo}/{br}/{SUBDIR}/recap/__init__.py"
        try:
            r = s.get(url, timeout=20)
        except requests.RequestException as e:
            last_err = e
            continue
        if r.status_code == 200:
            m = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', r.text)
            latest = m.group(1) if m else "0"
            changes = []
            try:
                c = s.get(f"https://api.github.com/repos/{repo}/commits",
                          params={"sha": br, "path": SUBDIR, "per_page": 8}, timeout=20)
                if c.status_code == 200:
                    changes = [x["commit"]["message"].splitlines()[0] for x in c.json()]
            except (requests.RequestException, ValueError, KeyError):
                pass
            return {"current": APP_VERSION, "latest": latest, "newer": vtuple(latest) > vtuple(APP_VERSION),
                    "branch": br, "repo": repo, "changes": changes}
        last_err = f"HTTP {r.status_code}"
    raise UpdateError(f"Không kiểm tra được bản mới từ {repo} ({last_err}).")


def _git_root(path: Path) -> Path | None:
    for p in (path, *path.parents):
        if (p / ".git").exists():
            return p
    return None


def update(settings: Settings, log, progress, cancel) -> dict:
    if getattr(sys, "frozen", False):
        raise UpdateError("Bản .exe đóng gói sẵn không tự cập nhật được - hãy tải bản mới và cài lại.")
    info = check(settings)
    if not info["newer"]:
        log(f"Đang dùng bản mới nhất ({APP_VERSION}).")
        return {**info, "updated": False}
    root = app_dir()
    groot = _git_root(root)
    if groot and shutil.which("git"):
        log(f"Cập nhật bằng git ({groot})...")
        progress(0.3, "git pull")
        r = subprocess.run(["git", "-C", str(groot), "pull", "--ff-only", "origin", info["branch"]],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise UpdateError("git pull lỗi (bạn đã sửa file trong thư mục tool?):\n" + (r.stderr or r.stdout)[-600:])
        log(r.stdout.strip()[-400:])
    else:
        _update_from_zip(info, root, settings, log, progress, cancel)
    _install_requirements(root, log, progress, cancel)
    progress(1.0, "Đã cập nhật")
    log(f"✅ Đã cập nhật {APP_VERSION} → {info['latest']}. Khởi động lại app để dùng bản mới.")
    return {**info, "updated": True}


def _update_from_zip(info: dict, root: Path, settings: Settings, log, progress, cancel) -> None:
    repo, br = info["repo"], info["branch"]
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{br}"
    log(f"Tải bản {info['latest']} từ GitHub...")
    s = _session(settings)
    buf = io.BytesIO()
    with s.get(url, stream=True, timeout=120) as r:
        if r.status_code != 200:
            raise UpdateError(f"Tải bản cập nhật lỗi HTTP {r.status_code}.")
        total = int(r.headers.get("content-length") or 0)
        for chunk in r.iter_content(1 << 16):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            buf.write(chunk)
            if total:
                progress(0.5 * buf.tell() / total, f"Tải bản cập nhật {buf.tell() / 1e6:.1f} MB")
    z = zipfile.ZipFile(buf)
    names = z.namelist()
    prefix = next((n for n in names if n.rstrip("/").endswith("/" + SUBDIR) or n.endswith("/" + SUBDIR + "/")), None)
    if not prefix:
        raise UpdateError("Bản tải về không có thư mục MovieRecapAI.")
    prefix = prefix if prefix.endswith("/") else prefix + "/"
    files = {n[len(prefix):]: n for n in names if n.startswith(prefix) and not n.endswith("/") and n[len(prefix):]}
    if "main.py" not in files or "recap/__init__.py" not in files:
        raise UpdateError("Bản tải về không hợp lệ (thiếu main.py).")
    backup = root / "_backup" / APP_VERSION
    changed = 0
    for i, (rel, zname) in enumerate(sorted(files.items())):
        if rel.split("/", 1)[0] in KEEP:
            continue
        data = z.read(zname)
        dest = root / rel
        if dest.exists() and dest.read_bytes() == data:
            continue
        if dest.exists():
            b = backup / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, b)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".new")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        changed += 1
        if i % 10 == 0:
            progress(0.5 + 0.35 * i / len(files), f"Chép {rel}")
    # dọn file mã nguồn đã bị xóa ở bản mới (tránh mô-đun cũ còn sót)
    new_set = set(files)
    for d in CODE_DIRS:
        for f in (root / d).rglob("*.py") if (root / d).exists() else []:
            rel = f.relative_to(root).as_posix()
            if rel not in new_set and "__pycache__" not in rel:
                b = backup / rel
                b.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), b)
                changed += 1
    (root / ".version.json").write_text(json.dumps({"version": info["latest"], "branch": br, "repo": repo},
                                                   ensure_ascii=False), encoding="utf-8")
    log(f"Đã cập nhật {changed} file (bản cũ sao lưu tại {backup}).")


def _install_requirements(root: Path, log, progress, cancel) -> None:
    req = root / "requirements.txt"
    if not req.exists():
        return
    from .components import pip_install

    progress(0.9, "Cài thư viện mới (nếu có)")
    try:
        pip_install(["-r", str(req)], log, progress, cancel)
    except Exception as e:  # noqa: BLE001
        log(f"Cài thư viện mới lỗi ({e}) - có thể chạy lại install.bat.", level="warn")


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
    log(f"Đã khôi phục bản {last.name}. Khởi động lại app.")
    return last.name


def restart_command() -> list[str]:
    from .components import python_exe

    exe = python_exe()
    w = Path(exe).with_name("pythonw.exe")
    if os.name == "nt" and w.exists():
        exe = str(w)
    return [exe, str(app_dir() / "main.py")]
