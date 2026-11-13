"""Cài đặt: chế độ chạy (tự động / trên máy / online), Ollama, khóa API, thư mục, cập nhật."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QLineEdit, QMessageBox, QScrollArea,
                               QVBoxLayout, QWidget)

from vietdub import VERSION, ai, hybrid, updater
from vietdub.config import MODES

from .common import PathPicker, button, card, fill, label, row

KEYS = [("gemini", "Google Gemini (miễn phí - dịch hay nhất)", "https://aistudio.google.com/apikey"),
        ("claude", "Anthropic Claude", "https://console.anthropic.com/settings/keys"),
        ("openai", "OpenAI", "https://platform.openai.com/api-keys"),
        ("groq", "Groq (Whisper + AI, có gói miễn phí)", "https://console.groq.com/keys"),
        ("openrouter", "OpenRouter (có DeepSeek miễn phí)", "https://openrouter.ai/keys"),
        ("deepseek", "DeepSeek", "https://platform.deepseek.com/api_keys"),
        ("elevenlabs", "ElevenLabs (giọng đọc)", "https://elevenlabs.io/app/settings/api-keys")]


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        b = win.binder
        self.setWindowTitle("⚙️ Cài đặt")
        self.resize(780, 820)
        outer = QVBoxLayout(self)
        inner = QWidget()
        inner.setObjectName("root")
        lay = QVBoxLayout(inner)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(inner)
        sc.viewport().setStyleSheet("background: transparent;")
        outer.addWidget(sc, 1)

        c, cl = card("⚡ Chế độ chạy")
        self.mode = b.combo(fill(QComboBox(), MODES), None, "mode")
        cl.addWidget(self.mode)
        cl.addWidget(label("⚡ Tự động: mỗi bước tự chọn chạy trên máy hay qua mạng - cái nào có sẵn & nhanh thì dùng, "
                           "lỗi / mất mạng thì tự chuyển cách kia (vd AI online hết lượt → AI trên máy; Ollama chưa mở → "
                           "AI online).\n🔒 Chỉ trên máy: không dùng mạng (Whisper + Ollama + Piper / VieNeu).\n"
                           "🌐 Ưu tiên online: dùng AI / giọng online trước, máy là dự phòng.", "muted"))
        lay.addWidget(c)

        c, cl = card("🧠 AI dịch trên máy (Ollama) - không bắt buộc nếu đã có key Gemini")
        f = QFormLayout()
        self.url = b.line(QLineEdit(), "ai", "ollama_url")
        f.addRow("Địa chỉ Ollama", self.url)
        self.lb_status = label("", "muted")
        f.addRow("Trạng thái", row(self.lb_status, button("🔄 Kiểm tra", self.check_ollama)))
        cur = hybrid.ollama_model(win.settings)
        models = dict(ai.OLLAMA_MODELS)
        if cur not in models and ":" in cur:
            models[cur] = cur
        self.model = fill(QComboBox(), models)
        self.model.setMinimumWidth(330)
        self.model.setCurrentIndex(max(0, self.model.findData(cur)))
        f.addRow("Model AI", row(self.model, button("⬇ Tải model AI", self.pull, "primary")))
        cl.addLayout(f)
        cl.addWidget(row(button("🌐 Tải Ollama (ollama.com)",
                                lambda: QDesktopServices.openUrl(QUrl("https://ollama.com/download"))),
                         label("Cài Ollama một lần, rồi bấm Tải model AI. Model 7B cần ~8GB RAM; máy yếu chọn 3B.",
                               "muted")))
        lay.addWidget(c)

        self.keys_card, kl = card("🔑 API key AI / giọng online (không bắt buộc - có thì nhanh hơn)")
        f = QFormLayout()
        for k, name, url in KEYS:
            e = b.line(QLineEdit(), "keys", k)
            e.setEchoMode(QLineEdit.Password)
            e.setPlaceholderText("dán key vào đây")
            f.addRow(name, row(e, button("Lấy key", lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u))),
                               stretch=False))
        kl.addLayout(f)
        lay.addWidget(self.keys_card)

        c, cl = card("📁 Thư mục & hệ thống")
        f = QFormLayout()
        self.out = PathPicker("dir", placeholder=str(win.settings.output_dir()))
        self.out.setText(win.settings.get("paths", "output", ""))
        self.out.changed.connect(lambda v: b.set("paths", "output", v))
        self.ff = PathPicker("file", "ffmpeg (ffmpeg.exe ffmpeg)", "(để trống = tự tìm)")
        self.ff.setText(win.settings.get("paths", "ffmpeg", ""))
        self.ff.changed.connect(lambda v: b.set("paths", "ffmpeg", v))
        f.addRow("Lưu video vào", self.out)
        self.dl = PathPicker("dir", placeholder=str(win.settings.downloads_dir()))
        self.dl.setText(win.settings.get("paths", "downloads", ""))
        self.dl.changed.connect(lambda v: b.set("paths", "downloads", v))
        f.addRow("Phim tải từ link", self.dl)
        f.addRow("FFmpeg", self.ff)
        from vietdub.config import app_home, disk_info

        drive, free, total = disk_info(app_home())
        f.addRow("Dữ liệu app", label(f"{app_home()}  ·  ổ {drive} còn {free:.1f}/{total:.0f} GB  ·  không dùng ổ C",
                                       "muted"))
        f.addRow("Proxy mạng", b.line(QLineEdit(), "net", "proxy"))
        cl.addLayout(f)
        lay.addWidget(c)

        c, cl = card(f"🔄 Cập nhật (đang dùng {VERSION})")
        cl.addWidget(b.check(QCheckBox("Tự kiểm tra bản mới khi mở app"), "update", "auto_check"))
        cl.addWidget(row(button("🔄 Kiểm tra & cập nhật ngay", self.update_now, "primary"),
                         button("↩ Quay lại bản trước", self.rollback)))
        lay.addWidget(c)
        lay.addStretch(1)
        outer.addWidget(row("stretch", button("Xong", self.accept, "primary")))
        self.mode.currentIndexChanged.connect(self._mode)
        self._mode()
        self.check_ollama()

    def _mode(self, *_):
        self.keys_card.setEnabled(self.mode.currentData() != "offline")

    def update_now(self):
        self.accept()
        self.win.check_update(silent=False)

    def rollback(self):
        if QMessageBox.question(self, "Quay lại bản trước", "Khôi phục bản sao lưu trước lần cập nhật gần nhất?") \
                != QMessageBox.Yes:
            return
        try:
            v = updater.rollback(lambda m, level="info": None)
        except updater.UpdateError as e:
            QMessageBox.information(self, "Quay lại bản trước", str(e))
            return
        if QMessageBox.question(self, "Đã khôi phục", f"Đã quay lại bản {v}. Khởi động lại app ngay?") == \
                QMessageBox.Yes:
            self.win.restart()

    def check_ollama(self):
        from .common import Bg

        self.lb_status.setText("⏳ Đang kiểm tra...")

        def done(r):
            ok, models = r
            try:
                self.lb_status.setText(("● Đang chạy · model đã có: " + (", ".join(models) or "chưa có")) if ok else
                                       ("○ Đã cài nhưng chưa mở (app sẽ tự mở khi cần)" if hybrid.ollama_exe() else
                                        "○ Chưa cài Ollama (bấm Tải Ollama, hoặc chạy install.bat)"))
            except RuntimeError:  # hộp thoại đã đóng
                pass
        Bg(lambda: hybrid.ensure_ollama(self.win.settings, wait=8), done)

    def pull(self):
        model = self.model.currentData() or "qwen2.5:7b"
        ok, _m = hybrid.ensure_ollama(self.win.settings, wait=8)
        if not ok:
            QMessageBox.warning(self, "Chưa có Ollama", "Hãy cài Ollama trước (nút Tải Ollama hoặc chạy install.bat).")
            return
        self.win.binder.set("ai", "ollama_model", model)

        def job(log, progress, cancel):
            ai.ollama_pull(model, self.win.settings, log, progress, cancel)
            return model
        self.win.run_task(job, "Tải model AI", on_done=lambda _m: self.win.refresh_status(force=True))

    def accept(self):
        m = self.model.currentData()
        if m:
            self.win.binder.set("ai", "ollama_model", m)
        self.win.settings.save()
        super().accept()
