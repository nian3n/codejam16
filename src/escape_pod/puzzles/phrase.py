# Owner: Teammate 4 (Puzzles and brain)
"""English wording for actions and rule conditions.

phrase(action, module) gives the concrete instruction for one drawn module
("Press the cow."). With module=None it gives the manual's symbolic wording
("Press the last button."). manual/build.py and manual/solve.py both use these
helpers, so the manual and the answer key never disagree on wording.
"""
from __future__ import annotations

from escape_pod.puzzles.engine import WIDGETS, Module
from escape_pod.puzzles.models import Action, PuzzleSpec

POSITIONS = ("first", "last")


def word(g: str, spec: PuzzleSpec | None = None) -> str:
    """How a gloss reads in English text. Digits and letters are shown in caps."""
    if spec is not None and spec.target_words in ("digits", "letters"):
        return g.upper()
    return {"frenchfries": "french fries", "icecream": "ice cream", "tv": "TV"}.get(g, g)


def _keys(keys: list[str]) -> str:
    return ", ".join(k.upper() for k in keys)


def phrase(action: Action, module: Module | None = None, spec: PuzzleSpec | None = None) -> str:
    if module is not None:
        spec = module.spec
        action = module.widget.resolve(action, module.facts)
    t = action.target
    v = action.verb
    if v == "cut":
        if "color" in t:
            return f"Cut the {t['color']} wire."
        return f"Cut the {t['wire']} wire."
    if v == "type":
        if "keys" in t:
            return f"Type {_keys(t['keys'])}."
        letters = spec is not None and spec.target_words == "letters"
        return {
            "display": "Type the display as shown.",
            "reversed": "Type the display in reverse order.",
            "sorted": "Type the display in alphabet order." if letters
            else "Type the display from smallest to largest.",
        }[t["keys_from"]]
    if v == "press":
        g = t["icon"]
        return f"Press the {g} button." if g in POSITIONS else f"Press the {word(g)}."
    if v == "turn":
        g = t["to"]
        return f"Turn the dial to the {g} picture." if g in POSITIONS else f"Turn the dial to the {word(g)}."
    if v == "set":
        label, state = t["switch"], t["state"]
        if state == "flip":
            name = f"the {label} switch" if label in POSITIONS else f"the {word(label)} switch"
            return f"Flip {name}."
        return f"Turn the {word(label)} switch {state}."
    if v == "hold":
        g = t["release_on"]
        when = f"the {g} face shows" if g in POSITIONS else f"the face is {word(g)}"
        return f"Hold the button and let go when {when}."
    raise ValueError(f"unknown verb {v}")


_CMP = {
    "digits": {">": "bigger than", "<": "smaller than", ">=": "at least", "<=": "at most"},
    "letters": {">": "later in the alphabet than", "<": "earlier in the alphabet than"},
}


def condition(cond: list, spec: PuzzleSpec) -> str:
    """One rule condition as English: ["has:cat", "==", true] -> "there is a cat"."""
    key, op, val = cond
    noun = {"digits": "digit", "letters": "letter"}.get(spec.target_words, WIDGETS[spec.widget].noun)
    if key.startswith("has:"):
        g = word(key[4:], spec)
        yes = (op == "==") == bool(val)
        if spec.widget == "keypad":
            return f"the display shows {g}" if yes else f"the display does not show {g}"
        if spec.widget == "wires":
            return f"there is a {g} wire" if yes else f"there is no {g} wire"
        return f"{g} is shown" if yes else f"{g} is not shown"
    if key.startswith("state_of:"):
        return f"the {word(key[9:])} switch is {val}" if op == "==" else f"the {word(key[9:])} switch is not {val}"
    if key == "needle":
        return f"the needle points at the {word(val)}" if op == "==" else f"the needle does not point at the {word(val)}"
    if key == "count_on":
        if op == "==" and val == 0:
            return "no switch is on"
        if op == ">=":
            return f"{val} or more switches are on"
        return f"the number of switches that are on is {op} {val}"
    if key in POSITIONS:
        if op == "in":
            return f"the {key} {noun} is one of {', '.join(word(x, spec) for x in val)}"
        if isinstance(val, str) and val in POSITIONS:  # e.g. first > last
            rel = _CMP.get(spec.target_words, {}).get(op, op)
            return f"the {key} {noun} is {rel} the {val} {noun}"
        neg = "not " if op == "!=" else ""
        if spec.widget in ("icons", "dial"):
            return f"the {key} {noun} {'does not show' if neg else 'shows'} the {word(val, spec)}"
        return f"the {key} {noun} is {neg}{word(val, spec)}"
    return f"{key} {op} {val}"
