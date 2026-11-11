"""Movie Recap AI - điểm khởi động.

    python main.py                 mở giao diện
    python main.py --cli ...       chạy không giao diện (xem --help)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _setup_streams() -> Path | None:
    """Chạy bằng pythonw.exe (run.bat) thì sys.stdout/stderr = None: mọi thanh tiến trình tải model
    (HuggingFace/tqdm) sẽ làm sập tác vụ. Ghi chúng ra file log thay thế."""
    try:
        from recap.config import app_home

        log_dir = app_home() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "app.log"
        if log_file.exists() and log_file.stat().st_size > 5_000_000:
            log_file.replace(log_dir / "app.old.log")
    except Exception:
        return None
    if sys.stdout is None or sys.stderr is None:
        fh = open(log_file, "a", encoding="utf-8", errors="replace", buffering=1)
        if sys.stdout is None:
            sys.stdout = fh
        if sys.stderr is None:
            sys.stderr = fh
    import logging

    logging.basicConfig(filename=str(log_file), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    def hook(exc_type, exc, tb):
        logging.getLogger("crash").error("Lỗi không bắt được", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = hook
    return log_file


def run_gui() -> int:
    import os

    _setup_streams()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QSplashScreen

    app = QApplication(sys.argv)
    app.setApplicationName("Movie Recap AI")
    app.setStyle("Fusion")
    icon = Path(__file__).resolve().parent / "assets" / "icon.png"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    # Màn hình chờ hiện ngay lập tức trong lúc nạp giao diện & thư viện
    pm = QPixmap(520, 300)
    pm.fill(QColor("#12141C"))
    p = QPainter(pm)
    if icon.exists():
        p.drawPixmap(30, 80, QPixmap(str(icon)).scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    p.setPen(QColor("#FFFFFF"))
    f = QFont()
    f.setPointSize(22)
    f.setBold(True)
    p.setFont(f)
    p.drawText(195, 140, "Movie Recap AI")
    f.setPointSize(11)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#9AA3B8"))
    p.drawText(197, 170, "Tóm tắt phim dài thành video ngắn bằng AI")
    p.end()
    splash = QSplashScreen(pm)
    splash.show()

    def status(msg):
        splash.showMessage(msg, Qt.AlignBottom | Qt.AlignHCenter, QColor("#B9A8FF"))
        app.processEvents()

    status("Đang nạp giao diện...")
    from gui.theme import QSS

    app.setStyleSheet(QSS)
    status("Đang nạp các công cụ xử lý video & giọng đọc...")
    from gui.main_window import MainWindow

    status("Đang mở cửa sổ chính...")
    w = MainWindow()
    w.show()
    splash.finish(w)
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
