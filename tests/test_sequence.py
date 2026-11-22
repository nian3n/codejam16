# Owner: Teammate 3 (Vision and retrieval)
"""Consecutive sign capture (static/sequence.js), run in Node with synthetic hands.

Each scenario is a list of steps at 30 fps. The JS side builds MediaPipe-like
results (two 21-point hands and shoulders) and returns the events.
"""
import json
import shutil
import subprocess

import pytest

import config

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
SEQUENCE_URL = (config.STATIC_DIR / "sequence.js").as_uri()

HARNESS = r"""
import { Sequencer, isOpenHand, isNextShape } from "%(url)s";

// A hand with its wrist at (cx, cy). open: four straight fingers pointing up.
function hand(cx, cy, open) {
  const p = [{ x: cx, y: cy, z: 0 }];
  for (let t = 1; t <= 4; t++) p.push({ x: cx - 0.04 + 0.01 * t, y: cy - 0.02 * t, z: 0 });  // thumb
  for (let f = 0; f < 4; f++) {
    const x = cx - 0.03 + 0.02 * f, mcpY = cy - 0.06;
    p.push({ x, y: mcpY, z: 0 });                               // mcp
    p.push({ x, y: mcpY - 0.03, z: 0 });                        // pip
    p.push({ x, y: open ? mcpY - 0.055 : mcpY - 0.01, z: 0 });  // dip
    p.push({ x, y: open ? mcpY - 0.08 : mcpY + 0.01, z: 0 });   // tip: curled below the knuckle
  }
  return p;
}
const pose = Array.from({ length: 33 }, () => ({ x: 0.5, y: 0.5, z: 0, visibility: 0.1 }));
pose[11] = { x: 0.6, y: 0.45, z: 0, visibility: 1 };
pose[12] = { x: 0.4, y: 0.45, z: 0, visibility: 1 };   // waist estimate: 0.45 + 1.3 * 0.2 = 0.71

// Step kinds: rest (no hands), sign (one closed hand circling at the chest),
// next (both open hands still), shake (both open hands shaking, like FINISH),
// lower (both open hands falling from the chest out of the frame).
function frame(kind, i, n) {
  const w = Math.sin(i / 2) * 0.04;
  if (kind === "rest") return { poseLandmarks: pose };
  if (kind === "sign") return { poseLandmarks: pose, rightHandLandmarks: hand(0.45 + w, 0.55 + w, false) };
  if (kind === "next") return { poseLandmarks: pose, leftHandLandmarks: hand(0.65, 0.5, true), rightHandLandmarks: hand(0.35, 0.5, true) };
  if (kind === "shake") return { poseLandmarks: pose, leftHandLandmarks: hand(0.62 + w, 0.5, true), rightHandLandmarks: hand(0.38 - w, 0.5, true) };
  if (kind === "lower") {
    const y = 0.5 + (0.5 * (i + 1)) / n;   // 0.5 -> 1.0 over the step
    return { poseLandmarks: pose, leftHandLandmarks: hand(0.65, y, true), rightHandLandmarks: hand(0.35, y, true) };
  }
  throw new Error(kind);
}

const scenarios = JSON.parse(process.argv[1]);
const results = {};
for (const [name, steps] of Object.entries(scenarios)) {
  const seq = new Sequencer();
  let t = 0, id = 0;
  const events = [...seq.start(0, { trimLongSigns: name === "gate" })];
  for (const [kind, ms] of steps) {
    if (kind === "stop") { events.push(...seq.stop()); continue; }
    const n = Math.round(ms / (1000 / 30));
    for (let i = 0; i < n; i++, t += 1000 / 30) events.push(...seq.push(t, frame(kind, i, n), `${kind}#${id++}`));
  }
  results[name] = events.map((e) => e.type === "clip"
    ? { clip: e.frames.length, ms: Math.round(e.ms), unclear: e.unclear, kinds: [...new Set(e.frames.map((f) => f.split("#")[0]))] }
    : e.phase);
}
results.shapes = {
  open: isOpenHand(hand(0.5, 0.5, true)), closed: isOpenHand(hand(0.5, 0.5, false)),
  next: isNextShape(frame("next", 0, 1)), oneHand: isNextShape(frame("sign", 0, 1)),
};
console.log(JSON.stringify(results));
"""


