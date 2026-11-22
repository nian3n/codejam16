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

// A short burst of white noise through a band-pass filter: the "snip" of the cutters.
function noise(a, { start = 0, dur = 0.08, freq = 3000, q = 1.2, gain = 0.3 }) {
  const t0 = a.currentTime + start;
  const len = Math.ceil(a.sampleRate * dur);
  const buf = a.createBuffer(1, len, a.sampleRate);
  const data = buf.getChannelData(0);
  for (let k = 0; k < len; k++) data[k] = (Math.random() * 2 - 1) * (1 - k / len);
  const src = a.createBufferSource();
  src.buffer = buf;
  const band = a.createBiquadFilter();
  band.type = "bandpass";
  band.frequency.value = freq;
  band.Q.value = q;
  const amp = a.createGain();
  amp.gain.value = gain;
  src.connect(band).connect(amp).connect(a.destination);
  src.start(t0);
}

/** A wire is cut: a sharp snip, then the cut end springs away. */
export function playSnip() {
  const a = audio();
  if (!a) return;
  noise(a, { dur: 0.05, freq: 4200, gain: 0.45 });
  tone(a, { freq: 1400, dur: 0.07, type: "square", gain: 0.05, slideTo: 500 });
  noise(a, { start: 0.045, dur: 0.12, freq: 1800, q: 0.8, gain: 0.12 });
}

/** A button, a dial position or a wheel: one short mechanical tick. */
export function playClick() {
  const a = audio();
  if (!a) return;
  noise(a, { dur: 0.025, freq: 2600, q: 2, gain: 0.35 });
  tone(a, { freq: 520, dur: 0.05, type: "triangle", gain: 0.08, slideTo: 300 });
}

/** A switch flips: two ticks close together, the lever leaving one stop and hitting the other. */
export function playToggle() {
  const a = audio();
  if (!a) return;
  noise(a, { dur: 0.02, freq: 1800, q: 2, gain: 0.25 });
  noise(a, { start: 0.045, dur: 0.03, freq: 3200, q: 2, gain: 0.4 });
  tone(a, { freq: 240, start: 0.045, dur: 0.06, type: "triangle", gain: 0.1 });
}

// Every control on the case clicks when pressed. Wires and switches are left out here: they
// play their own sound (playSnip, playToggle) where the cut or the flip is sent.
export function wireControlSounds() {
  document.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    const control = event.target.closest?.("#stage button, #case-lock-stage button");
    if (!control || control.disabled || control.matches(".switch, .cuttable")) return;
    playClick();
  }, { capture: true });
}
