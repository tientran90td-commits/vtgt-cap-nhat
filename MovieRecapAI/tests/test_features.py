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
    o = tts.apply_read_style("edge", dict(base, read_style="funny", tone="horror"))  # tone của đoạn được ưu tiên
    assert o["rate"] == -5 and o["pitch"] == -3, o
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
    p2.run_voices()
    assert got == [("dramatic", 3.0), ("funny", 10.0), ("serious", -4.0)], got
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


def check_config_migration():
    f = TMP / "old.json"
    f.write_text(json.dumps({"render": {"encoder": "libx264"}, "transcribe": {"model": "small"}}), encoding="utf-8")
    s = Settings(f)
    assert s.get("render", "encoder") == "auto" and s.get("transcribe", "model") == "auto"
    f.write_text(json.dumps({"config_version": 2, "render": {"encoder": "libx264"}}), encoding="utf-8")
    assert Settings(f).get("render", "encoder") == "libx264"  # người dùng tự chọn sau này thì giữ nguyên
    print("✓ nâng cấp cấu hình")


def main():
    s = Settings(TMP / "s.json")
    s.set("paths", "workspace", str(TMP / "ws"))
    check_read_styles()
    check_synth_robust(s)
    check_config_migration()
    check_components(s)
    check_vision_payloads(s)
    check_tmdb(s)
    check_film_and_script(s)
    print("OK", TMP)


if __name__ == "__main__":
    main()
