// Owner: Teammate 1 (Game, scenes, widgets)
// Lobby: room code, role cards, level picker, start button.
import { $, el, fmt, send, store } from "./core.js";
import { roleName } from "./guided.js";

export function renderLobby() {
  const s = store.state;
  $("#lobby-code").textContent = s.code;
  for (const card of document.querySelectorAll(".role")) {
    const role = card.dataset.role;
    const who = s.players.find((p) => p.role === role);
    const mine = s.me.role === role;
    const title = role === "defuser" ? "Defuser" : "Expert";
    card.querySelector("h2").textContent = s.guided ? roleName(role, s.guided.swapped) : title;
    card.querySelector("p").textContent = s.guided
      ? role === "defuser" ? "See the private clues and sign them to your partner." : "Watch your partner sign and operate the control panel."
      : role === "defuser" ? "You see the bomb. You sign what you see. You cut, press and turn." : "You read the manual. You never see the bomb. You tell the defuser what to do.";
    card.classList.toggle("mine", mine);
    card.querySelector(".role-who").textContent = who ? (mine ? `You (${who.name})` : who.name) + (who.online ? "" : " · offline") : "";
    card.querySelector(".take").classList.toggle("hidden", !!who);
  }
  $("#levels").classList.toggle("hidden", !!s.guided);
  $("#levels").replaceChildren(...Object.entries(s.levels).map(([k, l]) =>
    el("div", { class: "level" + (s.level === k ? " on" : ""), onclick: () => send({ type: "level", level: k }) },
      el("b", { text: k[0].toUpperCase() + k.slice(1) }),
      el("small", { text: `${l.modules} modules · ${fmt(l.timer_s)}${l.hard ? " · hard ones" : ""}` }))));
  $("#start").disabled = !s.can_start;
  $("#start").textContent = s.guided ? "Begin untimed practice" : "Start the game";
  $("#lobby-hint").textContent = s.players.length < 2
    ? "Waiting for a second player. Send them the room code or the invite link."
    : !s.can_start ? "Both players connect and choose a role." : s.guided
      ? "Frame your face and hands once practice opens. There’s no time limit for the first clue."
      : "Ready. Either player can start.";
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
