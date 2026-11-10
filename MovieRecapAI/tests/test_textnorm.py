"""Kiểm thử chuẩn hóa phát âm tiếng Việt + tích hợp VieNeu-TTS (giả lập model)."""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("MOVIE_RECAP_HOME", tempfile.mkdtemp(prefix="recap_tn_"))

from recap import textnorm, tts  # noqa: E402
from recap.config import Settings  # noqa: E402
from recap.ffmpeg_utils import media_duration  # noqa: E402

CASES = {
    0: "không", 15: "mười lăm", 21: "hai mươi mốt", 24: "hai mươi tư", 105: "một trăm linh năm",
    1005: "một nghìn không trăm linh năm", 2023: "hai nghìn không trăm hai mươi ba",
    1250000: "một triệu hai trăm năm mươi nghìn", 2000000000: "hai tỷ",
}
SENTENCES = {
    "Tăng 25% lên 1.500.000đ": "Tăng hai mươi lăm phần trăm lên một triệu năm trăm nghìn đồng",
    "Lúc 10h30 ngày 12/05/2023": "Lúc mười giờ ba mươi phút ngày mười hai tháng năm năm hai nghìn không trăm hai mươi ba",
    "Phần II, thứ 2, tháng 4": "Phần hai, thứ hai, tháng tư",
    "nặng 3,5 kg, chạy 100km/h": "nặng ba phẩy năm ki lô gam, chạy một trăm ki lô mét trên giờ",
    "$5 triệu tại TP.HCM": "năm triệu đô la tại thành phố Hồ Chí Minh",
    "thắng 3-1 giai đoạn 2010-2015": "thắng ba một giai đoạn hai nghìn không trăm mười đến hai nghìn không trăm mười lăm",
    "nhiệt độ -5°C": "nhiệt độ âm năm độ C",
}


def main():
    for n, want in CASES.items():
        assert textnorm.read_number_vi(n) == want, (n, textnorm.read_number_vi(n))
    for src, want in SENTENCES.items():
        got = textnorm.prepare(src, "vi", True, [])
        assert got == want, f"\n{src}\n got: {got}\nwant: {want}"
    ent = [{"from": "Thanos", "to": "Tha-nốt"}]
    assert textnorm.prepare("thanos búng tay", "vi", True, ent) == "Tha-nốt búng tay"
    assert textnorm.prepare("Thanosss", "vi", True, ent) == "Thanosss"

    # VieNeu-TTS: giả lập gói `vieneu` để kiểm tra đường tích hợp (không cần tải model)
    import numpy as np
    import wave
    calls = {}

    class FakeVieneu:
        def __init__(self, mode="v3turbo", **kw):
            calls["mode"] = mode

        def infer(self, text, voice=None, ref_audio=None, **kw):
            calls.update(text=text, voice=voice, ref=ref_audio)
            return (0.3 * np.sin(np.arange(48000 * 2) * 2 * np.pi * 440 / 48000)).astype(np.float32)

        def save(self, audio, path):
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(48000)
                w.writeframes((audio * 32767).astype("int16").tobytes())
    real = sys.modules.get("vieneu")
    sys.modules["vieneu"] = types.SimpleNamespace(Vieneu=FakeVieneu)
    try:
        s = Settings(Path(os.environ["MOVIE_RECAP_HOME"]) / "s.json")
        out = Path(os.environ["MOVIE_RECAP_HOME"]) / "vn.wav"
        tts.synthesize("vieneu", "Năm 2019 doanh thu tăng 50%.", "Hải Đăng", out,
                       {"model": "v3turbo", "lang_code": "vi", "rate": 10}, s)
        assert calls["voice"] == "Hải Đăng" and calls["mode"] == "v3turbo"
        assert calls["text"] == "Năm hai nghìn không trăm mười chín doanh thu tăng năm mươi phần trăm.", calls["text"]
        assert 1.5 < media_duration(out) < 2.1
    finally:
        if real is not None:
            sys.modules["vieneu"] = real
        else:
            sys.modules.pop("vieneu", None)
    voices = tts.list_voices("vieneu", s)
    assert voices[0].id == "clone" and len(voices) > 5
    print("OK -", len(voices) - 1, "giọng VieNeu:", ", ".join(v.id for v in voices[1:6]), "...")


if __name__ == "__main__":
    main()
