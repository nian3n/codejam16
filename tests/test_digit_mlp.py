# Owner: Teammate 3 (Vision and retrieval)
import math

import numpy as np
import pytest

from escape_pod.vision import digit_mlp, recognizer
from escape_pod.vision.digit_mlp import CLASSES, DigitMLP, fold_batchnorm, hand_features
from escape_pod.vision.handshape import DIGITS
from escape_pod.vision.landmarks import LEFT, N_POINTS, RIGHT

rng = np.random.default_rng(0)


def _hand(seed=1):
    pts = np.random.default_rng(seed).normal(size=(21, 3)).astype(np.float32) * 0.05 + 0.5
    return pts


def _clip(hand, side="right", frames=8):
    clip = np.full((frames, N_POINTS, 3), np.nan, np.float32)
    clip[:, RIGHT if side == "right" else LEFT] = hand
    return clip


def _tiny_model():
    # Random weights in the converted format: 3 dense layers, 63 -> 8 -> 8 -> 36.
    return DigitMLP([(rng.normal(size=(8, 63)), rng.normal(size=8)),
                     (rng.normal(size=(8, 8)), rng.normal(size=8)),
                     (rng.normal(size=(36, 8)), rng.normal(size=36))], CLASSES)


def test_fold_batchnorm_gives_the_same_output():
    W, b = rng.normal(size=(5, 4)), rng.normal(size=5)
    g, beta, mean, var = rng.normal(size=5), rng.normal(size=5), rng.normal(size=5), rng.uniform(0.5, 2, 5)
    x = rng.normal(size=(3, 4))
    want = (x @ W.T + b - mean) / np.sqrt(var + 1e-5) * g + beta
    W2, b2 = fold_batchnorm(W, b, g, beta, mean, var, 1e-5)
    assert np.allclose(x @ W2.T + b2, want)


def test_features_follow_the_model_card():
    # Card: pts - pts[0], then divide by the 3-D norm of point 9.
    hand = _hand()
    want = hand - hand[0]
    want = (want / np.linalg.norm(want[9])).reshape(-1)
    assert np.allclose(hand_features(_clip(hand)), want, atol=1e-5)


def test_a_left_hand_is_mirrored_to_a_right_hand():
    hand = _hand()
    mirrored = hand.copy()
    mirrored[:, 0] = 1.0 - mirrored[:, 0]
    assert np.allclose(hand_features(_clip(mirrored, "left")), hand_features(_clip(hand)), atol=1e-5)


def test_scores_are_log_probabilities_over_the_digits_only():
    s = _tiny_model().scores(_clip(_hand()))
    assert set(s) == set(DIGITS)
    assert math.isclose(sum(math.exp(v) for v in s.values()), 1.0, rel_tol=1e-6)


def test_no_hand_means_no_scores():
    assert _tiny_model().scores(np.full((5, N_POINTS, 3), np.nan, np.float32)) is None


def test_save_and_load(tmp_path):
    m = _tiny_model()
    path = m.save(tmp_path / "d.npz")
    clip = _clip(_hand())
    assert DigitMLP.load(path).scores(clip) == pytest.approx(m.scores(clip))


def test_the_recognizer_prefers_the_downloaded_digit_model(tmp_path, monkeypatch):
    path = _tiny_model().save(tmp_path / "d.npz")
    monkeypatch.setattr(digit_mlp.config, "DIGIT_MLP_FILE", path)
    monkeypatch.setattr(recognizer, "_hand", None)
    assert isinstance(recognizer.hand_model(), DigitMLP)
