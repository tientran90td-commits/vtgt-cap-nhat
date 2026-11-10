"""Trang 1: chọn / tải phim nguồn."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget)

from recap.pipeline import download_video

from .player import VideoPlayer
from .widgets import Page, button, hrow, muted, scroll

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg")


class DropArea(QFrame):
    dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
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

        fg = QGroupBox("🔍 Nhận diện phim (để AI viết đúng tên phim, tên nhân vật)")
        ff = QFormLayout(fg)
        self.f_title = QLineEdit()
        self.f_title.setPlaceholderText("Tên phim (AI tự điền, bạn sửa được)")
        self.f_year = QLineEdit()
        self.f_year.setPlaceholderText("Năm")
        self.f_year.setFixedWidth(70)
        self.f_chars = QPlainTextEdit()
        self.f_chars.setPlaceholderText("Mỗi dòng 1 nhân vật:  Tên - mô tả\nvd: Bruce Wayne - Người Dơi, tỷ phú")
        self.f_chars.setMaximumHeight(84)
        self.f_notes = QLineEdit()
        self.f_notes.setPlaceholderText("Ghi chú thêm cho AI (vd: đây là phần 2, nhân vật chính tên Minh...)")
        self.lb_film = muted("Chưa nhận diện.")
        b = self.app.binder
        self.c_ident = b.check(QCheckBox("Tự nhận diện khi làm tự động"), "script", "identify")
        self.c_vis = b.check(QCheckBox("AI xem hình ảnh các cảnh (chọn cảnh chính xác hơn)"), "script", "visual")
        ff.addRow("Phim", hrow(self.f_title, self.f_year, stretch_last=False))
        ff.addRow("Nhân vật", self.f_chars)
        ff.addRow("Ghi chú", self.f_notes)
        ff.addRow(self.lb_film)
        ff.addRow(hrow(self.c_ident, self.c_vis, "stretch"))
        ff.addRow(hrow(button("🔍 Nhận diện bằng AI", self.identify, "primary"),
                       button("👁 AI xem cảnh", self.visual), button("💾 Lưu thông tin phim", self.save_film),
                       "stretch"))
        self.film_group = fg
        left.addStretch(1)

        right = QVBoxLayout()
        self.player = VideoPlayer()
        right.addWidget(self.player, 1)
        right.addWidget(self.film_group)
        lw = QWidget()
        lw.setLayout(left)
        ls = scroll(lw)
        ls.setMinimumWidth(440)
        top.addWidget(ls, 4)
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

    # ------------------------------------------------ nhận diện phim
    def load_film(self):
        p = self.app.project
        f = (p.film if p else None) or {}
        self.f_title.setText(str(f.get("title") or ""))
        self.f_year.setText(str(f.get("year") or ""))
        self.f_chars.setPlainText("\n".join(
            f"{c.get('name')}" + (f" - {c.get('description')}" if c.get("description") else "")
            for c in f.get("characters") or [] if isinstance(c, dict) and c.get("name")))
        self.f_notes.setText(str(f.get("notes") or ""))
        if f:
            src = {"tmdb": "TMDB (chính xác)", "ai": "AI", "filename": "tên file", "user": "bạn nhập"}.get(
                f.get("source"), f.get("source", ""))
            vis = f" · AI đã xem {len(p.visual)} cảnh" if p and p.visual else ""
            self.lb_film.setText(f"Nguồn: {src} · độ tin cậy {float(f.get('confidence') or 0):.0%}{vis}"
                                 + (f"\n{f.get('premise')[:300]}" if f.get("premise") else ""))
        else:
            self.lb_film.setText("Chưa nhận diện. Bấm 🔍 hoặc để app tự làm khi bấm ⚡.")

    def save_film(self):
        p = self.app.require_project()
        if not p:
            return
        chars = []
        for ln in self.f_chars.toPlainText().splitlines():
            if ln.strip():
                name, _, desc = ln.partition(" - ")
                chars.append({"name": name.strip(), "description": desc.strip()})
        f = dict(p.film or {})
        old_title = f.get("title")
        f.update(title=self.f_title.text().strip(), year=self.f_year.text().strip(), characters=chars,
                 notes=self.f_notes.text().strip())
        if f.get("title") != old_title or not f.get("source"):
            f["source"] = "user"
            f["confidence"] = 1.0
        f.pop("whisper_hint", None)
        p.film = f
        p.save()
        self.load_film()
        self.app.log("Đã lưu thông tin phim - AI sẽ dùng khi nhận dạng thoại và viết kịch bản.")

    def identify(self):
        p = self.app.require_project()
        if not p:
            return
        if self.app.settings.get("script", "provider") == "none":
            self.app.log("Hãy chọn một AI ở bước 2 (vd Gemini) để nhận diện phim.", "warn")
            return
        self.app.run_task(p.run_identify, on_done=lambda _r: self.load_film(), title="Nhận diện phim")

    def visual(self):
        p = self.app.require_project()
        if not p:
            return
        self.app.run_task(p.run_visual, on_done=lambda _r: self.load_film(), title="AI xem cảnh phim")

    def set_project(self, proj):
        self.lb_name.setText(Path(proj.video).name)
        self.lb_meta.setText(proj.info.summary())
        self.player.open(proj.video)
        self.load_film()
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
        # chèn ký tự xuống dòng ẩn sau dấu / \\ để đường dẫn dài tự xuống dòng, không làm tràn khung
        path = str(p.dir).replace("\\", "\\\u200b").replace("/", "/\u200b")
        self.lb_state.setText("   ".join(parts) + f"\nThư mục dự án: {path}")

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
