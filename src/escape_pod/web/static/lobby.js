// Owner: Teammate 1 (Game, scenes, widgets)
// Lobby: room code, role cards, level picker, start button.
import { $, el, fmt, send, store } from "./core.js";

export function renderLobby() {
  const s = store.state;
  $("#lobby-code").textContent = s.code;
  for (const card of document.querySelectorAll(".role")) {
    const role = card.dataset.role;
    const who = s.players.find((p) => p.role === role);
    const mine = s.me.role === role;
    card.classList.toggle("mine", mine);
    card.querySelector(".role-who").textContent = who ? (mine ? `You (${who.name})` : who.name) + (who.online ? "" : " · offline") : "";
    card.querySelector(".take").classList.toggle("hidden", !!who);
  }
  $("#levels").replaceChildren(...Object.entries(s.levels).map(([k, l]) => k === "custom"
    ? customLevel(l, s.level === k)
    : el("div", { class: "level" + (s.level === k ? " on" : ""), onclick: () => send({ type: "level", level: k }) },
      el("b", { text: k[0].toUpperCase() + k.slice(1) }),
      el("small", { text: `${l.modules} modules · ${fmt(l.timer_s)}${l.hard ? " · hard ones" : ""}` }))));
  $("#start").disabled = !s.can_start;
  // Solo: no roles to pick, nobody to invite, so no room code either. The video dock
  // stays: it shows only the self-view (rtc.js), so the player can frame their hands.
  for (const sel of [".roles", ".room-code"]) $(sel).classList.toggle("hidden", !!s.solo);
  // Why we are here, e.g. "Ana ended the game." or "Ben left the room."
  const last = s.chat.at(-1);
  $("#lobby-note").textContent = last?.kind === "event" ? last.text : "";
}

/** The "Custom" level card: the players pick 1-5 modules and 1-20 minutes (config.py). */
function customLevel(l, on) {
  const pick = (modules, timer_s) => send({ type: "level", level: "custom", modules, timer_s });
  const [mLo, mHi] = l.range.modules;
  const [tLo, tHi] = l.range.timer_s;
  const stepper = (label, value, text, lo, hi, step, set) => el("div", { class: "stepper" },
    el("span", { class: "stepper-label", text: label }),
    el("button", { class: "btn small", type: "button", text: "−", disabled: value - step < lo ? "" : null,
      onclick: (e) => { e.stopPropagation(); set(value - step); } }),
    el("b", { class: "stepper-value", text }),
    el("button", { class: "btn small", type: "button", text: "+", disabled: value + step > hi ? "" : null,
      onclick: (e) => { e.stopPropagation(); set(value + step); } }));
  return el("div", { class: "level custom" + (on ? " on" : ""), onclick: () => pick(l.modules, l.timer_s) },
    el("b", { text: "Custom" }),
    stepper("Modules", l.modules, String(l.modules), mLo, mHi, 1, (n) => pick(n, l.timer_s)),
    stepper("Time", l.timer_s, fmt(l.timer_s), tLo, tHi, 60, (t) => pick(l.modules, t)));
}

export function bindLobby() {
  $("#copy-link").onclick = () => {
    navigator.clipboard?.writeText(`${location.origin}/?room=${store.state.code}`);
    $("#copy-link").textContent = "Copied!";
    setTimeout(() => ($("#copy-link").textContent = "Copy invite link"), 1500);
  };
  $("#start").onclick = () => send({ type: "start" });
  document.querySelectorAll(".role .take").forEach((b) => {
    b.onclick = () => send({ type: "role", role: b.closest(".role").dataset.role });
  });
}
