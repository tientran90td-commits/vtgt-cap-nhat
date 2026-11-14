"""Thử bản Termux trên máy tính: máy chủ web + review + dịch (AI dán tay giả lập) + giao diện (Chromium)."""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="phimviet_"))
os.environ["VIETDUB_HOME"] = str(TMP / "data")
os.environ["ANDROID_ROOT"] = "/system"          # giả lập Android: font Roboto, thử chip mã hóa của máy
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import server  # noqa: E402
from vietdub import voices  # noqa: E402
from vietdub.media import probe, run  # noqa: E402


def fake_synth(engine, text, voice, out, settings, log=None):
    """Giọng đọc giả (máy thử không vào được mạng Microsoft): tiếng bíp dài theo số chữ."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = int(48000 * max(0.6, len(text) / 14.5))
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * i / 48000))) for i in range(n)))
    return out


voices.synth = fake_synth
voices.list_voices = lambda e, s: [("vi-VN-HoaiMyNeural", "Hoài My · nữ"), ("vi-VN-NamMinhNeural", "Nam Minh · nam")]


def make_video(path: Path):
    font = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    L = ["一护推开宫殿大门。", "前方正是友哈巴赫。", "这一战不仅是为了守护。", "我不会让你失望的！"]
    srt = "".join(f"{i + 1}\n00:00:{i * 4 + 0:02d},500 --> 00:00:{i * 4 + 3:02d},300\n{L[i % 4]}\n\n" for i in range(8))
    (path.parent / "zh.srt").write_text(srt, encoding="utf-8")
    style = "Fontname=WenQuanYi Zen Hei,Fontsize=26,Outline=2" if Path(font).exists() else "Fontsize=26"
    run(["-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25", "-f", "lavfi", "-i", "sine=f=220:d=32", "-t", "32",
         "-vf", "hue=H=floor(t/2)*PI/2,drawbox=c=black:t=fill:enable='between(t,10,11.5)',"
         f"subtitles=zh.srt:force_style='{style}'", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", path.name], cwd=str(path.parent))
    return L


def call(base, path, body=None, headers=None, raw=False):
    h = {"X-PhimViet": "1", "Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers=h if body is not None else (headers or {}))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            return data if raw else json.loads(data)
    except urllib.error.HTTPError as e:
        return {"status": e.code, **json.loads(e.read() or b"{}")}


def wait(base, cond, limit=300):
    t0 = time.time()
    while time.time() - t0 < limit:
        st = call(base, "/api/state")
        if cond(st):
            return st
        time.sleep(0.5)
    raise AssertionError("hết giờ chờ: " + json.dumps(st, ensure_ascii=False)[:800])


def main():
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    out_dir = TMP / "out"
    server.SETTINGS.set("paths", "output", str(out_dir))
    vid = TMP / "Review 一护 #死神千年血战篇.mp4"
    L = make_video(vid)

    # chặn trang web lạ: thiếu header riêng / sai Host -> 403
    assert call(base, "/api/run", {}, headers={"X-PhimViet": "0"})["status"] == 403
    assert call(base, "/api/state", headers={"Host": "evil.com"})["status"] == 403

    # mở video, tự tìm khung phụ đề cứng, đọc thử
    assert call(base, "/api/open", {"path": str(vid)})["ok"]
    reg = call(base, "/api/region", {"auto": True})["region"]
    assert reg and reg[1] > 0.7, reg
    if shutil.which("tesseract"):
        txt = call(base, f"/api/ocr_test?t=5")["text"]
        assert "哈巴赫" in txt or "前方" in txt, txt  # Tesseract: đọc gần đúng là đủ (AI dịch vẫn hiểu)
    jpg = call(base, "/api/frame?t=3", raw=True)
    assert jpg[:2] == b"\xff\xd8"

    bgm = TMP / "nhac.mp3"
    run(["-f", "lavfi", "-i", "sine=f=660:d=5", "-c:a", "libmp3lame", "-b:a", "64k", str(bgm)])
    call(base, "/api/settings", {"bgm": str(bgm), "bgm_volume": 0.3, "karaoke": True, "multi_shot": True})

    # ---------------- REVIEW (không có key -> AI dán tay qua DeepSeek web)
    call(base, "/api/settings", {"mode": "recap", "target": 60, "speech": "ocr", "aspect": "9:16", "height": 540})
    assert call(base, "/api/run", {})["ok"]
    st = wait(base, lambda s: s.get("ask") or not s["busy"])
    assert st.get("ask"), st["logs"][-5:]
    p = st["ask"]["prompt"]
    assert "Review 一护" in p and "Luffy" in p and "[00:0" in p, p[:400]
    reply = json.dumps({"title": "Ichigo đối đầu Yhwach", "segments": [
        {"start": 1, "text": "Ichigo đẩy cửa cung điện, bước vào nơi Yhwach đang chờ."},
        {"start": 9, "text": "Trận chiến này không chỉ để bảo vệ thế giới, mà còn để trả thù cho mẹ của cậu, người đã bị "
                             "Yhwach cướp đi sức mạnh từ nhiều năm trước."},
        {"start": 25, "text": "Và cậu sẽ không để mọi người thất vọng."}]}, ensure_ascii=False)
    assert call(base, "/api/answer", {"id": st["ask"]["id"], "text": "Đây nhé:\n```json\n" + reply + "\n```"})["ok"]
    st = wait(base, lambda s: not s["busy"])
    assert st["status"].startswith("✅"), (st["status"], st["logs"][-8:])
    out = out_dir / st["result"]
    info = probe(out)
    assert (info.width, info.height) == (540, 960) and info.has_audio, info
    want = sum(len(t) / 14.5 + 0.35 for t in [s["text"] for s in json.loads(reply)["segments"]])
    assert abs(info.duration - want) < 1.0, (info.duration, want)
    logs = "\n".join(st["logs"]) if st.get("logs") else ""
    full = call(base, "/api/state?since=0")["logs"]
    multi = [ln for ln in full if "cảnh," in ln and "Đoạn" in ln]
    assert any(not ln.split(":", 2)[-1].strip().startswith("1 cảnh") for ln in multi), multi  # ghép nhiều cảnh
    assert any("nhạc nền" in ln for ln in full), full[-10:]
    ass = next((TMP / "data").rglob("p001.ass")).read_text(encoding="utf-8")
    assert "{\\k" in ass and "Style: Hook" in ass, ass[-400:]
    hook = next((TMP / "data").rglob("p000.ass")).read_text(encoding="utf-8")
    assert ",Hook," in hook
    # không lấy cảnh đen (giây 10 - 11.5)
    from recap import analyze, plan_pieces, shots
    sh = shots(analyze(str(vid), 8.0, 8.0), 16.0)
    assert any(y < 22 for _a, _b, y in sh), sh
    pcs = plan_pieces(sh, 9.0, 5.0, 32.0)
    assert all(not (a < 11.4 and a + l > 10.1) for a, l in pcs), pcs
    assert abs(sum(l for _a, l in pcs) - 5.0) < 0.05, pcs
    sc = call(base, "/api/script")
    assert sc["title"] == "Ichigo đối đầu Yhwach" and len(sc["segments"]) == 3
    # sửa kịch bản rồi xuất lại (không hỏi AI)
    sc["segments"][0]["text"] = "Ichigo bước vào cung điện."
    call(base, "/api/script", {"title": sc["title"], "segments": sc["segments"]})
    call(base, "/api/run", {"render_only": True})
    st = wait(base, lambda s: not s["busy"])
    assert st["status"].startswith("✅") and not st.get("ask"), st["status"]
    print(f"✓ review: lời gốc đọc từ phụ đề cứng, kịch bản qua DeepSeek web (dán tay), video dọc {info.width}x{info.height} "
          f"{info.duration:.1f}s; ghép nhiều cảnh theo điểm cắt (bỏ cảnh đen), karaoke, tiêu đề hook, nhạc nền; "
          "sửa kịch bản & xuất lại")

    # ---------------- DỊCH (dán tay, lời gốc đã có)
    call(base, "/api/settings", {"mode": "translate", "output": "both", "aspect": "source", "height": 540})
    call(base, "/api/run", {})
    st = wait(base, lambda s: s.get("ask") or not s["busy"])
    assert st.get("ask"), (st["status"], st["logs"][-6:])
    p = st["ask"]["prompt"]
    ids = [int(x.split(" |")[0]) for x in p.splitlines() if x[:1].isdigit() and " | " in x]
    assert len(ids) >= 6, p[-600:]
    vi = {str(i): f"Câu dịch số {i}" for i in ids[:-1]}  # cố tình thiếu 1 câu -> app phải hỏi lại
    call(base, "/api/answer", {"id": st["ask"]["id"], "text": json.dumps({"lines": vi}, ensure_ascii=False)})
    st = wait(base, lambda s: (s.get("ask") and s["ask"]["prompt"] != p) or not s["busy"])
    assert st.get("ask"), "câu thiếu phải được hỏi lại"
    call(base, "/api/answer", {"id": st["ask"]["id"], "text": json.dumps({"lines": {str(ids[-1]): "Câu cuối"}})})
    st = wait(base, lambda s: not s["busy"])
    assert st["status"].startswith("✅"), (st["status"], st["logs"][-8:])
    info = probe(out_dir / st["result"])
    assert (info.width, info.height) == (960, 540) and abs(info.duration - 32) < 1.0, info
    assert all(x["vi"] for x in call(base, "/api/script")["lines"])
    print(f"✓ dịch: {len(ids)} câu qua DeepSeek web (câu thiếu tự hỏi lại), thuyết minh + Vietsub {info.width}x{info.height}")

    # ---------------- giao diện trên trình duyệt điện thoại
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        chrome = next(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome"), None)
        b = pw.chromium.launch(executable_path=str(chrome) if chrome else None)
        pg = b.new_page(viewport={"width": 400, "height": 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(base + "/")
        pg.wait_for_function("document.querySelector('#vinfo').textContent.includes('Review')", timeout=15000)
        pg.wait_for_timeout(1200)
        shot = HERE / "tests" / "screens"
        shot.mkdir(exist_ok=True)
        pg.screenshot(path=str(shot / "lam_video.png"), full_page=True)
        assert pg.locator("#res").is_visible(), "video thành phẩm phải hiện để xem"
        pg.click("nav button[data-tab=script]")
        pg.wait_for_selector("#items textarea")
        n = pg.locator("#items textarea").count()
        assert n >= 6, n
        pg.screenshot(path=str(shot / "kich_ban.png"))
        pg.click("nav button[data-tab=set]")
        pg.wait_for_selector("[data-key=groq]")
        pg.screenshot(path=str(shot / "cai_dat.png"))
        # hộp dán tay hiện khi AI cần
        pg.click("nav button[data-tab=make]")
        pg.click("#mode button[data-v=recap]")
        call(base, "/api/run", {"redo": True})
        pg.wait_for_selector("#mask.on", timeout=30000)
        pg.screenshot(path=str(shot / "dan_deepseek.png"))
        pg.click("#acancel")
        wait(base, lambda s: not s["busy"])
        assert not errors, errors
        b.close()
    print("✓ giao diện điện thoại: làm video, kịch bản, cài đặt, hộp dán DeepSeek - không lỗi JS (ảnh ở tests/screens)")
    srv.shutdown()


if __name__ == "__main__":
    main()
