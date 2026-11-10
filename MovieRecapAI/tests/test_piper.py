"""Kiểm thử kho giọng Piper: tải nhiều/tất cả, repo HuggingFace, nhập file, đặt tên, độ biểu cảm, giọng gợi ý."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TMP = Path(tempfile.mkdtemp(prefix="recap_piper_"))
os.environ["MOVIE_RECAP_HOME"] = str(TMP / "home")

from recap import tts  # noqa: E402
from recap.config import Settings  # noqa: E402
from recap.ffmpeg_utils import media_duration  # noqa: E402


def cfg(lang="vi_VN", n=1, spk=None):
    return json.dumps({"language": {"code": lang}, "num_speakers": n, "speaker_id_map": spk or {}})


def main():
    s = Settings(TMP / "s.json")
    s.set("paths", "models", str(TMP / "models"))
    d = tts.piper_dir(s)

    # 1) Tải nhiều giọng từ kho chính thức (giả lập mạng), bỏ qua giọng đã có
    catalog = {
        "vi_VN-vais1000-medium": {"files": {"vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx": {"size_bytes": 60e6},
                                            "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json": {"size_bytes": 5e3}}},
        "vi_VN-25hours_single-low": {"files": {"vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx": {"size_bytes": 2e7},
                                               "vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx.json": {}}},
        "en_US-libritts_r-medium": {"files": {"en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx": {},
                                              "en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json": {}}},
    }
    got = []

    def fake_dl(url, target, settings, progress=None, cancel=None, label=""):
        got.append(url)
        if target.suffix == ".json":
            n = 3 if "libritts" in target.name else 1
            target.write_text(cfg("en_US" if "en_US" in target.name else "vi_VN", n,
                                  {"p1": 0, "p2": 1, "p3": 2} if n > 1 else {}), encoding="utf-8")
        else:
            target.write_bytes(b"onnx")
    tts._download_file = fake_dl
    (d / "vi_VN-25hours_single-low.onnx").write_bytes(b"x")  # đã có sẵn
    (d / "vi_VN-25hours_single-low.onnx.json").write_text(cfg(), encoding="utf-8")
    errs = tts.piper_download_many(list(catalog), catalog, s, print, lambda p, m="": None)
    assert not errs, errs
    assert not any("25hours" in u for u in got), "giọng đã có không được tải lại"
    assert all(u.startswith("https://huggingface.co/rhasspy/piper-voices/resolve/main/") for u in got)
    assert tts.piper_installed(s) == set(catalog)
    assert tts.piper_entry_size(catalog["vi_VN-vais1000-medium"]) == 60_005_000

    # 2) Repo HuggingFace cộng đồng: liệt kê cặp .onnx + config, kể cả tên file chung chung "model.onnx"
    import requests

    class R:
        status_code = 200

        def __init__(self, js):
            self._js = js

        def json(self):
            return self._js

        def raise_for_status(self):
            pass
    sib = ["README.md", "ngochuyen/model.onnx", "ngochuyen/config.json", "yennhi/yennhi.onnx", "yennhi/yennhi.onnx.json",
           "broken/only.onnx"]
    old_get = requests.Session.get
    requests.Session.get = lambda self, url, **kw: R({"gated": "auto", "siblings": [{"rfilename": f} for f in sib]})
    try:
        items = tts.hf_list_piper("https://huggingface.co/someone/vi-piper/tree/main", s)
    finally:
        requests.Session.get = old_get
    assert [(i["onnx"], i["config"], i["local"]) for i in items] == [
        ("ngochuyen/model.onnx", "ngochuyen/config.json", "ngochuyen-model"),
        ("yennhi/yennhi.onnx", "yennhi/yennhi.onnx.json", "yennhi")], items
    assert items[0]["repo"] == "someone/vi-piper" and items[0]["gated"]
    got.clear()
    tts.hf_download_piper(items[0], s)
    assert got[0] == "https://huggingface.co/someone/vi-piper/resolve/main/ngochuyen/config.json"
    assert (d / "ngochuyen-model.onnx").exists() and (d / "ngochuyen-model.onnx.json").exists()

    # 3) Nhập file + đặt tên "Ngọc Huyền - nữ hoạt ngôn"
    src = TMP / "src"
    src.mkdir()
    (src / "huyen voice.onnx").write_bytes(b"m")
    (src / "huyen voice.onnx.json").write_text(cfg(), encoding="utf-8")
    out = tts.piper_import(str(src / "huyen voice.onnx"), None, s, "Ngọc Huyền", "Female", "nữ hoạt ngôn")
    assert out.name == "huyen_voice.onnx"
    voices = tts.list_voices("piper", s)
    nh = [v for v in voices if v.id == "huyen_voice.onnx"][0]
    assert nh.name == "Ngọc Huyền" and nh.gender == "Female" and "hoạt ngôn" in nh.label()
    multi = [v for v in voices if v.id.startswith("en_US-libritts_r-medium.onnx#")]
    assert len(multi) == 3 and multi[0].name.endswith("p1"), [v.name for v in multi]
    assert voices[0].lang.startswith("vi"), "giọng tiếng Việt lên đầu"
    tts.piper_set_meta(s, "en_US-libritts_r-medium.onnx#1", "Anna", "Female", "")
    assert any(v.name == "Anna" for v in tts.list_voices("piper", s))

    # 4) Đọc bằng Piper: tốc độ + độ biểu cảm theo cách đọc được truyền vào SynthesisConfig
    seen = {}

    class FakeCfg:
        def __init__(self, **kw):
            seen.update(kw)

    class FakeVoice:
        @staticmethod
        def load(path):
            return FakeVoice()

        def synthesize_wav(self, text, wf, syn_config=None):
            import math
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"".join(int(8000 * math.sin(i / 8)).to_bytes(2, "little", signed=True)
                                    for i in range(22050)))
    real = sys.modules.get("piper")
    sys.modules["piper"] = types.SimpleNamespace(PiperVoice=FakeVoice, SynthesisConfig=FakeCfg)
    try:
        wav = TMP / "huyen.wav"
        tts.synthesize("piper", "Xin chào cả nhà, hôm nay mình review phim siêu hay!", "huyen_voice.onnx", wav,
                       {"read_style": "lively", "rate": 0, "lang_code": "vi"}, s)
        assert seen["noise_scale"] == 0.8 and seen["noise_w_scale"] == 0.95, seen
        assert abs(seen["length_scale"] - 1 / 1.09) < 1e-6, seen  # "hoạt ngôn" đọc nhanh hơn 9%
        assert media_duration(wav) > 0.5
        tts.synthesize("piper", "Tin tức.", "en_US-libritts_r-medium.onnx#2", TMP / "n.wav",
                       {"read_style": "natural"}, s)
        assert seen["speaker_id"] == 2 and seen["noise_scale"] is None
    finally:
        if real is not None:
            sys.modules["piper"] = real
        else:
            sys.modules.pop("piper", None)

    # 5) Xóa giọng
    tts.piper_delete("huyen_voice.onnx", s)
    assert not (d / "huyen_voice.onnx").exists() and not (d / "huyen_voice.onnx.json").exists()

    # 6) Giọng gợi ý: giọng VieNeu trong preset phải có thật trong bộ giọng v3turbo
    s.set("voice", "model", "v3turbo")
    vn = {v.id for v in tts.list_voices("vieneu", s)}
    for pr in tts.VOICE_PRESETS:
        if pr["engine"] == "vieneu":
            assert pr["voice"] in vn, pr
        assert pr["read_style"] in tts.READ_STYLES
    assert tts.VOICE_PRESETS[0]["voice"] == "Ngọc Huyền" and tts.VOICE_PRESETS[0]["read_style"] == "lively"
    print("OK - kho Piper, repo HF, nhập file, đặt tên, biểu cảm, giọng gợi ý")


if __name__ == "__main__":
    main()
