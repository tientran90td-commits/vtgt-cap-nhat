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
    season = Signal(list)  # nhiều tập (danh sách file) -> hộp gộp nhiều tập

    def season_request(self):
        self.season.emit([])

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        lay = QVBoxLayout(self)
        t = QLabel("🎬  Kéo & thả file phim vào đây")
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("font-size:14pt; font-weight:600;")
        s = muted("MP4, MKV, AVI, MOV, WEBM... phim dài 1-3 tiếng đều được · kéo NHIỀU tập hoặc cả THƯ MỤC → gộp thành 1 video")
        s.setAlignment(Qt.AlignCenter)
        b = hrow(button("📂 Chọn 1 phim", self.browse, "primary"),
                 button("📚 Nhiều tập → 1 video", self.season_request,
                        tip="Phim bộ / anime nhiều tập: làm 1 video recap cả bộ, hoặc nối thành 1 video dài bỏ OP/ED"),
                 stretch_last=False)
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
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()]
        videos = []
        for p in paths:
            pp = Path(p)
            if pp.is_dir():  # thả cả thư mục -> lấy mọi tập phim bên trong
                videos += [str(x) for x in pp.iterdir() if x.suffix.lower() in VIDEO_EXT]
            elif pp.suffix.lower() in VIDEO_EXT or len(paths) == 1:
                videos.append(p)
        if len(videos) > 1 or any(Path(p).is_dir() for p in paths):
            self.season.emit(videos)
        elif videos:
            self.dropped.emit(videos[0])


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
        self.btn_turbo = button("🚀 TURBO", self.app.turbo, "primary",
                                tip="Dùng thiết lập mạnh nhất của máy (card đồ họa, nhiều luồng) để làm video nhanh nhất")
        self.btn_turbo.setMinimumHeight(46)
        ql.addWidget(hrow(self.btn_turbo, self.btn_auto, stretch_last=False), 0, 1, Qt.AlignRight)
        from .widgets import sub_toggle

        ql.addWidget(hrow(sub_toggle(self.app), button("📚 Nhiều tập → 1 video", self.open_season_dialog),
                          button("Đi từng bước: Kịch bản AI →", lambda: self.app.goto(1)), stretch_last=False),
                     1, 1, Qt.AlignRight)
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
            if ov.get("hardsub"):
                parts.append(f"💬 Có phụ đề in cứng ({ov['hardsub']['ratio']:.0%} thời lượng) → sẽ xử lý theo mục "
                             "Thiết lập & xuất video › Làm sạch hình phim gốc")
        self.lb_guard.setText(" · ".join(parts))

    def open_season_dialog(self, files=None):
        dlg = SeasonDialog(self.app, self)
        if files:
            dlg._add(files)
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
            f"Khung hình: <b>{r['aspect']}</b> {r['height']}p · Phụ đề: {'bật' if r['subtitles'] else 'tắt'}"
            + (" · <b>🚀 Turbo đang bật</b>" if s.get("ui", "turbo") else ""))
        self.lb_quick.setTextFormat(Qt.RichText)
        self.refresh_state()


