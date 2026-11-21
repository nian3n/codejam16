// Owner: Teammate 3 (Vision and retrieval)
// Consecutive sign capture: split one long recording into one clip per sign.
//
// The word model reads ONE isolated sign per clip, so the whole job is a clean cut
// between signs. The player marks the cut with a separator that adds no word:
//   - hands down: both hands leave the frame or drop below the waist line, or
//   - the "next" pose: both hands open, fingers up, held still for STOP_HOLD_MS.
// Neither separator ever reaches the model: the frames that belong to it are cut
// off the clip. No game word is two still open hands (FINISH shakes them, the
// digit 5 is one hand), so the pose cannot end a real sign by mistake.
//
// Pure logic, no DOM: the page feeds MediaPipe Holistic results in, and gets
// events out. tests/test_sequence.py runs it in Node with synthetic hands.

export const CFG = {
  ARM_MS: 1000,          // after Space: time to set up the hands before recording starts
  STOP_HOLD_MS: 500,     // the "next" pose must be held this still for this long
  DOWN_MS: 150,          // hands down this long ends a sign
  MIN_SIGN_MS: 300,      // shorter clips are noise (a twitch), dropped
  MAX_SIGN_MS: 3000,     // longer clips are not one sign: shown as "unclear"
  MAX_FRAMES: 75,        // the server's limit per clip (practice.py MAX_FRAMES)
  STILL_SPEED: 0.35,     // hand speed (image heights per second) under which a hand counts as still
  FINGER_OPEN: 1.15,     // a finger is straight when tip-to-wrist > this x knuckle(PIP)-to-wrist
  LOWER_SPEED: 0.6,      // wrists falling faster than this (image heights per second) = hands going to rest
  PRE_ROLL: 2,           // frames kept from before a sign starts, so its first motion is in the clip
};

const FINGERS = [[8, 6, 5], [12, 10, 9], [16, 14, 13], [20, 18, 17]];  // [tip, pip, mcp]
const L_SHOULDER = 11, R_SHOULDER = 12, L_HIP = 23, R_HIP = 24;

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const seen = (p) => p && Number.isFinite(p.x) && Number.isFinite(p.y) && (p.visibility == null || p.visibility >= 0.5);

/** The y below which a hand counts as "down" (MediaPipe y grows downward). */
export function waistY(pose) {
  if (pose && seen(pose[L_HIP]) && seen(pose[R_HIP])) return (pose[L_HIP].y + pose[R_HIP].y) / 2;
  if (pose && seen(pose[L_SHOULDER]) && seen(pose[R_SHOULDER])) {
    // At a desk the hips are often off screen: estimate the waist from the shoulders.
    const sy = (pose[L_SHOULDER].y + pose[R_SHOULDER].y) / 2;
    return Math.min(0.92, sy + 1.3 * Math.abs(pose[L_SHOULDER].x - pose[R_SHOULDER].x));
  }
  return 0.92;
}

/** The hands that are visible and above the waist line. */
export function raisedHands(r) {
  const wy = waistY(r.poseLandmarks);
  return [r.leftHandLandmarks, r.rightHandLandmarks].filter((h) => h?.length === 21 && seen(h[0]) && h[0].y < wy);
}

/** All four fingers straight and pointing up. The thumb is ignored: it varies too much. */
export function isOpenHand(h) {
  return FINGERS.every(([tip, pip, mcp]) =>
    dist(h[tip], h[0]) > CFG.FINGER_OPEN * dist(h[pip], h[0]) && h[tip].y < h[mcp].y);
}

/** Both hands raised and open: the shape of the "next" pose (stillness is checked over time). */
export function isNextShape(r) {
  const up = raisedHands(r);
  return up.length === 2 && up.every(isOpenHand);
}

function handSpeed(prev, cur, dtMs) {
  // Mean wrist + fingertip movement of the hands seen in both frames, per second.
  if (!prev || dtMs <= 0) return Infinity;
  let sum = 0, n = 0;
  for (const key of ["leftHandLandmarks", "rightHandLandmarks"]) {
    const a = prev[key], b = cur[key];
    if (a?.length !== 21 || b?.length !== 21) continue;
    for (const i of [0, 4, 8, 12, 16, 20]) { sum += dist(a[i], b[i]); n++; }
  }
  return n ? (sum / n) * (1000 / dtMs) : Infinity;
}

