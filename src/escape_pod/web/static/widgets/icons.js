// Owner: Teammate 1 (Game, scenes, widgets)
// Picture buttons: a 2x2 grid; press one.
import { el, iconFace, wordOf } from "../core.js";

export function icons(m, i, { sendAct }) {
  return el("div", { class: "icon-grid" }, m.facts.icons.map((g) =>
    el("button", { class: "icon-btn", title: wordOf(g), onclick: () => sendAct(i, "press", { icon: g }) }, iconFace(g))));
}
