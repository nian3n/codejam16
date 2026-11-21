# Owner: Teammate 3 (Vision and retrieval)
"""Train the digit model from recorded samples (spec §6.4).

    uv run train-digits [--k 7]

Reads data/handshape/<person>/<digit>/*.npz (from record-digits), turns each
sample into the 63 hand-shape features and saves models/handshape.npz.

Before saving it prints an honest accuracy: with 2+ people, each person is
tested on a model trained only on the OTHER people (how a stranger at the demo
will do). With one person, a 5-fold split (optimistic: same hand, same camera).
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from escape_pod import config
from escape_pod.vision.handshape import DIGITS, HandshapeModel, features_from_hands


def load_samples(root: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """-> (X, y, person, skipped). Samples with no usable hand are skipped."""
    X, y, who, skipped = [], [], [], 0
    for f in sorted(root.glob("*/*/*.npz")):
        digit, person = f.parent.name, f.parent.parent.name
        if digit not in DIGITS:
            continue
        d = np.load(f)
        feat = features_from_hands(d["left"], d["right"])
        if feat is None:
            skipped += 1
            continue
        X.append(feat)
        y.append(digit)
        who.append(person)
    if not X:
        return np.zeros((0, 63), np.float32), np.array([]), np.array([]), skipped
    return np.stack(X), np.array(y), np.array(who), skipped


def evaluate(X: np.ndarray, y: np.ndarray, who: np.ndarray, k: int, seed: int = 0) -> tuple[str, list[tuple[str, str]]]:
    """-> (description, [(true, predicted)])."""
    people = sorted(set(who.tolist()))
    pairs: list[tuple[str, str]] = []
    if len(people) >= 2:
        for p in people:
            test = who == p
            m = HandshapeModel(X[~test], y[~test], k)
            pairs += [(t, m.predict(x)) for x, t in zip(X[test], y[test])]
        return f"leave-one-person-out over {len(people)} people", pairs
    folds = np.random.default_rng(seed).permutation(len(y)) % 5
    for f in range(5):
        test = folds == f
        m = HandshapeModel(X[~test], y[~test], k)
        pairs += [(t, m.predict(x)) for x, t in zip(X[test], y[test])]
    return "5-fold split, one person only (optimistic: record more people)", pairs


def report(desc: str, pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    right = sum(t == p for t, p in pairs)
    print(f"\nAccuracy ({desc}): {right}/{n} = {right / n:.0%}")
    per = defaultdict(lambda: [0, 0])
    for t, p in pairs:
        per[t][0] += 1
        per[t][1] += t == p
    print("  " + "  ".join(f"{d}:{per[d][1] * 100 // per[d][0]}%" for d in DIGITS if per[d][0]))
    confused = Counter((t, p) for t, p in pairs if t != p)
    if confused:
        print("Most confused (signed -> model said): " +
              ", ".join(f"{t}->{p} x{c}" for (t, p), c in confused.most_common(6)))
    return right / n


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description="Train the digit (handshape) model from recorded samples.")
    ap.add_argument("--k", type=int, default=7, help="neighbours that vote")
    ap.add_argument("--data", type=Path, default=config.HANDSHAPE_DATA_DIR)
    a = ap.parse_args(argv)
    X, y, who, skipped = load_samples(a.data)
    if len(y) == 0:
        raise SystemExit(f"No samples in {a.data}. Record some first: uv run --extra vision record-digits --name <you>")
    counts = Counter(y.tolist())
    print(f"{len(y)} samples from {len(set(who.tolist()))} people ({skipped} skipped: no hand found)")
    print("  " + "  ".join(f"{d}:{counts.get(d, 0)}" for d in DIGITS))
    missing = [d for d in DIGITS if counts.get(d, 0) == 0]
    if missing:
        print(f"Warning: no samples for {', '.join(missing)}. The model can never answer those.")
    if len(y) >= 10:
        report(*evaluate(X, y, who, a.k))
    path = HandshapeModel(X, y, a.k).save()
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main()
