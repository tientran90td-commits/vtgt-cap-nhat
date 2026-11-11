"""Cửa sổ chính: 1 màn hình duy nhất - ① Phim · ② Thiết lập · ③ Kịch bản - và nút TẠO VIDEO."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea,
                               QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from recapstudio import APP_NAME, VERSION, ai, render, transcript, voices, writer
from recapstudio.config import Settings
from recapstudio.media import ENCODERS, MediaError
from recapstudio.project import STEPS, Project
from recapstudio.transcript import fmt

from .common import Binder, PathPicker, Worker, button, card, fill, label, row, spin

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg")
OFFLINE_VOICES = ("vieneu", "piper", "sapi")


class DropZone(QFrame):
    def __init__(self, on_file):
        super().__init__()
        self.on_file = on_file
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(140)
        lay = QVBoxLayout(self)
        t = label("🎬  Kéo & thả phim vào đây", "cardTitle")
        t.setAlignment(Qt.AlignCenter)
        s = label("MP4, MKV, AVI, MOV... phim dài bao lâu cũng được", "muted")
        s.setAlignment(Qt.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addWidget(row("stretch", button("📂 Chọn phim", self.browse, "primary"), "stretch"))
        lay.addStretch(1)

    def browse(self):
        from PySide6.QtWidgets import QFileDialog

        p, _ = QFileDialog.getOpenFileName(self, "Chọn phim", "", "Video (" + " ".join("*" + e for e in VIDEO_EXT) + ")")
        if p:
            self.on_file(p)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            self.setProperty("hover", True)
            self.style().polish(self)
            e.acceptProposedAction()

    def dragLeaveEvent(self, _e):
        self.setProperty("hover", False)
        self.style().polish(self)

    def dropEvent(self, e):
        self.dragLeaveEvent(e)
        for u in e.mimeData().urls():
            if u.toLocalFile():
                self.on_file(u.toLocalFile())
                break


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None):
        super().__init__()
        self.settings = settings or Settings()
        self.binder = Binder(self.settings)
        self.project: Project | None = None
        self.worker: Worker | None = None
        self.last_output: Path | None = None
        self._loading_table = False
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        icon = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1480, 920)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(18, 14, 18, 14)
        main.setSpacing(12)

        # ---------------- đầu trang
        self.badge = label("", "badge", wrap=False)
        main.addWidget(row(label(f"🎬 {APP_NAME}", "title", wrap=False), label(f"v{VERSION}", "muted", wrap=False),
                           self.badge, "stretch", button("⚙️ Cài đặt", self.open_settings)))

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._col_film(), 0)
        body.addWidget(self._col_settings(), 0)
        body.addWidget(self._col_script(), 1)
        main.addLayout(body, 1)
        main.addWidget(self._bottom())
        self.refresh_mode()
        QTimer.singleShot(300, self.refresh_ai)

    # ================================================================ cột ① phim
    def _col_film(self) -> QWidget:
        c, lay = card("① Phim")
        c.setFixedWidth(340)
        lay.addWidget(DropZone(self.open_video))
        self.lb_film = label("Chưa chọn phim", "muted")
        lay.addWidget(self.lb_film)
        lay.addWidget(label("Phụ đề của phim (không bắt buộc - có thì nhanh & chính xác nhất)", "muted"))
        self.sub_file = PathPicker("file", "Phụ đề (*.srt *.vtt *.ass *.ssa)", "tự tìm file .srt cạnh phim")
        self.sub_file.changed.connect(self._sub_changed)
        lay.addWidget(self.sub_file)
        lay.addWidget(label("Lấy lời thoại bằng", "muted"))
        self.stt = fill(QComboBox(), {})
        lay.addWidget(self.stt)
        self.wmodel = self.binder.combo(fill(QComboBox(), {m: m for m in transcript.WHISPER_MODELS}),
                                        "speech", "whisper_model")
        self.wlang = self.binder.combo(fill(QComboBox(), {"auto": "Tự nhận ngôn ngữ", "vi": "Tiếng Việt",
                                                          "ja": "日本語", "en": "English", "zh": "中文", "ko": "한국어"}),
                                       "speech", "language")
        lay.addWidget(row(label("Whisper", "muted", wrap=False), self.wmodel, self.wlang, stretch=False))
        lay.addWidget(label("large-v3-turbo: chính xác cao. small: nhanh hơn nhiều, kém chính xác hơn.", "muted"))
        self.btn_stt = button("🎧 Lấy lời thoại", self.do_transcript)
        lay.addWidget(self.btn_stt)
        self.lb_tr = label("", "muted")
        lay.addWidget(self.lb_tr)
        lay.addStretch(1)
        return c

    # ================================================================ cột ② thiết lập
    def _col_settings(self) -> QWidget:
        b = self.binder
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(12)

        c, lay = card("② Kịch bản AI")
        self.provider = fill(QComboBox(), {})
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumContentsLength(6)
        self.model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.model.currentTextChanged.connect(lambda t: b.set("ai", "model", t.strip()) if t.strip() else None)
        self.lb_ai = label("", "muted")
        g = QGridLayout()
        g.addWidget(label("AI", "muted"), 0, 0)
        g.addWidget(self.provider, 0, 1)
        g.addWidget(label("Model", "muted"), 1, 0)
        b_ref = button("🔄", self.refresh_ai, tip="Kiểm tra AI / danh sách model")
        b_ref.setFixedWidth(40)
        g.addWidget(row(self.model, b_ref, stretch=False), 1, 1)
        g.addWidget(self.lb_ai, 2, 1)
        self.style_ = b.combo(fill(QComboBox(), {k: v[0] for k, v in writer.STYLES.items()}), "ai", "style")
        self.mode = b.combo(fill(QComboBox(), writer.MODES), "ai", "mode")
        self.lang = b.combo(fill(QComboBox(), {x: x for x in writer.LANGS}), "ai", "language")
        g.addWidget(label("Phong cách", "muted"), 3, 0)
        g.addWidget(self.style_, 3, 1)
        g.addWidget(label("Kiểu video", "muted"), 4, 0)
        g.addWidget(self.mode, 4, 1)
        g.addWidget(label("Ngôn ngữ", "muted"), 5, 0)
        g.addWidget(self.lang, 5, 1)
        self.minutes = b.spin(spin(0.5, 120, 0.5, " phút", 1), "ai", "minutes")
        quick = [button(f"{m}′", lambda _=False, m=m: self.minutes.setValue(m)) for m in (1, 3, 5, 10)]
        for q in quick:
            q.setFixedWidth(44)
        g.addWidget(label("Thời lượng", "muted"), 6, 0)
        g.addWidget(row(self.minutes, *quick, stretch=False), 6, 1)
        self.extra = b.line(QLineEdit(), "ai", "extra")
        self.extra.setPlaceholderText("Yêu cầu thêm (vd: gọi nhân vật chính là 'cậu nhóc')")
        g.addWidget(label("Yêu cầu", "muted"), 7, 0)
        g.addWidget(self.extra, 7, 1)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("🎙️ Giọng đọc")
        self.engine = fill(QComboBox(), {})
        self.engine.currentIndexChanged.connect(self._engine_changed)
        self.voice = QComboBox()
        self.voice.setMinimumContentsLength(6)
        self.voice.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice.currentIndexChanged.connect(
            lambda _i: b.set("voice", "voice", self.voice.currentData()) if self.voice.currentData() is not None
            else None)
        self.speed = b.spin(spin(-50, 80, 5, " %"), "voice", "speed")
        g = QGridLayout()
        g.addWidget(label("Công cụ", "muted"), 0, 0)
        g.addWidget(self.engine, 0, 1)
        g.addWidget(label("Giọng", "muted"), 1, 0)
        g.addWidget(self.voice, 1, 1)
        g.addWidget(label("Tốc độ", "muted"), 2, 0)
        g.addWidget(row(self.speed, button("🔊 Nghe thử", self.preview_voice), stretch=False), 2, 1)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("🎬 Video")
        g = QGridLayout()
        self.aspect = b.combo(fill(QComboBox(), render.ASPECTS), "video", "aspect")
        self.height_ = b.combo(fill(QComboBox(), {720: "720p", 1080: "1080p (Full HD)", 1440: "1440p (2K)"}),
                               "video", "height", int)
        self.fill_ = b.combo(fill(QComboBox(), render.FILLS), "video", "fill")
        self.subs = b.check(QCheckBox("Chèn phụ đề thuyết minh"), "video", "subtitles")
        self.sub_size = b.spin(spin(20, 120, 2, " cỡ"), "video", "sub_size")
        self.sub_pos = b.combo(fill(QComboBox(), render.POSITIONS), "video", "sub_position")
        self.cover = b.combo(fill(QComboBox(), render.COVERS), "video", "cover")
        self.cover_h = b.spin(spin(4, 40, 1, " %"), "video", "cover_height")
        self.music = PathPicker("file", "Âm thanh (*.mp3 *.wav *.m4a *.flac *.ogg)", "(không bắt buộc) nhạc nền")
        self.music.setText(self.settings.get("video", "music", ""))
        self.music.changed.connect(lambda v: b.set("video", "music", v))
        self.ov = b.spin(spin(0, 1, 0.05, "", 2), "video", "orig_volume")
        self.encoder = b.combo(fill(QComboBox(), ENCODERS), "video", "encoder")
        self.parallel = b.spin(spin(1, 6, 1, " đoạn"), "video", "parallel")
        items = [("Khung hình", row(self.aspect, self.height_, stretch=False)), ("Lấp khung", self.fill_),
                 ("Phụ đề", row(self.subs, self.sub_size, self.sub_pos, stretch=False)),
                 ("Phụ đề gốc", row(self.cover, self.cover_h, stretch=False)), ("Nhạc nền", self.music),
                 ("Tiếng phim gốc", row(self.ov, label("khi thuyết minh (0 = tắt)", "muted", wrap=False), stretch=False)),
                 ("Mã hóa", row(self.encoder, self.parallel, label("cùng lúc", "muted", wrap=False), stretch=False))]
        for i, (k, w) in enumerate(items):
            g.addWidget(label(k, "muted"), i, 0)
            g.addWidget(w, i, 1)
        lay.addLayout(g)
        col.addWidget(c)
        col.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(box)
        sc.setFixedWidth(500)
        box.setMaximumWidth(488)
        return sc

    # ================================================================ cột ③ kịch bản
    def _col_script(self) -> QWidget:
        c, lay = card("③ Kịch bản (sửa trực tiếp được)")
        self.title = QLineEdit()
        self.title.setPlaceholderText("Tiêu đề video (cũng là tên file)")
        self.title.textEdited.connect(lambda _t: self._table_changed())
        lay.addWidget(self.title)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Bắt đầu", "Kết thúc", "Lời thuyết minh (trống = giữ tiếng gốc)"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(lambda _it: self._table_changed())
        lay.addWidget(self.table, 1)
        self.lb_est = label("", "muted")
        self.btn_script = button("✍️ AI viết kịch bản", self.do_script, "primary")
        lay.addWidget(row(self.btn_script, button("➕ Thêm đoạn", self.add_row), button("➖ Xóa đoạn", self.del_row),
                          "stretch", self.lb_est))
        return c

    # ================================================================ thanh dưới
    def _bottom(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.chips = {}
        chips = []
        for sid, name in STEPS.items():
            lb = label(name + "\nchờ", "chip", wrap=False)
            lb.setAlignment(Qt.AlignCenter)
            lb.setMinimumWidth(130)
            self.chips[sid] = lb
            chips.append(lb)
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        self.prog.setFormat("%p%")
        self.lb_status = label("Sẵn sàng", "muted", wrap=False)
        self.lb_status.setMinimumWidth(260)
        self.btn_all = button("⚡ LÀM TẤT CẢ → XUẤT VIDEO", self.do_all, "big")
        self.btn_render = button("🎬 Xuất video từ kịch bản", self.do_render, "primary")
        self.btn_cancel = button("⏹ Hủy", self.cancel, "danger")
        self.btn_cancel.setEnabled(False)
        lay.addWidget(row(*chips, self.prog, self.lb_status, stretch=False))
        lay.addWidget(row(self.btn_all, self.btn_render, self.btn_cancel, "stretch",
                          button("📂 Mở thư mục video", self.open_folder), button("▶ Xem video", self.play)))
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFixedHeight(120)
        lay.addWidget(self.log)
        return w

    # ================================================================ chế độ / danh sách
    def refresh_mode(self):
        off = self.settings.offline
        self.badge.setText("🔒 Offline - chạy hoàn toàn trên máy" if off else "🌐 Dùng thêm AI/giọng online")
        self.badge.setObjectName("badge" if off else "badgeOnline")
        self.badge.style().polish(self.badge)
        stt = {"auto": "Tự động (phụ đề có sẵn → Whisper card đồ họa → CPU)" if off else transcript.ENGINES["auto"],
               "gpu": transcript.ENGINES["gpu"], "local": transcript.ENGINES["local"],
               "subtitle": transcript.ENGINES["subtitle"]}
        if not off:
            stt.update({"groq": transcript.ENGINES["groq"], "openai": transcript.ENGINES["openai"]})
        fill(self.stt, stt)
        self._select(self.stt, self.settings.get("speech", "engine"))
        self.stt.currentIndexChanged.connect(lambda _i: self.binder.set("speech", "engine", self.stt.currentData()))
        provs = {"ollama": ai.PROVIDERS["ollama"]["name"], "none": ai.PROVIDERS["none"]["name"]} if off else \
            {k: v["name"] for k, v in ai.PROVIDERS.items()}
        fill(self.provider, provs)
        self._select(self.provider, self.settings.get("ai", "provider"))
        if self.provider.currentData() != self.settings.get("ai", "provider"):
            self.binder.set("ai", "provider", self.provider.currentData())
        engines = {k: v["name"] for k, v in voices.ENGINES.items() if not off or k in OFFLINE_VOICES}
        fill(self.engine, engines)
        self._select(self.engine, self.settings.get("voice", "engine"))
        if self.engine.currentData() != self.settings.get("voice", "engine"):
            self.binder.set("voice", "engine", self.engine.currentData())
        self._provider_changed(init=True)
        self._engine_changed(init=True)

    @staticmethod
    def _select(combo: QComboBox, value):
        i = combo.findData(value)
        combo.setCurrentIndex(i if i >= 0 else 0)

    def _provider_changed(self, *_a, init=False):
        pid = self.provider.currentData() or "ollama"
        if not init:
            self.binder.set("ai", "provider", pid)
        cur = self.settings.get("ai", "model") or ""
        self.model.blockSignals(True)
        self.model.clear()
        models = list(ai.OLLAMA_MODELS) if pid == "ollama" else ai.PROVIDERS[pid]["models"]
        self.model.addItems(models)
        keep = cur if (cur and ai.model_fits(pid, cur) and (pid != "ollama" or ":" in cur or cur in models)) else \
            ai.PROVIDERS[pid]["default"]
        self.model.setEditText(keep)
        self.model.blockSignals(False)
        self.binder.set("ai", "model", keep)
        self.model.setEnabled(pid != "none")
        self.refresh_ai()

    def refresh_ai(self):
        pid = self.provider.currentData() or "ollama"
        if pid == "ollama":
            ok, models = ai.ollama_status(self.settings)
            m = self.model.currentText().strip()
            has = any(x == m or x.split(":")[0] == m or x == m + ":latest" for x in models)
            self.lb_ai.setText("● Ollama đang chạy" + ("" if has else f" · chưa tải {m} → ⚙️ Cài đặt → Tải model AI")
                               if ok else "○ Chưa mở Ollama → ⚙️ Cài đặt để cài & tải model (một lần)")
        elif pid == "none":
            self.lb_ai.setText("Không dùng AI: app tự cắt các cảnh nổi bật, giữ tiếng gốc.")
        else:
            k = ai.PROVIDERS[pid]["key"]
            self.lb_ai.setText("✓ Đã có API key" if self.settings.key(k) else "⚠️ Chưa nhập API key (⚙️ Cài đặt)")

    def _engine_changed(self, *_a, init=False):
        eng = self.engine.currentData() or "vieneu"
        if not init:
            self.binder.set("voice", "engine", eng)
        self.voice.blockSignals(True)
        self.voice.clear()
        for vid, name in voices.list_voices(eng, self.settings) if eng != "edge" else voices._EDGE_DEFAULT:
            self.voice.addItem(name, vid)
        cur = self.settings.get("voice", "voice")
        i = self.voice.findData(cur)
        if i < 0:
            i = max(0, self.voice.findData(voices.default_voice(eng)))
        self.voice.setCurrentIndex(i)
        self.voice.blockSignals(False)
        if self.voice.currentData() is not None:
            self.binder.set("voice", "voice", self.voice.currentData())

    def open_settings(self):
        from .settings_dialog import SettingsDialog

        SettingsDialog(self).exec()
        self.refresh_mode()

    # ================================================================ phim & kịch bản
    def open_video(self, path: str):
        if Path(path).suffix.lower() not in VIDEO_EXT:
            QMessageBox.warning(self, "Không phải video", "Hãy chọn file video (mp4, mkv, avi, mov...).")
            return
        try:
            self.project = Project(path, self.settings)
        except (MediaError, OSError) as e:
            QMessageBox.critical(self, "Không mở được phim", str(e))
            return
        p = self.project
        self.lb_film.setText(f"<b>{Path(path).name}</b><br>{p.info.summary()}")
        side = transcript.find_sidecar(path)
        self.sub_file.setText(str(side) if side else "")
        self._update_tr_label()
        self.load_script()
        self.log_msg(f"Đã mở phim: {Path(path).name}")

    def _sub_changed(self, v):
        if self.project:
            self.project.subtitle_file = v if v and Path(v).exists() else ""

    def _update_tr_label(self):
        p = self.project
        self.lb_tr.setText(f"✅ Đã có lời thoại: {len(p.transcript)} câu" if p and p.transcript else "")

    def load_script(self):
        sc = (self.project.script if self.project else None) or {"title": "", "segments": []}
        self._loading_table = True
        self.title.setText(sc.get("title", ""))
        self.table.setRowCount(0)
        for seg in sc.get("segments", []):
            self._append(seg)
        self._loading_table = False
        self._update_est()

    def _append(self, seg: dict, at: int | None = None):
        r = self.table.rowCount() if at is None else at
        self.table.insertRow(r)
        for c, v in enumerate((fmt(seg["start"]), fmt(seg["end"]), seg.get("narration", ""))):
            self.table.setItem(r, c, QTableWidgetItem(v))

    def collect(self) -> dict:
        segs = []
        for r in range(self.table.rowCount()):
            st = transcript._ts(self.table.item(r, 0).text() if self.table.item(r, 0) else "0")
            en = transcript._ts(self.table.item(r, 1).text() if self.table.item(r, 1) else "0")
            nar = (self.table.item(r, 2).text() if self.table.item(r, 2) else "").strip()
            if en <= st:
                en = st + 6
            segs.append({"start": st, "end": en, "narration": nar, "keep_original": not nar})
        return {"title": self.title.text().strip(), "description": "", "segments": segs}

    def _table_changed(self):
        if self._loading_table or not self.project:
            return
        self.project.save_script(self.collect())
        self._update_est()

    def _update_est(self):
        sc = self.collect()
        if not sc["segments"]:
            self.lb_est.setText("Chưa có kịch bản")
            return
        est = writer.estimate_seconds(sc, self.settings.get("ai", "language", "Tiếng Việt"))
        self.lb_est.setText(f"{len(sc['segments'])} đoạn · ≈ {int(est // 60)}:{int(est % 60):02d}")

    def add_row(self):
        r = self.table.currentRow()
        r = self.table.rowCount() if r < 0 else r + 1
        prev = self.collect()["segments"][r - 1] if r > 0 and self.table.rowCount() else {"end": 0}
        self._append({"start": prev["end"], "end": prev["end"] + 8, "narration": ""}, r)
        self._table_changed()

    def del_row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._table_changed()

    # ================================================================ chạy tác vụ
    def need_project(self) -> bool:
        if not self.project:
            QMessageBox.information(self, "Chưa có phim", "Hãy kéo thả hoặc chọn một bộ phim trước.")
            return False
        return True

    def run_task(self, fn, title: str, on_done=None, with_steps=False):
        if self.worker is not None:
            QMessageBox.information(self, "Đang bận", "Đang làm việc khác - đợi xong hoặc bấm Hủy.")
            return
        w = Worker(fn) if not with_steps else Worker(fn, step=lambda a, b, c="": w.step.emit(a, b, c))
        self.worker = w
        self._t0 = time.time()
        w.log.connect(self.log_msg)
        w.progress.connect(self._progress)
        w.step.connect(self._step)
        self.prog.setValue(0)
        self.lb_status.setText(f"⏳ {title}...")
        for b in (self.btn_all, self.btn_render, self.btn_script, self.btn_stt):
            b.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log_msg(f"▶ {title}")

        def finish():
            self.worker = None
            for b in (self.btn_all, self.btn_render, self.btn_script, self.btn_stt):
                b.setEnabled(True)
            self.btn_cancel.setEnabled(False)

        def ok(res):
            finish()
            el = time.time() - self._t0
            self.prog.setValue(1000)
            self.lb_status.setText(f"✅ {title} - xong ({int(el // 60)}:{int(el % 60):02d})")
            if on_done:
                on_done(res)

        def bad(msg, tb):
            finish()
            for sid, lb in self.chips.items():
                if lb.property("state") == "start":
                    self._step(sid, "fail" if msg != "Đã hủy." else "skip", "đã hủy" if msg == "Đã hủy." else "lỗi")
            if tb:
                self.log_msg(tb, "debug")
            self.log_msg(f"❌ {title}: {msg}", "error")
            self.lb_status.setText("⏹ Đã hủy" if msg == "Đã hủy." else f"❌ {title} lỗi")
            if msg != "Đã hủy.":
                QMessageBox.critical(self, f"Lỗi - {title}", msg[:1500])
        w.done.connect(ok)
        w.failed.connect(bad)
        w.start()

    def _progress(self, p, msg):
        self.prog.setValue(int(max(0.0, min(1.0, p)) * 1000))
        if msg:
            self.lb_status.setText(f"⏳ {msg}")

    def _step(self, sid, state, note=""):
        lb = self.chips.get(sid)
        if not lb:
            return
        if state == "start":
            lb._t = time.time()
        sub = {"start": "đang làm...", "skip": "bỏ qua", "fail": "lỗi"}.get(state, "")
        if state == "done":
            t0 = getattr(lb, "_t", None)
            el = time.time() - t0 if t0 else None
            sub = f"xong {int(el // 60)}:{int(el % 60):02d}" if el is not None else "xong"
            lb._t = None
        lb.setText(f"{STEPS[sid]}\n{sub}")
        lb.setToolTip(note)
        lb.setProperty("state", state)
        lb.style().unpolish(lb)
        lb.style().polish(lb)

    def _reset_chips(self):
        for sid in self.chips:
            self._step(sid, "pending")
            self.chips[sid].setText(f"{STEPS[sid]}\nchờ")

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.lb_status.setText("⏹ Đang hủy...")

    def log_msg(self, msg, level="info"):
        if level == "debug":
            return
        color = {"warn": "#FFC857", "error": "#FF6B81"}.get(level)
        ts = time.strftime("%H:%M:%S")
        txt = str(msg).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>")
        self.log.appendHtml(f"<span style='color:#6C7489'>{ts}</span> "
                            + (f"<span style='color:{color}'>{txt}</span>" if color else txt))

    # ================================================================ các nút
    def do_transcript(self):
        if not self.need_project():
            return
        p = self.project
        self._reset_chips()

        def job(log, progress, cancel, step):
            step("transcript", "start")
            r = p.run_transcript(log, progress, cancel)
            step("transcript", "done")
            return r
        self.run_task(job, "Lấy lời thoại", on_done=lambda _r: self._update_tr_label(), with_steps=True)

    def do_script(self):
        if not self.need_project():
            return
        p = self.project
        self._reset_chips()

        def job(log, progress, cancel, step):
            if not p.transcript:
                step("transcript", "start")
                p.run_transcript(log, lambda x, m="": progress(x * 0.6, m), cancel)
                step("transcript", "done")
            step("script", "start")
            r = p.run_script(log, lambda x, m="": progress(0.6 + x * 0.4, m), cancel)
            step("script", "done")
            return r
        self.run_task(job, "AI viết kịch bản", on_done=lambda _r: (self.load_script(), self._update_tr_label()),
                      with_steps=True)

    def do_render(self):
        if not self.need_project():
            return
        sc = self.collect()
        if not sc["segments"]:
            QMessageBox.information(self, "Chưa có kịch bản", "Bấm '✍️ AI viết kịch bản' hoặc 'LÀM TẤT CẢ' trước.")
            return
        p = self.project
        p.save_script(sc)
        self._reset_chips()
        self.run_task(lambda log, progress, cancel, step: p.run_render(None, log, progress, cancel, step),
                      "Xuất video", on_done=self.finished, with_steps=True)

    def do_all(self):
        if not self.need_project():
            return
        p = self.project
        self._reset_chips()
        self.run_task(lambda log, progress, cancel, step: p.run_all(None, log, progress, cancel, step),
                      "Làm tất cả", on_done=lambda out: (self.load_script(), self._update_tr_label(),
                                                         self.finished(out)), with_steps=True)

    def finished(self, out):
        self.last_output = Path(out)
        self.open_folder()

    def preview_voice(self):
        eng = self.engine.currentData()
        voice = self.voice.currentData() or ""
        out = Path(self.settings.path).parent / "preview" / f"preview_{int(time.time())}.wav"

        def job(log, progress, cancel):
            return voices.synth(eng, voices.SAMPLE, voice, out, self.settings, log)
        self.run_task(job, "Đọc thử", on_done=lambda f: self._play_file(Path(f)))

    def _play_file(self, f: Path):
        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(str(f), winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            except Exception:  # noqa: BLE001
                pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(f)))

    def open_folder(self):
        target = self.last_output if self.last_output and self.last_output.exists() else None
        if target and sys.platform.startswith("win"):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(str(target))}"')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent if target else self.settings.output_dir())))

    def play(self):
        if self.last_output and self.last_output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))
