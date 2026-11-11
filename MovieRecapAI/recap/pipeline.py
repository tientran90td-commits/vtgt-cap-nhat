"""Quản lý dự án và chuỗi xử lý: video -> lời thoại -> kịch bản AI -> giọng đọc -> video tóm tắt."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

from . import editor, film_id, script_writer, textnorm, transcribe, tts
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
        self.film: dict | None = None        # thông tin phim đã nhận diện
        self.visual: list[dict] | None = None  # mô tả khung hình do AI xem
        self.overlays: dict | None = None      # quảng cáo chèn cứng + logo cố định (None = chưa dò)
        self.exclusions: list[list] = []       # đoạn người dùng muốn bỏ: [[start, end], ...]
        self.episodes: list[dict] = []         # recap season: mốc từng tập trên dòng thời gian gộp
        self.season_exclusions: list[list] = []  # OP/ED từng tập
        self.load()
        from .season import load_season_meta

        meta = load_season_meta(self.video)
        if meta:
            self.episodes = meta.get("episodes", [])
            self.season_exclusions = meta.get("exclusions", [])

    # ---------------------------------------------------------------- lưu / nạp
    def _p(self, name: str) -> Path:
        return self.dir / name

    def load(self) -> None:
        for attr, name in (("transcript", "transcript.json"), ("scenes", "scenes.json"), ("script", "script.json"),
                           ("film", "film.json"), ("visual", "visual.json"), ("overlays", "overlays.json"),
                           ("exclusions", "exclusions.json")):
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
        if self.film is not None:
            film_id.save(self._p("film.json"), self.film)
        if self.visual is not None:
            film_id.save(self._p("visual.json"), self.visual)
        if self.overlays is not None:
            film_id.save(self._p("overlays.json"), self.overlays)
        film_id.save(self._p("exclusions.json"), self.exclusions or [])

    def blocked(self) -> list[list]:
        """Mọi khoảng không nên dùng làm cảnh: [start, end, loại]."""
        out = [[a, b, "user"] for a, b, *_ in (self.exclusions or [])]
        for a, b, *_ in self.season_exclusions or []:
            ep = next((e for e in self.episodes if abs(e["start"] - a) < 0.5), None)
            out.append([a, b, "opening" if ep else "ending"])
        for a, b in (self.overlays or {}).get("ranges", []):
            out.append([a, b, "overlay"])
        return out

    def run_overlays(self, log=_noop_log, progress=_noop_progress, cancel=None) -> dict:
        from .overlays import detect

        cancel = cancel or threading.Event()
        try:
            self.overlays = detect(self.video, self.info.duration, self.info.width, self.info.height,
                                   log, progress, cancel)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 - chỉ để chọn cảnh sạch hơn, lỗi thì bỏ qua
            log(f"Lọc quảng cáo chèn lỗi ({e}) - bỏ qua.", level="warn")
            self.overlays = {"ranges": [], "watermark": None}
        self.save()
        return self.overlays

    # ---------------------------------------------------------------- các bước
    def run_transcribe(self, log=_noop_log, progress=_noop_progress, cancel=None, subtitle_file=None,
                       engine=None) -> list[dict]:
        cancel = cancel or threading.Event()
        t = self.settings.section("transcribe")
        engine = engine or t.get("engine", "faster_whisper")
        self.transcript = transcribe.transcribe(
            self.video, self.dir, self.settings, engine, log, progress, cancel,
            subtitle_file=subtitle_file, model=t.get("model", "auto"), language=t.get("language", "auto"),
            device=t.get("device", "auto"), prompt=film_id.whisper_hint(self.film))
        self.save()
        log(f"Lời thoại: {len(self.transcript)} câu.")
        return self.transcript

    def run_scenes(self, log=_noop_log, progress=_noop_progress, cancel=None) -> list[float]:
        from .scenes import detect_scenes

        cancel = cancel or threading.Event()
        try:
            self.scenes = detect_scenes(self.video, log, progress, cancel)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 - dò cảnh chỉ để cắt clip đẹp hơn, lỗi thì bỏ qua
            log(f"Dò chuyển cảnh lỗi ({e}) - bỏ qua bước này, video vẫn được làm tiếp.", level="warn")
            self.scenes = []
        self.save()
        return self.scenes

    def run_identify(self, log=_noop_log, progress=_noop_progress, cancel=None) -> dict:
        """Nhận diện phim (tên, năm, nhân vật). Giữ lại ghi chú người dùng đã nhập."""
        cancel = cancel or threading.Event()
        notes = (self.film or {}).get("notes", "")
        self.film = film_id.identify(self.video, self.info.duration, self.transcript, self.settings, self.dir,
                                     log, progress, cancel)
        if notes:
            self.film["notes"] = notes
        self.save()
        return self.film

    def run_visual(self, log=_noop_log, progress=_noop_progress, cancel=None) -> list[dict]:
        cancel = cancel or threading.Event()
        self.visual = film_id.visual_notes(self.video, self.info.duration, self.film, self.settings, self.dir,
                                           log, progress, cancel)
        self.save()
        return self.visual

    def run_script(self, log=_noop_log, progress=_noop_progress, cancel=None) -> dict:
        cancel = cancel or threading.Event()
        opts = self.settings.section("script")
        self.script = script_writer.write_script(self.transcript, self.info.duration, self.settings, opts,
                                                 log, progress, cancel, self.scenes or [], self.film, self.visual,
                                                 self.episodes, self.blocked())
        self.save()
        return self.script

    def voice_opts(self) -> dict:
        v = self.settings.section("voice")
        lang = self.settings.get("script", "language", "Tiếng Việt")
        v["lang_code"] = tts.LANG_CODES.get(lang, "en")
        return v

    @staticmethod
    def segment_tone(seg: dict, v: dict) -> str:
        """Cách đọc của 1 đoạn: cách đọc AI/người dùng gán cho đoạn (nếu bật) > cách đọc chung."""
        if v.get("tone_auto", True) and seg.get("tone") in tts.READ_STYLES:
            return seg["tone"]
        return v.get("read_style") or "natural"

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
            vo = dict(v, tone=self.segment_tone(seg, v))
            key = tts.voice_cache_key(engine, voice, spoken[i], vo)
            out = vdir / f"v{i:03d}_{key}.wav"
            if not out.exists() or out.stat().st_size < 1000:
                progress(i / len(segs), f"Đọc giọng đoạn {i + 1}/{len(segs)}")
                for old in vdir.glob(f"v{i:03d}_*.wav"):
                    old.unlink(missing_ok=True)
                if spoken[i] != text:
                    log(f"Đoạn {i + 1} đọc là: {tts.speak_text(spoken[i], v)}", level="debug")
                tts.synthesize(engine, spoken[i], voice, out, vo, self.settings, cancel=cancel)
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
        opts["_target_seconds"] = float(self.settings.get("script", "target_minutes", 5) or 5) * 60
        if opts.get("avoid_overlays", True) or opts.get("delogo", True) or opts.get("hardsub_mode", "blur") != "none":
            if self.overlays is None or int(self.overlays.get("version", 1)) < 2:
                log("Lọc quảng cáo chèn & logo của nguồn...")
                self.run_overlays(log, lambda p, m="": progress((0.4 if has_narr else 0) + p * 0.05, m), cancel)
        res = editor.render(self.script, self.video, self.info, voices, opts, out_path, self.dir, self.transcript,
                            log, lambda p, m="": progress((0.4 if has_narr else 0) + p * (0.6 if has_narr else 1), m),
                            cancel, blocked=self.blocked(), watermark=(self.overlays or {}).get("watermark"),
                            hardsub=(self.overlays or {}).get("hardsub"))
        txt = out_path.with_suffix(".txt")
        txt.write_text(script_writer.script_to_text(self.script), encoding="utf-8")
        return res

    def run_all(self, log=_noop_log, progress=_noop_progress, cancel=None, subtitle_file=None,
                out_path=None) -> Path:
        cancel = cancel or threading.Event()
        sc = self.settings.section("script")
        ai = sc.get("provider") != "none"
        web = sc.get("provider") == "web"  # bản web: bớt số lần copy-dán (bỏ tự nhận diện & AI xem cảnh)
        if ai and not web and sc.get("identify", True) and not self.film:
            log("Bước 1/6: Nhận diện phim")
            try:
                self.run_identify(log, lambda p, m="": progress(p * 0.04, m), cancel)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Không nhận diện được phim ({e}) - tiếp tục.", level="warn")
        if not self.transcript:
            log("Bước 2/6: Nhận dạng lời thoại")
            self.run_transcribe(log, lambda p, m="": progress(0.04 + p * 0.32, m), cancel, subtitle_file)
            # Nhận diện lại bằng lời thoại nếu lần đầu chưa chắc chắn
            if ai and not web and sc.get("identify", True) and float((self.film or {}).get("confidence") or 0) < 0.6:
                try:
                    self.run_identify(log, lambda p, m="": progress(0.36 + p * 0.02, m), cancel)
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"Nhận diện lại lỗi ({e}).", level="warn")
        if self.settings.get("transcribe", "use_scenes", True) and self.scenes is None:
            log("Bước 3/6: Dò chuyển cảnh")
            self.run_scenes(log, lambda p, m="": progress(0.38 + p * 0.1, m), cancel)
        ro = self.settings.section("render")
        if (ro.get("avoid_overlays", True) or ro.get("delogo", True) or ro.get("hardsub_mode", "blur") != "none") and \
                (self.overlays is None or int(self.overlays.get("version", 1)) < 2):
            log("Lọc quảng cáo chèn & logo của nguồn")
            self.run_overlays(log, lambda p, m="": progress(0.47 + p * 0.03, m), cancel)
        if ai and not web and sc.get("visual") and not self.visual:
            log("Bước 4/6: AI xem hình ảnh các cảnh")
            try:
                self.run_visual(log, lambda p, m="": progress(0.48 + p * 0.07, m), cancel)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"AI xem cảnh lỗi ({e}) - bỏ qua.", level="warn")
        log("Bước 5/6: AI viết kịch bản")
        self.run_script(log, lambda p, m="": progress(0.55 + p * 0.07, m), cancel)
        log("Bước 6/6: Lồng tiếng & dựng video")
        return self.run_render(out_path, log, lambda p, m="": progress(0.62 + p * 0.38, m), cancel)


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
