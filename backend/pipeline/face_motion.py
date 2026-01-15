from __future__ import annotations

from pathlib import Path
import numpy as np
import cv2


def compute_facecam_motion_per_second(
    video_path: Path,
    *,
    w_ratio: float,
    h_ratio: float,
    sample_fps: int = 3,
    smooth_sec: int = 5,
) -> np.ndarray:
    """
    Returns an array motion[t] ~ average frame-diff energy for second t,
    computed only from the bottom-right crop region.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open video: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps <= 0:
        src_fps = 30.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    total_secs = int(np.ceil(total_frames / src_fps)) if total_frames > 0 else 0
    if total_secs <= 0:
        # fallback: attempt duration from timestamps while reading
        total_secs = 0

    # sample every N frames
    step = max(1, int(round(src_fps / float(sample_fps))))

    motion = np.zeros(max(1, total_secs), dtype=np.float32)

    prev_gray = None
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_idx % step != 0:
            frame_idx += 1
            continue

        h, w = frame.shape[:2]
        cw = max(1, int(w * float(w_ratio)))
        ch = max(1, int(h * float(h_ratio)))
        x = w - cw
        y = h - ch

        crop = frame[y:y + ch, x:x + cw]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # timestamp in seconds for this frame
        t_sec = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        t = int(t_sec)

        # expand if total_secs unknown/too small
        if t >= len(motion):
            motion = np.pad(motion, (0, t - len(motion) + 1), mode="constant")

        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            # mean absolute difference in [0,255]
            motion[t] += float(np.mean(diff))

        prev_gray = gray
        frame_idx += 1

    cap.release()

    # Smooth (moving average in seconds)
    k = int(max(1, smooth_sec))
    if len(motion) >= k and k > 1:
        kernel = np.ones(k, dtype=np.float32) / float(k)
        motion = np.convolve(motion, kernel, mode="same")

    return motion
