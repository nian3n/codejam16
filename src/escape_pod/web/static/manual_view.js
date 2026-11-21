// Owner: Teammate 1 (Game, scenes, widgets)
// Expert view: the manual index (with search) and the open page.
// Pages come from /api/manual, built from the same rules the server checks with.
import { $, el, icon, store, WIRE_COLORS } from "./core.js";

/** The pages whose words include any of these glosses. Every gloss is in one pool only. */
export function pagesFor(glosses) {
  return store.pages.filter((p) => glosses.some((g) => p.glosses.includes(g)));
}

export function openPage(id) {
  store.local.openPage = id;
  renderManual();
}

export function renderManual() {
  const { state, local, pages, pageById } = store;
  const lastSigns = [...state.chat].reverse().find((m) => m.kind === "signs");
  const matches = new Set(lastSigns ? pagesFor(lastSigns.glosses).map((p) => p.id) : []);
  const q = local.search.toLowerCase();
  const shown = pages.filter((p) => !q || [p.title, p.topic, ...p.words, ...p.glosses].some((x) => x.toLowerCase().includes(q)));
  const search = el("input", { placeholder: "Search a word or topic", value: local.search });
  search.addEventListener("input", () => {
    local.search = search.value;
    renderManual();
    const s = $(".man-index input");
    s.focus();
    s.setSelectionRange(s.value.length, s.value.length);
  });
  const index = el("div", { class: "man-index" }, search,
    shown.map((p) => el("button", {
      class: "man-entry" + (local.openPage === p.id ? " open" : "") + (matches.has(p.id) ? " match" : ""),
      onclick: () => openPage(p.id),
    }, `${p.number}. ${p.title}`, el("small", { text: p.topic + (matches.has(p.id) ? " · matches the last signs" : "") }))));
  $("#stage").replaceChildren(el("div", { class: "manual" }, index, pageView(pageById[local.openPage])));
}

function pageView(p) {
  const page = el("article", { class: "page" });
  if (!p) {
    page.append(el("h2", { text: "Defusal manual" }),
      el("p", { class: "meta", text: "20 puzzles. Each page has its own topic." }),
      el("p", { class: "blank", text: "Pick a page on the left. When the defuser signs, the pages with those words light up." }));
    return page;
  }
  const swatch = (g) => el("span", { style: `display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid #000;background:${WIRE_COLORS[g]}` });
  page.append(
    el("h2", { text: `${p.number}. ${p.title}` }),
    el("div", { class: "meta", text: `Topic: ${p.topic} · ${p.widget_name}${p.hard ? " · Hard" : ""}` }),
    el("h3", { text: "How to recognize it" }),
    el("p", { text: p.looks_like }),
    el("div", { class: "words" }, p.glosses.map((g, i) => el("span", { class: "word" },
      p.widget === "wires" ? swatch(g) : p.widget === "keypad" ? null : el("span", { text: icon(g).emoji }),
      p.words[i]))),
    el("p", { text: p.reading_order }),
    el("h3", { text: "Rules" }),
    el("p", { text: "Read the rules in order. Do the first rule that is true." }),
    el("ol", {}, p.rules.map((r) => el("li", {},
      r.if == null ? [el("b", { text: "Otherwise: " }), r.then] : [el("b", { text: "If " }), r.if + ": ", el("b", { text: r.then })]))));
  return page;
}
