// Owner: Teammate 3 (Vision and retrieval)
// The field agent's sign composer in the game: sign to the webcam, check the guesses,
// send them to the handler.
//
// It reads frames from the camera the video call already opened (rtc.js
// localCameraVideo), so there is one camera and one permission prompt. Frames go to
// the hand tracker worker (tracker.js) in this browser. Only landmarks go to the
// server, never video (spec rule 8). The Sequencer (sequence.js, the same one as
// solo practice) cuts the recording into one clip per sign, and each clip goes to
// /api/practice/guess with the words this bomb can show.
//
// Nothing goes to the handler until the agent presses "Send to <handler>": that press is the
// confirmation of every chip (spec rule 4). Each chip shows the top 3 guesses, so a
// wrong top guess costs one click, never a strike.
import { $, el, gameplayOpen, send, store, wordOf } from "./core.js";
import { Sequencer } from "./sequence.js";
import { packLandmarks, startTracker, track, trackerLoaded } from "./tracker.js";
import { localCameraVideo } from "./rtc.js";

const MAX_SIGNS = 12;  // server.py MAX_SIGNS
const CORE = ["yes", "no", "finish"];
// The case lock's words: the digits without 2 (mission.py LOCK_DIGITS). Every allowed word
// is a digit, so the server reads these clips with the digit model only (practice.py).
const LOCK_DIGITS = [..."013456789"];
const FRAME_INTERVAL_MS = 1000 / 24;  // matches camera capture and the clip size limit
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
let digitsReady = null;
let modelStatus;

// Chips live in store.local, so a new game (resetLocal) starts with none.
// {id, state: "pending" | "done" | "unclear" | "error", guesses, pick, text}
const chips = () => (store.local.signChips ??= []);

/**
 * The words the recognizer may choose from. Beginner and Intermediate: every word on
 * this bomb (config.LEVELS allowed_scope "bomb"), never one module's words, because
 * the agent never says which module they sign. Advanced: null, so the server uses all
 * game words.
 */
function allowedWords() {
  const s = store.state;
  if (s?.mission?.stage === "case_lock") return LOCK_DIGITS;
  if (s?.mission?.stage === "wire_tray") return store.pageById.colors.glosses;
  if (s?.bot_words) return s.bot_words;  // solo: the bot asked for numbers (server.py view)
  if (!s?.bomb || s.level === "advanced") return null;
  return [...new Set([...s.bomb.flatMap((m) => m.pool), ...CORE])];
}

function recording() { return seq.phase !== "idle"; }

function signLimit() {
  const mission = store.state?.mission;
  if (mission?.stage === "case_lock") return mission.case_code.length - mission.lock_confirmed;
  return mission?.stage === "wire_tray" ? 1 : MAX_SIGNS;
}

export function clearSignDraft() {
  run++;
  if (recording()) seq.stop();  // Discard the unfinished clip from the gate we left.
  clearChips();
  setNote("");
}

function clearChips() {
  for (const chip of chips()) chip.request?.abort();
  store.local.signChips = [];
}

export function preloadGameSigns() {
  void startTracker().catch(() => {});
  return modelStatus ??= fetch("/api/practice/warmup")
    .then((r) => {
      if (!r.ok) throw new Error("Sign model status unavailable");
      return r.json();
    })
    .catch(() => {
      modelStatus = null;
      return { digits_ready: false };
    });
}

export function signComposer() {
  clearSignDraft();
  digitsReady = null;
  const roundId = store.state.round_id;
  // Signs come from the camera only: the team dropped the typed fallback (Nov 2026).
  const composer = el("div", { class: "composer sign-composer" });
  void preloadGameSigns().then((status) => {
    if (!composer.isConnected || store.state?.round_id !== roundId || store.state.phase !== "playing") return;
    digitsReady = !!status.digits_ready;
    renderSignChips();
  });
  composer.append(
    el("div", { class: "label", id: "sign-instructions" }),
    el("div", { class: "seq-banner hidden", id: "game-banner", "aria-live": "polite" }),
    el("div", { class: "sign-buttons" },
      el("button", { class: "btn primary", id: "sign-record", text: "Start signing (Space)", onclick: toggleRecording }),
      el("button", { class: "btn small", id: "sign-clear", text: "Clear", onclick: () => {
        clearChips();
        renderSignChips();
      } })),
    el("div", { class: "label sign-note", id: "sign-note" }),
    el("div", { class: "sign-frame hidden", id: "sign-frame" }),
    el("div", { class: "seq-chips", id: "sign-chips" }),
    el("button", { class: "btn primary", id: "send-signs", onclick: sendSigns }));
  return composer;
}

/** Who reads the signs: the bot's name in a solo game, else the handler player's name. */
function handlerName() {
  const s = store.state;
  return (s?.solo ? s.bot_name : s?.players?.find((p) => p.role === "expert")?.name) || "the handler";
}

function sendSigns() {
  const s = store.state;
  if (!gameplayOpen() || store.ws?.readyState !== 1) return;
  const picks = chips().filter((c) => c.state === "done" && c.pick).map((c) => c.pick);
  if (!picks.length || chips().some((c) => c.state === "pending")) return;
  run++;
  if (recording()) seq.stop();
  const msg = { type: "signs", glosses: picks, round_id: s.round_id };
  if (s.mission && s.mission.stage !== "modules") msg.mission_revision = s.mission.revision;
  send(msg);
  store.local.signChips = [];
  renderSignChips();
}

function toggleRecording() {
  if (recording()) stopRecording(); else void startRecording();
}

