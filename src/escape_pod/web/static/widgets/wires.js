// Owner: Teammate 1 (Game, scenes, widgets)
// Wires: click a wire to cut it. Cut wires stay cut in this browser only;
// the server decides if the cut was right.
import { store, svg, WIRE_COLORS } from "../core.js";

export function wires(m, i, { sendAct, rerender }) {
  const cut = (store.local.cut[i] ||= new Set());
  const cols = m.facts.colors;
  const s = svg("svg", { viewBox: "0 0 200 160", class: "wires-svg" });
  s.append(svg("rect", { x: 4, y: 6, width: 16, height: 148, rx: 3, class: "terminal" }),
    svg("rect", { x: 180, y: 6, width: 16, height: 148, rx: 3, class: "terminal" }));
  cols.forEach((c, k) => {
    const y = 22 + k * (116 / Math.max(1, cols.length - 1));
    const g = svg("g", { class: "wire" });
    const paths = cut.has(c)
      ? [`M20 ${y} C 50 ${y - 8}, 70 ${y + 6}, 90 ${y + 14}`, `M110 ${y - 14} C 130 ${y - 6}, 150 ${y + 8}, 180 ${y}`]
      : [`M20 ${y} C 70 ${y - 14}, 130 ${y + 14}, 180 ${y}`];
    for (const d of paths) {
      g.append(svg("path", { d, stroke: "#000", "stroke-width": 11, fill: "none", "stroke-linecap": "round" }));
      g.append(svg("path", { d, stroke: WIRE_COLORS[c], "stroke-width": 7, fill: "none", "stroke-linecap": "round", class: "wire-line" }));
    }
    // Wide invisible line so thin wires are easy to click.
    g.append(svg("path", { d: `M20 ${y} L180 ${y}`, stroke: "transparent", "stroke-width": 24, fill: "none" }));
    const title = svg("title");
    title.textContent = c;
    g.append(title);
    if (!cut.has(c)) g.addEventListener("click", () => { cut.add(c); sendAct(i, "cut", { color: c }); rerender(); });
    s.append(g);
  });
  return s;
}
