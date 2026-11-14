"""Phim Việt Studio cho Termux: máy chủ web trên điện thoại (chỉ 127.0.0.1) + giao diện trong Chrome.

Dùng lõi VietDub (thư mục ../VietDub): lời gốc (Groq Whisper / đọc phụ đề cứng bằng Tesseract / .srt), dịch AI,
giọng đọc Edge, dựng bằng ffmpeg của Termux. Thêm chế độ review / tóm tắt phim (recap.py).
Chạy: python server.py  (hoặc lệnh `phimviet` sau khi cài bằng install.sh)
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent / "VietDub"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))
os.environ.setdefault("VIETDUB_HOME", str(HERE.parent / "data"))

from vietdub.config import fix_std_streams, setup_env  # noqa: E402

fix_std_streams(Path(os.environ["VIETDUB_HOME"]) / "logs")
setup_env()

from vietdub import ai, download, hybrid, translate, voices  # noqa: E402
from vietdub.config import Settings, app_home  # noqa: E402
from vietdub.media import Cancelled  # noqa: E402
from vietdub.project import Project  # noqa: E402

import recap  # noqa: E402

VERSION = "1.1.0"
PORT = int(os.environ.get("PHIMVIET_PORT", "8765"))
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v", ".ts")
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")
SHARED = Path.home() / "storage" / "shared"

TERMUX_DEFAULTS = {
    ("voice", "engine"): "edge", ("voice", "voice"): "vi-VN-HoaiMyNeural",
    ("video", "background"): "duck", ("video", "aspect"): "9:16", ("video", "height"): 720,
    ("video", "fill"): "blur", ("video", "quality"): 23, ("video", "soft_subs"): False,
    ("publish", "thumbnail"): False, ("publish", "info"): False, ("mode", None): "online",
    ("speech", "engine"): "auto", ("video", "karaoke"): True, ("video", "multi_shot"): True,
    ("video", "hook_title"): True, ("video", "bgm_volume"): 0.25,
}


def load_settings() -> Settings:
    s = Settings(app_home() / "settings.json")
    if not s.get("termux", "init"):
        for (sec, k), v in TERMUX_DEFAULTS.items():
            if k is None:
                s.data[sec] = v
            else:
                s.set(sec, k, v)
        s.set("termux", "init", True)
        s.save()
    if not s.get("paths", "output"):
        out = SHARED / "Movies" / "PhimViet" if SHARED.exists() else HERE.parent / "Video xuất"
        s.set("paths", "output", str(out))
        s.save()
    return s


SETTINGS = load_settings()


class Job:
    """Một việc chạy nền (chỉ 1 việc một lúc) + trạng thái cho giao diện hỏi định kỳ."""

    def __init__(self):
        self.lock = threading.Lock()
        self.busy = False
        self.title = ""
        self.status = ""
        self.progress = 0.0
        self.logs: list[str] = []
        self.cancel = threading.Event()
        self.ask: dict | None = None          # yêu cầu chờ người dùng dán câu trả lời từ DeepSeek web
        self._answer: str | None = None
        self._answered = threading.Event()
        self.result: str | None = None        # đường dẫn video thành phẩm mới nhất

    def log(self, m, level="info"):
        line = time.strftime("%H:%M:%S ") + ("⚠ " if level == "warn" else "") + str(m)
        with self.lock:
            self.logs.append(line)
            del self.logs[:-400]

    def prog(self, p, m=""):
        self.progress = max(0.0, min(1.0, float(p)))
        if m:
            self.status = str(m)

    def start(self, title: str, fn) -> bool:
        with self.lock:
            if self.busy:
                return False
            self.busy, self.title, self.status, self.progress = True, title, f"⏳ {title}...", 0.0
            self.cancel = threading.Event()

        def run():
            self.log(f"▶ {title}")
            try:
                fn()
                self.status, self.progress = f"✅ {title} - xong", 1.0
            except Cancelled:
                self.status = "⏹ Đã hủy"
                self.log("⏹ Đã hủy.")
            except Exception as e:  # noqa: BLE001
                self.status = f"❌ {e}".split("\n")[0][:200]
                self.log(f"❌ {title}: {e}", "warn")
                (app_home() / "logs").mkdir(parents=True, exist_ok=True)
                with open(app_home() / "logs" / "error.log", "a", encoding="utf-8") as f:
                    f.write(time.ctime() + "\n" + traceback.format_exc() + "\n")
            finally:
                self.ask = None
                self.busy = False
        threading.Thread(target=run, daemon=True).start()
        return True

    def ask_user(self, prompt: str, what: str) -> str:
        """Chờ người dùng dán câu trả lời của DeepSeek web (giao diện hiện hộp chép / dán)."""
        self._answered.clear()
        self._answer = None
        self.ask = {"id": str(time.time()), "prompt": prompt, "what": what}
        self.log(f"🐋 {what}: bấm Chép yêu cầu → dán vào DeepSeek → dán câu trả lời lại.")
        while not self._answered.wait(0.5):
            if self.cancel.is_set():
                raise Cancelled()
        self.ask = None
        if self._answer is None:
            raise Cancelled()
        return self._answer

    def answer(self, text: str | None):
        self._answer = text
        self._answered.set()


JOB = Job()


class State:
    project: Project | None = None
    segs: list[dict] = []
    recap_title = ""


def manual_ai() -> bool:
    return SETTINGS.get("termux", "ai") == "manual" or not hybrid.online_ai(SETTINGS)


def ask_ai(prompt: str, what: str) -> str:
    if manual_ai():
        return JOB.ask_user(prompt, what)
    return ai.chat(SETTINGS, "Bạn là trợ lý biên tập video tiếng Việt. Làm đúng yêu cầu, chỉ trả lời JSON.", prompt,
                   json_mode=True, log=JOB.log, cancel=JOB.cancel)


def out_path(name: str, suffix: str = "") -> Path:
    safe = re.sub(r'[\\/:*?"<>|\n]+', " ", name).strip()[:80] or "video"
    return SETTINGS.output_dir() / f"{safe}{suffix}.mp4"


# ------------------------------------------------------------------ các việc
def open_video(path: Path, title: str | None = None):
    p = Project(str(path), SETTINGS)
    State.project, State.segs, State.recap_title = p, [], ""
    f = p.dir / "recap.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            State.segs, State.recap_title = d.get("segments", []), d.get("title", "")
        except ValueError:
            pass
    if title:
        (p.dir / "title.txt").write_text(title, encoding="utf-8")
    i = p.info
    JOB.log(f"Video: {path.name} - {recap.fmt(i.duration)}, {i.width}x{i.height}" + ("" if i.has_audio else ", không tiếng"))


def video_title(p: Project) -> str:
    f = p.dir / "title.txt"
    return f.read_text(encoding="utf-8").strip() if f.exists() else p.title


def need_transcript(p: Project):
    if p.source:
        return
    want = SETTINGS.get("speech", "engine") or "auto"
    eng = want
    if eng == "auto":  # có key Groq thì nghe lời thoại, không thì đọc phụ đề cứng (nếu đã đặt khung)
        eng = "groq" if SETTINGS.key("groq") else ("ocr" if p.region else "")
    if not eng or (eng == "ocr" and not p.region):
        raise RuntimeError("Chưa lấy được lời gốc: đặt khung phụ đề cứng (mục 3, bấm 🔍 Tự tìm) để đọc chữ trên hình, "
                           "hoặc nhập key Groq (miễn phí) ở Cài đặt để nghe lời thoại.")
    SETTINGS.set("speech", "engine", eng)
    try:
        p.run_transcript(JOB.log, lambda x, m="": JOB.prog(x * 0.3, m), JOB.cancel)
    finally:
        SETTINGS.set("speech", "engine", want)


def do_recap(render_only: bool = False):
    p = State.project
    title = video_title(p)
    if not render_only or not State.segs:
        need_transcript(p)
        JOB.prog(0.32, "AI viết kịch bản review...")
        target = int(SETTINGS.get("termux", "target") or 180)
        q = recap.prompt(title, p.info.duration, p.source, target, SETTINGS.get("termux", "style") or "hap_dan",
                         SETTINGS.get("translate", "glossary") or "")
        last = None
        for _ in range(2):
            try:
                t, segs = recap.parse(ask_ai(q, "Viết kịch bản review"), p.info.duration)
                State.segs, State.recap_title = segs, t or title
                break
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                last = e
                JOB.log(f"Kịch bản lỗi ({str(e)[:120]}) - thử lại...", "warn")
        else:
            raise RuntimeError(f"AI không viết được kịch bản: {last}")
        (p.dir / "recap.json").write_text(json.dumps({"title": State.recap_title, "segments": State.segs},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
        JOB.log(f"Kịch bản: \"{State.recap_title}\" - {len(State.segs)} đoạn.")
    if p.region:
        SETTINGS.set("video", "band", [p.region[1], p.region[3]])
    else:
        SETTINGS.set("video", "band", None)
    out = out_path(State.recap_title or title, " - review")
    JOB.result = str(recap.render_recap(p.video, p.info, State.segs, State.recap_title or title, SETTINGS,
                                        p.dir / "recap", out, JOB.log, lambda x, m="": JOB.prog(0.4 + 0.6 * x, m),
                                        JOB.cancel))


def manual_translate(p: Project):
    """Dịch bằng DeepSeek web (dán tay): mỗi lần 120 câu, câu thiếu tự hỏi lại."""
    lines = translate.prepare_lines(p.source)
    result: dict[int, str] = {}
    first = True
    for _round in range(4):
        miss = [i for i in range(len(lines)) if i not in result]
        if not miss:
            break
        parts = [miss[a:a + translate.MANUAL_PART] for a in range(0, len(miss), translate.MANUAL_PART)]
        for k, idx in enumerate(parts):
            reply = JOB.ask_user(translate.manual_prompt(lines, idx, SETTINGS, video_title(p), first=first),
                                 f"Dịch phần {k + 1}/{len(parts)} ({len(idx)} câu)")
            first = False
            got = translate.parse_reply(reply, idx)
            result.update(got)
            JOB.log(f"Nhận {len(got)}/{len(idx)} câu.")
            JOB.prog(0.3 + 0.2 * len(result) / len(lines))
    p.save_lines([{"start": ln["start"], "end": ln["end"], "text": ln["text"], "vi": result.get(i, "")}
                  for i, ln in enumerate(lines)])


def do_translate(render_only: bool = False):
    p = State.project
    if not render_only or not p.lines:
        need_transcript(p)
        JOB.prog(0.3, "Dịch...")
        if manual_ai():
            manual_translate(p)
        else:
            p.run_translate(JOB.log, lambda x, m="": JOB.prog(0.3 + 0.2 * x, m), JOB.cancel)
    out = out_path(video_title(p), " - Vietsub")
    JOB.result = str(p.run_render(out, JOB.log, lambda x, m="": JOB.prog(0.5 + 0.5 * x, m), JOB.cancel))


# ------------------------------------------------------------------ trạng thái cho giao diện
def browse(kind: str = "video") -> list[dict]:
    """Video (hoặc nhạc) trong bộ nhớ máy (cần termux-setup-storage): Download, Movies, DCIM, Music, Zalo..."""
    exts = AUDIO_EXT if kind == "audio" else VIDEO_EXT
    dirs = ("Music", "Download", "Recordings", "Documents") if kind == "audio" else \
        ("Download", "Movies", "DCIM", "Pictures", "Zalo", "Telegram", "Documents")
    roots = [SHARED / d for d in dirs]
    out = []
    for r in roots:
        if not r.exists():
            continue
        for dirpath, dirs, files in os.walk(r):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "PhimViet"]
            for f in files:
                if f.lower().endswith(exts):
                    fp = Path(dirpath) / f
                    try:
                        st = fp.stat()
                    except OSError:
                        continue
                    out.append({"path": str(fp), "name": f, "dir": str(Path(dirpath).relative_to(SHARED)),
                                "size": st.st_size, "mtime": st.st_mtime})
            if len(out) > 400:
                break
    out.sort(key=lambda x: -x["mtime"])
    return out[:200]


def state(since: int = 0) -> dict:
    p = State.project
    d = {
        "version": VERSION, "busy": JOB.busy, "status": JOB.status, "progress": JOB.progress,
        "logs": JOB.logs[since:], "log_count": len(JOB.logs), "ask": JOB.ask,
        "result": Path(JOB.result).name if JOB.result else None,
        "storage": SHARED.exists(), "manual": manual_ai(),
        "online_ai": hybrid.online_ai(SETTINGS),
    }
    if p:
        d["video"] = {"name": Path(p.video).name, "title": video_title(p), "duration": p.info.duration,
                      "width": p.info.width, "height": p.info.height, "has_audio": p.info.has_audio,
                      "region": p.region, "source": len(p.source), "translated": sum(1 for x in p.lines if x.get("vi")),
                      "segs": len(State.segs)}
    return d


def settings_view() -> dict:
    s = SETTINGS
    keys = {k: bool(s.key(k)) for k in ("groq", "deepseek", "gemini", "openrouter", "openai", "claude")}
    return {
        "keys": keys, "ai": s.get("termux", "ai") or "auto", "mode": s.get("termux", "mode") or "recap",
        "target": s.get("termux", "target") or 180, "style": s.get("termux", "style") or "hap_dan",
        "styles": recap.STYLES, "speech": s.get("speech", "engine") or "auto",
        "ocr_lang": s.get("speech", "ocr_lang") or "auto", "language": s.get("speech", "language") or "auto",
        "voice_engine": s.get("voice", "engine") or "edge", "voice": s.get("voice", "voice") or "",
        "speed": s.get("voice", "speed") or 0, "output": s.get("video", "output") or "both",
        "aspect": s.get("video", "aspect") or "9:16", "height": s.get("video", "height") or 720,
        "fill": s.get("video", "fill") or "blur", "cover": s.get("video", "cover") or "auto",
        "background": s.get("video", "background") or "duck", "glossary": s.get("translate", "glossary") or "",
        "style_tr": s.get("translate", "style") or "natural", "styles_tr": {k: v[0] for k, v in translate.STYLES.items()},
        "out_dir": str(s.output_dir()), "separator": hybrid.has_module("onnxruntime"),
        "karaoke": bool(s.get("video", "karaoke", True)), "multi_shot": bool(s.get("video", "multi_shot", True)),
        "hook_title": bool(s.get("video", "hook_title", True)), "bgm": s.get("video", "bgm") or "",
        "bgm_volume": s.get("video", "bgm_volume") or 0.25,
    }


SETTABLE = {
    "ai": ("termux", "ai"), "mode": ("termux", "mode"), "target": ("termux", "target"), "style": ("termux", "style"),
    "speech": ("speech", "engine"), "ocr_lang": ("speech", "ocr_lang"), "language": ("speech", "language"),
    "voice_engine": ("voice", "engine"), "voice": ("voice", "voice"), "speed": ("voice", "speed"),
    "output": ("video", "output"), "aspect": ("video", "aspect"), "height": ("video", "height"),
    "fill": ("video", "fill"), "cover": ("video", "cover"), "background": ("video", "background"),
    "glossary": ("translate", "glossary"), "style_tr": ("translate", "style"),
    "karaoke": ("video", "karaoke"), "multi_shot": ("video", "multi_shot"), "hook_title": ("video", "hook_title"),
    "bgm": ("video", "bgm"), "bgm_volume": ("video", "bgm_volume"),
}


def self_update(log):
    """Tải bản mới (zip của nhánh) và thay thư mục Termux + VietDub; dữ liệu (data/) giữ nguyên."""
    import io
    import zipfile

    import requests

    repo = SETTINGS.get("update", "repo") or "tientran90td-commits/vtgt-cap-nhat"
    branch = SETTINGS.get("update", "branch") or "claude/movie-summary-app-0q90dq"
    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
    log("Tải bản mới...")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = HERE.parent
    n = 0
    for name in z.namelist():
        parts = name.split("/", 1)
        if len(parts) < 2 or not parts[1].startswith(("Termux/", "VietDub/")) or name.endswith("/"):
            continue
        rel = parts[1]
        if rel.startswith("VietDub/") and rel.split("/")[1] in ("data", ".venv", "tools", "opencut"):
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(z.read(name))
        n += 1
    log(f"✅ Đã cập nhật {n} file. Tắt Termux (gõ exit) rồi mở lại lệnh phimviet để dùng bản mới.")


# ------------------------------------------------------------------ máy chủ web
class Handler(BaseHTTPRequestHandler):
    server_version = "PhimViet"

    def log_message(self, *_a):
        pass

    def _ok_host(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _err(self, msg, code=400):
        self._json({"error": msg}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _file(self, path: Path, ctype: str | None = None):
        """Gửi file, hỗ trợ tua (Range) để xem video ngay trong trình duyệt."""
        size = path.stat().st_size
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a) if a else max(0, size - int(b))
            end = min(size - 1, int(b)) if (a and b) else end
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_GET(self):
        if not self._ok_host():
            return self._err("forbidden", 403)
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path in ("/", "/index.html"):
            return self._file(HERE / "web" / "index.html", "text/html; charset=utf-8")
        if u.path == "/api/state":
            return self._json(state(int(q.get("since", 0))))
        if u.path == "/api/settings":
            return self._json(settings_view())
        if u.path == "/api/browse":
            return self._json({"files": browse(q.get("kind", "video")), "storage": SHARED.exists()})
        if u.path == "/api/voices":
            eng = q.get("engine") or SETTINGS.get("voice", "engine") or "edge"
            vs = voices.list_voices(eng, SETTINGS)
            if eng == "edge":
                vs = [v for v in vs if v[0].startswith("vi-")] or vs
            return self._json({"voices": vs, "engines": {k: v["name"] for k, v in voices.ENGINES.items()
                                                         if k in ("edge", "gtts", "openai", "gemini", "elevenlabs")}})
        if u.path == "/api/frame":
            p = State.project
            if not p:
                return self._err("Chưa có video")
            t = float(q.get("t") or p.info.duration * 0.3)
            img = subprocess.run([hybrid_ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i",
                                  p.video, "-frames:v", "1", "-vf", "scale=720:-2", "-f", "image2pipe", "-c:v", "mjpeg",
                                  "-"], capture_output=True, timeout=60).stdout
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(img)))
            self.end_headers()
            self.wfile.write(img)
            return
        if u.path == "/api/script":
            p = State.project
            if not p:
                return self._err("Chưa có video")
            return self._json({"mode": SETTINGS.get("termux", "mode") or "recap", "title": State.recap_title,
                               "segments": State.segs, "lines": p.lines or [dict(x, vi="") for x in p.source]})
        if u.path == "/api/ocr_test":
            p = State.project
            if not p or not p.region:
                return self._err("Chưa đặt khung phụ đề")
            from vietdub import ocr
            t = float(q.get("t") or p.info.duration * 0.3)
            try:
                txt = ocr.read_image(ocr.grab(p.video, p.info, p.region, t), SETTINGS.get("speech", "ocr_lang") or "auto")
            except Exception as e:  # noqa: BLE001
                return self._err(str(e))
            return self._json({"text": txt})
        if u.path.startswith("/files/"):
            name = urllib.parse.unquote(u.path[7:])
            f = SETTINGS.output_dir() / Path(name).name
            if name == "preview.wav":
                f = app_home() / "preview.wav"
            if not f.exists():
                return self._err("Không có file", 404)
            return self._file(f)
        self._err("Không có trang này", 404)

    def do_POST(self):
        # chỉ nhận lệnh từ chính trang của app (chặn trang web lạ gửi lệnh tới máy chủ trên điện thoại)
        if not self._ok_host() or self.headers.get("X-PhimViet") != "1":
            return self._err("forbidden", 403)
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if u.path == "/api/upload":
            name = Path(q.get("name") or "video.mp4").name
            dst = SETTINGS.downloads_dir() / name
            n = int(self.headers.get("Content-Length") or 0)
            with open(dst, "wb") as f:
                left = n
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            try:
                open_video(dst, Path(name).stem)
            except Exception as e:  # noqa: BLE001
                return self._err(f"Không mở được video: {e}")
            return self._json({"ok": True})
        b = self._body()
        if u.path == "/api/open":
            f = Path(b.get("path", ""))
            if not f.exists() or not f.name.lower().endswith(VIDEO_EXT):
                return self._err("Không thấy file video")
            try:
                open_video(f, f.stem)
            except Exception as e:  # noqa: BLE001
                return self._err(f"Không mở được video: {e}")
            return self._json({"ok": True})
        if u.path == "/api/download":
            url = (b.get("url") or "").strip()
            m = re.search(r"https?://\S+", url)
            if not m:
                return self._err("Không thấy link")

            def job():
                f = download.download(m.group(0), SETTINGS, JOB.log, JOB.prog, JOB.cancel)
                open_video(f, f.stem)
            return self._json({"ok": JOB.start("Tải video", job)})
        if u.path == "/api/settings":
            for k, v in b.items():
                if k.startswith("key_"):
                    SETTINGS.set("keys", k[4:], str(v).strip())
                elif k in SETTABLE:
                    sec, key = SETTABLE[k]
                    SETTINGS.set(sec, key, v)
            SETTINGS.save()
            return self._json(settings_view())
        if u.path == "/api/region":
            p = State.project
            if not p:
                return self._err("Chưa có video")
            if b.get("auto"):
                reg = p.auto_region(JOB.cancel)
                if not reg:
                    return self._err("Không tự tìm thấy phụ đề cứng - kéo tay 2 thanh trượt")
            elif b.get("clear"):
                reg = None
            else:
                top, bottom = float(b["top"]), float(b["bottom"])
                x0, x1 = (p.region[0], p.region[2]) if p.region else (0.02, 0.98)
                reg = (x0, max(0.0, min(top, bottom - 0.02)), x1, min(1.0, bottom))
            p.set_region(reg)
            return self._json({"region": p.region})
        if u.path == "/api/run":
            if not State.project:
                return self._err("Chọn video trước")
            mode = SETTINGS.get("termux", "mode") or "recap"
            render_only = bool(b.get("render_only"))
            if b.get("redo"):
                State.segs = []
                State.project.save_lines([])
            fn = (lambda: do_recap(render_only)) if mode == "recap" else (lambda: do_translate(render_only))
            ok = JOB.start("Làm video review" if mode == "recap" else "Việt hóa video", fn)
            return self._json({"ok": ok} if ok else {"error": "Đang làm việc khác"})
        if u.path == "/api/reset":
            p = State.project
            if p:
                p.source = []
                p._save("source.json", [])
                p.save_lines([])
                State.segs = []
            return self._json({"ok": True})
        if u.path == "/api/script":
            p = State.project
            if not p:
                return self._err("Chưa có video")
            if "segments" in b:
                State.segs = [{"start": float(s["start"]), "text": str(s["text"]).strip()} for s in b["segments"]
                              if str(s.get("text", "")).strip()]
                State.recap_title = str(b.get("title") or State.recap_title)
                (p.dir / "recap.json").write_text(json.dumps({"title": State.recap_title, "segments": State.segs},
                                                             ensure_ascii=False, indent=1), encoding="utf-8")
            if "lines" in b:
                p.save_lines([{"start": float(x["start"]), "end": float(x["end"]), "text": x["text"],
                               "vi": str(x.get("vi") or "").strip()} for x in b["lines"]])
            return self._json({"ok": True})
        if u.path == "/api/answer":
            if not JOB.ask or b.get("id") != JOB.ask.get("id"):
                return self._err("Không có yêu cầu nào đang chờ")
            JOB.answer(b.get("text"))
            return self._json({"ok": True})
        if u.path == "/api/cancel":
            JOB.cancel.set()
            JOB.answer(None)
            return self._json({"ok": True})
        if u.path == "/api/voice_test":
            def job():
                eng = SETTINGS.get("voice", "engine") or "edge"
                voices.synth(eng, voices.SAMPLE, SETTINGS.get("voice", "voice") or "", app_home() / "preview.wav",
                             SETTINGS, JOB.log)
            return self._json({"ok": JOB.start("Nghe thử giọng", job)})
        if u.path == "/api/update":
            return self._json({"ok": JOB.start("Cập nhật", lambda: self_update(JOB.log))})
        self._err("Không có lệnh này", 404)


def hybrid_ffmpeg() -> str:
    from vietdub.media import ffmpeg_exe
    return ffmpeg_exe()


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Phim Việt Studio {VERSION} đang chạy: {url}")
    print("Giữ Termux mở. Bấm Ctrl+C để tắt.")
    if "--no-browser" not in sys.argv:
        opener = shutil.which("termux-open-url")
        if opener:
            subprocess.Popen([opener, url])
        else:
            import webbrowser
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
