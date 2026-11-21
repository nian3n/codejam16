# Owner: Teammate 3 (Vision and retrieval)
"""Record digit samples (0-9) for the handshape model (spec §6.4).

    uv run --extra vision record-digits --name ana [--rounds 30] [--camera 0] [--photos]

The tool shows a digit. Make that hand shape and hold it still: after HOLD_S of
stillness it saves the sample by itself, then waits until you move your hand
before it takes the next one (so every sample is a fresh try, not a copy).

Keys (in the video window):
  Space    pause / resume
  S        skip this digit for now
  X        delete the last sample (you made the wrong shape)
  Q / Esc  quit (everything saved so far stays)

Saved: data/handshape/<name>/<digit>/<time>.npz with the two hand blocks
(T, 21, 3) as MediaPipe gives them (NaN where a hand was not found). Landmarks
only, no images (spec rule 8). --photos also saves ONE clear photo per digit to
data/handshape/<name>/photos/, for the glossary. Ask the person first.
Then train: uv run train-digits
"""
from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

import numpy as np

from escape_pod import config
from escape_pod.vision.handshape import DIGITS, normalize, pick_hand
from escape_pod.vision.landmarks import LEFT, RIGHT, Extractor, left_handed

HOLD_S = 0.6        # hold the shape this long to save a sample
STILL = 0.035       # mean movement of the normalized hand per frame that still counts as still
MOVED = 0.12        # after a save, the hand must change this much (or leave) before the next one
PANEL_W = 380
GREEN, RED, AMBER, GREY, WHITE = (90, 220, 120), (70, 70, 240), (40, 190, 255), (150, 150, 150), (240, 240, 240)


def shape_of(lm: np.ndarray) -> np.ndarray | None:
    """One frame (543, 3) -> the signing hand, normalized (21, 3), or None."""
    hand, is_left = pick_hand(lm[None, LEFT, :], lm[None, RIGHT, :])
    n = normalize(hand.astype(np.float64), is_left)[0]
    return n if np.isfinite(n).all() else None


