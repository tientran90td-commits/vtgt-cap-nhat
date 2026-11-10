"""Dò chuyển cảnh bằng PySceneDetect (Breakthrough/PySceneDetect) để cắt clip đẹp hơn."""
from __future__ import annotations

from .ffmpeg_utils import Cancelled


def detect_scenes(video: str, log, progress, cancel, threshold: float = 27.0) -> list[float]:
    """Trả về danh sách mốc thời gian (giây) bắt đầu mỗi cảnh."""
    try:
        from scenedetect import ContentDetector, SceneManager, open_video
    except ImportError:
        log("Chưa cài scenedetect - bỏ qua bước dò cảnh (pip install scenedetect opencv-python).", level="warn")
        return []
    vid = open_video(video)
    total = vid.duration.get_seconds() if vid.duration else 0
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=threshold, min_scene_len=12))
    sm.auto_downscale = True

    def cb(frame_img, frame_num):
        if cancel.is_set():
            raise Cancelled()
        fps = vid.frame_rate or 25
        if total and frame_num % 250 == 0:
            progress(min(1.0, frame_num / fps / total), f"Dò cảnh {int(frame_num / fps)}/{int(total)}s")

    # bỏ 1 khung mỗi 2 khung cho nhanh
    sm.detect_scenes(vid, frame_skip=1, callback=cb, show_progress=False)
    cuts = [s[0].get_seconds() for s in sm.get_scene_list()]
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
