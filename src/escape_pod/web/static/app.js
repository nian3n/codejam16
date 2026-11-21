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

const roomButtons = ["#create-guided", "#create", "#join"].map($);
let roomToolsReady = false;

async function boot() {
  $("#open-practice").onclick = () => { showScreen("practice"); void enterPractice(); };
  $("#close-practice").onclick = () => showScreen("home");
  $("#leave-lobby").onclick = leaveLobby;
  const q = new URLSearchParams(location.search).get("room");
  $("#name").value = localStorage.getItem("ep:name") || "";
  setInvite(q);
  for (const field of [$("#name"), $("#code")]) {
    field.oninput = () => {
      if (field.hasAttribute("aria-invalid")) {
        field.removeAttribute("aria-invalid");
        $("#home-error").textContent = "";
      }
    };
  }
  let icons, pages;
  try {
    [icons, pages] = await Promise.all([loadJSON("/api/icons"), loadJSON("/api/manual")]);
  } catch {
    roomError("Room tools couldn’t load. Reload the page to try again.");
    return;
  }
  store.icons = icons;
  store.pages = pages;
  store.pageById = Object.fromEntries(pages.map((p) => [p.id, p]));
  roomToolsReady = true;
  roomStatus("");
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

async function loadJSON(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`Couldn’t load ${url}`);
  return response.json();
}

function roomStatus(message) {
  for (const button of roomButtons) button.disabled = !roomToolsReady || !!message;
  $("#home-status").textContent = message;
  if (message) $("#home-error").textContent = "";
}

function roomError(message, input) {
  roomStatus("");
  $("#home-error").textContent = message;
  if (input) {
    input.setAttribute("aria-invalid", "true");
    input.focus();
  }
}

function setInvite(code) {
  const join = $(".room-join");
  const create = $(".room-create");
  if (code) create.before(join);
  else join.before(create);
  $(".room-form").classList.toggle("has-invite", !!code);
  $("#room-form-title").textContent = code ? "Join your partner" : "Play together";
  $("#join").classList.toggle("primary", !!code);
  $("#create-guided").classList.toggle("primary", !code);
  $("#code").value = code?.toUpperCase() || "";
}

function saveName() {
  const n = $("#name").value.trim();
  if (!n) { roomError("Enter your name before you continue.", $("#name")); return false; }
  localStorage.setItem("ep:name", n);
  return true;
}

async function createRoom(mode) {
  if (!saveName()) return;
  roomStatus("Creating your room…");
  try {
    const room = await loadJSON(`/api/rooms?mode=${mode}`, { method: "POST" });
    connect(room.code);
  } catch {
    roomError("Couldn’t create a room. Try again.");
  }
}

function leaveLobby() {
  const ws = store.ws;
  store.ws = null;
  store.state = null;
  ws?.close();
  syncVideo(null);
  history.replaceState(null, "", "/");
  setInvite(null);
  roomStatus("");
  showScreen("home");
}

function connectionStatus(message) {
  const banner = $("#connection-status");
  banner.textContent = message;
  banner.classList.toggle("hidden", !message);
  $("#stage").inert = !!message;
  if (message && store.state?.phase === "lobby") {
    $("#lobby-hint").textContent = message;
    $("#start").disabled = true;
    for (const button of document.querySelectorAll(".role .take, #levels button")) button.disabled = true;
  }
}

function connect(c) {
  if (!/^[A-Z]{4}$/.test(c)) { roomError("Enter a four-letter room code.", $("#code")); return; }
  if (store.state?.code !== c) roomStatus("Connecting to your room…");
  let rejected = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${c}`);
  store.ws = ws;
  const timeout = setTimeout(() => ws.close(), 12_000);
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
      rejected = true;
      clearTimeout(timeout);
      store.state = null;
      syncVideo(null);
      showScreen("home");
      roomError(m.text);
    } else if (m.type === "state") {
      clearTimeout(timeout);
      roomStatus("");
      connectionStatus("");
      onState(m);
    }
    else if (m.type === "video") void receiveVideo(m);
  };
  ws.onclose = (event) => {
    clearTimeout(timeout);
    if (store.ws !== ws) return;
    const reconnect = !rejected && event.code !== 4000 && store.state?.code === c;
    syncVideo(reconnect ? { ...store.state, players: [] } : null);
    if (event.code === 4000) {
      store.state = null;
      showScreen("home");
      roomError("This seat is open in another tab.");
    } else if (reconnect) {
      connectionStatus("Room connection lost. Reconnecting…");
      setTimeout(() => { if (store.ws === ws) connect(c); }, 1500);
    } else if (!rejected) {
      roomError("Couldn’t reach the room. Check your connection and try again.");
    }
  };
}

function showScreen(id) {
  const entering = $("#" + id).classList.contains("hidden");
  if (id !== "practice" && !$("#practice").classList.contains("hidden")) leavePractice();
  if (id !== "game") {
    $("#end").classList.add("hidden");
    resetGuided();
    $("#connection-status").classList.add("hidden");
  }
  for (const s of ["home", "lobby", "game", "practice"]) $("#" + s).classList.toggle("hidden", s !== id);
  if (entering) {
    window.scrollTo(0, 0);
    const heading = id === "game" ? $("#game-role") : $(`#${id} h1`);
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
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
    if (!prev || prev.code !== s.code || prev.phase === "lobby" || prev.me.role !== s.me.role) setupGame();
    showScreen("game");
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
  $("#game").classList.toggle("studio", !!s.guided);
  $("#game-role").textContent = s.guided ? roleName(s.me.role, s.guided.swapped) : s.me.role === "defuser" ? "Defuser" : "Expert";
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
