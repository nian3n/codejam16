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
  $("#levels").replaceChildren(...Object.entries(s.levels).map(([k, l]) =>
    el("div", { class: "level" + (s.level === k ? " on" : ""), onclick: () => send({ type: "level", level: k }) },
      el("b", { text: k[0].toUpperCase() + k.slice(1) }),
      el("small", { text: `${l.modules} modules · ${fmt(l.timer_s)}${l.hard ? " · hard ones" : ""}` }))));
  $("#start").disabled = !s.can_start;
  $("#lobby-hint").textContent = s.players.length < 2
    ? "Waiting for a second player. Send them the room code or the invite link."
    : !s.can_start ? "Each player picks one role." : "Ready. Either player can start.";
  // Why we are here, e.g. "Ana ended the game." or "Ben left the room."
  const last = s.chat.at(-1);
  $("#lobby-note").textContent = last?.kind === "event" ? last.text : "";
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
