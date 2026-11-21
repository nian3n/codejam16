# Owner: Teammate 3 (Vision and retrieval)
"""Digit model (spec §6.4): features, nearest neighbours, and routing in the recognizer."""
import numpy as np

from escape_pod.vision import handshape as hs
from escape_pod.vision.handshape import DIGITS, HandshapeModel, features, features_from_hands
from escape_pod.vision.landmarks import LEFT, RIGHT
from escape_pod.vision.recognizer import rank_mixed

RNG = np.random.default_rng(0)
# One made-up "hand shape" per digit: 21 points around a wrist at 0 with a middle knuckle at (0, -1).
SHAPES = {}
for d in DIGITS:
    pts = RNG.normal(0, 0.6, (21, 3))
    pts[hs.WRIST] = 0
    pts[hs.MIDDLE_MCP] = [0, -1, 0]
    SHAPES[d] = pts


def hand_clip(d, frames=12, shift=(0.4, 0.5, 0.0), scale=0.1, noise=0.0, rng=RNG):
    h = SHAPES[d] * scale + np.array(shift)
    return np.repeat(h[None], frames, 0) + rng.normal(0, noise, (frames, 21, 3))


def full_clip(hand, left=False):
    clip = np.full((len(hand), 543, 3), np.nan, np.float32)
    clip[:, LEFT if left else RIGHT, :] = hand
    return clip


def nan_hand(frames=12):
    return np.full((frames, 21, 3), np.nan)


def test_features_ignore_where_the_hand_is_and_how_big_it_looks():
    a = features_from_hands(nan_hand(), hand_clip("3", shift=(0.2, 0.3, 0), scale=0.1))
    b = features_from_hands(nan_hand(), hand_clip("3", shift=(0.7, 0.6, 0.1), scale=0.25))
    assert a.shape == (hs.N_FEATURES,)
    assert np.allclose(a, b, atol=1e-5)


def test_a_left_hand_matches_the_same_shape_on_the_right_hand():
    right = hand_clip("7")
    left = right.copy()
    left[..., 0] = 1.0 - left[..., 0]  # the mirror image, as the left hand makes it
    assert np.allclose(features_from_hands(nan_hand(), right), features_from_hands(left, nan_hand()), atol=1e-5)


def test_the_steadiest_frames_win_over_the_hand_moving_into_place():
    still = hand_clip("5", frames=6)
    moving = hand_clip("2", frames=8, noise=0.05, rng=np.random.default_rng(1))  # shaky lead-in
    clip = np.concatenate([moving, still])
    assert np.allclose(features_from_hands(nan_hand(14), clip), features_from_hands(nan_hand(6), still), atol=1e-5)


def test_no_hand_means_no_features():
    assert features_from_hands(nan_hand(), nan_hand()) is None
    assert features(np.full((10, 543, 3), np.nan, np.float32)) is None


def _trained(per_digit=20, noise=0.004):
    rng = np.random.default_rng(2)
    X, y = [], []
    for d in DIGITS:
        for _ in range(per_digit):
            X.append(features_from_hands(nan_hand(), hand_clip(d, noise=noise, rng=rng)))
            y.append(d)
    return HandshapeModel(np.array(X), np.array(y))


def test_model_recognizes_noisy_digits_and_scores_a_full_clip():
    m = _trained()
    rng = np.random.default_rng(3)
    for d in DIGITS:
        clip = full_clip(hand_clip(d, shift=(0.6, 0.4, 0), scale=0.15, noise=0.004, rng=rng))
        s = m.scores(clip)
        assert max(s, key=lambda c: s[c]) == d
        assert set(s) == set(DIGITS)


def test_save_and_load_give_the_same_answers(tmp_path):
    m = _trained(per_digit=5)
    path = m.save(tmp_path / "hs.npz")
    m2 = HandshapeModel.load(path)
    f = features_from_hands(nan_hand(), hand_clip("8"))
    assert m2.proba(f) == m.proba(f)


def _logs(p):
    return {g: float(np.log(v)) for g, v in p.items()}


def test_mixed_ranking_stays_inside_the_allowed_set():
    hand = _logs({d: (0.91 if d == "4" else 0.01) for d in DIGITS})
    word = {g: 0.0 for g in ("yes", "no", "finish", "cat", "dog")}
    allowed = {"3", "4", "7", "yes", "no", "finish"}
    out = rank_mixed(word, hand, allowed, k=10)
    assert {g.gloss for g in out} <= allowed
    assert abs(sum(g.score for g in out) - 1) < 1e-9
    assert out[0].gloss == "4"


def test_a_clear_yes_beats_the_digits():
    hand = _logs({d: 0.1 for d in DIGITS})
    word = {"yes": 12.0, "no": 0.0, "finish": 0.0, "cat": 0.0}  # the word model is sure: YES
    out = rank_mixed(word, hand, {"1", "2", "yes", "no", "finish"}, k=3)
    assert out[0].gloss == "yes" and out[0].score > 0.9


def test_digits_only_and_no_hand_seen():
    hand = _logs({d: (0.5 if d == "9" else 0.5 / 9) for d in DIGITS})
    assert rank_mixed(None, hand, {"9", "1"}, k=2)[0].gloss == "9"
    assert rank_mixed(None, None, {"9", "1"}) == []
    word = {"yes": 1.0, "no": 0.0}
    out = rank_mixed(word, None, {"9", "yes", "no"}, k=3)  # no hand: only the word signs remain
    assert [g.gloss for g in out] == ["yes", "no"]


def test_train_digits_reads_recordings_scores_each_person_on_the_others_and_saves(tmp_path, monkeypatch, capsys):
    from escape_pod import config
    from escape_pod.vision import train_digits

    rng = np.random.default_rng(4)
    for person in ("ana", "ben"):
        for d in DIGITS:
            out = tmp_path / "data" / person / d
            out.mkdir(parents=True)
            for i in range(4):
                right = hand_clip(d, shift=(rng.uniform(0.3, 0.7), 0.5, 0), scale=rng.uniform(0.08, 0.2),
                                  noise=0.003, rng=rng)
                np.savez_compressed(out / f"{i}.npz", left=nan_hand(), right=right, digit=d, person=person)
    np.savez_compressed(tmp_path / "data" / "ana" / "3" / "nohand.npz", left=nan_hand(), right=nan_hand())

    X, y, who, skipped = train_digits.load_samples(tmp_path / "data")
    assert X.shape == (80, hs.N_FEATURES) and skipped == 1
    desc, pairs = train_digits.evaluate(X, y, who, k=3)
    assert "leave-one-person-out" in desc and len(pairs) == 80
    assert sum(t == p for t, p in pairs) == 80

    monkeypatch.setattr(config, "HANDSHAPE_FILE", tmp_path / "models" / "handshape.npz")
    train_digits.main(["--data", str(tmp_path / "data"), "--k", "3"])
    assert "Accuracy (leave-one-person-out over 2 people): 80/80" in capsys.readouterr().out
    assert HandshapeModel.load().predict(X[0]) == y[0]
