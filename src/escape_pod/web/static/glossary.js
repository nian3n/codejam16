// Owner: Teammate 1 (Game, scenes, widgets)
// The sign dictionary: every game word, A to Z, with a looping PopSign clip.
//
// Both roles can open it at any time during a game (the timer keeps running).
// It always lists ALL the words, never only this bomb's: a list of this bomb's
// words would tell the handler which topics are on the bomb (spec rule 3).
// Clips and the credit line come from /signs/index.json (signs/fetch_popsign.py).
import { $, el, icon, store, wordOf, WIRE_COLORS } from "./core.js";

const HANDSHAPE_PAGES = new Set(["numbers"]);  // digits: not in PopSign (spec 6.4)
// The signs that run the capture (spec 6.2). Not on any manual page, so listed here.
const CONTROL_SIGNS = { yes: "👍", no: "👎", finish: "🏁" };
let clips = null;        // {credit, clips: {gloss: {file, ...}}}, loaded on first open
let entries = [];        // [{gloss, word, topic}], sorted A to Z
let query = "";
let current = null;      // the open gloss

const root = el("div", { id: "glossary", class: "glossary hidden", role: "dialog", "aria-label": "Sign dictionary" });

// Colors have no emoji: show a swatch of the wire color instead.
function mark(g, cls) {
  if (WIRE_COLORS[g]) return el("span", { class: `${cls} swatch`, style: `background:${WIRE_COLORS[g]}` });
  return el("span", { class: cls, text: CONTROL_SIGNS[g] || icon(g).emoji });
}

export function bindGlossary() {
  document.body.append(root);
  $("#open-glossary").onclick = () => (root.classList.contains("hidden") ? openGlossary() : closeGlossary());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !root.classList.contains("hidden")) closeGlossary(); });
}

export async function openGlossary(gloss = null) {
  if (!clips) {
    clips = await fetch("/signs/index.json").then((r) => (r.ok ? r.json() : { clips: {} })).catch(() => ({ clips: {} }));
  }
  if (!entries.length) {
    entries = store.pages.filter((p) => !HANDSHAPE_PAGES.has(p.id))
      .flatMap((p) => p.glosses.map((g) => ({ gloss: g, word: wordOf(g), topic: p.topic })))
      .concat(Object.keys(CONTROL_SIGNS).map((g) => ({ gloss: g, word: g, topic: "game controls" })))
      .sort((a, b) => a.word.localeCompare(b.word));
  }
  if (gloss) current = gloss;
  root.classList.remove("hidden");
  $("#open-glossary").classList.add("on");
  render();
  root.querySelector(".gl-search")?.focus();
}

export function closeGlossary() {
  root.classList.add("hidden");
  $("#open-glossary")?.classList.remove("on");
  root.querySelector("video")?.pause();
}

function render() {
  const q = query.trim().toLowerCase();
  const shown = entries.filter((e) => !q || e.word.includes(q) || e.gloss.includes(q) || e.topic.includes(q));
  // Thumb index: one tab per letter that has words; a tab jumps the list to that letter.
  const letters = [...new Set(entries.map((e) => e.word[0].toUpperCase()))];
  const list = el("div", { class: "gl-list" });
  let last = "";
  for (const e of shown) {
    const L = e.word[0].toUpperCase();
    if (L !== last) { list.append(el("div", { class: "gl-letter", id: `gl-${L}`, text: L })); last = L; }
    list.append(el("button", { class: "gl-row" + (e.gloss === current ? " open" : ""), onclick: () => { current = e.gloss; render(); } },
      mark(e.gloss, "gl-emoji"),
      el("b", { text: e.word }),
      el("i", { text: e.topic })));
  }
  if (!shown.length) list.append(el("p", { class: "gl-none", text: `No word matches "${query}".` }));
  list.append(el("p", { class: "gl-note", text: "Numbers 0 to 9 are hand shapes, not in this dictionary yet." }));

  const search = el("input", { class: "gl-search", placeholder: "Look up a word", value: query, autocomplete: "off" });
  search.addEventListener("input", () => {
    query = search.value;
    render();
    const s = root.querySelector(".gl-search");
    s.focus();
    s.setSelectionRange(s.value.length, s.value.length);
  });

  root.replaceChildren(
    el("div", { class: "gl-book" },
      el("header", { class: "gl-head" },
        el("h2", { text: "Field Sign Dictionary" }),
        search,
        el("button", { class: "btn small", text: "✕ Close", onclick: closeGlossary })),
      el("nav", { class: "gl-tabs" }, ...letters.map((L) => el("button", {
        text: L, onclick: () => { query = ""; render(); root.querySelector(`#gl-${L}`)?.scrollIntoView({ block: "start" }); },
      }))),
      list,
      entryPage()));
  root.querySelector(".gl-row.open")?.scrollIntoView({ block: "nearest" });
}

function entryPage() {
  const e = entries.find((x) => x.gloss === current);
  if (!e) {
    return el("article", { class: "gl-entry blank" },
      el("p", { text: "Pick a word on the left to see how to sign it." }));
  }
  const clip = clips?.clips?.[e.gloss];
  const media = clip
    ? el("video", { class: "gl-video", src: `/signs/${clip.file}`, autoplay: "", loop: "", muted: "", playsinline: "", preload: "auto" })
    : el("div", { class: "gl-video missing", text: "No clip yet for this word." });
  if (clip) media.muted = true;  // the attribute alone does not satisfy autoplay rules everywhere
  return el("article", { class: "gl-entry" },
    el("div", { class: "gl-word" }, mark(e.gloss, "gl-mark"), el("h3", { text: e.word })),
    el("p", { class: "gl-pos", text: `topic: ${e.topic}` }),
    media,
    el("p", { class: "gl-how", text: "Watch the clip. It repeats. Sign it the same way, facing the camera." }),
    el("p", { class: "gl-credit", text: clips?.credit || "" }));
}
