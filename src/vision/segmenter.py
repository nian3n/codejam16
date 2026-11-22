# Owner: Teammate 3 (Vision and retrieval)
"""Decide when one sign starts and ends, from landmarks alone (spec §6.2 auto mode).

A sign starts when a hand is visible, above the waist and moving. It ends when the
hands drop (or vanish) or stay still for SEG_STILL_S. Clips outside
[SEG_MIN_S, SEG_MAX_S] are dropped. The still tail is trimmed off the clip.
"""
from __future__ import annotations

from collections import deque

import numpy as np

import config
from vision.landmarks import LEFT, POSE, RIGHT

HIP_ROWS = (POSE.start + 23, POSE.start + 24)
NO_HIPS_WAIST_Y = 0.95   # hips are often off-screen at a desk: then "above the waist" = on screen
PRE_ROLL = 3             # frames kept from before the start, so the first motion is in the clip
DROP_FRAMES = 3          # frames in a row without a raised hand that end the sign


def hand_points(frame: np.ndarray) -> np.ndarray:
    """(n, 3) points of the visible hands, maybe empty."""
    pts = np.concatenate([frame[LEFT], frame[RIGHT]])
    return pts[~np.isnan(pts[:, 0])]


def waist_y(frame: np.ndarray) -> float:
    hips = frame[list(HIP_ROWS), 1]
    hips = hips[~np.isnan(hips)]
    return float(hips.mean()) if len(hips) else NO_HIPS_WAIST_Y


class Segmenter:
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        self.frames: list[np.ndarray] = []
        self.pre: deque[np.ndarray] = deque(maxlen=PRE_ROLL)
        self.signing = False
        self.still = 0          # frames in a row without motion
        self.down = 0           # frames in a row without a raised hand
        self.last_active = 0    # len(self.frames) at the last moving frame
        self.prev_center: np.ndarray | None = None
        self.state = "idle"     # for the debug overlay: idle | signing

    def _moving(self, frame: np.ndarray) -> tuple[bool, bool]:
        """(hands up, moving) for one frame."""
        pts = hand_points(frame)
        if not len(pts):
            self.prev_center = None
            return False, False
        up = float(pts[:, 1].mean()) < waist_y(frame)
        center = pts[:, :2].mean(axis=0)
        moving = self.prev_center is not None and float(np.abs(center - self.prev_center).sum()) > config.SEG_MOVE
        self.prev_center = center
        return up, moving

    def push(self, frame_landmarks: np.ndarray) -> np.ndarray | None:
        """Feed one (543, 3) frame. Returns a finished clip (T, 543, 3), or None."""
        up, moving = self._moving(frame_landmarks)
        if not self.signing:
            self.pre.append(frame_landmarks)
            if up and moving:
                self.signing, self.state = True, "signing"
                self.frames = list(self.pre)
                self.still, self.last_active = 0, len(self.frames)
            return None
        self.frames.append(frame_landmarks)
        if up and moving:
            self.still, self.last_active = 0, len(self.frames)
        else:
            self.still += 1
        # MediaPipe loses a hand for a frame now and then; only a few frames in a row
        # without a raised hand count as "the hands dropped".
        self.down = 0 if up else self.down + 1
        dropped = self.down >= DROP_FRAMES
        still_long = self.still >= config.SEG_STILL_S * self.fps
        too_long = len(self.frames) > config.SEG_MAX_S * self.fps
        if not (dropped or still_long or too_long):
            return None
        clip = np.stack(self.frames[: self.last_active])
        self.reset()
        if too_long or len(clip) < config.SEG_MIN_S * self.fps:
            return None
        return clip

    def reset(self):
        self.frames, self.signing, self.state, self.still, self.down = [], False, "idle", 0, 0
        self.pre.clear()
