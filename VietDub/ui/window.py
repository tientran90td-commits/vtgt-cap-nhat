"""Cửa sổ chính: ① Video · ② Thiết lập · ③ Bảng lời gốc / tiếng Việt - và nút VIỆT HÓA.

Mọi việc kiểm tra (mạng, Ollama, bản mới) chạy nền nên giao diện không bao giờ bị đơ."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea,
                               QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from vietdub import APP_NAME, VERSION, ai, download, hybrid, render, transcript, translate, updater, voices
from vietdub.config import MODES, Settings
from vietdub.media import ENCODERS, MediaError
from vietdub.project import STEPS, Project
from vietdub.transcript import fmt

from .common import Bg, Binder, PathPicker, Worker, button, card, fill, label, row, spin

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except ImportError:  # thiếu QtMultimedia -> mở bằng trình phát của máy
    QMediaPlayer = None

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg")
OFFLINE_VOICES = ("vieneu", "piper", "sapi")
SRC_LANGS = {"auto": "Tự nhận ngôn ngữ", "zh": "Tiếng Trung", "en": "Tiếng Anh", "ja": "Tiếng Nhật",
             "ko": "Tiếng Hàn", "th": "Tiếng Thái", "id": "Tiếng Indonesia", "es": "Tiếng Tây Ban Nha",
             "fr": "Tiếng Pháp", "ru": "Tiếng Nga", "hi": "Tiếng Hindi"}
PRESETS = [  # (nút, gợi ý, thiết lập)
    ("🎙️ Thuyết minh + Vietsub", "Lồng tiếng Việt, in phụ đề Việt, xóa phụ đề gốc",
     {"video.output": "both", "video.cover": "auto", "video.aspect": "source"}),
    ("💬 Chỉ Vietsub", "Giữ tiếng gốc, in phụ đề Việt, xóa phụ đề gốc",
     {"video.output": "sub", "video.cover": "auto", "video.aspect": "source"}),
    ("📱 TikTok dọc", "Khung 9:16, thuyết minh + phụ đề",
     {"video.output": "both", "video.aspect": "9:16", "video.fill": "blur"}),
    ("⚡ Nhanh nhất", "Chỉ thuyết minh, giữ hình gốc (không mã hóa lại hình)",
     {"video.output": "dub", "video.cover": "none", "video.aspect": "source"}),
]


class DropZone(QFrame):
    def __init__(self, on_file):
        super().__init__()
        self.on_file = on_file
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)
        lay = QVBoxLayout(self)
        t = label("🎬  Kéo & thả video vào đây", "cardTitle")
        t.setAlignment(Qt.AlignCenter)
        s = label("Video tiếng Trung, Anh, Hàn, Nhật, Thái... dài bao lâu cũng được", "muted")
        s.setAlignment(Qt.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addWidget(row("stretch", button("📂 Chọn video", self.browse, "primary"), "stretch"))
        lay.addStretch(1)

    def browse(self):
        from PySide6.QtWidgets import QFileDialog

        p, _ = QFileDialog.getOpenFileName(self, "Chọn video", "",
                                           "Video (" + " ".join("*" + e for e in VIDEO_EXT) + ")")
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
        self._status: dict = {}
        self._update_info: dict | None = None
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        icon = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1500, 930)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(18, 14, 18, 14)
        main.setSpacing(12)

        self.mode_box = fill(QComboBox(), MODES)
        self.mode_box.setMinimumWidth(210)
        self.mode_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._select(self.mode_box, self.settings.mode)
        self.mode_box.setToolTip("Tự động: mỗi bước tự chọn chạy trên máy hay qua mạng (cái nào có sẵn & nhanh),\n"
                                 "lỗi thì tự chuyển cách kia.\nChỉ trên máy: không dùng mạng.\n"
                                 "Ưu tiên online: dùng AI/giọng online trước, máy là dự phòng.")
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.status = label("⏳ Đang kiểm tra...", "status", wrap=False)
        self.btn_update = button("🔄 Cập nhật", self.do_update, tip="Kiểm tra & cập nhật bản mới trực tiếp")
        main.addWidget(row(label(f"🌐 {APP_NAME}", "title", wrap=False), label(f"v{VERSION}", "muted", wrap=False),
                           self.mode_box, self.status, "stretch",
                           button("📦 Thư viện", self.open_components, tip="Tải giọng Ngọc Huyền, OCR mọi ngôn ngữ..."),
                           self.btn_update, button("⚙️ Cài đặt", self.open_settings)))

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._col_video(), 0)
        body.addWidget(self._col_settings(), 0)
        body.addWidget(self._col_table(), 1)
        main.addLayout(body, 1)
        main.addWidget(self._bottom())
        self.refresh_mode()
        self._bg_changed()
        self.refresh_status()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_status)
        self._timer.start(60_000)
        if self.settings.get("update", "auto_check", True) and self.settings.mode != "offline":
            QTimer.singleShot(2500, lambda: self.check_update(silent=True))

    # ================================================================ cột ① video
    def _col_video(self) -> QWidget:
        c, lay = card("① Video gốc")
        c.setFixedWidth(340)
        lay.addWidget(DropZone(self.open_video))
        self.link = QLineEdit()
        self.link.setPlaceholderText("hoặc dán link YouTube / TikTok / Douyin / Bilibili...")
        self.link.returnPressed.connect(self.do_download)
        b_dl = button("⬇ Tải", self.do_download, tip="Tải video từ link (yt-dlp) rồi mở luôn")
        b_dl.setFixedWidth(64)
        lay.addWidget(row(self.link, b_dl, stretch=False))
        self.player = None
        if QMediaPlayer is not None:
            self.video_w = QVideoWidget()
            self.video_w.setFixedHeight(172)
            self.video_w.setStyleSheet("background:#000; border-radius:10px;")
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.7)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.video_w)
            self.btn_pp = button("▶", self.toggle_play, tip="Phát / dừng")
            self.btn_pp.setFixedWidth(42)
            self.lb_pos = label("", "muted", wrap=False)
            self.player.positionChanged.connect(lambda ms: self.lb_pos.setText(fmt(ms / 1000)))
            self.player.playbackStateChanged.connect(
                lambda st: self.btn_pp.setText("⏸" if st == QMediaPlayer.PlayingState else "▶"))
            self.video_w.hide()
            lay.addWidget(self.video_w)
            self.player_bar = row(self.btn_pp, self.lb_pos, "stretch",
                                  button("⛶", self._open_current_media, tip="Mở bằng trình phát của máy"))
            self.player_bar.hide()
            lay.addWidget(self.player_bar)
        self.lb_film = label("Chưa chọn video", "muted")
        lay.addWidget(self.lb_film)
        lay.addWidget(label("Phụ đề gốc dạng file (không bắt buộc - có thì nhanh & chính xác nhất)", "muted"))
        self.sub_file = PathPicker("file", "Phụ đề (*.srt *.vtt *.ass *.ssa)", "tự tìm file .srt cạnh video")
        self.sub_file.changed.connect(self._sub_changed)
        lay.addWidget(self.sub_file)
        self.btn_region = button("🔲 Khung phụ đề cứng (quét chữ / xóa đúng chỗ)", self.open_region,
                                 tip="Kéo khung đúng dòng phụ đề in sẵn trên video gốc")
        lay.addWidget(self.btn_region)
        self.lb_region = label("", "muted")
        lay.addWidget(self.lb_region)
        self.srclang = self.binder.combo(fill(QComboBox(), SRC_LANGS), "speech", "language")
        lay.addWidget(row(label("Ngôn ngữ gốc", "muted", wrap=False), self.srclang, stretch=False))
        self.stt = fill(QComboBox(), {})
        lay.addWidget(row(label("Nghe bằng", "muted", wrap=False), self.stt, stretch=False))
        self.wmodel = self.binder.combo(fill(QComboBox(), {m: m for m in transcript.WHISPER_MODELS}),
                                        "speech", "whisper_model")
        lay.addWidget(row(label("Whisper", "muted", wrap=False), self.wmodel, stretch=False))
        self.btn_stt = button("🎧 Lấy lời gốc", self.do_transcript)
        lay.addWidget(self.btn_stt)
        self.lb_tr = label("", "muted")
        lay.addWidget(self.lb_tr)
        lay.addStretch(1)
        return c

    # ================================================================ cột ② thiết lập
    def _col_settings(self) -> QWidget:
        b = self.binder
        box = QWidget()
        box.setObjectName("root")
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(12)

        c, lay = card("⚡ Mẫu nhanh")
        g = QGridLayout()
        for i, (name, tip, vals) in enumerate(PRESETS):
            g.addWidget(button(name, lambda _=False, v=vals, n=name: self.apply_preset(v, n), "preset", tip),
                        i // 2, i % 2)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("② Dịch sang tiếng Việt")
        self.provider = fill(QComboBox(), {})
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumContentsLength(6)
        self.model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.model.currentTextChanged.connect(self._model_changed)
        self.lb_ai = label("", "muted")
        self.style_ = b.combo(fill(QComboBox(), {k: v[0] for k, v in translate.STYLES.items()}), "translate", "style")
        self.context = b.line(QLineEdit(), "translate", "context")
        self.context.setPlaceholderText("vd: phim cổ trang, A là sư phụ của B, C là công chúa")
        self.glossary = QPlainTextEdit()
        self.glossary.setPlaceholderText("Tên riêng (mỗi dòng 1 tên):\n林动 = Lâm Động\nHarry = Harry")
        self.glossary.setFixedHeight(64)
        self.glossary.setPlainText(self.settings.get("translate", "glossary", ""))
        self.glossary.textChanged.connect(lambda: b.set("translate", "glossary", self.glossary.toPlainText()))
        self.shorten = b.check(QCheckBox("Câu dịch dài quá thời gian nói → AI rút gọn"), "translate", "shorten")
        g = QGridLayout()
        b_ref = button("🔄", lambda: self.refresh_status(force=True), tip="Kiểm tra lại AI")
        b_ref.setFixedWidth(40)
        rows_ = [("AI dịch", self.provider), ("Model", row(self.model, b_ref, stretch=False)), ("", self.lb_ai),
                 ("Văn phong", self.style_), ("Bối cảnh", self.context), ("Tên riêng", self.glossary),
                 ("", self.shorten)]
        for i, (k, w) in enumerate(rows_):
            g.addWidget(label(k, "muted"), i, 0)
            g.addWidget(w, i, 1)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("🎙️ Thuyết minh")
        self.engine = fill(QComboBox(), {})
        self.engine.currentIndexChanged.connect(self._engine_changed)
        self.voice = QComboBox()
        self.voice.setMinimumContentsLength(6)
        self.voice.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.voice.currentIndexChanged.connect(
            lambda _i: b.set("voice", "voice", self.voice.currentData()) if self.voice.currentData() is not None
            else None)
        self.speed = b.spin(spin(-30, 50, 5, " %"), "voice", "speed")
        self.bg = b.combo(fill(QComboBox(), render.BACKGROUNDS), "video", "background")
        self.bg.currentIndexChanged.connect(lambda _i: self._bg_changed())
        self.ov = b.spin(spin(0, 1, 0.05, "", 2), "video", "orig_volume")
        self.ov.setToolTip("Âm lượng tiếng gốc (kiểu giữ tiếng gốc nhỏ)")
        self.duck = b.check(QCheckBox("tự giảm lúc đọc"), "video", "duck")
        self.btn_sep = button("⬇ Cài tách nhạc AI (~60 MB)", self.install_separator, "primary")
        self.lb_bg = label("", "muted")
        g = QGridLayout()
        self.lb_voice = label("", "muted")
        rows_ = [("Giọng đọc", self.engine), ("Giọng", self.voice), ("", self.lb_voice),
                 ("Tốc độ", row(self.speed, button("🔊 Nghe thử", self.preview_voice), stretch=False)),
                 ("Tiếng gốc", self.bg), ("", row(self.ov, self.duck, stretch=False)), ("", self.btn_sep),
                 ("", self.lb_bg)]
        for i, (k, w) in enumerate(rows_):
            g.addWidget(label(k, "muted"), i, 0)
            g.addWidget(w, i, 1)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("🎬 Video xuất ra")
        g = QGridLayout()
        self.output = b.combo(fill(QComboBox(), render.OUTPUTS), "video", "output")
        self.cover = b.combo(fill(QComboBox(), render.COVERS), "video", "cover")
        self.cover_h = b.spin(spin(4, 40, 1, " %"), "video", "cover_height")
        self.burn = b.check(QCheckBox("In phụ đề Việt lên hình"), "video", "burn_subs")
        self.soft = b.check(QCheckBox("Kèm phụ đề bật/tắt được"), "video", "soft_subs")
        self.sub_size = b.spin(spin(20, 120, 2, " cỡ"), "video", "sub_size")
        self.sub_pos = b.combo(fill(QComboBox(), render.POSITIONS), "video", "sub_position")
        self.aspect = b.combo(fill(QComboBox(), render.ASPECTS), "video", "aspect")
        self.height_ = b.combo(fill(QComboBox(), {720: "720p", 1080: "1080p", 1440: "1440p"}), "video", "height", int)
        self.fill_ = b.combo(fill(QComboBox(), render.FILLS), "video", "fill")
        self.encoder = b.combo(fill(QComboBox(), ENCODERS), "video", "encoder")
        items = [("Kiểu", self.output), ("Phụ đề gốc", self.cover),
                 ("Phụ đề Việt", row(self.burn, self.sub_size, self.sub_pos, stretch=False)), ("", self.soft),
                 ("Khung hình", row(self.aspect, self.height_, stretch=False)), ("Lấp khung", self.fill_),
                 ("Mã hóa", self.encoder)]
        for i, (k, w) in enumerate(items):
            g.addWidget(label(k, "muted"), i, 0)
            g.addWidget(w, i, 1)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("📤 Đăng bài")
        lay.addWidget(b.check(QCheckBox("Tạo ảnh bìa có tiêu đề tiếng Việt"), "publish", "thumbnail"))
        lay.addWidget(b.check(QCheckBox("AI viết tiêu đề, mô tả, hashtag tiếng Việt"), "publish", "info"))
        lay.addWidget(b.check(QCheckBox("Lưu ảnh bìa + mô tả cạnh video (mặc định chỉ để video)"), "publish",
                              "save_next_to_video"))
        col.addWidget(c)
        col.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(box)
        sc.viewport().setStyleSheet("background: transparent;")
        sc.setFixedWidth(500)
        box.setMaximumWidth(488)
        return sc

    # ================================================================ cột ③ bảng dịch
    def _col_table(self) -> QWidget:
        c, lay = card("③ Lời gốc → tiếng Việt (sửa trực tiếp được)")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Bắt đầu", "Kết thúc", "Lời gốc", "Tiếng Việt"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setWordWrap(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(lambda _it: self._table_changed())
        self.table.currentCellChanged.connect(lambda r, _c, _pr, _pc: self._seek_row(r))
        lay.addWidget(self.table, 1)
        self.lb_est = label("", "muted")
        self.btn_tr = button("🌐 AI dịch", self.do_translate, "primary", "Dịch (lại) toàn bộ sang tiếng Việt")
        self.btn_prev = button("👁 Xem thử 20 giây", self.do_preview, tip="Dựng thử quanh câu đang chọn")
        self.btn_edit = button("✏️ Chỉnh phụ đề trực tiếp", self.open_editor, "primary",
                               "Xem video, phụ đề Việt hiện ngay trên hình - sửa chữ, thời gian, kiểu chữ")
        lay.addWidget(row(self.btn_tr, self.btn_edit, self.btn_prev, "stretch", self.lb_est))
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
            lb.setMinimumWidth(118)
            self.chips[sid] = lb
            chips.append(lb)
        self.prog = QProgressBar()
        self.prog.setRange(0, 1000)
        self.prog.setFormat("%p%")
        self.lb_status = label("Sẵn sàng", "muted", wrap=False)
        self.lb_status.setMinimumWidth(260)
        self.btn_all = button("⚡ VIỆT HÓA → XUẤT VIDEO", self.do_all, "big")
        self.btn_render = button("🎬 Xuất lại từ bảng dịch", self.do_render, "primary")
        self.btn_cancel = button("⏹ Hủy", self.cancel, "danger")
        self.btn_cancel.setEnabled(False)
        self.btn_oc = button("🎬 Dựng tiếp trong OpenCut", self.open_opencut, "primary",
                             "Mở trình dựng OpenCut (tiếng Việt): video đã xóa phụ đề gốc + thuyết minh + phụ đề "
                             "Việt nạp sẵn trên dòng thời gian")
        self.btn_pub = button("📤 Đăng video", self.open_publish, tip="Ảnh bìa, tiêu đề, mô tả, hashtag")
        self.btn_pub.setEnabled(False)
        lay.addWidget(row(*chips, self.prog, self.lb_status, stretch=False))
        lay.addWidget(row(self.btn_all, self.btn_render, self.btn_cancel, "stretch", self.btn_oc, self.btn_pub,
                          button("📂 Mở thư mục video", self.open_folder), button("▶ Xem video", self.play)))
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFixedHeight(110)
        lay.addWidget(self.log)
        return w

    # ================================================================ chế độ / trạng thái
    @staticmethod
    def _select(combo: QComboBox, value):
        i = combo.findData(value)
        combo.setCurrentIndex(i if i >= 0 else 0)

    def _mode_changed(self, *_a):
        self.binder.set(None, "mode", self.mode_box.currentData())
        self.settings.save()
        self.refresh_mode()
        self.refresh_status(force=True)

    def refresh_mode(self):
        off = self.settings.mode == "offline"
        stt = {"auto": transcript.ENGINES["auto"], "ocr": transcript.ENGINES["ocr"], "gpu": transcript.ENGINES["gpu"],
               "local": transcript.ENGINES["local"], "subtitle": transcript.ENGINES["subtitle"]}
        if not off:
            stt.update({"groq": transcript.ENGINES["groq"], "openai": transcript.ENGINES["openai"]})
        try:
            self.stt.currentIndexChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        fill(self.stt, stt)
        self._select(self.stt, self.settings.get("speech", "engine"))
        self.stt.currentIndexChanged.connect(lambda _i: self.binder.set("speech", "engine", self.stt.currentData()))
        provs = {"auto": ai.PROVIDERS["auto"]["name"] if not off else "⚡ Tự chọn (AI trên máy)",
                 "ollama": ai.PROVIDERS["ollama"]["name"]}
        if not off:
            provs.update({k: v["name"] for k, v in ai.PROVIDERS.items() if k not in ("auto", "ollama", "none")})
        self.provider.blockSignals(True)
        fill(self.provider, provs)
        self._select(self.provider, self.settings.get("ai", "provider"))
        self.provider.blockSignals(False)
        if self.provider.currentData() != self.settings.get("ai", "provider"):
            self.binder.set("ai", "provider", self.provider.currentData())
        engines = {k: v["name"] for k, v in voices.ENGINES.items() if not off or k in OFFLINE_VOICES}
        self.engine.blockSignals(True)
        fill(self.engine, engines)
        self._select(self.engine, self.settings.get("voice", "engine"))
        self.engine.blockSignals(False)
        if self.engine.currentData() != self.settings.get("voice", "engine"):
            self.binder.set("voice", "engine", self.engine.currentData())
        self._provider_changed(init=True)
        self._engine_changed(init=True)

    def refresh_status(self, force: bool = False):
        if getattr(self, "_status_busy", False):
            return
        self._status_busy = True

        def done(st):
            self._status_busy = False
            self._status = st
            self._show_status()

        def fail(_m):
            self._status_busy = False
        Bg(lambda: hybrid.status(self.settings, force=force), done, fail)

    def _show_status(self):
        st = self._status
        if not st:
            return
        parts, tips = [], []
        for name, ok, tip in hybrid.describe(st):
            parts.append(f"<span style='color:{'#3DDC97' if ok else '#6C7489'}'>●</span> {name}")
            tips.append(("✅ " if ok else "⚪ ") + f"{name}: {tip}")
        chain = self._ai_chain_text()
        if chain:
            tips.append(f"\nAI dịch sẽ dùng: {chain}")
        self.status.setText("&nbsp;&nbsp;".join(parts))
        self.status.setToolTip("\n".join(tips))
        self.refresh_ai()

    def _ai_chain_text(self) -> str:
        st = self._status
        pid = self.provider.currentData() or "auto"
        online = [k for k in ai.FALLBACK_ORDER if k in st.get("keys", [])] if st.get("net") and \
            self.settings.mode != "offline" else []
        if self.settings.mode == "offline":
            chain = ["ollama"]
        elif pid == "ollama":
            chain = ["ollama", *online] if st.get("ollama_ready") else [*online, "ollama"]
        elif pid == "auto":
            chain = [*online, "ollama"]
        else:
            chain = [pid, *[k for k in online if k != pid], "ollama"]
        names = {"ollama": "AI trên máy", "gemini": "Gemini", "claude": "Claude", "openai": "OpenAI",
                 "groq": "Groq", "openrouter": "OpenRouter", "deepseek": "DeepSeek"}
        return " → ".join(names[c] for c in dict.fromkeys(chain))

    def _provider_changed(self, *_a, init=False):
        pid = self.provider.currentData() or "auto"
        if not init:
            self.binder.set("ai", "provider", pid)
        self.model.blockSignals(True)
        self.model.clear()
        if pid == "ollama":
            self.model.addItems(list(dict.fromkeys([*ai.OLLAMA_MODELS, *self._status.get("ollama_models", [])])))
            keep = hybrid.ollama_model(self.settings)
        elif pid == "auto":
            keep = ""
        else:
            cur = self.settings.get("ai", "model") or ""
            self.model.addItems(ai.PROVIDERS[pid]["models"])
            keep = cur if (cur and ai.model_fits(pid, cur) and not cur.startswith(tuple(ai.OLLAMA_MODELS))) else \
                ai.PROVIDERS[pid]["default"]
            self.binder.set("ai", "model", keep)
        self.model.setEditText(keep)
        self.model.blockSignals(False)
        self.model.setEnabled(pid != "auto")
        self.model.lineEdit().setPlaceholderText("tự chọn model tốt nhất" if pid == "auto" else "")
        self.refresh_ai()

    def _model_changed(self, text: str):
        t = text.strip()
        pid = self.provider.currentData() or "auto"
        if t and pid != "auto":
            self.binder.set("ai", "ollama_model" if pid == "ollama" else "model", t)

    def refresh_ai(self):
        pid = self.provider.currentData() or "auto"
        st = self._status
        if not st:
            self.lb_ai.setText("⏳ Đang kiểm tra AI...")
            return
        chain = self._ai_chain_text()
        if pid == "ollama" or (pid == "auto" and chain == "AI trên máy"):
            m = hybrid.ollama_model(self.settings)
            if st.get("ollama_ready"):
                msg = f"● AI trên máy sẵn sàng ({m})"
            elif st.get("ollama"):
                msg = f"⚠️ Chưa tải {m} → ⚙️ Cài đặt → Tải model AI"
            elif st.get("ollama_installed"):
                msg = "○ Ollama chưa mở - app sẽ tự mở khi cần"
            else:
                msg = "○ Chưa có AI: nhập API key Gemini (miễn phí) trong ⚙️ Cài đặt, hoặc cài Ollama"
            self.lb_ai.setText(msg + (f"\nDự phòng: {chain}" if "→" in chain else ""))
        else:
            k = ai.PROVIDERS[pid]["key"] if pid != "auto" else None
            if k and not self.settings.key(k):
                self.lb_ai.setText("⚠️ Chưa nhập API key (⚙️ Cài đặt) - sẽ tự dùng AI khác: " + chain)
            else:
                self.lb_ai.setText(f"Thứ tự: {chain}" + ("" if st.get("net") or self.settings.mode == "offline"
                                                          else " (đang mất mạng)"))

    def _engine_changed(self, *_a, init=False):
        eng = self.engine.currentData() or "edge"
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
        from vietdub import components

        need = {"vieneu": "vieneu", "piper": "piper"}.get(eng)
        self.lb_voice.setText("⚠️ Chưa tải giọng này → bấm 📦 Thư viện → Tải (lúc làm video app sẽ tạm dùng giọng "
                              "dự phòng)" if need and not components.status().get(need) else "")
        if self.voice.currentData() is not None:
            self.binder.set("voice", "voice", self.voice.currentData())

    def _bg_changed(self):
        from vietdub import separate

        mode = self.bg.currentData()
        ok = separate.available()
        self.btn_sep.setVisible(mode == "separate" and not ok)
        self.ov.setEnabled(mode == "duck")
        self.lb_bg.setText({"separate": ("Bỏ giọng gốc, giữ nhạc nền & tiếng động. Lần đầu tải model ~67 MB; "
                                         "có card đồ họa thì nhanh hơn." if ok else
                                         "Chưa cài bộ tách nhạc - bấm nút trên (tạm dùng tiếng gốc nhỏ)."),
                            "duck": "Tiếng gốc nhỏ dưới giọng thuyết minh, tự giảm thêm lúc đang đọc.",
                            "mute": "Chỉ còn giọng thuyết minh."}.get(mode, ""))

    def install_separator(self):
        from vietdub import separate

        def job(log, progress, cancel):
            import subprocess

            from vietdub.media import no_window

            progress(0.2, "Cài onnxruntime")
            r = subprocess.run(separate.install_command(), capture_output=True, text=True, encoding="utf-8",
                               errors="replace", **no_window())
            if r.returncode != 0:
                raise RuntimeError("Cài lỗi:\n" + (r.stderr or r.stdout)[-600:])
            import importlib

            importlib.invalidate_caches()
            separate.model_path(self.settings, log, progress, cancel)
            return True
        self.run_task(job, "Cài tách nhạc AI", on_done=lambda _r: self._bg_changed())

    def apply_preset(self, vals: dict, name: str):
        widgets = {"video.output": self.output, "video.cover": self.cover, "video.aspect": self.aspect,
                   "video.fill": self.fill_}
        for k, v in vals.items():
            sec, key = k.split(".")
            self.binder.set(sec, key, v)
            if k in widgets:
                self._select(widgets[k], v)
        self.log_msg(f"Mẫu {name}")

    def open_components(self):
        from .components_dialog import ComponentsDialog

        ComponentsDialog(self).exec()
        self._engine_changed(init=True)

    def open_region(self):
        if not self.need_project():
            return
        from .region_dialog import RegionDialog

        RegionDialog(self, self.project).exec()
        self._update_region_label()

    def _update_region_label(self):
        r = self.project.region if self.project else None
        self.lb_region.setText(f"✅ Đã đặt khung: ngang {r[0] * 100:.0f}–{r[2] * 100:.0f}%, "
                               f"dọc {r[1] * 100:.0f}–{r[3] * 100:.0f}%" if r else "")

    def open_editor(self):
        if not self.need_project():
            return
        if not self.project.lines:
            QMessageBox.information(self, "Chưa dịch", "Dịch trước (🌐 AI dịch) rồi mới chỉnh phụ đề được.")
            return
        self.project.save_lines(self.collect())
        if self.player is not None:
            self.player.pause()
        from .sub_editor import SubEditor

        SubEditor(self, self.project).exec()
        self.load_table()

    def open_settings(self):
        from .settings_dialog import SettingsDialog

        SettingsDialog(self).exec()
        self.mode_box.blockSignals(True)
        self._select(self.mode_box, self.settings.mode)
        self.mode_box.blockSignals(False)
        self.refresh_mode()
        self.refresh_status(force=True)

    # ================================================================ cập nhật trực tiếp
    def check_update(self, silent: bool = False):
        def done(info):
            self._update_info = info
            if info.get("newer"):
                self.btn_update.setText(f"⬆ Có bản mới {info['latest']}")
                self.btn_update.setObjectName("update")
                self.btn_update.style().unpolish(self.btn_update)
                self.btn_update.style().polish(self.btn_update)
                if not silent:
                    self._ask_update(info)
            elif not silent:
                QMessageBox.information(self, "Cập nhật", f"Bạn đang dùng bản mới nhất ({VERSION}).")

        def fail(msg):
            if not silent:
                QMessageBox.warning(self, "Cập nhật", msg)
        Bg(lambda: updater.check(self.settings), done, fail)

    def do_update(self):
        if self._update_info and self._update_info.get("newer"):
            self._ask_update(self._update_info)
        else:
            self.check_update(silent=False)

    def _ask_update(self, info: dict):
        ch = "\n".join("• " + c for c in info.get("changes", [])[:6])
        r = QMessageBox.question(self, "Có bản mới", f"Bản hiện tại: {info['current']}\nBản mới: {info['latest']}\n\n"
                                 + (f"Thay đổi gần đây:\n{ch}\n\n" if ch else "")
                                 + "Cập nhật ngay? (cài đặt, dự án và model của bạn được giữ nguyên)")
        if r != QMessageBox.Yes:
            return

        def done(res):
            if res.get("updated") and QMessageBox.question(
                    self, "Đã cập nhật", f"Đã cập nhật lên {res['latest']}.\nKhởi động lại app ngay?") == QMessageBox.Yes:
                self.restart()
        self.run_task(lambda log, progress, cancel: updater.update(self.settings, log, progress, cancel),
                      "Cập nhật app", on_done=done)

    def restart(self):
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication

        cmd = updater.restart_command()
        self.settings.save()
        if QProcess.startDetached(cmd[0], cmd[1:]):
            QApplication.quit()

    # ================================================================ video & bảng
    def open_video(self, path: str):
        if Path(path).suffix.lower() not in VIDEO_EXT:
            QMessageBox.warning(self, "Không phải video", "Hãy chọn file video (mp4, mkv, webm, mov...).")
            return
        try:
            self.project = Project(path, self.settings)
        except (MediaError, OSError) as e:
            QMessageBox.critical(self, "Không mở được video", str(e))
            return
        p = self.project
        self.lb_film.setText(f"<b>{Path(path).name}</b><br>{p.info.summary()}")
        side = transcript.find_sidecar(path)
        self.sub_file.setText(str(side) if side else "")
        self._update_tr_label()
        self._update_region_label()
        self.load_table()
        self._load_media(path)
        self.btn_pub.setEnabled(bool(p.publish_info) or p.thumbnail.exists())
        self.log_msg(f"Đã mở video: {Path(path).name}")
        p.start_analysis(lambda m, level="info": None)  # dò phụ đề gốc sẵn từ bây giờ (chạy nền)

    def _sub_changed(self, v):
        if self.project:
            self.project.subtitle_file = v if v and Path(v).exists() else ""

    def _update_tr_label(self):
        p = self.project
        self.lb_tr.setText(f"✅ Đã có lời gốc: {len(p.source)} câu" if p and p.source else "")

    def load_table(self):
        p = self.project
        rows = (p.lines if p and p.lines else [{**x, "vi": ""} for x in (p.source if p else [])])
        self._loading_table = True
        self.table.setRowCount(0)
        for ln in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, v in enumerate((fmt(ln["start"]), fmt(ln["end"]), ln.get("text", ""), ln.get("vi", ""))):
                it = QTableWidgetItem(v)
                if c == 2:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    it.setForeground(QColor("#AEB4C8"))
                self.table.setItem(r, c, it)
        self._loading_table = False
        self._update_est()

    def collect(self) -> list[dict]:
        p = self.project
        base = (p.lines if p and p.lines else (p.source if p else [])) or []
        out = []
        for r in range(self.table.rowCount()):
            def cell(c):
                it = self.table.item(r, c)
                return it.text() if it else ""
            src = base[r] if r < len(base) else {}
            st, en = transcript._ts(cell(0)), transcript._ts(cell(1))
            # giữ phần lẻ giây của mốc gốc nếu người dùng không sửa ô thời gian
            if src and fmt(src["start"]) == cell(0):
                st = src["start"]
            if src and fmt(src["end"]) == cell(1):
                en = src["end"]
            if en <= st:
                en = st + 2
            out.append({"start": st, "end": en, "text": cell(2), "vi": cell(3).strip()})
        return out

    def _table_changed(self):
        if self._loading_table or not self.project or not self.project.lines:
            return
        self.project.save_lines(self.collect())
        self._update_est()

    def _update_est(self):
        lines = self.collect()
        if not lines:
            self.lb_est.setText("Chưa có lời thoại")
            return
        done = sum(1 for x in lines if x["vi"])
        too_long = sum(1 for i, x in enumerate(lines) if x["vi"] and len(x["vi"]) >
                       translate.max_chars(x, lines[i + 1] if i + 1 < len(lines) else None) * 1.35)
        self.lb_est.setText(f"{len(lines)} câu · đã dịch {done}" + (f" · ⚠️ {too_long} câu dài" if too_long else ""))

    # ================================================================ chạy tác vụ
    def need_project(self) -> bool:
        if not self.project:
            QMessageBox.information(self, "Chưa có video", "Hãy kéo thả, chọn video hoặc dán link trước.")
            return False
        return True

    def _buttons(self):
        return (self.btn_all, self.btn_render, self.btn_tr, self.btn_stt, self.btn_prev, self.btn_edit, self.btn_oc)

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
        for b in self._buttons():
            b.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log_msg(f"▶ {title}")

        def finish():
            self.worker = None
            for b in self._buttons():
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
        sub = {"start": "đang làm...", "skip": "bỏ qua", "fail": "lỗi", "pending": "chờ"}.get(state, "")
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
    def do_download(self):
        url = self.link.text().strip()
        if not download.is_url(url):
            QMessageBox.information(self, "Dán link", "Dán link video (https://...) vào ô rồi bấm Tải.")
            return
        if self.settings.offline:
            QMessageBox.information(self, "Đang ở chế độ Chỉ trên máy",
                                    "Đổi chế độ (góc trên) sang ⚡ Tự động để tải video từ link.")
            return

        def done(path):
            self.link.clear()
            self.open_video(str(path))
        self.run_task(lambda log, progress, cancel: download.download(url, self.settings, log, progress, cancel),
                      "Tải video từ link", on_done=done)

    def do_transcript(self):
        if not self.need_project():
            return
        p = self.project
        self._reset_chips()

        def job(log, progress, cancel, step):
            step("transcript", "start")
            r = p.run_transcript(log, progress, cancel)
            step("transcript", "done", f"{len(r)} câu")
            return r
        self.run_task(job, "Lấy lời gốc", on_done=lambda _r: (self._update_tr_label(), self.load_table()),
                      with_steps=True)

    def do_translate(self):
        if not self.need_project():
            return
        p = self.project
        if p.lines and QMessageBox.question(self, "Dịch lại?", "Dịch lại toàn bộ? Chỗ bạn đã sửa tay sẽ bị thay.") \
                != QMessageBox.Yes:
            return
        self._reset_chips()

        def job(log, progress, cancel, step):
            if not p.source:
                step("transcript", "start")
                p.run_transcript(log, lambda x, m="": progress(x * 0.5, m), cancel)
                step("transcript", "done")
            step("translate", "start")
            r = p.run_translate(log, lambda x, m="": progress(0.5 + x * 0.5, m), cancel)
            step("translate", "done", f"{len(r)} câu")
            return r
        self.run_task(job, "AI dịch", on_done=lambda _r: (self._update_tr_label(), self.load_table()),
                      with_steps=True)

    def do_render(self):
        if not self.need_project():
            return
        if not self.project.lines:
            QMessageBox.information(self, "Chưa dịch", "Bấm '🌐 AI dịch' hoặc '⚡ VIỆT HÓA' trước.")
            return
        p = self.project
        p.save_lines(self.collect())
        self._reset_chips()
        self.run_task(lambda log, progress, cancel, step: p.run_render(None, log, progress, cancel, step),
                      "Xuất video", on_done=self.finished, with_steps=True)

    def do_all(self):
        if not self.need_project():
            return
        p = self.project
        if p.lines:
            p.save_lines(self.collect())
        self._reset_chips()
        self.run_task(lambda log, progress, cancel, step: p.run_all(None, log, progress, cancel, step),
                      "Việt hóa video", on_done=lambda out: (self._update_tr_label(), self.load_table(),
                                                             self.finished(out)), with_steps=True)

    def do_preview(self):
        if not self.need_project():
            return
        if not self.project.lines:
            QMessageBox.information(self, "Chưa dịch", "Dịch trước rồi mới xem thử được.")
            return
        r = max(0, self.table.currentRow())
        p = self.project
        p.save_lines(self.collect())
        t0 = p.lines[r]["start"] if r < len(p.lines) else 0.0
        self.run_task(lambda log, progress, cancel: p.preview(t0, 20.0, log, progress, cancel),
                      "Xem thử 20 giây", on_done=lambda f: self._load_media(str(f), play=True))

    def finished(self, out):
        self.last_output = Path(out)
        self.btn_pub.setEnabled(True)
        self._load_media(str(out))
        self.open_folder()

    def open_opencut(self):
        """Dựng tiếp trong OpenCut: chưa mở video thì mở danh sách dự án OpenCut."""
        from vietdub import opencut

        p = self.project
        if p is not None and p.lines:
            p.save_lines(self.collect())

        def job(log, progress, cancel):
            if not opencut.up_to_date():
                opencut.install(self.settings, log, progress, cancel)
            base = opencut.start()
            if p is None or not p.lines:
                return base + "/projects/"
            pk = p.opencut_package(log, progress, cancel)
            opencut.share(pk["files"], pk["manifest"])
            log("Mở OpenCut: video, thuyết minh và phụ đề Việt sẽ được nạp sẵn trên dòng thời gian.")
            return opencut.editor_url(base, pk["manifest"])

        def done(url):
            opencut.open_window(url)
            if not opencut.browser():
                QMessageBox.information(self, "OpenCut", "Không thấy Edge/Chrome - đã mở bằng trình duyệt mặc định. "
                                        "OpenCut chạy tốt nhất trên Edge hoặc Chrome.")
        self.run_task(job, "Chuẩn bị OpenCut", on_done=done)

    def open_publish(self):
        if not self.need_project():
            return
        from .publish_dialog import PublishDialog

        PublishDialog(self, self.project).exec()

    def preview_voice(self):
        eng = self.engine.currentData()
        voice = self.voice.currentData() or ""
        out = Path(self.settings.path).parent / "preview" / f"giong_{int(time.time())}.wav"
        self.run_task(lambda log, progress, cancel: voices.synth(eng, voices.SAMPLE, voice, out, self.settings, log),
                      "Nghe thử giọng", on_done=lambda f: self._load_media(str(f), play=True))

    # ================================================================ xem video
    def _load_media(self, path: str, play: bool = False, start: float = 0.0):
        self._media = Path(path)
        if self.player is None:
            if play:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            return
        self.video_w.show()
        self.player_bar.show()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        if start:
            self.player.setPosition(int(start * 1000))
        if play:
            self.player.play()
        else:
            self.player.pause()

    def toggle_play(self):
        if self.player is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _open_current_media(self):
        m = getattr(self, "_media", None)
        if m and Path(m).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(m)))

    def _seek_row(self, r: int):
        if r < 0 or not self.project or self.player is None or self._loading_table:
            return
        it = self.table.item(r, 0)
        if not it:
            return
        if getattr(self, "_media", None) != Path(self.project.video):
            self._load_media(self.project.video)
        self.player.setPosition(int(transcript._ts(it.text()) * 1000))

    def open_folder(self):
        target = self.last_output if self.last_output and self.last_output.exists() else None
        if target and sys.platform.startswith("win"):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(str(target))}"')
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent if target else self.settings.output_dir())))

    def play(self):
        if self.last_output and self.last_output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))

    def closeEvent(self, e):
        if self.worker is not None:
            if QMessageBox.question(self, "Đang làm việc", "App đang làm việc. Hủy và thoát?") != QMessageBox.Yes:
                e.ignore()
                return
            self.worker.cancel.set()
            self.worker.wait(3000)
        if self.player is not None:
            self.player.stop()
        self.settings.save()
        super().closeEvent(e)
