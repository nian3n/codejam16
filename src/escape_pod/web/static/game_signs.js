// Owner: Teammate 3 (Vision and retrieval)
// The field agent's sign composer in the game: sign to the webcam, check the guesses,
// send them to HQ.
//
// It reads frames from the camera the video call already opened (rtc.js
// localCameraVideo), so there is one camera and one permission prompt. Frames go to
// the hand tracker worker (tracker.js) in this browser. Only landmarks go to the
// server, never video (spec rule 8). The Sequencer (sequence.js, the same one as
// solo practice) cuts the recording into one clip per sign, and each clip goes to
// /api/practice/guess with the words this bomb can show.
//
// Nothing goes to HQ until the agent presses "Send to HQ": that press is the
// confirmation of every chip (spec rule 4). Each chip shows the top 3 guesses, so a
// wrong top guess costs one click, never a strike.
import { $, el, send, store, wordOf } from "./core.js";
import { Sequencer } from "./sequence.js";
import { packLandmarks, startTracker, track, trackerLoaded } from "./tracker.js";
import { localCameraVideo } from "./rtc.js";

const MAX_SIGNS = 12;  // server.py MAX_SIGNS
const CORE = ["yes", "no", "finish"];
const PROMPTS = {
  arming: ["GET YOUR HANDS READY", "Recording starts in 1 second."],
  ready: ["RECORDING", "Sign one word. Then lower your hands, or hold both palms up ✋✋."],
  signing: ["SIGNING…", "Lower your hands or hold both palms up when the sign is done."],
  cooldown: ["✓ GOT IT", "Wait a moment… then sign the next word. Space stops."],
};

const seq = new Sequencer();
let run = 0;           // id of the current recording loop; a new id stops the old loop
let nextId = 1;
let note = "";         // a short status line under the buttons

// Chips live in store.local, so a new game (resetLocal) starts with none.
// {id, state: "pending" | "done" | "unclear" | "error", guesses, pick, text, typed}
const chips = () => (store.local.signChips ??= []);

/**
 * The words the recognizer may choose from. Beginner and Intermediate: every word on
 * this bomb (config.LEVELS allowed_scope "bomb"), never one module's words, because
 * the agent never says which module they sign. Advanced: null, so the server uses all
 * game words.
 */
function allowedWords() {
  const s = store.state;
  if (!s?.bomb || s.level === "advanced") return null;
  return [...new Set([...s.bomb.flatMap((m) => m.pool), ...CORE])];
}

function recording() { return seq.phase !== "idle"; }

export function signComposer() {
  stopRecording();
  note = "";
  const typed = el("input", { placeholder: "Type a sign, press Enter", list: "glosses", autocomplete: "off", id: "type-sign" });
  typed.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const g = typed.value.trim().toLowerCase().replace(/\s+/g, "");
    if (g && chips().length < MAX_SIGNS) chips().push({ id: nextId++, state: "done", guesses: [], pick: g, typed: true });
    typed.value = "";
    renderSignChips();
  });
  const all = [...new Set(store.pages.flatMap((p) => p.glosses))].sort();
  return el("div", { class: "composer sign-composer" },
    el("div", { class: "label", text: "Sign each item on one module to your camera, one sign at a time. Dial: sign the pictures clockwise from the top, then the one the needle points at." }),
    el("div", { class: "seq-banner hidden", id: "game-banner", "aria-live": "polite" }),
    el("div", { class: "sign-buttons" },
      el("button", { class: "btn primary", id: "sign-record", text: "Start signing (Space)", onclick: toggleRecording }),
      el("button", { class: "btn small", id: "sign-clear", text: "Clear", onclick: () => { store.local.signChips = []; renderSignChips(); } })),
    el("div", { class: "label sign-note", id: "sign-note" }),
    el("div", { class: "seq-chips", id: "sign-chips" }),
    el("button", { class: "btn primary", id: "send-signs", text: "Send to HQ", onclick: sendSigns }),
    el("details", { class: "type-instead" },
      el("summary", { text: "No camera? Type the signs instead" }),
      typed,
      el("datalist", { id: "glosses" }, all.map((g) => el("option", { value: g })))));
}

function sendSigns() {
  const picks = chips().filter((c) => c.state === "done" && c.pick).map((c) => c.pick);
  if (!picks.length || chips().some((c) => c.state === "pending")) return;
  stopRecording();
  send({ type: "signs", glosses: picks });
  store.local.signChips = [];
  renderSignChips();
}

function toggleRecording() {
  if (recording()) stopRecording(); else void startRecording();
}

async function startRecording() {
  if (recording() || store.state?.phase !== "playing") return;
  const video = localCameraVideo();
  if (!video) { setNote("Turn your camera on to sign. Or type the signs below."); return; }
  const id = ++run;
  if (!trackerLoaded()) setNote("Loading the hand tracker (only the first time)…");
  try {
    await startTracker();
  } catch (error) {
    setNote(error.message || "The hand tracker could not start. Type the signs below.");
    return;
  }
  if (run !== id) return;
  setNote("");
  handle(seq.start(performance.now()));
  renderSignChips();
  void loop(id);
}

