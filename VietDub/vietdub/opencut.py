"""🎬 OpenCut tiếng Việt - trình dựng video mã nguồn mở (opencut-classic, giấy phép MIT) chạy kèm VietDub.

- Bản dựng web tĩnh đã Việt hóa (xem VietDub/opencut/build_opencut_vi.py), tải 1 lần (~15 MB nén).
- VietDub tự chạy 1 máy chủ web nhỏ trên máy (127.0.0.1, không ra mạng) và mở OpenCut trong cửa sổ riêng của
  Edge / Chrome (chế độ app, hồ sơ riêng) - không cần Node.js, không cần đăng nhập, video không rời khỏi máy.
- Cầu nối: /vietdub/... phục vụ video đã Việt hóa + phụ đề + thuyết minh của dự án đang mở để OpenCut tự nạp.
"""
from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from .config import Settings, app_home
from .media import Cancelled

PORT = 47821          # cố định: trình duyệt lưu dự án OpenCut theo địa chỉ, đổi cổng là "mất" dự án
ZIP_URL = ("https://raw.githubusercontent.com/tientran90td-commits/vtgt-cap-nhat/claude/movie-summary-app-0q90dq/"
           "VietDub/opencut/opencut-vi.zip")
_SERVER: dict = {}
_BRIDGE: dict = {"files": {}, "manifest": None}

mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/plain; charset=utf-8", ".txt")
mimetypes.add_type("text/vtt", ".vtt")


class OpenCutError(RuntimeError):
    pass


def web_dir() -> Path:
    return app_home() / "opencut"


def installed() -> bool:
    return (web_dir() / "projects" / "index.html").exists()


def bundled_zip() -> Path:
    """Bản OpenCut tiếng Việt đi kèm mã nguồn app (VietDub/opencut/opencut-vi.zip)."""
    return Path(__file__).resolve().parent.parent / "opencut" / "opencut-vi.zip"


def _version_of(z: Path) -> str:
    st = z.stat()
    return f"{st.st_size}-{int(st.st_mtime)}"


def up_to_date() -> bool:
    """Đã giải nén đúng bản đi kèm app chưa (cập nhật app -> tự giải nén lại bản mới)."""
    if not installed():
        return False
    z = bundled_zip()
    if not z.exists():
        return True
    f = web_dir() / ".bundle"
    return f.exists() and f.read_text(encoding="utf-8").strip() == _version_of(z)


