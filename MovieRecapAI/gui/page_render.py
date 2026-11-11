"""Trang 4: thiết lập dựng & xuất video."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFontComboBox, QFormLayout, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QTabWidget,
                               QVBoxLayout, QWidget)

from recap import editor
from recap.ffmpeg_utils import encoder_works

from .widgets import ColorButton, Page, PathPicker, button, fill_combo, hrow, muted, reveal, scroll, spin

PRESETS = {
    "tiktok": ("📱 TikTok / Reels / Shorts", {"aspect": "9:16", "fill": "face", "height": 1080, "fps": 30,
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
        f2.addRow("", muted("0 = tắt hẳn tiếng phim lúc thuyết minh (khuyên dùng: không lẫn lời thoại nhân vật)"))
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
        gh = QGroupBox("💬 Phụ đề gốc in cứng trong phim (Vietsub...)")
        fh = QFormLayout(gh)
        self.hardsub = b.combo(fill_combo(QComboBox(), editor.HARDSUB_MODES), "render", "hardsub_mode")
        fh.addRow("Cách xử lý", self.hardsub)
        fh.addRow(muted("App tự phát hiện phụ đề in sẵn trong hình (chữ trắng/vàng viền đen ở phía dưới) rồi che đi để "
                        "phụ đề thuyết minh của app không bị đè lên. Phụ đề rời (.srt, phụ đề nhúng trong MKV) luôn được "
                        "loại bỏ khỏi video xuất ra."))
        # Xóa sạch bằng AI qua video-subtitle-remover (công cụ ngoài, Apache-2.0)
        self.vsr_dir = PathPicker("dir", placeholder="Thư mục đã giải nén video-subtitle-remover (VSR)")
        self.vsr_dir.setText(s.get("render", "vsr_dir", ""))
        self.vsr_dir.changed.connect(lambda v: b._set("render", "vsr_dir", v))
        fh.addRow("Thư mục VSR", self.vsr_dir)
        from recap import vsr
        self.vsr_mode = b.combo(fill_combo(QComboBox(), vsr.MODES), "render", "vsr_mode")
        fh.addRow("Thuật toán AI", self.vsr_mode)
        fh.addRow("", hrow(button("🛠 Tự cài VSR (dùng card đồ họa)", self.install_vsr, "primary",
                                  tip="Tải mã nguồn VSR + model AI và cài môi trường riêng (DirectML cho card AMD/Intel, "
                                      "CUDA cho NVIDIA). Khoảng 3-4 GB, chỉ cài 1 lần."),
                           button("🔎 Tự tìm / ✔ Kiểm tra", self.check_vsr),
                           button("⬇ Trang tải", lambda: QDesktopServices.openUrl(QUrl(vsr.RELEASES_URL))), "stretch"))
        fh.addRow(muted("🧠 Chế độ 'Xóa sạch bằng AI': app gọi video-subtitle-remover để xóa chữ và vẽ lại nền, CHỈ cho "
                        "những cảnh được dùng trong video recap (vài phút, không phải cả phim) và lưu lại để lần sau dùng "
                        "ngay. Cách dễ nhất: bấm 🛠 Tự cài VSR (để trống ô thư mục). Đã có VSR thì để trống ô thư mục, app "
                        "tự tìm. Nếu VSR lỗi, app tự chuyển sang làm mờ."))
        l3.addWidget(gh)
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
        # Thời lượng video thành phẩm (dùng chung với 'Độ dài video' ở Bước 2)
        self.minutes = b.spin(spin(0.5, 180, 0.5, " phút", decimals=1), "script", "target_minutes")
        self.minutes.setToolTip("Độ dài mong muốn của video thành phẩm - AI viết kịch bản theo độ dài này")
        quick = [button(f"{m:g}′", lambda _=False, m=m: self.minutes.setValue(m)) for m in (1, 3, 5, 10, 15)]
        for q in quick:
            q.setFixedWidth(46)
        self.fit = b.check(QCheckBox("Ép đúng thời lượng khi xuất"), "render", "fit_duration")
        self.fit.setToolTip("Tự co/giãn đoạn giữ thoại gốc, chỉnh tốc độ đọc (0.88x-1.2x) và bỏ bớt đoạn thoại gốc "
                            "nếu cần để video vừa thời lượng đã chọn")
        f5.addRow("⏱ Thời lượng", hrow(self.minutes, *quick, self.fit, "stretch"))
        self.lb_est = muted("")
        f5.addRow("", hrow(self.lb_est, button("✍️ Viết lại kịch bản theo độ dài này", self.rewrite_script,
                                               tip="AI viết lại kịch bản (Bước 2) cho đúng độ dài mới"), "stretch"))
        self.minutes.valueChanged.connect(lambda _v: self.refresh_estimate())
        self.btn_go = button("🚀  XUẤT VIDEO", self.render, "big")
        self.lb_out = muted("")
        self.lb_out.setTextFormat(Qt.RichText)
        self.lb_out.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.lb_out.linkActivated.connect(lambda _l: self.open_dir())
        self.auto_open = b.check(QCheckBox("Xuất xong tự mở thư mục chứa video"), "render", "open_folder_after")
        f5.addRow(hrow(self.btn_go, button("📂 Mở thư mục", self.open_dir), button("▶ Xem video", self.play_last),
                       button("🧹 Xóa bản dựng tạm", self.clear_cache), "stretch"))
        self.pub_thumbs = b.check(QCheckBox("Tự tạo thumbnail"), "render", "publish_thumbs")
        self.pub_meta = b.check(QCheckBox("AI viết tiêu đề, mô tả, hashtag, mốc chương"), "render", "publish_meta")
        f5.addRow(hrow(self.pub_thumbs, self.pub_meta,
                       button("📣 Xem tiêu đề && thumbnail", self.show_publish,
                              tip="Xem/sao chép tiêu đề, mô tả, hashtag, mốc chương; tạo lại thumbnail"),
                       "stretch", self.auto_open))
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
        try:
            from recap.ffmpeg_utils import media_duration
            dur = media_duration(path)
            dtxt = f" · dài {int(dur // 60)}:{int(dur % 60):02d}"
        except Exception:  # noqa: BLE001
            dtxt = ""
        self.lb_out.setText(f'✅ Đã lưu{dtxt}: <a href="open" style="color:#8ab4ff">{path}</a> '
                            "(bấm để mở thư mục · kèm .srt phụ đề và .txt kịch bản)")
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
        txt = self.last_output.with_suffix(".youtube.txt")
        if txt.exists() and self.last_output.with_name(self.last_output.stem + "_thumb.jpg").exists():
            PublishDialog(self, self.last_output).exec()
            return
        p = self.app.require_project()
        if not p:
            return
        self.app.run_task(p.run_publish, self.last_output, on_done=lambda _r: PublishDialog(self, self.last_output).exec(),
                          title="Tạo thumbnail & tiêu đề")

    def on_show(self):
        v = float(self.app.settings.get("script", "target_minutes", 5) or 5)
        if abs(self.minutes.value() - v) > 1e-6:
            self.minutes.blockSignals(True)
            self.minutes.setValue(v)
            self.minutes.blockSignals(False)
        self.refresh_estimate()

    def refresh_estimate(self):
        p = self.app.project
        if not p or not (p.script or {}).get("segments"):
            self.lb_est.setText("Chưa có kịch bản - AI sẽ viết theo độ dài này ở Bước 2.")
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
        sp.minutes.setValue(self.minutes.value())
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

    def check_vsr(self):
        from recap import vsr
        cur = self.vsr_dir.text().strip()
        try:
            if not cur:
                found, err = vsr.autodetect(self.app.settings)
                if not found:
                    raise vsr.VSRError((err + "\n\n") if err else "Không tìm thấy VSR trên máy.\n\n"
                                       "Bấm 🛠 Tự cài VSR để app tự tải và cài (dùng được card AMD).")
                self.vsr_dir.setText(found)
                cur = found
            QMessageBox.information(self, "VSR sẵn sàng", vsr.check(cur) + "\n\nChọn 'Cách xử lý' = 🧠 Xóa sạch bằng AI.")
            self.hardsub.setCurrentIndex(self.hardsub.findData("vsr"))
        except vsr.VSRError as e:
            QMessageBox.warning(self, "Chưa dùng được VSR", str(e) + "\n\nCách dễ nhất: để trống ô thư mục và bấm "
                                "🛠 Tự cài VSR.")

    def install_vsr(self):
        from recap import vsr
        acc = vsr.accelerator()
        name = {"directml": "DirectML (card AMD/Intel)", "cuda": "CUDA (card NVIDIA)", "cpu": "CPU"}[acc]
        if QMessageBox.question(self, "Tự cài VSR", f"App sẽ tải video-subtitle-remover {vsr.VSR_TAG} (mã nguồn + model "
                                f"AI ~800 MB) và cài thư viện chạy bằng {name}, tổng khoảng 3-4 GB, mất 10-30 phút.\n\n"
                                f"Nơi cài: {vsr.managed_dir(self.app.settings)}\n\nTiếp tục?") != QMessageBox.Yes:
            return

        def done(path):
            self.vsr_dir.setText(path)
            self.hardsub.setCurrentIndex(self.hardsub.findData("vsr"))
            QMessageBox.information(self, "Đã cài VSR", f"Đã cài xong VSR tại:\n{path}\n\nĐã chọn chế độ "
                                    "🧠 Xóa sạch bằng AI.")
        self.app.run_task(vsr.install, self.app.settings, on_done=done, title="Cài VSR")


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
        f = self.video.with_suffix(".youtube.txt")
        self.text.setPlainText(f.read_text(encoding="utf-8") if f.exists() else "")
        left.addWidget(self.text, 1)
        left.addWidget(hrow(button("📋 Sao chép tất cả", self.copy_all, "primary"),
                            button("🔄 AI viết lại", lambda: self.regen(thumbs=False, meta=True)),
                            button("🖼 Tạo lại thumbnail", lambda: self.regen(thumbs=True, meta=False)),
                            button("📂 Mở thư mục", lambda: reveal(self.video)), "stretch"))
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
        stem = self.video.with_suffix("")
        for suf in ("_thumb.jpg", "_thumb_2.jpg", "_thumb_3.jpg", "_thumb_doc.jpg"):
            p = Path(f"{stem}{suf}")
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
            f = self.video.with_suffix(".youtube.txt")
            if f.exists():
                self.text.setPlainText(f.read_text(encoding="utf-8"))
            self.load_thumbs()
        self.page.app.run_task(p.run_publish, self.video, thumbs=thumbs, meta=meta, on_done=done,
                               title="Tạo thumbnail & tiêu đề")

