"""Movie Recap AI - điểm khởi động.

    python main.py                 mở giao diện
    python main.py --cli ...       chạy không giao diện (xem --help)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def run_gui() -> int:
    import os

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow
    from gui.theme import QSS

    app = QApplication(sys.argv)
    app.setApplicationName("Movie Recap AI")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    icon = Path(__file__).resolve().parent / "assets" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    w = MainWindow()
    w.show()
    return app.exec()


def run_cli(argv: list[str]) -> int:
    import argparse

    from recap.config import Settings
    from recap.pipeline import Project, download_video

    ap = argparse.ArgumentParser(prog="main.py --cli", description="Tóm tắt phim không cần giao diện")
    ap.add_argument("video", help="Đường dẫn phim hoặc link URL")
    ap.add_argument("-o", "--output", help="File mp4 xuất ra")
    ap.add_argument("--subtitle", help="Dùng file phụ đề có sẵn làm lời thoại")
    ap.add_argument("--minutes", type=float, help="Độ dài video tóm tắt (phút)")
    ap.add_argument("--provider", help="gemini | anthropic | openai | groq | deepseek | openrouter | ollama | none ...")
    ap.add_argument("--model", help="Tên model AI")
    ap.add_argument("--voice", help="Giọng đọc, vd vi-VN-NamMinhNeural")
    ap.add_argument("--tts", help="Engine giọng: edge | gtts | openai | elevenlabs | gemini | google | azure | fpt | piper | sapi | xtts")
    ap.add_argument("--aspect", choices=["16:9", "9:16", "1:1", "4:5", "original"])
    a = ap.parse_args(argv)
    s = Settings()
    for sec, key, val in (("script", "target_minutes", a.minutes), ("script", "provider", a.provider),
                          ("script", "model", a.model), ("voice", "voice", a.voice), ("voice", "engine", a.tts),
                          ("render", "aspect", a.aspect)):
        if val is not None:
            s.set(sec, key, val)
    video, sub = a.video, a.subtitle
    if video.startswith(("http://", "https://")):
        video, sub2 = download_video(video, s)
        sub = sub or sub2
    p = Project(video, s)
    if sub:
        p.run_transcribe(subtitle_file=sub, engine="subtitle")

    def prog(x, m=""):
        print(f"\r[{x * 100:5.1f}%] {m[:70]:70s}", end="", flush=True)
    out = p.run_all(progress=prog, subtitle_file=sub, out_path=a.output)
    print(f"\nXong: {out}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--sapi-worker":
        from recap.tts import sapi_worker

        sys.exit(sapi_worker(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        sys.exit(run_cli(sys.argv[2:]))
    sys.exit(run_gui())
