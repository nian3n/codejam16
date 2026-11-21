// Owner: Teammate 1 (Game, scenes, widgets)
// Defuser view: the bomb casing, the timer module and one slot per module.
// Each widget lives in widgets/<name>.js; to add one, register it in widgets/index.js.
import { $, el, send, store } from "./core.js";
import { WIDGETS } from "./widgets/index.js";

function sendAct(i, verb, target) {
  send({ type: "act", module: i, action: { verb, target } });
}

export function renderBomb() {
  const s = store.state;
  const mods = s.bomb || [];
  const ctx = { sendAct, rerender: renderBomb };
  const slots = [el("div", { class: "module timer-mod" },
    el("div", { class: "seg", text: "0:00" }),
    el("div", { class: "strikes" }, Array.from({ length: s.max_strikes }, (_, i) => el("div", { class: "strike-led" + (i < s.strikes ? " on" : "") }))),
    el("div", { class: "serial", text: `SN ${s.code}-${mods.length}` }))];
  mods.forEach((m, i) => {
    slots.push(el("div", { class: "module" + (m.defused ? " defused" : "") },
      el("div", { class: "mod-head" }, el("span", { class: "mod-title", text: `${i + 1} · ${m.title}` }), el("span", { class: "led" })),
      el("div", { class: "mod-body" }, WIDGETS[m.widget](m, i, ctx))));
  });
  while (slots.length % 3) slots.push(el("div", { class: "module empty-mod" }));
  $("#stage").replaceChildren(el("div", { class: "bomb" }, slots));
}
