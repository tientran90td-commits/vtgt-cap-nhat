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


# ---- Các bước của quá trình làm video (giao diện hiện thành thanh tiến trình từng bước)
STEP_TAG = "§step§"
STEPS = {"identify": "🔍 Nhận diện phim", "transcribe": "🎧 Nhận dạng lời thoại", "scenes": "🎞️ Dò chuyển cảnh",
         "overlays": "🛡️ Lọc quảng cáo / logo / phụ đề cứng", "visual": "👁️ AI xem cảnh",
         "script": "✍️ AI viết kịch bản", "voice": "🎙️ Lồng tiếng", "render": "🎬 Dựng video",
         "publish": "📣 Thumbnail & tiêu đề"}


def step(log, sid: str, state: str, note: str = "") -> None:
    """Báo trạng thái 1 bước: start | done | skip | fail (giao diện vẽ thành thanh các bước)."""
    log(f"{STEP_TAG}{sid}§{state}§{note}", level="step")


def step_text(msg: str) -> str:
    """Chuyển tin báo bước thành câu dễ đọc (cho dòng lệnh / nhật ký)."""
    try:
        sid, state, note = msg[len(STEP_TAG):].split("§", 2)
    except ValueError:
        return msg
    name = STEPS.get(sid, sid)
    icon = {"start": "▶", "done": "✅", "skip": "⏭", "fail": "❌"}.get(state, "•")
    return f"{icon} {name}" + (f" - {note}" if note else "")


