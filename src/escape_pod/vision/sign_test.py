# Owner: Teammate 3 (Vision and retrieval)
"""Sign-model test bench: sign to the webcam, see what the model thinks.

    uv run sign-test [--camera 0] [--target] [--set pets_farm] [--mirror] [--left-handed]

Keys (in the video window):
  T        target mode on/off: the tool asks for a word, you sign it, it scores you
  N        target mode: skip this word (not scored)
  X        undo the last scored attempt (you fumbled the sign)
  A / Z    next / previous allowed set (all 250, game words, one puzzle's words)
  Space    manual capture: 3-2-1, then 2.5 s of recording (if auto mode misses signs)
  M        mirror the input frame before MediaPipe (test both, spec §6.3 check 2)
  H        left-handed mode: mirror landmarks and swap hands (spec §6.3 check 4)
  Q / Esc  quit and print the report

Every attempt goes to logs/sign-test-<time>.jsonl: the guesses, settings and latency.
No images and no landmarks are saved (spec rule 8).
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np

from escape_pod import config
from escape_pod.puzzles.engine import load_pool
from escape_pod.vision.landmarks import Extractor, left_handed
from escape_pod.vision.recognizer import Guess, rank
from escape_pod.vision.segmenter import Segmenter
from escape_pod.vision.word_model import WordModel

PANEL_W = 430
VIEW_H = 720
GREEN, RED, AMBER, GREY, WHITE = (90, 220, 120), (70, 70, 240), (40, 190, 255), (150, 150, 150), (240, 240, 240)


def allowed_sets(model_glosses: set[str]) -> list[tuple[str, set[str] | None]]:
    """The choices the recognizer may pick from. A puzzle set = its pool + core signs,
    like the Beginner level (spec §6.3)."""
    core = set(config.CORE_SIGNS)
    pools = {s.id: set(s.pool) for s in load_pool().values() if s.widget != "keypad"}
    game = set().union(*pools.values()) | core
    sets: list[tuple[str, set[str] | None]] = [("all 250", None), ("game words", game & model_glosses)]
    sets += [(pid, (pool | core) & model_glosses) for pid, pool in sorted(pools.items())]
    return sets


class Bench:
    def __init__(self, args):
        import cv2

        self.cv2 = cv2
        print("Loading the sign model...")
        self.model = WordModel()
        print("Loading MediaPipe Holistic...")
        self.extractor = Extractor()
        self.sets = allowed_sets(set(self.model.glosses))
        names = [n for n, _ in self.sets]
        self.set_i = names.index(args.set) if args.set in names else 0
        self.mirror_input = args.mirror or config.MIRROR_INPUT
        self.left = args.left_handed or config.LEFT_HANDED
        self.target_mode = args.target
        self.target: str | None = None
        self.seg = Segmenter()
        self.pool = ThreadPoolExecutor(max_workers=1)  # recognition runs off the camera loop
        self.pending: Future | None = None
        self.last: dict | None = None      # last result shown on screen
        self.scored: list[dict] = []       # target-mode attempts
        self.manual_until = 0.0            # manual capture: end time of the recording window
        self.countdown_until = 0.0         # manual capture: end time of the 3-2-1
        self.manual_frames: list[np.ndarray] = []
        self.fps = 30.0
        config.LOGS_DIR.mkdir(exist_ok=True)
        self.log_path = config.LOGS_DIR / f"sign-test-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
        self.log = open(self.log_path, "a", encoding="utf-8")
        if self.target_mode:
            self.next_target()

    # ------------------------------------------------------------------ helpers
    @property
    def allowed(self) -> set[str] | None:
        return self.sets[self.set_i][1]

    def next_target(self):
        words = sorted((self.allowed or set(self.model.glosses)) - set(config.CORE_SIGNS))
        self.target = random.choice(words) if words else None

    def submit(self, clip: np.ndarray, how: str):
        if self.pending is not None and not self.pending.done():
            return  # still busy with the last clip; drop this one rather than queue up
        ended = time.perf_counter()
        allowed, target, set_name = self.allowed, self.target if self.target_mode else None, self.sets[self.set_i][0]

        def job():
            logits = self.model.scores(clip)
            return {
                "how": how, "frames": len(clip), "target": target, "set": set_name,
                "guesses": rank(logits, allowed, 5),
                "raw": rank(logits, None, 3),  # what it would say with all 250 allowed
                "latency_ms": round((time.perf_counter() - ended) * 1000),
                "mirror_input": self.mirror_input, "left_handed": self.left,
            }

        self.pending = self.pool.submit(job)

    def collect(self):
        if self.pending is None or not self.pending.done():
            return
        r = self.pending.result()
        self.pending = None
        self.last = r
        rec = {**r, "t": round(time.time(), 2),
               "guesses": [[g.gloss, round(g.score, 4)] for g in r["guesses"]],
               "raw": [[g.gloss, round(g.score, 4)] for g in r["raw"]]}
        if r["target"]:
            top = [g.gloss for g in r["guesses"]]
            rec["top1"], rec["top3"] = top[:1] == [r["target"]], r["target"] in top[:3]
            self.scored.append(rec)
            self.next_target()
        self.log.write(json.dumps(rec) + "\n")
        self.log.flush()

    # ------------------------------------------------------------------ main loop
    def run(self, camera: int):
        cv2 = self.cv2
        cap = cv2.VideoCapture(camera, cv2.CAP_DSHOW) if hasattr(cv2, "CAP_DSHOW") else cv2.VideoCapture(camera)
        if not cap.isOpened():
            cap = cv2.VideoCapture(camera)
        if not cap.isOpened():
            raise SystemExit(f"Could not open camera {camera}. Try --camera 1.")
        cv2.namedWindow("Escape Pod sign test", cv2.WINDOW_NORMAL)
        prev = time.perf_counter()
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("The camera stopped sending frames.")
                    break
                now = time.perf_counter()
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(1e-3, now - prev))
                prev = now
                self.seg.fps = self.fps  # segmenter thresholds are in seconds, so they follow the real fps

                img = cv2.flip(frame, 1) if self.mirror_input else frame
                lm, res = self.extractor.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                if self.left:
                    lm = left_handed(lm)
                self.extractor.draw(img, res)
                view = img if self.mirror_input else cv2.flip(img, 1)  # the player always sees a mirror

                if self.countdown_until and now >= self.countdown_until:
                    self.countdown_until, self.manual_until, self.manual_frames = 0.0, now + config.MANUAL_CAPTURE_S, []
                if self.manual_until:
                    self.manual_frames.append(lm)
                    if now >= self.manual_until:
                        self.manual_until = 0.0
                        self.submit(np.stack(self.manual_frames), "manual")
                elif not self.countdown_until:
                    clip = self.seg.push(lm)
                    if clip is not None:
                        self.submit(clip, "auto")
                self.collect()

                cv2.imshow("Escape Pod sign test", self.render(view, now))
                if not self.key(cv2.waitKey(1) & 0xFF, now):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self.extractor.close()
            self.pool.shutdown(wait=True)
            self.collect()
            self.report()
            self.log.close()

    def key(self, k: int, now: float) -> bool:
        if k in (ord("q"), 27):
            return False
        if k == ord("t"):
            self.target_mode = not self.target_mode
            if self.target_mode:
                self.next_target()
        elif k == ord("n") and self.target_mode:
            self.next_target()
        elif k == ord("x") and self.scored:
            undone = self.scored.pop()
            self.log.write(json.dumps({"undo": undone["t"]}) + "\n")
        elif k in (ord("a"), ord("z")):
            self.set_i = (self.set_i + (1 if k == ord("a") else -1)) % len(self.sets)
            if self.target_mode:
                self.next_target()
        elif k == ord(" ") and not (self.manual_until or self.countdown_until):
            self.seg.reset()
            self.countdown_until = now + 3.0
        elif k == ord("m"):
            self.mirror_input = not self.mirror_input
        elif k == ord("h"):
            self.left = not self.left
        return True

    # ------------------------------------------------------------------ drawing
    def render(self, view: np.ndarray, now: float) -> np.ndarray:
        cv2 = self.cv2
        # Most webcams give 640x480; scale up so the panel has room for every line.
        h = VIEW_H
        view = cv2.resize(view, (round(view.shape[1] * h / view.shape[0]), h))
        panel = np.full((h, PANEL_W, 3), 28, np.uint8)
        y = 30

        def text(s, color=WHITE, scale=0.6, dy=26, thick=1):
            nonlocal y
            cv2.putText(panel, s, (16, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)
            y += dy

        name, allowed = self.sets[self.set_i]
        text("ESCAPE POD - sign test", AMBER, 0.7, 34, 2)
        text(f"Allowed: {name} ({len(allowed) if allowed else 250})  [A/Z]", GREY, 0.5)
        text(f"Mirror input: {'on' if self.mirror_input else 'off'} [M]   Left-handed: {'on' if self.left else 'off'} [H]", GREY, 0.5)
        text(f"{self.fps:4.1f} fps", GREY, 0.5, 34)

        if self.countdown_until:
            text(f"Get ready... {int(self.countdown_until - now) + 1}", AMBER, 0.9, 40, 2)
        elif self.manual_until:
            text(f"RECORDING {self.manual_until - now:.1f}s", RED, 0.9, 40, 2)
        elif self.pending is not None:
            text("Thinking...", AMBER, 0.9, 40, 2)
        else:
            sig = self.seg.state == "signing"
            text("SIGNING" if sig else "Waiting for a sign", GREEN if sig else GREY, 0.9, 40, 2)

        if self.target_mode:
            text("Sign this word:", GREY, 0.55, 50)
            text((self.target or "-").upper(), AMBER, 1.3, 44, 3)
            if self.scored:
                n = len(self.scored)
                t1 = sum(r["top1"] for r in self.scored)
                t3 = sum(r["top3"] for r in self.scored)
                text(f"Score: top-1 {t1}/{n} ({100 * t1 // n}%)  top-3 {t3}/{n}", WHITE, 0.55, 34)
            text("[N] skip  [X] undo last  [T] free mode", GREY, 0.45, 34)
        else:
            text("Free mode: sign anything.  [T] target mode", GREY, 0.5, 34)

        r = self.last
        if r:
            hdr = f"Last ({r['how']}, {r['frames']} frames, {r['latency_ms']} ms)"
            if r["target"]:
                top = [g.gloss for g in r["guesses"]]
                hit = top[:1] == [r["target"]]
                hdr += f"  target {r['target'].upper()}: {'HIT' if hit else 'top-3' if r['target'] in top[:3] else 'MISS'}"
            text(hdr, GREY, 0.45, 26)
            for i, g in enumerate(r["guesses"]):
                self.bar(panel, y - 16, g, i == 0)
                y += 30
            y += 6
            text("All 250 would say: " + ", ".join(f"{g.gloss} {g.score:.0%}" for g in r["raw"]), GREY, 0.45)

        text("[Space] manual capture   [Q] quit", GREY, 0.45, 0)
        return np.concatenate([view, panel], axis=1)

    def bar(self, panel, y: int, g: Guess, best: bool):
        cv2 = self.cv2
        w = int((PANEL_W - 200) * g.score)
        cv2.rectangle(panel, (150, y), (150 + max(2, w), y + 18), GREEN if best else (90, 110, 90), -1)
        cv2.putText(panel, g.gloss, (16, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 2 if best else 1, cv2.LINE_AA)
        cv2.putText(panel, f"{g.score:.0%}", (PANEL_W - 44, y + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------ report
    def report(self):
        print(f"\nLog: {self.log_path}")
        if not self.scored:
            print("No target-mode attempts. Press T in the window to score yourself next time.")
            return
        per = defaultdict(lambda: [0, 0, 0])
        confused = defaultdict(int)
        for r in self.scored:
            p = per[r["target"]]
            p[0] += 1
            p[1] += r["top1"]
            p[2] += r["top3"]
            if not r["top1"] and r["guesses"]:
                confused[(r["target"], r["guesses"][0][0])] += 1
        n = len(self.scored)
        t1 = sum(r["top1"] for r in self.scored)
        t3 = sum(r["top3"] for r in self.scored)
        print(f"\nTarget mode: {n} attempts. top-1 {t1}/{n} ({100 * t1 / n:.0f}%), top-3 {t3}/{n} ({100 * t3 / n:.0f}%)")
        print(f"\n{'gloss':14} tries  top-1  top-3")
        for g, (a, h1, h3) in sorted(per.items(), key=lambda kv: kv[1][1] / kv[1][0]):
            print(f"{g:14} {a:5}  {h1:5}  {h3:5}")
        if confused:
            print("\nMost confused (signed -> model said):")
            for (a, b), c in sorted(confused.items(), key=lambda kv: -kv[1])[:10]:
                print(f"  {a} -> {b}  x{c}")
        summary = {"summary": True, "attempts": n, "top1": t1, "top3": t3,
                   "per_gloss": {g: {"tries": a, "top1": h1, "top3": h3} for g, (a, h1, h3) in per.items()}}
        self.log.write(json.dumps(summary) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Sign to the webcam and see what the ASL model recognizes.")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--target", action="store_true", help="start in target mode (scores you)")
    ap.add_argument("--set", default="all 250", help='allowed set: "all 250", "game words" or a puzzle id like pets_farm')
    ap.add_argument("--mirror", action="store_true", help="mirror the input before MediaPipe")
    ap.add_argument("--left-handed", action="store_true")
    a = ap.parse_args()
    try:
        Bench(a).run(a.camera)
    except FileNotFoundError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
