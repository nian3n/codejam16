# Owner: Teammate 1 (Game, scenes, widgets)
"""Score solo practice clips using the existing ASL word model."""
from threading import Lock

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from escape_pod.vision.landmarks import LEFT, N_POINTS, RIGHT
from escape_pod.vision.recognizer import model, rank

router = APIRouter(prefix="/api/practice")
APPROVAL_THRESHOLD = 0.75
MAX_FRAMES = 75
MIN_HAND_FRAMES = 3
FRAME_BYTES = N_POINTS * 3 * 4
model_lock = Lock()  # The shared TFLite interpreter handles one clip at a time.


def practice_model():
    try:
        return model()
    except (ImportError, FileNotFoundError) as exc:
        raise HTTPException(
            503, "Set up the sign model with uv sync --extra vision and uv run download-models."
        ) from exc


@router.get("")
def practice_options():
    with model_lock:
        return {"words": sorted(practice_model().glosses), "threshold": APPROVAL_THRESHOLD}


def score_clip(data: bytearray, target: str):
    if not data or len(data) % FRAME_BYTES:
        raise HTTPException(400, "Send a clip of complete landmark frames.")
    clip = np.frombuffer(data, dtype="<f4").reshape(-1, N_POINTS, 3)
    if np.isinf(clip).any():
        raise HTTPException(400, "The clip contains invalid landmarks.")
    left = np.isfinite(clip[:, LEFT]).all(axis=(1, 2))
    right = np.isfinite(clip[:, RIGHT]).all(axis=(1, 2))
    frames = np.flatnonzero(left | right)
    if len(frames) < MIN_HAND_FRAMES:
        raise HTTPException(422, "Keep your hands in view and try again.")

    with model_lock:
        classifier = practice_model()
        if target not in classifier.glosses:
            raise HTTPException(400, "Choose a word from the practice list.")
        logits = classifier.scores(clip[frames[0]:frames[-1] + 1])
    if not np.isfinite(list(logits.values())).all():
        raise HTTPException(422, "The model could not score that clip. Try again with your upper body in view.")
    # Rank against the full vocabulary so choosing a target does not inflate its score.
    guesses = rank(logits, None, k=len(logits))
    confidence = next(guess.score for guess in guesses if guess.gloss == target)
    return {
        "confidence": confidence,
        "best_guess": guesses[0].gloss,
        "approved": guesses[0].gloss == target and confidence >= APPROVAL_THRESHOLD,
    }


@router.post("/score")
async def practice_score(request: Request, target: str):
    if request.headers.get("content-type") != "application/octet-stream":
        raise HTTPException(415, "Expected a binary landmark clip.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_FRAMES * FRAME_BYTES:
            raise HTTPException(413, "This practice clip is too long.")
        data.extend(chunk)
    return await run_in_threadpool(score_clip, data, target)