def install(settings: Settings, log, progress, cancel, url: str = ZIP_URL, zip_path: Path | None = None) -> Path:
    """Giải nén bản OpenCut tiếng Việt đi kèm app (hoặc tải về nếu thiếu)."""
    d = web_dir()
    tmp = app_home() / "opencut.zip.part"
    if zip_path is None and bundled_zip().exists():
        zip_path = bundled_zip()
    if zip_path is None:
        log("Tải OpenCut tiếng Việt (một lần)...")
        with requests.get(url, stream=True, timeout=(15, 300), proxies=settings.proxies()) as r:
            if r.status_code != 200:
                raise OpenCutError(f"Tải OpenCut lỗi HTTP {r.status_code}")
            total = int(r.headers.get("content-length") or 0)
            got = 0
            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    if cancel is not None and cancel.is_set():
                        raise Cancelled()
                    fh.write(chunk)
                    got += len(chunk)
                    if total:
                        progress(0.9 * got / total, f"Tải OpenCut {got / 1e6:.0f}/{total / 1e6:.0f} MB")
        zip_path = tmp
    new = d.with_name("opencut.new")
    shutil.rmtree(new, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(new)
    if not (new / "projects" / "index.html").exists():
        shutil.rmtree(new, ignore_errors=True)
        raise OpenCutError("Bản OpenCut tải về không hợp lệ.")
    if zip_path == bundled_zip():
        (new / ".bundle").write_text(_version_of(zip_path), encoding="utf-8")
    shutil.rmtree(d, ignore_errors=True)
    new.rename(d)
    tmp.unlink(missing_ok=True)
    progress(1.0, "Đã cài OpenCut")
    log("✅ Đã cài OpenCut tiếng Việt.")
    return d


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache" if not self.path.startswith("/_next/static/") else
                         "public,max-age=31536000,immutable")
        super().end_headers()

    def _bridge(self, path: str) -> bool:
        if path == "/vietdub/manifest.json":
            data = json.dumps(_BRIDGE["manifest"] or {}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True
        name = path[len("/vietdub/files/"):] if path.startswith("/vietdub/files/") else None
        f = _BRIDGE["files"].get(name) if name else None
        if f is None or not Path(f).exists():
            self.send_error(404)
            return True
        size = Path(f).stat().st_size
        self.send_response(200)
        ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
        if Path(f).suffix.lower() in (".srt", ".vtt", ".ass", ".txt"):
            ctype = "text/plain; charset=utf-8"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(f, "rb") as fh:
            shutil.copyfileobj(fh, self.wfile, 1 << 20)
        return True

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path.startswith("/vietdub/"):
            try:
                self._bridge(path)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        super().do_GET()

    def translate_path(self, path):
        p = urlparse(path).path
        parts = p.split("/")
        # /editor/<id>/... -> /editor/_/... (1 trang dựng tĩnh dùng chung cho mọi dự án)
        if len(parts) > 2 and parts[1] == "editor" and parts[2] and parts[2] != "_":
            parts[2] = "_"
            p = "/".join(parts)
            if len(parts) == 3:
                p += "/"
        return super().translate_path(p)


def start(port: int = PORT) -> str:
    """Chạy máy chủ web nhỏ (chỉ trên máy này). Trả về địa chỉ gốc."""
    if _SERVER.get("srv"):
        return _SERVER["url"]
    if not installed():
        raise OpenCutError("Chưa cài OpenCut - bấm 📦 Thư viện → Tải (OpenCut tiếng Việt).")
    last = None
    for p in (port, port + 1, port + 2):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), partial(Handler, directory=str(web_dir())))
            break
        except OSError as e:
            last = e
    else:
        raise OpenCutError(f"Không mở được cổng cho OpenCut: {last}")
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _SERVER.update(srv=srv, url=f"http://127.0.0.1:{srv.server_port}")
    return _SERVER["url"]


def stop() -> None:
    srv = _SERVER.pop("srv", None)
    if srv:
        srv.shutdown()
    _SERVER.clear()


def share(files: dict[str, Path], manifest: dict) -> None:
    """Đưa video / phụ đề / thuyết minh của dự án VietDub cho OpenCut nạp."""
    _BRIDGE["files"] = {k: Path(v) for k, v in files.items()}
    _BRIDGE["manifest"] = manifest


def editor_url(base: str, manifest: dict) -> str:
    from urllib.parse import quote

    job = manifest["job"]
    return f"{base}/editor/vietdub-{job}/?vietdub={job}&name={quote(manifest.get('title') or 'Dự án VietDub')}"


def browser() -> str | None:
    """Edge / Chrome / Chromium (OpenCut cần trình duyệt nhân Chromium)."""
    cands = []
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            if base:
                cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe",
                          Path(base) / "Google/Chrome/Application/chrome.exe"]
    elif sys.platform == "darwin":
        cands += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")]
    for c in cands:
        if c.exists():
            return str(c)
    for name in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        f = shutil.which(name)
        if f:
            return f
    return None


def open_window(url: str) -> None:
    """Mở OpenCut như 1 cửa sổ app riêng (hồ sơ riêng để dự án được giữ lại giữa các lần mở)."""
    exe = browser()
    if exe:
        prof = app_home() / "opencut-profile"
        prof.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={prof}", "--no-first-run",
                          "--no-default-browser-check", "--window-size=1600,950", "--lang=vi"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    import webbrowser

    webbrowser.open(url)
