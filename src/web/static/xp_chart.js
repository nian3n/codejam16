// Owner: Teammate 1 (Game, scenes, widgets)
// The lobby graph of one profile's XP over its rounds (spec 2026-11-21-xp-history-design).
// Plain SVG: no chart library. The data comes from xp_store.history().
import { el, svg } from "./core.js";
import { xpForNext } from "./xp_levels.js";

const W = 520, H = 150, PAD = { l: 40, r: 12, t: 12, b: 22 };

/** The XP at which each level starts: level 2 at 250, level 3 at 600, ... */
function thresholds(upTo) {
  const out = [];
  for (let level = 1, at = 0; at <= upTo; level++) {
    at += xpForNext(level);
    out.push({ level: level + 1, at });
  }
  return out;
}

const day = (ms) => new Date(ms).toLocaleDateString(undefined, { day: "numeric", month: "short" });

export function renderXpHistory(box, hist) {
  if (!hist.rounds.length) {
    box.replaceChildren(el("p", { class: "xp-history-empty", text: "Play a round to start your history." }));
    return;
  }
  const points = [{ total: hist.start, label: `Earlier progress · ${hist.start} XP` },
    ...hist.rounds.map((r) => ({ total: r.total,
      label: `${day(r.at)} · ${r.won ? "Defused" : "Detonation"} · +${r.gain} XP · ${r.total} XP in all` }))];
  const lo = Math.min(...points.map((p) => p.total));
  const hi = Math.max(...points.map((p) => p.total));
  // Show the next level line too, so the player sees the goal above the last point.
  const next = thresholds(hi).find((t) => t.at > hi);
  const top = Math.max(next.at, lo + 1);
  const x = (i) => PAD.l + (W - PAD.l - PAD.r) * (points.length === 1 ? 0.5 : i / (points.length - 1));
  const y = (v) => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo) / (top - lo));

  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "xp-chart", role: "img",
    "aria-label": `XP over your last ${hist.rounds.length} rounds: from ${points[0].total} to ${hi} XP` });
  for (const t of thresholds(top)) {
    if (t.at < lo || t.at > top) continue;
    chart.append(svg("line", { class: "xp-level-line", x1: PAD.l, x2: W - PAD.r, y1: y(t.at), y2: y(t.at) }));
    const label = svg("text", { class: "xp-level-label", x: W - PAD.r, y: y(t.at) - 3, "text-anchor": "end" });
    label.textContent = `Level ${t.level}`;
    chart.append(label);
  }
  for (const v of [lo, top]) {
    const tick = svg("text", { class: "xp-axis", x: PAD.l - 6, y: y(v) + 4, "text-anchor": "end" });
    tick.textContent = v;
    chart.append(tick);
  }
  chart.append(svg("polyline", { class: "xp-line", points: points.map((p, i) => `${x(i)},${y(p.total)}`).join(" ") }));
  points.forEach((p, i) => {
    const dot = svg("circle", { class: "xp-dot" + (i === 0 ? " start" : ""), cx: x(i), cy: y(p.total), r: 4 });
    const title = svg("title");
    title.textContent = p.label;
    dot.append(title);
    chart.append(dot);
  });
  const caption = svg("text", { class: "xp-axis", x: PAD.l, y: H - 6 });
  caption.textContent = "earlier";
  const last = svg("text", { class: "xp-axis", x: W - PAD.r, y: H - 6, "text-anchor": "end" });
  last.textContent = "last round";
  chart.append(caption, last);
  box.replaceChildren(el("div", { class: "xp-history-head", text: "Your XP over your last rounds" }), chart);
}
