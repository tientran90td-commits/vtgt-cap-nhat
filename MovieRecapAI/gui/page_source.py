"""Trang 1: chọn / tải phim nguồn."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QVBoxLayout)

from recap.pipeline import download_video

from .player import VideoPlayer
from .widgets import Page, button, muted

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg")


class DropArea(QFrame):
    dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(130)
        lay = QVBoxLayout(self)
        t = QLabel("🎬  Kéo & thả file phim vào đây")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size:14pt; font-weight:600;")
        s = muted("MP4, MKV, AVI, MOV, WEBM... phim dài 1-3 tiếng đều được")
        s.setAlignment(Qt.AlignCenter)
        b = button("📂 Chọn file phim trên máy", self.browse, "primary")
        lay.addStretch(1)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addWidget(b, 0, Qt.AlignCenter)
        lay.addStretch(1)

    def browse(self):
        p, _ = QFileDialog.getOpenFileName(self, "Chọn phim", "",
                                           "Video (" + " ".join("*" + e for e in VIDEO_EXT) + ");;Tất cả (*.*)")
        if p:
            self.dropped.emit(p)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self.setProperty("hover", True)
            self.style().polish(self)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.setProperty("hover", False)
        self.style().polish(self)

    def dropEvent(self, e):
        self.setProperty("hover", False)
        self.style().polish(self)
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if p:
                self.dropped.emit(p)
                break


class SourcePage(Page):
    def __init__(self, app):
        super().__init__(app, "🎬  Bước 1 · Chọn phim nguồn",
                         "Chọn phim trên máy hoặc dán link (YouTube, Facebook, TikTok, Bilibili, Dailymotion... "
                         "hơn 1000 trang nhờ yt-dlp). Sau đó bấm ⚡ để app tự làm từ A đến Z, hoặc đi từng bước.")
        top = QHBoxLayout()
        left = QVBoxLayout()
        self.drop = DropArea()
        self.drop.dropped.connect(self.app.open_video)
        left.addWidget(self.drop)

        g = QGroupBox("🌐 Tải phim từ link")
        gl = QHBoxLayout(g)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://www.youtube.com/watch?v=...")
        gl.addWidget(self.url, 1)
        gl.addWidget(button("⬇ Tải về", self.download, "primary"))
        left.addWidget(g)

        self.info = QGroupBox("ℹ️ Thông tin phim")
        il = QVBoxLayout(self.info)
        self.lb_name = QLabel("Chưa chọn phim")
        self.lb_name.setStyleSheet("font-weight:600; font-size:11pt;")
        self.lb_name.setWordWrap(True)
        self.lb_meta = muted("")
        self.lb_state = muted("")
        il.addWidget(self.lb_name)
        il.addWidget(self.lb_meta)
        il.addWidget(self.lb_state)
        left.addWidget(self.info)
        left.addStretch(1)

        right = QVBoxLayout()
        self.player = VideoPlayer()
        right.addWidget(self.player, 1)
        top.addLayout(left, 5)
        top.addLayout(right, 6)
        self.root.addLayout(top, 1)

        quick = QGroupBox("⚡ Làm nhanh")
        ql = QGridLayout(quick)
        self.lb_quick = muted("")
        ql.addWidget(self.lb_quick, 0, 0)
        self.btn_auto = button("⚡  TỰ ĐỘNG LÀM TẤT CẢ  →  XUẤT VIDEO", self.app.run_all, "big")
        ql.addWidget(self.btn_auto, 0, 1, Qt.AlignRight)
        ql.addWidget(button("Đi từng bước: Kịch bản AI →", lambda: self.app.goto(1)), 1, 1, Qt.AlignRight)
        ql.setColumnStretch(0, 1)
        self.root.addWidget(quick)

    def download(self):
        url = self.url.text().strip()
        if not url:
            return

        def done(res):
            video, sub = res
            self.app.open_video(video, subtitle=sub)
        self.app.run_task(download_video, url, self.app.settings, on_done=done, title="Tải video")

    def set_project(self, proj):
        self.lb_name.setText(Path(proj.video).name)
        self.lb_meta.setText(proj.info.summary())
        self.player.open(proj.video)
        self.refresh_state()

    def refresh_state(self):
        p = self.app.project
        if not p:
            return
        parts = [
            ("✅" if p.transcript else "⬜") + f" Lời thoại ({len(p.transcript)} câu)",
            ("✅" if p.scenes is not None else "⬜") + f" Chuyển cảnh ({len(p.scenes or [])})",
            ("✅" if p.script else "⬜") + f" Kịch bản ({len((p.script or {}).get('segments', []))} đoạn)",
        ]
        self.lb_state.setText("   ".join(parts) + f"\nThư mục dự án: {p.dir}")

    def on_show(self):
        s = self.app.settings
        from recap.llm import PROVIDERS
        from recap.tts import ENGINES

        sc, v, r = s.section("script"), s.section("voice"), s.section("render")
        self.lb_quick.setText(
            f"AI: <b>{PROVIDERS.get(sc['provider'], {}).get('name', '?')}</b> / {sc['model']} · "
            f"Độ dài: <b>{sc['target_minutes']:g} phút</b> · Ngôn ngữ: {sc['language']}<br>"
            f"Giọng: <b>{ENGINES.get(v['engine'], {}).get('name', '?')}</b> / {v['voice']} · "
            f"Khung hình: <b>{r['aspect']}</b> {r['height']}p · Phụ đề: {'bật' if r['subtitles'] else 'tắt'}")
        self.lb_quick.setTextFormat(Qt.RichText)
        self.refresh_state()
