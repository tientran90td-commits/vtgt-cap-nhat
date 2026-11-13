"""Thành phần dùng chung: chạy nền, gắn cài đặt, khung thẻ, nút."""
from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from vietdub.media import Cancelled


class Worker(QThread):
    """Chạy fn(log, progress, cancel, step) ở luồng nền."""
    log = Signal(str, str)
    progress = Signal(float, str)
    step = Signal(str, str, str)
    done = Signal(object)
    failed = Signal(str, str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.cancel = threading.Event()

    def run(self):
        try:
            res = self.fn(*self.args, log=lambda m, level="info": self.log.emit(str(m), level),
                          progress=lambda p, m="": self.progress.emit(float(p), str(m)), cancel=self.cancel,
                          **self.kwargs)
            self.done.emit(res)
        except Cancelled:
            self.failed.emit("Đã hủy.", "")
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e) or e.__class__.__name__, traceback.format_exc())


class Bg(QObject):
    """Việc nhỏ chạy nền không chặn giao diện (kiểm tra trạng thái, kiểm tra bản mới...).
    Dùng luồng daemon nên đóng app lúc đang kiểm tra cũng không bị treo/lỗi."""
    done = Signal(object)
    failed = Signal(str)
    _alive: set = set()

    def __init__(self, fn, on_done=None, on_fail=None):
        super().__init__()
        if on_done:
            self.done.connect(on_done)
        if on_fail:
            self.failed.connect(on_fail)
        self.done.connect(lambda _r: Bg._alive.discard(self))
        self.failed.connect(lambda _m: Bg._alive.discard(self))
        Bg._alive.add(self)

        def run():
            try:
                res = fn()
            except Exception as e:  # noqa: BLE001
                self.failed.emit(str(e) or e.__class__.__name__)
                return
            self.done.emit(res)
        threading.Thread(target=run, daemon=True).start()


class Binder(QObject):
    """Đồng bộ ô nhập <-> cài đặt; tự lưu sau 0.6 giây."""
    changed = Signal(str, str)

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.t = QTimer(self)
        self.t.setSingleShot(True)
        self.t.setInterval(600)
        self.t.timeout.connect(self.s.save)

    def set(self, sec, key, val):
        if sec is None:
            self.s.data[key] = val
        else:
            self.s.set(sec, key, val)
        self.t.start()
        self.changed.emit(sec or "", key)

    def get(self, sec, key, default=None):
        return self.s.data.get(key, default) if sec is None else self.s.get(sec, key, default)

    def combo(self, w: QComboBox, sec, key, cast=str):
        v = self.get(sec, key)
        i = w.findData(v)
        if i < 0:
            i = next((j for j in range(w.count()) if str(w.itemData(j)) == str(v)), -1)
        if i >= 0:
            w.setCurrentIndex(i)
        w.currentIndexChanged.connect(lambda _i: self.set(sec, key, cast(w.currentData())))
        return w

    def check(self, w: QCheckBox, sec, key):
        w.setChecked(bool(self.get(sec, key)))
        w.toggled.connect(lambda v: self.set(sec, key, bool(v)))
        return w

    def spin(self, w, sec, key):
        v = self.get(sec, key, 0)
        w.setValue(float(v) if isinstance(w, QDoubleSpinBox) else int(v))
        w.valueChanged.connect(lambda v: self.set(sec, key, v))
        return w

    def line(self, w: QLineEdit, sec, key):
        w.setText(str(self.get(sec, key, "") or ""))
        w.textChanged.connect(lambda v: self.set(sec, key, v.strip()))
        return w


def fill(w: QComboBox, items) -> QComboBox:
    w.blockSignals(True)
    w.clear()
    for k, v in (items.items() if isinstance(items, dict) else items):
        w.addItem(str(v), k)
    w.blockSignals(False)
    w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    w.setMinimumContentsLength(6)
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return w


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


def label(text, kind=None, wrap=True) -> QLabel:
    lb = QLabel(text)
    if kind:
        lb.setObjectName(kind)
    lb.setWordWrap(wrap)
    return lb


def row(*widgets, stretch=True, spacing=8) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for x in widgets:
        if x == "stretch":
            lay.addStretch(1)
        elif isinstance(x, QWidget):
            lay.addWidget(x)
    if stretch and "stretch" not in widgets:
        lay.addStretch(1)
    return w


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 16)
    lay.setSpacing(10)
    lay.addWidget(label(title, "cardTitle"))
    return f, lay


def spin(lo, hi, step=1.0, suffix="", decimals=None):
    w = QDoubleSpinBox() if decimals is not None else QSpinBox()
    if decimals is not None:
        w.setDecimals(decimals)
    w.setRange(lo, hi)
    w.setSingleStep(step)
    if suffix:
        w.setSuffix(suffix)
    return w


class PathPicker(QWidget):
    changed = Signal(str)

    def __init__(self, mode="file", filt="Tất cả (*.*)", placeholder=""):
        super().__init__()
        self.mode, self.filt = mode, filt
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed.emit)
        b = button("📂", self.browse)
        b.setFixedWidth(42)
        x = button("✕", lambda: self.edit.setText(""))
        x.setFixedWidth(36)
        lay.addWidget(self.edit, 1)
        lay.addWidget(b)
        lay.addWidget(x)

    def browse(self):
        if self.mode == "dir":
            p = QFileDialog.getExistingDirectory(self, "Chọn thư mục", self.edit.text())
        else:
            p, _ = QFileDialog.getOpenFileName(self, "Chọn file", self.edit.text(), self.filt)
        if p:
            self.edit.setText(p)

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, t: str):
        self.edit.setText(t or "")
