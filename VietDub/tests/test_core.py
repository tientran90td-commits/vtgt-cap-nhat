"""Kiểm thử toàn bộ quy trình (không cần mạng): video tiếng Anh có phụ đề cứng -> lời gốc -> AI dịch (Ollama giả)
-> thuyết minh (giọng giả) -> xóa phụ đề gốc thông minh + phụ đề Việt -> video."""
from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="vietdub_"))
os.environ["VIETDUB_HOME"] = str(TMP / "home")

from vietdub import dub, hybrid, render, separate, transcript, translate, updater, voices  # noqa: E402
from vietdub.config import Settings  # noqa: E402
from vietdub.media import probe, run  # noqa: E402
from vietdub.project import Project  # noqa: E402

LOG: list = []


def log(m, level="info"):
    LOG.append(str(m))


def prog(p, m=""):
    pass


# ------------------------------------------------------------------ AI giả (đúng API Ollama)
class FakeAI(BaseHTTPRequestHandler):
    calls: dict = {"brief": 0, "translate": 0, "shorten": 0, "info": 0}
    dropped = False

    def log_message(self, *a):
        pass

    def _send(self, content: str):
        b = json.dumps({"message": {"content": content}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        b = json.dumps({"models": [{"name": "qwen2.5:7b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        system, user = body["messages"][0]["content"], body["messages"][1]["content"]
        if system.startswith("You prepare a translation brief"):
            FakeAI.calls["brief"] += 1
            return self._send(json.dumps({"genre": "phiêu lưu", "names": {"Jack": "Jack"},
                                          "pronouns": "Jack và Mary là bạn: xưng tôi - cậu."}))
        if system.startswith("You shorten"):
            FakeAI.calls["shorten"] += 1
            ids = re.findall(r"^(\d+) \|", user, re.M)
            return self._send(json.dumps({"lines": {i: f"Câu {i} ngắn." for i in ids}}, ensure_ascii=False))
        if system.startswith("You write Vietnamese metadata"):
            FakeAI.calls["info"] += 1
            return self._send(json.dumps({"titles": ["Chuyến phiêu lưu của Jack"], "description": "Mô tả.",
                                          "hashtags": ["vietsub", "#thuyetminh"], "tags": ["jack"]},
                                         ensure_ascii=False))
        FakeAI.calls["translate"] += 1
        assert "NAMES/TERMS" in user and "Jack = Jack" in user and "xưng tôi" in user
        ids = re.findall(r"^(\d+) \| [\d.]+s \| max (\d+) chars \|", user, re.M)
        out = {}
        for i, mx in ids:
            if i == "3" and not FakeAI.dropped:  # lần đầu "quên" câu 3 -> app phải tự dịch lại
                FakeAI.dropped = True
                continue
            out[i] = ("Đây là một câu tiếng Việt rất dài dòng dài hơn nhiều so với thời gian nói cho phép " * 3) \
                if i == "5" else f"Câu số {i} đã được dịch sang tiếng Việt."
        return self._send(json.dumps({"lines": out}, ensure_ascii=False))


def start_server(handler) -> str:
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def fake_tts(text, voice, out, speed, settings, log=None):
    wav = out.with_suffix(".raw.wav")
    run(["-f", "lavfi", "-i", f"sine=frequency=520:duration={max(0.6, len(text) / 15):.2f}", "-ac", "1", str(wav)])
    return wav


def make_video(path: Path, seconds: int = 60):
    """Video 'tiếng Anh' có phụ đề tiếng Anh in cứng + file phụ đề gốc .srt cạnh video."""
    lines = []
    for i in range(seconds // 4):
        a, b = i * 4 + 0.5, i * 4 + 3.2
        lines.append((a, b, f"This is English line number {i + 1}, Jack."))
    srt = "".join(f"{k + 1}\n{transcript.fmt(a)},500 --> {transcript.fmt(b)},200\n{t}\n\n"
                  for k, (a, b, t) in enumerate(lines))
    burn = path.with_name("burn.srt")
    burn.write_text(srt, encoding="utf-8")
    run(["-f", "lavfi", "-i", "mandelbrot=s=640x360:r=25", "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
         "-t", str(seconds), "-vf", "subtitles=burn.srt:force_style='Fontsize=22,Outline=2'", "-c:v", "libx264",
         "-preset", "ultrafast", "-c:a", "aac", "-shortest", path.name], cwd=str(path.parent))
    path.with_suffix(".srt").write_text(srt, encoding="utf-8")
    return len(lines)


def check_units():
    segs = [{"start": 0, "end": 1, "text": "字幕由Amara.org社区提供"}, {"start": 1, "end": 1.6, "text": "Hello"},
            {"start": 1.7, "end": 3, "text": "my friend."}, {"start": 3.2, "end": 4, "text": "my friend."},
            {"start": 5, "end": 6, "text": "♪ ♪"}]
    c = transcript.clean_lines(segs)
    assert [x["text"] for x in c] == ["Hello my friend."] and c[0]["end"] == 4, c
    assert translate.max_chars({"start": 0, "end": 2}, {"start": 3, "end": 5}) == int(3 * translate.CPS)
    assert translate._bad("Hello", None) and translate._bad("Hello", "你好") and not translate._bad("Hello", "Xin chào")
    assert not translate._bad("[laughs]", "") and translate._bad("Hello there", "")
    assert translate.parse_glossary("林动 = Lâm Động\nrác") == {"林动": "Lâm Động"}
    assert "00:00:01,000 --> 00:00:02,500\nXin chào" in translate.to_srt([{"start": 1, "end": 2.5, "vi": "Xin chào"}])
    # ghép thuyết minh: câu dài được đọc nhanh hơn, không bao giờ chồng lên nhau
    w = TMP / "dubunit"
    w.mkdir()
    a, b = w / "a.wav", w / "b.wav"
    run(["-f", "lavfi", "-i", "sine=f=400:d=3", "-ac", "1", "-ar", "48000", str(a)])
    run(["-f", "lavfi", "-i", "sine=f=600:d=1", "-ac", "1", "-ar", "48000", str(b)])
    st = dub.build([{"start": 1, "end": 2}, {"start": 3.5, "end": 5}], [a, b], 8, w / "d.wav", max_speed=1.35)
    assert st == {"placed": 2, "sped": 1, "max_late": st["max_late"]} and st["max_late"] < 0.3, st
    assert abs(probe(w / "d.wav").duration - 8) < 0.05
    # tách nhạc nền: STFT / iSTFT của bản gọn khôi phục đúng tín hiệu (giống torch.stft)
    import numpy as np

    m = separate.MDX.__new__(separate.MDX)
    m.n_fft = 6144
    m.win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(m.n_fft) / m.n_fft)).astype(np.float32)
    x = np.random.default_rng(1).standard_normal((2, separate.HOP * 255)).astype(np.float32)
    sp = m._stft(x)
    assert sp.shape == (2, 3073, 256) and np.abs(m._istft(sp, x.shape[1]) - x).max() < 1e-4
    print("✓ lọc câu rác Whisper, giới hạn chữ, kiểm tra bản dịch, ghép thuyết minh khớp thời gian, STFT tách nhạc")


def main():
    check_units()
    s = Settings(TMP / "settings.json")
    s.data["mode"] = "offline"
    s.set("ai", "ollama_url", start_server(FakeAI))
    s.set("paths", "output", str(TMP / "out"))
    s.set("voice", "engine", "piper")
    s.set("video", "background", "duck")
    hybrid.voice_ready = lambda e, _s: e == "piper"
    voices._piper = fake_tts
    video = TMP / "English Video.mp4"
    n = make_video(video)

    p = Project(str(video), s)
    steps = []
    t0 = time.time()
    out = p.run_all(log=log, progress=prog, step=lambda *a: steps.append(a))
    el = time.time() - t0
    assert len(p.source) == n and any("phụ đề" in m and ".srt" in m for m in LOG), LOG[:6]
    assert len(p.lines) == n and all(x["vi"] for x in p.lines), [x["vi"] for x in p.lines]
    assert FakeAI.calls["brief"] == 1 and FakeAI.calls["translate"] >= 2 and FakeAI.dropped  # câu sót -> dịch lại
    assert p.lines[4]["vi"] == "Câu 5 ngắn." and FakeAI.calls["shorten"] == 1             # câu quá dài -> rút gọn
    assert p.lines[2]["vi"] == "Câu số 3 đã được dịch sang tiếng Việt."
    info = probe(out)
    assert abs(info.duration - 60) < 1.0 and info.has_audio and (info.width, info.height) == (640, 360), info
    assert info.subtitles and info.subtitles[0]["codec"] == "mov_text", info.subtitles   # phụ đề Việt bật/tắt được
    assert [x[0] for x in steps] == ["transcript", "transcript", "translate", "translate", "publish", "voice", "voice",
                                    "render", "render", "publish"], steps
    assert steps[-1][1] == "done" and p.publish_info["titles"][0] == "Chuyến phiêu lưu của Jack"
    assert sorted(f.name for f in (TMP / "out").iterdir()) == [out.name]  # chỉ có video thành phẩm
    assert out.name == "Chuyến phiêu lưu của Jack.mp4"
    an = p.analysis()
    assert an.get("band") and an["band"][0] > 0.75 and an.get("boxes"), an  # dò được phụ đề gốc + lúc xuất hiện
    # phụ đề gốc đã bị xóa: dải phụ đề ở video ra khác hẳn bản gốc, phần trên giữ nguyên
    import numpy as np

    from vietdub.media import frames

    o = frames(str(out), 9.0, None, 320, 180, count=1)[0].astype(int)
    g = frames(str(video), 9.0, None, 320, 180, count=1)[0].astype(int)
    y0 = int(an["band"][0] * 180)
    assert np.abs(o[:y0 - 10] - g[:y0 - 10]).mean() < 6
    print(f"✓ A→Z ({el:.0f}s): {n} câu → dịch (bảng tên, dịch lại câu sót, rút gọn câu dài) → thuyết minh + "
          "phụ đề Việt + xóa phụ đề gốc thông minh + ảnh bìa & tiêu đề")

    # chỉ thuyết minh, không che, giữ hình gốc -> chép thẳng hình (rất nhanh)
    s.set("video", "output", "dub")
    s.set("video", "cover", "none")
    t0 = time.time()
    o2 = p.run_render(TMP / "out" / "dub_only.mp4", log=log, progress=prog)
    assert time.time() - t0 < 15 and any("giữ nguyên hình gốc" in m for m in LOG)
    assert abs(probe(o2).duration - 60) < 1.0
    # chỉ phụ đề: giữ tiếng gốc, không đọc giọng
    s.set("video", "output", "sub")
    steps.clear()
    o3 = p.run_render(TMP / "out" / "sub_only.mp4", log=log, progress=prog, step=lambda *a: steps.append(a))
    assert ("voice", "skip", "chỉ phụ đề") in steps and probe(o3).has_audio
    # thuyết minh trên nhạc nền đã tách giọng (giả lập bộ tách nhạc: không tải model trong kiểm thử)
    s.set("video", "output", "both")
    s.set("video", "background", "separate")
    fake_bg = TMP / "bg.flac"
    run(["-f", "lavfi", "-i", "sine=f=440:d=60", "-ac", "2", "-ar", "44100", str(fake_bg)])
    separate.available = lambda: True
    separate.background = lambda *a, **k: fake_bg
    p._an.pop("bg", None)
    o5 = p.run_render(TMP / "out" / "bg.mp4", log=log, progress=prog)
    assert any("nhạc nền đã tách giọng" in m for m in LOG) and abs(probe(o5).duration - 60) < 1.0
    # tách nhạc lỗi -> tự dùng tiếng gốc nhỏ, vẫn xuất được
    def boom(*a, **k):
        raise separate.SeparateError("hỏng")
    separate.background = boom
    p._an.pop("bg", None)
    o6 = p.run_render(TMP / "out" / "bg2.mp4", log=log, progress=prog)
    assert any("Tách nhạc nền lỗi" in m for m in LOG) and o6.exists()
    s.set("video", "background", "duck")
    # khung dọc
    s.set("video", "aspect", "9:16")
    s.set("video", "height", 360)
    o4 = p.run_render(TMP / "out" / "doc.mp4", log=log, progress=prog)
    assert (probe(o4).width, probe(o4).height) == (360, 640)
    # xem thử 20 giây
    s.set("video", "aspect", "source")
    pv = p.preview(10.0, 20.0, log, prog)
    assert 19 < probe(pv).duration < 21
    print("✓ chỉ thuyết minh (chép thẳng hình), chỉ phụ đề, nhạc nền tách giọng (+ tự xử lý khi lỗi), khung dọc 9:16, "
          "xem thử 20 giây")

    # cập nhật trực tiếp: chép bản mới, sao lưu bản cũ, không đụng .venv / app khác
    app = TMP / "app"
    (app / "vietdub").mkdir(parents=True)
    (app / ".venv").mkdir()
    (app / "main.py").write_text("old", encoding="utf-8")
    (app / "vietdub" / "old.py").write_text("x", encoding="utf-8")
    (app / ".venv" / "k.txt").write_text("k", encoding="utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("r-b/VietDub/", "")
        z.writestr("r-b/VietDub/main.py", "new")
        z.writestr("r-b/VietDub/vietdub/__init__.py", 'VERSION = "9.9.9"')
        z.writestr("r-b/VietDub/.venv/k.txt", "BAD")
        z.writestr("r-b/RecapStudio/main.py", "other app")
    assert updater.apply_zip(buf.getvalue(), app, "9.9.9", log) == 3
    assert (app / "main.py").read_text() == "new" and (app / ".venv" / "k.txt").read_text() == "k"
    assert not (app / "vietdub" / "old.py").exists() and (app / "_backup").exists()
    print("✓ cập nhật trực tiếp")
    assert render.OUTPUTS and "auto" in render.COVERS
    print("OK", TMP)


if __name__ == "__main__":
    main()
