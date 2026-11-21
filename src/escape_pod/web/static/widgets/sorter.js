// Owner: Teammate 1 (Game, scenes, widgets)
// Sorter: pictures on a tray, two boxes below. Drag a picture into a box (verb "sort",
// target {item, box}). Each drop is one step that the server checks: a right drop stays
// in its box (m.done), a wrong one is a strike and the picture stays on the tray.
//
// Tap to sort works too (tap a picture, then a box), for touch screens and trackpads,
// where HTML drag and drop is awkward. The tray keeps an empty slot where a sorted
// picture was, so "the first picture" stays where the manual's reading order says.
import { el, iconFace, store, wordOf } from "../core.js";

export function sorter(m, i, { sendAct, rerender }) {
  const st = (store.local.sort[i] ||= { pick: null });
  const boxOf = {};
  for (const a of m.done || []) if (a.verb === "sort") boxOf[a.target.item] = a.target.box;
  const drop = (g, box) => {
    st.pick = null;
    if (!boxOf[g]) sendAct(i, "sort", { item: g, box });
    rerender();
  };
  const card = (g) => el("button", {
    class: "icon-btn sort-item" + (st.pick === g ? " picked" : ""), type: "button", draggable: "true", title: wordOf(g),
    ondragstart: (e) => { e.dataTransfer.setData("text/plain", g); e.dataTransfer.effectAllowed = "move"; },
    onclick: () => { st.pick = st.pick === g ? null : g; rerender(); },
  }, iconFace(g));
  const box = (side) => el("div", {
    class: "sort-box" + (st.pick ? " ready" : ""), "data-box": side,
    ondragover: (e) => { e.preventDefault(); e.currentTarget.classList.add("over"); },
    ondragleave: (e) => e.currentTarget.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); const g = e.dataTransfer.getData("text/plain"); if (g) drop(g, side); },
    onclick: () => { if (st.pick) drop(st.pick, side); },
  },
    el("span", { class: "sort-label", text: side === "left" ? "LEFT BOX" : "RIGHT BOX" }),
    el("div", { class: "sort-in" }, m.facts.items.filter((g) => boxOf[g] === side).map((g) =>
      el("div", { class: "icon-btn sort-item done", title: wordOf(g) }, iconFace(g), el("span", { class: "pick-n", text: "✓" })))));
  return el("div", { class: "sorter" },
    el("div", { class: "sort-tray" }, m.facts.items.map((g) => boxOf[g] ? el("div", { class: "sort-slot" }) : card(g))),
    el("div", { class: "sort-boxes" }, box("left"), box("right")));
}