function stopRecording() {
  run++;
  if (recording()) handle(seq.stop());
  renderSignChips();
}

async function loop(id) {
  let last = -1;
  try {
    while (run === id) {
      await new Promise(requestAnimationFrame);
      const video = localCameraVideo();
      if (!video) { stopRecording(); setNote("The camera turned off, so the recording stopped."); return; }
      if (video.currentTime === last || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) continue;
      last = video.currentTime;
      const landmarks = await track(video);
      if (run !== id) return;
      handle(seq.push(performance.now(), landmarks, packLandmarks(landmarks)));
    }
  } catch {
    if (run === id) { stopRecording(); setNote("Hand tracking stopped. Start signing again, or type the signs below."); }
  }
}

function handle(events) {
  for (const e of events) {
    if (e.type === "phase") showBanner(e.phase);
    else if (e.type === "clip") addClip(e);
  }
}

function showBanner(phase) {
  const banner = $("#game-banner");
  if (!banner) return;
  const prompt = PROMPTS[phase];
  banner.classList.toggle("hidden", !prompt);
  banner.dataset.phase = phase;
  if (prompt) banner.replaceChildren(el("b", { text: prompt[0] }), el("span", { text: prompt[1] }));
}

function addClip(e) {
  if (chips().length >= MAX_SIGNS) { setNote(`At most ${MAX_SIGNS} signs per message. Send these first.`); return; }
  const chip = { id: nextId++, state: e.unclear ? "unclear" : "pending", guesses: [], pick: null, text: "" };
  chips().push(chip);
  renderSignChips();
  if (e.unclear) return;
  const words = allowedWords();
  const url = "/api/practice/guess" + (words ? `?words=${encodeURIComponent(words.join(","))}` : "");
  fetch(url, { method: "POST", body: new Blob(e.frames, { type: "application/octet-stream" }),
    headers: { "Content-Type": "application/octet-stream" } })
    .then(async (r) => {
      const body = await r.json();
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not read this sign.");
      chip.guesses = body.guesses;
      chip.pick = body.guesses[0]?.gloss ?? null;
      chip.state = chip.pick ? "done" : "unclear";
    })
    .catch((err) => { chip.state = "error"; chip.text = err.message; })
    .finally(renderSignChips);
}

function setNote(text) {
  note = text;
  const n = $("#sign-note");
  if (n) n.textContent = note;
}

function chipView(chip, i) {
  const remove = el("button", { class: "chip-x", text: "✕", title: "Delete this sign", "aria-label": `Delete sign ${i + 1}`,
    onclick: () => { store.local.signChips = chips().filter((c) => c !== chip); renderSignChips(); } });
  const head = el("span", { class: "chip-n", text: `#${i + 1}` });
  if (chip.state === "pending") return el("div", { class: "chip pending" }, head, el("span", { class: "chip-main", text: "…" }), remove);
  if (chip.state !== "done") {
    const text = chip.state === "unclear" ? "Unclear, sign again" : chip.text;
    return el("div", { class: "chip bad" }, head, el("span", { class: "chip-main", text }), remove);
  }
  if (chip.typed) return el("div", { class: "chip" }, head, el("span", { class: "chip-main", text: `${wordOf(chip.pick).toUpperCase()} (typed)` }), remove);
  const options = chip.guesses.map((g) => el("button", {
    class: "chip-opt" + (g.gloss === chip.pick ? " on" : ""),
    text: `${wordOf(g.gloss).toUpperCase()} ${Math.round(g.score * 100)}%`,
    title: "Pick this guess",
    onclick: () => { chip.pick = g.gloss; renderSignChips(); },
  }));
  return el("div", { class: "chip" }, head, el("div", { class: "chip-opts" }, ...options), remove);
}

/** Redraw the chips and buttons. app.js calls it after every state from the server. */
export function renderSignChips() {
  const box = $("#sign-chips");
  if (!box) return;
  const playing = store.state?.phase === "playing";
  if (!playing && recording()) { run++; handle(seq.stop()); }
  const list = chips();
  box.replaceChildren(...(list.length ? list.map(chipView)
    : [el("p", { class: "seq-empty", text: "Your signs show up here. Pick the right guess on each one, then send." })]));
  const rec = $("#sign-record");
  rec.textContent = recording() ? "Stop signing (Space)" : "Start signing (Space)";
  rec.classList.toggle("rec", recording());
  rec.disabled = !playing;
  if (!recording()) $("#game-banner")?.classList.add("hidden");
  const busy = list.some((c) => c.state === "pending");
  $("#send-signs").disabled = !playing || busy || !list.some((c) => c.state === "done");
  $("#sign-clear").disabled = !list.length;
  $("#sign-note").textContent = note;
}

// Space starts and stops a recording, as in solo practice. Not while typing.
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || !$("#sign-record") || $("#game").classList.contains("hidden")) return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target?.tagName)) return;
  e.preventDefault();
  if (e.repeat) return;
  toggleRecording();
});

/** Load the tracker in the background, so the first recording starts at once. */
export function preloadSignTracker() {
  void startTracker().catch(() => {});
}
