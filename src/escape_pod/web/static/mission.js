// Owner: Teammate 1 (Game, scenes, widgets)
import { $, el, svg } from "./core.js";
import { wireTrace } from "./widgets/wires.js";

function lockProgress(confirmed) {
  return `${confirmed} of 3 digits confirmed`;
}

function trayProgress(cuts) {
  return `${cuts} of 4 wires accepted`;
}

function caseLock(mission, lifting) {
  const confirmed = lifting ? mission.case_code.length : mission.lock_confirmed;
  return el("section", { class: "mission-gate mission-case" },
    el("h2", { text: "Closed case" }),
    el("div", { class: "case-lid" },
      el("div", { class: "case-tag" },
        el("span", { text: "CASE COMBINATION" }),
        el("strong", { text: mission.case_code })),
      el("div", { class: "case-lock" },
        el("div", { class: "lock-latch", "aria-hidden": "true" }),
        el("div", { class: "lock-slots", "aria-label": "Confirmed digits" },
          [...mission.case_code].map((digit, index) => el("span", {
            class: "lock-slot", text: index < confirmed ? digit : "–",
          }))),
        el("p", { class: "mission-count", text: lockProgress(confirmed) }))),
    el("p", { class: "mission-note", role: "status", text: mission.feedback || "Confirm the digits from left to right." }));
}

function wireRow(mission, color, index, lifting) {
  const cut = lifting || mission.cuts.includes(index);
  const art = svg("svg", { viewBox: "14 0 172 44", "aria-hidden": "true" });
  art.append(...wireTrace(color, 22, cut));
  return el("li", { class: "mission-wire", "data-wire-index": index },
    el("span", { class: "wire-position", text: index + 1 }),
    art, el("span", { class: "wire-name", text: cut ? `${color} · cut` : color }));
}

function wireTray(mission, lifting) {
  const progress = trayProgress(lifting ? mission.wires.length : mission.cut_count);
  return el("section", { class: "mission-gate mission-tray" },
    el("h2", { text: "Wire tray" }),
    el("p", { class: "mission-count", text: progress }),
    el("ol", { class: "tray-wires", "aria-label": "Wires from top to bottom" },
      mission.wires.map((color, index) => wireRow(mission, color, index, lifting))),
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

export function renderMission(state) {
  const { mission } = state;
  const key = JSON.stringify([state.round_id, state.phase, state.armed, state.me.role, mission]);
  const stage = $("#stage");
  if (stage.firstElementChild?.dataset.missionView === key) return;
  const view = state.me.role === "expert" ? missionManual(mission)
    : mission.stage === "case_lock" ? caseLock(mission, false) : wireTray(mission, false);
  view.dataset.missionView = key;
  stage.replaceChildren(view);
}

export function liftMissionLayer(previous, state) {
  const effect = $("#stage-effect");
  if (!previous?.mission || !state.mission || previous.round_id !== state.round_id || state.phase !== "playing") {
    effect.replaceChildren();
    return;
  }
  if (state.me.role !== "defuser" || previous.mission.stage === state.mission.stage
      || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  // The new stage is already authoritative. The old, completed layer only animates away.
  const layer = previous.mission.stage === "case_lock" ? caseLock(previous.mission, true) : wireTray(previous.mission, true);
  layer.classList.add("mission-lifting");
  layer.inert = true;
  layer.addEventListener("animationend", (event) => { if (event.target === layer) layer.remove(); });
  effect.replaceChildren(layer);
}
