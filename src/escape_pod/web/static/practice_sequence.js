// Owner: Teammate 3 (Vision and retrieval)
// Practice, "Sequence" mode: sign several words in one recording.
//
// Space starts a recording. For CFG.ARM_MS the banner says "get your hands ready",
// then the Sequencer (sequence.js) cuts the stream into one clip per sign at each
// separator (hands down, or both palms held up). Each clip goes to
// POST /api/practice/guess at once, in the background, and becomes a chip with the
// top 3 guesses. The player fixes or deletes chips, then clicks Check.
import { $, el, wordOf } from "./core.js";
import { Sequencer } from "./sequence.js";
import { onPracticeFrame, onPracticeStop, practiceCameraReady, practiceWords } from "./practice.js";

const TARGET_COUNT = 3;
const CORE = new Set(["yes", "no", "finish"]);
const PROMPTS = {
  arming: ["GET YOUR HANDS READY", "Recording starts in 1 second."],
  ready: ["RECORDING", "Sign a word. Then lower your hands, or hold both palms up ✋✋."],
  signing: ["SIGNING…", "Lower your hands or hold both palms up when the sign is done."],
  cooldown: ["✓ GOT IT", "Wait a moment… then sign the next word, or press Space to stop."],
};

const seq = new Sequencer();
let mode = "one";
let targets = [];
let chips = [];        // {id, state: "pending" | "done" | "unclear" | "error", guesses, pick, text}
let nextId = 1;
let oneText = "";  // the One word instructions, restored when the player switches back

const banner = $("#seq-banner");
const record = $("#seq-record");

function setMode(m) {
  mode = m;
  stopRecording();
  for (const node of document.querySelectorAll("#practice .one-only")) node.classList.toggle("hidden", m !== "one");
  for (const node of document.querySelectorAll("#practice .seq-only")) node.classList.toggle("hidden", m !== "seq");
  $("#mode-one").classList.toggle("on", m === "one");
  $("#mode-seq").classList.toggle("on", m === "seq");
  $("#mode-one").setAttribute("aria-pressed", String(m === "one"));
  $("#mode-seq").setAttribute("aria-pressed", String(m === "seq"));
  $("#practice-result").classList.add("hidden");
  const text = $("#practice-instructions");
  if (m === "seq") {
    oneText = text.textContent;
    text.textContent = `Sign ${TARGET_COUNT} words in one recording. Each word becomes a chip with the model's top 3 guesses.`;
  } else if (oneText) text.textContent = oneText;
  if (m === "seq" && !targets.length) newTargets();
  render();
}

function newTargets() {
  const pool = practiceWords().filter((g) => !CORE.has(g));
  targets = [];
  while (pool.length && targets.length < TARGET_COUNT) targets.push(pool.splice(Math.floor(Math.random() * pool.length), 1)[0]);
  $("#seq-targets").textContent = targets.map((g) => wordOf(g).toUpperCase()).join(" · ") || "(loading words…)";
  clearChips();
}

function clearChips() {
  chips = [];
  $("#practice-result").classList.add("hidden");
  render();
}

function showBanner(phase) {
  const prompt = PROMPTS[phase];
  banner.classList.toggle("hidden", !prompt);
  banner.dataset.phase = phase;
  if (prompt) banner.replaceChildren(el("b", { text: prompt[0] }), el("span", { text: prompt[1] }));
}

function startRecording() {
  if (!practiceCameraReady() || seq.phase !== "idle") return;
  handle(seq.start(performance.now()));
  render();
}

function stopRecording() {
  if (seq.phase === "idle") return;
  handle(seq.stop());
  render();
}

function handle(events) {
  for (const e of events) {
    if (e.type === "phase") showBanner(e.phase);
    else if (e.type === "clip") addClip(e);
  }
}

function addClip(e) {
  const chip = { id: nextId++, state: e.unclear ? "unclear" : "pending", guesses: [], pick: null, text: "" };
  chips.push(chip);
  render();
  if (e.unclear) return;
  // Score in the background: the player keeps signing the next word.
  fetch("/api/practice/guess", { method: "POST", body: new Blob(e.frames, { type: "application/octet-stream" }),
    headers: { "Content-Type": "application/octet-stream" } })
    .then(async (r) => {
      const body = await r.json();
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not score this sign.");
      chip.guesses = body.guesses;
      chip.pick = body.guesses[0]?.gloss ?? null;
      chip.state = chip.pick ? "done" : "unclear";
    })
    .catch((err) => { chip.state = "error"; chip.text = err.message; })
    .finally(render);
}

