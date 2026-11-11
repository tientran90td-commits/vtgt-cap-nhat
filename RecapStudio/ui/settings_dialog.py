"""Cài đặt: chế độ chạy trên máy / dùng API, Ollama, khóa API, thư mục."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QFormLayout, QLineEdit, QMessageBox, QVBoxLayout

from recapstudio import ai

from .common import PathPicker, button, card, fill, label, row

KEYS = [("gemini", "Google Gemini", "https://aistudio.google.com/apikey"),
        ("claude", "Anthropic Claude", "https://console.anthropic.com/settings/keys"),
        ("openai", "OpenAI", "https://platform.openai.com/api-keys"),
        ("groq", "Groq (Whisper + AI, có gói miễn phí)", "https://console.groq.com/keys"),
        ("openrouter", "OpenRouter", "https://openrouter.ai/keys"),
        ("deepseek", "DeepSeek", "https://platform.deepseek.com/api_keys"),
        ("elevenlabs", "ElevenLabs (giọng đọc)", "https://elevenlabs.io/app/settings/api-keys")]


class SettingsDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        b = win.binder
        self.setWindowTitle("⚙️ Cài đặt")
        self.resize(760, 760)
        lay = QVBoxLayout(self)

        c, cl = card("🔒 Chế độ chạy")
        self.offline = b.check(QCheckBox("Chỉ dùng trên máy (offline) - không cần API key, không cần mạng khi làm phim"),
                               None, "offline")
        cl.addWidget(self.offline)
        cl.addWidget(label("Offline: lời thoại = phụ đề có sẵn hoặc Whisper trên máy (card đồ họa/CPU) · kịch bản = "
                           "Ollama (AI chạy trên máy) · giọng = VieNeu / Piper / Windows. Lần đầu cần mạng để tải model "
                           "(một lần). Bỏ tick để dùng thêm AI/giọng online bằng API key.", "muted"))
        lay.addWidget(c)

        c, cl = card("🧠 AI trên máy (Ollama)")
        f = QFormLayout()
        self.url = b.line(QLineEdit(), "ai", "ollama_url")
        f.addRow("Địa chỉ Ollama", self.url)
        self.lb_status = label("", "muted")
        f.addRow("Trạng thái", row(self.lb_status, button("🔄 Kiểm tra", self.check_ollama)))
        cur = win.settings.get("ai", "model") or "qwen2.5:7b"
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

        self.keys_card, kl = card("🔑 API key (chỉ khi tắt chế độ offline)")
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
        f.addRow("FFmpeg", self.ff)
        f.addRow("Proxy mạng", b.line(QLineEdit(), "net", "proxy"))
        cl.addLayout(f)
        lay.addWidget(c)
        lay.addStretch(1)
        lay.addWidget(row("stretch", button("Xong", self.accept, "primary")))
        self.offline.toggled.connect(self._mode)
        self._mode()
        self.check_ollama()

    def _mode(self, *_):
        self.keys_card.setEnabled(not self.offline.isChecked())

    def check_ollama(self):
        ok, models = ai.ollama_status(self.win.settings)
        self.lb_status.setText(("● Đang chạy · model đã có: " + (", ".join(models) or "chưa có")) if ok else
                               "○ Chưa mở Ollama (cài từ ollama.com rồi mở lại)")

    def pull(self):
        model = self.model.currentData() or "qwen2.5:7b"
        ok, _m = ai.ollama_status(self.win.settings)
        if not ok:
            QMessageBox.warning(self, "Chưa có Ollama", "Hãy cài và mở Ollama trước (nút Tải Ollama).")
            return
        self.win.binder.set("ai", "model", model)

        def job(log, progress, cancel):
            ai.ollama_pull(model, self.win.settings, log, progress, cancel)
            return model
        self.win.run_task(job, "Tải model AI", on_done=lambda _m: (self.check_ollama(), self.win.refresh_ai()))

    def accept(self):
        m = self.model.currentData()
        if m and self.win.settings.get("ai", "provider") == "ollama":
            self.win.binder.set("ai", "model", m)
        self.win.settings.save()
        super().accept()
