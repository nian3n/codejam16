// Owner: Teammate 1 (Game, scenes, widgets)
// Big button: a screen that cycles faces and a button to hold and release.
// Spec §5.2 shows the faces only while the button is held. Here the screen cycles all
// the time, so the defuser can sign the faces before acting. Releasing sends the
// face on screen at that moment. app.js advances store.faceTick and calls updateFaces().
import { el, icon, store } from "../core.js";

const label = (tick, n) => `face ${(tick % n) + 1} of ${n}`;

export function big_button(m, i, { sendAct }) {
  const faces = m.facts.faces;
  const solvedFace = m.done?.find((a) => a.verb === "hold")?.target.release_on;
  const at = solvedFace ? faces.indexOf(solvedFace) : store.faceTick % faces.length;
  const screen = el("div", { class: "bb-screen", "data-faces": m.defused ? null : faces.join(",") });
  screen.textContent = icon(faces[at]).emoji;
  let held = false;
  const btn = el("button", { class: "bb-btn", text: "HOLD" });
  btn.addEventListener("pointerdown", () => { held = true; btn.classList.add("held"); });
  btn.addEventListener("pointerleave", () => { held = false; btn.classList.remove("held"); });
  btn.addEventListener("pointerup", () => {
    if (!held) return;
    held = false;
    btn.classList.remove("held");
    sendAct(i, "hold", { release_on: faces[store.faceTick % faces.length] });
  });
  return el("div", { class: "bb" }, screen, el("div", { class: "bb-pos", text: label(at, faces.length) }), btn);
}

export function updateFaces() {
  document.querySelectorAll(".bb-screen[data-faces]").forEach((s) => {
    const faces = s.dataset.faces.split(",");
    s.textContent = icon(faces[store.faceTick % faces.length]).emoji;
    const pos = s.parentElement.querySelector(".bb-pos");
    if (pos) pos.textContent = label(store.faceTick, faces.length);
  });
}
