// Owner: Teammate 1 (Game, scenes, widgets)
// Keypad: a display plus digit or letter keys. ENT sends the typed sequence.
import { el, store } from "../core.js";

export function keypad(m, i, { sendAct, rerender }) {
  const letters = m.target_words === "letters";
  const buf = (store.local.kp[i] ||= []);
  const accepted = m.done?.find((action) => action.verb === "type")?.target.keys;
  const keys = letters ? m.pool : ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
  const press = (k) => { if (buf.length < 6) { buf.push(k); rerender(); } };
  return el("div", { class: "keypad" },
    el("div", { class: "lcd", text: m.facts.display.join("").toUpperCase() }),
    el("div", { class: "typed", text: (accepted ?? buf).join(" ").toUpperCase() || " " }),
    el("div", { class: "keys " + (letters ? "letters" : "digits") },
      keys.map((k) => el("button", { class: "key", text: k.toUpperCase(), onclick: () => press(k) })),
      el("button", { class: "key fn", text: "CLR", onclick: () => { buf.length = 0; rerender(); } }),
      el("button", { class: "key fn", text: "ENT", style: letters ? "grid-column: span 7" : "grid-column: span 4", onclick: () => {
        if (!buf.length) return;
        sendAct(i, "type", { keys: [...buf] });
        buf.length = 0;
        rerender();
      } })));
}
