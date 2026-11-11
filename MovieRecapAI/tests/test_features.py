"""Kiểm thử bản 1.1: cách đọc, giọng không bị rỗng, nhận diện phim, AI xem cảnh, thành phần, model tự chọn."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
TMP = Path(tempfile.mkdtemp(prefix="recap_feat_"))
os.environ["MOVIE_RECAP_HOME"] = str(TMP / "home")

from recap import components, film_id, llm, script_writer, transcribe, tts  # noqa: E402
from recap.config import Settings  # noqa: E402
from recap.ffmpeg_utils import media_duration, run_ffmpeg  # noqa: E402
from recap.pipeline import Project  # noqa: E402
from test_pipeline import make_srt, make_video  # noqa: E402


def check_read_styles():
    base = {"rate": 5, "pitch": 0}
    o = tts.apply_read_style("edge", dict(base, read_style="funny"))
    assert o["rate"] == 15 and o["pitch"] == 1, o
    # tone của đoạn được ưu tiên khi tắt "giữ 1 giọng đồng nhất"
    o = tts.apply_read_style("edge", dict(base, read_style="funny", tone="horror", consistent=False))
    assert o["rate"] == -5 and o["pitch"] == -3, o
    o = tts.apply_read_style("edge", dict(base, read_style="funny", tone="horror"))  # mặc định: giữ cao độ chung
    assert o["pitch"] == 1 and o["rate"] == 9, o
    o = tts.apply_read_style("openai", dict(base, read_style="serious"))
    assert "news anchor" in o["style"] and o["rate"] == 5
    o = tts.apply_read_style("azure", dict(base, read_style="sad"))
    assert o["style"] == "sad"
    o = tts.apply_read_style("gemini", dict(base, read_style="custom", read_custom="giọng bựa chém gió"))
    assert o["style"] == "Đọc với giọng giọng bựa chém gió" or "bựa" in o["style"]
    o = tts.apply_read_style("elevenlabs", dict(base, read_style="excited"))
    assert o["el_tag"] == "[excited]" and o["el_settings"] == (0.3, 0.65)
    print("✓ cách đọc")


def check_synth_robust(s: Settings):
    calls = []

    def quiet(text, voice, base, opts, settings):  # giọng rất nhỏ (-60dB) -> lọc lặng cắt hết -> phải tự làm lại
        out = base.with_suffix(".wav")
        run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=300:duration=1.5", "-af", "volume=-62dB", str(out)])
        calls.append(opts)
        return out

    def empty(text, voice, base, opts, settings):
        out = base.with_suffix(".mp3")
        out.write_bytes(b"")
        return out
    tts._synth_edge = quiet
    out = TMP / "q.wav"
    tts.synthesize("edge", "Xin chào", "vi-VN-HoaiMyNeural", out, {"read_style": "funny"}, s)
    assert media_duration(out) > 1.0, media_duration(out)
    assert calls[-1]["rate"] == 10  # cách đọc hài hước được áp
    tts._synth_edge = empty
    bad = TMP / "bad.wav"
    try:
        tts.synthesize("edge", "Xin chào", "x", bad, {}, s)
        raise AssertionError("phải báo lỗi")
    except tts.TTSError as e:
        assert "rỗng" in str(e)
    assert not bad.exists(), "không được để lại file hỏng trong cache"
    print("✓ giọng đọc không bị rỗng/hỏng")


def check_film_and_script(s: Settings):
    assert film_id.clean_filename("The.Dark.Knight.2008.1080p.BluRay.x264-[YTS].mkv") == ("The Dark Knight", "2008")
    assert film_id.clean_filename("Bố Già (2021) Full HD Vietsub.mp4")[1] == "2021"
    vid, srt = TMP / "Inception.2010.1080p.mp4", TMP / "Inception.2010.1080p.srt"
    make_video(vid, 120)
    make_srt(srt, 120)
    s.set("script", "provider", "gemini")
    s.set("api", "gemini_key", "x")
    seen = {}

    def fake_chat(pid, model, system, user, settings, json_mode=True, max_tokens=0, log=None, images=None):
        if system == film_id.ID_SYSTEM:
            seen["id_images"] = len(images or [])
            seen["id_user"] = user
            return json.dumps({"title": "Kẻ Đánh Cắp Giấc Mơ", "original_title": "Inception", "year": "2010",
                               "type": "movie", "confidence": 0.95,
                               "characters": [{"name": "Cobb", "description": "kẻ trộm giấc mơ"}],
                               "whisper_hint": "Inception, Cobb, Ariadne"})
        if system == film_id.VIS_SYSTEM:
            seen["vis_images"] = len(images or [])
            return json.dumps({"frames": [{"t": "x", "desc": f"cảnh {i}"} for i in range(len(images))]})
        seen["script_user"] = user
        return json.dumps({"title": "T", "segments": [
            {"start": "00:00:05", "end": "00:00:15", "narration": "Cobb bước vào giấc mơ.", "tone": "dramatic"},
            {"start": "00:01:00", "end": "00:01:10", "narration": "Thật buồn cười!", "tone": "funny"},
            {"start": "00:01:30", "end": "00:01:40", "narration": "Hết.", "tone": "không-hợp-lệ"}]})
    film_id.chat = fake_chat
    script_writer.chat = fake_chat
    p = Project(str(vid), s)
    p.run_identify()
    assert p.film["title"] == "Kẻ Đánh Cắp Giấc Mơ" and seen["id_images"] == 7
    assert "Inception" in seen["id_user"]
    assert film_id.whisper_hint(p.film) == "Inception, Cobb, Ariadne"
    p.run_transcribe(subtitle_file=str(srt), engine="subtitle")
    p.run_visual()
    assert len(p.visual) == seen["vis_images"] > 0
    p.film["notes"] = "Phim của Christopher Nolan"
    p.run_script()
    u = seen["script_user"]
    assert "Kẻ Đánh Cắp Giấc Mơ" in u and "Cobb" in u and "Christopher Nolan" in u and "VISUAL NOTES" in u, u[:800]
    tones = [x["tone"] for x in p.script["segments"]]
    assert tones == ["dramatic", "funny", ""], tones
    # Lưu/nạp lại dự án giữ thông tin phim
    p2 = Project(str(vid), s)
    assert p2.film["original_title"] == "Inception" and p2.visual
    # Giọng theo cảm xúc từng đoạn
    got = []

    def rec(text, voice, base, opts, settings):
        got.append((opts.get("tone"), opts.get("rate")))
        out = base.with_suffix(".wav")
        run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=500:duration=1", str(out)])
        return out
    tts._synth_edge = rec
    s.set("voice", "engine", "edge")
    s.set("voice", "voice", "vi-VN-HoaiMyNeural")
    s.set("voice", "read_style", "serious")
    s.set("voice", "rate", 0)
    s.set("voice", "tone_auto", True)
    s.set("voice", "consistent", False)  # cảm xúc tự do từng đoạn
    p2.run_voices()
    assert got == [("dramatic", 3.0), ("funny", 10.0), ("serious", -4.0)], got
    # Giữ 1 giọng đồng nhất (mặc định): cao độ giống nhau mọi đoạn, chỉ nhích tốc độ tối đa ±6%
    s.set("voice", "consistent", True)
    for t in ("dramatic", "funny", "serious", "horror", "kids"):
        o = tts.apply_read_style("edge", {"read_style": "serious", "tone": t, "rate": 0, "pitch": 0, "consistent": True})
        assert o["pitch"] == -1 and -10 <= o["rate"] <= 2, (t, o["rate"], o["pitch"])
        o = tts.apply_read_style("gemini", {"read_style": "serious", "tone": t, "consistent": True})
        assert "nghiêm túc" in o.get("style", ""), o  # Gemini giữ 1 phong cách giọng
    s.set("voice", "consistent", False)
    got.clear()
    s.set("voice", "tone_auto", False)
    p2.run_voices()
    # đoạn 3 vốn đã đọc "serious" -> dùng lại cache, chỉ 2 đoạn đầu phải đọc lại
    assert [g[0] for g in got] == ["serious"] * 2, got
    print("✓ nhận diện phim, AI xem cảnh, kịch bản có cách đọc từng đoạn")


def check_tmdb(s: Settings):
    import requests

    class R:
        def __init__(self, js):
            self._js, self.status_code = js, 200

        def json(self):
            return self._js

        def raise_for_status(self):
            pass

    def get(self, url, params=None, headers=None, timeout=None):
        if "search/multi" in url:
            assert params["api_key"] == "k123"
            return R({"results": [{"media_type": "movie", "id": 27205, "release_date": "2010-07-15"}]})
        return R({"title": "Kẻ Đánh Cắp Giấc Mơ", "original_title": "Inception", "release_date": "2010-07-15",
                  "overview": "Cobb là kẻ trộm...", "genres": [{"name": "Hành Động"}],
                  "credits": {"cast": [{"name": "Leonardo DiCaprio", "character": "Dom Cobb"}]}})
    old = requests.Session.get
    requests.Session.get = get
    try:
        s.set("api", "tmdb_key", "k123")
        r = film_id.tmdb_lookup("Inception", "2010", s)
        assert r["characters"][0]["name"] == "Dom Cobb" and r["year"] == "2010" and r["premise"]
    finally:
        requests.Session.get = old
        s.set("api", "tmdb_key", "")
    print("✓ TMDB")


def check_vision_payloads(s: Settings):
    import requests

    bodies = []

    class R:
        status_code = 200

        def __init__(self, js):
            self._js = js

        def json(self):
            return self._js

    def post(self, url, **kw):
        bodies.append((url, kw.get("json")))
        if "generativelanguage" in url:
            return R({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})
        return R({"choices": [{"message": {"content": "{}"}}]})
    old = requests.Session.post
    requests.Session.post = post
    try:
        s.set("api", "openai_key", "x")
        s.set("api", "gemini_key", "x")
        llm.chat("gemini", "gemini-2.5-flash", "sys", "u", s, images=[("a", b"\xff\xd8jpg")])
        parts = bodies[-1][1]["contents"][0]["parts"]
        assert parts[0] == {"text": "a"} and parts[1]["inlineData"]["mimeType"] == "image/jpeg" and parts[2]["text"] == "u"
        llm.chat("openai", "gpt-4.1", "sys", "u", s, images=[("a", b"jpg")])
        content = bodies[-1][1]["messages"][1]["content"]
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    finally:
        requests.Session.post = old
    print("✓ gửi ảnh cho AI (Gemini/OpenAI)")


def check_components(s: Settings):
    assert components.status("edge_tts", s)[0]
    ok, note = components.status("ffmpeg", s)
    assert ok, note
    assert "xtts" in components.missing_for(s, "xtts") or components.is_module("TTS")
    m = transcribe.resolve_model("auto", "cpu")
    assert m in ("large-v3-turbo", "small")
    assert transcribe.resolve_model("medium") == "medium"
    print(f"✓ thành phần & model tự chọn (CPU {os.cpu_count()} luồng -> {m})")


def check_model_fallback(s: Settings):
    """Google ngừng gemini-2.5-flash (lỗi 404 như ảnh người dùng gửi) -> tự đổi model, nhớ vào cài đặt."""
    import requests

    calls = []

    class R:
        def __init__(self, code, js):
            self.status_code, self._js, self.text = code, js, json.dumps(js)

        def json(self):
            return self._js

    def post(self, url, **kw):
        calls.append(url)
        if "gemini-2.5-flash:" in url:
            return R(404, {"error": {"code": 404, "status": "NOT_FOUND", "message":
                    "This model models/gemini-2.5-flash is no longer available to new users. Please update your code "
                    "to use models/gemini-3.8-flash for the latest features and improvements."}})
        return R(200, {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]})

    def get(self, url, **kw):
        return R(200, {"models": [{"name": f"models/{n}", "supportedGenerationMethods": ["generateContent"]} for n in
                                  ("gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.8-flash-lite", "gemini-3.8-pro",
                                   "gemini-3.8-flash-preview-tts", "gemini-3.9-flash-image")]})
    old_p, old_g = requests.Session.post, requests.Session.get
    requests.Session.post, requests.Session.get = post, get
    llm._RESOLVED.clear()
    try:
        s.set("api", "gemini_key", "x")
        s.set("script", "provider", "gemini")
        s.set("script", "model", "gemini-2.5-flash")
        assert llm.chat("gemini", "gemini-2.5-flash", "sys", "u", s) == '{"ok": true}'
        assert "gemini-3.8-flash:generateContent" in calls[-1], calls
        assert s.get("script", "model") == "gemini-3.8-flash"
        n = len(calls)
        llm.chat("gemini", "gemini-2.5-flash", "sys", "u", s)  # lần sau dùng luôn model mới, không gọi lỗi nữa
        assert len(calls) == n + 1 and "3.8-flash:" in calls[-1]
        llm._RESOLVED.clear()
        assert llm.resolve_model("gemini", "auto", s) == "gemini-3.8-flash"
        assert llm.resolve_model("gemini", "gemini-2.5-flash-lite", s, error="404") == "gemini-3.8-flash-lite"
        assert llm.pick_model("gemini", "gemini-2.5-flash-preview-tts", ["gemini-3.8-flash", "gemini-3.8-flash-preview-tts"],
                              "tts") == "gemini-3.8-flash-preview-tts"
    finally:
        requests.Session.post, requests.Session.get = old_p, old_g
        llm._RESOLVED.clear()
    print("✓ tự đổi model khi Google ngừng model cũ")


def check_scenes():
    """Video có chuyển cảnh thật (lỗi 'FrameTimecode % int' chỉ xảy ra khi có cảnh)."""
    import threading

    from recap.scenes import detect_scenes

    vid = TMP / "cuts.mp4"
    srcs = ["testsrc2", "color=c=red", "smptebars", "color=c=blue", "rgbtestsrc"]
    args, filt = [], ""
    for i, src in enumerate(srcs):
        sep = ":" if "=" in src else "="
        args += ["-f", "lavfi", "-i", f"{src}{sep}size=320x180:rate=25:duration=4"]
        filt += f"[{i}:v]format=yuv420p,setsar=1[v{i}];"
    filt += "".join(f"[v{i}]" for i in range(len(srcs))) + f"concat=n={len(srcs)}:v=1:a=0[v]"
    run_ffmpeg([*args, "-filter_complex", filt, "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", str(vid)])
    prog = []
    cuts = detect_scenes(str(vid), lambda *a, **k: None, lambda p, m="": prog.append(p), threading.Event(), chunk=6)
    assert len(cuts) == 5 and all(abs(c - i * 4) < 0.2 for i, c in enumerate(cuts)), cuts
    assert prog and prog[-1] == 1.0, prog
    ev = threading.Event()
    ev.set()
    try:
        detect_scenes(str(vid), lambda *a, **k: None, lambda *a: None, ev)
        raise AssertionError("phải hủy được")
    except Exception as e:  # noqa: BLE001
        assert e.__class__.__name__ == "Cancelled", e
    print("✓ dò chuyển cảnh (scenedetect 0.7)")


def check_warmup(s: Settings):
    """Nạp sẵn khi mở app: model VieNeu được nạp đúng 1 lần, lỗi 1 bước không chặn các bước sau."""
    import threading
    import types

    from recap import warmup

    made = []

    class FakeVieneu:
        def __init__(self, mode="v3turbo", **kw):
            made.append(mode)
    real = sys.modules.get("vieneu")
    sys.modules["vieneu"] = types.SimpleNamespace(Vieneu=FakeVieneu, __spec__=None)
    old_dl = components.download_whisper
    components.download_whisper = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("không có mạng"))
    old_is = components.is_module
    components.is_module = lambda m: True if m == "vieneu" else old_is(m)
    try:
        s.set("voice", "engine", "vieneu")
        s.set("voice", "model", "v3turbo")
        s.set("script", "provider", "none")
        keys = [k for k, _ in warmup.plan(s)]
        assert "load_vieneu" in keys and "llm" not in keys, keys
        rep = warmup.run(s, lambda *a, **k: None, lambda *a, **k: None, threading.Event())
        tts.get_vieneu("v3turbo")  # lần sau dùng lại, không nạp lại
        assert made == ["v3turbo"], made
        assert "load_vieneu" in rep["done"] and "encoder" in rep["done"], rep
        if not components.whisper_model_ready(s):
            assert any("model" in e.lower() or "mạng" in e for e in rep["errors"]), rep
    finally:
        components.download_whisper = old_dl
        components.is_module = old_is
        tts._VIENEU.clear()
        if real is not None:
            sys.modules["vieneu"] = real
        else:
            sys.modules.pop("vieneu", None)
        s.set("voice", "engine", "edge")
    print("✓ nạp sẵn khi mở app")


def check_rate_limits(s: Settings):
    """Lỗi 429 như ảnh người dùng: OpenAI hết tiền -> báo rõ & tự chuyển sang Gemini; quá tải -> đợi đúng thời gian."""
    import requests
    import time as _time

    sent = []

    class R:
        def __init__(self, code, js, headers=None):
            self.status_code, self._js, self.text, self.headers = code, js, json.dumps(js), headers or {}

        def json(self):
            return self._js
    mode = {"openai": "quota"}

    def post(self, url, **kw):
        sent.append(url)
        if "api.openai.com" in url:
            if mode["openai"] == "quota":
                return R(429, {"error": {"message": "You exceeded your current quota, please check your plan and "
                                                    "billing details.", "type": "insufficient_quota",
                                         "code": "insufficient_quota"}})
            if mode["openai"] == "toolarge":
                return R(429, {"error": {"message": "Request too large for gpt-4.1 in organization org-x on tokens "
                                                    "per min (TPM): Limit 30000, Requested 45210.",
                                         "code": "rate_limit_exceeded"}})
            body = kw.get("json") or {}
            return R(200, {"choices": [{"message": {"content": json.dumps({"segments": [
                {"start": "00:00:01", "end": "00:00:09", "narration": "ok"}]}) if "segments" in str(body)[:4000]
                else "tóm tắt"}}]})
        if "generativelanguage" in url:
            if mode.get("gemini") == "minute" and sum("generativelanguage" in u for u in sent) == 1:
                return R(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota",
                                         "details": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"},
                                                     {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                                                      "retryDelay": "7s"}]}})
            return R(200, {"candidates": [{"content": {"parts": [{"text": '{"ok": "gemini"}'}]}}]})
        raise AssertionError(url)
    waits = []
    old_post, old_sleep = requests.Session.post, _time.sleep
    requests.Session.post = post
    _time.sleep = lambda x: waits.append(x)
    llm._DEAD.clear()
    llm._RESOLVED.clear()
    try:
        s.set("api", "openai_key", "sk")
        s.set("api", "gemini_key", "")
        s.set("script", "auto_fallback", True)
        try:
            llm.chat("openai", "gpt-4.1", "sys", "u", s)
            raise AssertionError("phải báo lỗi")
        except llm.LLMError as e:
            assert "hết tiền" in str(e) and "Nhập thêm key" in str(e), e
        assert sum("openai" in u for u in sent) == 1, "hết tiền thì không được thử lại vô ích"
        llm._DEAD.clear()
        s.set("api", "gemini_key", "g")
        llm._RESOLVED[("gemini", "auto", "text")] = "gemini-3.8-flash"
        assert llm.chat("openai", "gpt-4.1", "sys", "u", s) == '{"ok": "gemini"}'
        n_openai = sum("openai" in u for u in sent)
        llm.chat("openai", "gpt-4.1", "sys", "u", s)  # lần sau đi thẳng Gemini
        assert sum("openai" in u for u in sent) == n_openai
        # Gemini quá tải theo phút -> đợi đúng retryDelay (7s) rồi thử lại
        llm._DEAD.clear()
        sent.clear()
        mode["gemini"] = "minute"
        waits.clear()
        assert llm.chat("gemini", "gemini-3.8-flash", "sys", "u", s) == '{"ok": "gemini"}'
        assert waits and waits[0] >= 7, waits
        # Yêu cầu quá dài so với hạn mức TPM -> tự chia nhỏ lời thoại rồi viết lại
        mode["openai"] = "toolarge"
        llm._DEAD.clear()
        calls = {"n": 0}
        real_post = requests.Session.post

        def post2(self, url, **kw):
            calls["n"] += 1
            if calls["n"] > 1:
                mode["openai"] = "ok"
            return real_post(self, url, **kw)
        requests.Session.post = post2
        tr = [{"start": i * 5, "end": i * 5 + 4, "text": "câu thoại khá dài " * 6} for i in range(400)]
        logs = []
        sc = script_writer.write_script(tr, 2000, s, {"provider": "openai", "model": "gpt-4.1", "target_minutes": 1},
                                        lambda m, level="": logs.append(m), lambda *a, **k: None,
                                        __import__("threading").Event())
        assert sc["segments"] and any("chia nhỏ" in m for m in logs) and any("Tóm tắt trước" in m for m in logs), logs
    finally:
        requests.Session.post, _time.sleep = old_post, old_sleep
        llm._DEAD.clear()
        llm._RESOLVED.clear()
        s.set("api", "openai_key", "")
    print("✓ lỗi 429: hết tiền / quá tải / quá dài + tự chuyển AI")


def check_config_migration():
    f = TMP / "old.json"
    f.write_text(json.dumps({"render": {"encoder": "libx264"}, "transcribe": {"model": "small"}}), encoding="utf-8")
    s = Settings(f)
    assert s.get("render", "encoder") == "auto" and s.get("transcribe", "model") == "auto"
    f.write_text(json.dumps({"config_version": 2, "render": {"encoder": "libx264"}}), encoding="utf-8")
    assert Settings(f).get("render", "encoder") == "libx264"  # người dùng tự chọn sau này thì giữ nguyên
    f.write_text(json.dumps({"config_version": 2, "script": {"provider": "gemini", "model": "gemini-2.5-flash"}}),
                 encoding="utf-8")
    assert Settings(f).get("script", "model") == "auto"
    print("✓ nâng cấp cấu hình")


def check_whisper_gpu(s: Settings):
    """whisper.cpp (Vulkan): gọi whisper-cli, đọc tiến độ + tên card, đọc JSON kết quả đúng định dạng whisper.cpp."""
    import threading

    from recap import whisper_gpu

    bindir = TMP / "wcpp"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "whisper-cli"
    exe.write_text(f"""#!{sys.executable}
