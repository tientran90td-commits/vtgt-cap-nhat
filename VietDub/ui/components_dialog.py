"""📦 Thư viện & model: xem đã có gì, tải từng thứ hoặc bấm 1 nút tải tất cả (giọng Ngọc Huyền, OCR mọi ngôn ngữ...)."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QGridLayout, QVBoxLayout

from vietdub import components

from .common import button, card, label, row


class ComponentsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("📦 Thư viện & model")
        self.resize(760, 520)
        lay = QVBoxLayout(self)
        c, cl = card("Tải về máy 1 lần - sau đó làm video không cần mạng")
        self.grid = QGridLayout()
        cl.addLayout(self.grid)
        lay.addWidget(c)
        from vietdub.config import app_home, disk_info

        drive, free, _t = disk_info(app_home())
        self.lb_disk = label(f"Tất cả lưu vào {app_home()} - ổ {drive} còn trống {free:.1f} GB "
                             "(cần ~5 GB để tải hết). Không ghi gì vào ổ C.", "muted")
        lay.addWidget(self.lb_disk)
        lay.addWidget(label("Cần mạng khi tải. Đang tải vẫn có thể bấm Hủy ở cửa sổ chính.", "muted"))
        lay.addStretch(1)
        lay.addWidget(row(button("⬇ Tải tất cả", self.all, "big"), "stretch", button("Đóng", self.accept)))
        self.refresh()

    def refresh(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        st = components.status()
        for r, cid in enumerate(st):
            name, size = components.ITEMS[cid]
            ok = st[cid]
            self.grid.addWidget(label(name, wrap=False), r, 0)
            self.grid.addWidget(label(size, "muted", wrap=False), r, 1)
            self.grid.addWidget(label("✅ Đã có" if ok else "⚪ Chưa có", "muted", wrap=False), r, 2)
            b = button("Tải lại" if ok else "⬇ Tải", lambda _=False, c=cid: self.one(c))
            self.grid.addWidget(b, r, 3)

    def _run(self, fn, title):
        def done(_r):
            try:
                self.refresh()
            except RuntimeError:  # hộp thoại đã đóng
                pass
            self.win.refresh_mode()
            self.win.refresh_status(force=True)
        self.win.run_task(fn, title, on_done=done)

    def one(self, cid):
        self._run(lambda log, progress, cancel: components.install(cid, self.win.settings, log, progress, cancel),
                  f"Tải {components.ITEMS[cid][0]}")

    def all(self):
        self._run(lambda log, progress, cancel: components.install_all(self.win.settings, log, progress, cancel),
                  "Tải tất cả thư viện")
