# Owner: Teammate 3 (Vision and retrieval)
"""recognize(clip, allowed) -> ranked guesses (spec §4.1, §6.3).

Restricting the choice matters: picking among a module's 8 words plus yes/no/finish
is much more reliable than among all 250.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from escape_pod.vision.handshape import DIGITS, HandshapeModel
from escape_pod.vision.word_model import WordModel


@dataclass
class Guess:
    gloss: str
    score: float  # probability among the allowed set, 0..1


_model: WordModel | None = None
_hand: HandshapeModel | None = None


def model() -> WordModel:
    global _model
    if _model is None:
        _model = WordModel()
    return _model


def rank(logits: dict[str, float], allowed: set[str] | None, k: int = 5) -> list[Guess]:
    """Softmax over the allowed glosses only. allowed=None or empty means all of them.

    Allowed glosses the model does not know (the digits) are skipped: rank_mixed()
    sends those to the handshape model (spec §6.4).
    """
    names = [g for g in logits if not allowed or g in allowed]
    if not names:
        return []
    x = np.array([logits[g] for g in names], np.float64)
    p = np.exp(x - x.max())
    p /= p.sum()
    order = np.argsort(-p)[:k]
    return [Guess(names[i], float(p[i])) for i in order]


def hand_model() -> HandshapeModel:
    global _hand
    if _hand is None:
        _hand = HandshapeModel.load()
    return _hand


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    x = np.array(list(logits.values()), np.float64)
    p = np.exp(x - x.max())
    p /= p.sum()
    return dict(zip(logits, p.tolist()))


def rank_mixed(word_logits: dict[str, float] | None, hand_logprobs: dict[str, float] | None,
               allowed: set[str], k: int = 5) -> list[Guess]:
    """Rank an allowed set that mixes digits with word-model signs (a keypad: 0-9 + yes/no/finish).

    The two models never compete on the same sign. The word model's full 250-way
    softmax says how likely the clip is one of the allowed non-digit signs (p_word);
    the rest of the probability goes to the digits, split by the handshape model.
    A digit hand shape spreads the word model thin, so p_word stays small unless the
    player really signed YES, NO or FINISH.
    """
    digits = [g for g in allowed if g in DIGITS]
    others = [g for g in allowed if g not in DIGITS and word_logits and g in word_logits]
    p_word = 0.0
    out: dict[str, float] = {}
    if others and word_logits:
        p_all = _softmax(word_logits)
        p_word = sum(p_all[g] for g in others)
        inner = _softmax({g: word_logits[g] for g in others})
        out.update({g: p_word * inner[g] for g in others})
    if digits and hand_logprobs:
        hand = _softmax({g: hand_logprobs[g] for g in digits if g in hand_logprobs})
        out.update({g: (1.0 - p_word) * p for g, p in hand.items()})
    elif out:
        out = {g: p / p_word for g, p in out.items()}  # no hand seen: only the word signs are possible
    total = sum(out.values())
    if not out or total <= 0:
        return []
    ranked = sorted(out.items(), key=lambda kv: -kv[1])[:k]
    return [Guess(g, p / total) for g, p in ranked]


def recognize(clip: np.ndarray, allowed: set[str], k: int = 3) -> list[Guess]:
    if allowed and any(g in DIGITS for g in allowed):
        others = {g for g in allowed if g not in DIGITS}
        word = model().scores(clip) if others else None
        return rank_mixed(word, hand_model().scores(clip), allowed, k)
    return rank(model().scores(clip), allowed, k)
