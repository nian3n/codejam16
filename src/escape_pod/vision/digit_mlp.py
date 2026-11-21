# Owner: Teammate 3 (Vision and retrieval)
"""Digits 0-9 from a ready-made model: "ASL Landmark MLP" (spec §6.4).

Model: nocontextdoruk/asl-landmark-mlp on Hugging Face, CC BY-NC 4.0, trained on the
ASL-HG dataset (Pranto et al., Data in Brief, 2026). It reads one hand's 21 MediaPipe
points and scores 36 still hand shapes: 0-9 and A-Z. The game only ever asks for
digits, so scores() softmaxes over the 10 digit logits and drops the letters.

We do not run ONNX at play time. The network is 3 dense layers with BatchNorm and
ReLU, so download-models folds the BatchNorm into the dense layers once and saves plain
NumPy weights (models/digits/asl_mlp.npz). The server then needs no extra runtime.

Input, as on the model card: the points minus the wrist, divided by the 3-D length of
wrist -> middle-finger knuckle (point 9). A left hand is mirrored to a right hand, like
the k-NN digit model in handshape.py, which stays as the fallback.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from escape_pod import config
from escape_pod.vision.handshape import DIGITS, features_from_hands
from escape_pod.vision.landmarks import LEFT, RIGHT

CLASSES = tuple("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")  # mlp_classes.json order
SOURCE = "https://huggingface.co/nocontextdoruk/asl-landmark-mlp/resolve/main"
CREDIT = ("Digit model: ASL Landmark MLP (nocontextdoruk/asl-landmark-mlp), CC BY-NC 4.0, "
          "trained on ASL-HG (Pranto et al., 2026).")


def hand_features(clip: np.ndarray) -> np.ndarray | None:
    """(T, 543, 3) -> the model's 63 inputs from the steadiest frames, or None without a hand."""
    return features_from_hands(clip[:, LEFT, :], clip[:, RIGHT, :], scale_xyz=True)


def fold_batchnorm(W, b, gamma, beta, mean, var, eps):
    """Dense layer followed by BatchNorm (inference) -> one dense layer."""
    k = gamma / np.sqrt(var + eps)
    return W * k[:, None], (b - mean) * k + beta


class DigitMLP:
    def __init__(self, layers: list[tuple[np.ndarray, np.ndarray]], classes=CLASSES):
        self.layers = [(np.asarray(W, np.float32), np.asarray(b, np.float32)) for W, b in layers]
        self.classes = tuple(classes)
        self.digit_idx = [self.classes.index(d) for d in DIGITS]

    @classmethod
    def load(cls, path: Path | None = None) -> "DigitMLP":
        path = path or config.DIGIT_MLP_FILE
        if not path.exists():
            raise FileNotFoundError(f"No digit model at {path}. Run: uv run download-models")
        d = np.load(path)
        n = int(d["n_layers"])
        return cls([(d[f"W{i}"], d[f"b{i}"]) for i in range(n)], [str(c) for c in d["classes"]])

    def save(self, path: Path | None = None) -> Path:
        path = path or config.DIGIT_MLP_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"W{i}": W for i, (W, _) in enumerate(self.layers)}
        arrays.update({f"b{i}": b for i, (_, b) in enumerate(self.layers)})
        np.savez_compressed(path, n_layers=len(self.layers), classes=np.array(self.classes), **arrays)
        return path

    def logits(self, feat: np.ndarray) -> np.ndarray:
        x = feat.astype(np.float32)
        for i, (W, b) in enumerate(self.layers):
            x = x @ W.T + b
            if i < len(self.layers) - 1:
                x = np.maximum(x, 0.0)  # ReLU; Dropout is off at inference
        return x

    def scores(self, clip: np.ndarray) -> dict[str, float] | None:
        """Log-probabilities over the 10 digits for a (T, 543, 3) clip, or None without a hand."""
        f = hand_features(clip)
        if f is None:
            return None
        z = self.logits(f)[self.digit_idx].astype(np.float64)
        z = z - z.max()
        logp = z - np.log(np.exp(z).sum())
        return dict(zip(DIGITS, logp.tolist()))


def convert(onnx_path: Path, classes: list[str]) -> DigitMLP:
    """The downloaded ONNX file -> DigitMLP. Needs the onnx package (the "model" extra)."""
    import onnx
    from onnx import numpy_helper

    g = onnx.load(str(onnx_path)).graph
    w = {t.name: numpy_helper.to_array(t).astype(np.float64) for t in g.initializer}
    layers, pending = [], None
    for node in g.node:
        if node.op_type == "Gemm":
            if pending:
                layers.append(pending)
            pending = (w[node.input[1]], w[node.input[2]])  # transB=1: W is (out, in)
        elif node.op_type == "BatchNormalization":
            eps = next((a.f for a in node.attribute if a.name == "epsilon"), 1e-5)
            gamma, beta, mean, var = (w[n] for n in node.input[1:5])
            pending = fold_batchnorm(*pending, gamma, beta, mean, var, eps)
        elif node.op_type not in ("Relu", "Dropout", "Identity"):
            raise ValueError(f"unexpected layer {node.op_type} in {onnx_path.name}")
    layers.append(pending)
    return DigitMLP(layers, classes)
