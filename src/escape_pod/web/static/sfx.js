// Owner: Teammate 1 (Game, scenes, widgets)
// Sound effects, made with the Web Audio API: no sound files, so no downloads and no
// licenses to credit. Teammate 2 can swap these for recorded CC0 sounds later; keep the
// three function names so app.js does not change.
//
// Browsers start audio only after a click or a key press on the page. unlockAudio() runs
// on the first one (the player always clicks Start before a game), so the context is
// ready by the time the first sound plays.

let ctx = null;

function audio() {
  if (!ctx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    ctx = new Ctx();
  }
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

export function unlockAudio() {
  const go = () => audio();
  window.addEventListener("pointerdown", go, { once: true, capture: true });
  window.addEventListener("keydown", go, { once: true, capture: true });
}

// One note with a short attack and an exponential fade, so it never clicks.
function tone(a, { freq, start = 0, dur = 0.2, type = "sine", gain = 0.2, slideTo = null }) {
  const t0 = a.currentTime + start;
  const osc = a.createOscillator();
  const amp = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
  amp.gain.setValueAtTime(0.0001, t0);
  amp.gain.exponentialRampToValueAtTime(gain, t0 + 0.015);
  amp.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(amp).connect(a.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.05);
}

/** A module defused or a gate passed: two rising notes (E5 then A5). */
export function playSuccess() {
  const a = audio();
  if (!a) return;
  tone(a, { freq: 659, dur: 0.14, type: "triangle", gain: 0.22 });
  tone(a, { freq: 880, start: 0.11, dur: 0.32, type: "triangle", gain: 0.22 });
}

/** A strike: a low, rough buzz that falls in pitch. */
export function playStrike() {
  const a = audio();
  if (!a) return;
  tone(a, { freq: 150, dur: 0.45, type: "sawtooth", gain: 0.16, slideTo: 80 });
  tone(a, { freq: 156, dur: 0.45, type: "square", gain: 0.07, slideTo: 84 });  // slight detune = harsh
}

/** The bomb is defused: a rising major arpeggio that ends on a held chord. */
export function playVictory() {
  const a = audio();
  if (!a) return;
  [523, 659, 784].forEach((freq, k) => tone(a, { freq, start: k * 0.12, dur: 0.18, type: "triangle", gain: 0.2 }));
  for (const freq of [523, 659, 784, 1047]) tone(a, { freq, start: 0.38, dur: 1.1, type: "triangle", gain: 0.12 });
}
