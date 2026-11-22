// Owner: Teammate 1 (Game, scenes, widgets)
// The working controls that sit in the case's recessed module bays.
// Each widget lives in widgets/<name>.js; to add one, register it in widgets/index.js.
import { $, el, send, store } from "./core.js";
import { WIDGETS } from "./widgets/index.js";
import { playSnip, playToggle } from "./sfx.js";

function sendAct(i, verb, target) {
  // Buttons click through sfx.wireControlSounds. Wires are SVG paths and switches flip, so they sound here.
  if (verb === "cut") playSnip();
  else if (verb === "set") playToggle();
  send({ type: "act", round_id: store.state.round_id, module: i, action: { verb, target } });
}

export function renderBomb(force = false) {
  const s = store.state;
  const mods = s.bomb || [];
  const stage = $("#stage");
  const key = JSON.stringify([s.round_id, mods]);
  if (!force && stage.firstElementChild?.dataset.bombView === key) return;
  const ctx = { sendAct, rerender: () => renderBomb(true) };
  const slots = mods.map((m, i) => (
    el("div", { class: "module" + (m.defused ? " defused" : "") },
      el("div", { class: "mod-head" }, el("span", { class: "mod-title", text: `${i + 1} · ${m.title}` }), el("span", { class: "led" })),
      el("div", { class: "mod-body", inert: m.defused ? "" : null }, WIDGETS[m.widget](m, i, ctx)))
  ));
  stage.replaceChildren(el("div", { class: "bomb", "data-count": mods.length, "data-bomb-view": key }, slots));
}
