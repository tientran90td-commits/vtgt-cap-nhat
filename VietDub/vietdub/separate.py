"""Tách nhạc nền khỏi giọng nói bằng AI (model UVR MDX-Net, mã nguồn mở) - bản gọn chỉ cần onnxruntime + numpy.

Thuyết minh chuyên nghiệp: bỏ hẳn giọng gốc, giữ nhạc nền & tiếng động -> nghe như phim lồng tiếng thật.
- Model: UVR-MDX-NET-Inst_HQ_3 (~67 MB, tải 1 lần, kiểm tra SHA-256).
- Windows + card AMD/NVIDIA/Intel: chạy bằng DirectML (onnxruntime-directml) -> nhanh hơn CPU nhiều lần.
- Xử lý từng đoạn 5 phút (ít RAM), ghi thẳng ra FLAC (ít tốn ổ đĩa).
Thuật toán theo UVR / python-audio-separator (giấy phép MIT).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import requests

from .config import Settings, app_home
from .media import Cancelled, MediaInfo, ffmpeg_exe, no_window

MODEL = "UVR-MDX-NET-Inst_HQ_3.onnx"
MODEL_URL = f"https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/{MODEL}"
MODEL_SHA = "317554b07fe1ea5279a77f2b1520a41ea4b93432560c4ffd08792c30fddf9adc"
SR = 44100
HOP = 1024
OVERLAP = 0.25
BLOCK = 300.0      # giây mỗi lượt (giới hạn RAM)
CONTEXT = 3.0      # giây đệm 2 đầu mỗi lượt cho liền mạch


class SeparateError(RuntimeError):
    pass


def available() -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec("onnxruntime") is not None
    except (ImportError, ValueError):
        return False


def install_command() -> list[str]:
    import sys

    pkg = "onnxruntime-directml" if os.name == "nt" else "onnxruntime"
    return [sys.executable, "-m", "pip", "install", "--no-cache-dir", pkg]


def model_path(settings: Settings, log=None, progress=None, cancel=None) -> Path:
    d = app_home() / "models"
    d.mkdir(parents=True, exist_ok=True)
    f = d / MODEL
    if f.exists() and f.stat().st_size > 1_000_000:
        return f
    if log:
        log("Tải model tách nhạc nền UVR (~67 MB, một lần)...")
    tmp = f.with_suffix(".part")
    h = hashlib.sha256()
    with requests.get(MODEL_URL, stream=True, timeout=(15, 300), proxies=settings.proxies()) as r:
        if r.status_code != 200:
            raise SeparateError(f"Tải model tách nhạc lỗi HTTP {r.status_code}")
        total = int(r.headers.get("content-length") or 0)
        got = 0
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                fh.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress and total:
                    progress(0.1 * got / total, f"Tải model tách nhạc {got / 1e6:.0f}/{total / 1e6:.0f} MB")
    if h.hexdigest() != MODEL_SHA:
        tmp.unlink(missing_ok=True)
        raise SeparateError("Model tách nhạc tải về bị hỏng (sai mã kiểm tra) - thử lại.")
    tmp.replace(f)
    return f


class MDX:
    def __init__(self, model: Path, log=None):
        import numpy as np
        import onnxruntime as ort

        provs = [p for p in ("DmlExecutionProvider", "CUDAExecutionProvider") if p in ort.get_available_providers()]
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.sess = None
        for p in [*provs, "CPUExecutionProvider"]:
            try:
                self.sess = ort.InferenceSession(str(model), opts, providers=[p])
                self.provider = p
                break
            except Exception:  # noqa: BLE001 - card đồ họa không chạy được -> CPU
                continue
        if self.sess is None:
            raise SeparateError("Không chạy được model tách nhạc.")
        shape = self.sess.get_inputs()[0].shape          # [batch, 4, dim_f, dim_t]
        self.dim_f, self.dim_t = int(shape[2]), int(shape[3])
        self.n_fft = self.dim_f * 2
        self.chunk = HOP * (self.dim_t - 1)
        self.trim = self.n_fft // 2
        self.win = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(self.n_fft) / self.n_fft)).astype(np.float32)
        if log:
            log("Tách nhạc nền chạy bằng " + ("card đồ họa" if self.provider != "CPUExecutionProvider" else "CPU")
                + f" ({self.provider.replace('ExecutionProvider', '')}).")

    # --- STFT giống torch.stft(center=True, reflect, hann periodic)
    def _stft(self, x):
        import numpy as np

        pad = self.n_fft // 2
        xp = np.pad(x, ((0, 0), (pad, pad)), mode="reflect")
        n = 1 + (xp.shape[1] - self.n_fft) // HOP
        idx = np.arange(self.n_fft)[None, :] + HOP * np.arange(n)[:, None]
        spec = np.fft.rfft(xp[:, idx] * self.win, axis=-1)      # [ch, frames, bins]
        return spec.transpose(0, 2, 1)                          # [ch, bins, frames]

    def _istft(self, spec, length):
        import numpy as np

        fr = np.fft.irfft(spec.transpose(0, 2, 1), n=self.n_fft, axis=-1).astype(np.float32) * self.win
        ch, n, _ = fr.shape
        out_len = self.n_fft + HOP * (n - 1)
        y = np.zeros((ch, out_len), np.float32)
        ws = np.zeros(out_len, np.float32)
        w2 = self.win ** 2
        for i in range(n):
            y[:, i * HOP:i * HOP + self.n_fft] += fr[:, i]
            ws[i * HOP:i * HOP + self.n_fft] += w2
        y /= np.maximum(ws, 1e-8)
        pad = self.n_fft // 2
        return y[:, pad:pad + length]

    def _run(self, wave):
        """wave [2, chunk] -> nhạc nền [2, chunk]"""
        import numpy as np

        s = self._stft(wave)[:, : self.dim_f]                    # [2, dim_f, dim_t]
        x = np.stack([s[0].real, s[0].imag, s[1].real, s[1].imag])[None].astype(np.float32)
        x[:, :, :3, :] = 0
        y = self.sess.run(None, {self.sess.get_inputs()[0].name: x})[0][0]
        full = np.zeros((2, self.n_fft // 2 + 1, y.shape[-1]), np.complex64)
        full[0, : self.dim_f] = y[0] + 1j * y[1]
        full[1, : self.dim_f] = y[2] + 1j * y[3]
        return self._istft(full, wave.shape[1])

    def demix(self, mix, cancel=None, on_chunk=None):
        """mix [2, n] float32 -> nhạc nền [2, n]"""
        import numpy as np

        n = mix.shape[1]
        gen = self.chunk - 2 * self.trim
        pad = gen + self.trim - (n % gen)
        m = np.concatenate([np.zeros((2, self.trim), np.float32), mix, np.zeros((2, pad), np.float32)], 1)
        step = int((1 - OVERLAP) * self.chunk)
        res = np.zeros_like(m)
        div = np.zeros_like(m)
        starts = list(range(0, m.shape[1], step))
        for k, i in enumerate(starts):
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            end = min(i + self.chunk, m.shape[1])
            part = m[:, i:end]
            if part.shape[1] < self.chunk:
                part = np.concatenate([part, np.zeros((2, self.chunk - part.shape[1]), np.float32)], 1)
            w = np.hanning(end - i).astype(np.float32)[None]
            res[:, i:end] += self._run(part)[:, : end - i] * w
            div[:, i:end] += w
            if on_chunk:
                on_chunk(k + 1, len(starts))
        out = res / np.maximum(div, 1e-8)
        return out[:, self.trim: self.trim + n]


def _read(video: str, start: float, length: float):
    import numpy as np

    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
           "-i", video, "-vn", "-sn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    r = subprocess.run(cmd, capture_output=True, **no_window())
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).T.copy()


def background(video: str, info: MediaInfo, work: Path, settings: Settings, log, progress, cancel) -> Path:
    """Nhạc nền + tiếng động (đã bỏ giọng nói) của cả video -> background.flac (có lưu lại)."""
    import numpy as np

    out = Path(work) / "background.flac"
    meta = Path(work) / "background.json"
    st = os.stat(video)
    sig = [str(video), st.st_size, int(st.st_mtime), MODEL]
    if out.exists() and meta.exists():
        try:
            if json.loads(meta.read_text(encoding="utf-8")).get("sig") == sig:
                return out
        except ValueError:
            pass
    if not available():
        raise SeparateError("Chưa cài bộ tách nhạc (bấm 'Cài tách nhạc AI' trong mục Thuyết minh).")
    mdx = MDX(model_path(settings, log, progress, cancel), log)
    dur = info.duration
    blocks = [(s, min(BLOCK, dur - s)) for s in np.arange(0.0, dur, BLOCK)]
    tmp = out.with_suffix(".part.flac")
    enc = subprocess.Popen([ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-f", "s16le",
                            "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "flac", str(tmp)],
                           stdin=subprocess.PIPE, **no_window())
    log(f"Tách nhạc nền khỏi giọng nói ({dur / 60:.1f} phút âm thanh)...")
    try:
        for b, (s, ln) in enumerate(blocks):
            a = max(0.0, s - CONTEXT)
            mix = _read(video, a, ln + (s - a) + CONTEXT)
            if mix.shape[1] == 0:
                continue

            def tick(k, n, b=b):
                progress(0.1 + 0.9 * (b + k / n) / len(blocks), f"Tách nhạc nền {int(100 * (b + k / n) / len(blocks))}%")
            bg = mdx.demix(mix, cancel, tick)
            lo = int(round((s - a) * SR))
            seg = bg[:, lo: lo + int(round(ln * SR))]
            enc.stdin.write((np.clip(seg.T, -1, 1) * 32767).astype("<i2").tobytes())
        enc.stdin.close()
        enc.wait()
    except BaseException:
        enc.kill()
        tmp.unlink(missing_ok=True)
        raise
    if enc.returncode != 0 or not tmp.exists():
        raise SeparateError("Ghi file nhạc nền lỗi.")
    tmp.replace(out)
    meta.write_text(json.dumps({"sig": sig}), encoding="utf-8")
    progress(1.0, "Đã tách nhạc nền")
    log("✅ Đã tách nhạc nền (bỏ giọng gốc).")
    return out
