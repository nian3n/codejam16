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


# Puzzles whose words are verbs: "Press the dance." reads wrong, so these say
# "the dance picture" instead. Nouns keep the short form ("Press the cow.").
VERB_PUZZLES = {"actions", "senses"}


def the(g: str, spec: PuzzleSpec | None = None) -> str:
    """'the cow', or 'the dance picture' for a verb puzzle."""
    if spec is not None and spec.id in VERB_PUZZLES:
        return f"the {word(g, spec)} picture"
    return f"the {word(g, spec)}"


def _then(things: list[str], verb: str) -> str:
    """'Cut the white wire, then the black wire' (no final period)."""
    return f"{verb} {things[0]}" + "".join(f", then {x}" for x in things[1:])


def _keys(keys: list[str]) -> str:
    return ", ".join(k.upper() for k in keys)


def phrase(action: Action, module: Module | None = None, spec: PuzzleSpec | None = None) -> str:
    if module is not None:
        spec = module.spec
        action = module.widget.resolve(action, module.facts)
    t = action.target
    v = action.verb
    if v == "cut":
        if "order" in t:
            return {"top_down": "Cut every wire, from the top to the bottom.",
                    "bottom_up": "Cut every wire, from the bottom to the top."}[t["order"]]
        if "colors" in t:
            return f"{_then(['the ' + c + ' wire' for c in t['colors']], 'Cut')}."
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
            "plus_one": "Add 1 to each number on the display and type the result (9 becomes 0).",
        }[t["keys_from"]]
    if v == "press":
        if "icons" in t:
            return f"{_then([the(g, spec) for g in t['icons']], 'Press')}."
        g = t["icon"]
        return f"Press the {g} button." if g in POSITIONS else f"Press {the(g, spec)}."
    if v == "press_all":
        if "order" in t:
            return {"alpha": "Press all the buttons in alphabetical order (A to Z).",
                    "reverse": "Press all the buttons in reverse alphabetical order (Z to A)."}[t["order"]]
        return f"Press the buttons in this order: {', '.join(word(g, spec) for g in t['icons'])}."
    if v == "turn":
        g = t["to"]
        if g in ("alpha_first", "alpha_last"):
            return f"Turn the dial to the picture that comes {g[6:]} in the alphabet."
        return f"Turn the dial to the {g} picture." if g in POSITIONS else f"Turn the dial to {the(g, spec)}."
    if v == "set":
        if "all" in t:
            return "Flip every switch." if t["all"] == "flip" else f"Turn every switch {t['all']}."
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
        return f"the needle points at {the(val, spec)}" if op == "==" else f"the needle does not point at {the(val, spec)}"
    if key == "count_on":
        if op == "==" and val == 0:
            return "no switch is on"
        if op == "==" and val == spec.setup.get("shown"):
            return "every switch is on"
        if op == "==":
            return f"exactly {val} switches are on"
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
            return f"the {key} {noun} {'does not show' if neg else 'shows'} {the(val, spec)}"
        return f"the {key} {noun} is {neg}{word(val, spec)}"
    return f"{key} {op} {val}"
