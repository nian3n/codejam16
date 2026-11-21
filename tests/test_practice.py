# Owner: Teammate 1 (Game, scenes, widgets)
import math
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from escape_pod.vision.handshape import DIGITS
from escape_pod.vision.landmarks import LEFT, N_POINTS
from escape_pod.web import practice, server

client = TestClient(server.app)


@pytest.mark.parametrize(
    ("target", "score", "approved"),
    [("cat", 0.75, True), ("cat", 0.74, False), ("dog", 0.1, False)],
)
def test_practice_approval_uses_target_confidence(monkeypatch, target, score, approved):
    cat_probability = score if target == "cat" else 1 - score
    logit = math.log(cat_probability / (1 - cat_probability))
    monkeypatch.setattr(practice, "model", lambda: SimpleNamespace(
        glosses=["cat", "dog"], scores=lambda _: {"cat": logit, "dog": 0.0},
    ))
    clip = np.full((3, N_POINTS, 3), np.nan, dtype="<f4")
    clip[:, LEFT] = 0.5
    result = client.post(
        "/api/practice/score", params={"target": target},
        content=clip.tobytes(), headers={"Content-Type": "application/octet-stream"},
    )
    assert result.status_code == 200
    assert result.json() == {"confidence": pytest.approx(score), "best_guess": "cat", "approved": approved}


def test_practice_needs_detected_hands():
    clip = np.full((3, N_POINTS, 3), np.nan, dtype="<f4")
    result = client.post(
        "/api/practice/score", params={"target": "cat"},
        content=clip.tobytes(), headers={"Content-Type": "application/octet-stream"},
    )
    assert result.status_code == 422


def test_practice_lists_only_game_words(monkeypatch):
    monkeypatch.setattr(practice, "model", lambda: SimpleNamespace(
        glosses=["cat", "dog", "callonphone", "yes"], scores=lambda _: {},
    ))
    assert client.get("/api/practice").json()["words"] == ["cat", "dog", "yes"]
    clip = np.zeros((3, N_POINTS, 3), dtype="<f4")
    result = client.post(
        "/api/practice/score", params={"target": "callonphone"},
        content=clip.tobytes(), headers={"Content-Type": "application/octet-stream"},
    )
    assert result.status_code == 400


def test_guess_returns_the_top_three_game_words(monkeypatch):
    logits = {"cat": 3.0, "dog": 2.0, "cow": 1.0, "pig": 0.5, "callonphone": 9.0}
    monkeypatch.setattr(practice, "model", lambda: SimpleNamespace(glosses=list(logits), scores=lambda _: logits))
    clip = np.full((4, N_POINTS, 3), np.nan, dtype="<f4")
    clip[:, LEFT] = 0.5
    body = clip.tobytes()
    headers = {"Content-Type": "application/octet-stream"}
    got = client.post("/api/practice/guess", content=body, headers=headers).json()["guesses"]
    assert [g["gloss"] for g in got] == ["cat", "dog", "cow"]  # callonphone is no game word
    assert got[0]["score"] > got[1]["score"] > got[2]["score"]
    got = client.post("/api/practice/guess", params={"words": "pig,cow"}, content=body, headers=headers).json()
    assert [g["gloss"] for g in got["guesses"]] == ["cow", "pig"]
    assert client.post("/api/practice/guess", params={"words": "zzz"}, content=body, headers=headers).status_code == 400


def test_warmup_loads_the_model_once(monkeypatch):
    loads = []
    monkeypatch.setattr(practice, "model", lambda: loads.append(1) or SimpleNamespace(glosses=["cat"]))
    assert client.get("/api/practice/warmup").json()["ready"] is True
    assert loads


def test_warmup_without_the_model_says_so(monkeypatch):
    def missing():
        raise FileNotFoundError("models/islr/model.tflite")
    monkeypatch.setattr(practice, "model", missing)
    body = client.get("/api/practice/warmup").json()
    assert body["ready"] is False and "download-models" in body["detail"]


@pytest.mark.parametrize("trained", [False, True])
def test_digit_captures_use_the_handshape_model_or_report_the_fallback(monkeypatch, trained):
    def digits():
        if not trained:
            raise FileNotFoundError("models/handshape.npz")
        return SimpleNamespace(classes=DIGITS, scores=lambda _: {digit: -float(digit) for digit in DIGITS})

    monkeypatch.setattr(practice, "hand_model", digits)
    monkeypatch.setattr(practice, "warm_model", lambda: {"ready": False})
    assert client.get("/api/practice/warmup").json()["digits_ready"] is trained
    clip = np.full((3, N_POINTS, 3), np.nan, dtype="<f4")
    clip[:, LEFT] = 0.5
    response = client.post("/api/practice/guess", params={"words": ",".join(DIGITS)},
                           content=clip.tobytes(), headers={"Content-Type": "application/octet-stream"})
    if trained:
        assert response.status_code == 200
        assert [guess["gloss"] for guess in response.json()["guesses"]] == ["0", "1", "2"]
    else:
        assert response.status_code == 503 and "Type the digits" in response.json()["detail"]
