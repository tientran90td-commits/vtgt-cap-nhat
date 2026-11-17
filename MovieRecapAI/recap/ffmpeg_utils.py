"""Tiện ích FFmpeg: tìm file thực thi, đọc thông tin media, chạy lệnh có thể hủy."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

_FFMPEG_OVERRIDE: str | None = None


class Cancelled(Exception):
    """Người dùng bấm Hủy."""


class FFmpegError(RuntimeError):
    pass


def set_ffmpeg_path(path: str | None) -> None:
    global _FFMPEG_OVERRIDE
    _FFMPEG_OVERRIDE = path or None


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def ffmpeg_exe() -> str:
    """Thứ tự ưu tiên: đường dẫn trong Cài đặt > ./ffmpeg/ cạnh app > PATH > imageio-ffmpeg."""
    if _FFMPEG_OVERRIDE and Path(_FFMPEG_OVERRIDE).exists():
        return _FFMPEG_OVERRIDE
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    for cand in (_app_dir() / "ffmpeg" / exe, _app_dir() / "ffmpeg" / "bin" / exe):
        if cand.exists():
            return str(cand)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise FFmpegError(
            "Không tìm thấy FFmpeg. Hãy cài FFmpeg (winget install Gyan.FFmpeg) "
            "hoặc chỉ đường dẫn trong mục Cài đặt."
        ) from e


def ffprobe_exe() -> str | None:
    ff = Path(ffmpeg_exe())
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    cand = ff.with_name(name)
    if cand.exists():
        return str(cand)
    return shutil.which("ffprobe")


def _no_window_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": 0x08000000}  # CREATE_NO_WINDOW
    return {}


@dataclass
class MediaInfo:
    path: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    has_video: bool = False
    subtitle_streams: list = field(default_factory=list)

    def summary(self) -> str:
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        parts = [f"Thời lượng {h:02d}:{m:02d}:{s:02d}"]
        if self.has_video:
            parts.append(f"{self.width}x{self.height} @ {self.fps:.2f}fps")
        parts.append("có âm thanh" if self.has_audio else "KHÔNG có âm thanh")
        if self.subtitle_streams:
            parts.append(f"{len(self.subtitle_streams)} phụ đề nhúng")
        return " · ".join(parts)


def probe(path: str | os.PathLike) -> MediaInfo:
    path = str(path)
    info = MediaInfo(path=path)
    fp = ffprobe_exe()
    if fp:
        try:
            out = subprocess.run(
                [fp, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120, **_no_window_kwargs(),
            )
            data = json.loads(out.stdout or "{}")
            info.duration = float(data.get("format", {}).get("duration") or 0)
            for st in data.get("streams", []):
                ct = st.get("codec_type")
                if ct == "video" and not info.has_video and st.get("disposition", {}).get("attached_pic", 0) == 0:
                    info.has_video = True
                    info.width = int(st.get("width") or 0)
                    info.height = int(st.get("height") or 0)
                    fr = st.get("avg_frame_rate") or st.get("r_frame_rate") or "0/1"
                    try:
                        a, b = fr.split("/")
                        info.fps = float(a) / float(b) if float(b) else 0.0
                    except Exception:
                        info.fps = 0.0
                    if not info.duration:
                        info.duration = float(st.get("duration") or 0)
                elif ct == "audio":
                    info.has_audio = True
                    if not info.duration:
                        info.duration = float(st.get("duration") or 0)
                elif ct == "subtitle":
                    info.subtitle_streams.append({
                        "index": st.get("index"),
                        "codec": st.get("codec_name"),
                        "lang": (st.get("tags") or {}).get("language", ""),
                        "title": (st.get("tags") or {}).get("title", ""),
                    })
            if info.duration:
                return info
        except Exception:
            pass
    # Dự phòng: phân tích stderr của `ffmpeg -i`
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", **_no_window_kwargs())
    txt = out.stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if m:
        info.duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    for line in txt.splitlines():
        if "Stream #" not in line:
            continue
        if "Video:" in line and not info.has_video and "attached pic" not in line:
            info.has_video = True
            mm = re.search(r"(\d{2,5})x(\d{2,5})", line)
            if mm:
                info.width, info.height = int(mm.group(1)), int(mm.group(2))
            mf = re.search(r"([\d.]+)\s*fps", line)
            if mf:
                info.fps = float(mf.group(1))
        elif "Audio:" in line:
            info.has_audio = True
        elif "Subtitle:" in line:
            info.subtitle_streams.append({"index": len(info.subtitle_streams), "codec": "", "lang": "", "title": line})
    if not info.duration:
        raise FFmpegError(f"Không đọc được file media: {path}")
    return info


def media_duration(path: str | os.PathLike) -> float:
    return probe(path).duration


def run_ffmpeg(args: list[str], cancel: threading.Event | None = None, cwd: str | None = None,
               on_progress=None, total: float | None = None, log=None) -> None:
    """Chạy ffmpeg; báo tiến độ (0..1) qua on_progress nếu biết tổng thời lượng."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-y", "-nostdin"] + [str(a) for a in args]
    if log:
        log("$ ffmpeg " + " ".join(_quote(a) for a in cmd[1:]), level="debug")
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", **_no_window_kwargs())
    tail: list[str] = []
    time_re = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")
    assert proc.stderr is not None
    for line in proc.stderr:
        tail.append(line.rstrip())
        if len(tail) > 40:
            tail.pop(0)
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise Cancelled()
        if on_progress and total:
            m = time_re.search(line)
            if m:
                t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                on_progress(min(1.0, t / total))
    proc.wait()
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    if proc.returncode != 0:
        raise FFmpegError("FFmpeg lỗi (mã %s):\n%s" % (proc.returncode, "\n".join(tail[-15:])))


def _quote(a: str) -> str:
    return f'"{a}"' if (" " in a or ";" in a) else a


def extract_audio(video: str, out_path: str, sample_rate: int = 16000, cancel=None, bitrate: str | None = None,
                  on_progress=None, total=None) -> str:
    args = ["-i", video, "-vn", "-ac", "1", "-ar", str(sample_rate)]
    if bitrate:
        args += ["-c:a", "libmp3lame", "-b:a", bitrate]
    args.append(out_path)
    run_ffmpeg(args, cancel=cancel, on_progress=on_progress, total=total)
    return out_path


def list_encoders() -> set[str]:
    out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-encoders"], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", **_no_window_kwargs())
    names = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return names


def encoder_works(name: str) -> bool:
    """Thử mã hóa 1 khung hình để biết GPU encoder có dùng được không."""
    try:
        r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-v", "error", "-f", "lavfi", "-i",
                            "color=black:s=256x256:d=0.2", "-frames:v", "3", "-c:v", name, "-f", "null", "-"],
                           capture_output=True, timeout=30, **_no_window_kwargs())
        return r.returncode == 0
    except Exception:
        return False


def fmt_ts(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    return f"{h:02d}:{m:02d}:{s:05.2f}" if s % 1 else f"{h:02d}:{m:02d}:{int(s):02d}"


def parse_ts(val) -> float:
    """Nhận '01:02:03.5', '02:03', '75.2' hoặc số -> giây."""
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", ".")
    if not s:
        return 0.0
    parts = s.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return 0.0
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total
