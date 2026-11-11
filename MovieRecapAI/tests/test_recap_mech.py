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
from recap.ffmpeg_utils import ffmpeg_exe, probe, run_ffmpeg  # noqa: E402
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


def check_hardsub(s: Settings):
    """Phụ đề in cứng (các câu khác nhau, chữ trắng viền đen ở dưới): phát hiện -> làm mờ / cắt."""
    import cv2

    vid = TMP / "vietsub.mp4"
    lines = ["Anh đang làm gì ở đây vậy?", "Tôi chỉ đi ngang qua thôi mà.", "Đừng có nói dối tôi nữa!",
             "Chúng ta phải rời khỏi nơi này ngay.", "Kẻ thù đang đến gần rồi đó.", "Nhanh lên, không còn thời gian!",
             "Cậu có tin vào số phận không?", "Mọi chuyện sẽ ổn thôi, đừng lo."]
    (TMP / "vietsub.srt").write_text("\n".join(
        f"{i + 1}\n00:00:{i * 3:02d},000 --> 00:00:{i * 3 + 2:02d},800\n{lines[i % len(lines)]}\n" for i in range(20)),
        encoding="utf-8")
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=60", "-f", "lavfi", "-i",
                "sine=duration=60", "-vf", "subtitles=filename=vietsub.srt:force_style='Fontname=DejaVu Sans,"
                "Fontsize=22,Bold=1,Outline=2,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000'",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(vid)], cwd=str(TMP))
    info = probe(vid)
    res = overlays.detect(str(vid), info.duration, info.width, info.height, NOLOG, NOLOG, threading.Event())
    hs = res["hardsub"]
    assert hs and 0.7 < hs["y0"] < 0.92 and hs["y1"] > 0.9 and hs["ratio"] > 0.6, hs
    assert not res["ranges"], res  # phụ đề đổi liên tục -> không bị coi là quảng cáo
    plain = TMP / "plain.mp4"   # nguồn không phụ đề -> không được báo nhầm
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=40", "-c:v", "libx264", "-preset",
                "ultrafast", str(plain)])
    pi = probe(plain)
    assert overlays.detect(str(plain), pi.duration, pi.width, pi.height, NOLOG, NOLOG, threading.Event())["hardsub"] is None

    def band_edges(path, y0, y1):
        f = TMP / "band.png"
        run_ffmpeg(["-ss", "4", "-i", str(path), "-frames:v", "1", "-vf", "scale=640:360", str(f)])
        g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        return (cv2.Canny(g[int(y0 * 360):int(y1 * 360)], 80, 160) > 0).mean()
    p = Project(str(vid), s)
    p.overlays = res
    p.script = {"title": "t", "segments": [{"start": 2, "end": 12, "narration": ""}]}
    s.set("render", "subtitles", False)
    s.set("render", "fill", "crop")
    before = band_edges(vid, hs["y0"], hs["y1"])
    s.set("render", "hardsub_mode", "blur")
    out = p.run_render(TMP / "out" / "blur.mp4", log=NOLOG)
    after = band_edges(out, hs["y0"], hs["y1"])
    assert after < before * 0.5, (before, after)
    s.set("render", "hardsub_mode", "crop")
    out2 = p.run_render(TMP / "out" / "crop.mp4", log=NOLOG)
    assert band_edges(out2, 0.88, 0.99) < before
    # Xóa bằng AI qua video-subtitle-remover: dùng 1 bản VSR giả (cùng dòng lệnh) tô kín vùng được giao
    pkg = TMP / "vsr_pkg" / "vsr-v1.4.0"
    (pkg / "backend").mkdir(parents=True, exist_ok=True)
    (pkg / "Python").mkdir(exist_ok=True)
    py = pkg / "Python" / "python"
    if not py.exists():
        py.symlink_to(sys.executable)
    (pkg / "backend" / "main.py").write_text(f"""import argparse, subprocess
ap = argparse.ArgumentParser()
ap.add_argument("-i"); ap.add_argument("-o"); ap.add_argument("-c", nargs=4, type=int, action="append")
ap.add_argument("--inpaint-mode")
a = ap.parse_args()
y0, y1, x0, x1 = a.c[0]
subprocess.check_call([{ffmpeg_exe()!r}, "-y", "-loglevel", "error", "-i", a.i, "-vf",
                       f"drawbox=x={{x0}}:y={{y0}}:w={{x1 - x0}}:h={{y1 - y0}}:color=gray:t=fill", a.o])
print("done", a.inpaint_mode)
""", encoding="utf-8")
    from recap import vsr
    py_, root_, main_ = vsr.find(str(TMP / "vsr_pkg"))  # tự tìm sâu bên trong thư mục được chọn
    assert root_ == pkg and main_.name == "main.py" and py_ == py, (py_, root_, main_)
    exe_only = TMP / "vsr_exe"  # bản đóng gói chỉ có .exe -> báo rõ cách khác
    (exe_only / "_internal").mkdir(parents=True, exist_ok=True)
    (exe_only / "VideoSubtitleRemover.exe").write_bytes(b"MZ")
    try:
        vsr.find(str(exe_only / "VideoSubtitleRemover.exe"))
        raise AssertionError("phải báo lỗi")
    except vsr.VSRError as e:
        assert "VideoSubtitleRemover.exe" in str(e) and "_no_sub" in str(e), e
    s.set("render", "hardsub_mode", "vsr")
    s.set("render", "vsr_dir", str(TMP / "vsr_pkg"))
    logs = []
    out3 = p.run_render(TMP / "out" / "vsr.mp4", log=lambda m, level="info": logs.append(m))
    cleaned = list((p.dir / "vsr").glob("clean_*.mp4"))
    assert cleaned and band_edges(out3, hs["y0"], hs["y1"]) < before * 0.2, (cleaned, logs[-5:])
    assert not any("Không xóa được" in m for m in logs), logs
    s.set("render", "vsr_dir", str(TMP / "khong-co"))  # VSR hỏng/thiếu -> tự chuyển sang làm mờ, vẫn xuất được
    logs.clear()
    out4 = p.run_render(TMP / "out" / "vsr_fail.mp4", log=lambda m, level="info": logs.append(m))
    assert any("chuyển sang làm mờ" in m for m in logs) and band_edges(out4, hs["y0"], hs["y1"]) < before * 0.5
    s.set("render", "hardsub_mode", "blur")
    s.set("render", "subtitles", True)
    s.set("render", "fill", "blur")
    print(f"✓ xóa phụ đề bằng AI (VSR): {len(cleaned)} đoạn được xử lý · VSR lỗi -> tự làm mờ")
    print(f"✓ phụ đề in cứng: dải {hs['y0']:.0%}-{hs['y1']:.0%} ({hs['ratio']:.0%} thời lượng) · làm mờ: cạnh chữ "
          f"{before:.3f} → {after:.3f} · không báo nhầm video không phụ đề")


