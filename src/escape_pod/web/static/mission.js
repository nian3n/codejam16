// Owner: Teammate 1 (Game, scenes, widgets)
import { $, el, svg, WIRE_COLORS } from "./core.js";

function lockProgress(confirmed) {
  return `${confirmed} of 3 digits confirmed`;
}

function trayProgress(cuts) {
  return `${cuts} of 4 wires cut`;
}

export function renderLock(mission) {
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

function wireRow(mission, color, index, fresh) {
  const cut = mission.cuts.includes(index);
  return el("li", { class: "mission-wire", "data-wire-index": index },
    el("span", { class: "wire-position", text: index + 1 }),
    harnessWire(color, cut, fresh),
    el("span", { class: "wire-name", text: cut ? `${color} · cut` : color }));
}

function wireTray(mission, newlyCut = []) {
  return el("section", { class: "mission-tray" },
    el("p", { class: "mission-count", text: trayProgress(mission.cuts.length) }),
    el("ol", { class: "tray-wires", "aria-label": "Wires from top to bottom" },
      mission.wires.map((color, index) => wireRow(mission, color, index, newlyCut.includes(index)))),
    el("p", { class: "mission-note", role: "status", text: mission.feedback
      || "Ask your handler for the next position, then confirm that wire’s color." }));
}

function missionManual(mission) {
  const lock = mission.stage === "case_lock";
  return el("article", { class: "page mission-gate mission-manual" },
    el("h2", { text: lock ? "Case lock" : "Wire tray order" }),
    el("p", { class: "meta", text: lock ? lockProgress(mission.lock_confirmed) : trayProgress(mission.cut_count) }),
    el("p", { text: lock
      ? "Ask the agent to sign and confirm the three digits on their luggage tag from left to right."
      : "Count positions from top to bottom. Tell the agent the next position so they can sign its color." }),
    lock ? null : el("ol", {}, mission.wire_rule.map((position, index) =>
      el("li", { "aria-current": index === mission.cut_count ? "step" : null },
        index < mission.cut_count ? `${position} · accepted` : position))));
}

function freshCuts(previous, tray) {
  return previous?.cuts ? tray.cuts.filter((wire) => !previous.cuts.includes(wire)) : [];
}

export function renderMission(state, previous) {
  const { mission } = state;
  const key = JSON.stringify([state.round_id, state.me.role, mission]);
  const stage = $("#stage");
  if (stage.firstElementChild?.dataset.missionView === key) return;
  const view = state.me.role === "expert" ? missionManual(mission)
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
