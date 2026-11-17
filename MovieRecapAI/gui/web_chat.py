"""Chế độ dùng AI bản WEB (ChatGPT / Gemini / AI Studio / Claude...) - không cần API key.

- Nút 🔐 Đăng nhập: mở trình duyệt NGAY TRONG APP, đăng nhập 1 lần, app nhớ phiên đăng nhập (lưu trên máy).
- Khi cần AI: trang web hiện ngay trong hộp thoại, câu lệnh được copy sẵn -> bạn Ctrl+V, Enter -> bấm nút Copy
  dưới câu trả lời -> app TỰ NHẬN câu trả lời (theo dõi clipboard) và chạy tiếp.
- App không tự gõ/gửi tin nhắn hay đọc nội dung trang (tự động hóa trang web vi phạm điều khoản của các dịch vụ,
  dễ bị khóa tài khoản). Google thường chặn đăng nhập Google trong trình duyệt nhúng -> có nút mở bằng trình duyệt
  của máy, tính năng tự nhận câu trả lời vẫn hoạt động.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QLabel, QPlainTextEdit, QSplitter, QVBoxLayout,
                               QWidget)

from recap import llm
from recap.config import app_home
from recap.ffmpeg_utils import Cancelled

from .widgets import button, hrow, muted

try:  # QtWebEngine có sẵn trong PySide6 (gói Addons); thiếu thì dùng trình duyệt của máy
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
    from PySide6.QtWebEngineWidgets import QWebEngineView

    HAS_WEB = True
except Exception:  # pragma: no cover
    HAS_WEB = False

_PROFILE = None
GOOGLE_SITES = {"aistudio", "gemini"}


def web_profile():
    """Hồ sơ trình duyệt lưu trên đĩa -> đăng nhập 1 lần, lần sau vẫn còn."""
    global _PROFILE
    if _PROFILE is None and HAS_WEB:
        d = app_home() / "web_profile"
        d.mkdir(parents=True, exist_ok=True)
        app = QGuiApplication.instance()
        _PROFILE = QWebEngineProfile("MovieRecapAI", app)
        _PROFILE.setPersistentStoragePath(str(d))
        _PROFILE.setCachePath(str(d / "cache"))
        _PROFILE.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    return _PROFILE


class BrowserPane(QWidget):
    """Trình duyệt nhúng tối giản: chọn trang AI, quay lại, tải lại, mở bằng trình duyệt máy."""

    def __init__(self, site: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.site = site if site in llm.WEB_SITES else "aistudio"
        self.view = QWebEngineView(self)
        self.page = QWebEnginePage(web_profile(), self.view)
        self.view.setPage(self.page)
        self.cb = QComboBox()
        for k, (name, _url) in llm.WEB_SITES.items():
            self.cb.addItem(name, k)
        self.cb.setCurrentIndex(max(0, self.cb.findData(self.site)))
        self.cb.currentIndexChanged.connect(lambda _i: self.go(self.cb.currentData()))
        self.lb = muted("")
        lay.addWidget(hrow(self.cb, button("⟵", self.view.back, tip="Quay lại"),
                           button("⟳", self.view.reload, tip="Tải lại"),
                           button("↗ Mở bằng trình duyệt máy", self.external), "stretch", stretch_last=False))
        lay.addWidget(self.view, 1)
        lay.addWidget(self.lb)
        self.view.urlChanged.connect(self._url)
        self.go(self.site)

    def go(self, site: str):
        self.site = site
        self.view.setUrl(QUrl(llm.WEB_SITES[site][1]))
        self.lb.setText("Lưu ý: Google có thể chặn đăng nhập tài khoản Google trong trình duyệt nhúng - nếu vậy bấm "
                        "'↗ Mở bằng trình duyệt máy'." if site in GOOGLE_SITES else "")

    def _url(self, url: QUrl):
        if "accounts.google.com" in url.host():
            self.lb.setText("⚠️ Nếu Google báo 'trình duyệt không an toàn', hãy bấm '↗ Mở bằng trình duyệt máy' "
                            "(app vẫn tự nhận câu trả lời khi bạn bấm Copy).")

    def external(self):
        QDesktopServices.openUrl(QUrl(llm.WEB_SITES[self.site][1]))


class LoginDialog(QDialog):
    """🔐 Đăng nhập AI web 1 lần trong app."""

    def __init__(self, parent, site: str = "aistudio"):
        super().__init__(parent)
        self.setWindowTitle("🔐 Đăng nhập AI bản web")
        self.resize(1100, 780)
        lay = QVBoxLayout(self)
        if not HAS_WEB:
            lay.addWidget(muted("Máy thiếu thành phần trình duyệt nhúng (QtWebEngine) - hãy đăng nhập trong trình duyệt "
                                "của máy. App vẫn tự nhận câu trả lời khi bạn bấm Copy."))
            lay.addWidget(button("↗ Mở trang AI bằng trình duyệt máy",
                                 lambda: QDesktopServices.openUrl(QUrl(llm.WEB_SITES.get(site, llm.WEB_SITES["aistudio"])[1])),
                                 "primary"))
            return
        lay.addWidget(muted("Đăng nhập tài khoản của bạn trong cửa sổ này (chỉ cần 1 lần, app nhớ phiên đăng nhập). "
                            "Đăng nhập xong bấm Đóng."))
        self.pane = BrowserPane(site, self)
        lay.addWidget(self.pane, 1)
        lay.addWidget(hrow("stretch", button("✅ Đã đăng nhập xong - Đóng", self.accept, "primary")))


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
        dlg = WebChatDialog(self.window, job["site"], job["prompt"], job["json_mode"], self.window.settings)
        ok = dlg.exec() == QDialog.Accepted
        job["result"] = dlg.answer if ok else None
        job["cancel"] = not ok
        if ok and dlg.site != job["site"]:
            self.window.settings.set("script", "model", dlg.site)
        job["done"].set()


class WebChatDialog(QDialog):
    def __init__(self, parent, site: str, prompt: str, json_mode: bool, settings=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 AI bản web - dán câu lệnh, bấm Copy câu trả lời là xong")
        self.prompt, self.json_mode, self.answer = prompt, json_mode, None
        self.settings = settings
        self.site = site if site in llm.WEB_SITES else "aistudio"
        inapp = HAS_WEB and (settings.get("script", "web_inapp", True) if settings else True)
        self.resize(1360 if inapp else 820, 860 if inapp else 640)
        root = QVBoxLayout(self)
        steps = QLabel("<b>① Câu lệnh đã được copy sẵn</b> → <b>② Bấm vào ô chat, Ctrl+V, Enter</b> → "
                       "<b>③ Bấm nút Copy dưới câu trả lời</b> → app tự nhận & chạy tiếp ✅")
        steps.setWordWrap(True)
        root.addWidget(steps)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        self.cb_site = None
        if not inapp:
            self.cb_site = QComboBox()
            for k, (name, _url) in llm.WEB_SITES.items():
                self.cb_site.addItem(name, k)
            self.cb_site.setCurrentIndex(max(0, self.cb_site.findData(self.site)))
            self.cb_site.currentIndexChanged.connect(lambda _i: setattr(self, "site", self.cb_site.currentData()))
            sl.addWidget(hrow(self.cb_site, button("🌐 Mở trang AI", self.open_site, "primary"), stretch_last=False))
        sl.addWidget(hrow(button("📋 Copy lại câu lệnh", self.copy_prompt), muted(f"{len(prompt):,} ký tự"),
                          "stretch"))
        view = QPlainTextEdit(prompt)
        view.setReadOnly(True)
        view.setMaximumHeight(130)
        sl.addWidget(view)
        self.auto = QCheckBox("Tự nhận câu trả lời khi tôi bấm Copy")
        self.auto.setChecked(True)
        sl.addWidget(self.auto)
        sl.addWidget(QLabel("<b>Câu trả lời của AI</b> (tự điền khi bạn Copy, hoặc dán tay):"))
        self.ans = QPlainTextEdit()
        self.ans.setPlaceholderText("Câu trả lời (có thể kèm ```json ... ```) - app tự lọc lấy phần JSON")
        sl.addWidget(self.ans, 1)
        self.lb = muted("")
        self.lb.setWordWrap(True)
        sl.addWidget(self.lb)
        sl.addWidget(muted("Mẹo: Google AI Studio miễn phí, đọc được câu lệnh rất dài. Web báo câu lệnh quá dài → giảm ô "
                           "'Bản web' ở Bước 2. Câu trả lời bị ngắt → nhắn 'tiếp tục' rồi dán nối cả 2 phần."))
        self.btn_ok = button("✅ Xong", self.finish, "big")
        sl.addWidget(hrow(button("📥 Dán từ clipboard", self.paste), "stretch", self.btn_ok,
                          button("Hủy", self.reject, "danger")))

        if inapp:
            split = QSplitter(Qt.Horizontal)
            self.browser = BrowserPane(self.site, self)
            self.browser.cb.currentIndexChanged.connect(lambda _i: setattr(self, "site", self.browser.cb.currentData()))
            split.addWidget(self.browser)
            split.addWidget(side)
            split.setSizes([900, 440])
            root.addWidget(split, 1)
        else:
            self.browser = None
            root.addWidget(side, 1)

        self.clip = QGuiApplication.clipboard()
        self.clip.dataChanged.connect(self._clip_changed)
        QTimer.singleShot(150, self.copy_prompt)

    # ------------------------------------------------------------
    def copy_prompt(self):
        self._own = True
        self.clip.setText(self.prompt)
        self.lb.setText("✅ Đã copy câu lệnh - bấm vào ô chat của trang AI, Ctrl+V rồi Enter.")

    def open_site(self):
        self.copy_prompt()
        QDesktopServices.openUrl(QUrl(llm.WEB_SITES[self.site][1]))

    def paste(self):
        self.ans.setPlainText(self.clip.text())

    def _clip_changed(self):
        if getattr(self, "_own", False):  # thay đổi do chính app copy câu lệnh
            self._own = False
            return
        if not self.auto.isChecked():
            return
        text = (self.clip.text() or "").strip()
        if not text or text == self.prompt.strip() or len(text) < 20:
            return
        self.ans.setPlainText(text)
        if self.json_mode:
            try:
                llm.extract_json(text)
            except Exception:  # noqa: BLE001
                self.lb.setText("⏳ Đã nhận nội dung nhưng chưa thấy JSON đầy đủ - nếu AI chưa trả lời xong, đợi rồi bấm "
                                "Copy lại.")
                return
            self.lb.setText("✅ Đã nhận câu trả lời - đang tiếp tục...")
            QTimer.singleShot(700, self.finish)
        else:
            self.lb.setText("✅ Đã nhận câu trả lời - kiểm tra rồi bấm ✅ Xong.")
            self.btn_ok.setFocus()

    def finish(self):
        if self.answer is not None:
            return
        text = self.ans.toPlainText().strip()
        if not text:
            self.lb.setText("❌ Chưa có câu trả lời.")
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

    def done(self, r):
        try:
            self.clip.dataChanged.disconnect(self._clip_changed)
        except Exception:  # noqa: BLE001
            pass
        super().done(r)


# ====================================================================== Lấy API key miễn phí - tự động hoàn toàn
import re as _re  # noqa: E402

KEY_PATTERNS = [  # (regex, nhà cung cấp, trường key trong cài đặt)
    (r"AIza[0-9A-Za-z_\-]{35}", "gemini", "gemini_key"),
    (r"gsk_[0-9A-Za-z]{40,}", "groq", "groq_key"),
    (r"sk-ant-[0-9A-Za-z_\-]{30,}", "anthropic", "anthropic_key"),
    (r"sk-or-v1-[0-9a-f]{40,}", "openrouter", "openrouter_key"),
    (r"sk-proj-[0-9A-Za-z_\-]{30,}", "openai", "openai_key"),
]
KEY_PAGES = {
    "gemini": ("Google Gemini - MIỄN PHÍ (khuyên dùng)", "https://aistudio.google.com/apikey"),
    "groq": ("Groq - miễn phí (Llama, Whisper rất nhanh)", "https://console.groq.com/keys"),
    "openrouter": ("OpenRouter - có model miễn phí", "https://openrouter.ai/keys"),
}


def detect_key(text: str):
    """Tìm API key trong đoạn văn bản -> (provider, settings_field, key) hoặc None."""
    for pat, pid, field in KEY_PATTERNS:
        m = _re.search(pat, text or "")
        if m:
            return pid, field, m.group(0)
    return None


class KeyWizard(QDialog):
    """Mở trang tạo key -> người dùng bấm Create + Copy -> app tự nhận key, lưu, chọn nhà cung cấp."""

    def __init__(self, app_window, provider: str = "gemini"):
        super().__init__(app_window)
        self.app = app_window
        self.provider = provider
        self.got = None
        self.setWindowTitle("⚡ Lấy API key miễn phí - để app tự động hoàn toàn")
        self.resize(640, 360)
        lay = QVBoxLayout(self)
        intro = QLabel("<b>Có key là app chạy tự động hoàn toàn</b> (không phải copy-dán mỗi lần).<br>"
                       "① Bấm <b>Mở trang lấy key</b> và đăng nhập Google của bạn<br>"
                       "② Bấm <b>Create API key</b> (Tạo khóa API)<br>"
                       "③ Bấm nút <b>Copy</b> cạnh key → app <b>tự nhận, tự lưu</b> và chọn sẵn AI cho bạn ✅")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.cb = QComboBox()
        for k, (name, _u) in KEY_PAGES.items():
            self.cb.addItem(name, k)
        self.cb.setCurrentIndex(max(0, self.cb.findData(provider)))
        lay.addWidget(hrow(self.cb, button("🌐 Mở trang lấy key", self.open_page, "primary"), stretch_last=False))
        self.lb = QLabel("⏳ Đang chờ bạn bấm Copy key...")
        self.lb.setWordWrap(True)
        lay.addWidget(self.lb)
        lay.addWidget(muted("Key chỉ lưu trên máy bạn (mục 🔑 API & Cài đặt). Gói miễn phí của Gemini có giới hạn số lượt "
                            "mỗi ngày - đủ để làm nhiều video. Có thể dán key bằng tay ở mục 🔑 API & Cài đặt."))
        lay.addStretch(1)
        lay.addWidget(hrow("stretch", button("Đóng", self.reject)))
        self.clip = QGuiApplication.clipboard()
        self.clip.dataChanged.connect(self._clip)
        self._clip()  # có thể key đã nằm sẵn trong clipboard

    def open_page(self):
        QDesktopServices.openUrl(QUrl(KEY_PAGES[self.cb.currentData()][1]))

    def _clip(self):
        found = detect_key(self.clip.text() or "")
        if not found:
            return
        pid, field, key = found
        s = self.app.settings
        s.set("api", field, key)
        s.set("script", "provider", pid)
        s.set("script", "model", "auto" if pid == "gemini" else llm.PROVIDERS[pid]["models"][0])
        s.save()
        self.got = pid
        self.lb.setText(f"✅ Đã nhận & lưu key {llm.PROVIDERS[pid]['name']} - đang kiểm tra...")
        self.app.log(f"🔑 Đã lưu key {llm.PROVIDERS[pid]['name']} và chọn làm AI viết kịch bản.")

        def job(log, progress, cancel):
            return llm.list_models(pid, s)

        def ok(models):
            self.lb.setText(f"✅ Key hoạt động ({len(models)} model). App giờ chạy TỰ ĐỘNG hoàn toàn - đóng cửa sổ này "
                            "và bấm ⚡.")
            QTimer.singleShot(2500, self.accept)

        def bad(msg):
            self.lb.setText(f"⚠️ Đã lưu key nhưng kiểm tra lỗi: {msg[:200]}")
        self.app.run_task(job, on_done=ok, on_fail=bad, title="Kiểm tra key", quiet=True)

    def done(self, r):
        try:
            self.clip.dataChanged.disconnect(self._clip)
        except Exception:  # noqa: BLE001
            pass
        super().done(r)
