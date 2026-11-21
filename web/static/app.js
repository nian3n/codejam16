// Owner: Teammate 1 (Game, scenes, widgets)
// Escape Pod web client. The server owns the game; this file only renders the
// state it receives and sends player intents (role, signs, clicks) back.
"use strict";

const $ = (s) => document.querySelector(s);
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "style") n.style.cssText = v;
    else n.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) n.append(c);
  return n;
}
const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}
const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// ---------------------------------------------------------------- state
let ws = null, code = null, state = null, closedOnPurpose = false;
let icons = {}, pages = [], pageById = {};
let deadlineAt = 0;
const local = { signs: [], kp: {}, cut: {}, needle: {}, openPage: null, search: "", chatSeen: -1 };
let faceTick = 0;

const WIRE_COLORS = { red: "#e03a3a", blue: "#3f6fe6", green: "#3fb85a", yellow: "#f2d33b", black: "#1a1a1a",
  white: "#f2f2f2", brown: "#8a5a2b", orange: "#f28a1e" };

function icon(g) { return icons[g] || { emoji: "❔", caption: true }; }
function wordOf(g) { return { frenchfries: "french fries", icecream: "ice cream", tv: "TV" }[g] || g; }

// ---------------------------------------------------------------- boot
async function boot() {
  [icons, pages] = await Promise.all([fetch("/api/icons").then((r) => r.json()), fetch("/api/manual").then((r) => r.json())]);
  pageById = Object.fromEntries(pages.map((p) => [p.id, p]));
  $("#name").value = localStorage.getItem("ep:name") || "";
  const q = new URLSearchParams(location.search).get("room");
  if (q) $("#code").value = q.toUpperCase();
  $("#create").onclick = async () => {
    if (!saveName()) return;
    const r = await fetch("/api/rooms", { method: "POST" }).then((r) => r.json());
    connect(r.code);
  };
  $("#join").onclick = () => { if (saveName()) connect($("#code").value.trim().toUpperCase()); };
  $("#code").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#join").click(); });
  $("#copy-link").onclick = () => {
    navigator.clipboard?.writeText(`${location.origin}/?room=${code}`);
    $("#copy-link").textContent = "Copied!";
    setTimeout(() => ($("#copy-link").textContent = "Copy invite link"), 1500);
  };
  $("#start").onclick = () => send({ type: "start" });
  $("#again").onclick = () => send({ type: "again" });
  document.querySelectorAll(".role .take").forEach((b) => {
    b.onclick = () => send({ type: "role", role: b.closest(".role").dataset.role });
  });
  setInterval(tickTimer, 200);
  setInterval(() => { faceTick++; updateFaces(); }, 1200);
  // Reloading the page with ?room=CODE and a saved player id rejoins the same seat.
  if (q && localStorage.getItem(`ep:pid:${q.toUpperCase()}`)) connect(q.toUpperCase());
}

function saveName() {
  const n = $("#name").value.trim();
  if (!n) { $("#home-error").textContent = "Type your name first."; return false; }
  localStorage.setItem("ep:name", n);
  return true;
}

function send(msg) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(msg)); }

