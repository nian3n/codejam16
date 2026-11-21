// Owner: Teammate 1 (Game, scenes, widgets)
// Picture buttons: a 2x2 grid. A tap presses one button (verb "press").
//
// ORDER mode, for the rules "press all the buttons in alphabetical order": each tap
// numbers a button, and the last tap sends the whole order (verb "press_all"). The
// toggle is on every icon panel, so it gives nothing away about the module's rules.
import { el, iconFace, store, wordOf } from "../core.js";

export function icons(m, i, { sendAct, rerender }) {
  const seq = (store.local.ic[i] ||= { on: false, picks: [] });
  const n = m.facts.icons.length;
  const tap = (g) => {
    if (!seq.on) { sendAct(i, "press", { icon: g }); return; }
    if (seq.picks.includes(g)) return;
    seq.picks.push(g);
    if (seq.picks.length === n) {
      sendAct(i, "press_all", { icons: [...seq.picks] });
      seq.picks = [];
      seq.on = false;
    }
    rerender();
  };
  const toggle = () => { seq.on = !seq.on; seq.picks = []; rerender(); };
  return el("div", { class: "icon-mod" + (seq.on ? " ordering" : "") },
    el("div", { class: "icon-grid" }, m.facts.icons.map((g) => {
      const k = seq.picks.indexOf(g);
      return el("button", { class: "icon-btn" + (k >= 0 ? " picked" : ""), title: wordOf(g), onclick: () => tap(g) },
        iconFace(g), k >= 0 ? el("span", { class: "pick-n", text: String(k + 1) }) : null);
    })),
    el("div", { class: "icon-bar" },
      el("button", { class: "key fn order-btn" + (seq.on ? " on" : ""), type: "button", onclick: toggle,
        title: "Press all the buttons in a row: tap them in order. The last tap sends.",
        text: seq.on ? `ORDER ${seq.picks.length}/${n} · CANCEL` : "ORDER 1-2-3-4" })));
}
