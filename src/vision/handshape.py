# Owner: Teammate 3 (Vision and retrieval)
"""Digits 0-9 from one hand's shape (spec §6.4).

The word model has no numbers, and the ASL digits are still hand shapes, so a
small nearest-neighbour model on hand landmarks does the job:

- features: the signing hand's 21 points, moved to the wrist and scaled by the
  hand's size (wrist -> middle-finger knuckle), averaged over the steadiest 5
  frames of the clip. 63 numbers. A left hand is mirrored to look like a right
  hand, so left-handed players match right-handed samples.
- model: k nearest neighbours with distance weights. Training is a copy of the
  samples, so adding a player's recordings and retraining takes seconds.

Saved to models/handshape.npz by `uv run train-digits`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import config
from vision.landmarks import LEFT, RIGHT

DIGITS = tuple("0123456789")
WRIST, MIDDLE_MCP = 0, 9
STEADY_FRAMES = 5
N_FEATURES = 63


def pick_hand(left: np.ndarray, right: np.ndarray) -> tuple[np.ndarray, bool]:
    """The hand that is visible in more frames (ties: the right hand). Returns (hand, is_left)."""
    seen_l = int(np.isfinite(left).all(axis=(1, 2)).sum())
    seen_r = int(np.isfinite(right).all(axis=(1, 2)).sum())
    return (left, True) if seen_l > seen_r else (right, False)


def normalize(hand: np.ndarray, is_left: bool, scale_xyz: bool = False) -> np.ndarray:
    """(T, 21, 3) -> (T, 21, 3): wrist at the origin, hand size 1, left hands mirrored.

    The hand size uses x, y only (MediaPipe's z is noisy), unless scale_xyz: the
    ready-made digit model (digit_mlp.py) was trained with the 3-D length.
    """
    out = hand - hand[:, WRIST:WRIST + 1, :]
    size = np.linalg.norm(out[:, MIDDLE_MCP, :3 if scale_xyz else 2], axis=1)
    out = out / np.where(size > 1e-6, size, np.nan)[:, None, None]
    if is_left:
        out[..., 0] *= -1
    return out


def features_from_hands(left: np.ndarray, right: np.ndarray, scale_xyz: bool = False) -> np.ndarray | None:
    """left, right: (T, 21, 3) with NaN where the hand was not found. None if no usable frame."""
    hand, is_left = pick_hand(left, right)
    norm = normalize(hand.astype(np.float64), is_left, scale_xyz)
    ok = np.isfinite(norm).all(axis=(1, 2))
    frames = norm[ok]
    if len(frames) == 0:
        return None
    if len(frames) > STEADY_FRAMES:
        # The steadiest stretch: the window of consecutive frames that moves least.
        motion = np.linalg.norm(np.diff(frames, axis=0), axis=(1, 2))
        win = STEADY_FRAMES - 1
        costs = np.convolve(motion, np.ones(win), "valid")
        start = int(np.argmin(costs))
        frames = frames[start:start + STEADY_FRAMES]
    return frames.mean(axis=0).reshape(-1).astype(np.float32)


def features(clip: np.ndarray) -> np.ndarray | None:
    """clip: (T, 543, 3) Holistic landmarks -> (63,) or None."""
    return features_from_hands(clip[:, LEFT, :], clip[:, RIGHT, :])


class HandshapeModel:
    def __init__(self, X: np.ndarray, y: np.ndarray, k: int = 7):
        self.X = np.asarray(X, np.float32)
        self.y = np.asarray(y).astype(str)
        self.k = k
        self.classes = tuple(sorted(set(self.y.tolist())))

    @classmethod
    def load(cls, path: Path | None = None) -> "HandshapeModel":
        path = path or config.HANDSHAPE_FILE
        if not path.exists():
            raise FileNotFoundError(f"No digit model at {path}. Record samples (uv run record-digits), "
                                    "then run: uv run train-digits")
        d = np.load(path)
        return cls(d["X"], d["y"], int(d["k"]))

    def save(self, path: Path | None = None) -> Path:
        path = path or config.HANDSHAPE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, X=self.X, y=self.y, k=self.k)
        return path

    def proba(self, feat: np.ndarray) -> dict[str, float]:
        """Probability per class: distance-weighted votes of the k nearest samples, lightly smoothed."""
        d = np.linalg.norm(self.X - feat[None, :], axis=1)
        k = min(self.k, len(d))
        idx = np.argpartition(d, k - 1)[:k]
        w = 1.0 / (d[idx] + 1e-3)
        votes = {c: 0.0 for c in self.classes}
        for i, wi in zip(idx, w):
            votes[self.y[i]] += float(wi)
        total = sum(votes.values())
        eps = 0.01  # no class is ever exactly impossible: keeps log() finite and the ranking honest
        n = len(votes)
        return {c: (v / total) * (1 - eps) + eps / n for c, v in votes.items()}

    def predict(self, feat: np.ndarray) -> str:
        p = self.proba(feat)
        return max(p, key=lambda c: p[c])

    def scores(self, clip: np.ndarray) -> dict[str, float] | None:
        """Log-probabilities per digit for a (T, 543, 3) clip, or None when no hand was seen."""
        f = features(clip)
        if f is None:
            return None
        return {c: float(np.log(p)) for c, p in self.proba(f).items()}
