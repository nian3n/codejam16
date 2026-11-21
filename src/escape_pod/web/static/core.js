// Owner: Teammate 1 (Game, scenes, widgets)
// Shared helpers and the one client-side store. Every other module imports from here;
// this file imports nothing, so there are no import cycles.

export const $ = (s) => document.querySelector(s);

export function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "style") n.style.cssText = v;
    else n.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) n.append(c);
  return n;
}

const SVG_NS = "http://www.w3.org/2000/svg";
export function svg(tag, attrs = {}) {
  const n = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

export const fmt = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// state: the last view the server sent. local: things only this browser knows
// (signs not sent yet, keypad buffers, cut wires, the open manual page...).
export const store = {
  ws: null,
  state: null,
  icons: {},
  pages: [],
  pageById: {},
  deadlineAt: 0,
  faceTick: 0,
  local: { init: null, signs: [], signChips: [], kp: {}, ic: {}, cut: {}, needle: {}, openPage: null, search: "", chatSeen: -1 },
};

export function resetLocal() {
  store.local = { init: null, signs: [], signChips: [], kp: {}, ic: {}, cut: {}, needle: {}, openPage: null, search: store.local.search, chatSeen: -1 };
}

export function send(msg) {
  if (store.ws && store.ws.readyState === 1) store.ws.send(JSON.stringify(msg));
}

export const WIRE_COLORS = { red: "#e03a3a", blue: "#3f6fe6", green: "#3fb85a", yellow: "#f2d33b", black: "#1a1a1a",
  white: "#f2f2f2", brown: "#8a5a2b", orange: "#f28a1e" };

export function icon(g) { return store.icons[g] || { emoji: "❔", caption: true }; }
export function wordOf(g) { return { frenchfries: "french fries", icecream: "ice cream", tv: "TV" }[g] || g; }

/** Emoji plus an optional caption, for any widget that shows a picture of a gloss. */
export function iconFace(g) {
  const ic = icon(g);
  return [el("span", { class: "emoji", text: ic.emoji }), ic.caption ? el("span", { class: "cap", text: wordOf(g) }) : null];
}
