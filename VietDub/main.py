"""VietDub Studio - mở giao diện.
Dòng lệnh: python main.py video.mp4|link [--out video_viet.mp4] [--output both|dub|sub]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def cli(argv) -> int:
    from vietdub import download
    from vietdub.config import Settings
    from vietdub.project import Project

    ap = argparse.ArgumentParser(description="VietDub Studio (dòng lệnh)")
    ap.add_argument("video", help="file video hoặc link")
    ap.add_argument("--out")
    ap.add_argument("--output", choices=["both", "dub", "sub"])
    a = ap.parse_args(argv)
    s = Settings()
    if a.output:
        s.set("video", "output", a.output)
    log = lambda m, level="info": print(m)  # noqa: E731
    prog = lambda x, m="": print(f"\r[{x * 100:5.1f}%] {m[:60]:60s}", end="", flush=True)  # noqa: E731
    video = a.video
    if download.is_url(video):
        video = str(download.download(video, s, log, prog, None))
    p = Project(video, s)
    out = p.run_all(Path(a.out) if a.out else None, log=log, progress=prog,
                    step=lambda sid, st, note="": print(f"\n== {sid}: {st} {note}"))
    print(f"\nXong: {out}")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return cli(sys.argv[1:])
    from PySide6.QtWidgets import QApplication

    from ui.style import QSS
    from ui.window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
