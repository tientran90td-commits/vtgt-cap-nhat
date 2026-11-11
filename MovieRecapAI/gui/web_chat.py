"""Chế độ dùng bản WEB (ChatGPT / Gemini / AI Studio / Claude...) bằng copy & dán - không cần API key.

App KHÔNG tự đăng nhập hay điều khiển trang web (vi phạm điều khoản, dễ bị khóa tài khoản, hay hỏng).
Thay vào đó: app copy sẵn câu lệnh + mở trang web -> bạn dán & gửi -> copy câu trả lời dán lại vào app.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QPlainTextEdit, QVBoxLayout

from recap import llm
from recap.ffmpeg_utils import Cancelled

from .widgets import button, hrow, muted


class WebBridge(QObject):
    """Gọi từ luồng nền -> hiện hộp thoại ở luồng giao diện -> chờ người dùng dán câu trả lời."""

    request = Signal(object)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.request.connect(self._show)

    # chạy trong luồng nền (Worker)
    def __call__(self, site: str, prompt: str, json_mode: bool) -> str:
        job = {"site": site, "prompt": prompt, "json_mode": json_mode, "done": threading.Event(),
               "result": None, "cancel": False}
        self.request.emit(job)
        w = getattr(self.window, "main_worker", None)
        while not job["done"].wait(0.2):
            if w is not None and w.cancel.is_set():
                raise Cancelled()
        if job["cancel"] or job["result"] is None:
            raise Cancelled()
        return job["result"]

    # chạy ở luồng giao diện
    def _show(self, job):
        dlg = WebChatDialog(self.window, job["site"], job["prompt"], job["json_mode"])
        ok = dlg.exec() == QDialog.Accepted
        job["result"] = dlg.answer if ok else None
        job["cancel"] = not ok
        if ok and dlg.site != job["site"]:
            self.window.settings.set("script", "model", dlg.site)
        job["done"].set()


class WebChatDialog(QDialog):
    def __init__(self, parent, site: str, prompt: str, json_mode: bool):
        super().__init__(parent)
        self.setWindowTitle("🌐 Dùng AI bản web - copy & dán")
        self.resize(820, 640)
        self.prompt, self.json_mode, self.answer = prompt, json_mode, None
        self.site = site if site in llm.WEB_SITES else "aistudio"
        lay = QVBoxLayout(self)
        steps = QLabel(
            "<b>① Copy câu lệnh</b> → <b>② Mở trang AI</b> (đăng nhập tài khoản của bạn) → <b>③ Dán (Ctrl+V) & gửi</b> → "
            "<b>④ Copy toàn bộ câu trả lời</b> (nút Copy dưới câu trả lời) → <b>⑤ Dán vào ô dưới</b> → ✅ Xong")
        steps.setWordWrap(True)
        lay.addWidget(steps)
        self.cb_site = QComboBox()
        for k, (name, _url) in llm.WEB_SITES.items():
            self.cb_site.addItem(name, k)
        self.cb_site.setCurrentIndex(max(0, self.cb_site.findData(self.site)))
        self.cb_site.currentIndexChanged.connect(lambda _i: setattr(self, "site", self.cb_site.currentData()))
        n = len(prompt)
        lay.addWidget(hrow(button("① 📋 Copy câu lệnh", self.copy_prompt, "primary"), self.cb_site,
                           button("② 🌐 Mở trang AI", self.open_site, "primary"), "stretch",
                           muted(f"{n:,} ký tự"), stretch_last=False))
        view = QPlainTextEdit(prompt)
        view.setReadOnly(True)
        view.setMaximumHeight(160)
        lay.addWidget(view)
        lay.addWidget(muted("Mẹo: Google AI Studio đọc được câu lệnh rất dài và miễn phí. Nếu trang web báo câu lệnh quá "
                            "dài, hãy chọn AI Studio, hoặc giảm ô 'Bản web' (ký tự/lần dán) ở Bước 2 để app tự chia nhỏ. "
                            "Câu trả lời bị ngắt giữa chừng thì gõ 'tiếp tục' rồi dán nối cả 2 phần vào ô dưới."))
        lay.addWidget(QLabel("<b>⑤ Dán câu trả lời của AI vào đây:</b>"))
        self.ans = QPlainTextEdit()
        self.ans.setPlaceholderText("Dán câu trả lời (có thể kèm ```json ... ```) - app tự lọc lấy phần JSON")
        lay.addWidget(self.ans, 1)
        self.lb = muted("")
        lay.addWidget(self.lb)
        lay.addWidget(hrow(button("📥 Dán từ clipboard", self.paste), "stretch",
                           button("✅ Xong", self.finish, "big"), button("Hủy", self.reject, "danger")))

    def copy_prompt(self):
        QGuiApplication.clipboard().setText(self.prompt)
        self.lb.setText("✅ Đã copy câu lệnh - giờ mở trang AI và dán (Ctrl+V).")

    def open_site(self):
        self.copy_prompt()
        QDesktopServices.openUrl(QUrl(llm.WEB_SITES[self.site][1]))

    def paste(self):
        self.ans.setPlainText(QGuiApplication.clipboard().text())

    def finish(self):
        text = self.ans.toPlainText().strip()
        if not text:
            self.lb.setText("❌ Chưa dán câu trả lời.")
            return
        if self.json_mode:
            try:
                llm.extract_json(text)
            except Exception as e:  # noqa: BLE001
                self.lb.setText(f"❌ Câu trả lời chưa đúng dạng JSON ({str(e).splitlines()[0][:120]}). "
                                "Hãy copy đầy đủ câu trả lời, hoặc nhắn AI: 'trả lời lại chỉ bằng JSON'.")
                return
        self.answer = text
        self.accept()
