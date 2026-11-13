"""🔲 Khung phụ đề cứng: kéo khung đúng chỗ có chữ trên video gốc -> đọc thử, quét cả video (OCR) thành lời gốc,
và dùng khung này để xóa phụ đề gốc đúng chỗ."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
                               QGraphicsView, QHBoxLayout, QSlider, QVBoxLayout)

from vietdub import ocr
from vietdub.media import frames
from vietdub.transcript import fmt

from .common import Bg, button, fill, label, row

EDGE = 10


class Box(QGraphicsRectItem):
    """Khung kéo được: kéo giữa để di chuyển, kéo cạnh / góc để đổi kích thước."""

    def __init__(self, rect: QRectF, bounds: QRectF, on_change):
        super().__init__(rect)
        self.bounds, self.on_change = bounds, on_change
        self.setPen(QPen(QColor("#FFD23F"), 3))
        self.setBrush(QBrush(QColor(255, 210, 63, 40)))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.SizeAllCursor)
        self._mode = None
        self.touched = False

    def _edges(self, p):
        r = self.rect()
        return (abs(p.x() - r.left()) < EDGE, abs(p.y() - r.top()) < EDGE,
                abs(p.x() - r.right()) < EDGE, abs(p.y() - r.bottom()) < EDGE)

    def hoverMoveEvent(self, e):
        lft, top, rgt, bot = self._edges(e.pos())
        if (lft and top) or (rgt and bot):
            self.setCursor(Qt.SizeFDiagCursor)
        elif (rgt and top) or (lft and bot):
            self.setCursor(Qt.SizeBDiagCursor)
        elif lft or rgt:
            self.setCursor(Qt.SizeHorCursor)
        elif top or bot:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)

    def mousePressEvent(self, e):
        self.touched = True
        self._mode = self._edges(e.pos())
        self._p0, self._r0 = e.pos(), QRectF(self.rect())
        e.accept()

    def mouseMoveEvent(self, e):
        d = e.pos() - self._p0
        r = QRectF(self._r0)
        lft, top, rgt, bot = self._mode or (False,) * 4
        if not any(self._mode or ()):
            r.translate(d)
            b = self.bounds
            r.moveLeft(max(b.left(), min(r.left(), b.right() - r.width())))
            r.moveTop(max(b.top(), min(r.top(), b.bottom() - r.height())))
        else:
            if lft:
                r.setLeft(min(r.right() - 20, r.left() + d.x()))
            if rgt:
                r.setRight(max(r.left() + 20, r.right() + d.x()))
            if top:
                r.setTop(min(r.bottom() - 12, r.top() + d.y()))
            if bot:
                r.setBottom(max(r.top() + 12, r.bottom() + d.y()))
            r = r.intersected(self.bounds)
        self.setRect(r)
        self.on_change()

    def mouseReleaseEvent(self, e):
        self._mode = None
        self.on_change()


class RegionDialog(QDialog):
    def __init__(self, win, project):
        super().__init__(win)
        self.win, self.p = win, project
        self.setWindowTitle("🔲 Khung phụ đề cứng của video gốc")
        self.resize(1100, 780)
        info = project.info
        self.W = 960
        self.H = max(2, int(round(self.W * info.height / max(1, info.width) / 2)) * 2)
        lay = QVBoxLayout(self)
        lay.addWidget(label("Kéo khung vàng trùm đúng dòng phụ đề in sẵn trên video (kéo giữa để di chuyển, kéo cạnh "
                            "để đổi cỡ). Kéo thanh thời gian tới đoạn có chữ để căn cho chuẩn.", "muted"))
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setStyleSheet("background:#000; border-radius:10px;")
        self.pix = QGraphicsPixmapItem()
        self.scene.addItem(self.pix)
        self.scene.setSceneRect(0, 0, self.W, self.H)
        region = project.region or (0.1, 0.82, 0.9, 0.97)
        self.box = Box(self._to_rect(region), QRectF(0, 0, self.W, self.H), self._changed)
        self.scene.addItem(self.box)
        lay.addWidget(self.view, 1)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, max(1, int(info.duration * 10)))
        self.slider.setValue(int(min(info.duration * 0.3, 60) * 10))
        self.lb_t = label("", "muted", wrap=False)
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.setInterval(250)
        self._t.timeout.connect(self.load_frame)
        self.slider.valueChanged.connect(lambda _v: (self.lb_t.setText(fmt(self.slider.value() / 10)),
                                                     self._t.start()))
        lay.addLayout(self._hbox(label("Thời điểm", "muted", wrap=False), self.slider, self.lb_t))

        self.lang = fill(QComboBox(), {k: v[0] for k, v in ocr.LANGS.items()})
        self.lang.setMinimumWidth(330)
        i = self.lang.findData(win.settings.get("speech", "ocr_lang", "auto"))
        self.lang.setCurrentIndex(max(0, i))
        self.lang.currentIndexChanged.connect(lambda _i: win.binder.set("speech", "ocr_lang", self.lang.currentData()))
        self.lb_read = label("", "status")
        self.lb_box = label("", "muted", wrap=False)
        lay.addWidget(row(label("Chữ trên video là", "muted", wrap=False), self.lang,
                          button("🔍 Tự dò khung", self.auto), button("🔤 Đọc thử khung hình này", self.read_now),
                          "stretch", self.lb_box))
        lay.addWidget(self.lb_read)
        lay.addWidget(row(button("↺ Bỏ khung (để app tự dò)", self.clear), "stretch",
                          button("💾 Lưu khung (dùng để xóa phụ đề gốc)", self.save),
                          button("🔤 Quét cả video → lời gốc", self.scan, "primary")))
        self._changed()
        QTimer.singleShot(50, self.load_frame)
        if not project.region:
            QTimer.singleShot(100, self.auto)

    @staticmethod
    def _hbox(*ws):
        h = QHBoxLayout()
        for w in ws:
            h.addWidget(w, 1 if isinstance(w, QSlider) else 0)
        return h

    def _to_rect(self, r) -> QRectF:
        x0, y0, x1, y1 = r
        return QRectF(x0 * self.W, y0 * self.H, (x1 - x0) * self.W, (y1 - y0) * self.H)

    def region(self) -> tuple:
        r = self.box.rect()
        return (round(max(0.0, r.left() / self.W), 4), round(max(0.0, r.top() / self.H), 4),
                round(min(1.0, r.right() / self.W), 4), round(min(1.0, r.bottom() / self.H), 4))

    def _changed(self):
        x0, y0, x1, y1 = self.region()
        self.lb_box.setText(f"Khung: ngang {x0 * 100:.0f}–{x1 * 100:.0f}% · dọc {y0 * 100:.0f}–{y1 * 100:.0f}%")

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, e):
        super().showEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def load_frame(self):
        t = self.slider.value() / 10
        self.lb_t.setText(fmt(t))

        def job():
            fr = frames(self.p.video, t, None, self.W, self.H, pix="rgb24", count=1)
            return fr[0] if fr else None

        def done(img):
            if img is None:
                return
            q = QImage(img.data, self.W, self.H, self.W * 3, QImage.Format_RGB888).copy()
            self.pix.setPixmap(QPixmap.fromImage(q))
        Bg(job, done)

    def auto(self):
        self.lb_read.setText("⏳ Đang tự dò dòng phụ đề...")
        self.box.touched = False

        def done(r):
            if r and self.box.touched:  # người dùng đã tự kéo khung trong lúc dò -> giữ khung của họ
                self.lb_read.setText("Đã dò xong - giữ khung bạn vừa kéo.")
            elif r:
                self.box.setRect(self._to_rect(r))
                self._changed()
                self.lb_read.setText("✅ Đã dò được khung phụ đề - kiểm tra lại rồi bấm Đọc thử.")
            else:
                self.lb_read.setText("Không tự dò được - hãy kéo khung bằng tay vào dòng chữ.")
        Bg(lambda: self.p.auto_region(), done, lambda m: self.lb_read.setText(f"Lỗi tự dò: {m}"))

    def read_now(self):
        t = self.slider.value() / 10
        reg, lang = self.region(), self.lang.currentData()
        self.lb_read.setText("⏳ Đang đọc chữ...")

        def job():
            return ocr.read_image(ocr.grab(self.p.video, self.p.info, reg, t), lang)
        Bg(job, lambda txt: self.lb_read.setText(f"📖 Đọc được: {txt}" if txt else
                                                 "Không thấy chữ trong khung ở thời điểm này - kéo tới đoạn có chữ."),
           lambda m: self.lb_read.setText(f"❌ {m}"))

    def save(self):
        self.p.set_region(self.region())
        self.win.log_msg(f"Đã lưu khung phụ đề cứng: {self.lb_box.text()}")
        self.accept()

    def clear(self):
        self.p.set_region(None)
        self.win.log_msg("Bỏ khung phụ đề cứng - app tự dò.")
        self.accept()

    def scan(self):
        self.p.set_region(self.region())
        self.win.binder.set("speech", "engine", "ocr")
        self.win.binder.set("speech", "ocr_lang", self.lang.currentData())
        self.accept()
        self.win.refresh_mode()
        self.win.do_transcript()
