"""FFmpeg: tìm chương trình, đọc thông tin video, chạy lệnh có tiến độ + nút Hủy."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path


class Cancelled(Exception):
    """Người dùng bấm Hủy."""


class MediaError(RuntimeError):
    pass


_FFMPEG: str | None = None


def no_window() -> dict:
    return {"creationflags": 0x08000000} if os.name == "nt" else {}  # CREATE_NO_WINDOW


def ffmpeg_exe(custom: str = "") -> str:
    """FFmpeg: đường dẫn tự chọn -> ffmpeg trong PATH -> bản đi kèm imageio-ffmpeg."""
    global _FFMPEG
    if custom and Path(custom).is_file():
        return custom
    if _FFMPEG:
        return _FFMPEG
    found = shutil.which("ffmpeg")
    if not found:
        try:
            import imageio_ffmpeg

            found = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:  # noqa: BLE001
            raise MediaError("Không tìm thấy FFmpeg. Chạy install.bat hoặc cài FFmpeg rồi thử lại.") from e
    _FFMPEG = found
    return found


def ffprobe_exe() -> str | None:
    ff = Path(ffmpeg_exe())
    cand = ff.with_name("ffprobe.exe" if ff.suffix == ".exe" else "ffprobe")
    return str(cand) if cand.exists() else shutil.which("ffprobe")


@dataclass
class MediaInfo:
    path: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    subtitles: list = field(default_factory=list)   # [{"index": i, "codec": ..., "lang": ...}]

    def summary(self) -> str:
        t = int(self.duration)
        return (f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d} · {self.width}x{self.height}"
                f" · {self.fps:.0f}fps · " + ("có tiếng" if self.has_audio else "không có tiếng"))


def probe(path: str | Path) -> MediaInfo:
    path = str(path)
    info = MediaInfo(path=path)
    fp = ffprobe_exe()
    if fp:
        r = subprocess.run([fp, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", **no_window())
        if r.returncode == 0:
            data = json.loads(r.stdout or "{}")
            info.duration = float(data.get("format", {}).get("duration") or 0)
            n_sub = 0
            for s in data.get("streams", []):
                t = s.get("codec_type")
                if t == "video" and not info.width and s.get("disposition", {}).get("attached_pic") != 1:
                    info.width, info.height = int(s.get("width") or 0), int(s.get("height") or 0)
                    num, _, den = (s.get("avg_frame_rate") or "0/1").partition("/")
                    info.fps = float(num) / float(den or 1) if float(den or 1) else 0.0
                elif t == "audio":
                    info.has_audio = True
                elif t == "subtitle":
                    info.subtitles.append({"index": n_sub, "codec": s.get("codec_name", ""),
                                           "lang": (s.get("tags") or {}).get("language", "")})
                    n_sub += 1
            return info
    # không có ffprobe: đọc thông tin từ "ffmpeg -i"
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", **no_window())
    txt = r.stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if m:
        info.duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", txt)
    if m:
        info.width, info.height = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?) fps", txt)
    if m:
        info.fps = float(m.group(1))
    info.has_audio = "Audio:" in txt
    for k, m in enumerate(re.finditer(r"Stream #\d+:\d+(?:\((\w+)\))?: Subtitle: (\w+)", txt)):
        info.subtitles.append({"index": k, "codec": m.group(2), "lang": m.group(1) or ""})
    if not info.duration:
        raise MediaError(f"Không đọc được file: {Path(path).name}")
    return info


def run(args: list, cancel: threading.Event | None = None, total: float = 0.0, on_progress=None,
        cwd: str | None = None, low_priority: bool = False) -> str:
    """Chạy ffmpeg; báo tiến độ 0..1 theo thời lượng (nếu biết); bấm Hủy là dừng ngay. Trả về log của ffmpeg."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", *[str(a) for a in args]]
    kw = no_window()
    if low_priority:  # việc nền: nhường CPU cho các bước chính
        if os.name == "nt":
            kw["creationflags"] = kw.get("creationflags", 0) | 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
        else:
            kw["preexec_fn"] = lambda: os.nice(10)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=cwd, **kw)
    tail: list[str] = []
    buf = b""

    def reader():
        nonlocal buf
        for chunk in iter(lambda: proc.stderr.read(4096), b""):
            buf += chunk
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    seen = 0
    while proc.poll() is None:
        th.join(0.3)
        if cancel is not None and cancel.is_set():
            proc.kill()
            proc.wait()
            raise Cancelled()
        if on_progress and total > 0 and len(buf) > seen:
            txt = buf[seen:].decode("utf-8", "replace")
            seen = len(buf)
            m = list(re.finditer(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", txt))
            if m:
                g = m[-1]
                t = int(g.group(1)) * 3600 + int(g.group(2)) * 60 + float(g.group(3))
                on_progress(min(1.0, t / total))
    th.join(2)
    if proc.returncode != 0:
        tail = buf.decode("utf-8", "replace").strip().splitlines()[-8:]
        raise MediaError("FFmpeg lỗi:\n" + "\n".join(tail))
    return buf.decode("utf-8", "replace")


def frames(video: str, start: float, length: float | None, width: int, height: int, fps: float | None = None,
           pix: str = "gray", cancel=None, count: int | None = None) -> list:
    """Đọc khung hình (numpy uint8) đã thu nhỏ về width x height. pix: gray | rgb24."""
    import numpy as np

    ch = 3 if pix == "rgb24" else 1
    args = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, start):.3f}"]
    if length is not None:
        args += ["-t", f"{length:.3f}"]
    vf = (f"fps={fps}," if fps else "") + f"scale={width}:{height},format={pix}"
    args += ["-i", str(video), "-an", "-sn", "-vf", vf]
    if count:
        args += ["-frames:v", str(count)]
    args += ["-f", "rawvideo", "-"]
    if cancel is not None and cancel.is_set():
        raise Cancelled()
    r = subprocess.run(args, capture_output=True, timeout=600, **no_window())
    size = width * height * ch
    data = r.stdout
    out = []
    for i in range(len(data) // size):
        a = np.frombuffer(data, np.uint8, size, i * size)
        out.append(a.reshape(height, width, ch) if ch == 3 else a.reshape(height, width))
    return out


def duration(path: str | Path) -> float:
    return probe(path).duration


def extract_audio(video: str, out: str | Path, sr: int = 16000, cancel=None, bitrate: str | None = None,
                  start: float | None = None, length: float | None = None) -> Path:
    args = []
    if start is not None:
        args += ["-ss", f"{start:.3f}"]
    if length is not None:
        args += ["-t", f"{length:.3f}"]
    args += ["-i", video, "-vn", "-sn", "-ac", "1", "-ar", str(sr)]
    if bitrate:
        args += ["-b:a", bitrate]
    run([*args, str(out)], cancel=cancel)
    return Path(out)


# ------------------------------------------------------------------ bộ mã hóa video
ENCODERS = {"auto": "Tự động (dùng GPU nếu có)", "h264_amf": "GPU AMD (AMF)", "h264_nvenc": "GPU NVIDIA (NVENC)",
            "h264_qsv": "GPU Intel (QuickSync)", "libx264": "CPU (x264)"}
_BEST: str | None = None


def encoder_works(name: str) -> bool:
    try:
        run(["-f", "lavfi", "-i", "color=c=black:s=256x144:d=0.4", "-c:v", name, "-f", "null", "-"])
        return True
    except Exception:  # noqa: BLE001
        return False


def best_encoder() -> str:
    global _BEST
    if _BEST is None:
        _BEST = next((e for e in ("h264_nvenc", "h264_amf", "h264_qsv") if encoder_works(e)), "libx264")
    return _BEST


def encoder_args(name: str, quality: int = 21) -> list[str]:
    name = best_encoder() if name in ("", "auto") else name
    q = str(int(quality))
    if name == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", q, "-b:v", "0"]
    if name == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", q, "-qp_p", q]
    if name == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", q]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", q]