function connect(c) {
  if (!/^[A-Z]{4}$/.test(c)) { $("#home-error").textContent = "A room code has 4 letters."; return; }
  code = c;
  closedOnPurpose = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${c}`);
  ws.onopen = () => ws.send(JSON.stringify({ type: "hello", pid: localStorage.getItem(`ep:pid:${c}`), name: localStorage.getItem("ep:name") }));
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.type === "welcome") {
      localStorage.setItem(`ep:pid:${c}`, m.pid);
      history.replaceState(null, "", `/?room=${c}`);
    } else if (m.type === "error") {
      closedOnPurpose = true;
      showScreen("home");
      $("#home-error").textContent = m.text;
    } else if (m.type === "state") onState(m);
  };
  ws.onclose = () => { if (!closedOnPurpose && state) setTimeout(() => connect(code), 1500); };
}

function showScreen(id) {
  for (const s of ["home", "lobby", "game"]) $("#" + s).classList.toggle("hidden", s !== id);
}

// ---------------------------------------------------------------- state updates
function onState(s) {
  const prev = state;
  state = s;
  deadlineAt = performance.now() + s.remaining_s * 1000;
  if (s.phase === "lobby") {
    showScreen("lobby");
    renderLobby();
  } else {
    showScreen("game");
    if (!prev || prev.phase === "lobby" || prev.me.role !== s.me.role) setupGame();
    renderGame();
  }
  $("#end").classList.toggle("hidden", !(s.phase === "escaped" || s.phase === "boom"));
  if (s.phase === "escaped" || s.phase === "boom") renderEnd();
  if (prev && prev.phase === "playing" && s.strikes > prev.strikes) {
    document.body.classList.remove("flash");
    void document.body.offsetWidth;
    document.body.classList.add("flash");
    $("#stage").classList.remove("shake");
    void $("#stage").offsetWidth;
    $("#stage").classList.add("shake");
  }
  tickTimer();
}

function renderLobby() {
  const s = state;
  $("#lobby-code").textContent = s.code;
  for (const card of document.querySelectorAll(".role")) {
    const role = card.dataset.role;
    const who = s.players.find((p) => p.role === role);
    const mine = s.me.role === role;
    card.classList.toggle("mine", mine);
    card.querySelector(".role-who").textContent = who ? (mine ? `You (${who.name})` : who.name) + (who.online ? "" : " · offline") : "";
    card.querySelector(".take").classList.toggle("hidden", !!who);
  }
  const lv = $("#levels");
  lv.replaceChildren(...Object.entries(s.levels).map(([k, l]) =>
    el("div", { class: "level" + (s.level === k ? " on" : ""), onclick: () => send({ type: "level", level: k }) },
      el("b", { text: k[0].toUpperCase() + k.slice(1) }),
      el("small", { text: `${l.modules} modules · ${fmt(l.timer_s)}${l.hard ? " · hard ones" : ""}` }))));
  $("#start").disabled = !s.can_start;
  const n = s.players.length;
  $("#lobby-hint").textContent = n < 2 ? "Waiting for a second player. Send them the room code or the invite link."
    : !s.can_start ? "Each player picks one role." : "Ready. Either player can start.";
}

function setupGame() {
  local.signs = []; local.kp = {}; local.cut = {}; local.needle = {}; local.openPage = null; local.chatSeen = -1;
  $("#game-code").textContent = state.code;
  $("#game-role").textContent = state.me.role === "defuser" ? "💣 Defuser" : "📖 Expert";
  const comp = $("#composer");
  comp.replaceChildren(state.me.role === "defuser" ? defuserComposer() : expertComposer());
  const hdr = $(".topbar");
  hdr.querySelector(".dbg")?.remove();
  if (state.debug) hdr.append(el("a", { class: "btn small dbg", href: `/api/rooms/${state.code}/answer-key`, target: "_blank", text: "Answer key (debug)" }));
}

function renderGame() {
  const s = state;
  $("#top-strikes").replaceChildren(...Array.from({ length: s.max_strikes }, (_, i) => el("div", { class: "strike-led" + (i < s.strikes ? " on" : "") })));
  $("#top-progress").textContent = s.progress ? `Defused ${s.progress.defused} / ${s.progress.total}` : "";
  if (s.me.role === "defuser") renderBomb();
  else if (local.chatSeen !== s.chat.length || !$("#stage .manual")) renderManual();
  renderFeed();
  renderSignChips();
}

function tickTimer() {
  if (!state) return;
  const left = state.phase === "playing" ? Math.max(0, (deadlineAt - performance.now()) / 1000) : state.remaining_s;
  const t = fmt(Math.ceil(left));
  $("#top-timer").textContent = t;
  const seg = $(".seg");
  if (seg) seg.textContent = t;
}

function renderEnd() {
  const s = state;
  const win = s.phase === "escaped";
  $(".end-card").className = "card end-card " + (win ? "win" : "lose");
  $("#end-title").textContent = win ? "POD LAUNCHED!" : "BOOM";
  $("#end-stats").textContent = `Defused ${s.progress.defused} of ${s.progress.total} · Strikes ${s.strikes} · Time left ${fmt(Math.ceil(s.remaining_s))}`;
}

// ---------------------------------------------------------------- feed + composers
function pagesFor(glosses) {
  return pages.filter((p) => glosses.some((g) => p.glosses.includes(g)));
}

function renderFeed() {
  const feed = $("#feed");
  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 40;
  feed.replaceChildren(...state.chat.map((m) => {
    if (m.kind === "event") return el("div", { class: "msg event" + (m.strike ? " strike" : ""), text: m.text });
    if (m.kind === "say") return el("div", { class: "msg say" }, el("span", { class: "who", text: `${m.from} (expert)` }), m.text);
    const box = el("div", { class: "msg signs" }, el("span", { class: "who", text: `${m.from} signed` }),
      el("div", { class: "chips" }, m.glosses.map((g) => el("span", { class: "chip", text: g.toUpperCase() }))));
    if (state.me.role === "expert") {
      const hits = pagesFor(m.glosses);
      box.append(el("div", { class: "page-links" }, hits.length ? "Pages with these words:" : "No page has these words.",
        hits.map((p) => el("button", { class: "btn small", text: p.title, onclick: () => { local.openPage = p.id; renderManual(); } }))));
    }
    return box;
  }));
  if (nearBottom || local.chatSeen !== state.chat.length) feed.scrollTop = feed.scrollHeight;
  local.chatSeen = state.chat.length;
}

function defuserComposer() {
  const all = [...new Set(pages.flatMap((p) => p.glosses))].sort();
  const input = el("input", { placeholder: "Type one sign, press Enter", list: "glosses", autocomplete: "off" });
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const g = input.value.trim().toLowerCase().replace(/\s+/g, "");
    if (g && local.signs.length < 12) { local.signs.push(g); renderSignChips(); }
    input.value = "";
  });
  const sendBtn = el("button", { class: "btn primary", id: "send-signs", text: "Send to expert", onclick: () => {
    if (!local.signs.length) return;
    send({ type: "signs", glosses: local.signs });
    local.signs = [];
    renderSignChips();
    input.focus();
  } });
  return el("div", { class: "composer" },
    el("div", { class: "cam-box", text: "Webcam sign recognition comes next. For now, type each sign." }),
    el("div", { class: "label", text: "Sign what you see, one sign at a time. Dial: sign each picture clockwise from the top, then the one the needle points at." }),
    input,
    el("datalist", { id: "glosses" }, all.map((g) => el("option", { value: g }))),
    el("div", { class: "chips", id: "sign-chips" }),
    sendBtn);
}

function renderSignChips() {
  const box = $("#sign-chips");
  if (!box) return;
  box.replaceChildren(...local.signs.map((g, i) =>
    el("button", { class: "chip", title: "Remove", text: g.toUpperCase() + " ✕", onclick: () => { local.signs.splice(i, 1); renderSignChips(); } })));
  const b = $("#send-signs");
  if (b) b.disabled = !local.signs.length || state.phase !== "playing";
}

function expertComposer() {
  const input = el("input", { placeholder: "Tell the defuser what to do", maxlength: 300, autocomplete: "off" });
  const say = (text) => { if (text.trim()) send({ type: "say", text: text.trim() }); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { say(input.value); input.value = ""; } });
  const quick = ["Which module?", "Sign that again, please.", "Show me more signs.", "Are you sure? Look again."];
  return el("div", { class: "composer" },
    el("div", { class: "label", text: "Reply to the defuser" }),
    input,
    el("div", { class: "chips" }, quick.map((q) => el("button", { class: "btn small", text: q, onclick: () => say(q) }))));
}

// ---------------------------------------------------------------- expert: manual
function renderManual() {
  const lastSigns = [...state.chat].reverse().find((m) => m.kind === "signs");
  const matches = new Set(lastSigns ? pagesFor(lastSigns.glosses).map((p) => p.id) : []);
  const q = local.search.toLowerCase();
  const shown = pages.filter((p) => !q || [p.title, p.topic, ...p.words, ...p.glosses].some((x) => x.toLowerCase().includes(q)));
  const search = el("input", { placeholder: "Search a word or topic", value: local.search });
  search.addEventListener("input", () => {
    local.search = search.value;
    renderManual();
    const s = $(".man-index input");
    s.focus();
    s.setSelectionRange(s.value.length, s.value.length);
  });
  const index = el("div", { class: "man-index" }, search,
    shown.map((p) => el("button", {
      class: "man-entry" + (local.openPage === p.id ? " open" : "") + (matches.has(p.id) ? " match" : ""),
      onclick: () => { local.openPage = p.id; renderManual(); },
    }, `${p.number}. ${p.title}`, el("small", { text: p.topic + (matches.has(p.id) ? " · matches the last signs" : "") }))));
  const p = pageById[local.openPage];
  const page = el("article", { class: "page" });
  if (!p) {
    page.append(el("h2", { text: "Defusal manual" }),
      el("p", { class: "meta", text: "20 puzzles. Each page has its own topic." }),
      el("p", { class: "blank", text: "Pick a page on the left. When the defuser signs, the pages with those words light up." }));
  } else {
    page.append(
      el("h2", { text: `${p.number}. ${p.title}` }),
      el("div", { class: "meta", text: `Topic: ${p.topic} · ${p.widget_name}${p.hard ? " · Hard" : ""}` }),
      el("h3", { text: "How to recognize it" }),
      el("p", { text: p.looks_like }),
      el("div", { class: "words" }, p.glosses.map((g, i) => el("span", { class: "word" },
        p.widget === "wires" ? el("span", { style: `display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid #000;background:${WIRE_COLORS[g]}` })
          : (p.widget === "keypad" ? null : el("span", { text: icon(g).emoji })),
        p.words[i]))),
      el("p", { text: p.reading_order }),
      el("h3", { text: "Rules" }),
      el("p", { text: "Read the rules in order. Do the first rule that is true." }),
      el("ol", {}, p.rules.map((r) => el("li", {},
        r.if == null ? [el("b", { text: "Otherwise: " }), r.then] : [el("b", { text: "If " }), r.if + ": ", el("b", { text: r.then })]))));
  }
  $("#stage").replaceChildren(el("div", { class: "manual" }, index, page));
}

