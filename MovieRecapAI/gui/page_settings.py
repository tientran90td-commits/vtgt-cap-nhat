"""Trang API & Cài đặt: nhập API key cho các AI, kiểm tra kết nối, đường dẫn hệ thống."""
from __future__ import annotations

import subprocess

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from recap import llm, tts
from recap.ffmpeg_utils import ffmpeg_exe, set_ffmpeg_path

from .widgets import Page, PathPicker, button, hrow, muted, scroll

TTS_KEYS = [
    ("elevenlabs", "ElevenLabs", "elevenlabs_key", "https://elevenlabs.io/app/settings/api-keys"),
    ("google", "Google Cloud TTS", "google_tts_key", "https://console.cloud.google.com/apis/credentials"),
    ("azure", "Azure AI Speech", "azure_key", "https://portal.azure.com/#create/Microsoft.CognitiveServicesSpeechServices"),
    ("fpt", "FPT.AI (giọng Việt)", "fpt_key", "https://console.fpt.ai"),
]


class KeyField(QWidget):
    def __init__(self, binder, key, placeholder="Dán API key vào đây"):
        super().__init__()
        from PySide6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = binder.line(QLineEdit(), "api", key)
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(placeholder)
        eye = button("👁", self.toggle, tip="Hiện/ẩn key")
        eye.setFixedWidth(40)
        lay.addWidget(self.edit, 1)
        lay.addWidget(eye)

    def toggle(self):
        self.edit.setEchoMode(QLineEdit.Normal if self.edit.echoMode() == QLineEdit.Password else QLineEdit.Password)


