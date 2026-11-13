"""Dịch qua DeepSeek web (bạn tự dán): app soạn yêu cầu & chép sẵn, bạn dán vào chat.deepseek.com rồi dán câu
trả lời lại đây. App chỉ mở trang web cho bạn, không tự điều khiển trang."""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QCheckBox, QDialog, QMessageBox, QPlainTextEdit, QVBoxLayout

from vietdub import translate as tr

from .common import button, label, row


class ManualTranslateDialog(QDialog):
    def __init__(self, win, project):
        super().__init__(win)
        self.win, self.p = win, project
        self.setWindowTitle("🐋 Dịch qua DeepSeek web (dán tay, miễn phí)")
        self.resize(820, 620)
        self.lines = tr.prepare_lines(project.source)
        self.result: dict[int, str] = {}
        old = project.lines
        if old and len(old) == len(self.lines):  # làm tiếp phần đã dán lần trước
            self.result = {i: x["vi"] for i, x in enumerate(old) if x.get("vi")}
        self.asked: list[int] = []
        self.mode = "translate"
        self.first = not self.result

        lay = QVBoxLayout(self)
        lay.addWidget(label(
            "1. Bấm <b>📋 Chép yêu cầu</b> (app chép sẵn vào bộ nhớ).<br>"
            "2. Bấm <b>🌐 Mở DeepSeek</b>, dán (Ctrl+V) vào ô chat, gửi. Nên dùng cùng 1 cuộc trò chuyện cho mọi phần "
            "để tên riêng thống nhất.<br>"
            "3. Chép <b>toàn bộ câu trả lời</b> của DeepSeek, dán vào ô dưới, bấm <b>✅ Áp dụng</b>.<br>"
            f"Mỗi lần tối đa {tr.MANUAL_PART} câu - lặp lại tới khi đủ. Câu thiếu sẽ được hỏi lại ở lần sau."))
        self.lb = label("", "muted")
        lay.addWidget(self.lb)
        self.redo = QCheckBox("Dịch lại từ đầu (bỏ bản dịch đang có)")
        self.redo.toggled.connect(self._redo)
        self.redo.setVisible(bool(self.result))
        lay.addWidget(self.redo)
        self.btn_copy = button("📋 Chép yêu cầu", self.copy, "primary")
        self.btn_short = button("📋 Chép yêu cầu rút gọn câu dài", self.copy_shorten)
        lay.addWidget(row(self.btn_copy, button("🌐 Mở DeepSeek", self.open_chat), self.btn_short, "stretch"))
        self.box = QPlainTextEdit()
        self.box.setPlaceholderText("Dán câu trả lời của DeepSeek vào đây (có thể dán cả khối ```json ... ```)")
        lay.addWidget(self.box, 1)
        lay.addWidget(row(button("✅ Áp dụng", self.apply, "primary"), "stretch", button("Xong", self.accept)))
        self.refresh()

    # ------------------------------------------------------------------
    def missing(self) -> list[int]:
        return [i for i in range(len(self.lines)) if i not in self.result]

    def too_fast(self) -> list[int]:
        return [i for i, v in self.result.items() if tr.too_fast(self.lines[i], v)]

    def refresh(self):
        miss, fast = self.missing(), self.too_fast()
        n = len(self.lines)
        parts = -(-len(miss) // tr.MANUAL_PART) if miss else 0
        txt = f"Đã dịch {n - len(miss)}/{n} câu."
        if miss:
            txt += f" Còn {len(miss)} câu ({parts} lần dán)."
        elif fast:
            txt += f" ✅ Đủ câu. {len(fast)} câu đọc hơi nhanh - có thể chép yêu cầu rút gọn."
        else:
            txt += " ✅ Xong hết, bấm Xong."
        self.lb.setText(txt)
        self.btn_copy.setEnabled(bool(miss))
        self.btn_copy.setText(f"📋 Chép yêu cầu (phần tiếp, {min(len(miss), tr.MANUAL_PART)} câu)" if miss
                              else "📋 Chép yêu cầu")
        self.btn_short.setEnabled(not miss and bool(fast))

    def _redo(self, on):
        if on:
            self.result = {}
            self.first = True
            self.redo.setEnabled(False)
            self.refresh()

    def _clip(self, text: str):
        QGuiApplication.clipboard().setText(text)
        self.box.clear()

    def copy(self):
        self.asked = self.missing()[:tr.MANUAL_PART]
        self.mode = "translate"
        self._clip(tr.manual_prompt(self.lines, self.asked, self.win.settings, self.p.title, first=self.first))
        self.first = False
        self.win.log_msg(f"📋 Đã chép yêu cầu dịch {len(self.asked)} câu - dán vào DeepSeek.")

    def copy_shorten(self):
        self.asked = self.too_fast()[:tr.MANUAL_PART]
        self.mode = "shorten"
        self._clip(tr.manual_shorten_prompt(self.lines, self.result, self.asked))
        self.win.log_msg(f"📋 Đã chép yêu cầu rút gọn {len(self.asked)} câu - dán vào DeepSeek.")

    def open_chat(self):
        QDesktopServices.openUrl(QUrl(tr.CHAT_URL))

    def apply(self):
        text = self.box.toPlainText().strip()
        if not text:
            return
        if not self.asked:
            QMessageBox.information(self, "Chưa chép yêu cầu", "Bấm 📋 Chép yêu cầu trước, dán vào DeepSeek.")
            return
        got = tr.parse_reply(text, self.asked, self.result if self.mode == "shorten" else None)
        if not got:
            QMessageBox.warning(self, "Không đọc được", "Không thấy câu dịch nào trong nội dung dán. Hãy chép "
                                "toàn bộ câu trả lời của DeepSeek (phần JSON {\"lines\": ...}).")
            return
        self.result.update(got)
        lack = [i for i in self.asked if i not in got]
        self.win.log_msg(f"✅ Nhận {len(got)}/{len(self.asked)} câu từ DeepSeek"
                         + (f" - {len(lack)} câu còn thiếu sẽ hỏi lại lần sau." if lack and self.mode != "shorten"
                            else "."))
        self.asked = []
        self.box.clear()
        self.save()
        self.refresh()

    def save(self):
        self.p.save_lines([{"start": ln["start"], "end": ln["end"], "text": ln["text"],
                            "vi": self.result.get(i, "")} for i, ln in enumerate(self.lines)])
