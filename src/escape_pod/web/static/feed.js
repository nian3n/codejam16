// Owner: Teammate 1 (Game, scenes, widgets)
// The side panel: the shared message feed, the defuser's sign composer and the
// expert's reply box. The webcam recognizer (Teammate 3) will replace the typed
// input in defuserComposer() and push confirmed glosses into store.local.signs.
import { $, el, send, store } from "./core.js";
import { openPage, pagesFor } from "./manual_view.js";

export function renderFeed() {
  const { state, local } = store;
  const feed = $("#feed");
  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 40;
  feed.replaceChildren(...state.chat.map((m) => {
    if (m.kind === "event") return el("div", { class: "msg event" + (m.strike ? " strike" : ""), text: m.text });
    if (m.kind === "say") return el("div", { class: "msg say" }, el("span", { class: "who", text: `${m.from} (HQ)` }), m.text);
    const box = el("div", { class: "msg signs" }, el("span", { class: "who", text: `${m.from} signed` }),
      el("div", { class: "chips" }, m.glosses.map((g) => el("span", { class: "chip", text: g.toUpperCase() }))));
    if (state.me.role === "expert") {
      const hits = pagesFor(m.glosses);
      box.append(el("div", { class: "page-links" }, hits.length ? "Pages with these words:" : "No page has these words.",
        hits.map((p) => el("button", { class: "btn small", text: p.title, onclick: () => openPage(p.id) }))));
    }
    return box;
  }));
  if (nearBottom || local.chatSeen !== state.chat.length) feed.scrollTop = feed.scrollHeight;
  local.chatSeen = state.chat.length;
}

export function defuserComposer() {
  const all = [...new Set(store.pages.flatMap((p) => p.glosses))].sort();
  const input = el("input", { placeholder: "Type one sign, press Enter", list: "glosses", autocomplete: "off" });
  input.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const g = input.value.trim().toLowerCase().replace(/\s+/g, "");
    if (g && store.local.signs.length < 12) { store.local.signs.push(g); renderSignChips(); }
    input.value = "";
  });
  const sendBtn = el("button", { class: "btn primary", id: "send-signs", text: "Send to HQ", onclick: () => {
    if (!store.local.signs.length) return;
    send({ type: "signs", glosses: store.local.signs });
    store.local.signs = [];
    renderSignChips();
    input.focus();
  } });
  return el("div", { class: "composer" },
    el("div", { class: "label", text: "Sign what you see to the camera, one sign at a time. Dial: sign each picture clockwise from the top, then the one the needle points at." }),
    el("div", { class: "label", text: "Until sign recognition is in, also type each sign here:" }),
    input,
    el("datalist", { id: "glosses" }, all.map((g) => el("option", { value: g }))),
    el("div", { class: "chips", id: "sign-chips" }),
    sendBtn);
}

export function renderSignChips() {
  const box = $("#sign-chips");
  if (!box) return;
  const signs = store.local.signs;
  box.replaceChildren(...signs.map((g, i) =>
    el("button", { class: "chip", title: "Remove", text: g.toUpperCase() + " ✕", onclick: () => { signs.splice(i, 1); renderSignChips(); } })));
  const b = $("#send-signs");
  if (b) b.disabled = !signs.length || store.state.phase !== "playing";
}

export function expertComposer() {
  const input = el("input", { placeholder: "Tell the agent what to do", maxlength: 300, autocomplete: "off" });
  const say = (text) => { if (text.trim()) send({ type: "say", text: text.trim() }); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { say(input.value); input.value = ""; } });
  const quick = ["Which module?", "Sign that again, please.", "Show me more signs.", "Are you sure? Look again."];
  return el("div", { class: "composer" },
    el("div", { class: "label", text: "Reply to the agent" }),
    input,
    el("div", { class: "chips" }, quick.map((q) => el("button", { class: "btn small", text: q, onclick: () => say(q) }))));
}