// ---------------------------------------------------------------- defuser: bomb
function sendAct(i, verb, target) { send({ type: "act", module: i, action: { verb, target } }); }

function renderBomb() {
  const mods = state.bomb || [];
  const slots = [el("div", { class: "module timer-mod" },
    el("div", { class: "seg", text: "0:00" }),
    el("div", { class: "strikes" }, Array.from({ length: state.max_strikes }, (_, i) => el("div", { class: "strike-led" + (i < state.strikes ? " on" : "") }))),
    el("div", { class: "serial", text: `SN ${state.code}-${mods.length}` }))];
  mods.forEach((m, i) => {
    slots.push(el("div", { class: "module" + (m.defused ? " defused" : "") },
      el("div", { class: "mod-head" }, el("span", { class: "mod-title", text: `${i + 1} · ${m.title}` }), el("span", { class: "led" })),
      el("div", { class: "mod-body" }, WIDGET[m.widget](m, i))));
  });
  while (slots.length % 3) slots.push(el("div", { class: "module empty-mod" }));
  $("#stage").replaceChildren(el("div", { class: "bomb" }, slots));
}

function iconFace(g) {
  const ic = icon(g);
  return [el("span", { class: "emoji", text: ic.emoji }), ic.caption ? el("span", { class: "cap", text: wordOf(g) }) : null];
}

