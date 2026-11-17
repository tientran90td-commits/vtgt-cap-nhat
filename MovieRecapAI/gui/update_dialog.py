"""Hộp thoại cập nhật tool trực tiếp từ GitHub."""
from __future__ import annotations

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout

from recap import APP_VERSION, updater

from .widgets import button, hrow, muted


class UpdateDialog(QDialog):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("🔄 Cập nhật Movie Recap AI")
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        repo, branch = updater.source(app.settings)
        self.lb = QLabel(f"Đang dùng: <b>v{APP_VERSION}</b> · Đang kiểm tra bản mới...")
        lay.addWidget(self.lb)
        lay.addWidget(muted(f"Nguồn cập nhật: github.com/{repo} (nhánh {branch}). Cài đặt, API key, dự án và model của "
                            "bạn được giữ nguyên. File cũ được sao lưu để có thể khôi phục."))
        self.changes = QPlainTextEdit()
        self.changes.setReadOnly(True)
        lay.addWidget(QLabel("<b>Thay đổi gần đây:</b>"))
        lay.addWidget(self.changes, 1)
        self.btn_go = button("⬇ Cập nhật ngay", self.do_update, "big")
        self.btn_go.setEnabled(False)
        lay.addWidget(hrow(self.btn_go, button("↩ Khôi phục bản trước", self.do_rollback), "stretch",
                           button("Đóng", self.reject)))
        app.run_task(lambda log, progress, cancel: updater.check(app.settings), on_done=self._checked,
                     on_fail=lambda m: self.lb.setText(f"❌ Không kiểm tra được bản mới: {m}"), title="Kiểm tra bản mới",
                     quiet=True)

    def _checked(self, info):
        self.info = info
        self.changes.setPlainText("\n".join("• " + c for c in info.get("changes") or []) or "(không có thông tin)")
        if info["newer"]:
            self.lb.setText(f"Đang dùng <b>v{APP_VERSION}</b> → có bản mới <b style='color:#3DDC97'>v{info['latest']}</b>")
            self.btn_go.setEnabled(True)
        else:
            self.lb.setText(f"✅ Bạn đang dùng bản mới nhất (<b>v{APP_VERSION}</b>).")

    def do_update(self):
        if self.app.main_worker is not None:
            QMessageBox.information(self, "Đang bận", "Hãy đợi tác vụ hiện tại xong (hoặc bấm Hủy) rồi cập nhật.")
            return
        self.btn_go.setEnabled(False)

        def done(res):
            if res.get("updated"):
                self.lb.setText(f"✅ Đã cập nhật lên v{res['latest']}.")
                if QMessageBox.question(self, "Khởi động lại", "Đã cập nhật xong. Khởi động lại app ngay?") == \
                        QMessageBox.Yes:
                    restart(self.app)
        self.app.run_task(updater.update, self.app.settings, on_done=done, title="Cập nhật tool")

    def do_rollback(self):
        if QMessageBox.question(self, "Khôi phục", "Khôi phục mã nguồn bản trước lần cập nhật gần nhất?") != \
                QMessageBox.Yes:
            return
        try:
            v = updater.rollback(self.app.log)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Khôi phục", str(e))
            return
        if QMessageBox.question(self, "Khôi phục", f"Đã khôi phục v{v}. Khởi động lại app?") == QMessageBox.Yes:
            restart(self.app)


def restart(app_window):
    cmd = updater.restart_command()
    app_window.settings.save()
    QProcess.startDetached(cmd[0], cmd[1:])
    QApplication.instance().quit()