def _noop_log(msg, level="info"):
    print(step_text(msg) if level == "step" else msg)


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
            ep = next((e for e in self.episodes if e["start"] - 0.5 <= a < e["end"]), None)
            mid = (ep["start"] + ep["end"]) / 2 if ep else a + 1
            out.append([a, b, "opening" if a < mid else "ending"])
        for a, b in (self.overlays or {}).get("ranges", []):
            out.append([a, b, "overlay"])
        return out

    def run_overlays(self, log=_noop_log, progress=_noop_progress, cancel=None) -> dict:
        from .overlays import detect

        cancel = cancel or threading.Event()
        try:
            self.overlays = detect(self.video, self.info.duration, self.info.width, self.info.height,
                                   log, progress, cancel, fast=bool(self.settings.get("render", "fast_scan")))
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
        todo = []  # (i, file, opts) cần đọc
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
                for old in vdir.glob(f"v{i:03d}_*.wav"):
                    old.unlink(missing_ok=True)
                if spoken[i] != text:
                    log(f"Đoạn {i + 1} đọc là: {tts.speak_text(spoken[i], v)}", level="debug")
                todo.append((i, out, vo))
            files.append(out)
        # giọng online (Edge, OpenAI, Gemini...) đọc nhiều đoạn cùng lúc; giọng offline đọc lần lượt
        workers = int(v.get("parallel", 1) or 1)
        if tts.ENGINES.get(engine, {}).get("offline", True):
            workers = 1
        if workers <= 1 or len(todo) <= 1:
            for n, (i, out, vo) in enumerate(todo):
                if cancel.is_set():
                    raise Cancelled()
                progress(n / max(1, len(todo)), f"Đọc giọng đoạn {i + 1}/{len(segs)}")
                tts.synthesize(engine, spoken[i], voice, out, vo, self.settings, cancel=cancel)
        else:
            from concurrent.futures import ThreadPoolExecutor

            log(f"Đọc {len(todo)} đoạn giọng, {workers} đoạn cùng lúc...")
            done_n = [0]

            def one(job):
                i, out, vo = job
                if cancel.is_set():
                    raise Cancelled()
                tts.synthesize(engine, spoken[i], voice, out, vo, self.settings, cancel=cancel)
                done_n[0] += 1
                progress(done_n[0] / len(todo), f"Đọc giọng {done_n[0]}/{len(todo)} ({workers} luồng)")
            with ThreadPoolExecutor(max_workers=min(6, workers)) as ex:
                for f in [ex.submit(one, j) for j in todo]:
                    f.result()
        progress(1.0, "Xong giọng đọc")
        log(f"Giọng đọc: {sum(1 for f in files if f)} đoạn ({tts.ENGINES[engine]['name']} / {voice}).")
        return files

    def estimate_seconds(self) -> float:
        """Ước tính độ dài video từ kịch bản hiện tại (dùng giọng đã đọc nếu có, không thì ước theo số chữ)."""
        import wave

        segs = (self.script or {}).get("segments") or []
        vdir = self.dir / "voices"
        rate = 1 + float(self.settings.get("voice", "rate", 0) or 0) / 100
        total = 0.0
        for i, seg in enumerate(segs):
            text = (seg.get("narration") or "").strip()
            if not text:
                total += max(1.0, min(90.0, float(seg.get("end", 0)) - float(seg.get("start", 0))))
                continue
            got = None
            for f in sorted(vdir.glob(f"v{i:03d}_*.wav")) if vdir.exists() else []:
                try:
                    with wave.open(str(f)) as w:
                        got = w.getnframes() / float(w.getframerate())
                    break
                except Exception:  # noqa: BLE001
                    continue
            total += (got if got else len(text.split()) / (3.6 * max(0.5, rate))) + 0.35
        return total

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
            step(log, "voice", "start")
            voices = self.run_voices(log, lambda p, m="": progress(p * 0.4, m), cancel)
            step(log, "voice", "done", f"{sum(1 for v in voices if v)} đoạn")
        else:
            voices = [None] * len(self.script["segments"])
            step(log, "voice", "skip", "giữ thoại gốc")
        out_path = Path(out_path) if out_path else self.default_output()
        step(log, "render", "start")
        opts = self.settings.section("render")
        opts["_target_seconds"] = float(self.settings.get("script", "target_minutes", 5) or 5) * 60
        if opts.get("hardsub_mode") == "vsr":
            from . import vsr
            opts["vsr_dir"] = vsr.resolve_dir(opts.get("vsr_dir", ""), self.settings)
        if opts.get("avoid_overlays", True) or opts.get("delogo", True) or opts.get("hardsub_mode", "blur") != "none":
            if self.overlays is None or int(self.overlays.get("version", 1)) < 2:
                log("Lọc quảng cáo chèn & logo của nguồn...")
                self.run_overlays(log, lambda p, m="": progress((0.4 if has_narr else 0) + p * 0.05, m), cancel)
        res = editor.render(self.script, self.video, self.info, voices, opts, out_path, self.dir, self.transcript,
                            log, lambda p, m="": progress((0.4 if has_narr else 0) + p * (0.6 if has_narr else 1), m),
                            cancel, blocked=self.blocked(), watermark=(self.overlays or {}).get("watermark"),
                            hardsub=(self.overlays or {}).get("hardsub"), episodes=self.episodes)
        step(log, "render", "done", Path(res).name)
        txt = out_path.with_suffix(".txt")
        txt.write_text(script_writer.script_to_text(self.script), encoding="utf-8")
        if not (opts.get("publish_thumbs", True) or opts.get("publish_meta", True)):
            step(log, "publish", "skip", "tắt")
        if opts.get("publish_thumbs", True) or opts.get("publish_meta", True):
            progress(0.995, "Tạo thumbnail & tiêu đề")
            step(log, "publish", "start")
            try:
                self.run_publish(res, log, thumbs=opts.get("publish_thumbs", True),
                                 meta=opts.get("publish_meta", True))
                step(log, "publish", "done")
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Chưa tạo được thumbnail/tiêu đề ({e}) - video vẫn đã xuất xong.", level="warn")
                step(log, "publish", "skip", "lỗi, bỏ qua")
        if opts.get("only_video", True):
            from . import publish

            publish.tidy(res, log)
        return res

    def run_publish(self, out_video, log=_noop_log, progress=_noop_progress, cancel=None, thumbs=True, meta=True) -> dict:
        """Thumbnail + tiêu đề, mô tả, hashtag, mốc chương cho video đã xuất."""
        from . import publish

        res = publish.prepare(self, Path(out_video), log, thumbs=thumbs, meta=meta)
        if self.settings.get("render", "only_video", True):
            publish.tidy(out_video, log)
        return res

    def run_all(self, log=_noop_log, progress=_noop_progress, cancel=None, subtitle_file=None,
                out_path=None) -> Path:
        cancel = cancel or threading.Event()
        sc = self.settings.section("script")
        ai = sc.get("provider") != "none"
        web = sc.get("provider") == "web"  # bản web: bớt số lần copy-dán (bỏ tự nhận diện & AI xem cảnh)
        step(log, "plan", "start", ",".join(STEPS))
        if ai and not web and sc.get("identify", True) and not self.film:
            step(log, "identify", "start")
            try:
                self.run_identify(log, lambda p, m="": progress(p * 0.04, m), cancel)
                step(log, "identify", "done", (self.film or {}).get("title") or "")
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Không nhận diện được phim ({e}) - tiếp tục.", level="warn")
                step(log, "identify", "skip", "lỗi, bỏ qua")
        else:
            step(log, "identify", "skip", "đã có" if self.film else "tắt")
        if not self.transcript:
            step(log, "transcribe", "start")
            self.run_transcribe(log, lambda p, m="": progress(0.04 + p * 0.32, m), cancel, subtitle_file)
            step(log, "transcribe", "done", f"{len(self.transcript)} câu")
            # Nhận diện lại bằng lời thoại nếu lần đầu chưa chắc chắn
            if ai and not web and sc.get("identify", True) and float((self.film or {}).get("confidence") or 0) < 0.6:
                try:
                    self.run_identify(log, lambda p, m="": progress(0.36 + p * 0.02, m), cancel)
                except Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001
                    log(f"Nhận diện lại lỗi ({e}).", level="warn")
        else:
            step(log, "transcribe", "skip", f"đã có {len(self.transcript)} câu")
        if self.settings.get("transcribe", "use_scenes", True) and self.scenes is None:
            step(log, "scenes", "start")
            self.run_scenes(log, lambda p, m="": progress(0.38 + p * 0.1, m), cancel)
            step(log, "scenes", "done", f"{len(self.scenes or [])} cảnh")
        else:
            step(log, "scenes", "skip", "đã có" if self.scenes is not None else "tắt")
        ro = self.settings.section("render")
        if (ro.get("avoid_overlays", True) or ro.get("delogo", True) or ro.get("hardsub_mode", "blur") != "none") and \
                (self.overlays is None or int(self.overlays.get("version", 1)) < 2):
            step(log, "overlays", "start")
            self.run_overlays(log, lambda p, m="": progress(0.47 + p * 0.03, m), cancel)
            step(log, "overlays", "done")
        else:
            step(log, "overlays", "skip", "đã có" if self.overlays is not None else "tắt")
        if ai and not web and sc.get("visual") and not self.visual:
            step(log, "visual", "start")
            try:
                self.run_visual(log, lambda p, m="": progress(0.48 + p * 0.07, m), cancel)
                step(log, "visual", "done")
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"AI xem cảnh lỗi ({e}) - bỏ qua.", level="warn")
                step(log, "visual", "skip", "lỗi, bỏ qua")
        else:
            step(log, "visual", "skip", "đã có" if self.visual else "tắt")
        step(log, "script", "start")
        self.run_script(log, lambda p, m="": progress(0.55 + p * 0.07, m), cancel)
        step(log, "script", "done", f"{len((self.script or {}).get('segments', []))} đoạn")
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
