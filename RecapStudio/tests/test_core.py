"""Kiểm thử offline toàn bộ quy trình: phim giả + phụ đề -> AI (Ollama giả lập) -> giọng giả -> video."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="recapstudio_"))
os.environ["RECAPSTUDIO_HOME"] = str(TMP / "home")

from recapstudio import ai, render, transcript, voices, writer  # noqa: E402
from recapstudio.config import Settings  # noqa: E402
from recapstudio.media import Cancelled, probe, run  # noqa: E402
from recapstudio.project import Project  # noqa: E402

LOG = []


def log(m, level="info"):
    LOG.append(m)


def prog(p, m=""):
    pass


# ------------------------------------------------------------------ Ollama giả lập (đúng API /api/tags, /api/chat)
class FakeOllama(BaseHTTPRequestHandler):
    calls: list = []
    reply_words = [8, 45]   # lần 1 viết ngắn (để kiểm tra app tự yêu cầu viết dài thêm), lần 2 đủ dài

    def log_message(self, *a):
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": "qwen2.5:7b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.calls.append(body)
        n = FakeOllama.reply_words[min(len(FakeOllama.calls) - 1, 1)]
        segs = [{"start": f"00:{m:02d}:05", "end": f"00:{m:02d}:15",
                 "narration": " ".join(["Nhân vật chính bước tiếp trên hành trình"] * (n // 7 + 1))}
                for m in range(0, 3 if n < 20 else 10)]
        self._send({"message": {"content": json.dumps({"title": "Hành trình thử nghiệm", "segments": segs},
                                                      ensure_ascii=False)}})


def start_fake_ollama() -> str:
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def make_movie(path: Path, seconds: int = 660):
    run(["-f", "lavfi", "-i", f"testsrc2=size=640x360:rate=25:duration={seconds}", "-f", "lavfi", "-i",
         f"sine=frequency=330:duration={seconds}", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(path)])
    lines = []
    for i in range(seconds // 10):
        a, b = i * 10 + 1, i * 10 + 4
        lines += [str(i + 1), f"00:{a // 60:02d}:{a % 60:02d},000 --> 00:{b // 60:02d}:{b % 60:02d},500",
                  f"Câu thoại số {i + 1}.", ""]
    path.with_suffix(".srt").write_text("\n".join(lines), encoding="utf-8")


def fake_vieneu(text, voice, out, settings):
    wav = out.with_suffix(".raw.wav")
    d = max(1.0, len(text.split()) / 3.0)
    run(["-f", "lavfi", "-i", f"sine=frequency=660:duration={d:.2f}", "-ac", "1", str(wav)])
    return wav


def check_units():
    assert voices.vi_number(2024) == "hai nghìn không trăm hai mươi tư"
    assert voices.vi_normalize("tăng 12,5%") == "tăng mười hai phẩy năm phần trăm"
    cut = '{"title":"X","segments":[{"start":"00:00:10","end":"00:00:20","narration":"A"},{"start":"00:01'
    assert ai.extract_json(cut)["segments"][0]["narration"] == "A"
    assert ai.pick_gemini(["gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-pro"]) == \
        "gemini-3.8-flash"
    subs = transcript.parse_subtitles(_write(TMP / "a.ass", "[Events]\nFormat: Layer, Start, End, Style, Text\n"
                                             "Dialogue: 0,0:00:01.00,0:00:03.50,Default,{\\i1}Xin chào\\Nbạn\n"))
    assert subs == [{"start": 1.0, "end": 3.5, "text": "Xin chào bạn"}], subs
    ch = render.chunks("một hai ba bốn năm sáu bảy tám chín mười " * 4, 10, 20)
    assert ch[0][0] == 0.15 and abs(ch[-1][1] - 10) < 0.01 and all("\\N" in c[2] or len(c[2]) <= 20 for c in ch)
    # Hủy khi đang chờ AI -> dừng ngay
    ev = threading.Event()
    threading.Timer(0.5, ev.set).start()
    t0 = time.time()
    try:
        ai._watch(lambda: time.sleep(30), "AI", None, ev)
        raise AssertionError("phải dừng")
    except Cancelled:
        assert time.time() - t0 < 2
    print("✓ đọc số, JSON bị cắt, chọn model, phụ đề ASS, chia phụ đề, nút Hủy")


def _write(p: Path, t: str) -> Path:
    p.write_text(t, encoding="utf-8")
    return p


def main():
    check_units()
    s = Settings(TMP / "settings.json")
    s.set("ai", "ollama_url", start_fake_ollama())
    s.set("ai", "minutes", 2.0)
    s.set("paths", "output", str(TMP / "out"))
    s.set("video", "height", 360)
    s.set("video", "parallel", 3)
    voices._vieneu = fake_vieneu
    movie = TMP / "Phim Thử.mp4"
    make_movie(movie)
    assert s.offline and s.get("ai", "provider") == "ollama" and s.get("voice", "engine") == "vieneu"

    p = Project(str(movie), s)
    steps = []
    out = p.run_all(log=log, progress=prog, step=lambda *a: steps.append(a))
    # lời thoại lấy từ phụ đề cạnh phim (không cần nhận dạng giọng nói)
    assert len(p.transcript) == 66 and any("phụ đề cạnh phim" in m for m in LOG), LOG[:5]
    # AI chạy trên máy (Ollama): gửi đúng API, ngữ cảnh lớn, ép JSON; viết ngắn -> tự yêu cầu viết dài thêm
    assert len(FakeOllama.calls) == 2, len(FakeOllama.calls)
    c0 = FakeOllama.calls[0]
    assert c0["model"] == "qwen2.5:7b" and c0["format"] == "json" and c0["options"]["num_ctx"] >= 8192
    assert "TARGET VIDEO LENGTH: about 120 seconds" in c0["messages"][1]["content"]
    assert "FAR TOO SHORT" in FakeOllama.calls[1]["messages"][1]["content"]
    assert len(p.script["segments"]) == 10
    info = probe(out)
    assert (info.width, info.height) == (640, 360) and info.has_audio and 100 < info.duration < 200, info
    assert [x[0] for x in steps] == ["transcript", "transcript", "script", "script", "voice", "voice", "render",
                                    "render"], steps
    assert sorted(f.name for f in (TMP / "out").iterdir()) == [out.name]  # chỉ có video thành phẩm
    print(f"✓ offline A→Z: {len(p.transcript)} câu thoại → {len(p.script['segments'])} đoạn → {info.summary()}")

    # Dọc 9:16 + che phụ đề gốc (phóng to / làm mờ / dải đen) + giữ thoại gốc
    for aspect, cover in (("9:16", "zoom"), ("16:9", "blur"), ("1:1", "bar")):
        s.set("video", "aspect", aspect)
        s.set("video", "cover", cover)
        o = p.run_render(TMP / "out" / f"{cover}.mp4", log=log, progress=prog)
        i2 = probe(o)
        want = {"9:16": (360, 640), "16:9": (640, 360), "1:1": (360, 360)}[aspect]
        assert (i2.width, i2.height) == want, (aspect, i2.width, i2.height)
    p.save_script({"title": "x", "segments": [{"start": 30, "end": 36, "narration": "", "keep_original": True},
                                              {"start": 60, "end": 70, "narration": "Đoạn cuối.", "keep_original": False}]})
    o = p.run_render(TMP / "out" / "mixed.mp4", log=log, progress=prog)
    assert 7 < probe(o).duration < 12
    # làm lại: các đoạn đã dựng được dùng lại -> nhanh
    t0 = time.time()
    p.run_render(TMP / "out" / "mixed2.mp4", log=log, progress=prog)
    assert time.time() - t0 < 10
    print("✓ khung 9:16 / 16:9 / 1:1, che phụ đề gốc (phóng to, làm mờ, dải đen), giữ thoại gốc, dùng lại bản dựng")

    # không AI: tự cắt cảnh nổi bật
    s.set("ai", "provider", "none")
    sc = writer.write(p.transcript, p.info.duration, s, log, prog, threading.Event())
    assert sc["segments"] and all(x["keep_original"] for x in sc["segments"])
    print("OK", TMP)


if __name__ == "__main__":
    main()
