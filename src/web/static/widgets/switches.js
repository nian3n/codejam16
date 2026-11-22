// Owner: Teammate 1 (Game, scenes, widgets)
// Switches: a row of on/off levers. Clicking one asks to flip it; the server
// keeps the real state, so a wrong flip shows as a strike, not a moved lever.
import { el, iconFace, wordOf } from "../core.js";

export function switches(m, i, { sendAct }) {
  return el("div", { class: "switch-row" }, m.facts.switches.map((sw) =>
    el("button", { class: `switch ${sw.state}`, title: wordOf(sw.label),
      onclick: () => sendAct(i, "set", { switch: sw.label, state: sw.state === "on" ? "off" : "on" }) },
      iconFace(sw.label), el("div", { class: "track" }, el("div", { class: "knob" })),
      el("span", { class: "state", text: sw.state.toUpperCase() }))));
}
