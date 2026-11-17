"""📤 Đăng video: ảnh bìa, tiêu đề, mô tả, hashtag - sao chép 1 chạm, lưu ảnh bìa, làm lại."""
from __future__ import annotations

import shutil

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLineEdit, QMessageBox,
                               QPlainTextEdit, QSizePolicy)

from vietdub import publish

from .common import button, card, label, row


class PublishDialog(QDialog):
    def __init__(self, win, project):
        super().__init__(win)
        self.win, self.p = win, project
        self.setWindowTitle("📤 Đăng video")
        self.resize(980, 640)
        lay = QHBoxLayout(self)

        c, cl = card("🖼️ Ảnh bìa")
        self.thumb = label("", "thumb")
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setMinimumSize(400, 300)
        cl.addWidget(self.thumb, 1)
        cl.addWidget(row(button("💾 Lưu ảnh bìa...", self.save_thumb), button("🖼️ Mở", self.open_thumb), "stretch"))
        lay.addWidget(c, 1)

        c, cl = card("📝 Tiêu đề · mô tả · hashtag")
        f = QFormLayout()
        self.titles = QComboBox()
        self.titles.setEditable(True)
        self.desc = QPlainTextEdit()
        self.tags = QLineEdit()
        self.kw = QLineEdit()
        self.titles.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        b1 = button("📋", lambda: self.copy(self.titles.currentText()), tip="Sao chép tiêu đề")
        b2 = button("📋", lambda: self.copy(self.tags.text()), tip="Sao chép hashtag")
        for x in (b1, b2):
            x.setFixedWidth(44)
        f.addRow("Tiêu đề", row(self.titles, b1, stretch=False))
        f.addRow("Mô tả", self.desc)
        f.addRow("Hashtag", row(self.tags, b2, stretch=False))
        f.addRow("Từ khóa", self.kw)
        cl.addLayout(f, 1)
        cl.addWidget(label("Gợi ý: TikTok/Shorts dùng tiêu đề ngắn + 3-5 hashtag; YouTube dán cả mô tả.", "muted"))
        cl.addWidget(row(button("📋 Sao chép tất cả", self.copy_all, "primary"),
                         button("🔄 Làm lại bằng AI", self.redo), "stretch", button("Đóng", self.accept)))
        lay.addWidget(c, 1)
        self.load()

    def load(self):
        info = self.p.publish_info or publish.fallback_info({"title": self.p.title, "segments": []}, self.p.title)
        self.titles.clear()
        self.titles.addItems(info.get("titles", []))
        self.desc.setPlainText(info.get("description", ""))
        self.tags.setText(" ".join(info.get("hashtags", [])))
        self.kw.setText(", ".join(info.get("tags", [])))
        if self.p.thumbnail.exists():
            pm = QPixmap(str(self.p.thumbnail))
            self.thumb.setPixmap(pm.scaled(440, 440, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.thumb.setText("Chưa có ảnh bìa\n(bấm 🔄 Làm lại bằng AI)")

    def accept(self):
        if self.titles.count() or self.desc.toPlainText().strip():  # giữ lại chỗ bạn đã sửa
            titles = [self.titles.currentText()] + [self.titles.itemText(i) for i in range(self.titles.count())]
            info = {"titles": [t for t in dict.fromkeys(titles) if t.strip()],
                    "description": self.desc.toPlainText().strip(), "hashtags": self.tags.text().split(),
                    "tags": [t.strip() for t in self.kw.text().split(",") if t.strip()],
                    "source": (self.p.publish_info or {}).get("source") or self.p.title}
            self.p.publish_info = info
            publish.save_json(self.p.dir / "publish" / "info.json", info)
        super().accept()

    def copy(self, text: str):
        QGuiApplication.clipboard().setText(text)
        self.win.lb_status.setText("📋 Đã sao chép")

    def copy_all(self):
        src = (self.p.publish_info or {}).get("source") or self.p.title
        self.copy(f"{self.titles.currentText()}\n\n{self.desc.toPlainText().strip()}\n\nNguồn video gốc: {src}"
                  f"\n\n{self.tags.text().strip()}")

    def save_thumb(self):
        if not self.p.thumbnail.exists():
            return
        base = (self.win.last_output.with_suffix(".jpg") if self.win.last_output else
                self.win.settings.output_dir() / "thumbnail.jpg")
        f, _ = QFileDialog.getSaveFileName(self, "Lưu ảnh bìa", str(base), "Ảnh (*.jpg)")
        if f:
            shutil.copy2(self.p.thumbnail, f)

    def open_thumb(self):
        if self.p.thumbnail.exists():
            publish.open_path(self.p.thumbnail)

    def redo(self):
        if not self.p.lines:
            QMessageBox.information(self, "Chưa dịch", "Hãy dịch video trước.")
            return
        self.win.run_task(lambda log, progress, cancel: self.p.run_publish(log, cancel), "Tạo ảnh bìa & tiêu đề",
                          on_done=lambda _r: self.load())