async function startRecording() {
  const s = store.state;
  if (recording() || !gameplayOpen()) return;
  if (s.mission?.stage === "case_lock" && !digitsReady) return;
  const video = localCameraVideo();
  if (!video) { setNote("Turn your camera on to sign."); return; }
  const id = ++run;
  if (!trackerLoaded()) setNote("Loading the hand tracker (only the first time)…");
  try {
    await startTracker();
  } catch (error) {
    if (run === id) setNote(error.message || "The hand tracker could not start. Start signing again to retry.");
    return;
  }
  if (run !== id || !gameplayOpen()) return;
  setNote("");
  const gate = s.mission?.stage === "case_lock" || s.mission?.stage === "wire_tray";
  handle(seq.start(performance.now(), { trimLongSigns: gate }));
  renderSignChips();
  void loop(id);
}

function stopRecording() {
  run++;
  if (recording()) handle(seq.stop());
  renderSignChips();
}

async function loop(id) {
  let lastFrame = -1;
  let lastSample = -Infinity;
  try {
    while (run === id) {
      await new Promise(requestAnimationFrame);
      if (run !== id) return;
      const video = localCameraVideo();
      if (!video) {
        run++;
        seq.stop();
        setNote("The camera turned off. Turn it on and start signing again.");
        renderSignChips();
        return;
      }
      if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) continue;
      const now = performance.now();
      const frame = video.getVideoPlaybackQuality?.().totalVideoFrames || video.currentTime;
      if (frame === lastFrame || now - lastSample < FRAME_INTERVAL_MS) continue;
      lastFrame = frame;
      lastSample = now;
      const landmarks = await track(video);
      if (run !== id) return;
      handle(seq.push(performance.now(), landmarks, packLandmarks(landmarks)));
    }
  } catch {
    if (run === id) { stopRecording(); setNote("Hand tracking stopped. Start signing again."); }
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
  if (!gameplayOpen()) return;
  if (chips().length >= signLimit()) { setNote("Confirm the current chips first."); return; }
  const chip = { id: nextId++, state: e.unclear ? "unclear" : "pending", guesses: [], pick: null, text: "" };
  chips().push(chip);
  renderSignChips();
  if (e.unclear) return;
  const request = new AbortController();
  chip.request = request;
  const words = allowedWords();
  const url = "/api/practice/guess" + (words ? `?words=${encodeURIComponent(words.join(","))}` : "");
  fetch(url, { method: "POST", signal: request.signal, body: new Blob(e.frames, { type: "application/octet-stream" }),
    headers: { "Content-Type": "application/octet-stream" } })
    .then(async (r) => {
      const body = await r.json();
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not read this sign.");
      chip.guesses = body.guesses;
      chip.pick = body.guesses[0]?.gloss ?? null;
      chip.state = chip.pick ? "done" : "unclear";
    })
    .catch((err) => { chip.state = "error"; chip.text = err.message; })
    .finally(() => {
      chip.request = null;
      if (chips().includes(chip)) renderSignChips();
    });
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
  const s = store.state;
  const playing = gameplayOpen();
  const stage = s?.mission?.stage;
  const lock = stage === "case_lock";
  const tray = stage === "wire_tray";
  const list = chips();
  box.replaceChildren(...(list.length ? list.map(chipView)
    : [el("p", { class: "seq-empty", text: "Your signs show up here. Pick the right guess on each one, then send." })]));
  const rec = $("#sign-record");
  rec.textContent = recording() ? "Stop signing (Space)" : "Start signing (Space)";
  rec.classList.toggle("rec", recording());
  rec.disabled = !playing || (lock && !digitsReady);
  if (!recording()) $("#game-banner")?.classList.add("hidden");
  const busy = list.some((c) => c.state === "pending");
  $("#send-signs").disabled = !playing || busy || !list.some((c) => c.state === "done");
  $("#sign-clear").disabled = !list.length;
  $("#sign-note").textContent = note;
  $("#sign-instructions").textContent = lock
    ? digitsReady === false ? "The digit model is not available. Reload the page to try again."
      : digitsReady === null ? "Loading the digit model…"
      : "Sign the digits from the tag in order. Lower your hands between digits and check each chip before confirming."
    : tray ? "Sign the next wire’s color and press Enter to confirm it."
    : s?.solo ? ""  // solo: the bot's question says what to sign
    : "Sign each item on one module to your camera, one sign at a time. Dial: sign the pictures clockwise from the top, then the one the needle points at.";
  $("#send-signs").textContent = lock ? "Confirm digits (Enter)" : tray ? "Confirm color (Enter)" : `Send to ${handlerName()} (Enter)`;
  // Solo: the bot's template around the chips. "module": one item names the module.
  // "details": the answer to the bot's last question.
  const frame = $("#sign-frame");
  frame.classList.toggle("hidden", !s?.solo || !s.bot_stage);
  frame.textContent = s?.bot_stage === "details" ? "My answer:" : "I need help with:";
}

// Enter sends the chips to the handler. Outside text fields only, so Enter in the glossary
// search still works as usual. On a focused button it sends too, instead of
// clicking that button again: the player's hands are busy, Enter is the one key to find.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Enter" || !gameplayOpen() || store.state.me.role !== "defuser") return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target?.tagName) || e.repeat) return;
  if (e.target?.closest?.(".video-dock, .topbar, summary")) return;
  if (!$("#glossary")?.classList.contains("hidden")) return;
  e.preventDefault();
  if (!$("#send-signs").disabled) sendSigns();
});

// Space starts and stops a recording, as in solo practice. Not while typing.
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || !gameplayOpen() || store.state.me.role !== "defuser") return;
  if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target?.tagName)) return;
  if (e.target?.closest?.(".video-dock, .topbar, summary") || !$("#glossary").classList.contains("hidden")) return;
  e.preventDefault();
  if (e.repeat) return;
  toggleRecording();
});

