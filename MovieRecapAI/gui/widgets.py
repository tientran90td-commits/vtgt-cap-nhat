"""Widget dùng chung + hàm gắn widget với cấu hình (tự lưu)."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSlider, QSpinBox,
                               QVBoxLayout, QWidget)

from recap.ffmpeg_utils import Cancelled


# ------------------------------------------------------------------ Luồng nền
class Worker(QThread):
    log = Signal(str, str)
    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str, str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        import threading

        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.cancel = threading.Event()

    def _log(self, msg, level="info"):
        self.log.emit(str(msg), level)

    def _progress(self, p, msg=""):
        # gửi tối đa ~12 lần/giây để giao diện không bị "nghẽn" khi tác vụ báo tiến độ dày đặc
        import time

        now = time.monotonic()
        msg = str(msg)
        if p < 0.999 and msg == getattr(self, "_last_msg", None) and now - getattr(self, "_last_t", 0) < 0.08:
            return
        self._last_t, self._last_msg = now, msg
        self.progress.emit(float(p), msg)

    def run(self):
        try:
            res = self.fn(*self.args, log=self._log, progress=self._progress, cancel=self.cancel, **self.kwargs)
            self.done.emit(res)
        except Cancelled:
            self.failed.emit("Đã hủy.", "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e) or e.__class__.__name__, traceback.format_exc())


# ------------------------------------------------------------------ Gắn cấu hình
class Binder(QObject):
    """Đồng bộ widget <-> Settings, lưu file sau 600ms khi có thay đổi."""

    changed = Signal(str, str)

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.setInterval(600)
        self._t.timeout.connect(self.s.save)

    def _set(self, sec, key, val):
        self.s.set(sec, key, val)
        self._t.start()
        self.changed.emit(sec, key)

    def line(self, w: QLineEdit, sec, key):
        w.setText(str(self.s.get(sec, key, "") or ""))
        w.textChanged.connect(lambda v: self._set(sec, key, v))
        return w

    def text(self, w, sec, key):
        w.setPlainText(str(self.s.get(sec, key, "") or ""))
        w.textChanged.connect(lambda: self._set(sec, key, w.toPlainText()))
        return w

    def check(self, w: QCheckBox, sec, key):
        w.setChecked(bool(self.s.get(sec, key, False)))
        w.toggled.connect(lambda v: self._set(sec, key, bool(v)))
        return w

    def spin(self, w, sec, key):
        val = self.s.get(sec, key, 0)
        w.setValue(float(val) if isinstance(w, QDoubleSpinBox) else int(val))
        w.valueChanged.connect(lambda v: self._set(sec, key, v))
        return w

    def slider(self, w: QSlider, sec, key):
        w.setValue(int(self.s.get(sec, key, 0) or 0))
        w.valueChanged.connect(lambda v: self._set(sec, key, int(v)))
        return w

    def combo(self, w: QComboBox, sec, key, cast=str):
        """Combo dùng userData làm giá trị."""
        val = self.s.get(sec, key)
        i = w.findData(val)
        if i < 0 and val is not None:
            for j in range(w.count()):
                if str(w.itemData(j)) == str(val):
                    i = j
                    break
        if i >= 0:
            w.setCurrentIndex(i)
        w.currentIndexChanged.connect(lambda _i: self._set(sec, key, cast(w.currentData())))
        return w

    def edit_combo(self, w: QComboBox, sec, key):
        """Combo cho phép gõ (vd. tên model)."""
        w.setEditable(True)
        w.setCurrentText(str(self.s.get(sec, key, "") or ""))
        w.currentTextChanged.connect(lambda v: self._set(sec, key, v.strip()))
        return w


def fill_combo(w: QComboBox, items: dict | list):
    w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    w.setMinimumContentsLength(12)
    w.blockSignals(True)
    w.clear()
    if isinstance(items, dict):
        for k, v in items.items():
            w.addItem(str(v), k)
    else:
        for v in items:
            w.addItem(str(v), v)
    w.blockSignals(False)
    return w


# ------------------------------------------------------------------ Widget nhỏ
def hrow(*widgets, stretch_last=False, spacing=8) -> QWidget:
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for w in widgets:
        if w == "stretch":
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
    if stretch_last and widgets and isinstance(widgets[-1], QWidget):
        lay.setStretchFactor(widgets[-1], 1)
    return box


def button(text, slot=None, kind=None, tip=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if tip:
        b.setToolTip(tip)
    if slot:
        b.clicked.connect(slot)
    b.setCursor(Qt.PointingHandCursor)
    return b


def muted(text) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("muted")
    lb.setWordWrap(True)
    return lb


class PathPicker(QWidget):
    changed = Signal(str)

    def __init__(self, mode="file", filt="Tất cả (*.*)", placeholder="", parent=None):
        super().__init__(parent)
        self.mode, self.filt = mode, filt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed.emit)
        b = button("📂", self.browse, tip="Chọn")
        b.setFixedWidth(40)
        c = button("✕", lambda: self.edit.setText(""), tip="Xóa")
        c.setFixedWidth(34)
        lay.addWidget(self.edit, 1)
        lay.addWidget(b)
        lay.addWidget(c)

    def browse(self):
        cur = self.edit.text()
        if self.mode == "dir":
            p = QFileDialog.getExistingDirectory(self, "Chọn thư mục", cur)
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Chọn file", cur, self.filt)
        if p:
            self.edit.setText(p)

    def text(self):
        return self.edit.text().strip()

    def setText(self, t):
        self.edit.setText(t)


class ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self, color="#FFFFFF"):
        super().__init__()
        self.setFixedWidth(64)
        self.set_color(color)
        self.clicked.connect(self.pick)

    def set_color(self, c):
        self.color = c
        self.setStyleSheet(f"background:{c}; border:1px solid #555; border-radius:6px; min-height:22px;")

    def pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Chọn màu")
        if c.isValid():
            self.set_color(c.name().upper())
            self.changed.emit(self.color)


class LabeledSlider(QWidget):
    valueChanged = Signal(int)

    def __init__(self, lo, hi, fmt="{:+d}", step=1):
        super().__init__()
        self.fmt = fmt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.s = QSlider(Qt.Horizontal)
        self.s.setRange(lo, hi)
        self.s.setSingleStep(step)
        self.lb = QLabel()
        self.lb.setFixedWidth(64)
        self.lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.s, 1)
        lay.addWidget(self.lb)
        self.s.valueChanged.connect(self._ch)
        self._ch(self.s.value())

    def _ch(self, v):
        self.lb.setText(self.fmt.format(v))
        self.valueChanged.emit(v)

    def value(self):
        return self.s.value()

    def setValue(self, v):
        self.s.setValue(int(v))
        self._ch(self.s.value())


def bind_labeled_slider(binder: Binder, w: LabeledSlider, sec, key):
    w.setValue(int(binder.s.get(sec, key, 0) or 0))
    w.valueChanged.connect(lambda v: binder._set(sec, key, int(v)))
    return w


def scroll(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(widget)
    return sa


class Page(QWidget):
    """Trang có tiêu đề + mô tả."""

    def __init__(self, app, title, hint=""):
        super().__init__()
        self.app = app
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 18, 24, 12)
        self.root.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("pageTitle")
        self.root.addWidget(t)
        if hint:
            h = QLabel(hint)
            h.setObjectName("pageHint")
            h.setWordWrap(True)
            self.root.addWidget(h)

    def on_show(self):
        pass


def spin(lo, hi, step=1, suffix="", decimals=None):
    if decimals is not None:
        w = QDoubleSpinBox()
        w.setDecimals(decimals)
    else:
        w = QSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    if suffix:
        w.setSuffix(suffix)
    return w
