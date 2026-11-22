// Owner: Teammate 1 (Game, scenes, widgets)
import { $, el, gameplayOpen, send, store, svg, WIRE_COLORS } from "./core.js";
import { playSnip } from "./sfx.js";

function lockProgress(confirmed) {
  return `${confirmed} of 3 digits confirmed`;
}

function trayProgress(cuts) {
  return `${cuts} of 4 wires cut`;
}

// Two players: the handler signs the code, the agent sets it on three wheels and
// presses Open ({"type": "lock"}). The wheel values are local, per round.
function wheelState() {
  const round = store.state.round_id;
  if (store.local.lockWheels?.round !== round) store.local.lockWheels = { round, digits: [0, 0, 0] };
  return store.local.lockWheels.digits;
}

function renderWheels(mission) {
  const mount = $("#case-lock-stage");
  const digits = wheelState();
  const key = JSON.stringify(["wheels", digits, mission.revision, mission.feedback]);
  if (mount.dataset.lock === key) return;
  mount.dataset.lock = key;
  const spin = (i, step) => {
    digits[i] = (digits[i] + step + 10) % 10;
    renderWheels(mission);
  };
  const open = () => {
    const s = store.state;
    if (!gameplayOpen() || s.mission?.stage !== "case_lock") return;
    send({ type: "lock", code: digits.join(""), round_id: s.round_id, mission_revision: s.mission.revision });
  };
  mount.replaceChildren(el("section", { class: "mission-case" },
    el("div", { class: "case-lock wheels" },
      el("div", { class: "lock-latch", "aria-hidden": "true" }),
      el("div", { class: "lock-slots", role: "group", "aria-label": "Code wheels" },
        digits.map((d, i) => el("div", { class: "wheel" },
          el("button", { class: "wheel-step", type: "button", text: "▲", "aria-label": `Wheel ${i + 1} up`, onclick: () => spin(i, 1) }),
          el("span", { class: "lock-slot", text: String(d), "aria-live": "polite" }),
          el("button", { class: "wheel-step", type: "button", text: "▼", "aria-label": `Wheel ${i + 1} down`, onclick: () => spin(i, -1) })))),
      el("button", { class: "btn primary lock-open", type: "button", text: "Open", onclick: open }))));
}

export function renderLock(mission) {
  if (mission?.lock_wheels) { renderWheels(mission); return; }
  if (!mission?.case_code) return;
  const mount = $("#case-lock-stage");
  const key = JSON.stringify([mission.case_code, mission.lock_confirmed, mission.feedback]);
  if (mount.dataset.lock === key) return;
  mount.dataset.lock = key;
  mount.replaceChildren(el("section", { class: "mission-case" },
    el("div", { class: "case-lock" },
      el("div", { class: "lock-latch", "aria-hidden": "true" }),
      el("div", { class: "lock-slots", "aria-label": "Confirmed digits" },
        [...mission.case_code].map((digit, index) => el("span", {
          class: "lock-slot", text: index < mission.lock_confirmed ? digit : "–",
        }))),
      el("p", { class: "mission-count", text: lockProgress(mission.lock_confirmed) })),
    el("div", { class: "case-tag" },
      el("span", { text: "CASE COMBINATION" }),
      el("strong", { text: mission.case_code }))));
}

function wireBend(color, d, copper, side) {
  const group = svg("g", { class: side ? `wire-end ${side}` : "wire-arc" });
  for (const [cls, weight, stroke] of [
    ["wire-shadow", 13, "#090c0d"], ["wire-jacket", 12, "#1a1a1a"],
    ["wire-coat", 9, WIRE_COLORS[color]], ["wire-glint", 2, "#fff"],
  ]) {
    const opts = { d, fill: "none", stroke, "stroke-width": weight, "stroke-linecap": "round", class: cls };
    group.append(svg("path", opts));
  }
  if (copper) group.append(svg("path", { d: copper, class: "wire-copper", stroke: "#e2a973",
    "stroke-width": 4, fill: "none", "stroke-linecap": "round" }));
  return group;
}

export function harnessWire(color, cut, fresh = false) {
  const art = svg("svg", {
    viewBox: "0 0 342 58", "aria-hidden": "true",
    class: `harness-wire${fresh ? " wire-fresh" : ""}`,
  });
  for (const cx of [16, 326]) art.append(svg("circle", { cx, cy: 42, r: 11, class: "wire-socket" }));
  if (cut) {
    art.append(
      wireBend(color, "M16 42 C57 14 105 5 143 16", "M143 16 l10 -4", "left-end"),
      wireBend(color, "M326 42 C270 13 221 13 191 36", "M191 36 l-9 7", "right-end"));
  } else {
    art.append(wireBend(color, "M16 42 C100 -5 242 -7 326 42"));
  }
  return art;
}

