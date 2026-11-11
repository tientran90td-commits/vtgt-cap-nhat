"""Thanh 📋 Quá trình làm việc: hiện từng bước app đang làm (chờ / đang làm + thời gian / xong / bỏ qua / lỗi)."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from recap.pipeline import STEP_TAG, STEPS

SHORT = {"identify": "Nhận diện phim", "transcribe": "Nhận dạng thoại", "scenes": "Chuyển cảnh",
         "overlays": "Lọc quảng cáo", "visual": "AI xem cảnh", "script": "AI viết kịch bản",
         "voice": "Lồng tiếng", "render": "Dựng video", "publish": "Thumbnail"}
ICONS = {"pending": "⬜", "start": "⏳", "done": "✅", "skip": "⏭", "fail": "❌"}


def _fmt(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


class StepTracker(QFrame):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName("steps")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)
        head = QHBoxLayout()
        self.lb_title = QLabel("📋 Quá trình làm việc")
        self.lb_title.setObjectName("stepsTitle")
        self.lb_total = QLabel("")
        self.lb_total.setObjectName("muted")
        self.detail = QCheckBox("Hiện chi tiết (mọi thao tác, lệnh ffmpeg...)")
        self.detail.setChecked(bool(app.settings.get("ui", "debug", False)))
        self.detail.toggled.connect(lambda v: (app.settings.set("ui", "debug", bool(v)), app.settings.save()))
        head.addWidget(self.lb_title)
        head.addWidget(self.lb_total)
        head.addStretch(1)
        head.addWidget(self.detail)
        lay.addLayout(head)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.chips: dict[str, QLabel] = {}
        for k, sid in enumerate(STEPS):
            lb = QLabel()
            lb.setObjectName("stepChip")
            lb.setAlignment(Qt.AlignCenter)
            lb.setMinimumWidth(96)
            lb.setToolTip(STEPS[sid])
            grid.addWidget(lb, 0, k)
            grid.setColumnStretch(k, 1)
            self.chips[sid] = lb
        lay.addLayout(grid)
        self.state: dict[str, dict] = {}
        self.t0 = None
        self.running = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.setVisible(False)

    # ------------------------------------------------ trạng thái
    def reset(self, planned: bool):
        self.state = {sid: {"st": "pending", "t0": None, "t1": None, "note": ""} for sid in STEPS}
        for sid, lb in self.chips.items():
            lb.setVisible(planned)
            self._paint(sid)
        self.t0 = time.time()
        self.running = True
        self.timer.start()
        self.setVisible(True)

    def event_msg(self, msg: str) -> str | None:
        """Nhận tin báo bước; trả về câu để ghi nhật ký (hoặc None)."""
        try:
            sid, st, note = msg[len(STEP_TAG):].split("§", 2)
        except ValueError:
            return None
        if sid == "plan":
            self.reset(planned=True)
            return None
        if sid not in self.chips:
            return None
        if not self.running:
            self.reset(planned=False)
        s = self.state[sid]
        now = time.time()
        if st == "start":
            s.update(st="start", t0=now, t1=None, note=note)
        else:
            s.update(st=st, t1=now, note=note)
            if s["t0"] is None:
                s["t0"] = now
        self.chips[sid].setVisible(True)
        self._paint(sid)
        name = STEPS[sid]
        if st == "start":
            return f"▶ {name}..."
        if st == "done":
            return f"✅ {name} - xong ({_fmt(s['t1'] - s['t0'])})" + (f" · {note}" if note else "")
        if st == "skip":
            return f"⏭ {name} - bỏ qua" + (f" ({note})" if note else "")
        return f"❌ {name}" + (f": {note}" if note else "")

    def fail_running(self, msg: str):
        cancelled = msg == "Đã hủy."
        for sid, s in self.state.items():
            if s["st"] == "start":
                s.update(st="skip" if cancelled else "fail", t1=time.time(), note="đã hủy" if cancelled else "lỗi")
                self._paint(sid)
        self._stop("⏹ Đã hủy" if cancelled else "❌ Dừng vì lỗi")

    def finish(self):
        if not self.running:
            return
        for sid, s in self.state.items():
            if s["st"] == "pending":
                s["st"] = "skip"
                self._paint(sid)
        self._stop("✅ Hoàn tất")

    def _stop(self, label: str):
        self.running = False
        self.timer.stop()
        if self.t0:
            self.lb_total.setText(f"· {label} · tổng {_fmt(time.time() - self.t0)}")

    def _tick(self):
        if self.t0:
            self.lb_total.setText(f"· đang chạy {_fmt(time.time() - self.t0)}")
        for sid, s in self.state.items():
            if s["st"] == "start":
                self._paint(sid)

    def _paint(self, sid: str):
        s = self.state.get(sid, {"st": "pending"})
        st = s["st"]
        sub = {"pending": "chờ", "skip": "bỏ qua", "fail": "lỗi"}.get(st, "")
        if st == "start" and s.get("t0"):
            sub = f"đang làm {_fmt(time.time() - s['t0'])}"
        elif st == "done" and s.get("t0") and s.get("t1"):
            sub = f"xong {_fmt(s['t1'] - s['t0'])}"
        lb = self.chips[sid]
        lb.setText(f"{ICONS[st]} {SHORT[sid]}\n{sub}")
        tip = STEPS[sid] + (f"\n{s.get('note')}" if s.get("note") else "")
        lb.setToolTip(tip)
        lb.setProperty("state", st)
        lb.style().unpolish(lb)
        lb.style().polish(lb)
