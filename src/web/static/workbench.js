// Owner: Teammate 1 (Game, scenes, widgets)
// The scene consumes round snapshots. Effects never submit gameplay actions.
import { $, el } from "./core.js";
import { harnessWire, renderLock } from "./mission.js";

const bench = $("#workbench");
const bay = $(".case-bay");
const manual = $("#handler-desk");
const stage = $("#stage");
const lock = $("#case-lock-stage");
const tray = $("#case-tray");
const timer = $("#case-timer");
const digits = ["abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg"];
const stageTitle = { case_lock: "Case lock", wire_tray: "Wire tray", modules: "Main modules" };

export function resetWorkbench() {
  bench.dataset.stage = "";
  bench.dataset.view = "";
  bench.dataset.outcome = "";
  lock.replaceChildren();
  delete lock.dataset.lock;
  stage.replaceChildren();
  tray.replaceChildren();
  delete tray.dataset.tray;
  $("#stage-effect").replaceChildren();
}

export function prepareWorkbench(state, previous) {
  const { mission } = state;
  const playing = state.phase === "playing";
  const handler = playing && state.me.role === "expert";
  const view = handler ? manual : bay;
  if (stage.parentElement !== view) {
    stage.replaceChildren();
    view.prepend(stage);
  }
  bench.dataset.view = handler ? "manual" : "case";
  bench.dataset.stage = mission.stage;
  $("#case-note").textContent = playing && !handler && mission.stage === "case_lock"
    ? mission.feedback || (mission.lock_wheels ? "Set the code that your handler signs, then press Open."
      : "Confirm the digits from left to right.") : "";
  if (playing && mission.stage === "case_lock" && !handler) renderLock(mission);
  if (playing && mission.stage === "wire_tray" && previous?.mission?.case_code
      && previous.round_id === state.round_id) {
    renderLock({ ...previous.mission, lock_confirmed: mission.lock_confirmed });
  }

  const key = JSON.stringify(state.case_tray ?? null);
  if (tray.dataset.tray !== key) {
    tray.dataset.tray = key;
    tray.replaceChildren(...(state.case_tray?.wires.map((color, index) =>
      harnessWire(color, state.case_tray.cuts.includes(index))) ?? []));
  }
  if (!playing || mission.stage !== "modules") $("#stage-effect").replaceChildren();
}

export function renderDamageBays() {
  stage.replaceChildren(el("div", { class: "wreck-bays", "aria-hidden": "true" },
    el("i"), el("i"), el("i"), el("i")));
}

export function setCaseOutcome(outcome) {
  if (bench.dataset.outcome !== outcome) bench.dataset.outcome = outcome;
  $("#case-status").textContent = outcome === "success" ? "Safe" : outcome ? "Offline" : "Armed";
  const titles = { blast: "Detonation", failure: "Damaged case", success: "Safe case" };
  $("#bench-title").textContent = titles[outcome] || stageTitle[bench.dataset.stage] || "";
}

export function renderCaseTime(value) {
  if (timer.dataset.time === value) return;
  timer.dataset.time = value;
  const readout = value.padStart(5, "0");
  timer.replaceChildren(el("span", { class: "timer-value", text: value }),
    ...[...readout].map((glyph) => glyph === ":" ? el("i", { class: "timer-colon", "aria-hidden": "true" })
      : el("span", { class: "timer-digit", "aria-hidden": "true" },
        [..."abcdefg"].map((segment) => el("i", {
          class: `segment segment-${segment}${digits[Number(glyph)].includes(segment) ? " lit" : ""}`,
        })))));
}