function chipView(chip, i) {
  const remove = el("button", { class: "chip-x", text: "✕", title: "Delete this sign", "aria-label": `Delete sign ${i + 1}`,
    onclick: () => { chips = chips.filter((c) => c !== chip); render(); } });
  const head = el("span", { class: "chip-n", text: `#${i + 1}` });
  if (chip.state === "pending") return el("div", { class: "chip pending" }, head, el("span", { class: "chip-main", text: "…" }), remove);
  if (chip.state !== "done") {
    const text = chip.state === "unclear" ? "Unclear, sign again" : chip.text;
    return el("div", { class: "chip bad" }, head, el("span", { class: "chip-main", text }), remove);
  }
  const options = chip.guesses.map((g) => el("button", {
    class: "chip-opt" + (g.gloss === chip.pick ? " on" : ""),
    text: `${wordOf(g.gloss).toUpperCase()} ${Math.round(g.score * 100)}%`,
    title: "Pick this guess",
    onclick: () => { chip.pick = g.gloss; render(); },
  }));
  return el("div", { class: "chip" }, head, el("div", { class: "chip-opts" }, ...options), remove);
}

function check() {
  const picks = chips.filter((c) => c.state === "done").map((c) => c.pick);
  const marks = targets.map((g, i) => `${picks[i] === g ? "✓" : "✗"} ${wordOf(g).toUpperCase()}` +
    (picks[i] && picks[i] !== g ? ` (you: ${wordOf(picks[i]).toUpperCase()})` : picks[i] ? "" : " (missing)"));
  const right = targets.filter((g, i) => picks[i] === g).length;
  const result = $("#practice-result");
  result.textContent = `${right} / ${targets.length} right · ${marks.join(" · ")}` +
    (picks.length > targets.length ? ` · ${picks.length - targets.length} extra sign(s)` : "");
  result.classList.toggle("approved", right === targets.length && picks.length === targets.length);
  result.classList.remove("hidden");
}

function render() {
  if (mode !== "seq") { banner.classList.add("hidden"); return; }
  if (!targets.length && practiceWords().length) { newTargets(); return; }  // the word list arrived late
  const recording = seq.phase !== "idle";
  record.textContent = recording ? "Stop recording (Space)" : "Start recording (Space)";
  record.classList.toggle("rec", recording);
  record.disabled = !practiceCameraReady();
  if (!recording) banner.classList.add("hidden");
  $("#seq-chips").replaceChildren(...(chips.length ? chips.map(chipView)
    : [el("p", { class: "seq-empty", text: "Your signs show up here, one chip per sign." })]));
  const busy = chips.some((c) => c.state === "pending");
  $("#seq-check").disabled = recording || busy || !chips.some((c) => c.state === "done");
  $("#seq-clear").disabled = recording || !chips.length;
}

export function bindSequence() {
  $("#mode-one").onclick = () => setMode("one");
  $("#mode-seq").onclick = () => setMode("seq");
  $("#seq-new").onclick = () => newTargets();
  $("#seq-clear").onclick = () => clearChips();
  $("#seq-check").onclick = () => check();
  record.onclick = () => (seq.phase === "idle" ? startRecording() : stopRecording());
  onPracticeFrame((landmarks, pack) => {
    if (!landmarks) { render(); return; }  // the camera just became ready
    if (mode !== "seq" || seq.phase === "idle") return;
    // Pack every frame, even while arming: the frame that ends the arming time can open a clip.
    handle(seq.push(performance.now(), landmarks, pack(landmarks)));
  });
  onPracticeStop(() => { stopRecording(); setTimeout(render); });
  document.addEventListener("keydown", (e) => {
    if (e.code !== "Space" || mode !== "seq" || $("#practice").classList.contains("hidden")) return;
    if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target?.tagName)) return;
    e.preventDefault();  // no page scroll and no click on a focused button
    if (e.repeat) return;
    if (seq.phase === "idle") startRecording(); else stopRecording();
  });
}
