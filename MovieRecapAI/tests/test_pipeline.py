"""Kiểm thử end-to-end không cần mạng: video tổng hợp + phụ đề + giọng giả lập (ffmpeg sine)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from recap import llm, publish, tts  # noqa: E402
from recap.config import Settings  # noqa: E402
from recap.ffmpeg_utils import probe, run_ffmpeg  # noqa: E402
from recap.pipeline import Project  # noqa: E402
from recap.subtitles import parse_subtitle_file  # noqa: E402


def make_video(path: Path, seconds: int = 180):
    run_ffmpeg(["-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=25:duration={seconds}",
                "-f", "lavfi", "-i", f"sine=frequency=330:duration={seconds}",
                "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)])


def make_srt(path: Path, seconds: int = 180):
    lines = []
    for i in range(seconds // 6):
        st, en = i * 6 + 1, i * 6 + 4
        lines += [str(i + 1), f"00:{st // 60:02d}:{st % 60:02d},000 --> 00:{en // 60:02d}:{en % 60:02d},500",
                  f"Câu thoại số {i + 1} của nhân vật.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def fake_synth(text, voice, base, opts, settings):
    out = base.with_suffix(".wav")
    dur = max(1.0, len(text) / 15)
    run_ffmpeg(["-f", "lavfi", "-i", f"sine=frequency=660:duration={dur:.2f}", "-ac", "1", str(out)])
    return out


def main():
    tmp = Path(tempfile.mkdtemp(prefix="recap_test_"))
    os.environ["MOVIE_RECAP_HOME"] = str(tmp / "home")
    s = Settings(tmp / "settings.json")
    s.set("paths", "workspace", str(tmp / "ws"))
    s.set("paths", "output", str(tmp / "out"))
    s.set("render", "height", 360)
    s.set("render", "sub_font", "DejaVu Sans")
    s.set("render", "title_text", "Bộ phim thử nghiệm")
    s.set("render", "music", "")
    vid = tmp / "movie.mp4"
    srt = tmp / "movie.srt"
    make_video(vid)
    make_srt(srt)
    segs = parse_subtitle_file(srt)
    assert len(segs) == 30, len(segs)

    p = Project(str(vid), s)
    assert abs(p.info.duration - 180) < 1
    p.run_transcribe(subtitle_file=str(srt), engine="subtitle")
    assert len(p.transcript) == 30

    # Giả lập câu trả lời của AI
    fake_reply = json.dumps({"title": "Phim thử", "description": "mô tả", "segments": [
        {"start": "00:00:05", "end": "00:00:15", "narration": "Mở đầu, anh chàng bước vào căn phòng bí ẩn.",
         "scene": "a"},
        {"start": "00:01:00", "end": "00:01:08", "narration": "", "scene": "thoại gốc"},
        {"start": "00:02:50", "end": "00:03:30", "narration": "Cuối cùng, mọi bí mật được hé lộ. Thật bất ngờ!",
         "scene": "c"},
    ]}, ensure_ascii=False)
    llm.chat = lambda *a, **k: "```json\n" + fake_reply + "\n```"
    import recap.script_writer as sw
    sw.chat = llm.chat
    s.set("script", "provider", "gemini")
    s.set("script", "mode", "mixed")  # có đoạn giữ thoại gốc
    p.run_script()
    assert len(p.script["segments"]) == 3
    assert p.script["segments"][2]["end"] <= 180

    tts._synth_edge = fake_synth
    s.set("voice", "engine", "edge")
    s.set("voice", "voice", "vi-VN-HoaiMyNeural")
    s.set("voice", "pitch", 2)
    for aspect in ("16:9", "9:16"):
        s.set("render", "aspect", aspect)
        out = p.run_render(tmp / "out" / f"recap_{aspect.replace(':', 'x')}.mp4")
        info = probe(out)
        print(aspect, info.summary(), info.width, info.height)
        assert info.has_audio and info.has_video
        assert info.duration > 8
        assert publish.extra(out, ".srt").exists()
    # Ép thời lượng thành phẩm: mục tiêu 30s -> giãn đoạn thoại gốc, đọc chậm lại (giữ cao độ)
    from recap import editor
    pl = editor.plan_fit(100, [(1, 30), (3, 40)], 120)
    assert pl["clip_k"] == 0.5 and 1.17 < pl["tempo"] < 1.18 and abs(pl["estimate"] - 120) < 1, pl
    pl = editor.plan_fit(200, [(0, 10), (1, 60), (2, 50), (3, 10)], 100)
    assert pl["tempo"] == 1.2 and pl["drop"] == [1, 2], pl
    pl = editor.plan_fit(60, [(1, 20)], 120)
    assert pl["clip_k"] == 1.6 and pl["tempo"] == 0.88 and not pl["drop"], pl
    assert editor.plan_fit(100, [], 101)["tempo"] == 1.0
    s.set("render", "aspect", "16:9")
    s.set("render", "fit_duration", False)
    base_d = probe(p.run_render(tmp / "out" / "nofit.mp4")).duration
    s.set("script", "target_minutes", 0.5)
    s.set("render", "fit_duration", True)
    est = p.estimate_seconds()
    assert 10 < est < 25, est
    fit_d = probe(p.run_render(tmp / "out" / "fit.mp4")).duration
    assert fit_d > base_d + 3, (base_d, fit_d)
    print(f"ép thời lượng: {base_d:.1f}s → {fit_d:.1f}s (mục tiêu 30s, ước tính kịch bản {est:.1f}s)")
    # Thumbnail + tiêu đề/mô tả/mốc chương (AI giả lập)
    def meta_chat(pid, model, system, user, settings, **k):
        assert "Segments:" in user and "[0]" in user
        return json.dumps({"titles": ["Căn phòng bí ẩn và cái kết không ai ngờ", "B", "C"], "thumb_text": "CĂN PHÒNG BÍ ẨN",
                           "description": "Mô tả hấp dẫn.", "hashtags": ["#recap", "phimhay"], "tags": ["phim"],
                           "chapters": [{"seg": 0, "title": "Mở đầu"}, {"seg": 1, "title": "Thoại gốc"},
                                        {"seg": 2, "title": "Bí mật"}]}, ensure_ascii=False)
    llm.chat = meta_chat
    s.set("script", "provider", "gemini")
    s.set("render", "fit_duration", False)
    s.set("script", "target_minutes", 5)
    out = p.run_render(tmp / "out" / "pub.mp4")
    # thư mục xuất chỉ còn video thành phẩm; file phụ cất riêng
    assert sorted(f.name for f in out.parent.glob("pub*")) == ["pub.mp4"], list(out.parent.glob("pub*"))
    yt = publish.extra(out, ".youtube.txt").read_text(encoding="utf-8")
    assert "Căn phòng bí ẩn" in yt and "CĂN PHÒNG BÍ ẨN" in yt and "#phimhay" in yt, yt
    assert "Mốc thời gian" not in yt  # video 15s: chương < 10s không hợp lệ với YouTube -> bỏ
    from PIL import Image
    th = [publish.extra(out, x) for x in ("_thumb.jpg", "_thumb_doc.jpg")]
    assert publish.extra(out, ".srt").exists() and publish.extra(out, ".txt").exists()
    assert Image.open(th[0]).size == (1280, 720) and Image.open(th[1]).size == (1080, 1920)
    chs = [{"seg": 0, "title": "A"}, {"seg": 1, "title": "B"}, {"seg": 2, "title": "C"}, {"seg": 3, "title": "D"}]
    ch = publish.chapters_from(chs, [[0, 0, 40], [1, 40, 30], [2, 70, 5], [3, 75, 40]], 115)
    assert ch == [(0.0, "A"), (40.0, "B"), (70.0, "C")] or ch == [(0.0, "A"), (40.0, "B"), (75.0, "D")], ch
    m = publish.make_metadata(p.script, None, [[0, 0, 40], [1, 40, 30], [2, 70, 40]], 110, s)
    assert [c[1] for c in m["chapter_marks"]] == ["Mở đầu", "Thoại gốc", "Bí mật"], m["chapter_marks"]
    assert "00:00 Mở đầu" in publish.metadata_text(m) and "01:10 Bí mật" in publish.metadata_text(m)
    print("thumbnail + tiêu đề:", yt.splitlines()[1], "·", [x.name for x in th])
    # Chế độ không AI
    s.set("script", "provider", "none")
    s.set("script", "target_minutes", 1)
    p.run_script()
    assert len(p.script["segments"]) == 4 and all(not x["narration"] for x in p.script["segments"])
    out = p.run_render(tmp / "out" / "highlight.mp4")
    print("highlight", probe(out).summary())
    print("OK", tmp)


if __name__ == "__main__":
    main()
