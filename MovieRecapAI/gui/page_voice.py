"""Trang 3: chọn giọng đọc từ nhiều engine, chỉnh tốc độ/cao độ/âm lượng, nghe thử."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget)

from recap import tts

from .player import AudioPlayer
from .widgets import LabeledSlider, Page, PathPicker, bind_labeled_slider, button, fill_combo, hrow, muted

SAMPLE = {
    "vi": "Chào mừng các bạn quay trở lại kênh. Hôm nay chúng ta sẽ cùng tóm tắt một bộ phim cực kỳ hấp dẫn, "
          "với cái kết không ai ngờ tới.",
    "en": "Welcome back to the channel. Today we're recapping an incredible movie with an ending nobody saw coming.",
}

STYLE_HINT = {
    "openai": "Chỉ dẫn giọng (gpt-4o-mini-tts), vd: Giọng trầm, kịch tính như người kể chuyện phim kinh dị",
    "gemini": "Cách đọc, vd: Đọc một cách hồi hộp và bí ẩn",
    "azure": "Phong cách Azure (1 từ), vd: cheerful, sad, angry, excited, narration-professional",
}


class VoicePage(Page):
    def __init__(self, app):
        super().__init__(app, "🎙️  Bước 3 · Giọng đọc thuyết minh",
                         "Hơn 1000 giọng từ 11 công cụ: miễn phí (Edge TTS, gTTS), offline (Piper, giọng Windows, "
                         "XTTS nhân bản giọng) và cao cấp (ElevenLabs, OpenAI, Gemini, Google Cloud, Azure, FPT.AI).")
        b = app.binder
        self.voices: list[tts.Voice] = []
        body = QHBoxLayout()
        # ------------------------------------------------ trái: danh sách giọng
        left = QVBoxLayout()
        self.engine = b.combo(fill_combo(QComboBox(), {k: ("🔌 " if v["offline"] else "🌐 ") + v["name"]
                                                        for k, v in tts.ENGINES.items()}), "voice", "engine")
        self.engine.currentIndexChanged.connect(lambda _i: self.load_voices())
        self.lb_engine = muted("")
        flt = QHBoxLayout()
        self.f_lang = fill_combo(QComboBox(), [])
        self.f_lang.setMinimumWidth(150)
        self.f_gender = fill_combo(QComboBox(), {"": "Nam & Nữ", "Female": "Nữ", "Male": "Nam"})
        self.f_text = QLineEdit()
        self.f_text.setPlaceholderText("🔍 Tìm giọng...")
        for w in (self.f_lang, self.f_gender):
            w.currentIndexChanged.connect(self.apply_filter)
        self.f_text.textChanged.connect(self.apply_filter)
        flt.addWidget(self.f_lang)
        flt.addWidget(self.f_gender)
        flt.addWidget(self.f_text, 1)
        flt.addWidget(button("🔄", lambda: self.load_voices(refresh=True), tip="Tải lại danh sách giọng"))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._pick)
        self.list.itemDoubleClicked.connect(lambda _i: self.listen())
        self.lb_count = muted("")
        left.addWidget(self.engine)
        left.addWidget(self.lb_engine)
        left.addLayout(flt)
        left.addWidget(self.list, 1)
        left.addWidget(self.lb_count)

        # ------------------------------------------------ phải: tinh chỉnh
        right = QVBoxLayout()
        g = QGroupBox("🎚️ Tinh chỉnh giọng")
        f = QFormLayout(g)
        self.rate = bind_labeled_slider(b, LabeledSlider(-50, 100, "{:+d}%"), "voice", "rate")
        self.pitch = bind_labeled_slider(b, LabeledSlider(-12, 12, "{:+d} cung"), "voice", "pitch")
        self.volume = bind_labeled_slider(b, LabeledSlider(-50, 50, "{:+d}%"), "voice", "volume")
        f.addRow("Tốc độ", self.rate)
        f.addRow("Cao độ (trầm/bổng)", self.pitch)
        f.addRow("Âm lượng", self.volume)
        f.addRow(hrow("stretch", button("↺ Mặc định", self.reset)))
        f.addRow(muted("Mẹo: giọng nữ hạ -2 → -4 cung nghe trầm ấm; giọng nam +1 → +2 nghe trẻ hơn. "
                       "Review phim thường để tốc độ +10% → +20%."))
        self.model = fill_combo(QComboBox(), [])
        self.app.binder.edit_combo(self.model, "voice", "model")
        self.style = b.line(QLineEdit(), "voice", "style")
        self.row_model = ("Model", self.model)
        f.addRow("Model", self.model)
        f.addRow("Cảm xúc / phong cách", self.style)
        right.addWidget(g)

        self.g_extra = QGroupBox("Tùy chọn riêng")
        fe = QFormLayout(self.g_extra)
        self.btn_piper = button("⬇ Tải thêm giọng Piper (offline, 40+ ngôn ngữ)", self.piper_dialog, "primary")
        self.xtts_ref = PathPicker("file", "Âm thanh (*.wav *.mp3 *.flac *.m4a)", "File giọng mẫu 6-30 giây")
        self.xtts_ref.setText(app.settings.get("voice", "xtts_ref", ""))
        self.xtts_ref.changed.connect(lambda v: b._set("voice", "xtts_ref", v))
        self.xtts_dir = PathPicker("dir", placeholder="(tùy chọn) Thư mục model viXTTS / XTTS tinh chỉnh")
        self.xtts_dir.setText(app.settings.get("voice", "xtts_model_dir", ""))
        self.xtts_dir.changed.connect(lambda v: b._set("voice", "xtts_model_dir", v))
        fe.addRow(self.btn_piper)
        fe.addRow("Giọng mẫu", self.xtts_ref)
        fe.addRow("Model riêng", self.xtts_dir)
        self.lb_extra = muted("")
        fe.addRow(self.lb_extra)
        right.addWidget(self.g_extra)

        g2 = QGroupBox("🔊 Nghe thử")
        v2 = QVBoxLayout(g2)
        self.sample = QPlainTextEdit(SAMPLE["vi"])
        self.sample.setMaximumHeight(90)
        v2.addWidget(self.sample)
        v2.addWidget(hrow(button("▶ Nghe thử", self.listen, "primary"), button("⏹ Dừng", lambda: self.audio.stop()),
                          "stretch", button("Tiếp: Xuất video →", lambda: self.app.goto(3), "primary")))
        right.addWidget(g2)
        right.addStretch(1)

        lw, rw = QWidget(), QWidget()
        lw.setLayout(left)
        rw.setLayout(right)
        body.addWidget(lw, 5)
        body.addWidget(rw, 4)
        self.root.addLayout(body, 1)
        self.audio = AudioPlayer(self)
        self._loaded_engine = None

    def on_show(self):
        if self._loaded_engine != self.engine.currentData():
            self.load_voices()

    def reset(self):
        self.rate.setValue(0)
        self.pitch.setValue(0)
        self.volume.setValue(0)

    # ------------------------------------------------ danh sách giọng
    def _engine_ui(self, eng):
        info = tts.ENGINES[eng]
        txt = "🔌 Chạy offline trên máy." if info["offline"] else "🌐 Cần Internet."
        if info.get("key"):
            has = bool(self.app.settings.get("api", info["key"]))
            txt += " API key: " + ("✅ đã nhập" if has else "⚠️ chưa nhập (mục 🔑 API & Cài đặt)")
        else:
            txt += " Không cần API key."
        self.lb_engine.setText(txt)
        cur = self.app.settings.get("voice", "model", "")
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(info.get("models", []))
        self.model.blockSignals(False)
        self.model.setEnabled(bool(info.get("models")))
        if info.get("models"):
            self.model.setCurrentText(cur if cur in info["models"] else info["models"][0])
        self.style.setEnabled(bool(info.get("style")))
        self.style.setPlaceholderText(STYLE_HINT.get(eng, "(engine này không hỗ trợ)"))
        self.g_extra.setVisible(eng in ("piper", "xtts"))
        self.btn_piper.setVisible(eng == "piper")
        self.xtts_ref.setVisible(eng == "xtts")
        self.xtts_dir.setVisible(eng == "xtts")
        fe = self.g_extra.layout()
        for w in (self.xtts_ref, self.xtts_dir):
            lb = fe.labelForField(w)
            if lb:
                lb.setVisible(eng == "xtts")
        self.lb_extra.setText({
            "piper": "Giọng Piper lưu trong thư mục models/piper. Tiếng Việt: vi_VN-vais1000-medium, "
                     "vi_VN-25hours_single-low, vi_VN-vivos-x_low.",
            "xtts": "Cài thêm: pip install coqui-tts. XTTS-v2 hỗ trợ 17 ngôn ngữ (chưa có tiếng Việt). "
                    "Với tiếng Việt hãy tải model viXTTS (huggingface.co/capleaf/viXTTS) rồi chọn thư mục ở trên.",
        }.get(eng, ""))

    def load_voices(self, refresh=False):
        eng = self.engine.currentData()
        self._engine_ui(eng)
        self.list.clear()
        self.lb_count.setText("Đang tải danh sách giọng...")

        def done(voices):
            self._loaded_engine = eng
            self.voices = voices
            langs = sorted({v.lang for v in voices if v.lang})
            self.f_lang.blockSignals(True)
            self.f_lang.clear()
            self.f_lang.addItem("Mọi ngôn ngữ", "")
            for lg in langs:
                self.f_lang.addItem(lg, lg)
            cur = self.app.settings.get("voice", "voice", "")
            cur_lang = next((v.lang for v in voices if v.id == cur), None)
            idx = self.f_lang.findData(cur_lang) if cur_lang else -1
            if idx < 0:
                idx = next((i for i in range(self.f_lang.count())
                            if str(self.f_lang.itemData(i)).lower().startswith("vi")), 0)
            self.f_lang.setCurrentIndex(idx)
            self.f_lang.blockSignals(False)
            self.apply_filter()
            if not voices:
                self.lb_count.setText({"piper": "Chưa có giọng Piper nào - bấm 'Tải thêm giọng Piper'.",
                                       "sapi": "Không đọc được giọng hệ điều hành (cần cài pyttsx3)."}.get(
                    eng, "Không có giọng nào."))

        def fail(msg):
            self.lb_count.setText("❌ " + msg)
        self.app.run_task(lambda log, progress, cancel: tts.list_voices(eng, self.app.settings, refresh),
                          on_done=done, on_fail=fail, title="Tải danh sách giọng", quiet=True)

    def apply_filter(self):
        lang = self.f_lang.currentData() or ""
        gender = self.f_gender.currentData() or ""
        q = self.f_text.text().strip().lower()
        cur = self.app.settings.get("voice", "voice", "")
        self.list.blockSignals(True)
        self.list.clear()
        sel = None
        n = 0
        for v in self.voices:
            if lang and v.lang != lang:
                continue
            if gender and v.gender.lower() != gender.lower():
                continue
            if q and q not in v.label().lower() and q not in v.id.lower():
                continue
            it = QListWidgetItem(("👩 " if v.gender.lower() == "female" else "👨 " if v.gender.lower() == "male"
                                  else "🗣️ ") + v.label())
            it.setData(Qt.UserRole, v.id)
            it.setToolTip(v.id)
            self.list.addItem(it)
            n += 1
            if v.id == cur:
                sel = it
        self.list.blockSignals(False)
        if sel:
            self.list.setCurrentItem(sel)
        elif self.list.count():
            self.list.setCurrentRow(0)
        self.lb_count.setText(f"{n}/{len(self.voices)} giọng · Đang chọn: {self.app.settings.get('voice', 'voice')}"
                              " · Nhấp đúp để nghe thử")
        if lang.lower().startswith("vi") or not lang:
            if self.sample.toPlainText() in SAMPLE.values():
                self.sample.setPlainText(SAMPLE["vi"])
        elif self.sample.toPlainText() in SAMPLE.values():
            self.sample.setPlainText(SAMPLE["en"])

    def _pick(self, it, _prev=None):
        if it:
            self.app.binder._set("voice", "voice", it.data(Qt.UserRole))
            self.lb_count.setText(f"Đang chọn: {it.data(Qt.UserRole)}")

    # ------------------------------------------------ nghe thử
    def listen(self):
        text = self.sample.toPlainText().strip()
        if not text:
            return
        p = self.app.project
        opts = p.voice_opts() if p else dict(self.app.settings.section("voice"))
        eng, voice = opts["engine"], opts["voice"]
        if not voice:
            QMessageBox.information(self, "Giọng đọc", "Hãy chọn 1 giọng trong danh sách.")
            return
        out = Path(tempfile.gettempdir()) / f"recap_sample_{tts.voice_cache_key(eng, voice, text, opts)}.wav"

        def job(log, progress, cancel):
            if not out.exists():
                tts.synthesize(eng, text, voice, out, opts, self.app.settings, cancel)
            return str(out)
        self.app.run_task(job, on_done=self.audio.play, title="Đọc thử giọng")

    # ------------------------------------------------ Piper
    def piper_dialog(self):
        dlg = PiperDialog(self.app, self)
        dlg.exec()
        self.load_voices()


class PiperDialog(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("Tải giọng Piper (rhasspy/piper-voices)")
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        self.q = QLineEdit()
        self.q.setPlaceholderText("Lọc: vi_VN, en_US, ja, medium, high...")
        self.q.setText("vi_")
        self.q.textChanged.connect(self.fill)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.lb = muted("Đang tải danh sách...")
        lay.addWidget(self.q)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.lb)
        lay.addWidget(hrow("stretch", button("⬇ Tải giọng đã chọn", self.download, "primary"),
                           button("Đóng", self.accept)))
        self.catalog = {}
        app.run_task(lambda log, progress, cancel: tts.piper_catalog(app.settings), on_done=self._loaded,
                     title="Tải danh mục Piper", quiet=True)

    def _loaded(self, cat):
        self.catalog = cat
        self.fill()

    def fill(self):
        q = self.q.text().strip().lower()
        have = {p.stem for p in tts.piper_dir(self.app.settings).glob("*.onnx")}
        self.list.clear()
        for key, e in sorted(self.catalog.items()):
            lang = e.get("language", {})
            label = f"{key} · {lang.get('name_native', '')} ({lang.get('country_english', '')}) · " \
                    f"{e.get('quality')} · {e.get('num_speakers', 1)} giọng"
            if q and q not in label.lower():
                continue
            size = sum(f.get("size_bytes", 0) for p, f in e.get("files", {}).items() if p.endswith(".onnx"))
            it = QListWidgetItem(("✅ " if key in have else "") + label + f" · {size / 1e6:.0f} MB")
            it.setData(Qt.UserRole, key)
            self.list.addItem(it)
        self.lb.setText(f"{self.list.count()} giọng. Chọn (giữ Ctrl để chọn nhiều) rồi bấm Tải.")

    def download(self):
        keys = [i.data(Qt.UserRole) for i in self.list.selectedItems()]
        if not keys:
            return

        def job(log, progress, cancel):
            for k in keys:
                log(f"Tải giọng Piper {k}...")
                tts.piper_download(k, self.catalog[k], self.app.settings, progress)
            return True
        self.app.run_task(job, on_done=lambda _r: self.fill(), title="Tải giọng Piper")
