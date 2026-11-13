"""VietDub Studio - mở giao diện.
Dòng lệnh: python main.py video.mp4|link [--out video_viet.mp4] [--output both|dub|sub]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vietdub.config import fix_std_streams, setup_env  # noqa: E402

fix_std_streams()  # pythonw.exe không có cửa sổ dòng lệnh: lời in ra của thư viện ghi vào data/logs/app.log
setup_env()  # trước mọi thư viện khác: file tạm, model, bộ nhớ đệm đều về ổ chứa app


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

    from vietdub.config import app_home, needs_migration, old_home

    if needs_migration():  # cài đặt bản cũ (ổ C) -> chép ngay để mở app đúng cài đặt; phần còn lại chuyển sau
        old_set, new_set = old_home() / "settings.json", app_home() / "settings.json"
        if old_set.exists() and not new_set.exists():
            import shutil

            shutil.copy2(old_set, new_set)

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
