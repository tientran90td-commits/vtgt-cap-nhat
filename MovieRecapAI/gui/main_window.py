"""Cửa sổ chính."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from recap import APP_NAME, APP_VERSION
from recap.config import Settings
from recap.ffmpeg_utils import set_ffmpeg_path
from recap.pipeline import Project

from .page_about import AboutPage
from .page_components import ComponentsPage
from .page_render import RenderPage
from .page_script import ScriptPage
from .page_settings import SettingsPage
from .page_source import SourcePage
from .page_voice import VoicePage
from .widgets import Binder, Worker, button

NAV = ["🎬   1. Video nguồn", "📝   2. Kịch bản AI", "🎙️   3. Giọng đọc", "🎛️   4. Thiết lập & xuất video",
       "🔑   API & Cài đặt", "🧩   Thành phần & sửa lỗi", "ℹ️   Hướng dẫn & mã nguồn"]
PAGE_COMPONENTS = 5


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings()
        set_ffmpeg_path(self.settings.get("paths", "ffmpeg") or None)
        self.binder = Binder(self.settings)
        # chế độ dùng AI bản web (copy & dán)
        from recap import llm as _llm

        from .web_chat import WebBridge

        self.web_bridge = WebBridge(self)
        _llm.WEB_BRIDGE = self.web_bridge
        self.project: Project | None = None
        self.pending_subtitle: str | None = None
        self.workers: list[Worker] = []
        self.main_worker: Worker | None = None
        self.setWindowTitle(f"{APP_NAME} - Tóm tắt phim dài thành video ngắn")
        self.resize(1400, 880)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(232)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 10)
        t = QLabel("🎥 Movie Recap AI")
        t.setObjectName("appTitle")
        s = QLabel(f"Tóm tắt phim bằng AI · v{APP_VERSION}")
        s.setObjectName("appSub")
        sl.addWidget(t)
        sl.addWidget(s)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        for n in NAV:
            QListWidgetItem(n, self.nav)
        sl.addWidget(self.nav, 1)
        self.lb_proj = QLabel("Chưa mở phim")
        self.lb_proj.setObjectName("appSub")
        self.lb_proj.setWordWrap(True)
        sl.addWidget(self.lb_proj)
        self.btn_update = button(f"🔄 Cập nhật · v{APP_VERSION}", self.update_dialog, tip="Kiểm tra & cài bản mới")
        sl.addWidget(self.btn_update)
        h.addWidget(side)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.stack = QStackedWidget()
        self.pages = [SourcePage(self), ScriptPage(self), VoicePage(self), RenderPage(self), SettingsPage(self),
                      ComponentsPage(self), AboutPage(self)]
        for p in self.pages:
            self.stack.addWidget(p)
        self.nav.currentRowChanged.connect(self._nav)

        self.logbox = QPlainTextEdit()
        self.logbox.setObjectName("log")
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(5000)
        from .steps import StepTracker

        self.steps = StepTracker(self)
        bottom = QWidget()
        bl0 = QVBoxLayout(bottom)
        bl0.setContentsMargins(0, 0, 0, 0)
        bl0.setSpacing(4)
        bl0.addWidget(self.steps)
        self.logbox.setMinimumHeight(80)
        bl0.addWidget(self.logbox, 1)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.stack)
        split.addWidget(bottom)
        split.setStretchFactor(0, 5)
        split.setStretchFactor(1, 1)
        split.setSizes([600, 230])
        right.addWidget(split, 1)

        bar = QFrame()
        bar.setObjectName("bottombar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(16, 8, 16, 8)
        self.status = QLabel("Sẵn sàng")
        self.status.setMinimumWidth(320)
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        self.prog.setFormat("%p%")
        self.lb_eta = QLabel("")
        self.lb_eta.setObjectName("muted")
        self.btn_cancel = button("⏹ Hủy", self.cancel, "danger")
        # tiến độ chuẩn bị nền (khi mở app)
        self.bg_box = QWidget()
        bgl = QHBoxLayout(self.bg_box)
        bgl.setContentsMargins(0, 0, 0, 0)
        self.lb_bg = QLabel("")
        self.lb_bg.setObjectName("muted")
        self.bg_prog = QProgressBar()
        self.bg_prog.setRange(0, 100)
        self.bg_prog.setFixedWidth(110)
        self.bg_prog.setTextVisible(False)
        bgl.addWidget(self.lb_bg)
        bgl.addWidget(self.bg_prog)
        self.bg_box.setVisible(False)
        self.bg_worker = None
        self._after_warmup: list = []
        self.btn_cancel.setEnabled(False)
        bl.addWidget(self.status)
        bl.addWidget(self.prog, 1)
        bl.addWidget(self.lb_eta)
        bl.addWidget(self.bg_box)
        bl.addWidget(self.btn_cancel)
        right.addWidget(bar)
        rw = QWidget()
        rw.setLayout(right)
        h.addWidget(rw, 1)
        self.nav.setCurrentRow(0)
        self.log(f"{APP_NAME} {APP_VERSION} sẵn sàng. Cấu hình: {self.settings.path}")
        if not any(self.settings.get("api", k) for k in ("gemini_key", "anthropic_key", "openai_key", "groq_key",
                                                         "deepseek_key", "openrouter_key")):
            self.log("👉 Mẹo: vào '🔑 API & Cài đặt' nhập Gemini API key miễn phí để AI viết kịch bản.", "warn")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(300, self.startup_check)
        QTimer.singleShot(5000, self.check_update_quiet)

    # ------------------------------------------------------------ chuẩn bị khi mở app
    def startup_check(self):
        """Mở app: chạy nền việc kiểm tra, tự cài phần thiếu, tải & nạp sẵn model (không khóa giao diện)."""
        from recap import warmup

        steps = warmup.plan(self.settings)
        if len(steps) <= 1 and not self.settings.get("ui", "auto_install", True):
            return self._legacy_check()
        self.bg_box.setVisible(True)
        self.lb_bg.setText("⚙️ Đang chuẩn bị...")
        w = Worker(warmup.run, self.settings)
        self.bg_worker = w
        w.log.connect(self.log)
        w.progress.connect(self._bg_progress)
        w.done.connect(self._bg_done)
        w.failed.connect(lambda m, tb: self._bg_done({"errors": [m]}))
        self.workers.append(w)
        w.start()

    def _bg_progress(self, p, msg):
        self.bg_prog.setValue(int(max(0.0, min(1.0, p)) * 100))
        if msg:
            self.lb_bg.setText(f"⚙️ {msg[:60]}")

    def _bg_done(self, report):
        w = getattr(self, "bg_worker", None)
        if w in self.workers:
            self.workers.remove(w)
        self.bg_worker = None
        errors = (report or {}).get("errors") or []
        if errors:
            self.lb_bg.setText("⚠️ Chuẩn bị xong (có lỗi - xem log / mục 🧩)")
            self.log("Một số thành phần chưa sẵn sàng - vào '🧩 Thành phần & sửa lỗi' để cài lại.", "warn")
        else:
            self.lb_bg.setText("✅ Đã sẵn sàng")
            self.log("✅ App đã chuẩn bị xong mọi thứ cần thiết.")
        from PySide6.QtCore import QTimer

        QTimer.singleShot(6000 if not errors else 20000, lambda: self.bg_box.setVisible(False))
        # các trang dùng dữ liệu vừa tải -> làm mới
        self.pages[2]._loaded_engine = None
        cur = self.stack.currentIndex()
        if cur in (2, PAGE_COMPONENTS):
            self.pages[cur].on_show()
        pending, self._after_warmup = self._after_warmup, []
        for fn in pending:
            fn()

    def _legacy_check(self):
        from recap import components

        s = self.settings

        def job(log, progress, cancel):
            return components.missing_for(s, s.get("voice", "engine"), s.get("transcribe", "engine"))

        def done(missing):
            if not missing:
                return
            names = "\n• ".join(components.COMPONENTS[k]["name"] for k in missing)
            if QMessageBox.question(self, "Thiếu thành phần",
                                    f"App cần thêm:\n• {names}\n\nTự tải & cài ngay bây giờ?") == QMessageBox.Yes:
                self.goto(PAGE_COMPONENTS)
                self.pages[PAGE_COMPONENTS].install(missing)
        self.run_task(job, on_done=done, title="Kiểm tra thành phần", quiet=True)

    def ensure(self, engine=None, stt=None, then=None, include_models=False) -> bool:
        """Kiểm tra thành phần cho engine; nếu thiếu thì hỏi để tự cài rồi chạy tiếp `then`.
        Trả True nếu đã đủ (gọi `then` ngay)."""
        from recap import components

        missing = components.missing_for(self.settings, engine, stt, include_models)
        if not missing:
            if then:
                then()
            return True
        if getattr(self, "bg_worker", None) is not None:
            # app đang tự chuẩn bị ở chế độ nền -> đợi xong rồi làm tiếp, tránh cài trùng
            self.log("⏳ App đang tự tải/cài phần cần thiết (xem thanh dưới) - sẽ làm tiếp ngay khi xong.", "warn")
            self._after_warmup.append(lambda: self.ensure(engine, stt, then, include_models))
            return False
        names = "\n• ".join(components.COMPONENTS[k]["name"] for k in missing)
        if QMessageBox.question(self, "Cần tải thêm",
                                f"Để dùng chức năng này cần:\n• {names}\n\nTự tải & cài ngay?") == QMessageBox.Yes:
            self.pages[PAGE_COMPONENTS].install(missing, then=then)
        return False

    # ------------------------------------------------------------ điều hướng
    def _nav(self, i):
        self.stack.setCurrentIndex(i)
        self.pages[i].on_show()

    def goto(self, i):
        self.nav.setCurrentRow(i)

    def refresh(self):
        self.pages[0].refresh_state()
        self.pages[0].refresh_guard()
        if self.project:
            self.lb_proj.setText(f"Đang mở:\n{Path(self.project.video).name}")

    # ------------------------------------------------------------ dự án
    def open_video(self, path: str, subtitle: str | None = None):
        try:
            self.project = Project(path, self.settings)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Không mở được phim", str(e))
            return
        self.pending_subtitle = subtitle
        sp: ScriptPage = self.pages[1]
        if subtitle:
            sp.sub_file.setText(subtitle)
            sp.stt_engine.setCurrentIndex(sp.stt_engine.findData("subtitle"))
            self.log(f"Phát hiện phụ đề kèm theo - sẽ dùng làm lời thoại: {Path(subtitle).name}")
        elif self.project.info.subtitle_streams and not self.project.transcript:
            self.log(f"Phim có {len(self.project.info.subtitle_streams)} phụ đề nhúng - có thể chọn "
                     "'Lấy phụ đề nhúng trong video' ở bước 2.")
        else:
            sib = [Path(path).with_suffix(e) for e in (".srt", ".vtt", ".ass")]
            sib = [x for x in sib if x.exists()]
            if sib and not self.project.transcript:
                sp.sub_file.setText(str(sib[0]))
                sp.stt_engine.setCurrentIndex(sp.stt_engine.findData("subtitle"))
                self.pending_subtitle = str(sib[0])
                self.log(f"Tìm thấy phụ đề cùng tên: {sib[0].name}")
        self.pages[0].set_project(self.project)
        sp.load_script()
        sp.refresh_transcript_label()
        self.refresh()
        self.log(f"Đã mở: {path}  ·  {self.project.info.summary()}")

    def require_project(self) -> Project | None:
        if not self.project:
            QMessageBox.information(self, "Chưa có phim", "Hãy chọn phim ở bước 1 trước.")
            self.goto(0)
            return None
        return self.project

    def turbo(self):
        """🚀 Turbo: áp thiết lập mạnh nhất / nhanh nhất của máy rồi làm luôn từ A đến Z."""
        from recap import turbo

        changes = turbo.plan(self.settings, self.project)
        lines = "\n".join(f"• {why}" for _s, _k, _v, why in changes if why) or "• Máy đã ở thiết lập nhanh nhất."
        box = QMessageBox(QMessageBox.Question, "🚀 Turbo - làm video nhanh nhất",
                          "Turbo dùng hết sức máy để làm video nhanh nhất:\n\n" + lines +
                          "\n\nGiọng đọc, phong cách, khung hình... của bạn giữ nguyên. Thiết lập cũ được cất lại - "
                          "bấm '↩ Bỏ Turbo' (Bước 4 → Mẫu thiết lập) để khôi phục.", parent=self)
        b_go = box.addButton("🚀 Áp dụng && làm luôn", QMessageBox.AcceptRole)
        b_set = box.addButton("Chỉ áp dụng", QMessageBox.ActionRole)
        box.addButton("Hủy", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() not in (b_go, b_set):
            return
        n = turbo.apply(self.settings, changes)
        self.binder.reload()
        self.log(f"🚀 Turbo: đã đổi {n} thiết lập sang chế độ nhanh nhất.")
        cur = self.pages[self.nav.currentRow()] if 0 <= self.nav.currentRow() < len(self.pages) else None
        if cur is not None:
            cur.on_show()
        if box.clickedButton() is b_go:
            if not self.project:
                QMessageBox.information(self, "Turbo", "Đã bật Turbo. Hãy chọn phim (hoặc nhiều tập) rồi bấm "
                                        "⚡ TỰ ĐỘNG LÀM TẤT CẢ.")
                self.goto(0)
                return
            self.run_all()

    def turbo_off(self):
        from recap import turbo

        n = turbo.restore(self.settings)
        self.binder.reload()
        self.log(f"↩ Đã bỏ Turbo, khôi phục {n} thiết lập cũ." if n else "Turbo chưa bật.")

    def run_all(self):
        p = self.require_project()
        if not p:
            return
        sp: ScriptPage = self.pages[1]
        pid = self.settings.get("script", "provider")
        from recap.llm import PROVIDERS

        k = PROVIDERS.get(pid, {}).get("key")
        if k and not self.settings.get("api", k):
            r = QMessageBox.question(self, "Chưa có API key",
                                     f"Chưa có API key cho {PROVIDERS[pid]['name']}.\n\n"
                                     "Lấy key Gemini MIỄN PHÍ ngay bây giờ (khoảng 1 phút, bấm Copy là app tự nhận)?\n"
                                     "Có key thì app chạy tự động hoàn toàn.\n\n"
                                     "(Chọn No để tự nhập key ở mục 🔑 API & Cài đặt.)")
            if r == QMessageBox.Yes:
                from .web_chat import KeyWizard

                dlg = KeyWizard(self)
                dlg.exec()
                if dlg.got:
                    sp.provider.setCurrentIndex(sp.provider.findData(dlg.got))
                    sp._provider_changed()
                    return self.run_all()
            else:
                self.goto(4)
            return
        v = self.settings.section("voice")
        if v.get("voice") == "clone" and v.get("engine") in ("vieneu", "xtts"):
            from pathlib import Path as _P

            if not v.get("xtts_ref") or not _P(v["xtts_ref"]).exists():
                QMessageBox.warning(self, "Thiếu giọng mẫu",
                                    "Bạn đang chọn '🎤 Nhân bản giọng' nhưng chưa chọn file giọng mẫu (3-8 giây).\n\n"
                                    "Vào '🎙️ Giọng đọc' chọn file mẫu, hoặc chọn một giọng có sẵn (vd ⭐ Ngọc Huyền).")
                self.goto(2)
                return
        engine = sp.stt_engine.currentData()
        sub = sp.sub_file.text() or self.pending_subtitle
        if engine == "subtitle" and not sub:
            QMessageBox.warning(self, "Thiếu phụ đề", "Bạn chọn dùng file phụ đề nhưng chưa chọn file.")
            self.goto(1)
            return

        def done(path):
            sp.load_script()
            self.pages[0].load_film()
            self.refresh()
            self.pages[3].finished(path)

        def go():
            self.run_task(p.run_all, on_done=done, title="Tự động làm tất cả", subtitle_file=sub)
        need_stt = None if p.transcript else engine
        self.ensure(self.settings.get("voice", "engine"), need_stt, then=go)

    # ------------------------------------------------------------ tác vụ nền
    def run_task(self, fn, *args, on_done=None, on_fail=None, title="", quiet=False, **kwargs):
        if not quiet and self.main_worker is not None:
            QMessageBox.information(self, "Đang bận", "Đang chạy một tác vụ khác, hãy đợi hoặc bấm Hủy.")
            return None
        w = Worker(fn, *args, **kwargs)
        w.log.connect(self.log)
        if not quiet:
            self.main_worker = w
            self._t0 = time.time()
            w.progress.connect(self._progress)
            self.status.setText(f"⏳ {title}...")
            self.prog.setValue(0)
            self.btn_cancel.setEnabled(True)
            self.log(f"▶ {title}")

        def finish():
            if w in self.workers:
                self.workers.remove(w)
            if self.main_worker is w:
                self.main_worker = None
                self.btn_cancel.setEnabled(False)
                self.lb_eta.setText("")

        def ok(res):
            finish()
            if not quiet:
                self.steps.finish()
                self.status.setText(f"✅ {title} - xong ({time.time() - self._t0:.0f}s)")
                self.prog.setValue(1000)
            if on_done:
                on_done(res)

        def bad(msg, tb):
            finish()
            if not quiet:
                self.steps.fail_running(msg)
            if tb:
                self.log(tb, "debug")
            self.log(f"❌ {title}: {msg}", "error")
            if on_fail:
                on_fail(msg)
            elif not quiet:
                self.status.setText(f"❌ {title} lỗi")
                if msg != "Đã hủy.":
                    QMessageBox.critical(self, f"Lỗi - {title}", msg[:2000])
                else:
                    self.status.setText("⏹ Đã hủy")
        w.done.connect(ok)
        w.failed.connect(bad)
        self.workers.append(w)
        w.start()
        return w

    def _progress(self, p, msg):
        self.prog.setValue(int(max(0.0, min(1.0, p)) * 1000))
        if msg:
            self.status.setText(f"⏳ {msg}")
        el = time.time() - self._t0
        if p > 0.02 and el > 5:
            rem = el / p - el
            self.lb_eta.setText(f"còn ~{int(rem // 60)}:{int(rem % 60):02d}")

    def cancel(self):
        if self.main_worker:
            self.main_worker.cancel.set()
            self.status.setText("⏹ Đang hủy...")

    def log(self, msg, level="info"):
        if level == "step":
            text = self.steps.event_msg(str(msg))
            if not text:
                return
            msg, level = text, ("error" if text.startswith("❌") else "info")
        if level == "debug":
            if not self.settings.get("ui", "debug", False):
                return
        color = {"warn": "#FFC857", "error": "#FF6B81", "debug": "#6C7489"}.get(level)
        ts = time.strftime("%H:%M:%S")
        text = str(msg).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        if color:
            self.logbox.appendHtml(f"<span style='color:#6C7489'>{ts}</span> <span style='color:{color}'>{text}</span>")
        else:
            self.logbox.appendHtml(f"<span style='color:#6C7489'>{ts}</span> {text}")

    # ------------------------------------------------------------ cập nhật tool
    def check_update_quiet(self):
        from recap import updater

        def done(info):
            self._update_info = info
            if info.get("newer"):
                self.btn_update.setText(f"🆕 Có bản mới v{info['latest']} - Cập nhật")
                self.btn_update.setObjectName("primary")
                self.btn_update.style().polish(self.btn_update)
                self.log(f"🆕 Đã có bản mới v{info['latest']} - bấm nút 'Cập nhật' ở góc trái dưới.", "warn")
        self.run_task(lambda log, progress, cancel: updater.check(self.settings), on_done=done,
                      on_fail=lambda m: None, title="Kiểm tra bản mới", quiet=True)

    def update_dialog(self):
        from .update_dialog import UpdateDialog

        UpdateDialog(self).exec()

    def closeEvent(self, e):
        for w in list(self.workers):
            w.cancel.set()
        for w in list(self.workers):
            w.wait(3000)
        self.settings.save()
        super().closeEvent(e)
