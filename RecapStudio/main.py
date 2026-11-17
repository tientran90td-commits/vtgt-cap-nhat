"""Recap Studio - mở giao diện. Dòng lệnh: python main.py phim.mp4 [--minutes 5] [--out video.mp4]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def cli(argv) -> int:
    from recapstudio.config import Settings
    from recapstudio.project import Project

    ap = argparse.ArgumentParser(description="Recap Studio (dòng lệnh)")
    ap.add_argument("video")
    ap.add_argument("--minutes", type=float)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    s = Settings()
    if a.minutes:
        s.set("ai", "minutes", a.minutes)
    p = Project(a.video, s)
    out = p.run_all(Path(a.out) if a.out else None, log=lambda m, level="info": print(m),
                    progress=lambda x, m="": print(f"\r[{x * 100:5.1f}%] {m[:60]:60s}", end="", flush=True),
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
