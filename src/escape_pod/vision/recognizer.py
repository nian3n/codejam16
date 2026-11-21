# Owner: Teammate 3 (Vision and retrieval)
"""recognize(clip, allowed) -> ranked guesses (spec §4.1, §6.3).

Restricting the choice matters: picking among a module's 8 words plus yes/no/finish
is much more reliable than among all 250.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from escape_pod.vision.word_model import WordModel


@dataclass
class Guess:
    gloss: str
    score: float  # probability among the allowed set, 0..1


_model: WordModel | None = None


def model() -> WordModel:
    global _model
    if _model is None:
        _model = WordModel()
    return _model


def rank(logits: dict[str, float], allowed: set[str] | None, k: int = 5) -> list[Guess]:
    """Softmax over the allowed glosses only. allowed=None or empty means all of them.

    Allowed glosses the model does not know (digits, letters) are skipped: those go to
    the handshape classifier (spec §6.4), which does not exist yet.
    """
    names = [g for g in logits if not allowed or g in allowed]
    if not names:
        return []
    x = np.array([logits[g] for g in names], np.float64)
    p = np.exp(x - x.max())
    p /= p.sum()
    order = np.argsort(-p)[:k]
    return [Guess(names[i], float(p[i])) for i in order]


def recognize(clip: np.ndarray, allowed: set[str], k: int = 3) -> list[Guess]:
    return rank(model().scores(clip), allowed, k)
