"""Trình phát video/âm thanh xem trước (QtMultimedia)."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .widgets import button

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget

    HAS_MM = True
except Exception:  # pragma: no cover
    HAS_MM = False


def _fmt(ms: int) -> str:
    s = max(0, ms // 1000)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class VideoPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._stop_at = None
        if not HAS_MM:
            lay.addWidget(QLabel("(Không có QtMultimedia - không xem trước được)"))
            self.player = None
            return
        self.video = QVideoWidget()
        self.video.setMinimumHeight(220)
        self.video.setStyleSheet("background:black; border-radius:10px;")
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.btn = button("▶", self.toggle)
        self.btn.setFixedWidth(44)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v))
        self.time = QLabel("00:00:00 / 00:00:00")
        self.time.setObjectName("muted")
        ctr = QHBoxLayout()
        ctr.addWidget(self.btn)
        ctr.addWidget(self.slider, 1)
        ctr.addWidget(self.time)
        lay.addWidget(self.video, 1)
        lay.addLayout(ctr)
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, d))
        self.player.positionChanged.connect(self._pos)
        self.player.playbackStateChanged.connect(
            lambda st: self.btn.setText("⏸" if st == QMediaPlayer.PlayingState else "▶"))

    def _pos(self, p):
        if not self.slider.isSliderDown():
            self.slider.setValue(p)
        self.time.setText(f"{_fmt(p)} / {_fmt(self.player.duration())}")
        if self._stop_at is not None and p >= self._stop_at:
            self._stop_at = None
            self.player.pause()

    def open(self, path: str):
        if self.player:
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.pause()

    def toggle(self):
        if not self.player:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def play_range(self, start: float, end: float | None = None):
        if not self.player:
            return
        self._stop_at = int(end * 1000) if end else None
        self.player.setPosition(int(start * 1000))
        self.player.play()

    def stop(self):
        if self.player:
            self.player.stop()


class AudioPlayer:
    """Phát file giọng đọc.

    Windows: dùng winsound (có sẵn, phát WAV PCM rất ổn định) -> nếu lỗi dùng QtMultimedia
    -> nếu vẫn lỗi mở bằng trình phát mặc định của máy. Lỗi được báo qua on_error.
    """

    def __init__(self, parent=None, on_error=None, on_info=None):
        self.on_error = on_error or (lambda m: None)
        self.on_info = on_info or (lambda m: None)
        self.player = None
        self._parent = parent
        if HAS_MM:
            self.player = QMediaPlayer(parent)
            self.audio = QAudioOutput(parent)
            self.audio.setVolume(1.0)
            self.player.setAudioOutput(self.audio)
            self.player.errorOccurred.connect(self._qt_error)
        self._last = None

    def _qt_error(self, *_a):
        msg = self.player.errorString() if self.player else "?"
        self.on_error(f"Trình phát Qt lỗi: {msg} - mở bằng trình phát mặc định của máy.")
        if self._last:
            open_external(self._last)

    def play(self, path: str):
        import os
        import sys

        path = str(path)
        self._last = path
        if not os.path.exists(path) or os.path.getsize(path) < 1000:
            self.on_error(f"File âm thanh rỗng hoặc không tồn tại: {path}")
            return
        if sys.platform.startswith("win") and path.lower().endswith(".wav"):
            try:
                import winsound

                winsound.PlaySound(None, 0)
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                self.on_info(f"🔊 Đang phát: {os.path.basename(path)}")
                return
            except Exception as e:  # noqa: BLE001
                self.on_error(f"winsound lỗi ({e}) - thử trình phát khác.")
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
            QTimer.singleShot(50, lambda: (self.player.setSource(QUrl.fromLocalFile(path)), self.player.play()))
            self.on_info(f"🔊 Đang phát: {os.path.basename(path)}")
        else:
            open_external(path)

    def stop(self):
        import sys

        if sys.platform.startswith("win"):
            try:
                import winsound

                winsound.PlaySound(None, 0)
            except Exception:
                pass
        if self.player:
            self.player.stop()


def open_external(path: str):
    """Mở file bằng ứng dụng mặc định của hệ điều hành."""
    import os
    import subprocess
    import sys

    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass
