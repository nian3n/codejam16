# Owner: Teammate 3 (Vision and retrieval)
"""Spec §13 vision tests. The model tests skip if the model or TFLite is not installed."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from escape_pod import config
from escape_pod.puzzles.engine import load_pool
from escape_pod.vision.landmarks import LEFT, POSE, RIGHT, left_handed, to_array
from escape_pod.vision.recognizer import rank
from escape_pod.vision.segmenter import Segmenter

HAVE_MODEL = (config.ISLR_DIR / "model.tflite").exists()


def _lms(n, x=0.5, y=0.5):
    return SimpleNamespace(landmark=[SimpleNamespace(x=x, y=y, z=0.0) for _ in range(n)])


def test_to_array_order_and_nan_blocks():
    res = SimpleNamespace(face_landmarks=_lms(468, 0.1), left_hand_landmarks=None,
                          pose_landmarks=_lms(33, 0.3), right_hand_landmarks=_lms(21, 0.9))
    a = to_array(res)
    assert a.shape == (543, 3) and a.dtype == np.float32
    assert np.allclose(a[:468, 0], 0.1)
    assert np.isnan(a[LEFT]).all()
    assert np.allclose(a[POSE, 0], 0.3)
    assert np.allclose(a[RIGHT, 0], 0.9)


def test_left_handed_mirrors_and_swaps():
    a = np.full((543, 3), 0.5, np.float32)
    a[RIGHT, 0] = 0.8
    a[LEFT] = np.nan
    b = left_handed(a)
    assert np.allclose(b[LEFT, 0], 0.2)  # the right hand moved to the left block, mirrored
    assert np.isnan(b[RIGHT]).all()


def test_rank_restricts_and_renormalizes():
    logits = {"cat": 2.0, "dog": 1.0, "cow": 0.5, "car": 9.0}
    g = rank(logits, {"cat", "dog", "cow", "zebra"}, k=5)
    assert [x.gloss for x in g] == ["cat", "dog", "cow"]  # never "car", never unknown "zebra"
    assert abs(sum(x.score for x in g) - 1.0) < 1e-9
    assert rank(logits, None, k=1)[0].gloss == "car"


def _frame(hand_x=None, hand_y=0.5):
    f = np.full((543, 3), np.nan, np.float32)
    f[POSE] = 0.5
    f[POSE.start + 23, 1] = f[POSE.start + 24, 1] = 0.8  # hips at y = 0.8
    if hand_x is not None:
        f[RIGHT, 0], f[RIGHT, 1], f[RIGHT, 2] = hand_x, hand_y, 0.0
    return f


def test_segmenter_splits_three_signs():
    seg = Segmenter(fps=30)
    frames = []
    for _ in range(3):
        frames += [_frame()] * 15                                              # hands down
        frames += [_frame(0.3 + 0.02 * (i % 10), 0.4) for i in range(30)]       # 1 s of signing
        frames += [_frame(0.3, 0.4)] * 15                                       # hold still 0.5 s
    frames += [_frame()] * 10
    clips = [c for c in (seg.push(f) for f in frames) if c is not None]
    assert len(clips) == 3
    for c in clips:
        assert c.shape[1:] == (543, 3) and 25 <= len(c) <= 36


def test_segmenter_ignores_short_twitch_and_resting_hands():
    seg = Segmenter(fps=30)
    frames = [_frame(0.3 + 0.02 * i, 0.4) for i in range(4)]   # 0.13 s twitch
    frames += [_frame()] * 10
    frames += [_frame(0.3, 0.9)] * 40                           # hand resting below the waist
    assert all(seg.push(f) is None for f in frames)


@pytest.mark.skipif(not HAVE_MODEL, reason="run: uv run download-models")
def test_every_word_model_gloss_is_in_the_label_map():
    index = json.loads((config.ISLR_DIR / "sign_to_prediction_index_map.json").read_text())
    labels = {g.lower() for g in index}
    for s in load_pool().values():
        if s.widget == "keypad":
            continue  # digits and letters use the handshape classifier (spec §6.4)
        missing = [g for g in s.pool if g not in labels]
        assert not missing, f"{s.id}: {missing} are not in the model's label map"
    assert set(config.CORE_SIGNS) <= labels


@pytest.mark.skipif(not HAVE_MODEL, reason="run: uv run download-models")
def test_word_model_returns_250_scores():
    pytest.importorskip("mediapipe")  # stands in for "the vision extra is installed"
    from escape_pod.vision.word_model import WordModel

    m = WordModel()
    clip = np.random.default_rng(0).random((20, 543, 3)).astype(np.float32)
    clip[:, LEFT] = np.nan
    s = m.scores(clip)
    assert len(s) == 250 and "tv" in s and "cow" in s
    assert len(m.scores(clip[:1])) == 250  # 1-frame clips are padded (XNNPACK needs >= 3)