class Recorder:
    def __init__(self, args):
        import cv2

        self.cv2 = cv2
        self.name = args.name.strip().lower().replace(" ", "_")
        self.rounds = args.rounds
        self.photos = args.photos
        self.left = args.left_handed or config.LEFT_HANDED
        self.dir = config.HANDSHAPE_DATA_DIR / self.name
        self.counts = {d: len(list((self.dir / d).glob("*.npz"))) for d in DIGITS}
        self.saved: list[Path] = []
        self.queue: list[str] = []
        self.target = self.next_target()
        self.buf: list[np.ndarray] = []     # recent frames (543, 3) while the shape is held
        self.still_since = 0.0
        self.armed = True                   # False right after a save, until the hand moves
        self.ref: np.ndarray | None = None  # the shape at the last save
        self.paused = False
        self.flash_until = 0.0
        print("Loading MediaPipe Holistic...")
        self.extractor = Extractor()

    def next_target(self) -> str | None:
        todo = [d for d in DIGITS if self.counts[d] < self.rounds]
        if not todo:
            return None
        if not self.queue:
            self.queue = random.sample(todo, len(todo))  # a shuffled round: no long runs of one digit
        while self.queue:
            d = self.queue.pop()
            if self.counts[d] < self.rounds:
                return d
        return self.next_target()

    def save(self, frames: list[np.ndarray], bgr: np.ndarray):
        clip = np.stack(frames)
        d = self.target
        out = self.dir / d / f"{time.strftime('%Y%m%d-%H%M%S')}-{len(self.saved)}.npz"
        out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out, left=clip[:, LEFT, :], right=clip[:, RIGHT, :], digit=d, person=self.name)
        self.saved.append(out)
        self.counts[d] += 1
        if self.photos:
            photo = self.dir / "photos" / f"{d}.jpg"
            if not photo.exists():  # keep the first one; delete the file to take another
                photo.parent.mkdir(parents=True, exist_ok=True)
                self.cv2.imwrite(str(photo), bgr)

    def undo(self):
        if not self.saved:
            return
        last = self.saved.pop()
        d = last.parent.name
        last.unlink(missing_ok=True)
        self.counts[d] -= 1
        self.target = d  # do that digit again
        self.armed = True

    def step(self, lm: np.ndarray, bgr: np.ndarray, now: float):
        if self.paused or self.target is None:
            return
        shape = shape_of(lm)
        if shape is None:
            self.buf, self.still_since, self.armed = [], 0.0, True  # hand gone: ready for a fresh try
            return
        if not self.armed:
            if self.ref is None or np.abs(shape - self.ref).mean() > MOVED:
                self.armed = True
            return
        prev = shape_of(self.buf[-1]) if self.buf else None
        if prev is None or np.abs(shape - prev).mean() > STILL:
            self.buf, self.still_since = [lm], now
            return
        self.buf.append(lm)
        if now - self.still_since >= HOLD_S:
            self.save(self.buf, bgr)
            self.ref, self.armed, self.buf = shape, False, []
            self.flash_until = now + 0.5
            self.target = self.next_target()

    def run(self, camera: int):
        cv2 = self.cv2
        cap = cv2.VideoCapture(camera, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(camera)
        if not cap.isOpened():
            cap = cv2.VideoCapture(camera)
        if not cap.isOpened():
            raise SystemExit(f"Could not open camera {camera}. Try --camera 1.")
        win = "Record digits"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("The camera stopped sending frames.")
                    break
                now = time.perf_counter()
                lm, res = self.extractor.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if self.left:
                    lm = left_handed(lm)
                raw = frame.copy()  # the photo shows the signer as a viewer facing them sees them
                self.step(lm, raw, now)
                self.extractor.draw(frame, res)
                cv2.imshow(win, self.render(cv2.flip(frame, 1), now))
                k = cv2.waitKey(1) & 0xFF
                if k in (ord("q"), 27) or self.target is None:
                    break
                if k == ord(" "):
                    self.paused = not self.paused
                elif k == ord("s"):
                    self.target = self.next_target()
                elif k == ord("x"):
                    self.undo()
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.extractor.close()
        total = sum(self.counts.values())
        print(f"\n{self.name}: {total} samples in {self.dir}")
        print("  " + "  ".join(f"{d}:{self.counts[d]}" for d in DIGITS))
        print("Next: uv run train-digits")

    def render(self, view: np.ndarray, now: float) -> np.ndarray:
        cv2 = self.cv2
        h = 720
        view = cv2.resize(view, (round(view.shape[1] * h / view.shape[0]), h))
        if now < self.flash_until:
            cv2.rectangle(view, (0, 0), (view.shape[1] - 1, h - 1), GREEN, 18)
        panel = np.full((h, PANEL_W, 3), 28, np.uint8)
        put = lambda s, y, c=WHITE, sc=0.6, t=1: cv2.putText(panel, s, (16, y), cv2.FONT_HERSHEY_SIMPLEX, sc, c, t, cv2.LINE_AA)
        put(f"RECORD DIGITS - {self.name}", 34, AMBER, 0.7, 2)
        if self.target is None:
            put("All done!", 120, GREEN, 1.2, 3)
        else:
            put("Make this number and hold still:", 80, GREY, 0.55)
            put(self.target, 250, AMBER, 6, 12)
            if self.paused:
                put("PAUSED  [Space]", 310, RED, 0.8, 2)
            elif not self.armed:
                put("Saved. Move your hand, then again.", 310, GREEN, 0.6, 2)
            elif self.buf:
                put(f"Hold... {min(1.0, (now - self.still_since) / HOLD_S):.0%}", 310, GREEN, 0.8, 2)
            else:
                put("Show your hand", 310, GREY, 0.8, 2)
        y = 380
        for i, d in enumerate(DIGITS):  # two columns: 0-4 and 5-9
            x = 16 if i < 5 else 200
            cv2.putText(panel, f"{d}: {self.counts[d]:3}/{self.rounds}", (x, y + (i % 5) * 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, GREEN if self.counts[d] >= self.rounds else WHITE, 1, cv2.LINE_AA)
        put("[Space] pause  [S] skip  [X] undo  [Q] quit", h - 20, GREY, 0.45)
        return np.concatenate([view, panel], axis=1)


def main():
    ap = argparse.ArgumentParser(description="Record digit hand shapes for the handshape model.")
    ap.add_argument("--name", required=True, help="who is signing (a folder name, e.g. ana)")
    ap.add_argument("--rounds", type=int, default=30, help="samples per digit")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--photos", action="store_true", help="also save one photo per digit (ask the person first)")
    ap.add_argument("--left-handed", action="store_true")
    a = ap.parse_args()
    Recorder(a).run(a.camera)


if __name__ == "__main__":
    main()