import json, sys
a = sys.argv
out = a[a.index("-of") + 1]
assert a[a.index("-l") + 1] == "vi" and "-m" in a and "--prompt" in a
print("ggml_vulkan: Found 1 Vulkan devices:", file=sys.stderr)
print("ggml_vulkan: 0 = AMD Radeon RX 5700 XT (AMD proprietary driver) | uma: 0 | fp16: 1", file=sys.stderr)
for p in (10, 50, 100):
    print(f"whisper_print_progress_callback: progress = {{p:3d}}%", file=sys.stderr)
json.dump({{"transcription": [
    {{"offsets": {{"from": 1000, "to": 3500}}, "text": " Xin chào anh Cobb."}},
    {{"offsets": {{"from": 4000, "to": 4000}}, "text": " [BLANK_AUDIO]"}},
    {{"offsets": {{"from": 5200, "to": 8000}}, "text": " Giấc mơ này là thật sao?"}}]}},
    open(out + ".json", "w", encoding="utf-8"), ensure_ascii=False)
""", encoding="utf-8")
    exe.chmod(0o755)
    s.set("transcribe", "wcpp_dir", str(bindir))
    mdir = s.models_dir() / "whisper.cpp" / "models"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / "ggml-large-v3-turbo-q8_0.bin").write_bytes(b"0" * 11_000_000)
    wav = TMP / "a16k.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=duration=9", "-ac", "1", "-ar", "16000", str(wav)])
    logs, prog = [], []
    segs = whisper_gpu.transcribe(str(wav), 9.0, s, "large-v3-turbo", "vi", lambda m, level="info": logs.append(m),
                                  lambda p, m="": prog.append(p), threading.Event(), prompt="Inception, Cobb",
                                  work_dir=TMP)
    assert [x["text"] for x in segs] == ["Xin chào anh Cobb.", "Giấc mơ này là thật sao?"], segs
    assert segs[0]["start"] == 1.0 and segs[1]["end"] == 8.0
    assert any("RX 5700 XT" in m for m in logs) and max(prog) == 1.0, logs
    s.set("transcribe", "wcpp_dir", str(TMP / "khong-co"))
    old = whisper_gpu.tool_dir
    whisper_gpu.tool_dir = lambda _s: TMP / "khong-co-2"
    try:
        assert whisper_gpu.find_exe(s) is None or "whisper-cli" in str(whisper_gpu.find_exe(s))
    finally:
        whisper_gpu.tool_dir = old
        s.set("transcribe", "wcpp_dir", "")
    assert "whisper_gpu" in transcribe.ENGINES
    print("✓ Whisper bằng card đồ họa (whisper.cpp Vulkan): tiến độ, tên card, đọc kết quả")


def main():
    s = Settings(TMP / "s.json")
    s.set("paths", "workspace", str(TMP / "ws"))
    check_read_styles()
    check_synth_robust(s)
    check_config_migration()
    check_scenes()
    check_warmup(s)
    check_model_fallback(s)
    check_rate_limits(s)
    check_components(s)
    check_whisper_gpu(s)
    check_vision_payloads(s)
    check_tmdb(s)
    check_film_and_script(s)
    print("OK", TMP)


if __name__ == "__main__":
    main()
