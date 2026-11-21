# Owner: Teammate 1 (Game, scenes, widgets)
"""Score solo practice clips using the existing ASL word model."""
from threading import Lock

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from escape_pod.vision.handshape import DIGITS
from escape_pod.vision.landmarks import LEFT, N_POINTS, RIGHT
from escape_pod.vision.handshape import DIGITS
from escape_pod.vision.recognizer import game_words, hand_model, model, rank, rank_mixed

router = APIRouter(prefix="/api/practice")
APPROVAL_THRESHOLD = 0.75
MAX_FRAMES = 75
MIN_HAND_FRAMES = 3
FRAME_BYTES = N_POINTS * 3 * 4
model_lock = Lock()  # The shared TFLite interpreter handles one clip at a time.
DIGIT_FALLBACK = "Camera digit recognition is unavailable. Type the digits instead."


def practice_model():
    try:
        return model()
    except (ImportError, FileNotFoundError) as exc:
        raise HTTPException(
            503, "Set up the sign model with uv sync --extra vision and uv run download-models."
        ) from exc


def warm_model() -> dict:
    """Load the word model now (about 6 s the first time), so the first sign is not slow."""
    try:
        with model_lock:
            practice_model()
    except HTTPException as exc:
        return {"ready": False, "detail": exc.detail}
    return {"ready": True}


def digit_classifier():
    try:
        classifier = hand_model()
    except (OSError, ValueError, KeyError):
        return None
    # Any digit can appear on the tag, so partial training cannot replace typing.
    return classifier if set(DIGITS) <= set(classifier.classes) else None


def recognition_status() -> dict:
    status = warm_model()
    with model_lock:
        status["digits_ready"] = digit_classifier() is not None
    return status


@router.get("/warmup")
async def practice_warmup():
    # The game's "Initializing" screen waits for this before the timer starts.
    return await run_in_threadpool(recognition_status)


@router.get("")
def practice_options():
    with model_lock:
        glosses = set(practice_model().glosses)
    # Only the game's words (the glossary words), so every practice word has a clip to
    # learn from. Scoring below still ranks against all 250, so a sign is never approved
    # just because the list is short.
    words = game_words(glosses) & glosses
    return {"words": sorted(words), "threshold": APPROVAL_THRESHOLD}


def parse_clip(data: bytearray) -> np.ndarray:
    """Little-endian float32 frames -> (T, 543, 3), trimmed to the frames with a hand."""
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
    return clip[frames[0]:frames[-1] + 1]


def logits_for(clip: np.ndarray) -> tuple[dict[str, float], list[str]]:
    with model_lock:
        classifier = practice_model()
        logits = classifier.scores(clip)
        glosses = list(classifier.glosses)
    if not np.isfinite(list(logits.values())).all():
        raise HTTPException(422, "The model could not score that clip. Try again with your upper body in view.")
    return logits, glosses


def score_clip(data: bytearray, target: str):
    clip = parse_clip(data)
    with model_lock:
        known = set(practice_model().glosses)
    if target not in known or target not in game_words(known):
        raise HTTPException(400, "Choose a word from the practice list.")
    logits, _ = logits_for(clip)
    # Rank against the full vocabulary so choosing a target does not inflate its score.
    guesses = rank(logits, None, k=len(logits))
    confidence = next(guess.score for guess in guesses if guess.gloss == target)
    return {
        "confidence": confidence,
        "best_guess": guesses[0].gloss,
        "approved": guesses[0].gloss == target and confidence >= APPROVAL_THRESHOLD,
    }


def guess_clip(data: bytearray, words: str | None):
    """Top 3 guesses for one clip of a sequence, among the game words (or a subset)."""
    clip = parse_clip(data)
    logits, glosses = logits_for(clip)
    allowed = game_words(set(glosses))
    if words:
        allowed &= {w.strip() for w in words.split(",")}
        if not allowed:
            raise HTTPException(400, "None of those words is a game word.")
    guesses = rank(logits, allowed, k=3)
    if allowed & set(DIGITS):
        # A keypad is on the bomb: the digit model takes the probability the word model
        # does not give to the allowed words (recognizer.rank_mixed). Without a digit
        # model, digits stay typed only.
        try:
            with model_lock:
                hand = hand_model().scores(clip)
            guesses = rank_mixed(logits, hand, allowed, k=3)
        except FileNotFoundError:
            pass
    return {"guesses": [{"gloss": g.gloss, "score": g.score} for g in guesses]}


async def read_clip(request: Request) -> bytearray:
    if request.headers.get("content-type") != "application/octet-stream":
        raise HTTPException(415, "Expected a binary landmark clip.")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_FRAMES * FRAME_BYTES:
            raise HTTPException(413, "This practice clip is too long.")
        data.extend(chunk)
    return data


@router.post("/guess")
async def practice_guess(request: Request, words: str | None = None):
    """words: optional comma-separated subset (the game will pass a module's pool)."""
    return await run_in_threadpool(guess_clip, await read_clip(request), words)


@router.post("/score")
async def practice_score(request: Request, target: str):
    return await run_in_threadpool(score_clip, await read_clip(request), target)
