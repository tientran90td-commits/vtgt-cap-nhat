"""Chuẩn bị sẵn mọi thứ khi mở app (chạy nền, không khóa giao diện).

Thứ tự: FFmpeg -> thư viện bắt buộc -> thư viện cho giọng/nhận dạng đang chọn -> model AI (Whisper, VieNeu,
giọng Piper) -> nạp sẵn model giọng đọc vào RAM -> làm nóng bộ nhớ đệm (danh sách giọng, model Gemini 'auto',
bộ mã hóa GPU). Mỗi bước lỗi thì ghi log và làm tiếp bước sau.
"""
from __future__ import annotations

from . import components
from .config import Settings
from .ffmpeg_utils import Cancelled


def plan(settings: Settings) -> list[tuple[str, str]]:
    """Danh sách (mã bước, mô tả) sẽ làm - để hiển thị."""
    s = settings
    eng = s.get("voice", "engine", "edge")
    stt = s.get("transcribe", "engine", "faster_whisper")
    steps = [("check", "Kiểm tra thành phần")]
    if s.get("ui", "auto_install", True):
        steps.append(("install", "Tự cài phần còn thiếu"))
        if stt == "faster_whisper":
            steps.append(("whisper_model", "Tải model nhận dạng thoại"))
    if s.get("ui", "preload", True):
        if eng == "vieneu":
            steps.append(("load_vieneu", "Nạp sẵn giọng VieNeu"))
        if eng == "piper":
            steps.append(("load_piper", "Nạp sẵn giọng Piper"))
        steps.append(("voices", "Nạp danh sách giọng"))
        if s.get("script", "provider") != "none":
            steps.append(("llm", "Chọn model AI viết kịch bản"))
        steps.append(("encoder", "Dò bộ mã hóa video (GPU)"))
    return steps


def run(settings: Settings, log, progress, cancel) -> dict:
    s = settings
    eng = s.get("voice", "engine", "edge")
    stt = s.get("transcribe", "engine", "faster_whisper")
    steps = plan(s)
    report: dict = {"errors": [], "done": []}

    def sub(i):
        return lambda p, m="": progress((i + max(0.0, min(1.0, p))) / len(steps), m)

    for i, (key, label) in enumerate(steps):
        if cancel.is_set():
            raise Cancelled()
        progress(i / len(steps), label)
        try:
            if key == "check":
                report["missing"] = components.missing_for(s, eng, stt)
            elif key == "install":
                req = [k for k, c in components.COMPONENTS.items() if c.get("required") and c["kind"] != "model"]
                want = list(dict.fromkeys(["ffmpeg"] + req + components.ENGINE_NEEDS.get(eng, [])
                                          + components.STT_NEEDS.get(stt, [])))
                todo = [k for k in want if not components.status(k, s)[0]]
                if todo:
                    log("⚙️ Tự cài: " + ", ".join(components.COMPONENTS[k]["name"] for k in todo))
                    errs = components.install_many(todo, s, log, sub(i), cancel)
                    report["errors"] += errs
            elif key == "whisper_model":
                if components.is_module("faster_whisper") and not components.whisper_model_ready(s):
                    log(f"⚙️ Tải sẵn model Whisper '{components.whisper_model_name(s)}' (chỉ tải 1 lần)...")
                    components.download_whisper(s, log, sub(i), cancel)
            elif key == "load_vieneu":
                if components.is_module("vieneu"):
                    from .tts import get_vieneu

                    log("⚙️ Nạp sẵn model VieNeu-TTS (lần đầu sẽ tải model)...")
                    get_vieneu(s.get("voice", "model") or "v3turbo")
                    log("✅ VieNeu-TTS sẵn sàng - bấm Nghe thử sẽ đọc ngay.")
            elif key == "load_piper":
                from .tts import get_piper, piper_dir

                name = (s.get("voice", "voice") or "").partition("#")[0]
                f = piper_dir(s) / name
                if name and f.exists() and components.is_module("piper"):
                    get_piper(f)
            elif key == "voices":
                from .tts import list_voices

                list_voices(eng, s)
            elif key == "llm":
                from .llm import PROVIDERS, resolve_model

                pid = s.get("script", "provider")
                p = PROVIDERS.get(pid, {})
                if p.get("key") and not s.get("api", p["key"]):
                    continue
                model = s.get("script", "model") or "auto"
                if model == "auto":
                    report["model"] = resolve_model(pid, "auto", s, log)
            elif key == "encoder":
                if s.get("render", "encoder", "auto") == "auto":
                    from .editor import best_encoder

                    report["encoder"] = best_encoder(log)
            report["done"].append(key)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            report["errors"].append(f"{label}: {e}")
            log(f"⚠️ {label}: {e}", level="warn")
    progress(1.0, "Sẵn sàng")
    return report
