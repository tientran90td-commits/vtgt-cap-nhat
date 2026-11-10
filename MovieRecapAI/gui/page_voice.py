"""Trang 3: chọn giọng đọc từ nhiều engine, chỉnh tốc độ/cao độ/âm lượng, nghe thử."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from recap import textnorm, tts

from .player import AudioPlayer
from .widgets import LabeledSlider, Page, PathPicker, bind_labeled_slider, button, fill_combo, hrow, muted, scroll

SAMPLE = {
    "vi": "Chào mừng các bạn quay trở lại kênh. Hôm nay chúng ta sẽ cùng tóm tắt một bộ phim cực kỳ hấp dẫn, "
          "với cái kết không ai ngờ tới.",
    "en": "Welcome back to the channel. Today we're recapping an incredible movie with an ending nobody saw coming.",
}



class VoicePage(Page):
    def __init__(self, app):
        super().__init__(app, "🎙️  Bước 3 · Giọng đọc thuyết minh",
                         "Hơn 1000 giọng từ 12 công cụ: ⭐ VieNeu-TTS (AI giọng Việt chuẩn, offline), miễn phí (Edge TTS, gTTS), "
                         "offline (Piper, giọng Windows, XTTS) và cao cấp (ElevenLabs, OpenAI, Gemini, Google Cloud, "
                         "Azure, FPT.AI). Bật 'Phát âm chuẩn' để số, ngày tháng, tên riêng được đọc đúng.")
        b = app.binder
        self.voices: list[tts.Voice] = []
        body = QHBoxLayout()
        # ------------------------------------------------ trái: danh sách giọng
        left = QVBoxLayout()
        self.engine = b.combo(fill_combo(QComboBox(), {k: ("🔌 " if v["offline"] else "🌐 ") + v["name"]
                                                        for k, v in tts.ENGINES.items()}), "voice", "engine")
        self.engine.currentIndexChanged.connect(lambda _i: self.load_voices())
        self.lb_engine = muted("")
        self.btn_install = button("⬇ Cài ngay", self.install_engine, "primary")
        self.btn_install.setVisible(False)
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
        self.preset = QComboBox()
        self.preset.addItem("⭐ Giọng gợi ý - chọn nhanh...", None)
        for i, pr in enumerate(tts.VOICE_PRESETS):
            self.preset.addItem(pr["name"], i)
        self.preset.activated.connect(self.apply_preset)
        left.addWidget(self.preset)
        left.addWidget(self.engine)
        left.addWidget(hrow(self.lb_engine, self.btn_install, "stretch"))
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
        f.addRow("Model", self.model)
        right.addWidget(g)

        gs = QGroupBox("🎭 Cách đọc")
        fs = QFormLayout(gs)
        self.read_style = b.combo(fill_combo(QComboBox(), {k: v["name"] for k, v in tts.READ_STYLES.items()}),
                                  "voice", "read_style")
        self.read_custom = b.line(QLineEdit(), "voice", "read_custom")
        self.read_custom.setPlaceholderText("Tự mô tả, vd: giọng bựa, chém gió như dân chơi; hoặc trầm buồn sâu lắng")
        self.tone_auto = b.check(QCheckBox("Mỗi đoạn tự đổi cách đọc theo cảm xúc cảnh (AI gán ở bước 2)"),
                                 "voice", "tone_auto")
        self.lb_style = muted("")
        fs.addRow("Cách đọc chung", self.read_style)
        fs.addRow("Mô tả riêng", self.read_custom)
        fs.addRow(self.tone_auto)
        fs.addRow(self.lb_style)
        self.read_style.currentIndexChanged.connect(lambda _i: self._style_ui())
        g = gs
        right.addWidget(g)

        self.g_extra = QGroupBox("Tùy chọn riêng")
        fe = QFormLayout(self.g_extra)
        self.btn_piper = button("🔌 Kho giọng Piper: tải tất cả giọng / nhập giọng / đặt tên", self.piper_dialog,
                                "primary")
        self.xtts_ref = PathPicker("file", "Âm thanh (*.wav *.mp3 *.flac *.m4a)", "File giọng mẫu (VieNeu: 3-8 giây, XTTS: 6-30 giây)")
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

        gp = QGroupBox("🗣️ Phát âm chuẩn")
        fp = QVBoxLayout(gp)
        self.c_norm = b.check(QCheckBox("Tự đọc đúng số, ngày tháng, giờ, tiền, %, đơn vị, chữ viết tắt"),
                              "voice", "normalize")
        self.c_ai = b.check(QCheckBox("AI soát phát âm trước khi đọc (dùng AI đã chọn ở Bước 2)"), "voice", "ai_pron")
        self.c_tr = b.check(QCheckBox("Phiên âm tên nước ngoài sang tiếng Việt (Batman → Bát-men)"),
                            "voice", "transliterate")
        self.c_ai.toggled.connect(self.c_tr.setEnabled)
        self.c_tr.setEnabled(self.c_ai.isChecked())
        for w in (self.c_norm, self.c_ai, self.c_tr):
            fp.addWidget(w)
        fp.addWidget(hrow(button("📖 Từ điển phát âm", self.edit_dict, tip="Tự quy định cách đọc tên riêng, từ khó"),
                          button("🔎 Xem cách đọc", self.show_spoken, tip="Xem văn bản thực sự được đọc"), "stretch"))
        right.addWidget(gp)

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
        rs = scroll(rw)
        rs.setMinimumWidth(470)
        body.addWidget(rs, 4)
        self.root.addLayout(body, 1)
        self.audio = AudioPlayer(self, on_error=lambda m: app.log(m, "warn"), on_info=app.log)
        self._loaded_engine = None
        self._busy_ui = False
        self.model.currentTextChanged.connect(self._model_changed)

    def _model_changed(self, _t):
        # VieNeu: Turbo và Nano có bộ giọng khác nhau
        if not self._busy_ui and self.engine.currentData() == "vieneu" and self._loaded_engine == "vieneu":
            self.load_voices()

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
        self._busy_ui = True
        cur = self.app.settings.get("voice", "model", "")
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(info.get("models", []))
        self.model.blockSignals(False)
        self.model.setEnabled(bool(info.get("models")))
        if info.get("models"):
            self.model.setCurrentText(cur if cur in info["models"] else info["models"][0])
        self._style_ui()
        from recap import components

        missing = [m for m in components.ENGINE_NEEDS.get(eng, []) if not components.status(m, self.app.settings)[0]]
        self.btn_install.setVisible(bool(missing))
        if missing:
            self.lb_engine.setText(txt + "  ⚠️ Chưa cài công cụ này.")
        self._busy_ui = False
        self.g_extra.setVisible(eng in ("piper", "xtts", "vieneu"))
        self.btn_piper.setVisible(eng == "piper")
        self.xtts_ref.setVisible(eng in ("xtts", "vieneu"))
        self.xtts_dir.setVisible(eng == "xtts")
        fe = self.g_extra.layout()
        for w, show in ((self.xtts_ref, eng in ("xtts", "vieneu")), (self.xtts_dir, eng == "xtts")):
            lb = fe.labelForField(w)
            if lb:
                lb.setVisible(show)
        self.lb_extra.setText({
            "vieneu": "Model v3turbo: hay nhất (48kHz) · v3nano: nhẹ cho máy yếu. Lần đầu tự tải model. "
                      "Chọn '🎤 Nhân bản' + file mẫu 3-8 giây để đọc bằng giọng riêng.",
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

        self._load_seq = getattr(self, "_load_seq", 0) + 1
        seq = self._load_seq

        def done(voices):
            if seq != self._load_seq or eng != self.engine.currentData():
                return  # kết quả của lần tải cũ (người dùng đã đổi công cụ) - bỏ qua
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
            if seq == self._load_seq:
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

    def _style_ui(self):
        eng = self.engine.currentData()
        key = self.read_style.currentData()
        self.read_custom.setVisible(key == "custom")
        lb = self.read_style.parentWidget().layout().labelForField(self.read_custom)
        if lb:
            lb.setVisible(key == "custom")
        if eng in tts.EXPRESSIVE:
            how = {"openai": "OpenAI đọc theo mô tả cảm xúc", "gemini": "Gemini đọc theo mô tả cảm xúc",
                   "azure": "Azure dùng phong cách cảm xúc của giọng (giọng có hỗ trợ)",
                   "elevenlabs": "ElevenLabs chỉnh độ biểu cảm (model eleven_v3 có thêm thẻ cảm xúc)"}[eng]
        else:
            how = ("Công cụ này không điều khiển cảm xúc bằng lời - app tự chỉnh nhịp đọc & cao độ cho hợp "
                   "cách đọc. Muốn cảm xúc rõ hơn: dùng OpenAI (gpt-4o-mini-tts), Gemini TTS hoặc Azure.")
            if eng == "vieneu":
                hint = {"serious": "Mai Anh, Minh Đức (tin tức)", "warm": "Thiện Minh, Ngọc Linh (kể chuyện)",
                        "horror": "Thái Sơn, Thiền Tâm Đức (kể chuyện)", "funny": "Adam bựa",
                        "sad": "Mỹ Duyên, Quỳnh Anh (đọc truyện)", "dramatic": "Thiện Minh, Thanh Bình",
                        "kids": "Trúc Ly, Ngọc Huyền"}.get(key)
                if hint:
                    how += f" Giọng VieNeu hợp: {hint}."
        self.lb_style.setText(how)

    def apply_preset(self, idx):
        i = self.preset.itemData(idx)
        if i is None:
            return
        pr = tts.VOICE_PRESETS[i]
        b = self.app.binder
        b._set("voice", "voice", pr["voice"])
        if pr["engine"] == "vieneu":
            b._set("voice", "model", "v3turbo")
        self.rate.setValue(pr.get("rate", 0))
        self.pitch.setValue(pr.get("pitch", 0))
        self.read_style.setCurrentIndex(max(0, self.read_style.findData(pr.get("read_style", "natural"))))
        j = self.engine.findData(pr["engine"])
        if self.engine.currentIndex() != j:
            self.engine.setCurrentIndex(j)  # tự nạp lại danh sách giọng và chọn giọng ở trên
        else:
            self.load_voices()
        self.preset.setCurrentIndex(0)
        self.app.log(f"Đã chọn giọng gợi ý: {pr['name']}")
        if pr["engine"] == "piper" and not (tts.piper_dir(self.app.settings) / pr["voice"]).exists():
            self.app.log("Giọng Piper này chưa tải - bấm '🔌 Kho giọng Piper' để tải.", "warn")

    def install_engine(self):
        eng = self.engine.currentData()
        self.app.ensure(eng, then=lambda: (self.load_voices(refresh=True), self.app.log("Đã sẵn sàng - bấm Nghe thử.")))

    # ------------------------------------------------ nghe thử
    def listen(self):
        eng = self.engine.currentData()
        self.app.ensure(eng, then=self._listen)

    def _listen(self):
        text = self.sample.toPlainText().strip()
        if not text:
            return
        p = self.app.project
        opts = p.voice_opts() if p else dict(self.app.settings.section("voice"), lang_code=self._lang_code())
        eng, voice = opts["engine"], opts["voice"]
        if not voice:
            QMessageBox.information(self, "Giọng đọc", "Hãy chọn 1 giọng trong danh sách.")
            return
        out = Path(tempfile.gettempdir()) / f"recap_sample_{tts.voice_cache_key(eng, voice, text, opts)}.wav"

        def job(log, progress, cancel):
            if not out.exists() or out.stat().st_size < 1000:
                log(f"Đọc: {tts.speak_text(text, opts)[:160]}")
                tts.synthesize(eng, text, voice, out, opts, self.app.settings, cancel)
            return str(out)
        self.app.run_task(job, on_done=self.audio.play, title="Đọc thử giọng")

    # ------------------------------------------------ Phát âm
    def _lang_code(self):
        return tts.LANG_CODES.get(self.app.settings.get("script", "language", "Tiếng Việt"), "vi")

    def show_spoken(self):
        text = self.sample.toPlainText().strip()
        opts = dict(self.app.settings.section("voice"), lang_code=self._lang_code())
        QMessageBox.information(self, "Cách giọng AI sẽ đọc",
                                f"Văn bản gốc:\n{text}\n\nSẽ được đọc là:\n{tts.speak_text(text, opts)}"
                                + ("\n\n(+ AI soát phát âm khi xuất video)" if opts.get("ai_pron") else ""))

    def edit_dict(self):
        PronDictDialog(self).exec()

    # ------------------------------------------------ Piper
    def piper_dialog(self):
        # không chặn cửa sổ chính để còn bấm ⏹ Hủy khi đang tải nhiều giọng
        self._piper_dlg = PiperDialog(self.app, self)
        self._piper_dlg.finished.connect(lambda _r: self.load_voices())
        self._piper_dlg.show()


class PiperDialog(QDialog):
    """Kho giọng Piper offline: tải tất cả giọng chính thức, giọng cộng đồng trên HuggingFace, nhập file."""

    def __init__(self, app, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QTabWidget

        self.app = app
        self.setWindowTitle("🔌 Kho giọng Piper (offline)")
        self.resize(860, 640)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Giọng Piper chạy hoàn toàn offline sau khi tải. Tiến trình tải hiện ở thanh dưới cửa sổ "
                            "chính (bấm ⏹ Hủy ở đó để dừng). Giọng đã tải sẽ không tải lại."))
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)
        tabs.addTab(self._tab_official(), "📚 Kho chính thức (rhasspy)")
        tabs.addTab(self._tab_hf(), "🤗 Repo HuggingFace (cộng đồng)")
        tabs.addTab(self._tab_file(), "📁 Nhập từ file")
        tabs.addTab(self._tab_installed(), "✅ Giọng đã có")
        lay.addWidget(hrow("stretch", button("Đóng", self.accept)))
        self.catalog: dict = {}
        self.hf_items: list[dict] = []
        app.run_task(lambda log, progress, cancel: tts.piper_catalog(app.settings), on_done=self._loaded,
                     on_fail=lambda m: self.lb.setText("❌ Không tải được danh mục: " + m),
                     title="Tải danh mục Piper", quiet=True)

    # ---------------- kho chính thức
    def _tab_official(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.q = QLineEdit()
        self.q.setPlaceholderText("Lọc: vi_VN, en_US, ja, medium, high... (để trống = tất cả)")
        self.q.setText("vi_")
        self.q.textChanged.connect(self.fill)
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.lb = muted("Đang tải danh mục...")
        v.addWidget(self.q)
        v.addWidget(self.list, 1)
        v.addWidget(self.lb)
        v.addWidget(hrow(button("Chọn hết đang lọc", self.list.selectAll),
                         button("⬇ Tải đã chọn", self.download_selected, "primary"),
                         button("⬇ Tải tất cả đang lọc", self.download_filtered),
                         "stretch",
                         button("🇻🇳 Tải tất cả giọng tiếng Việt", lambda: self.download_prefix("vi_")),
                         button("🌍 Tải TẤT CẢ giọng Piper", self.download_all, "big")))
        return w

    def _loaded(self, cat):
        self.catalog = cat
        self.fill()

    def fill(self):
        q = self.q.text().strip().lower()
        have = tts.piper_installed(self.app.settings)
        self.list.clear()
        n = size = 0
        for key, e in sorted(self.catalog.items()):
            lang = e.get("language", {})
            label = (f"{key} · {lang.get('name_native', '')} ({lang.get('country_english', '')}) · "
                     f"{e.get('quality')} · {e.get('num_speakers', 1)} giọng")
            if q and q not in label.lower():
                continue
            sz = tts.piper_entry_size(e)
            it = QListWidgetItem(("✅ " if key in have else "⬜ ") + label + f" · {sz / 1e6:.0f} MB")
            it.setData(Qt.UserRole, key)
            self.list.addItem(it)
            n += 1
            size += 0 if key in have else sz
        total = len(self.catalog)
        self.lb.setText(f"{n} giọng (tổng kho: {total} giọng · {len(have & set(self.catalog))} đã tải) · "
                        f"cần tải thêm cho danh sách này ≈ {size / 1e9:.2f} GB")

    def _start(self, keys: list[str], label: str):
        have = tts.piper_installed(self.app.settings)
        todo = [k for k in keys if k not in have]
        if not todo:
            QMessageBox.information(self, "Piper", "Các giọng này đã có đủ trên máy.")
            return
        size = sum(tts.piper_entry_size(self.catalog[k]) for k in todo)
        if size > 2e9 and QMessageBox.question(
                self, "Tải nhiều giọng", f"Sẽ tải {len(todo)} giọng, khoảng {size / 1e9:.1f} GB. "
                                         "Cần ổ cứng trống và có thể mất khá lâu. Tiếp tục?") != QMessageBox.Yes:
            return

        def job(log, progress, cancel):
            return tts.piper_download_many(todo, self.catalog, self.app.settings, log, progress, cancel)

        def done(errors):
            self.fill()
            self.refresh_installed()
            if errors:
                QMessageBox.warning(self, "Một số giọng lỗi", "\n".join(errors)[:3000])
            else:
                self.app.log(f"✅ Đã tải xong {len(todo)} giọng Piper.")
        self.app.run_task(job, on_done=done, title=label)

    def download_selected(self):
        self._start([i.data(Qt.UserRole) for i in self.list.selectedItems()], "Tải giọng Piper")

    def download_filtered(self):
        self._start([self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())], "Tải giọng Piper")

    def download_prefix(self, prefix):
        self._start([k for k in self.catalog if k.startswith(prefix)], "Tải giọng Piper tiếng Việt")

    def download_all(self):
        self._start(list(self.catalog), "Tải tất cả giọng Piper")

    # ---------------- repo HuggingFace
    def _tab_hf(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(muted("Dán tên repo HuggingFace chứa giọng Piper (file .onnx + .onnx.json), ví dụ giọng tiếng Việt "
                          "cộng đồng chia sẻ. Repo cần đăng nhập: vào trang repo bấm 'Agree' rồi dán HuggingFace token "
                          "ở mục 🔑 API & Cài đặt."))
        self.repo = QLineEdit()
        self.repo.setPlaceholderText("vd: rhasspy/piper-voices  hoặc  https://huggingface.co/<tên>/<repo>")
        self.hf_list = QListWidget()
        self.hf_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.hf_lb = muted("")
        v.addWidget(hrow(self.repo, button("🔍 Liệt kê giọng", self.hf_scan, "primary"), stretch_last=False))
        v.addWidget(self.hf_list, 1)
        v.addWidget(self.hf_lb)
        v.addWidget(hrow(button("Chọn hết", self.hf_list.selectAll),
                         button("⬇ Tải đã chọn", self.hf_download, "primary"), "stretch"))
        return w

    def hf_scan(self):
        repo = self.repo.text().strip()
        if not repo:
            return
        self.hf_lb.setText("Đang đọc repo...")

        def done(items):
            self.hf_items = items
            self.hf_list.clear()
            have = tts.piper_installed(self.app.settings)
            for it in items:
                li = QListWidgetItem(("✅ " if it["local"] in have else "⬜ ") + f"{it['onnx']}  →  {it['local']}")
                li.setData(Qt.UserRole, it)
                self.hf_list.addItem(li)
            self.hf_lb.setText(f"{len(items)} giọng Piper trong repo" + (" (repo cần đăng nhập)" if items and
                                                                         items[0]["gated"] else ""))
        self.app.run_task(lambda log, progress, cancel: tts.hf_list_piper(repo, self.app.settings), on_done=done,
                          on_fail=lambda m: self.hf_lb.setText("❌ " + m), title="Đọc repo", quiet=True)

    def hf_download(self):
        items = [i.data(Qt.UserRole) for i in self.hf_list.selectedItems()]
        if not items:
            return

        def job(log, progress, cancel):
            for n, it in enumerate(items):
                log(f"⬇ [{n + 1}/{len(items)}] {it['repo']}/{it['onnx']}")
                tts.hf_download_piper(it, self.app.settings,
                                      lambda p, m="", n=n: progress((n + p) / len(items), m), cancel)
            return True
        self.app.run_task(job, on_done=lambda _r: (self.hf_scan(), self.refresh_installed()),
                          title="Tải giọng Piper từ HuggingFace")

    # ---------------- nhập file
    def _tab_file(self):
        w = QWidget()
        f = QFormLayout(w)
        self.f_onnx = PathPicker("file", "Model Piper (*.onnx)", "File model .onnx")
        self.f_json = PathPicker("file", "Cấu hình (*.json)", "(tự tìm) file .onnx.json đi kèm")
        self.f_name = QLineEdit()
        self.f_name.setPlaceholderText("Tên hiển thị, vd: Ngọc Huyền")
        self.f_gender = fill_combo(QComboBox(), {"Female": "Nữ", "Male": "Nam", "": "Không rõ"})
        self.f_desc = QLineEdit()
        self.f_desc.setPlaceholderText("Mô tả, vd: nữ hoạt ngôn, miền Bắc")
        f.addRow(muted("Có sẵn file giọng Piper (do bạn tải hoặc tự huấn luyện)? Nhập vào đây để dùng offline."))
        f.addRow("Model .onnx", self.f_onnx)
        f.addRow("Cấu hình .json", self.f_json)
        f.addRow("Tên giọng", self.f_name)
        f.addRow("Giới tính", self.f_gender)
        f.addRow("Mô tả", self.f_desc)
        f.addRow(hrow(button("📥 Nhập giọng", self.do_import, "primary"), "stretch"))
        return w

    def do_import(self):
        try:
            out = tts.piper_import(self.f_onnx.text(), self.f_json.text() or None, self.app.settings,
                                   self.f_name.text(), self.f_gender.currentData(), self.f_desc.text())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Nhập giọng", str(e))
            return
        self.app.log(f"✅ Đã nhập giọng Piper: {out.name}")
        self.refresh_installed()

    # ---------------- giọng đã có
    def _tab_installed(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self.inst = QListWidget()
        v.addWidget(self.inst, 1)
        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("Tên hiển thị (vd: Ngọc Huyền)")
        self.e_gender = fill_combo(QComboBox(), {"Female": "Nữ", "Male": "Nam", "": "Không rõ"})
        self.e_desc = QLineEdit()
        self.e_desc.setPlaceholderText("Mô tả (vd: nữ hoạt ngôn)")
        v.addWidget(hrow(self.e_name, self.e_gender, self.e_desc, button("💾 Đặt tên", self.save_meta, "primary"),
                         button("🗑 Xóa giọng", self.delete_voice, "danger")))
        self.inst.currentItemChanged.connect(self._pick_inst)
        self.refresh_installed()
        return w

    def refresh_installed(self):
        self.inst.clear()
        for vo in tts.list_voices("piper", self.app.settings):
            it = QListWidgetItem(vo.label())
            it.setData(Qt.UserRole, vo)
            self.inst.addItem(it)

    def _pick_inst(self, it, _prev=None):
        if not it:
            return
        vo = it.data(Qt.UserRole)
        m = tts.piper_meta(self.app.settings).get(vo.id, {})
        self.e_name.setText(m.get("name", ""))
        self.e_gender.setCurrentIndex(max(0, self.e_gender.findData(m.get("gender", ""))))
        self.e_desc.setText(m.get("desc", ""))

    def save_meta(self):
        it = self.inst.currentItem()
        if it:
            vo = it.data(Qt.UserRole)
            tts.piper_set_meta(self.app.settings, vo.id, self.e_name.text(), self.e_gender.currentData(),
                               self.e_desc.text())
            self.refresh_installed()

    def delete_voice(self):
        it = self.inst.currentItem()
        if it and QMessageBox.question(self, "Xóa giọng", f"Xóa giọng {it.text()}?") == QMessageBox.Yes:
            tts.piper_delete(it.data(Qt.UserRole).id, self.app.settings)
            self.refresh_installed()
            self.fill()


class PronDictDialog(QDialog):
    """Từ điển phát âm: quy định cách đọc tên riêng, từ nước ngoài, từ hay bị đọc sai."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📖 Từ điển phát âm")
        self.resize(620, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(muted("Mỗi dòng: từ/cụm từ trong kịch bản → cách đọc. Áp dụng cho mọi giọng, phụ đề vẫn giữ chữ gốc. "
                            "Ví dụ: 'Thanos' → 'Tha-nốt', 'MCU' → 'em xi diu', 'DiCaprio' → 'Đi-ca-pri-ô'."))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Từ trong kịch bản", "Đọc là", "Aa"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeaderItem(2).setToolTip("Tích = phân biệt chữ hoa/thường")
        self.table.setColumnWidth(2, 44)
        lay.addWidget(self.table, 1)
        for e in textnorm.load_dict():
            self._add(e)
        self.test = QLineEdit()
        self.test.setPlaceholderText("Gõ câu để thử, vd: Năm 2019 Thanos búng tay xóa 50% sự sống")
        self.out = muted("")
        self.test.textChanged.connect(self._try)
        lay.addWidget(self.test)
        lay.addWidget(self.out)
        lay.addWidget(hrow(button("➕ Thêm", lambda: self._add({})), button("➖ Xóa", self._del),
                           button("📥 Nhập", self._import), button("📤 Xuất", self._export),
                           button("↺ Mặc định", self._reset), "stretch",
                           button("💾 Lưu", self._save, "primary"), button("Đóng", self.reject)))

    def _add(self, e):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(e.get("from", "")))
        self.table.setItem(r, 1, QTableWidgetItem(e.get("to", "")))
        it = QTableWidgetItem()
        it.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        it.setCheckState(Qt.Checked if e.get("case") else Qt.Unchecked)
        self.table.setItem(r, 2, it)
        if not e:
            self.table.editItem(self.table.item(r, 0))

    def _del(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def entries(self):
        out = []
        for r in range(self.table.rowCount()):
            a = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            b = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            c = self.table.item(r, 2).checkState() == Qt.Checked if self.table.item(r, 2) else False
            if a:
                out.append({"from": a, "to": b, "case": c})
        return out

    def _try(self, t):
        self.out.setText("→ " + textnorm.prepare(t, "vi", True, self.entries()) if t.strip() else "")

    def _save(self):
        textnorm.save_dict(self.entries())
        self.accept()

    def _reset(self):
        self.table.setRowCount(0)
        for e in textnorm.DEFAULT_DICT:
            self._add(e)

    def _import(self):
        f, _ = QFileDialog.getOpenFileName(self, "Nhập từ điển", "", "Từ điển (*.json *.csv *.txt)")
        if not f:
            return
        import csv
        import json

        if f.lower().endswith(".json"):
            items = json.loads(Path(f).read_text(encoding="utf-8"))
        else:
            items = []
            for row in csv.reader(Path(f).read_text(encoding="utf-8-sig").splitlines()):
                if len(row) >= 2 and row[0].strip():
                    items.append({"from": row[0].strip(), "to": row[1].strip()})
        for e in items:
            self._add(e)

    def _export(self):
        f, _ = QFileDialog.getSaveFileName(self, "Xuất từ điển", "tu_dien_phat_am.json", "JSON (*.json)")
        if f:
            import json

            Path(f).write_text(json.dumps(self.entries(), ensure_ascii=False, indent=2), encoding="utf-8")
