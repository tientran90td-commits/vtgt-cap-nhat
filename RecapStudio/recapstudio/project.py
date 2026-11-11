"""Một dự án = một bộ phim. Lưu lời thoại, kịch bản, giọng, các đoạn đã dựng để làm lại rất nhanh."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

from . import render, transcript, voices, writer
from .config import Settings, app_home
from .media import Cancelled, probe

STEPS = {"transcript": "🎧 Lời thoại", "script": "✍️ Kịch bản AI", "voice": "🎙️ Giọng đọc", "render": "🎬 Dựng video"}


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
        v = self.settings.section("voice")
        engine, voice = v.get("engine", "edge"), v.get("voice") or voices.default_voice(v.get("engine", "edge"))
        vdir = self.dir / "voices"
        vdir.mkdir(exist_ok=True)
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
        voices.synth_many(engine, items, voice, self.settings, log, progress, cancel)
        return files

    def default_output(self) -> Path:
        title = (self.script or {}).get("title") or Path(self.video).stem
        base = self.settings.output_dir() / f"{safe_name(title)}.mp4"
        out, n = base, 1
        while out.exists():
            n += 1
            out = base.with_name(f"{base.stem} ({n}).mp4")
        return out

    def run_render(self, out: Path | None = None, log=_noop, progress=_noop, cancel=None, step=_noop) -> Path:
        if not self.script or not self.script.get("segments"):
            raise RuntimeError("Chưa có kịch bản.")
        step("voice", "start")
        vf = self.voice_files(log, lambda p, m="": progress(p * 0.35, m), cancel)
        step("voice", "done", f"{sum(1 for f in vf if f)} đoạn")
        step("render", "start")
        res = render.render(self.script["segments"], vf, self.video, self.info, self.settings.section("video"),
                            Path(out) if out else self.default_output(), self.dir, log,
                            lambda p, m="": progress(0.35 + p * 0.65, m), cancel)
        step("render", "done", res.name)
        return res

    def run_all(self, out: Path | None = None, log=_noop, progress=_noop, cancel=None, step=_noop) -> Path:
        cancel = cancel or threading.Event()
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
