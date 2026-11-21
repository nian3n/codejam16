# Owner: Teammate 3 (Vision and retrieval)
"""TFLite word-sign model wrapper (spec §6.3).

Day-one checks, measured on 2026-11-21 (see vision/README.md):
  signature  serving_default: inputs (T, 543, 3) float32 -> outputs (250,) logits
  XNNPACK    fails on clips shorter than 3 frames, so short clips are padded
  latency    ~30-75 ms for 3-120 frames on a laptop CPU (x64 under emulation)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from escape_pod import config

MIN_FRAMES = 3


def _interpreter(path: Path):
    try:  # macOS / Linux: the small LiteRT runtime
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:  # Windows: no LiteRT wheels, so use TensorFlow's copy
        import os
        import warnings

        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
        warnings.filterwarnings("ignore", message=".*tf.lite.Interpreter is deprecated.*")
        import tensorflow as tf

        Interpreter = tf.lite.Interpreter
    return Interpreter(model_path=str(path))


class WordModel:
    def __init__(self, model_dir: Path = config.ISLR_DIR):
        model_path = model_dir / "model.tflite"
        index_path = model_dir / "sign_to_prediction_index_map.json"
        if not model_path.exists():
            raise FileNotFoundError(f"{model_path} is missing. Run: uv run download-models")
        self.interp = _interpreter(model_path)
        self.runner = self.interp.get_signature_runner("serving_default")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        # Labels are lowercased: the map has "TV", the game uses "tv" (one spelling per gloss).
        self.glosses = [g.lower() for g, _ in sorted(index.items(), key=lambda kv: kv[1])]

    def logits(self, clip: np.ndarray) -> np.ndarray:
        """clip (T, 543, 3) float32 with NaN for missing parts -> (250,) logits."""
        clip = np.asarray(clip, np.float32)
        if len(clip) < MIN_FRAMES:
            clip = np.concatenate([clip] * (MIN_FRAMES // max(1, len(clip)) + 1))[:MIN_FRAMES]
        out = self.runner(inputs=clip)
        return np.asarray(out["outputs"], np.float32).reshape(-1)

    def scores(self, clip: np.ndarray) -> dict[str, float]:
        return dict(zip(self.glosses, self.logits(clip).tolist()))
