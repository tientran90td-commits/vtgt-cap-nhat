"""Dò chuyển cảnh bằng PySceneDetect (Breakthrough/PySceneDetect) để cắt clip đẹp hơn."""
from __future__ import annotations

from .ffmpeg_utils import Cancelled


def _seconds(t, fps: float) -> float:
    """FrameTimecode (scenedetect >= 0.7) hoặc số khung hình (bản cũ) -> giây."""
    sec = getattr(t, "seconds", None)  # scenedetect >= 0.7
    if isinstance(sec, (int, float)):
        return float(sec)
    if hasattr(t, "get_seconds"):  # 0.6
        return float(t.get_seconds())
    return float(t) / (fps or 25.0)


def detect_scenes(video: str, log, progress, cancel, threshold: float = 27.0, chunk: float = 60.0) -> list[float]:
    """Trả về danh sách mốc thời gian (giây) bắt đầu mỗi cảnh.

    Quét theo từng đoạn `chunk` giây để báo tiến độ & cho phép Hủy (callback của scenedetect chỉ được gọi
    khi có cảnh mới, và kiểu tham số khác nhau giữa các phiên bản)."""
    try:
        from scenedetect import ContentDetector, SceneManager, open_video
    except ImportError:
        log("Chưa cài scenedetect - bỏ qua bước dò cảnh (pip install scenedetect opencv-python).", level="warn")
        return []
    vid = open_video(video)
    fps = float(vid.frame_rate or 25.0)
    total = _seconds(vid.duration, fps) if vid.duration is not None else 0.0
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold, min_scene_len=12))
    sm.auto_downscale = True

    def cb(_frame_img, _pos):
        if cancel.is_set():
            raise Cancelled()

    t = 0.0
    while True:
        if cancel.is_set():
            raise Cancelled()
        end = t + chunk
        # bỏ 1 khung mỗi 2 khung cho nhanh; mỗi lần gọi quét tiếp từ vị trí hiện tại tới `end`
        n = sm.detect_scenes(vid, end_time=end, frame_skip=1, callback=cb, show_progress=False)
        pos = _seconds(vid.position, fps) if getattr(vid, "position", None) is not None else end
        if total:
            progress(min(1.0, pos / total), f"Dò cảnh {int(pos)}/{int(total)}s")
        if (total and pos >= total - 0.5) or (not total and not n) or pos < t + 0.5:
            break
        t = pos
    cuts = sorted({round(_seconds(sc[0], fps), 3) for sc in sm.get_scene_list()})
    progress(1.0, "Xong dò cảnh")
    log(f"Tìm thấy {len(cuts)} cảnh.")
    return cuts


def snap(t: float, cuts: list[float], window: float = 1.5) -> float:
    """Kéo mốc thời gian về điểm chuyển cảnh gần nhất (nếu đủ gần)."""
    if not cuts:
        return t
    import bisect

    i = bisect.bisect_left(cuts, t)
    best = t
    best_d = window + 1
    for j in (i - 1, i):
        if 0 <= j < len(cuts):
            d = abs(cuts[j] - t)
            if d < best_d:
                best, best_d = cuts[j], d
    return best if best_d <= window else t
