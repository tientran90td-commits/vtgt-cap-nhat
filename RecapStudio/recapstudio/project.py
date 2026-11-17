"""Một dự án = một bộ phim. Lưu lời thoại, kịch bản, giọng, các đoạn đã dựng để làm lại rất nhanh."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from . import hardsub, hybrid, publish, render, scenes, transcript, voices, writer
from .config import Settings, app_home
from .media import Cancelled, probe

STEPS = {"transcript": "🎧 Lời thoại", "script": "✍️ Kịch bản AI", "voice": "🎙️ Giọng đọc", "render": "🎬 Dựng video",
         "publish": "📤 Ảnh bìa & tiêu đề"}


def _noop(*_a, **_k):
    pass


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\n\r\t]+', " ", s or "").strip()
    return s[:80] or "recap"


class Project:
    def __init__(self, video: str, settings: Settings):
        self.video = str(Path(video).resolve())
        self.settings = settings
        self.info = probe(self.video)
        h = hashlib.sha1(self.video.lower().encode()).hexdigest()[:8]
        self.dir = app_home() / "projects" / f"{safe_name(Path(video).stem)[:40]}_{h}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.transcript: list[dict] = self._load("transcript.json", [])
        self.script: dict | None = self._load("script.json", None)
        self.subtitle_file = ""
        self.voice_engine_used = ""
        self.publish_info: dict | None = self._load("publish/info.json", None)
        self._analysis: dict = {}
        self._an_thread: threading.Thread | None = None

    @property
    def thumbnail(self) -> Path:
        return self.dir / "publish" / "thumbnail.jpg"

    def _load(self, name, default):
        f = self.dir / name
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                pass
        return default

    def _save(self, name, data):
        (self.dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def save_script(self, script: dict) -> None:
        self.script = script
        self._save("script.json", script)

    # ------------------------------------------------ các bước
    def run_transcript(self, log=_noop, progress=_noop, cancel=None) -> list[dict]:
        segs, src = transcript.transcribe(self.video, self.dir, self.settings, log, progress, cancel,
                                          subtitle_file=self.subtitle_file, prompt=Path(self.video).stem)
        if not segs:
            raise RuntimeError("Không lấy được lời thoại nào từ phim.")
        self.transcript = segs
        self._save("transcript.json", segs)
        log(f"Lời thoại: {len(segs)} câu (nguồn: {src}).")
        return segs

    def run_script(self, log=_noop, progress=_noop, cancel=None) -> dict:
        sc = writer.write(self.transcript, self.info.duration, self.settings, log, progress, cancel)
        self.save_script(sc)
        return sc

    def voice_files(self, log=_noop, progress=_noop, cancel=None) -> list:
        """Đọc giọng cho từng đoạn. Giọng đã chọn lỗi / không dùng được -> tự chuyển giọng dự phòng
        (trên máy <-> online) và đọc lại TOÀN BỘ bằng giọng đó cho đồng đều."""
        v = self.settings.section("voice")
        want = v.get("engine") or "vieneu"
        chain = hybrid.voice_chain(self.settings, want)
        if chain[0] != want:
            log(f"Giọng {voices.ENGINES.get(want, {}).get('name', want)} chưa dùng được lúc này → dùng "
                f"{voices.ENGINES[chain[0]]['name']}.", "warn")
        vdir = self.dir / "voices"
        vdir.mkdir(exist_ok=True)
        last: Exception | None = None
        for k, engine in enumerate(chain):
            voice = (v.get("voice") if engine == want else "") or voices.default_voice(engine)
            files, items = [], []
            for i, seg in enumerate(self.script["segments"]):
                if not seg.get("narration"):
                    files.append(None)
                    continue
                key = hashlib.sha1(json.dumps([engine, voice, v.get("speed"), v.get("volume"), seg["narration"]],
                                              ensure_ascii=False).encode()).hexdigest()[:10]
                f = vdir / f"v{i:03d}_{key}.wav"
                files.append(f)
                items.append((seg["narration"], f))
            try:
                voices.synth_many(engine, items, voice, self.settings, log, progress, cancel)
                self.voice_engine_used = engine
                return files
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                last = e
                if k + 1 < len(chain):
                    log(f"Giọng {voices.ENGINES[engine]['name']} lỗi ({e}) → chuyển sang "
                        f"{voices.ENGINES[chain[k + 1]]['name']}.", "warn")
        raise RuntimeError(f"Không đọc được giọng thuyết minh: {last}")

    # ------------------------------------------------ phân tích phim (chạy nền, song song với AI viết kịch bản)
    def start_analysis(self, log=_noop, cancel=None) -> None:
        if self._an_thread is not None:
            return
        opts = self.settings.section("video")
        ready = self._an_ready = threading.Event()

        def job():
            try:
                if opts.get("snap_scenes", True):
                    self._analysis["cuts"] = scenes.detect(self.video, self.dir, cancel, log)
                if opts.get("cover") == "auto":
                    self._analysis["band"] = hardsub.detect(self.video, self.info, self.dir, cancel, log)
            except Cancelled:
                return
            except Exception as e:  # noqa: BLE001
                log(f"Phân tích phim lỗi ({e}) - bỏ qua.", "warn")
            finally:
                ready.set()
            try:  # dò chuyển cảnh chi tiết, chạy nền ưu tiên thấp; xong trước lúc dựng thì dùng
                if opts.get("snap_scenes", True):
                    self._analysis["cuts"] = scenes.detect(self.video, self.dir, cancel, None, full=True)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._an_thread = None
        self._an_thread = threading.Thread(target=job, daemon=True)
        self._an_thread.start()

    def analysis(self, log=_noop, cancel=None) -> dict:
        """Đợi phần phân tích nhanh (khung khóa + phụ đề cứng); phần chi tiết vẫn chạy nền."""
        if self._an_thread is None and not self._analysis:
            self.start_analysis(log, cancel)
        ev = getattr(self, "_an_ready", None)
        while ev is not None and not ev.wait(0.3):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
        opts = self.settings.section("video")
        if opts.get("cover") == "auto" and "band" not in self._analysis:  # bật Tự dò sau khi đã phân tích
            self._analysis["band"] = hardsub.detect(self.video, self.info, self.dir, cancel, log)
        if opts.get("snap_scenes", True) and "cuts" not in self._analysis:
            self._analysis["cuts"] = scenes.detect(self.video, self.dir, cancel, log)
        return self._analysis

    # ------------------------------------------------ ảnh bìa, tiêu đề, hashtag
    def run_publish(self, log=_noop, cancel=None) -> dict:
        opts = self.settings.section("publish")
        film = Path(self.video).stem
        sc = self.script or {"title": film, "segments": []}
        res: dict = {}
        if opts.get("info", True):
            info = publish.make_info(sc, film, self.settings, log, cancel)
            publish.save_json(self.dir / "publish" / "info.json", info)
            self.publish_info = info
            res["info"] = info
        if opts.get("thumbnail", True):
            try:
                title = (self.publish_info or {}).get("titles", [sc.get("title")])[0] or sc.get("title") or film
                res["thumbnail"] = publish.make_thumbnail(
                    self.video, self.info, sc.get("segments", []), title, self.thumbnail,
                    self.settings.get("video", "aspect", "16:9"), cancel)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Tạo ảnh bìa lỗi ({e}).", "warn")
        return res

    def _export_publish(self, out: Path) -> None:
        if not self.settings.get("publish", "save_next_to_video", False):
            return
        import shutil

        if self.thumbnail.exists():
            shutil.copy2(self.thumbnail, out.with_suffix(".jpg"))
        if self.publish_info:
            out.with_suffix(".txt").write_text(publish.text_block(self.publish_info), encoding="utf-8")

    def default_output(self) -> Path:
        title = (self.script or {}).get("title") or Path(self.video).stem
        base = self.settings.output_dir() / f"{safe_name(title)}.mp4"
        out, n = base, 1
        while out.exists():
            n += 1
            out = base.with_name(f"{base.stem} ({n}).mp4")
        return out

    def _segments_for_render(self, log, cancel) -> tuple[list[dict], tuple | None]:
        an = self.analysis(log, cancel)
        segs = self.script["segments"]
        if an.get("cuts") and self.settings.get("video", "snap_scenes", True):
            segs = scenes.snap_segments(segs, an["cuts"])
        return segs, an.get("band")

    def run_render(self, out: Path | None = None, log=_noop, progress=_noop, cancel=None, step=_noop) -> Path:
        if not self.script or not self.script.get("segments"):
            raise RuntimeError("Chưa có kịch bản.")
        cancel = cancel or threading.Event()
        self.start_analysis(log, cancel)
        pub: dict = {}
        pub_th = None
        if self.settings.get("publish", "thumbnail", True) or self.settings.get("publish", "info", True):
            step("publish", "start")

            def pjob():
                try:
                    pub["res"] = self.run_publish(log, cancel)
                except Cancelled:
                    pub["err"] = "đã hủy"
                except Exception as e:  # noqa: BLE001
                    pub["err"] = str(e)
                    log(f"Ảnh bìa / tiêu đề lỗi: {e}", "warn")
            pub_th = threading.Thread(target=pjob, daemon=True)
            pub_th.start()
        else:
            step("publish", "skip", "đã tắt")
        step("voice", "start")
        vf = self.voice_files(log, lambda p, m="": progress(p * 0.35, m), cancel)
        step("voice", "done", f"{sum(1 for f in vf if f)} đoạn · {self.voice_engine_used}")
        step("render", "start")
        segs, band = self._segments_for_render(log, cancel)
        res = render.render(segs, vf, self.video, self.info, self.settings.section("video"),
                            Path(out) if out else self.default_output(), self.dir, log,
                            lambda p, m="": progress(0.35 + p * 0.65, m), cancel, band=band)
        step("render", "done", res.name)
        if pub_th is not None:
            t0 = time.time()
            while pub_th.is_alive() and time.time() - t0 < 600:
                progress(0.995, "Đợi tạo ảnh bìa & tiêu đề")
                pub_th.join(0.5)
                if cancel.is_set():
                    raise Cancelled()
            if pub_th.is_alive():
                step("publish", "fail", "quá lâu")
            elif pub.get("err"):
                step("publish", "fail", pub["err"])
            else:
                step("publish", "done", "")
                self._export_publish(res)
        return res

    def preview_segment(self, index: int, log=_noop, progress=_noop, cancel=None) -> Path:
        """Dựng thử 1 đoạn (giọng + phụ đề + khung hình như bản thật) để xem trước."""
        seg = self.script["segments"][index]
        sub = {"title": "", "segments": [seg]}
        full = self.script
        self.script = sub
        try:
            vf = self.voice_files(log, lambda p, m="": progress(p * 0.4, m), cancel)
        finally:
            self.script = full
        segs, band = self._segments_for_render(log, cancel)
        out = self.dir / "preview" / f"doan_{index + 1}.mp4"
        work = self.dir / "preview"
        return render.render([segs[index]], vf, self.video, self.info, self.settings.section("video"), out, work,
                             log, lambda p, m="": progress(0.4 + p * 0.6, m), cancel, band=band)

    def run_all(self, out: Path | None = None, log=_noop, progress=_noop, cancel=None, step=_noop) -> Path:
        cancel = cancel or threading.Event()
        self.start_analysis(log, cancel)  # dò chuyển cảnh + phụ đề cứng song song với các bước dưới
        if self.transcript:
            step("transcript", "skip", f"đã có {len(self.transcript)} câu")
        else:
            step("transcript", "start")
            self.run_transcript(log, lambda p, m="": progress(p * 0.3, m), cancel)
            step("transcript", "done", f"{len(self.transcript)} câu")
        if cancel.is_set():
            raise Cancelled()
        step("script", "start")
        self.run_script(log, lambda p, m="": progress(0.3 + p * 0.2, m), cancel)
        step("script", "done", f"{len(self.script['segments'])} đoạn")
        return self.run_render(out, log, lambda p, m="": progress(0.5 + p * 0.5, m), cancel, step)