const WIDGET = {
  wires(m, i) {
    const cut = (local.cut[i] ||= new Set());
    const cols = m.facts.colors;
    const s = svg("svg", { viewBox: "0 0 200 160", class: "wires-svg" });
    s.append(svg("rect", { x: 4, y: 6, width: 16, height: 148, rx: 3, class: "terminal" }),
      svg("rect", { x: 180, y: 6, width: 16, height: 148, rx: 3, class: "terminal" }));
    cols.forEach((c, k) => {
      const y = 22 + k * (116 / Math.max(1, cols.length - 1));
      const g = svg("g", { class: "wire" });
      const d = cut.has(c)
        ? [`M20 ${y} C 50 ${y - 8}, 70 ${y + 6}, 90 ${y + 14}`, `M110 ${y - 14} C 130 ${y - 6}, 150 ${y + 8}, 180 ${y}`]
        : [`M20 ${y} C 70 ${y - 14}, 130 ${y + 14}, 180 ${y}`];
      for (const p of d) {
        g.append(svg("path", { d: p, stroke: "#000", "stroke-width": 11, fill: "none", "stroke-linecap": "round" }));
        g.append(svg("path", { d: p, stroke: WIRE_COLORS[c], "stroke-width": 7, fill: "none", "stroke-linecap": "round", class: "wire-line" }));
      }
      g.append(svg("path", { d: `M20 ${y} L180 ${y}`, stroke: "transparent", "stroke-width": 24, fill: "none" }));
      const title = svg("title");
      title.textContent = c;
      g.append(title);
      if (!cut.has(c)) g.addEventListener("click", () => { cut.add(c); sendAct(i, "cut", { color: c }); renderBomb(); });
      s.append(g);
    });
    return s;
  },

  keypad(m, i) {
    const letters = m.target_words === "letters";
    const buf = (local.kp[i] ||= []);
    const keys = letters ? m.pool : ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
    const press = (k) => { if (buf.length < 6) { buf.push(k); renderBomb(); } };
    return el("div", { class: "keypad" },
      el("div", { class: "lcd", text: m.facts.display.join("").toUpperCase() }),
      el("div", { class: "typed", text: buf.join(" ").toUpperCase() || " " }),
      el("div", { class: "keys " + (letters ? "letters" : "digits") },
        keys.map((k) => el("button", { class: "key", text: k.toUpperCase(), onclick: () => press(k) })),
        el("button", { class: "key fn", text: "CLR", onclick: () => { buf.length = 0; renderBomb(); } }),
        el("button", { class: "key fn", text: "ENT", style: letters ? "grid-column: span 7" : "grid-column: span 4", onclick: () => {
          if (!buf.length) return;
          sendAct(i, "type", { keys: [...buf] });
          buf.length = 0;
          renderBomb();
        } })));
  },

  icons(m, i) {
    return el("div", { class: "icon-grid" }, m.facts.icons.map((g) =>
      el("button", { class: "icon-btn", title: wordOf(g), onclick: () => sendAct(i, "press", { icon: g }) }, iconFace(g))));
  },

  dial(m, i) {
    const opts = m.facts.options;
    const at = local.needle[i] ?? m.facts.needle;
    const box = el("div", { class: "dial" });
    opts.forEach((g, k) => {
      const a = (-90 + (k * 360) / opts.length) * (Math.PI / 180);
      box.append(el("button", {
        class: "dial-opt", title: wordOf(g), style: `left:${50 + 38 * Math.cos(a)}%;top:${50 + 38 * Math.sin(a)}%`,
        onclick: () => { local.needle[i] = g; sendAct(i, "turn", { to: g }); renderBomb(); },
      }, iconFace(g)));
    });
    const k = opts.indexOf(at);
    box.append(el("div", { class: "needle", style: `top:22%;left:calc(50% - 3px);transform:rotate(${(k * 360) / opts.length}deg)` }),
      el("div", { class: "hub" }));
    return box;
  },

  switches(m, i) {
    return el("div", { class: "switch-row" }, m.facts.switches.map((sw) =>
      el("button", { class: `switch ${sw.state}`, title: wordOf(sw.label),
        onclick: () => sendAct(i, "set", { switch: sw.label, state: sw.state === "on" ? "off" : "on" }) },
        iconFace(sw.label), el("div", { class: "track" }, el("div", { class: "knob" })), el("span", { class: "state", text: sw.state.toUpperCase() }))));
  },

  big_button(m, i) {
    // Spec §5.2 shows the faces only while the button is held. Here the screen cycles all
    // the time, so the defuser can sign the faces before acting. Releasing sends the
    // face on screen at that moment.
    const screen = el("div", { class: "bb-screen", "data-faces": m.facts.faces.join(",") });
    screen.textContent = icon(m.facts.faces[faceTick % m.facts.faces.length]).emoji;
    let held = false;
    const btn = el("button", { class: "bb-btn", text: "HOLD" });
    btn.addEventListener("pointerdown", () => { held = true; btn.classList.add("held"); });
    btn.addEventListener("pointerleave", () => { held = false; btn.classList.remove("held"); });
    btn.addEventListener("pointerup", () => {
      if (!held) return;
      held = false;
      btn.classList.remove("held");
      const faces = m.facts.faces;
      sendAct(i, "hold", { release_on: faces[faceTick % faces.length] });
    });
    const n = m.facts.faces.length;
    const pos = el("div", { class: "bb-pos", text: `face ${(faceTick % n) + 1} of ${n}` });
    return el("div", { class: "bb" }, screen, pos, btn);
  },
};

function updateFaces() {
  document.querySelectorAll(".bb-screen").forEach((s) => {
    const faces = s.dataset.faces.split(",");
    s.textContent = icon(faces[faceTick % faces.length]).emoji;
    const pos = s.parentElement.querySelector(".bb-pos");
    if (pos) pos.textContent = `face ${(faceTick % faces.length) + 1} of ${faces.length}`;
  });
}

boot();
