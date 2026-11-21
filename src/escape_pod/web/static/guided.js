// Owner: Teammate 1 (Game, scenes, widgets)
import { $, el, send } from "./core.js";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const PNG_HANDSHAPES = "PQRSUVWYZ";
const COLORS = {
  blue: "#6aa9ff", teal: "#56dccc", amber: "#f7af55",
  red: "#ff686b", green: "#78d795", yellow: "#f9d664",
};
let layoutKey = null;
let endDemo = null;
let panel = null;

export function roleName(role, swapped) {
  if (role === "defuser") return swapped ? "Parent · Signer" : "Child · Signer";
  return swapped ? "Child · Decoder" : "Parent · Decoder";
}

export function resetGuided() {
  endDemo?.();
  endDemo = null;
  layoutKey = null;
  panel = null;
}

function titleCase(text) {
  return text[0].toUpperCase() + text.slice(1);
}

function controlArtwork(control) {
  const label = control.number
    ? `${titleCase(control.color)} ${control.number}`
    : `${titleCase(control.color)} wire`;
  const face = el("span", { class: control.number ? "panel-number" : "panel-wire", "aria-hidden": "true", text: control.number });
  return el("span", {
    class: "control-art",
    style: `--signal-color: ${COLORS[control.color]}`,
  }, face, el("span", { class: "control-name", text: label }));
}

function handshape(letter) {
  const extension = PNG_HANDSHAPES.includes(letter) ? "png" : "svg";
  return el("img", { src: `/static/asl/${letter}.${extension}`, alt: `ASL handshape for ${letter}`, draggable: "false" });
}

function demo(spelling, autoplay = false) {
  const cards = [...spelling.toUpperCase()];
  const picture = el("div", { class: "demo-hand" });
  const caption = el("div", { class: "demo-caption" });
  const replay = el("button", { class: "btn primary", text: "Play ASL demonstration" });
  const next = el("button", { class: "btn", text: "Next handshape" });
  let timer;
  let index = 0;

  function show() {
    const letter = cards[index];
    const repeated = letter !== " " && cards[index - 1] === letter;
    picture.replaceChildren(letter === " " ? el("span", { text: "Pause" }) : handshape(letter));
    caption.textContent = letter === " " ? "Next word" : repeated ? `${letter} again` : letter;
  }
  function play() {
    show();
    if (index < cards.length - 1) {
      timer = setTimeout(() => { index++; play(); }, cards[index] === " " ? 450 : 650);
    }
  }
  replay.onclick = () => {
    clearTimeout(timer);
    index = 0;
    play();
    replay.textContent = "Replay ASL demonstration";
  };
  next.onclick = () => {
    clearTimeout(timer);
    do {
      index = (index + 1) % cards.length;
    } while (cards[index] === " ");
    show();
  };
  endDemo = () => clearTimeout(timer);
  if (autoplay) replay.onclick();
  else show();
  return el("section", { class: "sign-demo", "aria-label": "Fingerspelling demonstration" },
    el("div", { class: "demo-frame" }, picture, caption),
    el("div", { class: "demo-copy" },
      el("h3", { text: "Fingerspell the clue" }),
      el("p", { text: spelling.toUpperCase() }),
      /([a-z])\1/.test(spelling)
        ? el("p", { class: "demo-tip", text: "For a double letter, try a small slide outward on the second letter." })
        : null,
      el("div", { class: "guided-actions" }, replay, next)));
}

function alphabet() {
  return el("details", { class: "alphabet-reference" },
    el("summary", { text: "ASL alphabet reference" }),
    el("div", { class: "alphabet-grid" }, [...ALPHABET].map((letter) =>
      el("figure", {}, handshape(letter), el("figcaption", { text: letter })))),
    el("p", { class: "guided-note", text: "Follow the movement arrows for J and Z." }));
}

function buildPanel(controls, turn) {
  const confirm = el("button", { class: "btn primary", text: "Confirm selection", disabled: true });
  let selected = null;
  let cursor = 0;
  function choose(index) {
    cursor = index;
    selected = controls[index].id;
    confirm.disabled = false;
    buttons.forEach((button, i) => {
      button.tabIndex = i === cursor ? 0 : -1;
      button.setAttribute("aria-pressed", String(i === index));
    });
  }
  function submit() {
    if (selected) send({ type: "guided_action", turn: panel.turn, control: selected });
  }
  const buttons = controls.map((control, index) => {
    const button = el("button", {
      class: "panel-control", type: "button", tabindex: index === 0 ? 0 : -1, "aria-pressed": "false",
      onclick: () => choose(index),
    }, controlArtwork(control));
    button.addEventListener("keydown", (event) => {
      const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -3, ArrowDown: 3 }[event.key];
      if (offset) {
        event.preventDefault();
        const destination = (index + offset + controls.length) % controls.length;
        choose(destination);
        buttons[destination].focus();
      } else if (event.key === "Enter") {
        event.preventDefault();
        if (event.repeat) return;
        choose(index);
        submit();
      }
    });
    return button;
  });
  confirm.onclick = submit;
  panel = {
    turn,
    clear(newTurn) {
      this.turn = newTurn;
      selected = null;
      confirm.disabled = true;
      buttons.forEach((button) => button.setAttribute("aria-pressed", "false"));
    },
  };
  return el("div", { class: "decoder-panel" },
    el("h2", { text: "Control panel" }),
    el("p", { class: "guided-note", text: "Use arrow keys to choose a control and Enter to confirm." }),
    el("div", { class: "panel-grid", "aria-label": "Colored numbered buttons and wires" }, buttons),
    el("div", { class: "guided-actions" }, confirm, el("button", {
      class: "btn", text: "Sign again", onclick: () => send({ type: "guided_repeat", turn: panel.turn }),
    })));
}

