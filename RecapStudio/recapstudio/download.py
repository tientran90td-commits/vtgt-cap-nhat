"""Tải phim từ link (YouTube, TikTok, Facebook, Bilibili... - hơn 1000 trang) bằng yt-dlp (mã nguồn mở).

Chỉ tải video bạn có quyền sử dụng. Có phụ đề tiếng Việt/Anh đi kèm thì tải luôn (app dùng làm lời thoại).
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import Settings
from .media import Cancelled, ffmpeg_exe

URL_RE = re.compile(r"^https?://\S+$", re.I)


class DownloadError(RuntimeError):
    pass


def is_url(text: str) -> bool:
    return bool(URL_RE.match((text or "").strip()))


class _Log:
    def __init__(self, log):
        self.log = log

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        if "ffmpeg" not in msg.lower():
            self.log(f"yt-dlp: {msg}", "warn")

    def error(self, msg):
        self.log(f"yt-dlp: {msg}", "warn")


def download(url: str, settings: Settings, log, progress, cancel, max_height: int = 1080) -> Path:
    try:
        import yt_dlp
    except ImportError as e:
        raise DownloadError("Chưa cài yt-dlp (pip install yt-dlp) - chạy lại install.bat.") from e
    if settings.offline:
        raise DownloadError("Đang ở chế độ 'Chỉ trên máy' - đổi sang Tự động để tải phim từ link.")
    out_dir = settings.downloads_dir()

    def hook(d):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            got = d.get("downloaded_bytes") or 0
            sp = d.get("speed") or 0
            msg = f"Tải phim {got / 1e6:.0f}/{total / 1e6:.0f} MB" if total else f"Tải phim {got / 1e6:.0f} MB"
            if sp:
                msg += f" · {sp / 1e6:.1f} MB/s"
            progress(min(0.99, got / total) if total else 0.0, msg)
    opts = {
        "outtmpl": str(out_dir / "%(title).70B [%(id)s].%(ext)s"),
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/bv*+ba/b",
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_exe(settings.get("paths", "ffmpeg") or ""),
        "noplaylist": True, "quiet": True, "no_warnings": True, "noprogress": True,
        "windowsfilenames": True, "progress_hooks": [hook], "logger": _Log(log),
        "writesubtitles": True, "subtitleslangs": ["vi", "vi-.*", "en", "en-.*"], "subtitlesformat": "srt/vtt/best",
        "retries": 5, "fragment_retries": 5, "concurrent_fragment_downloads": 4,
    }
    proxy = (settings.get("net", "proxy") or "").strip()
    if proxy:
        opts["proxy"] = proxy
    log(f"Tải phim từ link: {url}")
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=True)
            if info.get("entries"):
                info = next(e for e in info["entries"] if e)
            reqs = info.get("requested_downloads") or []
            path = Path(reqs[0]["filepath"]) if reqs and reqs[0].get("filepath") else Path(y.prepare_filename(info))
    except Cancelled:
        raise
    except Exception as e:  # noqa: BLE001
        if cancel is not None and cancel.is_set():
            raise Cancelled() from e
        raise DownloadError(f"Không tải được phim từ link: {str(e)[:300]}") from e
    if not path.exists():
        cands = sorted(out_dir.glob(f"*[[]{info.get('id', '')}[]].*"), key=lambda p: p.stat().st_size, reverse=True)
        cands = [c for c in cands if c.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")]
        if not cands:
            raise DownloadError("Tải xong nhưng không thấy file phim.")
        path = cands[0]
    progress(1.0, "Đã tải phim")
    log(f"✅ Đã tải: {path.name} ({path.stat().st_size / 1e6:.0f} MB)")
    return path
