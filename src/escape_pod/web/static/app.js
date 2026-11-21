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
import { $, el, fmt, gameplayOpen, resetLocal, secondsLeft, send, store } from "./core.js";
import { bindLobby, renderLobby } from "./lobby.js";
import { renderBomb } from "./bomb.js";
import { renderManual } from "./manual_view.js";
import { defuserComposer, expertComposer, renderFeed, renderSignChips } from "./feed.js";
import { clearSignDraft, preloadGameSigns } from "./game_signs.js";
import { finishTray, renderMission } from "./mission.js";
import { prepareWorkbench, renderCaseTime, renderDamageBays, resetWorkbench, setCaseOutcome } from "./workbench.js";
import { updateFaces } from "./widgets/big_button.js";
import { onRoomState, onRtc, placeDock, stopVideo } from "./rtc.js";
import { bindGlossary, closeGlossary } from "./glossary.js";
import { enterPractice, leavePractice, preloadMediaPipe } from "./practice.js";
import { bindSequence, setSequenceProfile } from "./practice_sequence.js";
import { bindProfiles, currentProfile, moveProgress, savePracticeCredits, saveProfile } from "./progress.js";

let activeSeatKey = null;
let activeScreen = "home";
let lobbyCamera = true;
const DETONATION_MS = 1500;
let detonationTimer = null;

async function boot() {
  const legacyProfile = bindProfiles();
  const [icons, pages] = await Promise.all([
    fetch("/api/icons").then((r) => r.json()),
    fetch("/api/manual").then((r) => r.json()),
  ]);
  store.icons = icons;
  store.pages = pages;
  store.pageById = Object.fromEntries(pages.map((p) => [p.id, p]));
  const q = new URLSearchParams(location.search).get("room");
  if (q) $("#code").value = q.toUpperCase();
  $("#create").onclick = () => void createRoom(false);
  $("#create-solo").onclick = () => void createRoom(true);
  $("#join").onclick = () => {
    const profile = requireProfile();
    if (profile) connect($("#code").value.trim().toUpperCase(), profile);
  };
  $("#code").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#join").click(); });
  $("#again").onclick = () => send({ type: "again" });
  $("#leave").onclick = leaveRoom;
  $("#exit-game").onclick = exitGame;
  bindLobby();
  bindGlossary();
  bindSequence();
  $("#open-practice").onclick = () => {
    const profile = requireProfile();
    if (!profile) return;
    setSequenceProfile(profile);
    showScreen("practice");
    void enterPractice();
  };
  // Start loading MediaPipe as soon as the player points at the button.
  for (const ev of ["pointerenter", "focus", "touchstart"]) $("#open-practice").addEventListener(ev, preloadMediaPipe, { once: true, passive: true });
  $("#close-practice").onclick = () => showScreen("home");
  window.addEventListener("pagehide", stopVideo);
  window.addEventListener("pageshow", (event) => {
    if (event.persisted && store.state) onState(store.state);
  });
  setInterval(tickTimer, 200);
  setInterval(() => {
    if (store.state?.phase !== "playing") return;
    store.faceTick++;
    updateFaces();
  }, 1200);
  // Keep room seats in each tab so a fresh invite can be opened by another profile.
  const profile = currentProfile();
  if (q && profile) {
    const room = q.toUpperCase();
    const key = seatKey(profile, room);
    const oldKey = `ep:pid:${room}`;
    const legacySeat = legacyProfile?.id === profile.id && localStorage.getItem(oldKey);
    if (legacySeat) {
      sessionStorage.setItem(key, legacySeat);
      localStorage.removeItem(oldKey);
    }
    if (sessionStorage.getItem(key)) connect(room, profile);
  }
}

function requireProfile() {
  const profile = saveProfile();
  $("#home-error").textContent = profile ? "" : "Choose a profile or type your name first.";
  if (!profile) $("#name").focus();
  return profile;
}

function setConnecting(connecting) {
  for (const field of ["#profile", "#name", "#create", "#create-solo", "#join", "#open-practice"]) {
    $(field).disabled = connecting;
  }
}

async function createRoom(solo) {
  const profile = requireProfile();
  if (!profile) return;
  setConnecting(true);
  try {
    const response = await fetch("/api/rooms", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ solo }) });
    if (!response.ok) throw new Error();
    const room = await response.json();
    connect(room.code, profile);
  } catch {
    setConnecting(false);
    $("#home-error").textContent = "Couldn’t create a room. Try again.";
  }
}

function seatKey(profile, room) {
  return `ep:pid:${profile.id}:${room}`;
}

