"""Tạo dữ liệu chuẩn cho test VieNeu trên máy ảo (chạy trong GitHub Actions):
VieNeu-TTS bản Python (onnx) -> âm vị, id, log(giây) của câu thử, x-vector + style của giọng nhân bản.
Ghi vào app/src/androidTest/assets (kèm sea_g2p.bin và file giọng mẫu)."""
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from huggingface_hub import hf_hub_download

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
repo = "pnnbao-ump/VieNeu-TTS-v3-Nano"
models = Path(sys.argv[2]) if len(sys.argv) > 2 else out / "models"
models.mkdir(parents=True, exist_ok=True)
for f in ["text_encoder.onnx", "duration_predictor.onnx", "vector_estimator.onnx", "codec_decoder.onnx", "config.json",
          "constants.npz", "speaker_encoder.onnx", "codec_encoder.onnx", "reference_encoder.onnx"]:
    shutil.copy(hf_hub_download(repo, f), models / f)

import sea_g2p  # noqa: E402
shutil.copy(Path(sea_g2p.__file__).parent / "sea_g2p.bin", out / "sea_g2p.bin")

from vieneu.v3nano import OnnxV3NanoEngine  # noqa: E402
from vieneu_utils.phonemize_text import phonemize_text_with_emotions  # noqa: E402

eng = OnnxV3NanoEngine(local_dir=str(models))
pkg = Path(importlib.util.find_spec("vieneu").origin).parent
voices = json.loads((pkg / "assets" / "voices_v3_nano.json").read_text(encoding="utf-8"))["presets"]
v = voices["Minh Quân"]
texts = ["Xin chào, đây là giọng đọc review phim.", "Ichigo đẩy cửa cung điện năm 2024, giá 3,5 triệu đồng."]
ph = [phonemize_text_with_emotions(t) for t in texts]
ids = eng.encode_phones(ph[0])
spk = np.asarray(v["speaker_emb"], np.float32)[None]
style = np.asarray(v["style"], np.float32)[None]
ctx = eng.s_text.run(None, {"ids": ids, "style": style})[0]
log_s = float(np.asarray(eng.s_dur.run(None, {"ctx": ctx, "ctx_mask": ids != eng.pad, "spk": spk})[0]).reshape(-1)[0])

wav_src = pkg / "assets" / "samples" / "Ly (nữ miền Bắc).wav"
shutil.copy(wav_src, out / "clone_ref.wav")
spk2, style2 = eng.prepare_reference(str(wav_src), denoise=False)
ref = {"texts": texts, "phonemes": ph, "ids": ids[0].tolist(), "log_s": log_s,
       "clone_spk": [float(x) for x in spk2], "clone_style_shape": list(style2.shape),
       "clone_style_row0": [float(x) for x in style2[0, :64]]}
(out / "vieneu_ref.json").write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
print("phonemes:", ph)
print("log_s:", log_s, "ids:", len(ref["ids"]), "style:", style2.shape)
