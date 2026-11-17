"""Công cụ AI của VietDub dùng ngay trong OpenCut (tab "VietDub AI"), chạy trên máy qua máy chủ 127.0.0.1.

OpenCut gửi file (hoặc chữ / link) -> VietDub làm ở luồng nền -> trả về file kết quả để OpenCut thêm vào dòng thời gian.
Công cụ: đọc chữ thành giọng, tạo phụ đề Việt, thuyết minh tiếng Việt, tách nhạc nền & giọng, xóa phụ đề cứng,
tải video từ link, dịch chữ sang tiếng Việt.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from .config import Settings, app_home
from .media import Cancelled, probe

_JOBS: dict[str, dict] = {}
_UPLOADS: dict[str, Path] = {}
_LOCK = threading.Lock()
_STATE: dict = {"settings": None}
MAX_UPLOAD = 8 * 1024 ** 3


def set_settings(settings: Settings) -> None:
    _STATE["settings"] = settings


def settings() -> Settings:
    return _STATE["settings"] or Settings()


def work_root() -> Path:
    d = app_home() / "opencut-jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cleanup(max_age_h: float = 48) -> None:
    """Dọn file tạm của công cụ cũ hơn 2 ngày (đỡ đầy ổ)."""
    now = time.time()
    for d in work_root().iterdir():
        try:
            if now - d.stat().st_mtime > max_age_h * 3600:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name or "file").strip(" .")
    return name[:120] or "file"


def save_upload(name: str, stream, length: int) -> str:
    if length <= 0 or length > MAX_UPLOAD:
        raise ValueError("File rỗng hoặc quá lớn.")
    uid = uuid.uuid4().hex[:12]
    d = work_root() / f"up_{uid}"
    d.mkdir(parents=True)
    f = d / safe_name(name)
    left = length
    with open(f, "wb") as fh:
        while left > 0:
            chunk = stream.read(min(1 << 20, left))
            if not chunk:
                break
            fh.write(chunk)
            left -= len(chunk)
    if left:
        raise ValueError("Tải file lên bị ngắt giữa chừng.")
    with _LOCK:
        _UPLOADS[uid] = f
    return uid


def upload_path(uid: str) -> Path:
    f = _UPLOADS.get(uid or "")
    if not f or not f.exists():
        raise ValueError("Không thấy file đã gửi - thử lại.")
    return f


# ------------------------------------------------------------------ công việc nền
def start(tool: str, args: dict) -> str:
    fn = TOOLS.get(tool)
    if fn is None:
        raise ValueError(f"Không có công cụ '{tool}'.")
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "tool": tool, "state": "running", "progress": 0.0, "message": "Đang bắt đầu...",
           "log": [], "result": None, "error": None, "cancel": threading.Event(), "dir": work_root() / f"job_{jid}"}
    job["dir"].mkdir(parents=True)

    def log(m, level="info"):
        job["log"] = (job["log"] + [str(m)])[-30:]
        if level != "debug":
            job["message"] = str(m)

    def progress(p, m=""):
        job["progress"] = max(0.0, min(1.0, float(p)))
        if m:
            job["message"] = m

    def run():
        try:
            job["result"] = fn(args, job["dir"], log, progress, job["cancel"])
            job["state"], job["progress"], job["message"] = "done", 1.0, "Xong"
        except Cancelled:
            job["state"], job["message"] = "cancelled", "Đã hủy"
        except Exception as e:  # noqa: BLE001
            job["state"], job["error"], job["message"] = "error", str(e) or e.__class__.__name__, "Lỗi"
    with _LOCK:
        _JOBS[jid] = job
    threading.Thread(target=run, daemon=True).start()
    return jid


def status(jid: str) -> dict:
    job = _JOBS.get(jid)
    if not job:
        return {"state": "missing"}
    out = {k: job[k] for k in ("id", "tool", "state", "progress", "message", "error")}
    out["result"] = job["result"] if job["state"] == "done" else None
    return out


def cancel(jid: str) -> None:
    job = _JOBS.get(jid)
    if job:
        job["cancel"].set()


def job_file(jid: str, name: str) -> Path | None:
    job = _JOBS.get(jid)
    if not job:
        return None
    f = (job["dir"] / safe_name(name)).resolve()
    return f if f.parent == job["dir"].resolve() and f.exists() else None


def _item(job_dir: Path, f: Path, kind: str, label: str | None = None) -> dict:
    return {"name": label or f.name, "url": f"/vietdub/api/file/{job_dir.name[4:]}/{f.name}", "kind": kind}


def _project(src: Path, job_dir: Path):
    """Dự án VietDub tạm cho 1 file từ OpenCut (dùng lại toàn bộ quy trình của app)."""
    from .project import Project

    p = Project(str(src), settings())
    return p


# ------------------------------------------------------------------ các công cụ
def tool_voices(_args, _d, _log, _progress, _cancel) -> dict:
    from . import voices

    s = settings()
    out = {}
    for eng in ("vieneu", "edge", "piper"):
        try:
            out[eng] = [{"id": v, "label": label} for v, label in
                        (voices.list_voices(eng, s) if eng != "edge" else voices._EDGE_DEFAULT)]
        except Exception:  # noqa: BLE001
            out[eng] = []
    return {"voices": out, "default": {"engine": s.get("voice", "engine"), "voice": s.get("voice", "voice")}}


def tool_tts(args, d, log, progress, cancel) -> dict:
    """Đọc chữ thành giọng (mặc định giọng đang chọn trong VietDub, vd Ngọc Huyền)."""
    from . import hybrid, voices

    text = " ".join(str(args.get("text") or "").split())
    if not text:
        raise ValueError("Nhập chữ cần đọc.")
    s = settings()
    want = args.get("engine") or s.get("voice", "engine") or "vieneu"
    chain = hybrid.voice_chain(s, want)
    last = None
    for eng in chain:
        voice = (args.get("voice") if eng == want else "") or (s.get("voice", "voice") if eng == want else "") or \
            voices.default_voice(eng)
        try:
            progress(0.2, f"Đọc bằng {voices.ENGINES[eng]['name'].split(' - ')[0]}...")
            out = voices.synth(eng, text, voice, d / "giong_doc.wav", s, log)
            label = (text[:40] + ("…" if len(text) > 40 else "")) + ".wav"
            return {"items": [_item(d, out, "audio", "Giọng: " + label)], "engine": eng}
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"{eng} lỗi ({e}) - thử giọng khác.", "warn")
    raise RuntimeError(f"Không đọc được: {last}")


def _transcribe_translate(src: Path, d: Path, log, progress, cancel):
    from . import translate

    p = _project(src, d)
    if not p.source:
        progress(0.05, "Nghe lời thoại...")
        p.run_transcript(log, lambda x, m="": progress(0.05 + x * 0.45, m), cancel)
    if not p.lines or len(p.lines) != len(p.source):
        progress(0.5, "Dịch sang tiếng Việt...")
        p.run_translate(log, lambda x, m="": progress(0.5 + x * 0.3, m), cancel)
    srt = d / "phu_de_viet.srt"
    srt.write_text(translate.to_srt(p.lines), encoding="utf-8")
    return p, srt


def tool_subtitles(args, d, log, progress, cancel) -> dict:
    """Nghe lời gốc -> dịch -> phụ đề Việt (chữ sửa được trên dòng thời gian)."""
    src = upload_path(args.get("upload"))
    _p, srt = _transcribe_translate(src, d, log, progress, cancel)
    return {"items": [_item(d, srt, "subtitle", "Phụ đề Việt.srt")]}


def tool_dub(args, d, log, progress, cancel) -> dict:
    """Thuyết minh tiếng Việt cho cả file: giọng đọc khớp thời gian + phụ đề Việt."""
    from . import dub

    src = upload_path(args.get("upload"))
    p, srt = _transcribe_translate(src, d, log, progress, cancel)
    progress(0.8, "Đọc giọng thuyết minh...")
    files = p.voice_files(p.lines, log, lambda x, m="": progress(0.8 + x * 0.15, m), cancel)
    wav = d / "thuyet_minh.wav"
    dub.build(p.lines, files, p.info.duration, wav, float(settings().get("voice", "max_speed", 1.35)),
              cancel=cancel, log=log)
    return {"items": [_item(d, wav, "audio", "Thuyết minh tiếng Việt.wav"),
                      _item(d, srt, "subtitle", "Phụ đề Việt.srt")]}


def tool_separate(args, d, log, progress, cancel) -> dict:
    """Tách nhạc nền & giọng nói (model UVR)."""
    import numpy as np

    from . import separate
    from .media import run

    src = upload_path(args.get("upload"))
    info = probe(src)
    if not info.has_audio:
        raise ValueError("File này không có tiếng.")
    if not separate.available():
        raise RuntimeError("Chưa cài bộ tách nhạc (📦 Thư viện trong VietDub → Tách nhạc nền).")
    bg = separate.background(str(src), info, d, settings(), log, lambda x, m="": progress(x * 0.85, m), cancel)
    progress(0.88, "Tách giọng nói...")
    mix_raw, bg_raw = d / "mix.f32", d / "bg.f32"
    run(["-i", str(src), "-vn", "-ac", "2", "-ar", "44100", "-f", "f32le", str(mix_raw)], cancel=cancel)
    run(["-i", str(bg), "-ac", "2", "-ar", "44100", "-f", "f32le", str(bg_raw)], cancel=cancel)
    m = np.fromfile(mix_raw, "<f4").reshape(-1, 2)
    b = np.fromfile(bg_raw, "<f4").reshape(-1, 2)
    n = min(len(m), len(b))
    raw = d / "giong_noi.f32"
    np.clip(m[:n] - b[:n], -1, 1).astype("<f4").tofile(raw)   # giọng = tiếng gốc - nhạc nền
    vf = d / "giong_noi.wav"
    run(["-f", "f32le", "-ar", "44100", "-ac", "2", "-i", str(raw), "-c:a", "pcm_s16le", str(vf)], cancel=cancel)
    music = d / "nhac_nen.wav"
    run(["-i", str(bg), "-c:a", "pcm_s16le", str(music)], cancel=cancel)
    for f in (mix_raw, bg_raw, raw):
        f.unlink(missing_ok=True)
    return {"items": [_item(d, music, "audio", "Nhạc nền (đã bỏ giọng).wav"),
                      _item(d, vf, "audio", "Giọng nói (đã bỏ nhạc).wav")]}


def tool_remove_subs(args, d, log, progress, cancel) -> dict:
    """Xóa phụ đề cứng thông minh (chỉ đúng chỗ, đúng lúc có chữ)."""
    from . import hardsub, render

    src = upload_path(args.get("upload"))
    info = probe(src)
    progress(0.05, "Dò phụ đề cứng...")
    band = hardsub.detect(str(src), info, d, cancel, log)
    if not band:
        raise RuntimeError("Không thấy phụ đề cứng trong video này.")
    boxes = hardsub.timeline(str(src), info, band, d, cancel, log)
    out = render.clean_video(str(src), info, {"cover": "auto", "aspect": "source"}, d / f"{src.stem}_sach.mp4",
                             d / "work", log, lambda x, m="": progress(0.3 + x * 0.7, m), cancel, band=band,
                             boxes=boxes)
    return {"items": [_item(d, out, "video", f"{src.stem} (đã xóa phụ đề).mp4")]}


def tool_download(args, d, log, progress, cancel) -> dict:
    from . import download

    url = str(args.get("url") or "").strip()
    if not download.is_url(url):
        raise ValueError("Dán link video (https://...).")
    f = download.download(url, settings(), log, progress, cancel)
    dst = d / safe_name(f.name)
    shutil.copy2(f, dst)
    return {"items": [_item(d, dst, "video", f.name)]}


def tool_translate_text(args, d, log, progress, cancel) -> dict:
    """Dịch các đoạn chữ sang tiếng Việt (giữ nguyên số đoạn)."""
    from .ai import chat, extract_json

    texts = [str(t) for t in (args.get("texts") or []) if str(t).strip()]
    if not texts:
        raise ValueError("Chọn đoạn chữ trên dòng thời gian trước.")
    progress(0.2, "AI đang dịch...")
    body = "\n".join(f"{i + 1} | {t}" for i, t in enumerate(texts))
    system = ("Translate each numbered line into natural, standard Vietnamese with full diacritics. Keep it short "
              "enough for on-screen text. Reply ONLY with JSON {\"lines\": {\"<id>\": \"<Vietnamese>\"}}.")
    data = extract_json(chat(settings(), system, body, json_mode=True, max_tokens=2000, log=log, cancel=cancel))
    got = data.get("lines", data) if isinstance(data, dict) else {}
    out = [str(got.get(str(i + 1)) or got.get(i + 1) or t).strip() for i, t in enumerate(texts)]
    return {"texts": out}


TOOLS = {"voices": tool_voices, "tts": tool_tts, "subtitles": tool_subtitles, "dub": tool_dub,
         "separate": tool_separate, "remove_subs": tool_remove_subs, "download": tool_download,
         "translate_text": tool_translate_text}


def handle_json(body: bytes) -> dict:
    try:
        return json.loads(body.decode("utf-8") or "{}")
    except ValueError as e:
        raise ValueError("Dữ liệu gửi lên không hợp lệ.") from e
