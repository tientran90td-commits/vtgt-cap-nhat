"""Trang 1: chọn / tải phim nguồn."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget)

from recap.pipeline import download_video

from .player import VideoPlayer
from .widgets import Page, button, hrow, muted, scroll

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg")


class DropArea(QFrame):
    dropped = Signal(str)
    season = Signal()

    def season_request(self):
        self.season.emit()

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
        b = hrow(button("📂 Chọn 1 phim", self.browse, "primary"),
                 button("📚 Gộp nhiều tập (recap cả season)", self.season_request,
                        tip="Chọn nhiều tập phim bộ/anime -> làm 1 video recap chung"), stretch_last=False)
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
        self.drop.season.connect(self.open_season_dialog)
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
        self.excl = QLineEdit()
        self.excl.setPlaceholderText("Bỏ qua đoạn: vd 00:00-01:30, 22:10-23:40 (intro, OP/ED, cảnh không muốn dùng)")
        self.excl.editingFinished.connect(self.save_exclusions)
        il.addWidget(self.excl)
        self.lb_guard = muted("")
        il.addWidget(self.lb_guard)
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

    # ------------------------------------------------ đoạn bỏ qua / quảng cáo / season
    def save_exclusions(self):
        p = self.app.project
        if not p:
            return
        from recap.ffmpeg_utils import parse_ts

        out = []
        for part in self.excl.text().replace(";", ",").split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                sa, sb = parse_ts(a), parse_ts(b)
                if sb > sa:
                    out.append([sa, sb])
        p.exclusions = out
        p.save()
        self.refresh_guard()

    def refresh_guard(self):
        p = self.app.project
        if not p:
            return
        from recap.ffmpeg_utils import fmt_ts

        self.excl.setText(", ".join(f"{fmt_ts(a)}-{fmt_ts(b)}" for a, b, *_ in p.exclusions or []))
        parts = []
        if p.episodes:
            parts.append(f"📚 Season {len(p.episodes)} tập · tự bỏ OP/ED ({len(p.season_exclusions)} đoạn)")
        ov = p.overlays
        if ov is None:
            parts.append("🛡️ Quảng cáo chèn/logo: sẽ tự dò khi xuất video")
        else:
            n = len(ov.get("ranges", []))
            parts.append(f"🛡️ Quảng cáo chèn: {n} đoạn sẽ được tránh" if n else "🛡️ Không thấy quảng cáo chèn")
            if ov.get("watermark"):
                parts.append("🧽 Có logo cố định → sẽ che mờ")
        self.lb_guard.setText(" · ".join(parts))

    def open_season_dialog(self):
        dlg = SeasonDialog(self.app, self)
        dlg.exec()

    def set_project(self, proj):
        self.lb_name.setText(Path(proj.video).name)
        self.lb_meta.setText(proj.info.summary())
        self.player.open(proj.video)
        self.load_film()
        self.refresh_guard()
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


class SeasonDialog(QDialog):
    """Chọn nhiều tập -> gộp thành 1 nguồn -> làm 1 video recap cả season."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget

        self.app = app
        self.setWindowTitle("📚 Recap cả season - gộp nhiều tập")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Thêm các tập phim (app tự sắp xếp theo số tập trong tên file). App gộp thành 1 nguồn, giữ mốc "
                            "từng tập, rồi AI kể lại cả season theo thứ tự tập. Gộp nhanh không mã hóa lại nếu các tập "
                            "cùng định dạng (cần ổ cứng trống bằng tổng dung lượng các tập)."))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        lay.addWidget(self.list, 1)
        lay.addWidget(hrow(button("➕ Thêm tập", self.add_files, "primary"), button("📁 Thêm cả thư mục", self.add_dir),
                           button("➖ Bỏ tập đã chọn", self.remove), "stretch"))
        from .widgets import spin

        self.op = spin(0, 300, 5, " giây")
        self.op.setValue(90)
        self.ed = spin(0, 300, 5, " giây")
        self.ed.setValue(90)
        self.mins = spin(1, 120, 1, " phút")
        self.mins.setValue(15)
        f = QFormLayout()
        f.addRow("Bỏ đầu mỗi tập (OP/intro)", self.op)
        f.addRow("Bỏ cuối mỗi tập (ED/credit)", self.ed)
        f.addRow("Độ dài video recap", self.mins)
        w = QWidget()
        w.setLayout(f)
        lay.addWidget(w)
        lay.addWidget(muted("Anime thường có OP ~90 giây và ED ~90 giây. Đặt 0 nếu phim không có. Gợi ý độ dài: "
                            "khoảng 1-2 phút cho mỗi tập."))
        lay.addWidget(hrow("stretch", button("📚 Gộp && mở", self.build, "big"), button("Hủy", self.reject)))

    def _paths(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def _add(self, paths):
        from PySide6.QtWidgets import QListWidgetItem

        from recap.season import episode_title, natural_key

        allp = sorted(set(self._paths() + [str(p) for p in paths]), key=natural_key)
        self.list.clear()
        for i, p in enumerate(allp):
            it = QListWidgetItem(f"{episode_title(p, i)}  ·  {Path(p).name}")
            it.setData(Qt.UserRole, p)
            it.setToolTip(p)
            self.list.addItem(it)
        self.mins.setValue(max(self.mins.value(), min(120, int(round(len(allp) * 1.5)))))

    def add_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "Chọn các tập", "",
                                             "Video (" + " ".join("*" + e for e in VIDEO_EXT) + ")")
        if fs:
            self._add(fs)

    def add_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Thư mục chứa các tập")
        if d:
            self._add([p for p in Path(d).iterdir() if p.suffix.lower() in VIDEO_EXT])

    def remove(self):
        for it in self.list.selectedItems():
            self.list.takeItem(self.list.row(it))

    def build(self):
        files = self._paths()
        if len(files) < 2:
            QMessageBox.information(self, "Recap season", "Hãy thêm ít nhất 2 tập.")
            return
        from recap.season import build_season

        out_dir = self.app.settings.workspace() / "seasons"
        op, ed, mins = self.op.value(), self.ed.value(), self.mins.value()

        def done(meta):
            self.app.settings.set("script", "target_minutes", float(mins))
            self.app.settings.save()
            self.app.open_video(meta["video"])
            self.accept()
        self.app.run_task(build_season, files, out_dir, op, ed, on_done=done, title="Gộp các tập")
