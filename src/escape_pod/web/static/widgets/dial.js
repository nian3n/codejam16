// Owner: Teammate 1 (Game, scenes, widgets)
// Dial: pictures clockwise from the top (the manual's reading order) and a needle.
// Clicking a picture turns the needle there and sends the action.
import { el, iconFace, store, wordOf } from "../core.js";

export function dial(m, i, { sendAct, rerender }) {
  const opts = m.facts.options;
  const at = store.local.needle[i] ?? m.facts.needle;
  const box = el("div", { class: "dial" });
  opts.forEach((g, k) => {
    const a = (-90 + (k * 360) / opts.length) * (Math.PI / 180);
    box.append(el("button", {
      class: "dial-opt", title: wordOf(g), style: `left:${50 + 38 * Math.cos(a)}%;top:${50 + 38 * Math.sin(a)}%`,
      onclick: () => { store.local.needle[i] = g; sendAct(i, "turn", { to: g }); rerender(); },
    }, iconFace(g)));
  });
  const k = opts.indexOf(at);
  box.append(el("div", { class: "needle", style: `top:22%;left:calc(50% - 3px);transform:rotate(${(k * 360) / opts.length}deg)` }),
    el("div", { class: "hub" }));
  return box;
}
