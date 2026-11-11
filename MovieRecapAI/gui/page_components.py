"""Trang 🧩 Thành phần & sửa lỗi: kiểm tra, tự tải/cài thư viện, FFmpeg, model AI; chẩn đoán lỗi giọng đọc."""
from __future__ import annotations

import os
import platform
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFormLayout, QGroupBox, QHeaderView, QMessageBox, QTableWidget, QTableWidgetItem

from recap import components, tts
from recap.ffmpeg_utils import run_ffmpeg

from .player import AudioPlayer
from .widgets import Page, PathPicker, button, hrow, muted

ORDER = ["ffmpeg", "edge_tts", "vieneu", "faster_whisper", "whisper_model", "vieneu_model", "scenedetect", "yt_dlp",
         "anthropic", "num2words", "gtts", "piper", "piper_vi", "pyttsx3", "xtts"]


class ComponentsPage(Page):
    def __init__(self, app):
        super().__init__(app, "🧩  Thành phần & sửa lỗi",
                         "App tự kiểm tra những gì còn thiếu và tải/cài giúp bạn. Bấm 'Cài tất cả còn thiếu' "
                         "cho lần đầu. Nếu không nghe được giọng đọc, bấm '🩺 Chẩn đoán giọng đọc'.")
        self.lb_sys = muted(self._sysinfo())
        self.root.addWidget(self.lb_sys)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Thành phần", "Trạng thái", "Ghi chú", ""])
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.root.addWidget(self.table, 1)
        # Công cụ AI cài thêm (tùy chọn) - gom về một chỗ
        from recap import vsr
        s = app.settings
        gt = QGroupBox("🧠 Công cụ AI cài thêm (tùy chọn)")
        ft = QFormLayout(gt)
        self.vsr_dir = PathPicker("dir", placeholder="(để trống = app tự tìm / tự cài) thư mục video-subtitle-remover")
        self.vsr_dir.setText(s.get("render", "vsr_dir", ""))
        self.vsr_dir.changed.connect(lambda v: s.set("render", "vsr_dir", v))
        ft.addRow("🧽 Xóa phụ đề AI (VSR)", hrow(self.vsr_dir,
                  button("🛠 Tự cài (dùng card đồ họa)", self.install_vsr, "primary",
                         tip="Tải VSR + model AI, cài môi trường riêng (DirectML cho card AMD/Intel, CUDA cho NVIDIA). "
                             "Khoảng 3-4 GB, chỉ cài 1 lần."),
                  button("🔎 Tìm / kiểm tra", self.check_vsr),
                  button("⬇ Trang tải", lambda: QDesktopServices.openUrl(QUrl(vsr.RELEASES_URL))), stretch_last=False))
        self.wcpp_dir = PathPicker("dir", placeholder="(để trống = app tự tải) thư mục chứa whisper-cli.exe")
        self.wcpp_dir.setText(s.get("transcribe", "wcpp_dir", ""))
        self.wcpp_dir.changed.connect(lambda v: s.set("transcribe", "wcpp_dir", v))
        ft.addRow("⚡ Whisper card đồ họa", hrow(self.wcpp_dir,
                  button("⬇ Tải ngay (chương trình + model)", self.install_wcpp, "primary"), stretch_last=False))
        ft.addRow(muted("VSR: dùng ở Bước 4 → Hình ảnh → Phụ đề in cứng = 🧠 Xóa sạch bằng AI. "
                        "Whisper card đồ họa: dùng ở Bước 2 → Lời thoại → Công cụ = ⚡ Whisper bằng card đồ họa."))
        self.root.addWidget(gt)
        self.root.addWidget(hrow(
            button("⬇ Cài tất cả còn thiếu (khuyên dùng)", self.install_missing, "big"),
            button("🔄 Kiểm tra lại", self.refresh),
            "stretch",
            button("🩺 Chẩn đoán giọng đọc", self.diagnose_voice, "primary"),
            button("🔔 Thử loa", self.test_speaker),
            button("📂 Mở file log", self.open_logs)))
        self.audio = AudioPlayer(self, on_error=lambda m: app.log(m, "warn"), on_info=app.log)
        self._statuses: dict[str, bool] = {}

    @staticmethod
    def _sysinfo() -> str:
        cuda = "có" if _safe_cuda() else "không (card AMD/Intel → Whisper & VieNeu chạy bằng CPU, vẫn ổn)"
        return (f"Máy: {platform.system()} {platform.release()} · CPU {os.cpu_count()} luồng · "
                f"GPU NVIDIA CUDA: {cuda} · Python {platform.python_version()}")

    def on_show(self):
        self.refresh()

    def refresh(self):
        s = self.app.settings

        def job(log, progress, cancel):
            res = {}
            for k in ORDER:
                try:
                    res[k] = components.status(k, s)
                except Exception as e:  # noqa: BLE001
                    res[k] = (False, str(e))
            return res
        self.app.run_task(job, on_done=self._fill, title="Kiểm tra thành phần", quiet=True)

    def _fill(self, res):
        self._statuses = {k: v[0] for k, v in res.items()}
        self.table.setRowCount(0)
        for k in ORDER:
            ok, note = res[k]
            c = components.COMPONENTS[k]
            r = self.table.rowCount()
            self.table.insertRow(r)
            tag = " (bắt buộc)" if c.get("required") else (" (nên có)" if c.get("recommended") else "")
            self.table.setItem(r, 0, QTableWidgetItem(c["name"] + tag))
            st = QTableWidgetItem("✅ Sẵn sàng" if ok else "⬜ Chưa có")
            st.setForeground(Qt.green if ok else Qt.yellow)
            self.table.setItem(r, 1, st)
            self.table.setItem(r, 2, QTableWidgetItem(note))
            label = ("⟳ Cập nhật" if ok and c["kind"] == "pip" else "✓" if ok else
                     ("⬇ Tải" if c["kind"] in ("model", "ffmpeg") else "⬇ Cài"))
            b = button(label, lambda _=False, k=k: self.install([k]))
            b.setEnabled(not ok or c["kind"] == "pip")
            self.table.setCellWidget(r, 3, b)
        self.table.resizeRowsToContents()

    def install(self, keys: list[str], then=None):
        s = self.app.settings
        heavy = [k for k in keys if k == "xtts"]
        if heavy and QMessageBox.question(self, "Cài XTTS", "Coqui XTTS nặng khoảng 2GB và cần GPU NVIDIA để chạy "
                                          "nhanh. Máy dùng card AMD sẽ rất chậm. Vẫn cài?") != QMessageBox.Yes:
            return

        def job(log, progress, cancel):
            for k in keys:
                c = components.COMPONENTS[k]
                if components.status(k, s)[0] and c["kind"] == "pip":  # đã có -> cập nhật
                    components.pip_install(c["pip"], log, progress, cancel, upgrade=True)
                    continue
            todo = [k for k in keys if not components.status(k, s)[0]]
            return components.install_many(todo, s, log, progress, cancel)

        def done(errors):
            self.refresh()
            if errors:
                QMessageBox.warning(self, "Một số thành phần chưa cài được", "\n\n".join(errors)[:3000])
            elif then:
                then()
        self.app.run_task(job, on_done=done, title="Cài thành phần")

    def install_missing(self):
        s = self.app.settings
        want = [k for k in ORDER if components.COMPONENTS[k].get("required") or components.COMPONENTS[k].get("recommended")]
        eng = s.get("voice", "engine")
        want += components.ENGINE_NEEDS.get(eng, [])
        if eng == "piper":
            want.append("piper_vi")
        if s.get("transcribe", "engine") != "faster_whisper":
            want = [k for k in want if k != "whisper_model"]
        want = list(dict.fromkeys(want))

        def job(log, progress, cancel):
            todo = [k for k in want if not components.status(k, s)[0]]
            if not todo:
                log("✅ Đã đủ mọi thành phần cần thiết.")
                return []
            log("Sẽ cài: " + ", ".join(components.COMPONENTS[k]["name"] for k in todo))
            return components.install_many(todo, s, log, progress, cancel)

        def done(errors):
            self.refresh()
            if errors:
                QMessageBox.warning(self, "Chưa cài được hết", "\n\n".join(errors)[:3000])
            else:
                QMessageBox.information(self, "Xong", "Đã có đủ thành phần. Nếu vừa cài thư viện mới mà app báo "
                                                      "chưa có, hãy đóng app và mở lại.")
        self.app.run_task(job, on_done=done, title="Cài thành phần còn thiếu")

    # ------------------------------------------------------------ chẩn đoán
    def test_speaker(self):
        """Phát tiếng bíp 1 giây: nghe được = loa & trình phát OK."""
        out = Path(tempfile.gettempdir()) / "recap_beep.wav"

        def job(log, progress, cancel):
            run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=660:duration=1", "-ac", "2", "-ar", "48000",
                        "-c:a", "pcm_s16le", str(out)])
            return str(out)

        def done(p):
            self.audio.play(p)
            QMessageBox.information(self, "Thử loa", "Bạn có nghe tiếng 'bíp' không?\n\n"
                                    "• Có: loa & trình phát ổn, lỗi (nếu có) nằm ở bước tạo giọng → bấm Chẩn đoán.\n"
                                    "• Không: kiểm tra âm lượng Windows / tai nghe / thiết bị phát mặc định.")
        self.app.run_task(job, on_done=done, title="Thử loa")

    def diagnose_voice(self):
        s = self.app.settings
        eng = s.get("voice", "engine", "edge")
        voice = s.get("voice", "voice", "")
        text = "Xin chào, đây là giọng đọc thử nghiệm năm 2025."

        def job(log, progress, cancel):
            report = []
            ok, note = components.ffmpeg_status()
            report.append(("FFmpeg", ok, note))
            missing = components.missing_for(s, eng)
            missing = [m for m in missing if m != "ffmpeg"]
            report.append((f"Thư viện cho {tts.ENGINES[eng]['name']}", not missing,
                           "đủ" if not missing else "thiếu: " + ", ".join(missing)))
            if missing:
                log("Tự cài thư viện còn thiếu...")
                errs = components.install_many(missing, s, log, progress, cancel)
                report.append(("Tự cài thư viện", not errs, "; ".join(errs) or "đã cài"))
            if not voice:
                report.append(("Giọng đã chọn", False, "chưa chọn giọng ở mục 🎙️ Giọng đọc"))
                return report, None
            out = Path(tempfile.gettempdir()) / "recap_diagnose.wav"
            out.unlink(missing_ok=True)
            opts = dict(s.section("voice"), lang_code=tts.LANG_CODES.get(s.get("script", "language"), "vi"))
            try:
                tts.synthesize(eng, text, voice, out, opts, s, cancel)
                from recap.ffmpeg_utils import media_duration

                d = media_duration(out)
                report.append(("Tạo giọng đọc", d > 0.3, f"{d:.1f} giây âm thanh"))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                report.append(("Tạo giọng đọc", False, msg[:300]))
                if eng == "edge":
                    log("Edge TTS lỗi - thử cập nhật edge-tts lên bản mới nhất...")
                    try:
                        components.pip_install(["edge-tts"], log, progress, cancel, upgrade=True)
                        report.append(("Cập nhật edge-tts", True, "đã cập nhật - hãy khởi động lại app rồi thử lại"))
                    except Exception as e2:  # noqa: BLE001
                        report.append(("Cập nhật edge-tts", False, str(e2)[:200]))
                return report, None
            return report, str(out)

        def done(res):
            report, path = res
            lines = [("✅ " if ok else "❌ ") + f"{name}: {note}" for name, ok, note in report]
            if path:
                self.audio.play(path)
                lines.append("\n🔊 Đang phát câu thử. Nếu vẫn không nghe thấy: bấm 'Thử loa'.")
            QMessageBox.information(self, "Chẩn đoán giọng đọc", "\n".join(lines))
            self.refresh()
        self.app.run_task(job, on_done=done, title="Chẩn đoán giọng đọc")

    def open_logs(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(components.logs_dir())))

    # ------------------------------------------------ công cụ AI cài thêm
    def check_vsr(self):
        from recap import vsr
        cur = self.vsr_dir.text().strip()
        try:
            if not cur:
                found, err = vsr.autodetect(self.app.settings)
                if not found:
                    raise vsr.VSRError(err or "Không tìm thấy VSR trên máy.")
                self.vsr_dir.setText(found)
                cur = found
            QMessageBox.information(self, "VSR sẵn sàng", vsr.check(cur) + "\n\nỞ Bước 4 → Hình ảnh, chọn Phụ đề in "
                                    "cứng = 🧠 Xóa sạch bằng AI.")
        except vsr.VSRError as e:
            QMessageBox.warning(self, "Chưa dùng được VSR", str(e) + "\n\nCách dễ nhất: để trống ô thư mục và bấm "
                                "🛠 Tự cài.")

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
            self.app.settings.set("render", "hardsub_mode", "vsr")
            QMessageBox.information(self, "Đã cài VSR", f"Đã cài xong VSR tại:\n{path}\n\nĐã bật chế độ "
                                    "🧠 Xóa sạch bằng AI (Bước 4 → Hình ảnh).")
        self.app.run_task(vsr.install, self.app.settings, on_done=done, title="Cài VSR")

    def install_wcpp(self):
        from recap import whisper_gpu
        s = self.app.settings
        model = s.get("transcribe", "model", "auto")
        model = model if model and model != "auto" else "large-v3-turbo"

        def job(log, progress, cancel):
            exe = whisper_gpu.ensure_exe(s, log, progress, cancel)
            m = whisper_gpu.ensure_model(s, model, log, progress, cancel)
            return f"{exe}\n{m}"

        def done(res):
            s.set("transcribe", "engine", "whisper_gpu")
            QMessageBox.information(self, "Whisper card đồ họa sẵn sàng", f"Đã có:\n{res}\n\nĐã chọn công cụ nhận dạng "
                                    "thoại = ⚡ Whisper bằng card đồ họa (Bước 2).")
        self.app.run_task(job, on_done=done, title="Tải whisper.cpp")

def _safe_cuda() -> bool:
    try:
        from recap.transcribe import has_cuda

        return has_cuda()
    except Exception:
        return False
