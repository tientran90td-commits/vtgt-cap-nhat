"""Trang 4: thiết lập dựng & xuất video."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QTabWidget, QCheckBox, QComboBox, QFontComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QLineEdit, QMessageBox, QVBoxLayout, QWidget)

from recap import editor
from recap.ffmpeg_utils import encoder_works

from .widgets import ColorButton, Page, PathPicker, button, fill_combo, hrow, muted, scroll, spin

PRESETS = {
    "tiktok": ("📱 TikTok / Reels / Shorts", {"aspect": "9:16", "fill": "blur", "height": 1080, "fps": 30,
                                             "sub_position": "middle", "sub_size": 60}),
    "youtube": ("▶️ YouTube ngang", {"aspect": "16:9", "fill": "blur", "height": 1080, "fps": 30,
                                     "sub_position": "bottom", "sub_size": 52}),
    "facebook": ("📘 Facebook vuông", {"aspect": "1:1", "fill": "blur", "height": 1080, "fps": 30,
                                       "sub_position": "bottom", "sub_size": 56}),
}


class RenderPage(Page):
    def __init__(self, app):
        super().__init__(app, "🎞️  Bước 4 · Dựng & xuất video",
                         "Chọn khung hình, phụ đề, nhạc nền, logo rồi bấm XUẤT VIDEO. Giọng đọc được tạo tự động, "
                         "các đoạn đã dựng được lưu lại nên sửa 1 đoạn rồi xuất lại sẽ rất nhanh.")
        b = app.binder
        s = app.settings

        pre = QGroupBox("⚡ Mẫu nhanh")
        pl = hrow(*[button(v[0], lambda _=False, k=k: self.apply_preset(k)) for k, v in PRESETS.items()], "stretch")
        QVBoxLayout(pre).addWidget(pl)
        tabs = QTabWidget()
        t1, t2, t3 = QWidget(), QWidget(), QWidget()
        l1, l2, l3 = QGridLayout(t1), QGridLayout(t2), QVBoxLayout(t3)
        l1.addWidget(pre, 0, 0, 1, 2)

        g1 = QGroupBox("🖼️ Khung hình")
        f1 = QFormLayout(g1)
        self.aspect = b.combo(fill_combo(QComboBox(), editor.ASPECTS), "render", "aspect")
        self.fill = b.combo(fill_combo(QComboBox(), editor.FILLS), "render", "fill")
        self.height_ = b.combo(fill_combo(QComboBox(), {720: "720p (HD)", 1080: "1080p (Full HD)",
                                                         1440: "1440p (2K)", 2160: "2160p (4K)"}),
                               "render", "height", int)
        self.fps = b.combo(fill_combo(QComboBox(), {"source": "Giống phim gốc", 24: "24 fps", 25: "25 fps",
                                                     30: "30 fps", 60: "60 fps"}),
                           "render", "fps", int)
        self.encoder = b.combo(fill_combo(QComboBox(), editor.ENCODERS), "render", "encoder")
        self.quality = b.spin(spin(14, 32, 1), "render", "quality")
        self.quality.setToolTip("Số càng nhỏ chất lượng càng cao, file càng nặng (18-23 là đẹp)")
        f1.addRow("Tỉ lệ", self.aspect)
        f1.addRow("Lấp khung", self.fill)
        f1.addRow("Độ phân giải", self.height_)
        f1.addRow("Khung hình/giây", self.fps)
        f1.addRow("Bộ mã hóa", hrow(self.encoder, button("🔍 Kiểm tra GPU", self.check_gpu)))
        f1.addRow("Chất lượng (CRF)", self.quality)
        l1.addWidget(g1, 1, 0)

        g2 = QGroupBox("🔊 Âm thanh")
        f2 = QFormLayout(g2)
        self.vv = b.spin(spin(0, 3, 0.05, decimals=2), "render", "voice_volume")
        self.ov = b.spin(spin(0, 1, 0.02, decimals=2), "render", "orig_volume_voice")
        self.oc = b.spin(spin(0, 2, 0.05, decimals=2), "render", "orig_volume_clip")
        self.music = PathPicker("file", "Âm thanh (*.mp3 *.wav *.m4a *.aac *.ogg *.flac)", "(tùy chọn) Nhạc nền")
        self.music.setText(s.get("render", "music", ""))
        self.music.changed.connect(lambda v: b._set("render", "music", v))
        self.mv = b.spin(spin(0, 1, 0.01, decimals=2), "render", "music_volume")
        self.fit = b.combo(fill_combo(QComboBox(), editor.FITS), "render", "fit")
        self.gap = b.spin(spin(0, 2, 0.05, " giây", decimals=2), "render", "gap")
        f2.addRow("Giọng thuyết minh", self.vv)
        f2.addRow("Tiếng phim khi có thuyết minh", self.ov)
        f2.addRow("Tiếng phim ở đoạn thoại gốc", self.oc)
        f2.addRow("Nhạc nền", self.music)
        f2.addRow("Âm lượng nhạc", self.mv)
        f2.addRow("Khớp cảnh", self.fit)
        f2.addRow("Nghỉ giữa các đoạn", self.gap)
        l2.addWidget(g2, 0, 0)

        g3 = QGroupBox("💬 Phụ đề")
        f3 = QFormLayout(g3)
        self.subs = b.check(QCheckBox("Chèn phụ đề vào video (kèm file .srt riêng)"), "render", "subtitles")
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(s.get("render", "sub_font", "Arial")))
        self.font.currentFontChanged.connect(lambda f: b._set("render", "sub_font", f.family()))
        self.size = b.spin(spin(16, 140, 2), "render", "sub_size")
        self.color = ColorButton(s.get("render", "sub_color", "#FFFFFF"))
        self.color.changed.connect(lambda c: b._set("render", "sub_color", c))
        self.ocolor = ColorButton(s.get("render", "sub_outline_color", "#000000"))
        self.ocolor.changed.connect(lambda c: b._set("render", "sub_outline_color", c))
        self.outline = b.spin(spin(0, 10, 0.5, decimals=1), "render", "sub_outline")
        self.pos = b.combo(fill_combo(QComboBox(), {"bottom": "Dưới", "middle": "Giữa", "top": "Trên"}),
                           "render", "sub_position")
        self.bold = b.check(QCheckBox("Chữ đậm"), "render", "sub_bold")
        self.maxc = b.spin(spin(16, 80, 1, " ký tự/dòng"), "render", "sub_max_chars")
        self.orig = b.check(QCheckBox("Hiện phụ đề thoại gốc ở các đoạn giữ thoại"), "render", "sub_original")
        f3.addRow(self.subs)
        f3.addRow("Phông chữ", self.font)
        f3.addRow("Cỡ chữ (1080p)", hrow(self.size, self.bold, "stretch"))
        f3.addRow("Màu chữ / viền", hrow(self.color, self.ocolor, self.outline, "stretch"))
        f3.addRow("Vị trí", hrow(self.pos, self.maxc, "stretch"))
        f3.addRow(self.orig)
        l1.addWidget(g3, 1, 1)

        g4 = QGroupBox("🏷️ Tiêu đề && logo")
        f4 = QFormLayout(g4)
        self.title = b.line(QLineEdit(), "render", "title_text")
        self.title.setPlaceholderText("Chữ hiện ở đầu video (để trống = không có)")
        self.tsec = b.spin(spin(1, 15, 0.5, " giây", decimals=1), "render", "title_seconds")
        self.logo = PathPicker("file", "Ảnh (*.png *.jpg *.jpeg *.webp)", "(tùy chọn) Logo/watermark PNG")
        self.logo.setText(s.get("render", "logo", ""))
        self.logo.changed.connect(lambda v: b._set("render", "logo", v))
        self.lpos = b.combo(fill_combo(QComboBox(), {"top-right": "Trên phải", "top-left": "Trên trái",
                                                      "bottom-right": "Dưới phải", "bottom-left": "Dưới trái"}),
                            "render", "logo_position")
        self.lscale = b.spin(spin(0.03, 0.5, 0.01, decimals=2), "render", "logo_scale")
        f4.addRow("Tiêu đề mở đầu", hrow(self.title, button("Lấy từ kịch bản", self.title_from_script),
                                        stretch_last=False))
        f4.addRow("Hiện trong", self.tsec)
        f4.addRow("Logo", self.logo)
        f4.addRow("Vị trí / kích thước", hrow(self.lpos, self.lscale, "stretch"))
        l2.addWidget(g4, 0, 1)
        gfx = QGroupBox("✨ Hiệu ứng && âm lượng")
        ffx = QFormLayout(gfx)
        self.trans = b.combo(fill_combo(QComboBox(), {"fade": "Mờ dần nhẹ giữa các đoạn (mượt)", "cut": "Cắt thẳng"}),
                             "render", "transition")
        ffx.addRow("Chuyển cảnh", self.trans)
        ffx.addRow(b.check(QCheckBox("Cân bằng âm lượng tổng (-16 LUFS, to đều như YouTube)"), "render", "loudnorm"))
        l2.addWidget(gfx, 1, 0, 1, 2)
        l2.setRowStretch(2, 1)
        l2.setColumnStretch(0, 1)
        l2.setColumnStretch(1, 1)

        gs = QGroupBox("🎯 Chọn cảnh thông minh")
        fs = QVBoxLayout(gs)
        for key, text, tip in (
                ("sentence_sync", "Khớp hình theo TỪNG CÂU thuyết minh (mỗi câu chiếu đúng khoảnh khắc nó kể)",
                 "AI gán mốc phim cho từng câu; app chia giọng đọc theo khoảng lặng giữa các câu"),
                ("no_reuse", "Không lặp lại cảnh đã chiếu (tự lấy cảnh mới gần đó)", ""),
                ("avoid_overlays", "Tránh đoạn có quảng cáo / chữ chèn cứng của web phim", "Tự dò lớp chèn đứng yên"),
                ("delogo", "Che mờ logo / watermark cố định của nguồn (tự phát hiện)", ""),
                ("final_qa", "Kiểm tra video sau khi xuất: màn hình đen, đứng hình, âm lượng", "")):
            cb = b.check(QCheckBox(text), "render", key)
            cb.setToolTip(tip)
            fs.addWidget(cb)
        fs.addWidget(muted("Đoạn cần bỏ qua (intro, OP/ED, cảnh nhạy cảm...) nhập ở Bước 1 → ô 'Bỏ qua đoạn'. "
                           "Sau khi xuất, kết quả kiểm tra nằm cạnh video (file .qa.json) và trong nhật ký."))
        l3.addWidget(gs)
        l3.addStretch(1)
        tabs.addTab(scroll(t1), "🖼️ Khung hình && phụ đề")
        tabs.addTab(scroll(t2), "🔊 Âm thanh, logo && hiệu ứng")
        tabs.addTab(scroll(t3), "🎯 Chọn cảnh thông minh")

        g5 = QGroupBox("📦 Xuất file")
        f5 = QFormLayout(g5)
        self.outdir = PathPicker("dir", placeholder=str(s.output_dir()))
        self.outdir.setText(s.get("paths", "output", ""))
        self.outdir.changed.connect(lambda v: b._set("paths", "output", v))
        self.fname = QLineEdit()
        self.fname.setPlaceholderText("Tên file (để trống = theo tiêu đề kịch bản)")
        f5.addRow("Thư mục lưu", self.outdir)
        f5.addRow("Tên file", self.fname)
        self.btn_go = button("🚀  XUẤT VIDEO", self.render, "big")
        self.lb_out = muted("")
        f5.addRow(hrow(self.btn_go, button("📂 Mở thư mục", self.open_dir), button("▶ Xem video", self.play_last),
                       button("🧹 Xóa bản dựng tạm", self.clear_cache), "stretch"))
        f5.addRow(self.lb_out)
        l1.setColumnStretch(0, 1)
        l1.setColumnStretch(1, 1)
        l1.setRowStretch(2, 1)
        self.root.addWidget(tabs, 1)
        self.root.addWidget(g5)
        self.last_output: Path | None = None

    def apply_preset(self, key):
        vals = PRESETS[key][1]
        for k, v in vals.items():
            self.app.settings.set("render", k, v)
        self.app.settings.save()
        for w, k in ((self.aspect, "aspect"), (self.fill, "fill"), (self.height_, "height"), (self.fps, "fps"),
                     (self.pos, "sub_position")):
            i = w.findData(vals[k])
            if i >= 0:
                w.setCurrentIndex(i)
        self.size.setValue(vals["sub_size"])
        self.app.log(f"Đã áp dụng mẫu {PRESETS[key][0]}")

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
        self.lb_out.setText(f"✅ Đã lưu: {path}  (kèm .srt phụ đề và .txt kịch bản)")
        r = QMessageBox.question(self, "Xong!", f"Đã xuất video:\n{path}\n\nMở video ngay?")
        if r == QMessageBox.Yes:
            self.play_last()

    def open_dir(self):
        d = self.last_output.parent if self.last_output else self.app.settings.output_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

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

