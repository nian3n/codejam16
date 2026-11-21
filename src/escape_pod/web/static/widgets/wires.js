// Owner: Teammate 1 (Game, scenes, widgets)
// Wires: click a wire to cut it. The server checks each cut (Module.apply): a right cut
// stays cut (m.done), a wrong one is a strike and the wire stays whole. Some answers are
// several cuts in a row ("Cut the white wire, then the black wire").
import { svg, WIRE_COLORS } from "../core.js";

export function wireTrace(color, y, cut) {
  const paths = cut
    ? [`M20 ${y} C 50 ${y - 8}, 70 ${y + 6}, 90 ${y + 14}`, `M110 ${y - 14} C 130 ${y - 6}, 150 ${y + 8}, 180 ${y}`]
    : [`M20 ${y} C 70 ${y - 14}, 130 ${y + 14}, 180 ${y}`];
  return paths.flatMap((d) => [
    svg("path", { d, stroke: "#000", "stroke-width": 11, fill: "none", "stroke-linecap": "round" }),
    svg("path", { d, stroke: WIRE_COLORS[color], "stroke-width": 7, fill: "none", "stroke-linecap": "round", class: "wire-line" }),
  ]);
}

export function wires(m, i, { sendAct }) {
  const cut = new Set((m.done || []).filter((a) => a.verb === "cut").map((a) => a.target.color));
  const cols = m.facts.colors;
  const s = svg("svg", { viewBox: "0 0 200 160", class: "wires-svg" });
  s.append(svg("rect", { x: 4, y: 6, width: 16, height: 148, rx: 3, class: "terminal" }),
    svg("rect", { x: 180, y: 6, width: 16, height: 148, rx: 3, class: "terminal" }));
  cols.forEach((c, k) => {
    const y = 22 + k * (116 / Math.max(1, cols.length - 1));
    const g = svg("g", { class: "wire" });
    g.append(...wireTrace(c, y, cut.has(c)));
    // Wide invisible line so thin wires are easy to click.
    g.append(svg("path", { d: `M20 ${y} L180 ${y}`, stroke: "transparent", "stroke-width": 24, fill: "none" }));
    const title = svg("title");
    title.textContent = c;
    g.append(title);
    if (!cut.has(c) && !m.defused) g.addEventListener("click", () => sendAct(i, "cut", { color: c }));
    s.append(g);
  });
  return s;
}
