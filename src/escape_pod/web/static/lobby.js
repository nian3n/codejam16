// Owner: Teammate 1 (Game, scenes, widgets)
// Lobby: room code, role cards, level picker, start button.
import { $, el, fmt, send, store } from "./core.js";
import { roleName } from "./guided.js";

export function renderLobby() {
  const s = store.state;
  if ($("#lobby-code").textContent !== s.code) {
    $("#invite-fallback").classList.add("hidden");
    $("#invite-status").textContent = "";
  }
  $("#lobby-code").textContent = s.code;
  $("#lobby-mode").textContent = s.guided ? "Guided room" : "Classic room";
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
    card.querySelector(".role-who").textContent = who ? (mine ? "Your role" : who.name) + (who.online ? "" : " · offline") : "";
    const take = card.querySelector(".take");
    take.disabled = false;
    take.classList.toggle("hidden", !!who);
    take.setAttribute("aria-label", `Choose ${card.querySelector("h2").textContent}`);
  }
  $("#levels").classList.toggle("hidden", !!s.guided);
  $("#levels").replaceChildren(...Object.entries(s.levels).map(([k, l]) =>
    el("button", { type: "button", class: "btn level" + (s.level === k ? " on" : ""),
      "aria-pressed": String(s.level === k), onclick: () => send({ type: "level", level: k }) },
      el("b", { text: k[0].toUpperCase() + k.slice(1) }),
      el("small", { text: `${l.modules} modules · ${fmt(l.timer_s)}${l.hard ? " · hard ones" : ""}` }))));
  $("#start").disabled = !s.can_start;
  $("#start").textContent = s.guided ? "Begin untimed practice" : "Start the game";
  $("#lobby-hint").textContent = s.players.filter((player) => player.online).length < 2
    ? "Waiting for your partner. Share the room code or invite link."
    : !s.can_start ? "Choose one role each to continue." : s.guided
      ? "Both roles are set. You’ll check your cameras in the untimed practice round."
      : "Both roles are set. Either player can start.";
}

export function bindLobby() {
  $("#copy-link").onclick = async () => {
    const address = new URL(`/?room=${store.state.code}`, location.origin).href;
    try {
      await navigator.clipboard.writeText(address);
      $("#invite-fallback").classList.add("hidden");
      $("#invite-status").textContent = "Invite link copied.";
    } catch {
      $("#invite-fallback").classList.remove("hidden");
      $("#invite-address").value = address;
      $("#invite-address").focus();
      $("#invite-address").select();
      $("#invite-status").textContent = "Copy the selected link or share the room code.";
    }
  };
  $("#start").onclick = () => send({ type: "start" });
  document.querySelectorAll(".role .take").forEach((b) => {
    b.onclick = () => send({ type: "role", role: b.closest(".role").dataset.role });
  });
}