class SeasonDialog(QDialog):
    """Nhiều tập -> 1 video: recap tóm tắt cả bộ (AI kể lại), hoặc nối thành 1 video dài bỏ OP/ED."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QButtonGroup, QListWidget, QRadioButton

        from .widgets import spin

        self.app = app
        self.setWindowTitle("📚 Nhiều tập → 1 video")
        self.resize(780, 680)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Thêm các tập (hoặc kéo thả nhiều file / cả thư mục vào khung chọn phim). App tự sắp theo số "
                            "tập trong tên file và tự dò nhạc mở đầu (OP) / kết thúc (ED) lặp lại ở mỗi tập để bỏ đi."))
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setAcceptDrops(False)
        lay.addWidget(self.list, 1)
        self.lb_total = muted("")
        lay.addWidget(hrow(button("➕ Thêm tập", self.add_files, "primary"), button("📁 Thêm cả thư mục", self.add_dir),
                           button("➖ Bỏ tập đã chọn", self.remove), "stretch", self.lb_total))
        # kết quả muốn có
        self.r_recap = QRadioButton("📚 1 video RECAP tóm tắt cả bộ (AI xem hết các tập rồi kể lại theo thứ tự)")
        self.r_join = QRadioButton("🔗 Chỉ NỐI các tập thành 1 video dài (bỏ OP/ED, không tóm tắt)")
        grp = QButtonGroup(self)
        grp.addButton(self.r_recap)
        grp.addButton(self.r_join)
        self.r_recap.setChecked(True)
        lay.addWidget(self.r_recap)
        lay.addWidget(self.r_join)
        f = QFormLayout()
        self.auto = QCheckBox("Tự dò OP/ED bằng âm thanh (khuyên dùng - đúng cả khi tập có cảnh mở màn trước OP)")
        self.auto.setChecked(True)
        self.op = spin(0, 300, 5, " giây")
        self.op.setValue(90)
        self.ed = spin(0, 300, 5, " giây")
        self.ed.setValue(90)
        f.addRow(self.auto)
        f.addRow("Không dò được thì bỏ", hrow(QLabel("đầu"), self.op, QLabel("cuối"), self.ed, "stretch"))
        self.mins = spin(1, 180, 1, " phút")
        self.mins.setValue(15)
        self.go_all = QCheckBox("Gộp xong tự làm luôn: nhận dạng thoại → AI viết kịch bản → giọng → xuất video")
        self.go_all.setChecked(True)
        self.row_recap = hrow(self.mins, self.go_all, "stretch")
        f.addRow("Độ dài video recap", self.row_recap)
        self.exact = QCheckBox("Cắt chính xác từng giây (mã hóa lại, lâu hơn) - không tick: nối nhanh không mã hóa")
        f.addRow("Nối tập", self.exact)
        w = QWidget()
        w.setLayout(f)
        lay.addWidget(w)
        self.r_recap.toggled.connect(self._mode)
        self._mode()
        lay.addWidget(hrow("stretch", button("▶ Bắt đầu", self.build, "big"), button("Hủy", self.reject)))

    def _mode(self, *_):
        recap = self.r_recap.isChecked()
        self.row_recap.setEnabled(recap)
        self.exact.setEnabled(not recap)

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
        self.mins.setValue(max(self.mins.value(), min(180, int(round(len(allp) * 1.5)))))
        gb = sum(Path(p).stat().st_size for p in allp if Path(p).exists()) / 1e9
        self.lb_total.setText(f"{len(allp)} tập · {gb:.1f} GB")

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
            QMessageBox.information(self, "Nhiều tập → 1 video", "Hãy thêm ít nhất 2 tập.")
            return
        from recap import season

        op, ed, mins, auto = self.op.value(), self.ed.value(), self.mins.value(), self.auto.isChecked()
        s = self.app.settings
        if self.r_join.isChecked():
            from recap.editor import encoder_args
            from recap.pipeline import safe_name

            out = s.output_dir() / f"{safe_name(Path(sorted(files, key=season.natural_key)[0]).stem)}_full_{len(files)}tap.mp4"
            enc = encoder_args(s.get("render", "encoder", "auto"), int(s.get("render", "quality", 21)))

            def done_join(res):
                self.accept()
                from .widgets import reveal
                reveal(res["video"])
                QMessageBox.information(self.parent(), "Đã nối xong",
                                        f"Đã nối {len(files)} tập thành 1 video ({res['duration'] / 60:.0f} phút):\n"
                                        f"{res['video']}")
            self.app.run_task(season.join_episodes, files, out, op, ed, auto_detect=auto, exact=self.exact.isChecked(),
                              encoder=enc, on_done=done_join, title="Nối các tập")
            return
        out_dir = s.workspace() / "seasons"
        go_all = self.go_all.isChecked()

        def done(meta):
            s.set("script", "target_minutes", float(mins))
            s.save()
            self.app.open_video(meta["video"])
            self.accept()
            if go_all:
                self.app.run_all()
        self.app.run_task(season.build_season, files, out_dir, op, ed, auto_detect=auto, on_done=done,
                          title="Gộp các tập")
