"""Trang 4: MỘT mục chứa toàn bộ thiết lập video thành phẩm + xuất video."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFontComboBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from recap import editor
from recap.publish import extra
from recap.ffmpeg_utils import encoder_works

from .widgets import ColorButton, Page, PathPicker, button, fill_combo, hrow, muted, reveal, scroll, spin

# thiết lập không đưa vào "mẫu của tôi" (phụ thuộc máy)
PRESET_SKIP = {"vsr_dir", "encoder"}

PRESETS = {
    "tiktok": ("📱 TikTok / Reels / Shorts", {"aspect": "9:16", "fill": "face", "height": 1080, "fps": 30,
                                             "sub_position": "middle", "sub_size": 60}),
    "youtube": ("▶️ YouTube ngang", {"aspect": "16:9", "fill": "blur", "height": 1080, "fps": 30,
                                     "sub_position": "bottom", "sub_size": 52}),
    "facebook": ("📘 Facebook vuông", {"aspect": "1:1", "fill": "blur", "height": 1080, "fps": 30,
                                       "sub_position": "bottom", "sub_size": 56}),
}


class RenderPage(Page):
    """Bước 4: MỘT mục chứa toàn bộ thiết lập của video thành phẩm + nút xuất.

    Trái: mục lục các nhóm thiết lập (bấm để nhảy tới). Giữa: tất cả thiết lập trên một trang cuộn.
    Dưới: thanh Xuất video luôn hiện."""

    def __init__(self, app):
        super().__init__(app, "🎛️  Bước 4 · Thiết lập & xuất video",
                         "Mọi thiết lập của video thành phẩm nằm trong mục này. Chọn mẫu có sẵn hoặc chỉnh từng nhóm "
                         "(bấm tên nhóm bên trái để nhảy tới), lưu thành mẫu riêng của bạn, rồi bấm XUẤT VIDEO.")
        b = app.binder
        s = app.settings
        self.sections: list[tuple[str, QGroupBox]] = []
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 8, 0)
        col.setSpacing(12)

        def section(title: str) -> QFormLayout:
            g = QGroupBox(title.replace("&", "&&"))
            f = QFormLayout(g)
            col.addWidget(g)
            self.sections.append((title, g))
            return f

        # ------------------------------------------------ ⚡ Mẫu thiết lập
        f = section("⚡ Mẫu thiết lập")
        f.addRow("Mẫu có sẵn", hrow(*[button(v[0], lambda _=False, k=k: self.apply_preset(k))
                                      for k, v in PRESETS.items()], "stretch"))
        self.my_presets = QComboBox()
        self.my_presets.setMinimumContentsLength(16)
        f.addRow("Mẫu của tôi", hrow(self.my_presets, button("✔ Áp dụng", self.apply_my_preset),
                                    button("💾 Lưu thiết lập hiện tại", self.save_my_preset, "primary"),
                                    button("🗑", self.delete_my_preset, tip="Xóa mẫu đang chọn"), "stretch"))
        f.addRow("", hrow(button("↺ Khôi phục mặc định", self.reset_defaults,
                                 tip="Đưa mọi thiết lập video về mặc định của app"), "stretch"))
        f.addRow(muted("Mẫu của tôi lưu toàn bộ thiết lập dưới đây (khung hình, phụ đề, logo, nhạc, âm lượng, thời lượng...)"
                       " - tiện khi làm nhiều kênh khác nhau."))

        # ------------------------------------------------ 🎙️ Nội dung & giọng (tóm tắt, chỉnh ở bước 2-3)
        f = section("🎙️ Nội dung & giọng đọc")
        self.lb_content = muted("")
        self.lb_content.setTextFormat(Qt.RichText)
        f.addRow(self.lb_content)
        f.addRow("", hrow(button("📝 Đổi kiểu video / phong cách (Bước 2)", lambda: self.app.goto(1)),
                          button("🎙️ Đổi giọng / cách đọc (Bước 3)", lambda: self.app.goto(2)), "stretch"))

        # ------------------------------------------------ ⏱ Thời lượng & nhịp
        f = section("⏱ Thời lượng & nhịp")
        self.minutes = b.spin(spin(0.5, 180, 0.5, " phút", decimals=1), "script", "target_minutes")
        self.minutes.setToolTip("Độ dài mong muốn của video thành phẩm - AI viết kịch bản theo độ dài này")
        quick = [button(f"{m:g}′", lambda _=False, m=m: self.minutes.setValue(m)) for m in (1, 3, 5, 10, 15)]
        for q in quick:
            q.setFixedWidth(46)
        f.addRow("Thời lượng", hrow(self.minutes, *quick, "stretch"))
        self.fit = b.check(QCheckBox("Ép đúng thời lượng khi xuất (co/giãn đoạn thoại gốc, chỉnh tốc độ đọc 0.88-1.2x, "
                                     "bỏ bớt đoạn thoại gốc nếu vẫn dài)"), "render", "fit_duration")
        f.addRow(self.fit)
        self.lb_est = muted("")
        f.addRow("", hrow(self.lb_est, button("✍️ Viết lại kịch bản theo thời lượng", self.rewrite_script), "stretch"))
        self.fit_mode = b.combo(fill_combo(QComboBox(), editor.FITS), "render", "fit")
        self.gap = b.spin(spin(0, 2, 0.05, " giây", decimals=2), "render", "gap")
        f.addRow("Khớp cảnh với giọng", self.fit_mode)
        f.addRow("Nghỉ giữa các đoạn", self.gap)
        self.minutes.valueChanged.connect(lambda _v: self.refresh_estimate())

        # ------------------------------------------------ 🖼️ Khung hình & chất lượng
        f = section("🖼️ Khung hình & chất lượng")
        self.aspect = b.combo(fill_combo(QComboBox(), editor.ASPECTS), "render", "aspect")
        self.fill = b.combo(fill_combo(QComboBox(), editor.FILLS), "render", "fill")
        self.height_ = b.combo(fill_combo(QComboBox(), {720: "720p (HD)", 1080: "1080p (Full HD)",
                                                         1440: "1440p (2K)", 2160: "2160p (4K)"}),
                               "render", "height", int)
        self.fps = b.combo(fill_combo(QComboBox(), {"source": "Giống phim gốc", 24: "24 fps", 25: "25 fps",
                                                     30: "30 fps", 60: "60 fps"}),
                           "render", "fps", int)
        self.trans = b.combo(fill_combo(QComboBox(), {"fade": "Mờ dần nhẹ giữa các đoạn (mượt)", "cut": "Cắt thẳng"}),
                             "render", "transition")
        self.encoder = b.combo(fill_combo(QComboBox(), editor.ENCODERS), "render", "encoder")
        self.quality = b.spin(spin(14, 32, 1), "render", "quality")
        self.quality.setToolTip("Số càng nhỏ chất lượng càng cao, file càng nặng (18-23 là đẹp)")
        f.addRow("Tỉ lệ", self.aspect)
        f.addRow("Lấp khung", self.fill)
        f.addRow("Độ phân giải", hrow(self.height_, QLabel("Khung hình/giây"), self.fps, "stretch"))
        f.addRow("Chuyển cảnh", self.trans)
        f.addRow("Bộ mã hóa", hrow(self.encoder, button("🔍 Kiểm tra GPU", self.check_gpu), QLabel("Chất lượng (CRF)"),
                                   self.quality, "stretch"))

        # ------------------------------------------------ 🧽 Làm sạch hình phim gốc
        f = section("🧽 Làm sạch hình phim gốc")
        from recap import vsr
        self.hardsub = b.combo(fill_combo(QComboBox(), editor.HARDSUB_MODES), "render", "hardsub_mode")
        self.vsr_mode = b.combo(fill_combo(QComboBox(), vsr.MODES), "render", "vsr_mode")
        f.addRow("Phụ đề in cứng", self.hardsub)
        f.addRow("Thuật toán AI", hrow(self.vsr_mode, button("🧩 Cài / kiểm tra VSR", lambda: self.app.goto(5)),
                                      "stretch"))
        f.addRow(b.check(QCheckBox("Che mờ logo / watermark cố định của nguồn (tự phát hiện)"), "render", "delogo"))
        f.addRow(b.check(QCheckBox("Tránh đoạn có quảng cáo / chữ chèn cứng của web phim"), "render", "avoid_overlays"))
        f.addRow(muted("Phụ đề in sẵn (Vietsub) được tự phát hiện để che, cắt, né hoặc xóa sạch bằng AI (VSR - chỉ xử lý "
                       "các cảnh được dùng). Phụ đề rời (.srt, phụ đề nhúng MKV) luôn được bỏ khỏi video xuất ra."))

        # ------------------------------------------------ 💬 Phụ đề thuyết minh
        f = section("💬 Phụ đề thuyết minh")
        self.subs = b.check(QCheckBox("Chèn phụ đề vào video"), "render", "subtitles")
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(s.get("render", "sub_font", "Arial")))
        self.font.currentFontChanged.connect(lambda fo: b._set("render", "sub_font", fo.family()))
        b.register("render", "sub_font", b._silent(self.font, lambda v: self.font.setCurrentFont(QFont(v or "Arial"))))
        self.size = b.spin(spin(16, 140, 2), "render", "sub_size")
        self.color = ColorButton(s.get("render", "sub_color", "#FFFFFF"))
        self.color.changed.connect(lambda c: b._set("render", "sub_color", c))
        b.register("render", "sub_color", lambda v: self.color.set_color(v or "#FFFFFF"))
        self.ocolor = ColorButton(s.get("render", "sub_outline_color", "#000000"))
        self.ocolor.changed.connect(lambda c: b._set("render", "sub_outline_color", c))
        b.register("render", "sub_outline_color", lambda v: self.ocolor.set_color(v or "#000000"))
        self.outline = b.spin(spin(0, 10, 0.5, decimals=1), "render", "sub_outline")
        self.pos = b.combo(fill_combo(QComboBox(), {"bottom": "Dưới", "middle": "Giữa", "top": "Trên"}),
                           "render", "sub_position")
        self.bold = b.check(QCheckBox("Chữ đậm"), "render", "sub_bold")
        self.maxc = b.spin(spin(16, 80, 1, " ký tự/dòng"), "render", "sub_max_chars")
        self.orig = b.check(QCheckBox("Hiện phụ đề thoại gốc ở các đoạn giữ thoại"), "render", "sub_original")
        f.addRow(self.subs)
        f.addRow("Phông chữ", hrow(self.font, QLabel("Cỡ (1080p)"), self.size, self.bold, "stretch"))
        f.addRow("Màu chữ / viền", hrow(self.color, self.ocolor, QLabel("Độ dày viền"), self.outline, "stretch"))
        f.addRow("Vị trí", hrow(self.pos, self.maxc, "stretch"))
        f.addRow(self.orig)

        # ------------------------------------------------ 🏷️ Tiêu đề mở đầu & logo
        f = section("🏷️ Tiêu đề mở đầu & logo kênh")
        self.title = b.line(QLineEdit(), "render", "title_text")
        self.title.setPlaceholderText("Chữ hiện ở đầu video (để trống = không có)")
        self.tsec = b.spin(spin(1, 15, 0.5, " giây", decimals=1), "render", "title_seconds")
        self.logo = PathPicker("file", "Ảnh (*.png *.jpg *.jpeg *.webp)", "(tùy chọn) Logo/watermark PNG")
        self.logo.setText(s.get("render", "logo", ""))
        self.logo.changed.connect(lambda v: b._set("render", "logo", v))
        b.register("render", "logo", lambda v: self.logo.setText(v or ""))
        self.lpos = b.combo(fill_combo(QComboBox(), {"top-right": "Trên phải", "top-left": "Trên trái",
                                                      "bottom-right": "Dưới phải", "bottom-left": "Dưới trái"}),
                            "render", "logo_position")
        self.lscale = b.spin(spin(0.03, 0.5, 0.01, decimals=2), "render", "logo_scale")
        f.addRow("Tiêu đề mở đầu", hrow(self.title, button("Lấy từ kịch bản", self.title_from_script),
                                       QLabel("hiện trong"), self.tsec, stretch_last=False))
        f.addRow(b.check(QCheckBox("Video nhiều tập: hiện chữ \"Tập N\" khi câu chuyện chuyển sang tập mới"), "render",
                         "episode_labels"))
        f.addRow("Logo", self.logo)
        f.addRow("Vị trí / kích thước", hrow(self.lpos, self.lscale, "stretch"))

        # ------------------------------------------------ 🔊 Âm thanh & nhạc nền
        f = section("🔊 Âm thanh & nhạc nền")
        self.vv = b.spin(spin(0, 3, 0.05, decimals=2), "render", "voice_volume")
        self.ov = b.spin(spin(0, 1, 0.02, decimals=2), "render", "orig_volume_voice")
        self.oc = b.spin(spin(0, 2, 0.05, decimals=2), "render", "orig_volume_clip")
        self.music = PathPicker("file", "Âm thanh (*.mp3 *.wav *.m4a *.aac *.ogg *.flac)", "(tùy chọn) Nhạc nền")
        self.music.setText(s.get("render", "music", ""))
        self.music.changed.connect(lambda v: b._set("render", "music", v))
        b.register("render", "music", lambda v: self.music.setText(v or ""))
        self.mv = b.spin(spin(0, 1, 0.01, decimals=2), "render", "music_volume")
        f.addRow("Giọng thuyết minh", self.vv)
        f.addRow("Tiếng phim khi thuyết minh", hrow(self.ov, muted("0 = tắt hẳn (khuyên dùng, không lẫn lời nhân vật)"),
                                                   "stretch"))
        f.addRow("Tiếng phim ở đoạn thoại gốc", self.oc)
        f.addRow("Nhạc nền", hrow(self.music, QLabel("Âm lượng"), self.mv, stretch_last=False))
        f.addRow(b.check(QCheckBox("Cân bằng âm lượng tổng (-16 LUFS, to đều như YouTube)"), "render", "loudnorm"))

        # ------------------------------------------------ 🎯 Chọn cảnh
        f = section("🎯 Chọn cảnh")
        for key, text, tip in (
                ("sentence_sync", "Khớp hình theo TỪNG CÂU thuyết minh (mỗi câu chiếu đúng khoảnh khắc nó kể)",
                 "AI gán mốc phim cho từng câu; app chia giọng đọc theo khoảng lặng giữa các câu"),
                ("no_reuse", "Không lặp lại cảnh đã chiếu (tự lấy cảnh mới gần đó)", ""),
                ("final_qa", "Kiểm tra video sau khi xuất: màn hình đen, đứng hình, âm lượng", "")):
            cb = b.check(QCheckBox(text), "render", key)
            cb.setToolTip(tip)
            f.addRow(cb)
        f.addRow(muted("Đoạn cần bỏ qua (intro, OP/ED, cảnh nhạy cảm...) nhập ở Bước 1 → ô 'Bỏ qua đoạn'."))

        # ------------------------------------------------ 📣 Sau khi xuất
        f = section("📣 Sau khi xuất & đăng video")
        self.only_video = b.check(QCheckBox("Thư mục xuất CHỈ để lại video thành phẩm (file phụ xem ở nút 📣)"),
                                  "render", "only_video")
        self.auto_open = b.check(QCheckBox("Xuất xong tự mở thư mục chứa video"), "render", "open_folder_after")
        self.pub_thumbs = b.check(QCheckBox("Tự tạo thumbnail (16:9 + dọc 9:16 + 2 phương án)"), "render",
                                  "publish_thumbs")
        self.pub_meta = b.check(QCheckBox("AI viết tiêu đề, mô tả, hashtag, mốc chương YouTube"), "render",
                                "publish_meta")
        for w in (self.only_video, self.auto_open, self.pub_thumbs, self.pub_meta):
            f.addRow(w)
        col.addStretch(1)

        # mục lục bên trái
        self.nav = QListWidget()
        self.nav.setFixedWidth(230)
        self.nav.setObjectName("subnav")
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for title, _g in self.sections:
            self.nav.addItem(title)
        self.body_scroll = scroll(body)
        self.nav.currentRowChanged.connect(self._jump)
        self.body_scroll.verticalScrollBar().valueChanged.connect(self._sync_nav)
        mid = QHBoxLayout()
        mid.addWidget(self.nav)
        mid.addWidget(self.body_scroll, 1)
        self.root.addLayout(mid, 1)

        # ------------------------------------------------ thanh Xuất video (luôn hiện)
        g5 = QGroupBox("📦 Xuất video")
        f5 = QFormLayout(g5)
        self.outdir = PathPicker("dir", placeholder=str(s.output_dir()))
        self.outdir.setText(s.get("paths", "output", ""))
        self.outdir.changed.connect(lambda v: b._set("paths", "output", v))
        self.fname = QLineEdit()
        self.fname.setPlaceholderText("Tên file (để trống = theo tiêu đề kịch bản)")
        self.lb_sum = muted("")
        f5.addRow("Lưu vào", hrow(self.outdir, self.fname))
        self.btn_go = button("🚀  XUẤT VIDEO", self.render, "big")
        self.lb_out = muted("")
        self.lb_out.setTextFormat(Qt.RichText)
        self.lb_out.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.lb_out.linkActivated.connect(lambda _l: self.open_dir())
        f5.addRow(hrow(self.btn_go, button("📂 Mở thư mục", self.open_dir), button("▶ Xem video", self.play_last),
                       button("📣 Tiêu đề && thumbnail", self.show_publish), self.lb_sum,
                       "stretch", button("🧹 Xóa bản dựng tạm", self.clear_cache)))
        f5.addRow(self.lb_out)
        self.root.addWidget(g5)
        self.last_output: Path | None = None
        b.changed.connect(lambda sec, _k: self.refresh_summary() if sec in ("render", "script") else None)
        self._load_my_presets()
        self.refresh_summary()

    # ------------------------------------------------ mục lục
    def _jump(self, row: int):
        if 0 <= row < len(self.sections):
            g = self.sections[row][1]
            self._jumping = True
            self.body_scroll.verticalScrollBar().setValue(max(0, g.y() - 6))
            self._jumping = False

    def _sync_nav(self, value: int):
        if getattr(self, "_jumping", False):
            return
        row = 0
        for i, (_t, g) in enumerate(self.sections):
            if g.y() <= value + 40:
                row = i
        if self.nav.currentRow() != row:
            self.nav.blockSignals(True)
            self.nav.setCurrentRow(row)
            self.nav.blockSignals(False)

    # ------------------------------------------------ mẫu thiết lập
    def apply_preset(self, key):
        for k, v in PRESETS[key][1].items():
            self.app.settings.set("render", k, v)
        self.app.settings.save()
        self.app.binder.reload("render")
        self.refresh_summary()
        self.app.log(f"Đã áp dụng mẫu {PRESETS[key][0]}")

    def _load_my_presets(self):
        cur = self.my_presets.currentText()
        self.my_presets.clear()
        names = sorted((self.app.settings.get("ui", "video_presets") or {}).keys())
        if not names:
            self.my_presets.addItem("(chưa có mẫu)", None)
        for n in names:
            self.my_presets.addItem(n, n)
        i = self.my_presets.findText(cur)
        if i >= 0:
            self.my_presets.setCurrentIndex(i)

    def save_my_preset(self):
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Lưu mẫu thiết lập", "Tên mẫu (vd: Kênh TikTok review):",
                                        text=self.my_presets.currentData() or "")
        name = (name or "").strip()
        if not ok or not name:
            return
        s = self.app.settings
        render = {k: v for k, v in s.section("render").items() if k not in PRESET_SKIP}
        presets = dict(s.get("ui", "video_presets") or {})
        presets[name] = {"render": render, "target_minutes": s.get("script", "target_minutes", 5)}
        s.set("ui", "video_presets", presets)
        s.save()
        self._load_my_presets()
        self.my_presets.setCurrentIndex(self.my_presets.findText(name))
        self.app.log(f"💾 Đã lưu mẫu thiết lập '{name}'.")

    def apply_my_preset(self):
        name = self.my_presets.currentData()
        p = (self.app.settings.get("ui", "video_presets") or {}).get(name) if name else None
        if not p:
            return
        s = self.app.settings
        for k, v in (p.get("render") or {}).items():
            s.set("render", k, v)
        if p.get("target_minutes"):
            s.set("script", "target_minutes", p["target_minutes"])
        s.save()
        self.app.binder.reload()
        self.refresh_summary()
        self.refresh_estimate()
        self.app.log(f"Đã áp dụng mẫu của tôi '{name}'.")

    def delete_my_preset(self):
        name = self.my_presets.currentData()
        if not name or QMessageBox.question(self, "Xóa mẫu", f"Xóa mẫu '{name}'?") != QMessageBox.Yes:
            return
        presets = dict(self.app.settings.get("ui", "video_presets") or {})
        presets.pop(name, None)
        self.app.settings.set("ui", "video_presets", presets)
        self.app.settings.save()
        self._load_my_presets()

    def reset_defaults(self):
        from recap.config import DEFAULTS

        if QMessageBox.question(self, "Khôi phục mặc định", "Đưa mọi thiết lập video về mặc định của app? "
                                "(Mẫu của tôi vẫn được giữ.)") != QMessageBox.Yes:
            return
        s = self.app.settings
        for k, v in DEFAULTS["render"].items():
            if k not in PRESET_SKIP:
                s.set("render", k, v)
        s.set("script", "target_minutes", DEFAULTS["script"]["target_minutes"])
        s.save()
        self.app.binder.reload()
        self.refresh_summary()
        self.refresh_estimate()
        self.app.log("Đã khôi phục thiết lập video mặc định.")

    def refresh_summary(self):
        s = self.app.settings
        r = s.section("render")
        mins = float(s.get("script", "target_minutes", 5) or 5)
        self.lb_sum.setText(f"{editor.ASPECTS.get(r.get('aspect'), r.get('aspect'))} · {r.get('height')}p · "
                            f"{mins:g} phút" + (" · ép thời lượng" if r.get("fit_duration") else ""))
        try:
            from recap import script_writer, tts
            v = s.section("voice")
            sc = s.section("script")
            eng = tts.ENGINES.get(v.get("engine"), {}).get("name", v.get("engine"))
            rs = tts.READ_STYLES.get(v.get("read_style") or "natural", {}).get("name", "")
            mode = script_writer.MODES.get(sc.get("mode"), sc.get("mode"))
            style = script_writer.STYLES.get(sc.get("style"), {}).get("name", sc.get("style"))
            self.lb_content.setText(f"Kiểu video: <b>{mode}</b> · Phong cách: <b>{style}</b><br>"
                                    f"Giọng: <b>{v.get('voice') or '(chưa chọn)'}</b> ({eng}) · Cách đọc: <b>{rs}</b>"
                                    + (" · giữ 1 giọng đồng nhất" if v.get("consistent", True) else ""))
        except Exception:  # noqa: BLE001
            pass

    def title_from_script(self):
        p = self.app.project
        if p and p.script:
            self.title.setText(p.script.get("title", ""))

    def check_gpu(self):
        def job(log, progress, cancel):
            res = {}
            for i, e in enumerate(editor.ENCODERS):
                progress(i / len(editor.ENCODERS), f"Thử {e}")
                res[e] = encoder_works(e)
            return res

        def done(res):
            ok = [editor.ENCODERS[k] for k, v in res.items() if v]
            QMessageBox.information(self, "Bộ mã hóa khả dụng", "Dùng được:\n• " + "\n• ".join(ok))
            best = next((k for k in ("h264_nvenc", "h264_qsv", "h264_amf") if res.get(k)), None)
            if best:
                self.encoder.setCurrentIndex(self.encoder.findData(best))
        self.app.run_task(job, on_done=done, title="Kiểm tra GPU")

    def render(self):
        p = self.app.require_project()
        if not p:
            return
        if not p.script or not p.script.get("segments"):
            QMessageBox.warning(self, "Chưa có kịch bản", "Hãy tạo kịch bản ở Bước 2 trước.")
            return
        name = self.fname.text().strip()
        out = None
        if name:
            from recap.pipeline import safe_name

            out = p.settings.output_dir() / (safe_name(name) + ".mp4")
        self.app.run_task(p.run_render, out, on_done=self.finished, title="Xuất video")

    def finished(self, path):
        self.last_output = Path(path)
        try:
            from recap.ffmpeg_utils import media_duration
            dur = media_duration(path)
            dtxt = f" · dài {int(dur // 60)}:{int(dur % 60):02d}"
        except Exception:  # noqa: BLE001
            dtxt = ""
        self.lb_out.setText(f'✅ Đã lưu{dtxt}: <a href="open" style="color:#8ab4ff">{path}</a> (bấm để mở thư mục)')
        if self.app.settings.get("render", "open_folder_after", True):
            reveal(path)
            return
        box = QMessageBox(QMessageBox.Information, "Xong!", f"Đã xuất video{dtxt}:\n{path}", parent=self)
        b_play = box.addButton("▶ Xem video", QMessageBox.AcceptRole)
        b_dir = box.addButton("📂 Mở thư mục", QMessageBox.ActionRole)
        box.addButton("Đóng", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is b_play:
            self.play_last()
        elif box.clickedButton() is b_dir:
            self.open_dir()

    def open_dir(self):
        """Mở thư mục lưu video (chọn sẵn video vừa xuất)."""
        if self.last_output and self.last_output.exists():
            reveal(self.last_output)
        else:
            reveal(self.app.settings.output_dir())

    def show_publish(self):
        if not self.last_output or not self.last_output.exists():
            QMessageBox.information(self, "Chưa có video", "Hãy XUẤT VIDEO trước - thumbnail và tiêu đề được tạo cho "
                                    "video vừa xuất.")
            return
        if extra(self.last_output, ".youtube.txt").exists() and extra(self.last_output, "_thumb.jpg").exists():
            PublishDialog(self, self.last_output).exec()
            return
        p = self.app.require_project()
        if not p:
            return
        self.app.run_task(p.run_publish, self.last_output, on_done=lambda _r: PublishDialog(self, self.last_output).exec(),
                          title="Tạo thumbnail & tiêu đề")

    def on_show(self):
        self.app.binder.reload()
        self.refresh_summary()
        self.refresh_estimate()

    def refresh_estimate(self):
        p = self.app.project
        if not p or not (p.script or {}).get("segments"):
            self.lb_est.setText("Chưa có kịch bản - AI sẽ viết theo thời lượng này ở Bước 2.")
            return
        try:
            est = p.estimate_seconds()
        except Exception:  # noqa: BLE001
            return
        tgt = self.minutes.value() * 60
        diff = est - tgt
        txt = f"Kịch bản hiện tại ≈ {int(est // 60)}:{int(est % 60):02d}"
        if abs(diff) > max(10, 0.1 * tgt):
            txt += (f" ({'dài' if diff > 0 else 'ngắn'} hơn mục tiêu {abs(diff) / 60:.1f} phút"
                    + (" - sẽ được ép bớt khi xuất" if self.fit.isChecked() and diff > 0 else "") + ")")
        else:
            txt += " ✓ khớp mục tiêu"
        self.lb_est.setText(txt)

    def rewrite_script(self):
        sp = self.app.pages[1]
        self.app.goto(1)
        sp.do_script()

    def play_last(self):
        if self.last_output and self.last_output.exists():
            if sys.platform.startswith("win"):
                os.startfile(str(self.last_output))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(self.last_output)])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))

    def clear_cache(self):
        p = self.app.project
        if p:
            editor.clear_render_cache(p.dir)
            self.app.log("Đã xóa các đoạn dựng tạm.")


class PublishDialog(QDialog):
    """Xem & sao chép tiêu đề, mô tả, hashtag, mốc chương + xem trước thumbnail."""

    def __init__(self, page, video: Path):
        super().__init__(page)
        self.page, self.video = page, Path(video)
        self.setWindowTitle("📣 Đăng video: tiêu đề, mô tả & thumbnail")
        self.resize(1100, 720)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.text = QPlainTextEdit()
        f = extra(self.video, ".youtube.txt")
        self.text.setPlainText(f.read_text(encoding="utf-8") if f.exists() else "")
        left.addWidget(self.text, 1)
        left.addWidget(hrow(button("📋 Sao chép tất cả", self.copy_all, "primary"),
                            button("🔄 AI viết lại", lambda: self.regen(thumbs=False, meta=True)),
                            button("🖼 Tạo lại thumbnail", lambda: self.regen(thumbs=True, meta=False)),
                            button("📂 Thư mục file phụ", lambda: reveal(extra(self.video, ".youtube.txt")),
                                   tip="Phụ đề .srt, kịch bản, thumbnail, tiêu đề của video này"), "stretch"))
        lay.addLayout(left, 3)
        self.thumbs = QVBoxLayout()
        right = QWidget()
        right.setLayout(self.thumbs)
        lay.addWidget(scroll(right), 2)
        self.load_thumbs()

    def load_thumbs(self):
        while self.thumbs.count():
            w = self.thumbs.takeAt(0).widget()
            if w:
                w.deleteLater()
        for suf in ("_thumb.jpg", "_thumb_2.jpg", "_thumb_3.jpg", "_thumb_doc.jpg"):
            p = extra(self.video, suf)
            if not p.exists():
                continue
            pm = QPixmap(str(p))
            lb = QLabel()
            lb.setPixmap(pm.scaledToWidth(360 if "doc" not in suf else 200, Qt.SmoothTransformation))
            lb.setToolTip(str(p))
            self.thumbs.addWidget(lb)
            self.thumbs.addWidget(muted(p.name))
        self.thumbs.addStretch(1)

    def copy_all(self):
        QApplication.clipboard().setText(self.text.toPlainText())
        self.page.app.log("Đã sao chép tiêu đề, mô tả, hashtag vào bộ nhớ tạm.")

    def regen(self, thumbs: bool, meta: bool):
        p = self.page.app.require_project()
        if not p:
            return

        def done(_r):
            f = extra(self.video, ".youtube.txt")
            if f.exists():
                self.text.setPlainText(f.read_text(encoding="utf-8"))
            self.load_thumbs()
        self.page.app.run_task(p.run_publish, self.video, thumbs=thumbs, meta=meta, on_done=done,
                               title="Tạo thumbnail & tiêu đề")