function connect(c, profile) {
  if (!/^[A-Z]{4}$/.test(c)) { $("#home-error").textContent = "A room code has 4 letters."; return; }
  setConnecting(true);
  const key = seatKey(profile, c);
  activeSeatKey = key;
  let rejected = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${c}`);
  store.ws = ws;
  ws.onopen = () => ws.send(JSON.stringify({ type: "hello", pid: sessionStorage.getItem(key), name: profile.name }));
  ws.onmessage = (e) => {
    if (store.ws !== ws) return;
    const m = JSON.parse(e.data);
    if (m.type === "welcome") {
      sessionStorage.setItem(key, m.pid);
      history.replaceState(null, "", `/?room=${c}`);
    } else if (m.type === "error") {
      rejected = true;
      stopVideo();
      clearSignDraft();
      lobbyCamera = true;
      store.state = null;
      renderOutcome();
      setConnecting(false);
      showScreen("home");
      $("#home-error").textContent = m.text;
    } else if (m.type === "state") {
      const credits = savePracticeCredits(profile, m.practice_credits ?? []);
      if (credits.length) send({ type: "practice_saved", credits });
      setConnecting(false);
      onState(m);
    } else if (m.type === "rtc") onRtc(m.data);
  };
  ws.onclose = () => {
    if (rejected || store.ws !== ws) return;
    if (store.state) setTimeout(() => { if (store.ws === ws) connect(c, profile); }, 1500);
    else {
      setConnecting(false);
      $("#home-error").textContent = "Couldn’t reach the room. Try again.";
    }
  };
}

/** Lobby "Leave room": give up the seat and go back to the home screen. */
function leaveRoom() {
  send({ type: "leave" });
  const ws = store.ws;
  store.ws = null;
  store.state = null;
  ws?.close();
  sessionStorage.removeItem(activeSeatKey);  // a reload must not rejoin the old seat
  history.replaceState(null, "", "/");
  $("#code").value = "";
  $("#home-error").textContent = "";
  stopVideo();
  lobbyCamera = true;
  closeGlossary();
  setConnecting(false);
  showScreen("home");
}

/** In-game "Exit game": ends the game for both players. Needs a second click, so a
 *  stray click does not throw away the round. */
let exitArmed = null;
function exitGame() {
  const b = $("#exit-game");
  if (!exitArmed) {
    b.classList.add("armed");
    b.textContent = "Click again to end the game";
    exitArmed = setTimeout(disarmExit, 3000);
    return;
  }
  disarmExit();
  send({ type: "exit" });
}
function disarmExit() {
  clearTimeout(exitArmed);
  exitArmed = null;
  const b = $("#exit-game");
  b.classList.remove("armed");
  b.textContent = "Exit game";
}

function showScreen(id) {
  if (id !== "practice" && !$("#practice").classList.contains("hidden")) leavePractice();
  for (const s of ["home", "lobby", "game", "practice"]) $("#" + s).classList.toggle("hidden", s !== id);
  if (activeScreen !== id) {
    activeScreen = id;
    moveProgress(id);
  }
}

function onState(s) {
  const prev = store.state;
  store.state = s;
  const playing = s.phase === "playing";
  if (playing) {
    const deadline = performance.now() + s.remaining_s * 1000;
    // A delayed snapshot cannot add time to a round that is already underway.
    store.deadlineAt = prev?.round_id === s.round_id && prev.phase === "playing"
      ? Math.min(store.deadlineAt, deadline) : deadline;
  } else {
    store.deadlineAt = 0;
  }
  const over = s.phase === "escaped" || s.phase === "boom";
  if (s.phase === "lobby") {
    if (exitArmed) disarmExit();
    closeGlossary();  // the glossary is for games only
    if (prev && prev.phase !== "lobby") {
      clearSignDraft();
      stopVideo();
      lobbyCamera = false;
    }
    resetWorkbench();
    showScreen("lobby");
    renderLobby();
    placeDock($("#lobby-video"));
    onRoomState(s, lobbyCamera);
    if (s.me.role === "defuser" && prev?.me.role !== "defuser") void preloadGameSigns();
  } else {
    showScreen("game");
    if (playing) {
      placeDock($(".side"));
      onRoomState(s, true);
    } else if (prev?.phase === "playing") {
      stopVideo();
      closeGlossary();
    }
    if (!prev || prev.phase === "lobby" || prev.round_id !== s.round_id || prev.me.role !== s.me.role) setupGame();
    else if (s.me.role === "defuser" && (prev.mission?.stage !== s.mission?.stage || (over && prev.phase === "playing"))) clearSignDraft();
    renderGame(prev);
  }
  renderOutcome(prev);
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
  $("#game-role").textContent = s.me.role === "defuser" ? "🕵️ Field agent" : "🎧 Handler";
  const by = (role) => s.players.find((p) => p.role === role)?.name || (s.solo && role === "expert" ? s.bot_name : "?");
  // Solo: no room code on screen (nobody joins). The operation name drops it too.
  $("#game-room").classList.toggle("hidden", !!s.solo);
  $("#op-line").textContent = `Operation KMNE${s.solo ? "" : "-" + s.code} · Agent ${by("defuser")} · Handler ${by("expert")}`;
  $("#composer").replaceChildren(s.me.role === "defuser" ? defuserComposer() : expertComposer());
  const bar = $(".topbar");
  bar.querySelector(".dbg")?.remove();
  if (s.debug) bar.append(el("a", { class: "btn small dbg", href: `/api/rooms/${s.code}/answer-key`, target: "_blank", text: "Answer key (debug)" }));
}

function renderGame(previous) {
  const s = store.state;
  const playing = s.phase === "playing";
  $("#game").classList.toggle("round-over", !playing);
  $("#game").dataset.role = s.me.role;
  prepareWorkbench(s, previous);
  $("#top-strikes").replaceChildren(...Array.from({ length: s.max_strikes }, (_, i) => el("div", { class: "strike-led" + (i < s.strikes ? " on" : "") })));
  $("#top-progress").textContent = s.progress ? `Defused ${s.progress.defused} / ${s.progress.total}` : "";
  $("#exit-game").classList.toggle("hidden", s.phase !== "playing");
  if (!playing) {
    if (s.bomb) renderBomb();
    else renderDamageBays();
  } else if (s.me.role === "defuser" && s.mission.stage === "case_lock") {
    $("#stage").replaceChildren();
  } else if (s.mission.stage !== "modules") renderMission(s, previous);
  else if (s.me.role === "defuser") renderBomb();
  // Re-render the manual only when new messages arrive, so the page keeps its scroll.
  else if (store.local.chatSeen !== s.chat.length || !$("#stage .manual")) renderManual();
  finishTray(previous, s);
  renderFeed();
  renderSignChips();
}

function tickTimer() {
  const s = store.state;
  if (!s) { document.body.classList.remove("critical"); return; }
  const left = secondsLeft();
  const workbench = $("#workbench");
  const locked = !gameplayOpen();
  if (locked && !workbench.inert && s.phase === "playing" && s.me.role === "defuser") {
    clearSignDraft();
    renderSignChips();
  }
  workbench.inert = locked;
  $("#composer").inert = locked;
  $(".topbar").inert = locked;
  // The alarm speeds up in the last 30 s of a running game only, so it never leaks into the lobby or end screen.
  document.body.classList.toggle("critical", s.phase === "playing" && left < 30);
  const t = fmt(Math.ceil(left));
  $("#top-timer").textContent = t;
  renderCaseTime(t);
}

function renderOutcome(previous) {
  const s = store.state;
  const end = $("#end");
  const detonation = $("#detonation");
  if (s?.phase !== "escaped" && s?.phase !== "boom") {
    clearTimeout(detonationTimer);
    detonationTimer = null;
    end.classList.add("hidden");
    detonation.classList.add("hidden");
    setCaseOutcome("");
    return;
  }
  renderEnd();
  if (s.timed_out && previous?.round_id === s.round_id && previous.phase === "playing"
      && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    end.classList.add("hidden");
    $("#workbench").style.setProperty("--blast-duration", `${DETONATION_MS}ms`);
    setCaseOutcome("blast");
    detonation.classList.remove("hidden");
    // The report must open even if a background tab never paints the animation.
    detonationTimer = setTimeout(() => {
      detonationTimer = null;
      if (store.state?.round_id !== s.round_id || !store.state.timed_out) return;
      setCaseOutcome("failure");
      detonation.classList.add("hidden");
      end.classList.remove("hidden");
      $("#again").focus();
    }, DETONATION_MS);
  } else if (detonation.classList.contains("hidden")) {
    setCaseOutcome(s.phase === "escaped" ? "success" : "failure");
    const wasHidden = end.classList.contains("hidden");
    end.classList.remove("hidden");
    if (wasHidden) $("#again").focus();
  }
}

function renderEnd() {
  const s = store.state;
  const win = s.phase === "escaped";
  $(".end-card").className = "card end-card " + (win ? "win" : "lose");
  $("#end-title").textContent = win ? "Defused" : "Detonation";
  $("#end-stats").textContent = `Defused ${s.progress.defused} of ${s.progress.total} · Strikes ${s.strikes} · Time left ${fmt(Math.ceil(s.remaining_s))}`;
}

boot();
