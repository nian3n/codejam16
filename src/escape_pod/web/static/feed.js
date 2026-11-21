// Owner: Teammate 1 (Game, scenes, widgets)
// The side panel: the shared message feed, the defuser's sign composer and the
// expert's reply box.
import { $, el, send, store } from "./core.js";
import { openPage, pagesFor } from "./manual_view.js";

export function renderFeed() {
  const { state, local } = store;
  const feed = $("#feed");
  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 40;
  feed.replaceChildren(...state.chat.map((m) => {
    if (m.kind === "event") return el("div", { class: "msg event" + (m.strike ? " strike" : ""), text: m.text });
    if (m.kind === "say") return el("div", { class: "msg say" }, el("span", { class: "who", text: `${m.from} (handler)` }), m.text);
    const box = el("div", { class: "msg signs" }, el("span", { class: "who", text: `${m.from} signed` }),
      el("div", { class: "chips" }, m.glosses.map((g) => el("span", { class: "chip", text: g.toUpperCase() }))));
    if (state.me.role === "expert" && !m.mission_stage) {
      const hits = pagesFor(m.glosses);
      box.append(el("div", { class: "page-links" }, hits.length ? "Pages with these words:" : "No page has these words.",
        hits.map((p) => el("button", { class: "btn small", text: p.title, onclick: () => openPage(p.id) }))));
    }
    return box;
  }));
  // Solo: the bot "thinks" for a second before each reply (server BOT_DELAY_S).
  if (state.bot_typing) {
    feed.append(el("div", { class: "msg say typing", "aria-label": `${state.bot_name} is typing` },
      el("span", { class: "who", text: `${state.bot_name} (handler)` }),
      el("span", { class: "dots" }, el("i"), el("i"), el("i"))));
  }
  const seen = state.chat.length + (state.bot_typing ? 0.5 : 0);
  if (nearBottom || local.chatSeen !== seen) feed.scrollTop = feed.scrollHeight;
  local.chatSeen = seen;
}

// The field agent's composer (webcam signs) is in game_signs.js.
export { signComposer as defuserComposer, renderSignChips } from "./game_signs.js";

const REPLY_HINT = "Tell the agent what to do";

export function expertComposer() {
  const input = el("input", { id: "reply-text", placeholder: REPLY_HINT, maxlength: 300, autocomplete: "off" });
  const say = (text) => { if (text.trim()) send({ type: "say", text: text.trim() }); };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { say(input.value); input.value = ""; } });
  const quick = ["Which module?", "Sign that again, please.", "Show me more signs.", "Are you sure? Look again."];
  return el("div", { class: "composer", id: "expert-composer" },
    el("div", { class: "label", text: "Reply to the agent" }),
    input,
    el("div", { class: "chips" }, quick.map((q) => el("button", { class: "btn small", text: q, onclick: () => say(q) }))));
}

/** The case lock: the handler must sign the code, so the server ignores typed replies.
 * Show that here instead of a box that seems to work. */
export function lockExpertComposer(state) {
  const box = $("#expert-composer");
  if (!box) return;
  const off = state.phase === "playing" && state.mission?.stage === "case_lock";
  for (const control of box.querySelectorAll("input, button")) control.disabled = off;
  $("#reply-text").placeholder = off ? "Typing is off. Sign the code to the agent." : REPLY_HINT;
}
