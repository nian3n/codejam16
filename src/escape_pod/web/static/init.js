// Owner: Teammate 1 (Game, scenes, widgets)
// "Initializing": the screen between Start and the first second of the timer.
//
// The first sign of a game used to sit on "…" for about 6 s: the server loaded the word
// model on the first guess. Now the agent's browser loads the hand tracker (tracker.js)
// and asks the server to load the word model (/api/practice/warmup) while this screen
// shows. When both are done it sends {"type": "ready"}. The server then counts 3-2-1
// (countdown_s in the state, so both players see the same count) and starts the clock
// (server.py arm). Without the count, signing went live with no warning. The handler
// sees the same screen until then. A step that fails does not block
// the game: the typed fallback still works, and the server starts the clock after
// ARM_TIMEOUT_S anyway.
import { $, el, send, store } from "./core.js";
import { startTracker } from "./tracker.js";

const MARK = { wait: "…", ok: "✓", fail: "!" };

function row(label, state, failText) {
  return el("li", { class: `init-step ${state}` }, el("span", { class: "mark", text: MARK[state] }),
    el("span", { text: state === "fail" ? `${label}: ${failText}` : label }));
}

function draw() {
  const s = store.state;
  const box = $("#init-steps");
  if (!box || !s) return;
  if (s.me.role !== "defuser") {
    box.replaceChildren(row("The field agent's equipment is starting", "wait"));
    return;
  }
  const st = store.local.init || { tracker: "wait", model: "wait" };
  box.replaceChildren(
    row("Hand tracker", st.tracker, "not available. You can type the signs instead."),
    row("Sign model", st.model, "not available. You can type the signs instead."));
}

async function run() {
  const st = (store.local.init = { tracker: "wait", model: "wait" });
  const done = (key) => (ok) => { st[key] = ok ? "ok" : "fail"; draw(); };
  await Promise.all([
    startTracker().then(() => true, () => false).then(done("tracker")),
    fetch("/api/practice/warmup").then((r) => r.json()).then((b) => !!b.ready, () => false).then(done("model")),
  ]);
  await new Promise((r) => setTimeout(r, 400));  // long enough to see the ticks
  if (store.local.init === st) send({ type: "ready" });
}

// The 3-2-1: the server sends the seconds left; the page counts down from there.
let countEnd = 0;
let countTimer = 0;

function tick() {
  const left = Math.max(0, (countEnd - performance.now()) / 1000);
  const n = $("#init-count");
  if (n) n.textContent = left > 0 ? String(Math.ceil(left)) : "GO";
  if (left <= 0) { clearInterval(countTimer); countTimer = 0; }
}

/** Show the screen while the game waits for the clock. app.js calls it after every state. */
export function renderInit() {
  const s = store.state;
  const show = s?.phase === "playing" && !s.armed;
  $("#init").classList.toggle("hidden", !show);
  const counting = show && s.countdown_s != null;
  $("#init").classList.toggle("counting", counting);
  $("#init-title").textContent = counting ? "GET READY" : "INITIALIZING";
  $("#init-hint").textContent = counting ? "Signing goes live, and the timer starts, at zero."
    : "The timer starts when everything is ready.";
  if (counting) {
    countEnd = performance.now() + s.countdown_s * 1000;
    if (!countTimer) countTimer = setInterval(tick, 100);
    tick();
  } else if (countTimer) {
    clearInterval(countTimer);
    countTimer = 0;
  }
  if (!show) return;
  if (s.me.role === "defuser" && !store.local.init) void run();
  draw();
}