function cutWire(index) {
  const s = store.state;
  if (!gameplayOpen() || s.mission?.stage !== "wire_tray") return;
  playSnip();
  send({ type: "wire_cut", wire: index, round_id: s.round_id, mission_revision: s.mission.revision });
}

function wireRow(mission, color, index, fresh) {
  const cut = mission.cuts.includes(index);
  // The cuts unlock when the agent has signed all four colors (server: Mission.tray_ready).
  const ready = !!mission.signed_colors && mission.wires.every((c) => mission.signed_colors.includes(c));
  const signed = mission.signed_colors?.includes(color);
  const name = color[0].toUpperCase() + color.slice(1);  // only the color is capitalized
  const label = cut ? `${name} · cut` : signed ? `${name} · sent` : name;
  const parts = [el("span", { class: "wire-position", text: index + 1 }), harnessWire(color, cut, fresh),
    el("span", { class: "wire-name", text: label })];
  if (cut || !ready) return el("li", { class: "mission-wire", "data-wire-index": index }, ...parts);
  return el("li", { "data-wire-index": index },
    el("button", { class: "mission-wire cuttable", type: "button", title: `Cut the ${color} wire`,
      onclick: () => cutWire(index) }, ...parts));
}

function wireTray(mission, newlyCut = []) {
  return el("section", { class: "mission-tray" },
    el("p", { class: "mission-count", text: trayProgress(mission.cuts.length) }),
    el("ol", { class: "tray-wires", "aria-label": "Wires from top to bottom" },
      mission.wires.map((color, index) => wireRow(mission, color, index, newlyCut.includes(index)))),
    el("p", { class: "mission-note", role: "status", text: mission.feedback
      || "Sign the color of each wire, top to bottom." }));
}

function missionManual(mission, chat = []) {
  if (mission.stage === "case_lock") {
    // Only the handler sees the code. The pictures help a handler who does not know the signs.
    return el("article", { class: "page mission-gate mission-manual" },
      el("h2", { text: "Case lock" }),
      el("p", { text: "Sign this code to the agent, one digit at a time, from left to right. "
        + "The agent reads your signs on the video and sets the code on the lock. Typing is off for this step." }),
      el("div", { class: "code-card", "aria-label": `Code ${[...(mission.case_code || "")].join(" ")}` },
        [...(mission.case_code || "")].map((d) => el("figure", { class: "code-digit" },
          el("img", { src: `/signs/pictures/${d}.png`, alt: `The sign for ${d}`, loading: "lazy" }),
          el("figcaption", { text: d })))));
  }
  // Only the colors from messages that the handler revealed with a hint (server chat_for).
  const signed = [...new Set(chat.filter((m) => m.kind === "signs" && m.mission_stage === "wire_tray" && m.glosses)
    .flatMap((m) => m.glosses))];
  return el("article", { class: "page mission-gate mission-manual" },
    el("h2", { text: "Wire tray" }),
    el("p", { class: "meta", text: `${trayProgress(mission.cut_count)} · ${mission.colors_received ?? 0} of 4 colors received` }),
    el("p", { text: "The agent signs the colors of the four wires. Cut the wires in this order of colors. "
      + "Skip the colors that the agent does not have. Tell the agent the order." }),
    el("ol", { class: "wire-rank" }, mission.wire_rank.map((color) =>
      el("li", { class: signed.includes(color) ? "signed" : "" },
        el("span", { class: "rank-swatch", style: `background:${WIRE_COLORS[color]}` }),
        el("span", { class: "rank-color", text: color }),
        signed.includes(color) ? el("span", { class: "rank-have", text: " ✓ the agent signed it" }) : null))));
}

function freshCuts(previous, tray) {
  return previous?.cuts ? tray.cuts.filter((wire) => !previous.cuts.includes(wire)) : [];
}

export function renderMission(state, previous) {
  const { mission } = state;
  const key = JSON.stringify([state.round_id, state.me.role, mission, state.me.role === "expert" ? state.chat : null]);
  const stage = $("#stage");
  if (stage.firstElementChild?.dataset.missionView === key) return;
  const view = state.me.role === "expert" ? missionManual(mission, state.chat)
    : wireTray(mission, freshCuts(previous?.round_id === state.round_id ? previous.mission : null, mission));
  view.dataset.missionView = key;
  stage.replaceChildren(view);
}

export function finishTray(previous, state) {
  if (state.me.role !== "defuser" || state.phase !== "playing" || state.mission.stage !== "modules"
      || previous?.round_id !== state.round_id || previous.mission.stage !== "wire_tray"
      || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const tray = state.case_tray;
  const layer = wireTray({ ...tray, feedback: "Tray cleared." }, freshCuts(previous.mission, tray));
  layer.classList.add("tray-reveal");
  layer.inert = true;
  layer.addEventListener("animationend", (event) => { if (event.target === layer) layer.remove(); });
  $("#stage-effect").replaceChildren(layer);
}
