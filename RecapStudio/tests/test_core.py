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

from recapstudio import (ai, hardsub, hybrid, publish, reframe, render, scenes, transcript, updater,  # noqa: E402
                         voices, writer)
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
    info_calls: list = []
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
        if body["messages"][0]["content"].startswith("You write metadata"):  # tiêu đề / hashtag
            FakeOllama.info_calls.append(body)
            return self._send({"message": {"content": json.dumps(
                {"titles": ["Hành trình kỳ lạ của cậu bé"], "description": "Một chuyến đi.",
                 "hashtags": ["reviewphim", "#phimhay"], "tags": ["phim"]}, ensure_ascii=False)}})
        FakeOllama.calls.append(body)
        n = FakeOllama.reply_words[min(len(FakeOllama.calls) - 1, 1)]
        segs = [{"start": f"00:{m:02d}:05", "end": f"00:{m:02d}:15",
                 "narration": " ".join(["Nhân vật chính bước tiếp trên hành trình"] * (n // 7 + 1))}
                for m in range(0, 3 if n < 20 else 10)]
        self._send({"message": {"content": json.dumps({"title": "Hành trình thử nghiệm", "segments": segs},
                                                      ensure_ascii=False)}})


class FakeOnline(BaseHTTPRequestHandler):
    """AI online giả (chuẩn OpenAI /chat/completions)."""
    calls: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOnline.calls.append(body)
        b = json.dumps({"choices": [{"message": {"content": "online-ok"}, "finish_reason": "stop"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def start_server(handler) -> str:
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


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


READY_VOICES = {"vieneu", "piper"}


def check_hybrid(s: Settings, p: Project):
    """Chế độ lai: thứ tự AI theo chế độ / mạng / key; tự chuyển online <-> trên máy; giọng dự phòng."""
    online = start_server(FakeOnline)
    ai.PROVIDERS["deepseek"]["base"] = online
    s.set("keys", "deepseek", "sk-test")
    s.data["mode"] = "auto"
    hybrid.set_net(False)
    assert hybrid.ai_chain(s) == ["ollama"]                     # mất mạng -> AI trên máy
    hybrid.set_net(True)
    assert hybrid.ai_chain(s) == ["deepseek", "ollama"]         # có mạng + key -> online trước, máy dự phòng
    s.set("ai", "provider", "ollama")
    assert hybrid.ai_chain(s) == ["ollama", "deepseek"]         # chọn AI trên máy -> máy trước, online dự phòng
    s.data["mode"] = "offline"
    assert hybrid.ai_chain(s) == ["ollama"]
    s.data["mode"] = "auto"
    s.set("ai", "provider", "auto")
    assert ai.chat(s, "sys", "xin chào", json_mode=False) == "online-ok" and FakeOnline.calls[-1]["model"] == \
        "deepseek-chat"
    # online không kết nối được -> tự chuyển sang AI trên máy
    ai.PROVIDERS["deepseek"]["base"] = "http://127.0.0.1:9"
    n = len(FakeOllama.calls)
    t0 = time.time()
    ai.chat(s, "sys", "xin chào", json_mode=False, log=log)
    assert len(FakeOllama.calls) == n + 1 and time.time() - t0 < 10
    # AI trên máy tắt -> tự chuyển sang online
    ai.PROVIDERS["deepseek"]["base"] = online
    s.set("ai", "provider", "ollama")
    good = s.get("ai", "ollama_url")
    s.set("ai", "ollama_url", "http://127.0.0.1:9")
    s.set("ai", "auto_start_ollama", False)
    assert ai.chat(s, "sys", "xin chào", json_mode=False, log=log) == "online-ok"
    s.set("ai", "ollama_url", good)
    s.set("ai", "provider", "auto")
    s.set("keys", "deepseek", "")
    # giọng: giọng online khi offline -> giọng trên máy; giọng lỗi -> giọng dự phòng, đọc lại toàn bộ cho đều
    s.data["mode"] = "offline"
    s.set("voice", "engine", "edge")
    p.voice_files(log, prog)
    assert p.voice_engine_used == "vieneu", p.voice_engine_used
    s.set("voice", "engine", "vieneu")

    def bad(*_a, **_k):
        raise voices.TTSError("hỏng")
    voices._vieneu, keep = bad, voices._vieneu
    import shutil

    shutil.rmtree(p.dir / "voices")  # bỏ giọng đã đọc sẵn để buộc đọc lại
    voices._piper = lambda text, voice, out, speed, settings, log=None: fake_vieneu(text, voice, out, settings)
    files = p.voice_files(log, prog)
    assert p.voice_engine_used == "piper" and all(f is None or f.exists() for f in files)
    voices._vieneu = keep
    print("✓ chế độ lai: chọn AI theo mạng/key, online ⇄ trên máy tự chuyển, giọng dự phòng")


def check_tools():
    """Dò chuyển cảnh, dò phụ đề cứng, ảnh bìa, cập nhật trực tiếp, tải từ link."""
    w = TMP / "tools"
    w.mkdir()
    # 5 cảnh khác nhau, mỗi cảnh 6 giây
    srcs = ["testsrc2", "color=c=red", "mandelbrot", "color=c=blue", "smptebars"]
    args, fc = [], ""
    for i, src in enumerate(srcs):
        args += ["-f", "lavfi", "-i", f"{src}{'=' if '=' not in src else ':'}s=640x360:r=25"]
        fc += f"[{i}]trim=duration=6,setpts=PTS-STARTPTS,format=yuv420p[v{i}];"
    fc += "".join(f"[v{i}]" for i in range(5)) + "concat=n=5:v=1[v]"
    run([*args, "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-preset", "veryfast", str(w / "sc.mp4")])
    assert isinstance(scenes.detect(str(w / "sc.mp4"), w), list)   # dò nhanh (khung khóa)
    cuts = scenes.detect(str(w / "sc.mp4"), w, full=True)          # dò chi tiết
    assert all(any(abs(c - t) < 0.3 for c in cuts) for t in (6, 12, 18, 24)), cuts
    assert scenes.snap(11.2, cuts) == round(min(cuts, key=lambda c: abs(c - 12)) + 0.04, 3)
    assert scenes.snap(9.0, cuts) == 9.0  # xa điểm chuyển cảnh -> giữ nguyên
    # phụ đề cứng
    srt = w / "s.srt"
    srt.write_text("".join(f"{i + 1}\n00:00:{i * 2:02d},000 --> 00:00:{i * 2 + 1:02d},800\nCâu phụ đề số {i} "
                           f"đang chạy\n\n" for i in range(20)), encoding="utf-8")
    run(["-f", "lavfi", "-i", "mandelbrot=s=1280x720:r=25", "-t", "40", "-vf",
         f"subtitles={srt.name}:force_style='Fontsize=24,Outline=2'", "-c:v", "libx264", "-preset", "ultrafast",
         "hs.mp4"], cwd=str(w))
    band = hardsub.detect(str(w / "hs.mp4"), probe(w / "hs.mp4"), w)
    assert band and 0.8 < band[0] < band[1] <= 1.0, band
    (w / "hardsub.json").unlink()
    assert hardsub.detect(str(w / "sc.mp4"), probe(w / "sc.mp4"), w) is None
    # ảnh bìa dọc
    th = publish.make_thumbnail(str(w / "sc.mp4"), probe(w / "sc.mp4"), [{"start": 2, "end": 8, "narration": "a"}],
                                "Tiêu đề rất dài để thử xuống dòng của ảnh bìa video", w / "t.jpg", "9:16")
    from PIL import Image

    assert Image.open(th).size == (1080, 1920)
    assert publish.fallback_info({"title": "X", "segments": []}, "Phim Hay")["hashtags"][0] == "#PhimHay"
    # cập nhật trực tiếp: chép bản mới, sao lưu bản cũ, dọn file thừa, không đụng .venv
    import io
    import zipfile

    app = w / "app"
    (app / "recapstudio").mkdir(parents=True)
    (app / ".venv").mkdir()
    (app / "main.py").write_text("old", encoding="utf-8")
    (app / "recapstudio" / "old_module.py").write_text("x", encoding="utf-8")
    (app / ".venv" / "keep.txt").write_text("k", encoding="utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("repo-branch/RecapStudio/", "")
        z.writestr("repo-branch/RecapStudio/main.py", "new")
        z.writestr("repo-branch/RecapStudio/recapstudio/__init__.py", 'VERSION = "9.9.9"')
        z.writestr("repo-branch/RecapStudio/.venv/keep.txt", "BAD")
        z.writestr("repo-branch/MovieRecapAI/main.py", "other app")
    n = updater.apply_zip(buf.getvalue(), app, "9.9.9", log)
    assert n == 3 and (app / "main.py").read_text() == "new" and not (app / "recapstudio" / "old_module.py").exists()
    assert (app / ".venv" / "keep.txt").read_text() == "k"
    assert (app / "_backup").exists() and json.loads((app / ".version.json").read_text())["version"] == "9.9.9"
    assert updater.vtuple("2.0.10") > updater.vtuple("2.0.9")
    # tải phim từ link (yt-dlp, máy chủ giả trên máy)
    try:
        import yt_dlp  # noqa: F401  # pyflakes: ignore
    except ImportError:
        print("✓ dò chuyển cảnh, dò phụ đề cứng, ảnh bìa, cập nhật trực tiếp (bỏ qua tải link: chưa có yt-dlp)")
        return
    import functools
    from http.server import SimpleHTTPRequestHandler

    from recapstudio import download

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(w)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = Settings(w / "dl.json")
    s.set("paths", "downloads", str(w / "dl"))
    s.data["mode"] = "auto"
    assert download.is_url(" https://youtu.be/abc ") and not download.is_url("C:/phim.mp4")
    got = download.download(f"http://127.0.0.1:{srv.server_port}/sc.mp4", s, log, prog, threading.Event())
    assert got.exists() and 29 < probe(got).duration < 31, got
    print("✓ dò chuyển cảnh, dò phụ đề cứng, ảnh bìa, cập nhật trực tiếp, tải phim từ link")


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
    s.data["mode"] = "offline"
    voices._vieneu = fake_vieneu
    hybrid.voice_ready = lambda e, _s: e in READY_VOICES
    movie = TMP / "Phim Thử.mp4"
    make_movie(movie)
    assert s.offline and s.get("ai", "provider") == "auto" and s.get("voice", "engine") == "vieneu"
    assert hybrid.ai_chain(s) == ["ollama"]

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
    assert [x[0] for x in steps] == ["transcript", "transcript", "script", "script", "publish", "voice", "voice",
                                    "render", "render", "publish"], steps
    assert steps[-1][1] == "done", steps[-1]
    assert sorted(f.name for f in (TMP / "out").iterdir()) == [out.name]  # chỉ có video thành phẩm
    # ảnh bìa + tiêu đề/hashtag (AI trên máy) nằm trong dự án, không làm bẩn thư mục video
    assert len(FakeOllama.info_calls) == 1 and p.publish_info["titles"][0] == "Hành trình kỳ lạ của cậu bé"
    assert p.publish_info["hashtags"][0] == "#reviewphim"
    from PIL import Image

    assert Image.open(p.thumbnail).size == (1280, 720)
    print(f"✓ offline A→Z: {len(p.transcript)} câu thoại → {len(p.script['segments'])} đoạn → {info.summary()} "
          "+ ảnh bìa + tiêu đề/hashtag")

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

    # xem trước 1 đoạn
    pv = p.preview_segment(1, log=log, progress=prog)
    assert pv.exists() and 0.8 < probe(pv).duration < 12, probe(pv).duration
    # khung dọc bám nhân vật
    s.set("video", "aspect", "9:16")
    s.set("video", "fill", "face")
    s.set("video", "cover", "auto")
    o = p.run_render(TMP / "out" / "face.mp4", log=log, progress=prog)
    assert (probe(o).width, probe(o).height) == (360, 640)
    print("✓ xem trước 1 đoạn, khung dọc bám nhân vật" + ("" if reframe.available() else " (không có OpenCV)"))

    check_hybrid(s, p)
    check_tools()

    # không AI: tự cắt cảnh nổi bật
    s.set("ai", "provider", "none")
    sc = writer.write(p.transcript, p.info.duration, s, log, prog, threading.Event())
    assert sc["segments"] and all(x["keep_original"] for x in sc["segments"])
    print("OK", TMP)


if __name__ == "__main__":
    main()
