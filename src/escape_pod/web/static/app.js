// Owner: Teammate 1 (Game, scenes, widgets)
// Entry point: boot, the WebSocket connection and switching screens.
// The server owns the game; the client only renders the state it receives and
// sends player intents (role, signs, clicks) back.
//
//   core.js         helpers + the shared store (imports nothing)
//   lobby.js        room code, roles, level, start
//   bomb.js         defuser view; widgets/*.js draw each module type
//   manual_view.js  expert view
//   feed.js         messages, sign composer, reply box
import { $, el, fmt, resetLocal, send, store } from "./core.js";
import { bindLobby, renderLobby } from "./lobby.js";
import { renderBomb } from "./bomb.js";
import { renderManual } from "./manual_view.js";
import { defuserComposer, expertComposer, renderFeed, renderSignChips } from "./feed.js";
import { renderGuided, resetGuided, roleName } from "./guided.js";
import { enterPractice, leavePractice } from "./practice.js";
import { receiveVideo, syncVideo } from "./room_video.js";
import { updateFaces } from "./widgets/big_button.js";

let code = null;
let closedOnPurpose = false;

async function boot() {
  $("#open-practice").onclick = () => { showScreen("practice"); void enterPractice(); };
  $("#close-practice").onclick = () => showScreen("home");
  const [icons, pages] = await Promise.all([
    fetch("/api/icons").then((r) => r.json()),
    fetch("/api/manual").then((r) => r.json()),
  ]);
  store.icons = icons;
  store.pages = pages;
  store.pageById = Object.fromEntries(pages.map((p) => [p.id, p]));
  $("#name").value = localStorage.getItem("ep:name") || "";
  const q = new URLSearchParams(location.search).get("room");
  if (q) $("#code").value = q.toUpperCase();
  async function createRoom(mode) {
    if (!saveName()) return;
    const r = await fetch(`/api/rooms?mode=${mode}`, { method: "POST" }).then((r) => r.json());
    connect(r.code);
  }
  $("#create").onclick = () => createRoom("classic");
  $("#create-guided").onclick = () => createRoom("guided");
  $("#join").onclick = () => { if (saveName()) connect($("#code").value.trim().toUpperCase()); };
  $("#code").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#join").click(); });
  $("#again").onclick = () => send({ type: "again" });
  bindLobby();
  setInterval(tickTimer, 200);
  setInterval(() => { store.faceTick++; updateFaces(); }, 1200);
  // Keep seats per tab so two tabs can play different roles on the same laptop.
  if (q) {
    const room = q.toUpperCase();
    const key = `ep:pid:${room}`;
    const pid = sessionStorage.getItem(key) || localStorage.getItem(key);
    if (pid) {
      sessionStorage.setItem(key, pid);
      localStorage.removeItem(key);
      connect(room);
    }
  }
}

function saveName() {
  const n = $("#name").value.trim();
  if (!n) { $("#home-error").textContent = "Type your name first."; return false; }
  localStorage.setItem("ep:name", n);
  return true;
}