function wristFall(prev, cur, dtMs) {
  // Mean downward wrist speed (positive = falling), per second.
  if (!prev || dtMs <= 0) return 0;
  let sum = 0, n = 0;
  for (const key of ["leftHandLandmarks", "rightHandLandmarks"]) {
    const a = prev[key]?.[0], b = cur[key]?.[0];
    if (!seen(a) || !seen(b)) continue;
    sum += b.y - a.y; n++;
  }
  return n ? (sum / n) * (1000 / dtMs) : 0;
}

/**
 * Phases: "idle" -> start() -> "arming" (ARM_MS) -> "ready" -> "signing" -> (separator)
 * -> "ready" or "next" (pose still held) -> ... -> stop() -> "idle".
 * push() and stop() return events: {type: "phase", phase} and
 * {type: "clip", frames: [payload...], ms, unclear}.
 */
export class Sequencer {
  constructor(cfg = CFG) {
    this.cfg = cfg;
    this.phase = "idle";
    this.armUntil = 0;
    this.seg = [];          // {t, payload} of the sign being recorded
    this.recent = [];       // the last PRE_ROLL frames while ready
    this.prev = null;       // the previous frame's results and time, for speed
    this.downSince = null;  // time the hands went down (during a sign)
    this.openSince = null;  // time the hands first took the "next" shape (continuous)
    this.stillSince = null; // time the "next" shape became still
  }

  start(t) {
    this.reset();
    this.phase = "arming";
    this.armUntil = t + this.cfg.ARM_MS;
    return [{ type: "phase", phase: "arming" }];
  }

  stop() {
    const out = this.phase === "signing" ? this.close(this.seg) : [];
    this.reset();
    this.phase = "idle";
    return [...out, { type: "phase", phase: "idle" }];
  }

  reset() {
    this.seg = []; this.recent = []; this.prev = null;
    this.downSince = this.openSince = this.stillSince = null;
  }

  setPhase(phase, out) {
    if (this.phase !== phase) { this.phase = phase; out.push({ type: "phase", phase }); }
  }

  close(frames) {
    if (frames.length < 2) return [];
    const ms = frames[frames.length - 1].t - frames[0].t;
    if (ms < this.cfg.MIN_SIGN_MS) return [];
    const unclear = ms > this.cfg.MAX_SIGN_MS || frames.length > this.cfg.MAX_FRAMES;
    return [{ type: "clip", frames: unclear ? [] : frames.map((f) => f.payload), ms, unclear }];
  }

  push(t, r, payload) {
    const out = [];
    if (this.phase === "idle") return out;
    if (this.phase === "arming") {
      if (t < this.armUntil) return out;
      this.setPhase("ready", out);
    }
    const up = raisedHands(r).length;
    const shape = isNextShape(r);
    const speed = this.prev ? handSpeed(this.prev.r, r, t - this.prev.t) : Infinity;
    const falling = this.prev ? wristFall(this.prev.r, r, t - this.prev.t) > this.cfg.LOWER_SPEED : false;
    this.prev = { r, t };

    // Track the separators continuously, whatever the phase.
    this.downSince = up === 0 ? (this.downSince ?? t) : null;
    this.openSince = shape ? (this.openSince ?? t) : null;
    // Any motion restarts the hold: the pose counts only after STOP_HOLD_MS of unbroken stillness.
    this.stillSince = shape && speed < this.cfg.STILL_SPEED ? (this.stillSince ?? t) : null;
    const nextHeld = this.stillSince != null && t - this.stillSince >= this.cfg.STOP_HOLD_MS;
    const frame = { t, payload };

    // Open hands that MOVE are a sign (FINISH shakes two open hands), not the pose.
    const moving = speed >= this.cfg.STILL_SPEED;
    if (this.phase === "ready") {
      // Hands on their way down to rest never start a sign.
      if (up > 0 && (!shape || moving) && !falling) {
        this.seg = [...this.recent, frame];
        this.recent = [];
        this.setPhase("signing", out);
      } else {
        this.recent = [...this.recent, frame].slice(-this.cfg.PRE_ROLL);
      }
    } else if (this.phase === "signing") {
      this.seg.push(frame);
      if (this.downSince != null && t - this.downSince >= this.cfg.DOWN_MS) {
        out.push(...this.close(this.seg.filter((f) => f.t < this.downSince)));
        this.seg = [];
        this.setPhase("ready", out);
      } else if (nextHeld) {
        // Cut from the moment the hands took the open shape: the pose is not part of the sign.
        out.push(...this.close(this.seg.filter((f) => f.t < this.openSince)));
        this.seg = [];
        this.setPhase("next", out);
      }
    } else if (this.phase === "next") {
      if (!shape || moving) this.setPhase("ready", out);  // the next frame with raised hands starts a sign
    }
    return out;
  }
}