class SettingsPage(Page):
    def __init__(self, app):
        super().__init__(app, "🔑  API & Cài đặt",
                         "Nhập API key cho các dịch vụ AI bạn muốn dùng (không bắt buộc tất cả). "
                         "Gợi ý miễn phí: Gemini (viết kịch bản) + Edge TTS (giọng đọc) + Whisper offline (nhận dạng). "
                         f"Key chỉ lưu trên máy bạn tại: {app.settings.path}")
        b = app.binder
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 8, 0)

        g1 = QGroupBox("🧠 AI viết kịch bản (LLM)")
        f1 = QFormLayout(g1)
        self.status: dict[str, QLabel] = {}
        for pid, p in llm.PROVIDERS.items():
            if pid in ("none", "web"):
                continue
            st = QLabel("")
            self.status[pid] = st
            widgets = []
            if p.get("key"):
                widgets.append(KeyField(b, p["key"]))
            if p.get("base_key"):
                be = b.line(QLineEdit(), "api", p["base_key"])
                be.setPlaceholderText(p.get("base") or "https://.../v1")
                be.setMinimumWidth(230)
                widgets.append(be)
            widgets.append(button("Kiểm tra", lambda _=False, pid=pid: self.test_llm(pid)))
            if p.get("url_help"):
                widgets.append(button("Lấy key ↗", lambda _=False, u=p["url_help"]: self.open(u), "link"))
            widgets.append(st)
            row = hrow(*widgets)
            row.layout().setStretch(0, 1)
            f1.addRow(p["name"], row)
        f1.addRow(muted("OpenAI key cũng dùng cho OpenAI TTS & Whisper API; Groq key dùng cho Groq Whisper; "
                        "Gemini key dùng cho Gemini TTS. Ollama/LM Studio chạy model trên máy, không cần key."))
        v.addWidget(g1)

        g2 = QGroupBox("🎙️ Giọng đọc (TTS)")
        f2 = QFormLayout(g2)
        for eng, name, key, url in TTS_KEYS:
            st = QLabel("")
            self.status["tts_" + eng] = st
            ws = [KeyField(b, key)]
            if eng == "azure":
                reg = b.line(QLineEdit(), "api", "azure_region")
                reg.setPlaceholderText("Vùng, vd southeastasia")
                reg.setFixedWidth(160)
                ws.append(reg)
            ws += [button("Kiểm tra", lambda _=False, e=eng: self.test_tts(e)),
                   button("Lấy key ↗", lambda _=False, u=url: self.open(u), "link"), st]
            row = hrow(*ws)
            row.layout().setStretch(0, 1)
            f2.addRow(name, row)
        hf = hrow(KeyField(b, "hf_token", "(tùy chọn) HuggingFace token - chỉ cần cho repo giọng/model phải đăng nhập"),
                  button("Lấy token ↗", lambda: self.open("https://huggingface.co/settings/tokens"), "link"))
        hf.layout().setStretch(0, 1)
        f2.addRow("HuggingFace", hf)
        f2.addRow(muted("Edge TTS, gTTS, Piper, VieNeu, giọng Windows và XTTS không cần key."))
        v.addWidget(g2)

        gm = QGroupBox("🎬 Dữ liệu phim (tùy chọn - giúp nhận diện phim & tên nhân vật chính xác)")
        fm = QFormLayout(gm)
        st = QLabel("")
        self.status["tmdb"] = st
        row = hrow(KeyField(b, "tmdb_key", "TMDB API Key (v3) hoặc API Read Access Token"),
                   button("Kiểm tra", self.test_tmdb),
                   button("Lấy key ↗", lambda: self.open("https://www.themoviedb.org/settings/api"), "link"), st)
        row.layout().setStretch(0, 1)
        fm.addRow("TMDB", row)
        fm.addRow(muted("Miễn phí: tạo tài khoản themoviedb.org → Settings → API. Có key thì app lấy đúng tên phim, "
                        "năm, nội dung và tên nhân vật (tiếng Việt nếu có)."))
        v.addWidget(gm)

        g3 = QGroupBox("⚙️ Hệ thống")
        f3 = QFormLayout(g3)
        self.ff = PathPicker("file", "ffmpeg (ffmpeg.exe ffmpeg)", "Để trống = tự tìm (khuyên dùng)")
        self.ff.setText(app.settings.get("paths", "ffmpeg", ""))
        self.ff.changed.connect(lambda val: (b._set("paths", "ffmpeg", val), set_ffmpeg_path(val or None)))
        self.lb_ff = muted("")
        f3.addRow("FFmpeg", hrow(self.ff, button("Kiểm tra", self.test_ffmpeg)))
        f3.addRow("", self.lb_ff)
        for key, label in (("workspace", "Thư mục dự án (file tạm)"), ("models", "Thư mục model (Whisper, Piper)")):
            pp = PathPicker("dir", placeholder="Mặc định")
            pp.setText(app.settings.get("paths", key, ""))
            pp.changed.connect(lambda val, k=key: b._set("paths", k, val))
            f3.addRow(label, pp)
        from PySide6.QtWidgets import QCheckBox

        f3.addRow(b.check(QCheckBox("Mở app là tự cài phần còn thiếu (thư viện, FFmpeg, model nhận dạng thoại)"),
                          "ui", "auto_install"))
        f3.addRow(b.check(QCheckBox("Mở app là nạp sẵn model giọng đọc & dữ liệu (dùng mượt, bấm là chạy ngay)"),
                          "ui", "preload"))
        proxy = b.line(QLineEdit(), "api", "proxy")
        proxy.setPlaceholderText("(tùy chọn) http://user:pass@host:port")
        f3.addRow("Proxy mạng", proxy)
        v.addWidget(g3)
        v.addStretch(1)
        self.root.addWidget(scroll(body), 1)

    def open(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def _mark(self, key, ok, msg):
        lb = self.status[key]
        lb.setObjectName("ok" if ok else "err")
        lb.setText(("✅ " if ok else "❌ ") + msg[:80])
        lb.setToolTip(msg)
        lb.style().polish(lb)

    def test_llm(self, pid):
        model = (llm.PROVIDERS[pid]["models"] or [""])[0]
        if self.app.settings.get("script", "provider") == pid:
            model = self.app.settings.get("script", "model") or model
        self.status[pid].setText("⏳ ...")

        def job(log, progress, cancel):
            try:
                models = llm.list_models(pid, self.app.settings)
                return f"OK · {len(models)} model"
            except Exception:
                return "OK · " + llm.test_provider(pid, model, self.app.settings)[:40]
        self.app.run_task(job, on_done=lambda r: self._mark(pid, True, r),
                          on_fail=lambda m: self._mark(pid, False, m), title=f"Kiểm tra {pid}", quiet=True)

    def test_tts(self, eng):
        self.status["tts_" + eng].setText("⏳ ...")

        def job(log, progress, cancel):
            voices = tts.list_voices(eng, self.app.settings, refresh=True)
            return f"OK · {len(voices)} giọng"
        self.app.run_task(job, on_done=lambda r: self._mark("tts_" + eng, True, r),
                          on_fail=lambda m: self._mark("tts_" + eng, False, m), title=f"Kiểm tra {eng}", quiet=True)

    def test_tmdb(self):
        from recap.film_id import tmdb_lookup

        self.status["tmdb"].setText("⏳ ...")

        def job(log, progress, cancel):
            r = tmdb_lookup("Inception", "2010", self.app.settings)
            return f"OK · {r['title']} ({r['year']})" if r else "OK"
        self.app.run_task(job, on_done=lambda r: self._mark("tmdb", True, r),
                          on_fail=lambda m: self._mark("tmdb", False, m), title="Kiểm tra TMDB", quiet=True)

    def test_ffmpeg(self):
        try:
            exe = ffmpeg_exe()
            out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20)
            self.lb_ff.setText("✅ " + out.stdout.splitlines()[0][:90] + f"\n{exe}")
        except Exception as e:  # noqa: BLE001
            self.lb_ff.setText(f"❌ {e}")
