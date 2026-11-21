# Owner: Teammate 3 (Vision and retrieval)
"""MediaPipe Holistic -> (543, 3) float32 arrays, NaN for missing parts (spec §6.3).

Row order is the Kaggle competition order: face 0-467, left hand 468-488,
pose 489-521, right hand 522-542.
"""
from __future__ import annotations

import numpy as np

FACE, LEFT, POSE, RIGHT = slice(0, 468), slice(468, 489), slice(489, 522), slice(522, 543)
N_POINTS = 543


def to_array(results) -> np.ndarray:
    def block(lms, n):
        if lms is None:
            return np.full((n, 3), np.nan, np.float32)
        return np.array([[p.x, p.y, p.z] for p in lms.landmark], np.float32)

    return np.concatenate([
        block(results.face_landmarks, 468),
        block(results.left_hand_landmarks, 21),
        block(results.pose_landmarks, 33),
        block(results.right_hand_landmarks, 21),
    ])


def left_handed(frame: np.ndarray) -> np.ndarray:
    """Mirror x and swap the hand blocks, so a left-handed signer looks right-handed.

    Spec §6.3 check 4. Pose and face rows keep their indices; only x is mirrored.
    """
    out = frame.copy()
    out[..., 0] = 1.0 - out[..., 0]
    left = out[..., LEFT, :].copy()
    out[..., LEFT, :] = out[..., RIGHT, :]
    out[..., RIGHT, :] = left
    return out


class Extractor:
    """Wraps mediapipe Holistic. Imports mediapipe lazily so tests run without it."""

    def __init__(self):
        import mediapipe as mp

        self._mp = mp
        # refine_face_landmarks=False -> 468 face points, as the model expects (not 478).
        self.holistic = mp.solutions.holistic.Holistic(
            refine_face_landmarks=False, model_complexity=1,
            min_detection_confidence=0.5, min_tracking_confidence=0.5)

    def process(self, rgb: np.ndarray):
        """rgb: HxWx3 uint8. Returns (landmarks (543, 3), raw mediapipe results)."""
        results = self.holistic.process(rgb)
        return to_array(results), results

    def draw(self, bgr: np.ndarray, results) -> None:
        """Draw hands and upper-body pose on the frame, so players see what the model sees."""
        du = self._mp.solutions.drawing_utils
        h = self._mp.solutions.holistic
        du.draw_landmarks(bgr, results.pose_landmarks, h.POSE_CONNECTIONS,
                          du.DrawingSpec((80, 80, 80), 1, 1), du.DrawingSpec((120, 120, 120), 1, 1))
        for hand, col in ((results.left_hand_landmarks, (60, 200, 255)), (results.right_hand_landmarks, (120, 255, 120))):
            du.draw_landmarks(bgr, hand, h.HAND_CONNECTIONS, du.DrawingSpec(col, 2, 2), du.DrawingSpec(col, 2, 1))

    def close(self):
        self.holistic.close()