def run(scenarios: dict) -> dict:
    script = HARNESS % {"url": SEQUENCE_URL}
    assert NODE is not None
    out = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps(scenarios)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def clips(events):
    return [e for e in events if isinstance(e, dict)]


def test_hand_shapes():
    assert run({})["shapes"] == {"open": True, "closed": False, "next": True, "oneHand": False}


def test_nothing_is_recorded_during_the_one_second_setup():
    r = run({"s": [["sign", 900], ["rest", 300], ["stop", 0]]})["s"]
    assert clips(r) == [] and r[0] == "arming"


def test_hands_down_ends_a_sign_and_the_rest_is_not_in_the_clip():
    r = run({"s": [["rest", 1100], ["sign", 1000], ["rest", 400]]})["s"]
    assert r[:3] == ["arming", "ready", "signing"]
    (c,) = clips(r)
    assert c["kinds"] == ["rest", "sign"] or c["kinds"] == ["sign"]  # pre-roll may keep 2 rest frames
    assert 950 <= c["ms"] <= 1150 and not c["unclear"]
    assert r[-1] == "cooldown"  # 0.4 s after the sign: still inside the 1 s cooldown


def test_the_next_pose_splits_signs_and_never_reaches_a_clip():
    r = run({"s": [["rest", 1100], ["sign", 800], ["next", 1600], ["sign", 900], ["stop", 0]]})["s"]
    got = clips(r)
    assert len(got) == 2
    assert all("next" not in c["kinds"] for c in got)
    assert "cooldown" in r  # the banner shows the player that the sign was taken


def test_many_signs_in_a_row():
    steps = [["rest", 1100]] + [s for _ in range(4) for s in (["sign", 900], ["next", 1600])] + [["stop", 0]]
    assert len(clips(run({"s": steps})["s"])) == 4


def test_shaking_open_hands_are_a_sign_not_the_pose():
    got = clips(run({"s": [["rest", 1100], ["shake", 900], ["rest", 400]]})["s"])
    assert len(got) == 1 and got[0]["kinds"][-1] == "shake"


def test_a_twitch_is_dropped_and_a_long_stretch_is_unclear():
    r = run({"twitch": [["rest", 1100], ["sign", 150], ["rest", 400]],
             "long": [["rest", 1100], ["sign", 4000], ["rest", 400]]})
    assert clips(r["twitch"]) == []
    (c,) = clips(r["long"])
    assert c["unclear"] and c["clip"] == 0


def test_gate_records_a_held_sign_once_and_allows_the_same_sign_again():
    r = run({"gate": [["rest", 1100], ["sign", 5000], ["rest", 1400], ["sign", 800], ["rest", 500]]})
    first, second = clips(r["gate"])
    assert first["clip"] == 75 and not first["unclear"]
    assert second["clip"] > 0 and not second["unclear"]


def test_lowering_the_hands_after_the_pose_records_nothing():
    r = run({"s": [["rest", 1100], ["sign", 800], ["next", 700], ["lower", 400], ["rest", 400], ["stop", 0]]})["s"]
    assert len(clips(r)) == 1


def test_a_short_dropout_does_not_split_a_sign():
    # The hands leave the frame for 0.2 s in the middle of a sign: still one word.
    r = run({"s": [["rest", 1100], ["sign", 600], ["rest", 200], ["sign", 600], ["rest", 500], ["stop", 0]]})["s"]
    assert len(clips(r)) == 1


def test_no_new_word_within_one_second_after_a_sign():
    # Hands drop (the sign ends), then come back at once: the cooldown ignores them.
    quick = run({"s": [["rest", 1100], ["sign", 800], ["rest", 400], ["sign", 500], ["rest", 600], ["stop", 0]]})["s"]
    assert len(clips(quick)) == 1
    # After the cooldown, the next sign counts.
    later = run({"s": [["rest", 1100], ["sign", 800], ["rest", 1400], ["sign", 800], ["rest", 500], ["stop", 0]]})["s"]
    assert len(clips(later)) == 2
