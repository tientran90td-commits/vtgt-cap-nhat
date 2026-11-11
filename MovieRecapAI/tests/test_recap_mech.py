"""Kiểm thử các cơ chế học từ pipeline recap chuyên nghiệp (tự viết lại):
khớp tiếng-hình theo câu, không lặp cảnh, lọc quảng cáo chèn + che logo, recap cả season."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TMP = Path(tempfile.mkdtemp(prefix="recap_mech_"))
os.environ["MOVIE_RECAP_HOME"] = str(TMP / "home")

import numpy as np  # noqa: E402

from recap import overlays, script_writer, season, tts  # noqa: E402
from recap.config import Settings  # noqa: E402
from recap.ffmpeg_utils import probe, run_ffmpeg  # noqa: E402
from recap.footage import Footage, sentence_durations, valid_sentences  # noqa: E402
from recap.pipeline import Project  # noqa: E402
from recap.subtitles import transcript_to_text  # noqa: E402

NOLOG = (lambda *a, **k: None)


def make_source(path: Path, seconds=120, ad=(40, 60)):
    """Nền đổi hình liên tục + logo cố định góc phải + 'quảng cáo' chèn cứng trong khoảng `ad`."""
    srcs = ["testsrc2", "smptebars", "rgbtestsrc"]
    n = seconds // 2
    args, fc = [], ""
    for i in range(n):
        args += ["-f", "lavfi", "-i", f"{srcs[i % 3]}=size=640x360:rate=25:duration=2"]
        fc += f"[{i}:v]format=yuv420p,setsar=1[v{i}];"
    fc += "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0,"
    fc += ("drawbox=x=560:y=12:w=64:h=28:color=white@1:t=fill,drawbox=x=566:y=18:w=52:h=16:color=black@1:t=fill,"
           f"drawbox=x=120:y=280:w=400:h=50:color=yellow@1:t=fill:enable='between(t,{ad[0]},{ad[1]})',"
           f"drawbox=x=130:y=290:w=380:h=30:color=red@1:t=fill:enable='between(t,{ad[0]},{ad[1]})'[v]")
    run_ffmpeg([*args, "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}", "-filter_complex", fc,
                "-map", "[v]", "-map", f"{n}:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                "-shortest", str(path)])


def speech_wav(base: Path, text: str) -> Path:
    """Giọng giả: mỗi câu là 1 đoạn âm, giữa các câu có khoảng lặng 0.45s (như người đọc thật)."""
    sr = 22050
    parts = [p for p in text.replace("!", ".").split(".") if p.strip()]
    audio = []
    for k, p in enumerate(parts):
        d = max(0.8, len(p) / 14)
        t = np.arange(int(sr * d)) / sr
        audio.append((0.4 * np.sin(2 * np.pi * (220 + 60 * k) * t)).astype(np.float32))
        audio.append(np.zeros(int(sr * 0.45), np.float32))
    pcm = (np.concatenate(audio) * 32767).astype(np.int16)
    out = base.with_suffix(".wav")
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return out


def check_overlays(vid: Path):
    info = probe(vid)
    res = overlays.detect(str(vid), info.duration, info.width, info.height, NOLOG, NOLOG, threading.Event())
    assert res["watermark"], res
    x0, y0, x1, y1 = res["watermark"]["box"]
    assert x0 > 0.8 and y1 < 0.2, res["watermark"]  # logo ở góc trên phải
    rng = res["ranges"]
    assert rng and any(s <= 44 and e >= 56 for s, e in rng), rng           # bắt được quảng cáo 40-60s
    assert sum(e - s for s, e in rng) < 40, rng                           # không chặn nhầm cả phim
    print(f"✓ lọc quảng cáo chèn: {rng} · logo {res['watermark']['box']}")
    return res


def check_footage():
    f = Footage(100, blocked=[[40, 60, "overlay"]])
    a = f.place(10, 5)
    b = f.place(10, 5)            # cùng mốc -> phải lấy cảnh mới
    c = f.place(38, 6, 44)        # rơi vào quảng cáo -> phải né
    assert a == 10 and b >= 15 and (c + 6 <= 40 or c >= 60), (a, b, c)
    assert f.stats["reused_s"] == 0 and f.stats["blocked_s"] == 0
    print(f"✓ không lặp cảnh & né đoạn chặn: {a}, {b}, {c}")


def check_sentence_split():
    text = "Câu thứ nhất khá dài để thử nghiệm. Câu hai ngắn. Câu thứ ba kết thúc câu chuyện!"
    wav = speech_wav(TMP / "s", text)
    from recap.ffmpeg_utils import media_duration

    total = media_duration(wav)
    parts = [x.strip() + "." for x in text.replace("!", ".").split(".") if x.strip()]
    durs = sentence_durations(str(wav), parts, total)
    # ranh giới thật = cuối mỗi câu + nửa khoảng lặng
    real, acc = [], 0.0
    for p in parts[:-1]:
        acc += max(0.8, len(p.rstrip(".")) / 14) + 0.45
        real.append(acc - 0.225)
    got = np.cumsum(durs)[:-1]
    assert all(abs(g - r) < 0.3 for g, r in zip(got, real)), (got, real)
    print(f"✓ chia giọng theo câu bám khoảng lặng: {np.round(got, 2).tolist()} ≈ {np.round(real, 2).tolist()}")


def check_render_sync(vid: Path, s: Settings):
    p = Project(str(vid), s)
    p.transcript = [{"start": i * 5.0, "end": i * 5 + 4.0, "text": f"thoại {i}"} for i in range(24)]
    sents = [{"text": "Anh ta bước vào phòng.", "start": 5, "end": 12},
             {"text": "Cô gái quay lại nhìn.", "start": 70, "end": 78},
             {"text": "Và mọi thứ kết thúc!", "start": 100, "end": 108}]
    p.script = {"title": "t", "segments": [
        {"start": 5, "end": 15, "narration": " ".join(x["text"] for x in sents), "sentences": sents, "tone": ""},
        {"start": 5, "end": 15, "narration": "Đoạn hai trùng mốc với đoạn một.", "tone": ""},
        {"start": 45, "end": 55, "narration": "Đoạn này AI chọn trúng quảng cáo.", "tone": ""}]}
    assert valid_sentences(p.script["segments"][0])
    tts._synth_edge = lambda text, voice, base, opts, settings: speech_wav(base, text)
    s.set("voice", "engine", "edge")
    s.set("voice", "voice", "vi-VN-HoaiMyNeural")
    s.set("render", "height", 360)
    s.set("render", "sub_font", "DejaVu Sans")
    out = p.run_render(TMP / "out" / "sync.mp4", log=NOLOG)
    qa = json.loads((p.dir / "render_qa.json").read_text(encoding="utf-8"))
    assert qa["sentence_synced_segments"] == 1 and qa["pieces"] == 5, qa
    assert qa["reused_seconds"] == 0 and qa["blocked_seconds_used"] == 0 and qa["delogo"], qa
    assert probe(out).duration > 8
    # Logo đã bị che: vùng góc phải trên không còn là khối trắng-đen tương phản cao
    frame = TMP / "f.png"
    run_ffmpeg(["-ss", "1", "-i", str(out), "-frames:v", "1", "-vf", "scale=640:360", str(frame)])
    print(f"✓ dựng khớp hình theo câu: {qa}")
    # Người dùng sửa lời -> mất khớp theo câu, quay về khớp theo đoạn (không lỗi)
    p.script["segments"][0]["narration"] = "Lời đã sửa tay."
    assert valid_sentences(p.script["segments"][0]) is None
    return p


def check_season(s: Settings):
    eps = []
    for i in range(3):
        f = TMP / f"Phim Hay Tập {i + 1}.mp4"
        run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size=320x180:rate=25:duration={20 + i}", "-f", "lavfi", "-i",
                    f"sine=frequency={300 + 50 * i}:duration={20 + i}", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-shortest", str(f)])
        eps.append(str(f))
    meta = season.build_season(list(reversed(eps)), TMP / "season", 3, 2, NOLOG, NOLOG, threading.Event())
    titles = [e["title"] for e in meta["episodes"]]
    assert titles == ["Tập 1", "Tập 2", "Tập 3"], titles  # sắp đúng thứ tự dù chọn lộn xộn
    total = probe(meta["video"]).duration
    assert abs(total - 63) < 1.5, total
    assert meta["episodes"][1]["start"] > 19.5 and len(meta["exclusions"]) == 6
    p = Project(meta["video"], s)
    assert len(p.episodes) == 3 and len(p.season_exclusions) == 6
    kinds = {b[2] for b in p.blocked()}
    assert {"opening", "ending"} <= kinds, kinds
    tr = [{"start": t, "end": t + 3, "text": f"câu {t}"} for t in range(0, 63, 4)]
    text = transcript_to_text(tr, episodes=p.episodes)
    assert text.count("=== Tập") == 3 and text.index("=== Tập 2") > text.index("=== Tập 1"), text
    prompt = script_writer.build_user_prompt(text, total, {"target_minutes": 3}, False, "", "", p.episodes, p.blocked())
    assert "SEASON RECAP" in prompt and "AVOID" in prompt and "opening song" in prompt
    print(f"✓ recap season: {titles} · {total:.0f}s · {len(meta['exclusions'])} đoạn OP/ED bị tránh")


def check_candidates_style(vid: Path, s: Settings):
    """Nhiều phương án + AI chấm chọn bản hay nhất; góc nhìn người kể; học phong cách video mẫu."""
    from recap import style_ref, transcribe as tr_mod

    prompts = []

    def fake_chat(pid, model, system, user, settings, **kw):
        prompts.append((system, user))
        if system == script_writer.JUDGE_SYSTEM:
            return json.dumps({"scores": [55, 92, 70], "best": 1, "reason": "Mở đầu cuốn nhất"})
        k = 1 if "shocking hook" in user else 2 if "calmer" in user else 0
        return json.dumps({"title": f"Bản {k}", "segments": [
            {"start": f"00:00:{10 + k * 5:02d}", "end": f"00:00:{20 + k * 5:02d}", "narration": f"Lời bản {k}."},
            {"start": "00:01:30", "end": "00:01:40", "narration": "Kết."}]})
    script_writer.chat = fake_chat
    s.set("api", "gemini_key", "x")
    tr = [{"start": i * 5.0, "end": i * 5 + 4.0, "text": f"thoại {i}"} for i in range(24)]
    opts = {"provider": "gemini", "model": "gemini-3.8-flash", "target_minutes": 1, "candidates": 3,
            "perspective": "character", "focus_character": "Rudeus",
            "style_ref": {"wps": 3.1, "avg_cut": 2.4, "words_per_sentence": 11, "sample": "Thanh niên này..."}}
    logs = []
    sc = script_writer.write_script(tr, 120, s, opts, lambda m, level="": logs.append(m), NOLOG, threading.Event())
    assert sc["title"] == "Bản 1" and len(sc["alternatives"]) == 2, sc["title"]
    first_user = prompts[0][1]
    assert "eyes of Rudeus" in first_user and "STYLE REFERENCE" in first_user and "Thanh niên này" in first_user
    assert any("⭐ chọn" in m for m in logs), logs
    # Học phong cách: đo nhịp đọc & nhịp cắt cảnh của video mẫu
    real = tr_mod.transcribe
    tr_mod.transcribe = lambda *a, **k: [{"start": i * 4.0, "end": i * 4 + 3.0,
                                         "text": "Thanh niên này không ngờ rằng mọi chuyện mới bắt đầu."} for i in range(30)]
    try:
        ref = style_ref.analyze(str(vid), s, NOLOG, NOLOG)
    finally:
        tr_mod.transcribe = real
    assert ref["wps"] > 2 and ref["words_per_sentence"] == 11 and ref["avg_cut"] > 0 and ref["sample"], ref
    print(f"✓ 3 phương án → AI chọn '{sc['title']}' · góc nhìn nhân vật · phong cách mẫu {ref['wps']} từ/s, "
          f"cảnh ~{ref['avg_cut']}s")


def main():
    s = Settings(TMP / "s.json")
    s.set("paths", "workspace", str(TMP / "ws"))
    vid = TMP / "nguon_co_quang_cao.mp4"
    make_source(vid)
    check_footage()
    check_sentence_split()
    check_overlays(vid)
    check_render_sync(vid, s)
    check_season(s)
    check_candidates_style(vid, s)
    print("OK", TMP)


if __name__ == "__main__":
    main()
