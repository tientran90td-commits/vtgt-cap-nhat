"""Trang 2: nhận dạng lời thoại + AI viết kịch bản + chỉnh sửa kịch bản."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                               QHeaderView, QLineEdit, QMessageBox,
                               QPlainTextEdit, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from recap import llm, script_writer, transcribe, tts
from recap.ffmpeg_utils import fmt_ts, parse_ts

from .player import AudioPlayer, VideoPlayer
from .widgets import Page, PathPicker, button, fill_combo, hrow, muted, scroll, spin

COLS = ["#", "Bắt đầu", "Kết thúc", "Lời thuyết minh (sửa trực tiếp · trống = giữ thoại gốc)", "Cách đọc",
        "Ghi chú cảnh"]
TONE_COL = 4


class ScriptPage(Page):
    def __init__(self, app):
        super().__init__(app, "📝  Bước 2 · Lời thoại & Kịch bản AI",
                         "① Nhận dạng lời thoại của phim → ② AI đọc hiểu và viết kịch bản tóm tắt, tự chọn cảnh "
                         "minh họa → sửa lại tùy ý trong bảng bên phải.")
        b = app.binder
        split = QSplitter(Qt.Horizontal)
        # ------------------------------------------------ cột trái: thiết lập
        from PySide6.QtWidgets import QTabWidget

        self.tabs = QTabWidget()
        g1 = QWidget()
        f1 = QFormLayout(g1)
        self.stt_engine = b.combo(fill_combo(QComboBox(), transcribe.ENGINES), "transcribe", "engine")
        self.stt_model = b.combo(fill_combo(QComboBox(), transcribe.WHISPER_MODELS), "transcribe", "model")
        self.stt_lang = b.combo(fill_combo(QComboBox(), transcribe.LANGUAGES), "transcribe", "language")
        self.stt_dev = b.combo(fill_combo(QComboBox(), {"auto": "Tự động (GPU nếu có)", "cpu": "CPU",
                                                         "cuda": "GPU NVIDIA (CUDA)"}), "transcribe", "device")
        self.sub_file = PathPicker("file", "Phụ đề (*.srt *.vtt *.ass *.ssa)", "Chọn file .srt/.vtt/.ass")
        self.scenes = b.check(QCheckBox("Dò chuyển cảnh (cắt clip đẹp hơn)"),
                              "transcribe", "use_scenes")
        f1.addRow("Công cụ", self.stt_engine)
        f1.addRow("Model Whisper", self.stt_model)
        f1.addRow("Ngôn ngữ phim", self.stt_lang)
        f1.addRow("Thiết bị", self.stt_dev)
        f1.addRow("File phụ đề", self.sub_file)
        f1.addRow(self.scenes)
        f1.addRow(muted("Mẹo: 'Tự chọn' dùng large-v3-turbo (chính xác cao) nếu máy có GPU NVIDIA hoặc CPU từ 8 luồng. "
                        "Máy không có card NVIDIA mà muốn nhanh: dùng Groq Whisper API (miễn phí). "
                        "Phim có sẵn phụ đề thì dùng phụ đề là nhanh và chuẩn nhất."))
        self.lb_tr = muted("")
        f1.addRow(hrow(button("① Nhận dạng thoại", self.do_transcribe, "primary"),
                       button("👁 Xem lời thoại", self.show_transcript), "stretch"))
        f1.addRow(self.lb_tr)
        self.stt_engine.currentIndexChanged.connect(self._stt_ui)

        g2 = QWidget()
        f2 = QFormLayout(g2)
        self.provider = b.combo(fill_combo(QComboBox(), {k: v["name"] for k, v in llm.PROVIDERS.items()}),
                                "script", "provider")
        self.model = fill_combo(QComboBox(), [])
        b.edit_combo(self.model, "script", "model")
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.lb_prov = muted("")
        self.mode = b.combo(fill_combo(QComboBox(), script_writer.MODES), "script", "mode")
        self.style = b.combo(fill_combo(QComboBox(), {k: v["name"] for k, v in script_writer.STYLES.items()}),
                             "script", "style")
        self.lang = b.edit_combo(fill_combo(QComboBox(), script_writer.OUTPUT_LANGUAGES), "script", "language")
        self.lb_minutes = muted("")
        self.lb_minutes.setWordWrap(False)
        self.spoiler = b.check(QCheckBox("Kể cả cái kết (spoil)"), "script", "spoiler")
        self.custom = QPlainTextEdit()
        self.custom.setPlaceholderText("Yêu cầu thêm cho AI, ví dụ: gọi nhân vật chính là 'thanh niên', "
                                       "mở đầu bằng câu hỏi gây tò mò, nhấn mạnh tình tiết phản bội...")
        self.custom.setMaximumHeight(80)
        b.text(self.custom, "script", "custom")
        f2.addRow("Nhà cung cấp AI", self.provider)
        f2.addRow("Model", hrow(self.model, button("🔄", self.refresh_models, tip="Lấy danh sách model"),
                                stretch_last=False))
        f2.addRow(self.lb_prov)
        f2.addRow(hrow(button("⚡ Lấy key miễn phí → tự động hoàn toàn", self.key_wizard,
                              tip="Mở trang lấy key Gemini miễn phí, bấm Copy là app tự lưu & dùng"), "stretch"))
        self.web_inapp = b.check(QCheckBox("Mở trang AI ngay trong app"), "script", "web_inapp")
        self.btn_login = button("🔐 Đăng nhập AI web", self.web_login, "primary")
        self.web_row = hrow(self.btn_login, self.web_inapp, "stretch")
        f2.addRow(self.web_row)
        f2.addRow("Kiểu video", self.mode)
        f2.addRow("Phong cách", self.style)
        f2.addRow("Ngôn ngữ kể", self.lang)
        f2.addRow("Độ dài video", hrow(self.lb_minutes, button("⏱ Đổi thời lượng", lambda: self.app.goto(3),
                                                              tip="Chỉnh ở Bước 4 → ô Thời lượng"),
                                       self.spoiler, "stretch"))
        f2.addRow("Yêu cầu thêm", self.custom)
        f2.addRow(hrow(button("② AI viết kịch bản", self.do_script, "primary"), "stretch"))

        # ---- thẻ Nâng cao
        g3 = QWidget()
        f3 = QFormLayout(g3)
        self.persp = b.combo(fill_combo(QComboBox(), script_writer.PERSPECTIVES), "script", "perspective")
        self.focus = b.line(QLineEdit(), "script", "focus_character")
        self.focus.setPlaceholderText("Tên nhân vật (khi kể qua góc nhìn nhân vật)")
        self.cands = b.spin(spin(1, 3, 1, " phương án"), "script", "candidates")
        self.cands.setToolTip("AI viết 2-3 kịch bản khác nhau rồi tự chấm điểm & chọn bản hay nhất (tốn thêm lượt AI)")
        self.lb_ref = muted("")
        self.fallback = b.check(QCheckBox("AI này hết tiền/quá tải → tự chuyển sang AI khác đã nhập key"),
                                "script", "auto_fallback")
        self.web_max = b.spin(spin(5000, 1000000, 5000, " ký tự/lần dán"), "script", "web_max_chars")
        self.web_max.setToolTip("Phim dài hơn mức này sẽ được chia thành nhiều lần copy-dán. "
                                "ChatGPT/Gemini web: 30.000-60.000 · Google AI Studio: 300.000+")
        f3.addRow("Góc nhìn người kể", self.persp)
        f3.addRow("Nhân vật", self.focus)
        f3.addRow("Số phương án", self.cands)
        f3.addRow(muted("2-3 phương án: AI viết nhiều bản (mở đầu gắt hơn / kể rõ ràng hơn), chấm điểm độ cuốn hút, "
                        "độ chính xác, độ dài - rồi chọn bản hay nhất."))
        f3.addRow("Học phong cách", hrow(button("🎯 Chọn video recap mẫu", self.pick_style_ref, "primary"),
                                         button("✕ Bỏ", self.clear_style_ref), "stretch"))
        f3.addRow(self.lb_ref)
        f3.addRow(self.fallback)
        f3.addRow("Bản web", self.web_max)

        def top(w):  # dồn các ô lên trên, không giãn cách khi cửa sổ cao
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(8, 8, 8, 8)
            v.addWidget(w)
            v.addStretch(1)
            return scroll(box)
        self.tabs.addTab(top(g1), "① Lời thoại")
        self.tabs.addTab(top(g2), "② AI viết kịch bản")
        self.tabs.addTab(top(g3), "⚙️ Nâng cao")
        self.tabs.setCurrentIndex(1)
        self.model.setMinimumWidth(220)

        # ------------------------------------------------ cột phải: kịch bản
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        self.title = QLineEdit()
        self.title.setPlaceholderText("Tiêu đề video")
        self.title.textEdited.connect(self._meta_changed)
        self.desc = QLineEdit()
        self.desc.setPlaceholderText("Mô tả ngắn để đăng kèm video")
        self.desc.textEdited.connect(self._meta_changed)
        rl.addWidget(self.title)
        rl.addWidget(self.desc)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Interactive)
        hh.setSectionResizeMode(5, QHeaderView.Interactive)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 110)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._item_changed)
        self.table.cellDoubleClicked.connect(lambda r, c: self.preview() if c in (0, 1, 2) else None)
        rl.addWidget(self.table, 1)
        tb = hrow(button("➕ Thêm", self.add_row), button("➖ Xóa", self.del_row),
                  button("⬆", lambda: self.move(-1)), button("⬇", lambda: self.move(1)),
                  button("▶ Xem cảnh", self.preview, tip="Xem đoạn phim gốc của dòng đang chọn"),
                  button("🔊 Nghe thử", self.listen, tip="Đọc thử lời thuyết minh bằng giọng đã chọn"),
                  "stretch")
        rl.addWidget(tb)
        self.lb_est = muted("")
        rl.addWidget(hrow(self.lb_est, "stretch", button("📂 Mở", self.open_script),
                          button("💾 Lưu", self.save_script), button("📄 TXT", self.export_txt),
                          button("Tiếp: Giọng đọc →", lambda: self.app.goto(2), "primary")))
        self.tabs.setMinimumWidth(450)
        split.addWidget(self.tabs)
        split.addWidget(right)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 7)

        self.root.addWidget(split, 1)
        self._loading = False
        self.audio = AudioPlayer(self, on_error=lambda m: app.log(m, "warn"), on_info=app.log)
        self._provider_changed(init=True)
        self._stt_ui()
        self._ref_label()

    # ------------------------------------------------ UI helpers
    def _stt_ui(self):
        e = self.stt_engine.currentData()
        self.sub_file.setEnabled(e == "subtitle")
        self.stt_model.setEnabled(e in ("faster_whisper", "whisper_gpu"))
        self.stt_dev.setEnabled(e == "faster_whisper")

    def _provider_changed(self, *_a, init=False):
        pid = self.provider.currentData()
        p = llm.PROVIDERS.get(pid, {})
        cur = self.model.currentText()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(p.get("models", []))
        self.model.blockSignals(False)
        if init and cur:
            self.model.setCurrentText(cur)
        else:
            self.model.setCurrentText((p.get("models") or [""])[0])
        note = p.get("note", "")
        if "auto" in p.get("models", []):
            note = "Model 'auto' = app tự chọn bản mới nhất còn dùng được. " + note
        key = p.get("key")
        if key and not self.app.settings.get("api", key):
            note = "⚠️ Chưa nhập API key - vào mục 🔑 API & Cài đặt. " + note
        self.lb_prov.setText(note)
        if hasattr(self, "web_row"):
            self.web_row.setVisible(pid == "web")
        if hasattr(self, "web_max"):
            self.web_max.setVisible(pid == "web")
            lb = self.web_max.parentWidget().layout().labelForField(self.web_max)
            if lb:
                lb.setVisible(pid == "web")

    def _ref_label(self):
        ref = self.app.settings.get("script", "style_ref")
        self.lb_ref.setText(f"🎯 Đang học theo: {ref['name']} · {ref['wps']} từ/giây · cảnh ~{ref['avg_cut']}s · "
                            f"{ref['target_minutes']} phút" if ref else
                            "Chọn 1 video recap bạn thích (vd video review đang viral): app đo nhịp đọc, độ dài cảnh, "
                            "giọng văn để AI viết theo phong cách đó (không chép nội dung).")

    def pick_style_ref(self):
        f, _ = QFileDialog.getOpenFileName(self, "Video recap mẫu", "", "Video (*.mp4 *.mkv *.mov *.webm *.avi)")
        if not f:
            return
        from recap import style_ref

        def done(ref):
            self.app.settings.set("script", "style_ref", ref)
            self.app.settings.save()
            self._ref_label()
            if QMessageBox.question(self, "Độ dài video", f"Video mẫu dài {ref['target_minutes']} phút. Đặt độ dài recap "
                                    "giống video mẫu?") == QMessageBox.Yes:
                self.app.settings.set("script", "target_minutes", max(0.5, ref["target_minutes"]))
                self.on_show()
        self.app.run_task(style_ref.analyze, f, self.app.settings, on_done=done, title="Học phong cách video mẫu")

    def clear_style_ref(self):
        self.app.settings.set("script", "style_ref", None)
        self.app.settings.save()
        self._ref_label()

    def web_login(self):
        from .web_chat import LoginDialog

        LoginDialog(self, self.model.currentText() or "aistudio").exec()

    def key_wizard(self):
        from .web_chat import KeyWizard

        dlg = KeyWizard(self.app)
        dlg.exec()
        if dlg.got:
            i = self.provider.findData(dlg.got)
            self.provider.setCurrentIndex(i)
            self._provider_changed()
            self.app.pages[0].on_show()

    def refresh_models(self):
        pid = self.provider.currentData()

        def done(models):
            cur = self.model.currentText()
            self.model.clear()
            self.model.addItems(models)
            self.model.setCurrentText(cur if cur in models else (models[0] if models else cur))
            self.app.log(f"{len(models)} model từ {llm.PROVIDERS[pid]['name']}")
        self.app.run_task(lambda log, progress, cancel: llm.list_models(pid, self.app.settings), on_done=done,
                          title="Lấy danh sách model")

    def on_show(self):
        v = float(self.app.settings.get("script", "target_minutes", 5) or 5)
        self.lb_minutes.setText(f"<b>{v:g} phút</b>")
        self._provider_changed(init=True)
        self.refresh_transcript_label()

    def refresh_transcript_label(self):
        p = self.app.project
        if p and p.transcript:
            self.lb_tr.setText(f"✅ Đã có {len(p.transcript)} câu thoại "
                               f"({fmt_ts(p.transcript[0]['start'])} → {fmt_ts(p.transcript[-1]['end'])})")
        else:
            self.lb_tr.setText("Chưa có lời thoại.")

    # ------------------------------------------------ actions
    def do_transcribe(self):
        p = self.app.require_project()
        if not p:
            return
        engine = self.stt_engine.currentData()
        sub = self.sub_file.text() or self.app.pending_subtitle

        def job(log, progress, cancel):
            sc = self.app.settings.section("script")
            if sc.get("identify", True) and sc.get("provider") != "none" and not p.film:
                try:
                    p.run_identify(log, lambda x, m="": progress(x * 0.05, m), cancel)
                except Exception as e:  # noqa: BLE001
                    log(f"Không nhận diện được phim ({e}) - tiếp tục.", level="warn")
            p.run_transcribe(log, progress, cancel, subtitle_file=sub, engine=engine)
            if self.app.settings.get("transcribe", "use_scenes", True) and p.scenes is None:
                p.run_scenes(log, progress, cancel)
            return True

        def go():
            self.app.run_task(job, on_done=lambda _r: (self.refresh_transcript_label(), self.app.refresh(),
                                                       self.app.pages[0].load_film()),
                              title="Nhận dạng lời thoại")
        self.app.ensure(stt=engine, then=go, include_models=False)

    def show_transcript(self):
        p = self.app.project
        if not p or not p.transcript:
            QMessageBox.information(self, "Lời thoại", "Chưa có lời thoại.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Lời thoại phim")
        dlg.resize(760, 600)
        lay = QVBoxLayout(dlg)
        ed = QPlainTextEdit("\n".join(f"[{fmt_ts(s['start'])}] {s['text']}" for s in p.transcript))
        ed.setReadOnly(True)
        lay.addWidget(ed)
        dlg.exec()

    def do_script(self):
        p = self.app.require_project()
        if not p:
            return
        if not p.transcript and self.provider.currentData() != "none":
            QMessageBox.warning(self, "Thiếu lời thoại", "Hãy bấm ① Nhận dạng thoại trước (hoặc nạp file phụ đề).")
            return
        self.app.run_task(p.run_script, on_done=lambda _r: (self.load_script(), self.app.refresh()),
                          title="AI viết kịch bản")

    # ------------------------------------------------ bảng kịch bản
    def load_script(self):
        p = self.app.project
        sc = (p.script if p else None) or {"title": "", "description": "", "segments": []}
        self._loading = True
        self.title.setText(sc.get("title", ""))
        self.desc.setText(sc.get("description", ""))
        self.table.setRowCount(0)
        for s in sc.get("segments", []):
            self._append(s)
        self._loading = False
        self.table.resizeRowsToContents()
        self._estimate()

    def _append(self, s, row=None):
        r = self.table.rowCount() if row is None else row
        self.table.insertRow(r)
        vals = [str(r + 1), fmt_ts(s["start"]), fmt_ts(s["end"]), s.get("narration", ""), "", s.get("scene", "")]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if c == 0:
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setTextAlignment(Qt.AlignCenter)
            if c == 3 and s.get("sentences"):
                it.setData(Qt.UserRole, s["sentences"])  # mốc phim từng câu (khớp tiếng-hình theo câu)
                it.setToolTip("🎯 Khớp hình theo từng câu:\n" + "\n".join(
                    f"{fmt_ts(x['start'])} · {x['text']}" for x in s["sentences"]))
            self.table.setItem(r, c, it)
        cb = QComboBox()
        cb.addItem("— cách đọc chung —", "")
        for k in tts.TONE_KEYS:
            cb.addItem(tts.READ_STYLES[k]["name"], k)
        i = cb.findData(s.get("tone") or "")
        cb.setCurrentIndex(max(0, i))
        cb.currentIndexChanged.connect(lambda _i: self._commit())
        self.table.setCellWidget(r, TONE_COL, cb)

    def collect(self) -> dict:
        segs = []
        for r in range(self.table.rowCount()):
            g = lambda c: (self.table.item(r, c).text() if self.table.item(r, c) else "")  # noqa: E731
            st, en = parse_ts(g(1)), parse_ts(g(2))
            if en <= st:
                en = st + 8
            cb = self.table.cellWidget(r, TONE_COL)
            seg = {"start": st, "end": en, "narration": g(3).strip(), "scene": g(5).strip(),
                   "tone": (cb.currentData() if cb else "") or ""}
            sents = self.table.item(r, 3).data(Qt.UserRole) if self.table.item(r, 3) else None
            if sents:
                from recap.footage import valid_sentences

                if valid_sentences(dict(seg, sentences=sents)):
                    seg["sentences"] = sents
            segs.append(seg)
        return {"title": self.title.text().strip(), "description": self.desc.text().strip(), "segments": segs}

    def _commit(self):
        p = self.app.project
        if not p or self._loading:
            return
        p.script = self.collect()
        p.save()
        self._estimate()

    def _item_changed(self, _it):
        if not self._loading:
            self._commit()

    def _meta_changed(self, *_):
        self._commit()

    def _renumber(self):
        self._loading = True
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            if it:
                it.setText(str(r + 1))
        self._loading = False

    def _estimate(self):
        sc = self.collect()
        words = sum(len(s["narration"].split()) for s in sc["segments"])
        clip = sum(s["end"] - s["start"] for s in sc["segments"] if not s["narration"])
        est = words / 2.8 + clip + 0.35 * len(sc["segments"])
        self.lb_est.setText(f"{len(sc['segments'])} đoạn · {words} từ thuyết minh · "
                            f"ước tính video ≈ {int(est // 60)} phút {int(est % 60)} giây")

    def add_row(self):
        r = self.table.currentRow()
        base = self.collect()["segments"]
        start = base[r]["end"] if 0 <= r < len(base) else 0
        self._loading = True
        self._append({"start": start, "end": start + 10, "narration": "", "scene": ""},
                     row=(r + 1) if r >= 0 else None)
        self._loading = False
        self._renumber()
        self._commit()

    def del_row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._renumber()
        self._commit()

    def move(self, d):
        r = self.table.currentRow()
        if r < 0 or not (0 <= r + d < self.table.rowCount()):
            return
        segs = self.collect()["segments"]
        segs[r], segs[r + d] = segs[r + d], segs[r]
        p = self.app.project
        if p:
            p.script["segments"] = segs
        self._loading = True
        self.table.setRowCount(0)
        for s in segs:
            self._append(s)
        self._loading = False
        self.table.selectRow(r + d)
        self._commit()

    def _sel(self):
        r = self.table.currentRow()
        segs = self.collect()["segments"]
        return segs[r] if 0 <= r < len(segs) else None

    def preview(self):
        s = self._sel()
        p = self.app.project
        if not s or not p:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Cảnh {fmt_ts(s['start'])} → {fmt_ts(s['end'])}")
        dlg.resize(820, 540)
        lay = QVBoxLayout(dlg)
        vp = VideoPlayer()
        lay.addWidget(vp, 1)
        lay.addWidget(muted(s.get("narration") or "(giữ thoại gốc)"))
        vp.open(p.video)
        from PySide6.QtCore import QTimer

        QTimer.singleShot(300, lambda: vp.play_range(s["start"], s["end"]))
        dlg.finished.connect(vp.stop)
        dlg.exec()

    def listen(self):
        s = self._sel()
        p = self.app.project
        if not s or not s.get("narration"):
            QMessageBox.information(self, "Nghe thử", "Chọn 1 dòng có lời thuyết minh.")
            return
        opts = p.voice_opts() if p else dict(self.app.settings.section("voice"))
        from recap.pipeline import Project

        opts["tone"] = Project.segment_tone(s, opts)
        key = tts.voice_cache_key(opts["engine"], opts["voice"], s["narration"], opts)
        out = Path(tempfile.gettempdir()) / f"recap_listen_{key}.wav"

        def job(log, progress, cancel):
            if not out.exists() or out.stat().st_size < 1000:
                tts.synthesize(opts["engine"], s["narration"], opts["voice"], out, opts, self.app.settings, cancel)
            return str(out)
        self.app.ensure(opts["engine"], then=lambda: self.app.run_task(job, on_done=self.audio.play, title="Đọc thử"))

    def open_script(self):
        p = self.app.require_project()
        if not p:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Mở kịch bản", str(p.dir), "Kịch bản (*.json)")
        if f:
            p.script = script_writer.load_script(f)
            p.save()
            self.load_script()

    def save_script(self):
        p = self.app.project
        if not p:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Lưu kịch bản", str(p.dir / "kich_ban.json"), "Kịch bản (*.json)")
        if f:
            script_writer.save_script(self.collect(), f)

    def export_txt(self):
        p = self.app.project
        if not p:
            return
        f, _ = QFileDialog.getSaveFileName(self, "Xuất TXT", str(p.dir / "kich_ban.txt"), "Text (*.txt)")
        if f:
            Path(f).write_text(script_writer.script_to_text(self.collect()), encoding="utf-8")

