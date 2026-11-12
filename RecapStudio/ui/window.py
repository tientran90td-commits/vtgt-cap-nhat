"""Cửa sổ chính: 1 màn hình duy nhất - ① Phim · ② Thiết lập · ③ Kịch bản - và nút TẠO VIDEO.

Mọi việc kiểm tra (mạng, Ollama, bản mới) chạy nền nên giao diện không bao giờ bị đơ."""
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

from recapstudio import APP_NAME, VERSION, ai, download, hybrid, render, transcript, updater, voices, writer
from recapstudio.config import MODES, Settings
from recapstudio.media import ENCODERS, MediaError
from recapstudio.project import STEPS, Project
from recapstudio.transcript import fmt

from .common import Bg, Binder, PathPicker, Worker, button, card, fill, label, row, spin

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except ImportError:  # thiếu QtMultimedia -> mở bằng trình phát của máy
    QMediaPlayer = None

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg")
OFFLINE_VOICES = ("vieneu", "piper", "sapi")
PRESETS = [  # (nút, gợi ý, thiết lập)
    ("📱 TikTok 1′", "Dọc 9:16, 1 phút, bám nhân vật", {"video.aspect": "9:16", "video.fill": "face", "ai.minutes": 1.0}),
    ("📱 Shorts 3′", "Dọc 9:16, 3 phút", {"video.aspect": "9:16", "video.fill": "face", "ai.minutes": 3.0}),
    ("▶ YouTube 5′", "Ngang 16:9, 5 phút", {"video.aspect": "16:9", "video.fill": "blur", "ai.minutes": 5.0}),
    ("🎞 YouTube 10′", "Ngang 16:9, 10 phút", {"video.aspect": "16:9", "video.fill": "blur", "ai.minutes": 10.0}),
]


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
        main.addWidget(row(label(f"🎬 {APP_NAME}", "title", wrap=False), label(f"v{VERSION}", "muted", wrap=False),
                           self.mode_box, self.status, "stretch", self.btn_update,
                           button("⚙️ Cài đặt", self.open_settings)))

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._col_film(), 0)
        body.addWidget(self._col_settings(), 0)
        body.addWidget(self._col_script(), 1)
        main.addLayout(body, 1)
        main.addWidget(self._bottom())
        self._status: dict = {}
        self._update_info: dict | None = None
        self.refresh_mode()
        self.refresh_status()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_status)
        self._timer.start(60_000)
        if self.settings.get("update", "auto_check", True) and self.settings.mode != "offline":
            QTimer.singleShot(2500, lambda: self.check_update(silent=True))

    # ================================================================ cột ① phim
    def _col_film(self) -> QWidget:
        c, lay = card("① Phim")
        c.setFixedWidth(340)
        self.drop = DropZone(self.open_video)
        lay.addWidget(self.drop)
        self.link = QLineEdit()
        self.link.setPlaceholderText("hoặc dán link YouTube / TikTok / Facebook...")
        self.link.returnPressed.connect(self.do_download)
        b_dl = button("⬇ Tải", self.do_download, tip="Tải phim từ link (yt-dlp) rồi mở luôn")
        b_dl.setFixedWidth(64)
        lay.addWidget(row(self.link, b_dl, stretch=False))
        self.player = None
        if QMediaPlayer is not None:
            self.video_w = QVideoWidget()
            self.video_w.setFixedHeight(172)
            self.video_w.setStyleSheet("background:#000; border-radius:10px;")
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.6)
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

        c, lay = card("⚡ Mẫu nhanh")
        pres = []
        for name, tip, vals in PRESETS:
            pb = button(name, lambda _=False, v=vals, n=name: self.apply_preset(v, n), "preset", tip)
            pres.append(pb)
        g = QGridLayout()
        for i, pb in enumerate(pres):
            g.addWidget(pb, i // 2, i % 2)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("② Kịch bản AI")
        self.provider = fill(QComboBox(), {})
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setMinimumContentsLength(6)
        self.model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.model.currentTextChanged.connect(self._model_changed)
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
        self.snap = b.check(QCheckBox("Khớp đầu đoạn vào điểm chuyển cảnh"), "video", "snap_scenes")
        items = [("Khung hình", row(self.aspect, self.height_, stretch=False)), ("Lấp khung", self.fill_),
                 ("Phụ đề", row(self.subs, self.sub_size, self.sub_pos, stretch=False)),
                 ("Phụ đề gốc", row(self.cover, self.cover_h, stretch=False)), ("Nhạc nền", self.music),
                 ("Tiếng phim gốc", row(self.ov, label("khi thuyết minh (0 = tắt)", "muted", wrap=False), stretch=False)),
                 ("Cắt cảnh", self.snap),
                 ("Mã hóa", row(self.encoder, self.parallel, label("cùng lúc", "muted", wrap=False), stretch=False))]
        for i, (k, w) in enumerate(items):
            g.addWidget(label(k, "muted"), i, 0)
            g.addWidget(w, i, 1)
        lay.addLayout(g)
        col.addWidget(c)

        c, lay = card("📤 Đăng bài")
        lay.addWidget(b.check(QCheckBox("Tạo ảnh bìa (thumbnail) từ khung hình đẹp nhất"), "publish", "thumbnail"))
        lay.addWidget(b.check(QCheckBox("AI viết tiêu đề, mô tả, hashtag"), "publish", "info"))
        lay.addWidget(b.check(QCheckBox("Lưu ảnh bìa + mô tả cạnh video (mặc định chỉ để video)"), "publish",
                              "save_next_to_video"))
        col.addWidget(c)
        col.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(box)
        box.setObjectName("root")
        sc.viewport().setStyleSheet("background: transparent;")
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
        self.table.currentCellChanged.connect(lambda r, _c, _pr, _pc: self._seek_row(r))
        lay.addWidget(self.table, 1)
        self.lb_est = label("", "muted")
        self.btn_script = button("✍️ AI viết kịch bản", self.do_script, "primary")
        self.btn_prev = button("👁 Xem trước đoạn", self.do_preview, tip="Dựng thử đoạn đang chọn (giọng + phụ đề)")
        lay.addWidget(row(self.btn_script, self.btn_prev, button("➕ Thêm", self.add_row), button("➖ Xóa", self.del_row),
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
            lb.setMinimumWidth(118)
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
        self.btn_pub = button("📤 Đăng video", self.open_publish, tip="Ảnh bìa, tiêu đề, mô tả, hashtag để đăng")
        self.btn_pub.setEnabled(False)
        lay.addWidget(row(self.btn_all, self.btn_render, self.btn_cancel, "stretch", self.btn_pub,
                          button("📂 Mở thư mục video", self.open_folder), button("▶ Xem video", self.play)))
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setFixedHeight(120)
        lay.addWidget(self.log)
        return w

    # ================================================================ chế độ / trạng thái
    def _mode_changed(self, *_a):
        self.binder.set(None, "mode", self.mode_box.currentData())
        self.settings.save()
        self.refresh_mode()
        self.refresh_status(force=True)

    def refresh_mode(self):
        mode = self.settings.mode
        off = mode == "offline"
        stt = {"auto": transcript.ENGINES["auto"], "gpu": transcript.ENGINES["gpu"],
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
        provs["none"] = ai.PROVIDERS["none"]["name"]
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
        """Kiểm tra mạng / Ollama / key ở luồng nền rồi cập nhật đèn trạng thái."""
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
            tips.append(f"\nAI viết kịch bản sẽ dùng: {chain}")
        self.status.setText("&nbsp;&nbsp;".join(parts))
        self.status.setToolTip("\n".join(tips))
        self.refresh_ai()

    def _ai_chain_text(self) -> str:
        st = self._status
        pid = self.provider.currentData() or "auto"
        if pid == "none":
            return ""
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

    @staticmethod
    def _select(combo: QComboBox, value):
        i = combo.findData(value)
        combo.setCurrentIndex(i if i >= 0 else 0)

    def _provider_changed(self, *_a, init=False):
        pid = self.provider.currentData() or "auto"
        if not init:
            self.binder.set("ai", "provider", pid)
        self.model.blockSignals(True)
        self.model.clear()
        if pid == "ollama":
            self.model.addItems(list(dict.fromkeys([*ai.OLLAMA_MODELS, *self._status.get("ollama_models", [])])))
            keep = hybrid.ollama_model(self.settings)
        elif pid in ("auto", "none"):
            keep = ""
        else:
            cur = self.settings.get("ai", "model") or ""
            self.model.addItems(ai.PROVIDERS[pid]["models"])
            keep = cur if (cur and ai.model_fits(pid, cur) and not cur.startswith(tuple(ai.OLLAMA_MODELS))) else \
                ai.PROVIDERS[pid]["default"]
            self.binder.set("ai", "model", keep)
        self.model.setEditText(keep)
        self.model.blockSignals(False)
        self.model.setEnabled(pid not in ("auto", "none"))
        self.model.lineEdit().setPlaceholderText("tự chọn model tốt nhất" if pid == "auto" else "")
        self.refresh_ai()

    def _model_changed(self, text: str):
        t = text.strip()
        pid = self.provider.currentData() or "auto"
        if not t or pid in ("auto", "none"):
            return
        self.binder.set("ai", "ollama_model" if pid == "ollama" else "model", t)

    def refresh_ai(self):
        """Chỉ đọc trạng thái đã kiểm tra sẵn (không gọi mạng) -> không làm đơ giao diện."""
        pid = self.provider.currentData() or "auto"
        st = self._status
        if not st:
            self.lb_ai.setText("⏳ Đang kiểm tra AI...")
            return
        if pid == "none":
            self.lb_ai.setText("Không dùng AI: app tự cắt các cảnh nổi bật, giữ tiếng gốc.")
            return
        chain = self._ai_chain_text()
        if pid == "ollama" or (pid == "auto" and chain == "AI trên máy"):
            m = hybrid.ollama_model(self.settings)
            if st.get("ollama_ready"):
                msg = f"● AI trên máy sẵn sàng ({m})"
            elif st.get("ollama"):
                msg = f"⚠️ Chưa tải {m} → ⚙️ Cài đặt → Tải model AI" + (" (hoặc app tự tải khi chạy)"
                                                                       if st.get("net") else "")
            elif st.get("ollama_installed"):
                msg = "○ Ollama chưa mở - app sẽ tự mở khi cần"
            else:
                msg = "○ Chưa cài Ollama → ⚙️ Cài đặt (hoặc nhập API key AI online)"
            self.lb_ai.setText(msg + (f"\nDự phòng: {chain}" if "→" in chain else ""))
        else:
            k = ai.PROVIDERS[pid]["key"] if pid != "auto" else None
            if k and not self.settings.key(k):
                self.lb_ai.setText("⚠️ Chưa nhập API key (⚙️ Cài đặt) - sẽ tự dùng AI khác: " + chain)
            else:
                self.lb_ai.setText(f"Thứ tự: {chain}" + ("" if st.get("net") or self.settings.mode == "offline"
                                                          else " (đang mất mạng)"))

    def apply_preset(self, vals: dict, name: str):
        for k, v in vals.items():
            sec, key = k.split(".")
            self.binder.set(sec, key, v)
        self._select(self.aspect, self.settings.get("video", "aspect"))
        self._select(self.fill_, self.settings.get("video", "fill"))
        self.minutes.setValue(float(self.settings.get("ai", "minutes")))
        self.log_msg(f"Mẫu {name}: {', '.join(f'{k.split(chr(46))[1]}={v}' for k, v in vals.items())}")

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

        def job(log, progress, cancel):
            return updater.update(self.settings, log, progress, cancel)

        def done(res):
            if not res.get("updated"):
                return
            if QMessageBox.question(self, "Đã cập nhật", f"Đã cập nhật lên {res['latest']}.\nKhởi động lại app ngay?") \
                    == QMessageBox.Yes:
                self.restart()
        self.run_task(job, "Cập nhật app", on_done=done)

    def restart(self):
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication

        cmd = updater.restart_command()
        self.settings.save()
        if QProcess.startDetached(cmd[0], cmd[1:]):
            QApplication.quit()

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
        self._load_media(path)
        self.btn_pub.setEnabled(bool(p.publish_info) or p.thumbnail.exists())
        self.log_msg(f"Đã mở phim: {Path(path).name}")
        p.start_analysis(lambda m, level="info": None)  # dò chuyển cảnh / phụ đề cứng sẵn từ bây giờ (chạy nền)

    # ================================================================ tải phim từ link
    def do_download(self):
        url = self.link.text().strip()
        if not download.is_url(url):
            QMessageBox.information(self, "Dán link", "Dán link video (https://...) vào ô rồi bấm Tải.")
            return
        if self.settings.offline:
            QMessageBox.information(self, "Đang ở chế độ Chỉ trên máy",
                                    "Đổi chế độ (góc trên) sang ⚡ Tự động để tải phim từ link.")
            return

        def job(log, progress, cancel):
            return download.download(url, self.settings, log, progress, cancel)

        def done(path):
            self.link.clear()
            self.open_video(str(path))
        self.run_task(job, "Tải phim từ link", on_done=done)

    # ================================================================ xem phim / xem trước
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

    def do_preview(self):
        if not self.need_project():
            return
        r = self.table.currentRow()
        sc = self.collect()
        if r < 0 or r >= len(sc["segments"]):
            QMessageBox.information(self, "Chọn đoạn", "Bấm chọn 1 dòng trong bảng kịch bản để xem trước.")
            return
        p = self.project
        p.save_script(sc)
        self.run_task(lambda log, progress, cancel: p.preview_segment(r, log, progress, cancel),
                      f"Xem trước đoạn {r + 1}", on_done=lambda f: self._load_media(str(f), play=True))

    # ================================================================ đăng bài
    def open_publish(self):
        if not self.need_project():
            return
        from .publish_dialog import PublishDialog

        PublishDialog(self, self.project).exec()

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
        for b in (self.btn_all, self.btn_render, self.btn_script, self.btn_stt, self.btn_prev):
            b.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log_msg(f"▶ {title}")

        def finish():
            self.worker = None
            for b in (self.btn_all, self.btn_render, self.btn_script, self.btn_stt, self.btn_prev):
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
        self.btn_pub.setEnabled(True)
        self._load_media(str(out))
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
