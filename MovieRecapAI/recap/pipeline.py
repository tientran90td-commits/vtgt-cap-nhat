"""Quản lý dự án và chuỗi xử lý: video -> lời thoại -> kịch bản AI -> giọng đọc -> video tóm tắt."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

from . import editor, script_writer, textnorm, transcribe, tts
from .config import Settings
from .ffmpeg_utils import Cancelled, MediaInfo, probe, set_ffmpeg_path


def _noop_log(msg, level="info"):
    print(msg)


def _noop_progress(p, msg=""):
    pass


def safe_name(s: str, maxlen: int = 60) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", s).strip()
    return (s[:maxlen].strip() or "video")


class Project:
    """Một phim = một thư mục làm việc chứa transcript, cảnh, kịch bản, giọng đọc, bản dựng tạm."""

    def __init__(self, video: str, settings: Settings):
        self.settings = settings
        set_ffmpeg_path(settings.get("paths", "ffmpeg") or None)
        self.video = str(Path(video).resolve())
        self.info: MediaInfo = probe(self.video)
        st = Path(self.video).stat()
        h = hashlib.sha1(f"{self.video}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:8]
        self.dir = settings.workspace() / f"{safe_name(Path(self.video).stem, 40)}_{h}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.transcript: list[dict] = []
        self.scenes: list[float] | None = None  # None = chưa dò
        self.script: dict | None = None
        self.load()

    # ---------------------------------------------------------------- lưu / nạp
    def _p(self, name: str) -> Path:
        return self.dir / name

    def load(self) -> None:
        for attr, name in (("transcript", "transcript.json"), ("scenes", "scenes.json"), ("script", "script.json")):
            f = self._p(name)
            if f.exists():
                try:
                    setattr(self, attr, json.loads(f.read_text(encoding="utf-8")))
                except Exception:
                    pass

    def save(self) -> None:
        self._p("transcript.json").write_text(json.dumps(self.transcript, ensure_ascii=False), encoding="utf-8")
        if self.scenes is not None:
            self._p("scenes.json").write_text(json.dumps(self.scenes), encoding="utf-8")
        if self.script is not None:
            script_writer.save_script(self.script, self._p("script.json"))

    # ---------------------------------------------------------------- các bước
    def run_transcribe(self, log=_noop_log, progress=_noop_progress, cancel=None, subtitle_file=None,
                       engine=None) -> list[dict]:
        cancel = cancel or threading.Event()
        t = self.settings.section("transcribe")
        engine = engine or t.get("engine", "faster_whisper")
        self.transcript = transcribe.transcribe(
            self.video, self.dir, self.settings, engine, log, progress, cancel,
            subtitle_file=subtitle_file, model=t.get("model", "small"), language=t.get("language", "auto"),
            device=t.get("device", "auto"))
        self.save()
        log(f"Lời thoại: {len(self.transcript)} câu.")
        return self.transcript

    def run_scenes(self, log=_noop_log, progress=_noop_progress, cancel=None) -> list[float]:
        from .scenes import detect_scenes

        cancel = cancel or threading.Event()
        self.scenes = detect_scenes(self.video, log, progress, cancel)
        self.save()
        return self.scenes

    def run_script(self, log=_noop_log, progress=_noop_progress, cancel=None) -> dict:
        cancel = cancel or threading.Event()
        opts = self.settings.section("script")
        self.script = script_writer.write_script(self.transcript, self.info.duration, self.settings, opts,
                                                 log, progress, cancel, self.scenes or [])
        self.save()
        return self.script

    def voice_opts(self) -> dict:
        v = self.settings.section("voice")
        lang = self.settings.get("script", "language", "Tiếng Việt")
        v["lang_code"] = tts.LANG_CODES.get(lang, "en")
        return v

    def run_voices(self, log=_noop_log, progress=_noop_progress, cancel=None) -> list:
        cancel = cancel or threading.Event()
        if not self.script:
            raise RuntimeError("Chưa có kịch bản.")
        v = self.voice_opts()
        engine, voice = v.get("engine", "edge"), v.get("voice", "")
        if not voice:
            raise RuntimeError("Chưa chọn giọng đọc (mục 🎙️ Giọng đọc).")
        vdir = self.dir / "voices"
        vdir.mkdir(exist_ok=True)
        segs = self.script["segments"]
        texts = [(seg.get("narration") or "").strip() for seg in segs]
        spoken = list(texts)
        if v.get("ai_pron"):
            idx = [i for i, t in enumerate(texts) if t]
            log("AI đang soát phát âm lời thuyết minh...")
            progress(0.02, "AI soát phát âm")
            fixed = textnorm.ai_speakable([texts[i] for i in idx], self.settings.get("script", "language", "Tiếng Việt"),
                                          self.settings, bool(v.get("transliterate")), log, cache_dir=self.dir)
            for i, t in zip(idx, fixed):
                spoken[i] = t
        files: list = []
        for i, seg in enumerate(segs):
            if cancel.is_set():
                raise Cancelled()
            text = texts[i]
            if not text:
                files.append(None)
                continue
            key = tts.voice_cache_key(engine, voice, spoken[i], v)
            out = vdir / f"v{i:03d}_{key}.wav"
            if not out.exists():
                progress(i / len(segs), f"Đọc giọng đoạn {i + 1}/{len(segs)}")
                for old in vdir.glob(f"v{i:03d}_*.wav"):
                    old.unlink(missing_ok=True)
                if spoken[i] != text:
                    log(f"Đoạn {i + 1} đọc là: {tts.speak_text(spoken[i], v)}", level="debug")
                tts.synthesize(engine, spoken[i], voice, out, v, self.settings, cancel=cancel)
            files.append(out)
        progress(1.0, "Xong giọng đọc")
        log(f"Giọng đọc: {sum(1 for f in files if f)} đoạn ({tts.ENGINES[engine]['name']} / {voice}).")
        return files

    def default_output(self) -> Path:
        title = (self.script or {}).get("title") or Path(self.video).stem
        base = self.settings.output_dir() / f"{safe_name(title)}_recap.mp4"
        n = 1
        out = base
        while out.exists():
            n += 1
            out = base.with_name(f"{base.stem}_{n}.mp4")
        return out

    def run_render(self, out_path: Path | None = None, log=_noop_log, progress=_noop_progress, cancel=None) -> Path:
        cancel = cancel or threading.Event()
        if not self.script or not self.script.get("segments"):
            raise RuntimeError("Chưa có kịch bản để dựng.")
        has_narr = any((s.get("narration") or "").strip() for s in self.script["segments"])
        if has_narr:
            log("① Tạo giọng đọc...")
            voices = self.run_voices(log, lambda p, m="": progress(p * 0.4, m), cancel)
        else:
            voices = [None] * len(self.script["segments"])
        out_path = Path(out_path) if out_path else self.default_output()
        log("② Dựng video...")
        opts = self.settings.section("render")
        res = editor.render(self.script, self.video, self.info, voices, opts, out_path, self.dir, self.transcript,
                            log, lambda p, m="": progress((0.4 if has_narr else 0) + p * (0.6 if has_narr else 1), m),
                            cancel)
        txt = out_path.with_suffix(".txt")
        txt.write_text(script_writer.script_to_text(self.script), encoding="utf-8")
        return res

    def run_all(self, log=_noop_log, progress=_noop_progress, cancel=None, subtitle_file=None,
                out_path=None) -> Path:
        cancel = cancel or threading.Event()
        if not self.transcript:
            log("Bước 1/4: Nhận dạng lời thoại")
            self.run_transcribe(log, lambda p, m="": progress(p * 0.35, m), cancel, subtitle_file)
        if self.settings.get("transcribe", "use_scenes", True) and self.scenes is None:
            log("Bước 2/4: Dò chuyển cảnh")
            self.run_scenes(log, lambda p, m="": progress(0.35 + p * 0.15, m), cancel)
        log("Bước 3/4: AI viết kịch bản")
        self.run_script(log, lambda p, m="": progress(0.5 + p * 0.1, m), cancel)
        log("Bước 4/4: Lồng tiếng & dựng video")
        return self.run_render(out_path, log, lambda p, m="": progress(0.6 + p * 0.4, m), cancel)


def download_video(url: str, settings: Settings, log=_noop_log, progress=_noop_progress, cancel=None) -> tuple[str, str | None]:
    """Tải video bằng yt-dlp (YouTube, Facebook, TikTok, Bilibili... 1000+ trang). Trả (video, phụ đề|None)."""
    import yt_dlp

    from .ffmpeg_utils import ffmpeg_exe

    cancel = cancel or threading.Event()
    dest = settings.workspace() / "downloads"
    dest.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if cancel.is_set():
            raise Cancelled()
        if d.get("status") == "downloading":
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if tot:
                progress(d.get("downloaded_bytes", 0) / tot, f"Tải video {d.get('_percent_str', '').strip()}")

    opts = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "outtmpl": str(dest / "%(title).80s [%(id)s].%(ext)s"),
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_exe(),
        "progress_hooks": [hook],
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["vi", "en", "en-US"],
        "subtitlesformat": "srt/vtt/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "ignoreerrors": False,
    }
    proxy = (settings.get("api", "proxy") or "").strip()
    if proxy:
        opts["proxy"] = proxy
    log(f"Đang tải: {url}")
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            if "subtitle" in str(e).lower():
                opts.update(writesubtitles=False, writeautomaticsub=False)
                with yt_dlp.YoutubeDL(opts) as ydl2:
                    info = ydl2.extract_info(url, download=True)
            else:
                raise
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
        if not path.exists():
            cands = sorted(dest.glob(f"*[[]{info.get('id')}[]].*"), key=lambda p: p.stat().st_size, reverse=True)
            cands = [c for c in cands if c.suffix.lower() in (".mp4", ".mkv", ".webm")]
            if not cands:
                raise RuntimeError("Không tìm thấy file đã tải.")
            path = cands[0]
    sub = None
    for lang in ("vi", "en", "en-US"):
        for ext in ("srt", "vtt"):
            for c in dest.glob(f"*[[]{info.get('id')}[]].{lang}*.{ext}"):
                sub = str(c)
                break
            if sub:
                break
        if sub:
            break
    log(f"Đã tải xong: {path.name}" + (f" (kèm phụ đề {Path(sub).name})" if sub else ""))
    return str(path), sub
