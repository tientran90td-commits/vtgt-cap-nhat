"""Một dự án = một video. Lưu lời gốc, bản dịch, giọng đọc để sửa & xuất lại rất nhanh."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

from . import dub, hardsub, hybrid, ocr, publish, render, separate, transcript, translate, voices
from .config import Settings, app_home
from .media import Cancelled, probe

STEPS = {"transcript": "🎧 Lời gốc", "translate": "🌐 Dịch tiếng Việt", "voice": "🎙️ Thuyết minh",
         "render": "🎬 Xuất video", "publish": "📤 Ảnh bìa & tiêu đề"}


def _noop(*_a, **_k):
    pass


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\n\r\t]+', " ", s or "").strip()
    return s[:80] or "video"


class Project:
    def __init__(self, video: str, settings: Settings):
        self.video = str(Path(video).resolve())
        self.settings = settings
        self.info = probe(self.video)
        h = hashlib.sha1(self.video.lower().encode()).hexdigest()[:8]
        self.dir = app_home() / "projects" / f"{safe_name(Path(video).stem)[:40]}_{h}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.source: list[dict] = self._load("source.json", [])          # lời gốc
        self.lines: list[dict] = self._load("lines.json", [])            # lời gốc + bản dịch (vi)
        self.brief: dict | None = self._load("brief.json", None)         # tên riêng, xưng hô
        self.publish_info: dict | None = self._load("publish/info.json", None)
        r = self._load("region.json", None)                              # khung phụ đề cứng người dùng chọn
        self.region: tuple | None = tuple(r) if r else None
        self.subtitle_file = ""
        self.voice_engine_used = ""
        self._an: dict = {}
        self._an_thread: threading.Thread | None = None
        self._an_ready: threading.Event | None = None

    @property
    def title(self) -> str:
        return Path(self.video).stem

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
        f = self.dir / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def save_lines(self, lines: list[dict]) -> None:
        self.lines = lines
        self._save("lines.json", lines)

    # ------------------------------------------------ phân tích hình (chạy nền ngay khi mở video)
    def start_analysis(self, log=_noop, cancel=None) -> None:
        if self._an_thread is not None or self._an:
            return
        ready = self._an_ready = threading.Event()

        def job():
            try:
                if self._wants_bg():
                    self._an["bg"] = self._separate(log, cancel)
            except Cancelled:
                pass
            except Exception as e:  # noqa: BLE001
                log(f"Tách nhạc nền lỗi ({e}) - dùng tiếng gốc nhỏ thay thế.", "warn")
                self._an["bg"] = None
            try:
                if self.settings.get("video", "cover") in ("auto", "smart"):
                    if self.region:
                        self._cover_from_region(cancel, log)
                    else:
                        band = hardsub.detect(self.video, self.info, self.dir, cancel, log)
                        self._an["band"] = band
                        if band:
                            self._an["boxes"] = hardsub.timeline(self.video, self.info, band, self.dir, cancel, log)
            except Cancelled:
                pass
            except Exception as e:  # noqa: BLE001
                log(f"Dò phụ đề gốc lỗi ({e}) - bỏ qua.", "warn")
            finally:
                ready.set()
                self._an_thread = None
        self._an_thread = threading.Thread(target=job, daemon=True)
        self._an_thread.start()

    def set_region(self, region: tuple | None) -> None:
        """Khung phụ đề cứng (x0, y0, x1, y1 theo tỉ lệ) người dùng kéo: dùng để quét chữ & xóa đúng chỗ."""
        self.region = tuple(round(float(v), 4) for v in region) if region else None
        self._save("region.json", list(self.region) if self.region else None)
        for k in ("band", "boxes"):
            self._an.pop(k, None)

    def _cover_from_region(self, cancel=None, log=_noop) -> None:
        x0, y0, x1, y1 = self.region
        band = (y0, y1)
        boxes = hardsub.timeline(self.video, self.info, band, self.dir, cancel, log)
        self._an["band"] = band
        self._an["boxes"] = [(a, b, max(x0, bx0), min(x1, bx1)) for a, b, bx0, bx1 in boxes
                             if min(x1, bx1) > max(x0, bx0)]

    def auto_region(self, cancel=None) -> tuple | None:
        """Gợi ý khung phụ đề: dải tự dò + bề rộng chữ lớn nhất."""
        band = hardsub.detect(self.video, self.info, self.dir, cancel)
        if not band:
            return None
        boxes = hardsub.timeline(self.video, self.info, band, self.dir, cancel)
        if boxes:
            x0 = max(0.0, min(b[2] for b in boxes) - 0.02)
            x1 = min(1.0, max(b[3] for b in boxes) + 0.02)
        else:
            x0, x1 = 0.05, 0.95
        return (round(x0, 4), round(max(0.0, band[0] - 0.01), 4), round(x1, 4), round(min(1.0, band[1] + 0.01), 4))

    def _wants_bg(self) -> bool:
        return self._wants_dub() and self.settings.get("video", "background") == "separate" and separate.available()

    def _separate(self, log=_noop, cancel=None, progress=None) -> Path:
        last = [0]

        def prog(p, m=""):
            if progress:
                progress(p, m)
            elif int(p * 5) > last[0]:  # chạy nền: báo mỗi 20%
                last[0] = int(p * 5)
                log(f"Tách nhạc nền {int(p * 100)}%...")
        return separate.background(self.video, self.info, self.dir, self.settings, log, prog, cancel)

    def analysis(self, log=_noop, cancel=None, progress=None) -> dict:
        need_cover = self.settings.get("video", "cover") in ("auto", "smart")
        if not need_cover and not self._wants_bg():
            return {}
        self.start_analysis(log, cancel)
        while self._an_ready is not None and not self._an_ready.wait(0.3):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
        if self._wants_bg() and "bg" not in self._an:  # bật tách nhạc sau khi đã phân tích
            try:
                self._an["bg"] = self._separate(log, cancel, progress)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                log(f"Tách nhạc nền lỗi ({e}) - dùng tiếng gốc nhỏ thay thế.", "warn")
                self._an["bg"] = None
        if need_cover and "band" not in self._an and self.region:
            self._cover_from_region(cancel, log)
        if need_cover and "band" not in self._an:
            self._an["band"] = hardsub.detect(self.video, self.info, self.dir, cancel, log)
            if self._an["band"]:
                self._an["boxes"] = hardsub.timeline(self.video, self.info, self._an["band"], self.dir, cancel, log)
        return self._an

    # ------------------------------------------------ các bước
    def run_ocr(self, log=_noop, progress=_noop, cancel=None) -> tuple[list[dict], str]:
        region = self.region or self.auto_region(cancel)
        if not region:
            raise RuntimeError("Không thấy phụ đề cứng - bấm '🔲 Khung phụ đề cứng' để kéo khung đúng chỗ có chữ.")
        lang = self.settings.get("speech", "ocr_lang", "auto")
        segs = ocr.scan(self.video, self.info, region, self.dir, lang, log, progress, cancel)
        return segs, f"đọc phụ đề cứng (OCR {ocr.LANGS.get(lang, ocr.LANGS['auto'])[0]})"

    def run_transcript(self, log=_noop, progress=_noop, cancel=None) -> list[dict]:
        if self.settings.get("speech", "engine") == "ocr" and not self.subtitle_file:
            segs, src = self.run_ocr(log, progress, cancel)
        else:
            segs, src = transcript.transcribe(self.video, self.dir, self.settings, log, progress, cancel,
                                              subtitle_file=self.subtitle_file)
        segs = transcript.clean_lines(segs)
        if not segs:
            raise RuntimeError("Không nghe được lời thoại nào trong video.")
        self.source = segs
        self._save("source.json", segs)
        self.save_lines([])
        log(f"Lời gốc: {len(segs)} câu (nguồn: {src}).")
        return segs

    def run_translate(self, log=_noop, progress=_noop, cancel=None) -> list[dict]:
        if not self.source:
            raise RuntimeError("Chưa có lời gốc.")
        # lập lại bảng tên mỗi lần dịch: bảng cũ có thể do AI yếu làm sai, dùng lại sẽ sai mãi
        progress(0.02, "AI đọc lướt: nhận ra phim, tên riêng, xưng hô")
        lines = translate.translate(self.source, self.settings, log, lambda p, m="": progress(0.05 + p * 0.95, m),
                                    cancel, title=self.title, brief=None, on_brief=self._set_brief)
        self.save_lines(lines)
        return lines

    def _set_brief(self, brief: dict) -> None:
        self.brief = brief
        self._save("brief.json", brief)

    def voice_files(self, lines: list[dict], log=_noop, progress=_noop, cancel=None) -> list:
        """Đọc giọng cho từng câu. Giọng đã chọn không dùng được -> giọng dự phòng (máy <-> online),
        đọc lại TOÀN BỘ bằng giọng đó cho đồng đều."""
        v = self.settings.section("voice")
        want = v.get("engine") or "edge"
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
            for ln in lines:
                text = (ln.get("vi") or "").strip()
                if not text:
                    files.append(None)
                    continue
                key = hashlib.sha1(json.dumps([engine, voice, v.get("speed"), v.get("volume"), text],
                                              ensure_ascii=False).encode()).hexdigest()[:12]
                f = vdir / f"{key}.wav"
                files.append(f)
                items.append((text, f))
            items = list(dict.fromkeys(items))
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

    def default_output(self) -> Path:
        title = ((self.publish_info or {}).get("titles") or [None])[0] or self.title
        base = self.settings.output_dir() / f"{safe_name(title)}.mp4"
        out, n = base, 1
        while out.exists():
            n += 1
            out = base.with_name(f"{base.stem} ({n}).mp4")
        return out

    def _wants_dub(self) -> bool:
        return self.settings.get("video", "output", "both") in ("both", "dub")

    def run_render(self, out: Path | None = None, log=_noop, progress=_noop, cancel=None, step=_noop) -> Path:
        if not self.lines:
            raise RuntimeError("Chưa có bản dịch.")
        cancel = cancel or threading.Event()
        opts = self.settings.section("video")
        self.start_analysis(log, cancel)
        pub, pub_th = {}, None
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
        track = None
        if self._wants_dub():
            step("voice", "start")
            files = self.voice_files(self.lines, log, lambda p, m="": progress(p * 0.4, m), cancel)
            track = self.dir / "dub.wav"
            st = dub.build(self.lines, files, self.info.duration, track,
                           float(self.settings.get("voice", "max_speed", 1.35)), cancel=cancel, log=log)
            step("voice", "done", f"{st['placed']} câu · {self.voice_engine_used}")
        else:
            step("voice", "skip", "chỉ phụ đề")
        step("render", "start")
        an = self.analysis(log, cancel, lambda p, m="": progress(0.4 + p * 0.2, m))
        if pub_th is not None and out is None:  # đợi tiêu đề tiếng Việt để đặt tên file
            pub_th.join(90)
        res = render.render_video(self.video, self.info, self.lines, track, opts,
                                  Path(out) if out else self.default_output(), self.dir / "render", log,
                                  lambda p, m="": progress(0.6 + p * 0.4, m), cancel, band=an.get("band"),
                                  boxes=an.get("boxes"), bg_audio=an.get("bg"))
        step("render", "done", res.name)
        if pub_th is not None:
            pub_th.join(300)
            if pub.get("err") or pub_th.is_alive():
                step("publish", "fail", pub.get("err") or "quá lâu")
            else:
                step("publish", "done", "")
                self._export_publish(res)
        log(f"✅ Đã xuất video: {res}")
        return res

    def preview(self, t0: float, seconds: float = 20.0, log=_noop, progress=_noop, cancel=None) -> Path:
        """Dựng thử ~20 giây quanh câu đang chọn (giọng + phụ đề + che phụ đề gốc như bản thật)."""
        t0 = max(0.0, t0 - 0.5)
        seconds = min(seconds, max(1.0, self.info.duration - t0))
        part = [x for x in self.lines if x["end"] > t0 and x["start"] < t0 + seconds]
        track = None
        if self._wants_dub():
            files = self.voice_files(part, log, lambda p, m="": progress(p * 0.5, m), cancel)
            track = self.dir / "preview" / "dub.wav"
            dub.build(part, files, seconds, track, float(self.settings.get("voice", "max_speed", 1.35)),
                      offset=t0, cancel=cancel)
        an = self.analysis(log, cancel)
        out = self.dir / "preview" / f"xem_thu_{int(t0)}.mp4"
        return render.render_video(self.video, self.info, part, track, self.settings.section("video"), out,
                                   self.dir / "preview", log, lambda p, m="": progress(0.5 + p * 0.5, m), cancel,
                                   band=an.get("band"), boxes=an.get("boxes"), start=t0, length=seconds,
                                   bg_audio=an.get("bg"))

    # ------------------------------------------------ dựng tiếp trong OpenCut
    def opencut_package(self, log=_noop, progress=_noop, cancel=None) -> dict:
        """Chuẩn bị cho OpenCut: video đã xóa phụ đề gốc (tiếng nền), giọng thuyết minh, phụ đề Việt (chữ sửa được).
        Trả về {files: {...}, manifest: {...}} để máy chủ OpenCut phục vụ."""
        import uuid

        opts = self.settings.section("video")
        out_dir = self.dir / "opencut"
        out_dir.mkdir(exist_ok=True)
        an = self.analysis(log, cancel, lambda p, m="": progress(0.05 + p * 0.25, m))
        has_vi = any((x.get("vi") or "").strip() for x in self.lines)
        files, items = {}, []
        bg = an.get("bg") if opts.get("background") == "separate" else None
        clean = render.clean_video(self.video, self.info, opts, out_dir / "video_sach.mp4", out_dir / "work", log,
                                   lambda p, m="": progress(0.3 + p * 0.4, m), cancel, band=an.get("band"),
                                   boxes=an.get("boxes"), audio=bg)
        files["video"] = clean
        items.append({"name": f"{self.title} (đã xóa phụ đề gốc).mp4", "url": "/vietdub/files/video", "kind": "video"})
        if has_vi and self._wants_dub():
            vfiles = self.voice_files(self.lines, log, lambda p, m="": progress(0.7 + p * 0.25, m), cancel)
            track = out_dir / "thuyet_minh.wav"
            dub.build(self.lines, vfiles, self.info.duration, track,
                      float(self.settings.get("voice", "max_speed", 1.35)), cancel=cancel, log=log)
            files["dub"] = track
            items.append({"name": "Thuyết minh tiếng Việt.wav", "url": "/vietdub/files/dub", "kind": "audio"})
        if has_vi:
            srt = out_dir / "phu_de_viet.srt"
            srt.write_text(translate.to_srt(self.lines), encoding="utf-8")
            files["srt"] = srt
            items.append({"name": "Phụ đề Việt.srt", "url": "/vietdub/files/srt", "kind": "subtitle"})
        ci = probe(clean)
        title = ((self.publish_info or {}).get("titles") or [None])[0] or f"{self.title} (Việt hóa)"
        manifest = {"job": uuid.uuid4().hex[:12], "title": title[:80], "width": ci.width, "height": ci.height,
                    "items": items}
        progress(1.0, "Đã chuẩn bị cho OpenCut")
        return {"files": files, "manifest": manifest}

    # ------------------------------------------------ ảnh bìa, tiêu đề, hashtag
    def run_publish(self, log=_noop, cancel=None) -> dict:
        opts = self.settings.section("publish")
        sc = {"title": self.title,
              "segments": [{"start": x["start"], "end": x["end"], "narration": x.get("vi", "")} for x in self.lines]}
        res: dict = {}
        if opts.get("info", True):
            info = publish.make_info(sc, self.title, self.settings, log, cancel)
            publish.save_json(self.dir / "publish" / "info.json", info)
            self.publish_info = info
            res["info"] = info
        if opts.get("thumbnail", True):
            try:
                t = (self.publish_info or {}).get("titles", [self.title])[0] or self.title
                res["thumbnail"] = publish.make_thumbnail(self.video, self.info, sc["segments"], t, self.thumbnail,
                                                          self.settings.get("video", "aspect", "source")
                                                          if self.settings.get("video", "aspect") != "source"
                                                          else ("9:16" if self.info.height > self.info.width else
                                                                "16:9"), cancel)
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

    def run_all(self, out: Path | None = None, log=_noop, progress=_noop, cancel=None, step=_noop) -> Path:
        cancel = cancel or threading.Event()
        self.start_analysis(log, cancel)  # dò phụ đề gốc song song với các bước dưới
        if self.source:
            step("transcript", "skip", f"đã có {len(self.source)} câu")
        else:
            step("transcript", "start")
            self.run_transcript(log, lambda p, m="": progress(p * 0.3, m), cancel)
            step("transcript", "done", f"{len(self.source)} câu")
        if cancel.is_set():
            raise Cancelled()
        if self.lines and len(self.lines) == len(self.source):
            step("translate", "skip", "đã dịch")
        else:
            step("translate", "start")
            self.run_translate(log, lambda p, m="": progress(0.3 + p * 0.2, m), cancel)
            step("translate", "done", f"{len(self.lines)} câu")
        return self.run_render(out, log, lambda p, m="": progress(0.5 + p * 0.5, m), cancel, step)
