"""✏️ Chỉnh phụ đề trực tiếp: xem video, phụ đề Việt hiện ngay trên hình, sửa chữ / thời gian / kiểu chữ là thấy liền.

Phím tắt: Space phát/dừng · Ctrl+S lưu · Alt+[ đặt bắt đầu = lúc này · Alt+] đặt kết thúc = lúc này ·
PageUp / PageDown câu trước / sau · Ctrl+Enter phát lại câu đang chọn.
"""
from __future__ import annotations

import bisect

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt, QTimer, QUrl
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QKeySequence, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QGraphicsItem,
                               QGraphicsScene, QGraphicsView, QGridLayout, QHBoxLayout, QHeaderView, QMessageBox,
                               QPlainTextEdit, QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from vietdub import render, translate

from .common import button, card, fill, label, row

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
except ImportError:  # thiếu QtMultimedia
    QMediaPlayer = None


def ts(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


class SubOverlay(QGraphicsItem):
    """Phụ đề vẽ đè lên video: chữ có viền đen, tự xuống dòng, đúng cỡ/màu/vị trí như khi xuất."""

    def __init__(self):
        super().__init__()
        self.text, self.orig = "", ""
        self.size, self.color, self.pos_ = 54, "#FFFFFF", "bottom"
        self.show_orig = False
        self.box = QRectF(0, 0, 960, 540)
        self.setZValue(10)

    def boundingRect(self):
        return self.box

    def set(self, text, orig=""):
        if (text, orig) != (self.text, self.orig):
            self.text, self.orig = text, orig
            self.update()

    def _lines(self, fm, text, max_w):
        words, lines, cur = text.split(), [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if fm.horizontalAdvance(t) <= max_w or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def _draw(self, p, text, px, color, anchor_y, align):
        f = QFont("Arial")
        f.setBold(True)
        f.setPixelSize(max(10, int(px)))
        fm = QFontMetricsF(f)
        W = self.box.width()
        lines = self._lines(fm, text, W * 0.88)
        lh = fm.height() * 1.05
        total = lh * len(lines)
        y = {"bottom": anchor_y - total, "top": anchor_y, "middle": anchor_y - total / 2}[align]
        path = QPainterPath()
        for i, ln in enumerate(lines):
            x = self.box.left() + (W - fm.horizontalAdvance(ln)) / 2
            path.addText(QPointF(x, y + fm.ascent() + i * lh), f, ln)
        p.setPen(QPen(QColor(0, 0, 0, 230), max(2.0, px / 9), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(color)))
        p.drawPath(path)

    def paint(self, p, _opt, _w=None):
        p.setRenderHint(p.RenderHint.Antialiasing)
        H = self.box.height()
        px = self.size * H / 1080
        if self.text:
            pos = self.pos_
            anchor = {"bottom": self.box.bottom() - H * 0.055, "top": self.box.top() + H * 0.055,
                      "middle": self.box.center().y()}[pos]
            self._draw(p, self.text, px, self.color, anchor, pos)
        if self.show_orig and self.orig:
            self._draw(p, self.orig, px * 0.7, "#B9C0D4", self.box.top() + H * 0.04, "top")


class SubEditor(QDialog):
    def __init__(self, win, project):
        super().__init__(win)
        self.win, self.p = win, project
        self.s = win.settings
        self.setWindowTitle("✏️ Chỉnh phụ đề trực tiếp")
        self.resize(1480, 900)
        self.lines = [dict(x) for x in (project.lines or [])]
        self.dirty = False
        self.cur = -1
        self._busy = False
        main = QHBoxLayout(self)

        # ---------------- trái: video + phụ đề đè lên
        left = QVBoxLayout()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setStyleSheet("background:#000; border-radius:10px;")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        info = project.info
        self.VW = 960
        self.VH = max(2, int(round(self.VW * info.height / max(1, info.width))))
        self.scene.setSceneRect(0, 0, self.VW, self.VH)
        self.overlay = SubOverlay()
        self.overlay.box = QRectF(0, 0, self.VW, self.VH)
        self.player = None
        if QMediaPlayer is not None:
            self.vitem = QGraphicsVideoItem()
            self.vitem.setSize(QSizeF(self.VW, self.VH))
            self.scene.addItem(self.vitem)
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.audio.setVolume(0.8)
            self.player.setAudioOutput(self.audio)
            self.player.setVideoOutput(self.vitem)
            self.player.setSource(QUrl.fromLocalFile(project.video))
            self.player.positionChanged.connect(self._tick)
            self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
            self.player.playbackStateChanged.connect(
                lambda st: self.btn_play.setText("⏸" if st == QMediaPlayer.PlayingState else "▶"))
        self.scene.addItem(self.overlay)
        left.addWidget(self.view, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, int(info.duration * 1000))
        self.slider.sliderMoved.connect(lambda v: self.player and self.player.setPosition(v))
        self.lb_time = label("00:00:00.00", "muted", wrap=False)
        left.addWidget(self.slider)
        self.btn_play = button("▶", self.toggle)
        self.btn_play.setFixedWidth(48)
        left.addWidget(row(self.btn_play, button("⏮ Câu trước", lambda: self.go(-1)),
                           button("⏭ Câu sau", lambda: self.go(1)), button("↺ Phát lại câu", self.replay),
                           button("-2s", lambda: self.seek_rel(-2)), button("+2s", lambda: self.seek_rel(2)),
                           "stretch", self.lb_time))

        st, sl = card("🎨 Kiểu chữ (xem trước ngay, áp dụng khi xuất video)")
        self.size = QSpinBox()
        self.size.setRange(20, 120)
        self.size.setSingleStep(2)
        self.size.setValue(int(self.s.get("video", "sub_size", 54)))
        self.color = fill(QComboBox(), {k: v[0] for k, v in render.COLORS.items()})
        self.color.setCurrentIndex(max(0, self.color.findData(self.s.get("video", "sub_color", "white"))))
        self.pos = fill(QComboBox(), render.POSITIONS)
        self.pos.setCurrentIndex(max(0, self.pos.findData(self.s.get("video", "sub_position", "bottom"))))
        self.show_orig = QCheckBox("Hiện lời gốc ở trên (để so)")
        for w in (self.size,):
            w.valueChanged.connect(self._style)
        for w in (self.color, self.pos):
            w.currentIndexChanged.connect(self._style)
        self.show_orig.toggled.connect(self._style)
        sl.addWidget(row(label("Cỡ chữ", "muted", wrap=False), self.size, label("Màu", "muted", wrap=False),
                         self.color, label("Vị trí", "muted", wrap=False), self.pos, self.show_orig))
        left.addWidget(st)
        main.addLayout(left, 3)

        # ---------------- phải: danh sách + sửa câu
        right = QVBoxLayout()
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Bắt đầu", "Kết thúc", "Tiếng Việt"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setWordWrap(True)
        self.table.currentCellChanged.connect(lambda r, *_a: self.select(r, seek=True))
        right.addWidget(self.table, 1)

        ed, el = card("✏️ Câu đang chọn")
        self.lb_orig = label("", "muted")
        self.edit = QPlainTextEdit()
        self.edit.setFixedHeight(80)
        self.edit.textChanged.connect(self._text_changed)
        self.lb_len = label("", "muted", wrap=False)
        self.st = QDoubleSpinBox()
        self.en = QDoubleSpinBox()
        for w in (self.st, self.en):
            w.setDecimals(2)
            w.setRange(0, max(1.0, info.duration))
            w.setSingleStep(0.1)
            w.setSuffix(" s")
            w.valueChanged.connect(self._time_changed)
        g = QGridLayout()
        g.addWidget(label("Lời gốc", "muted"), 0, 0)
        g.addWidget(self.lb_orig, 0, 1)
        g.addWidget(label("Tiếng Việt", "muted"), 1, 0)
        g.addWidget(self.edit, 1, 1)
        g.addWidget(self.lb_len, 2, 1)
        g.addWidget(label("Bắt đầu", "muted"), 3, 0)
        g.addWidget(row(self.st, button("⏱ = lúc này", lambda: self.set_now("start"), tip="Alt+["),
                        button("-0.1", lambda: self.st.setValue(self.st.value() - 0.1)),
                        button("+0.1", lambda: self.st.setValue(self.st.value() + 0.1)), stretch=False), 3, 1)
        g.addWidget(label("Kết thúc", "muted"), 4, 0)
        g.addWidget(row(self.en, button("⏱ = lúc này", lambda: self.set_now("end"), tip="Alt+]"),
                        button("-0.1", lambda: self.en.setValue(self.en.value() - 0.1)),
                        button("+0.1", lambda: self.en.setValue(self.en.value() + 0.1)), stretch=False), 4, 1)
        el.addLayout(g)
        el.addWidget(row(button("✂ Tách tại con trỏ", self.split, tip="Tách câu tại vị trí con trỏ trong ô chữ"),
                         button("🔗 Gộp với câu sau", self.merge), button("➕ Thêm câu lúc này", self.add),
                         button("🗑 Xóa câu", self.delete)))
        self.shift = QDoubleSpinBox()
        self.shift.setRange(-30, 30)
        self.shift.setDecimals(2)
        self.shift.setSingleStep(0.1)
        self.shift.setSuffix(" s")
        el.addWidget(row(label("Dời tất cả phụ đề", "muted", wrap=False), self.shift,
                         button("Áp dụng", self.shift_all), "stretch"))
        right.addWidget(ed)
        self.lb_state = label("", "muted", wrap=False)
        right.addWidget(row(self.lb_state, "stretch", button("💾 Lưu (Ctrl+S)", self.save),
                            button("✅ Lưu & đóng", self.save_close, "primary")))
        main.addLayout(right, 2)

        for key, fn in (("Ctrl+S", self.save), ("Space", self.toggle), ("Alt+[", lambda: self.set_now("start")),
                        ("Alt+]", lambda: self.set_now("end")), ("PgUp", lambda: self.go(-1)),
                        ("PgDown", lambda: self.go(1)), ("Ctrl+Return", self.replay)):
            sc = QShortcut(QKeySequence(key), self)
            sc.activated.connect(fn)
            if key == "Space":
                sc.setContext(Qt.WidgetWithChildrenShortcut)
                self._space = sc
        self.edit.installEventFilter(self)
        self._style()
        self.fill_table()
        if self.lines:
            self.table.selectRow(0)
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(lambda: self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio))

    # ------------------------------------------------ hiển thị
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, e):
        super().showEvent(e)
        self._t.start(50)

    def eventFilter(self, obj, e):  # gõ chữ trong ô sửa: phím Space là dấu cách, không phải phát/dừng
        if obj is self.edit and e.type() in (e.Type.FocusIn, e.Type.FocusOut):
            self._space.setEnabled(e.type() == e.Type.FocusOut)
        return False

    def _style(self, *_a):
        self.overlay.size = self.size.value()
        self.overlay.color = render.COLORS.get(self.color.currentData(), render.COLORS["white"])[2]
        self.overlay.pos_ = self.pos.currentData()
        self.overlay.show_orig = self.show_orig.isChecked()
        self.overlay.update()
        self.s.set("video", "sub_size", self.size.value())
        self.s.set("video", "sub_color", self.color.currentData())
        self.s.set("video", "sub_position", self.pos.currentData())

    def fill_table(self):
        self._busy = True
        self.table.setRowCount(len(self.lines))
        for i, ln in enumerate(self.lines):
            self._row(i)
        self._busy = False

    def _row(self, i):
        ln = self.lines[i]
        for c, v in enumerate((ts(ln["start"]), ts(ln["end"]), ln.get("vi", ""))):
            it = self.table.item(i, c)
            if it is None:
                self.table.setItem(i, c, QTableWidgetItem(v))
            else:
                it.setText(v)
        mx = translate.max_chars(ln, self.lines[i + 1] if i + 1 < len(self.lines) else None)
        long_ = len(ln.get("vi", "")) > mx * 1.35
        self.table.item(i, 2).setForeground(QColor("#FFC857" if long_ else "#E6E8EF"))

    def _mark(self):
        self.dirty = True
        self.lb_state.setText("● Chưa lưu")

    def _starts(self):
        return [x["start"] for x in self.lines]

    def _at(self, t):
        i = bisect.bisect_right(self._starts(), t) - 1
        if 0 <= i < len(self.lines) and self.lines[i]["start"] <= t <= self.lines[i]["end"]:
            return i
        return -1

    def _tick(self, ms):
        t = ms / 1000
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.lb_time.setText(ts(t))
        i = self._at(t)
        if i >= 0:
            self.overlay.set(self.lines[i].get("vi", ""), self.lines[i].get("text", ""))
        else:
            self.overlay.set("", "")

    # ------------------------------------------------ điều khiển
    def toggle(self):
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek(self, t):
        if self.player:
            self.player.setPosition(int(max(0.0, t) * 1000))
        self._tick(int(max(0.0, t) * 1000))

    def seek_rel(self, d):
        if self.player:
            self.seek(self.player.position() / 1000 + d)

    def go(self, d):
        if self.lines:
            self.table.selectRow(max(0, min(len(self.lines) - 1, self.cur + d)))

    def replay(self):
        if 0 <= self.cur < len(self.lines):
            self.seek(self.lines[self.cur]["start"])
            if self.player:
                self.player.play()

    def select(self, r, seek=False):
        if self._busy or r < 0 or r >= len(self.lines):
            return
        self.cur = r
        ln = self.lines[r]
        self._busy = True
        self.lb_orig.setText(ln.get("text", ""))
        self.edit.setPlainText(ln.get("vi", ""))
        self.st.setValue(ln["start"])
        self.en.setValue(ln["end"])
        self._busy = False
        self._len_label()
        if seek:
            self.seek(ln["start"] + 0.01)

    def _len_label(self):
        if not (0 <= self.cur < len(self.lines)):
            return
        ln = self.lines[self.cur]
        mx = translate.max_chars(ln, self.lines[self.cur + 1] if self.cur + 1 < len(self.lines) else None)
        n = len(ln.get("vi", ""))
        self.lb_len.setText(f"{n}/{mx} ký tự" + (" · ⚠️ dài, giọng sẽ phải đọc nhanh" if n > mx * 1.35 else ""))

    def _text_changed(self):
        if self._busy or not (0 <= self.cur < len(self.lines)):
            return
        self.lines[self.cur]["vi"] = " ".join(self.edit.toPlainText().split())
        self._row(self.cur)
        self._len_label()
        self._mark()
        if self.player:
            self._tick(self.player.position())

    def _time_changed(self):
        if self._busy or not (0 <= self.cur < len(self.lines)):
            return
        st, en = round(self.st.value(), 2), round(self.en.value(), 2)
        if en <= st:
            en = round(st + 0.3, 2)
        self.lines[self.cur]["start"], self.lines[self.cur]["end"] = st, en
        self._row(self.cur)
        self._mark()

    def set_now(self, which):
        if not self.player or not (0 <= self.cur < len(self.lines)):
            return
        t = round(self.player.position() / 1000, 2)
        (self.st if which == "start" else self.en).setValue(t)

    def split(self):
        if not (0 <= self.cur < len(self.lines)):
            return
        ln = self.lines[self.cur]
        text = ln.get("vi", "")
        pos = self.edit.textCursor().position()
        a, b = text[:pos].strip(), text[pos:].strip()
        if not a or not b:
            QMessageBox.information(self, "Tách câu", "Đặt con trỏ vào giữa câu (chỗ muốn tách) rồi bấm Tách.")
            return
        mid = round(ln["start"] + (ln["end"] - ln["start"]) * len(a) / max(1, len(a) + len(b)), 2)
        self.lines[self.cur] = {**ln, "vi": a, "end": mid}
        self.lines.insert(self.cur + 1, {**ln, "vi": b, "start": mid, "text": ""})
        self._refresh(self.cur)

    def merge(self):
        i = self.cur
        if not (0 <= i < len(self.lines) - 1):
            return
        a, b = self.lines[i], self.lines[i + 1]
        self.lines[i] = {**a, "end": b["end"], "vi": f"{a.get('vi', '')} {b.get('vi', '')}".strip(),
                         "text": f"{a.get('text', '')} {b.get('text', '')}".strip()}
        del self.lines[i + 1]
        self._refresh(i)

    def add(self):
        t = round(self.player.position() / 1000, 2) if self.player else 0.0
        new = {"start": t, "end": round(t + 2.0, 2), "text": "", "vi": ""}
        i = bisect.bisect_right(self._starts(), t)
        self.lines.insert(i, new)
        self._refresh(i)
        self.edit.setFocus()

    def delete(self):
        if 0 <= self.cur < len(self.lines):
            del self.lines[self.cur]
            self._refresh(min(self.cur, len(self.lines) - 1))

    def shift_all(self):
        d = self.shift.value()
        if not d:
            return
        for ln in self.lines:
            ln["start"] = round(max(0.0, ln["start"] + d), 2)
            ln["end"] = round(max(ln["start"] + 0.3, ln["end"] + d), 2)
        self.shift.setValue(0)
        self._refresh(self.cur)

    def _refresh(self, select):
        self.lines.sort(key=lambda x: x["start"])
        self.fill_table()
        self._mark()
        if 0 <= select < len(self.lines):
            self.table.selectRow(select)
            self.select(select)

    # ------------------------------------------------ lưu
    def save(self):
        self.p.save_lines(self.lines)
        self.s.save()
        self.dirty = False
        self.lb_state.setText("✅ Đã lưu")
        self.win.load_table()

    def save_close(self):
        self.save()
        self.accept()

    def reject(self):
        if self.dirty:
            r = QMessageBox.question(self, "Chưa lưu", "Lưu các chỗ đã sửa trước khi đóng?",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Yes:
                self.save()
        if self.player:
            self.player.stop()
        super().reject()

    def accept(self):
        if self.player:
            self.player.stop()
        super().accept()
