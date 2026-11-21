# Owner: Teammate 1 (Game, scenes, widgets)
import math
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

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