function connect(c) {
  if (!/^[A-Z]{4}$/.test(c)) { $("#home-error").textContent = "A room code has 4 letters."; return; }
  code = c;
  closedOnPurpose = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${c}`);
  store.ws = ws;
  const key = `ep:pid:${c}`;
  const name = $("#name").value.trim();
  ws.onopen = () => ws.send(JSON.stringify({ type: "hello", pid: sessionStorage.getItem(key), name }));
  ws.onmessage = (e) => {
    if (store.ws !== ws) return;
    const m = JSON.parse(e.data);
    if (m.type === "welcome") {
      sessionStorage.setItem(key, m.pid);
      history.replaceState(null, "", `/?room=${c}`);
    } else if (m.type === "error") {
      closedOnPurpose = true;
      syncVideo(null);
      showScreen("home");
      $("#home-error").textContent = m.text;
    } else if (m.type === "state") onState(m);
    else if (m.type === "video") void receiveVideo(m);
  };
  ws.onclose = (event) => {
    if (store.ws !== ws) return;
    syncVideo(null);
    if (event.code === 4000) {
      showScreen("home");
      $("#home-error").textContent = "This seat is open in another tab.";
    } else if (!closedOnPurpose && store.state) {
      setTimeout(() => { if (store.ws === ws) connect(code); }, 1500);
    }
  };
}

function showScreen(id) {
  if (id !== "practice" && !$("#practice").classList.contains("hidden")) leavePractice();
  if (id !== "game") {
    $("#end").classList.add("hidden");
    resetGuided();
  }
  for (const s of ["home", "lobby", "game", "practice"]) $("#" + s).classList.toggle("hidden", s !== id);
}

function onState(s) {
  const prev = store.state;
  store.state = s;
  syncVideo(s);
  store.deadlineAt = performance.now() + s.remaining_s * 1000;
  if (s.phase === "lobby") {
    showScreen("lobby");
    renderLobby();
  } else {
    showScreen("game");
    if (!prev || prev.code !== s.code || prev.phase === "lobby" || prev.me.role !== s.me.role) setupGame();
    renderGame();
  }
  const over = !s.guided && (s.phase === "escaped" || s.phase === "boom");
  $("#end").classList.toggle("hidden", !over);
  if (over) renderEnd();
  if (prev && prev.phase === "playing" && s.strikes > prev.strikes) flashStrike();
  tickTimer();
}

function flashStrike() {
  // Remove, force a reflow, add again: restarts the CSS animation every strike.
  for (const [node, cls] of [[document.body, "flash"], [$("#stage"), "shake"]]) {
    node.classList.remove(cls);
    void node.offsetWidth;
    node.classList.add(cls);
  }
}

function setupGame() {
  resetLocal();
  const s = store.state;
  $("#game-code").textContent = s.code;
  $("#game").classList.toggle("guided-mode", !!s.guided);
  $("#game").classList.toggle("guided-decoder", !!s.guided && s.me.role === "expert");
  $("#game-role").textContent = s.guided ? roleName(s.me.role, s.guided.swapped) : s.me.role === "defuser" ? "💣 Defuser" : "📖 Expert";
  $("#top-strikes").classList.toggle("hidden", !!s.guided);
  $("#composer").replaceChildren();
  const bar = $(".topbar");
  bar.querySelector(".dbg")?.remove();
  if (s.guided) return;
  $("#composer").replaceChildren(s.me.role === "defuser" ? defuserComposer() : expertComposer());
  if (s.debug) bar.append(el("a", { class: "btn small dbg", href: `/api/rooms/${s.code}/answer-key`, target: "_blank", text: "Answer key (debug)" }));
}

function renderGame() {
  const s = store.state;
  if (s.guided) {
    $("#top-progress").textContent = s.guided.step === "practice" || s.guided.step === "ready"
      ? "Practice round"
      : `${s.guided.solved} / ${s.guided.total} clues solved`;
    renderGuided(s);
    return;
  }
  $("#top-strikes").replaceChildren(...Array.from({ length: s.max_strikes }, (_, i) => el("div", { class: "strike-led" + (i < s.strikes ? " on" : "") })));
  $("#top-progress").textContent = s.progress ? `Defused ${s.progress.defused} / ${s.progress.total}` : "";
  if (s.me.role === "defuser") renderBomb();
  // Re-render the manual only when new messages arrive, so the page keeps its scroll.
  else if (store.local.chatSeen !== s.chat.length || !$("#stage .manual")) renderManual();
  renderFeed();
  renderSignChips();
}

function tickTimer() {
  const s = store.state;
  if (!s) return;
  if (s.guided && ["practice", "ready", "untimed"].includes(s.guided.step)) {
    $("#top-timer").textContent = "Untimed";
    return;
  }
  const left = s.phase === "playing" ? Math.max(0, (store.deadlineAt - performance.now()) / 1000) : s.remaining_s;
  const t = fmt(Math.ceil(left));
  $("#top-timer").textContent = s.guided?.step === "unlocked" && left === 0 ? "Unlocked" : t;
  const seg = $(".seg");
  if (seg) seg.textContent = t;
}

function renderEnd() {
  const s = store.state;
  const win = s.phase === "escaped";
  $(".end-card").className = "card end-card " + (win ? "win" : "lose");
  $("#end-title").textContent = win ? "POD LAUNCHED!" : "BOOM";
  $("#end-stats").textContent = `Defused ${s.progress.defused} of ${s.progress.total} · Strikes ${s.strikes} · Time left ${fmt(Math.ceil(s.remaining_s))}`;
}

boot();