function signerClue(clue, practice) {
  return [
    el("p", { class: "guided-note", text: practice
      ? "In this story, you’ve been kidnapped. You wake up in a dim room beside a fictional bomb. Your partner can unlock the room using the clues you sign."
      : "Sign this private clue to your partner." }),
    el("div", { class: "private-clue" },
      el("h2", { text: clue.text }), controlArtwork(clue.picture)),
    el("p", { id: "repeat-cue", class: "repeat-cue hidden", role: "status" }),
    demo(clue.spelling),
  ];
}

function nextButton(text, type, disabled = false) {
  return el("button", { class: "btn primary", text, disabled, onclick: () => send({ type }) });
}

function buildLayout(state) {
  const game = state.guided;
  if (game.step === "unlocked") {
    const reviewDemo = el("div", { class: "review-demo", "aria-label": "Selected clue demonstration" });
    return [
      el("h2", { text: "Room unlocked" }),
      el("p", { class: "guided-note", text: "You opened the room together. Here are the clues you practiced." }),
      el("ul", { class: "sign-review" }, game.review.map((clue) =>
        el("li", {},
          el("strong", { text: clue.text }),
          el("button", {
            class: "btn small", text: "Replay signs", "aria-label": `Replay signs for ${clue.text}`,
            onclick: () => { endDemo?.(); reviewDemo.replaceChildren(demo(clue.spelling, true)); },
          })))),
      reviewDemo,
      el("div", { class: "guided-actions" },
        nextButton("Swap roles", "guided_swap"), nextButton("Back to the lobby", "again")),
    ];
  }
  if (game.step === "timeout") {
    const panelPreview = state.me.role === "expert"
      ? buildPanel(game.controls, game.turn)
      : null;
    return [
      el("div", { class: "dark-panel", "aria-hidden": "true", inert: true }, panelPreview),
      el("h2", { text: "The panel went dark" }),
      el("p", { class: "guided-note", text: "Try the same clues again at your own pace." }),
      nextButton("Retry without a timer", "guided_retry"),
    ];
  }
  if (game.step === "ready") {
    return [
      el("h2", { text: "Practice complete" }),
      el("p", { class: "guided-note", text: "Check that your partner’s face and hands are clear, then start when you’re both ready." }),
      el("div", { id: "begin-guided" }),
    ];
  }
  if (state.me.role === "defuser") return signerClue(game.clue, game.step === "practice");
  return [buildPanel(game.controls, game.turn), alphabet()];
}

export function renderGuided(state) {
  const game = state.guided;
  const isSigner = state.me.role === "defuser";
  const key = JSON.stringify([state.code, state.me.role, game.step, isSigner ? game.turn : null]);
  if (layoutKey !== key) {
    resetGuided();
    layoutKey = key;
    $("#stage").replaceChildren(el("div", { class: "guided-content" },
      el("div", { class: "guided-feedback", role: "status" }), ...buildLayout(state)));
  } else if (panel && panel.turn !== game.turn) {
    panel.clear(game.turn);
  }
  const feedback = $(".guided-feedback");
  feedback.textContent = game.feedback === "try_again" ? "That control didn’t match. Try again."
    : game.feedback === "correct" && game.step !== "unlocked" ? "Correct! ✦" : "";
  feedback.dataset.result = game.feedback;

  const repeat = $("#repeat-cue");
  if (repeat) {
    repeat.classList.toggle("hidden", !game.repeat);
    repeat.textContent = game.repeat ? `Your partner asks you to sign again${game.repeat > 1 ? ` (${game.repeat})` : ""}.` : "";
  }
  const begin = $("#begin-guided");
  if (begin) {
    const online = state.players.filter((player) => player.online).length === 2;
    if (!begin.firstChild) begin.append(nextButton("Start countdown", "guided_begin", !online));
    else begin.firstChild.disabled = !online;
  }
}