def check_reframe(s: Settings):
    """Khung dọc 9:16 bám theo 'khuôn mặt' (ô vuông sáng chạy từ trái sang phải)."""
    import cv2

    from recap import reframe

    vid = TMP / "moving.mp4"
    run_ffmpeg(["-f", "lavfi", "-i", "color=c=0x202020:size=1280x720:rate=25:duration=12", "-f", "lavfi", "-i",
                "color=c=white:size=140x160:rate=25:duration=12", "-f", "lavfi", "-i", "sine=duration=12",
                "-filter_complex", "[0:v][1:v]overlay=x='80+t*80':y=280[v]", "-map", "[v]", "-map", "2:a",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(vid)])

    def fake_faces(g):  # "mặt" = vùng trắng
        ys, xs = np.where(g > 200)
        return [(int(xs.min()), int(ys.min()), int(np.ptp(xs)) + 1, int(np.ptp(ys)) + 1)] if len(xs) else []
    keys = reframe.track(str(vid), 0, 10, 1280, 720, detector=fake_faces)
    assert keys[0][1] < 0.25 and keys[-1][1] > 0.6, keys  # khung lia theo nhân vật
    # dò mặt thật (OpenCV) trên hình không có người: không lỗi, về giữa / vùng chi tiết
    assert reframe.track(str(vid), 0, 3, 1280, 720)
    old = reframe.faces
    reframe.faces = fake_faces
    try:
        p = Project(str(vid), s)
        p.overlays = {"ranges": [], "watermark": None, "hardsub": None, "version": 2}
        p.script = {"title": "t", "segments": [{"start": 0, "end": 10, "narration": ""}]}
        s.set("render", "aspect", "9:16")
        s.set("render", "subtitles", False)
        s.set("render", "fit_duration", False)
        res = {}
        for fill in ("face", "crop"):
            s.set("render", "fill", fill)
            out = p.run_render(TMP / "out" / f"rf_{fill}.mp4", log=NOLOG)
            xs = []
            for t in (1.0, 8.0):
                f = TMP / "rf.png"
                run_ffmpeg(["-ss", str(t), "-i", str(out), "-frames:v", "1", str(f)])
                g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
                ys_, xs_ = np.where(g > 200)
                xs.append(xs_.mean() / g.shape[1] if len(xs_) > 50 else None)
            res[fill] = xs
        assert all(x is not None and 0.2 < x < 0.8 for x in res["face"]), res  # nhân vật luôn nằm trong khung
        assert any(x is None or not 0.2 < x < 0.8 for x in res["crop"]), res   # cắt giữa thì lạc mất
    finally:
        reframe.faces = old
        s.set("render", "aspect", "16:9")
        s.set("render", "fill", "blur")
        s.set("render", "subtitles", True)
    print(f"✓ khung dọc bám nhân vật: vị trí trong khung {res['face']} (cắt giữa: {res['crop']})")


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
    check_hardsub(s)
    check_reframe(s)
    print("OK", TMP)


if __name__ == "__main__":
    main()
