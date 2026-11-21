# Owner: Teammate 4 (Puzzles and brain)
"""Rule engine: load the pool, draw modules, evaluate rules (spec §5).

The widget *logic* hooks (generate / derive / resolve) live here as plain classes.
Drawing and clicks moved to the browser (web/static/widgets/*.js) when the game became a
two-player web app, so puzzles/widgets/ would only hold logic; keeping it in one file
is the simplest option until Teammate 1 needs a Python-side widget again.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field

from escape_pod import config
from escape_pod.puzzles.models import Action, PuzzleSpec

OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "in": lambda a, b: a in b,
}


ALPHA = ("alpha_first", "alpha_last")  # dial targets: the picture first or last in the alphabet
ORDERS = {"alpha": False, "reverse": True}  # press_all orders -> sorted(reverse=...)


def _pick(items: list, which):
    """'first' / 'last' -> the concrete item; anything else passes through."""
    if which == "first":
        return items[0]
    if which == "last":
        return items[-1]
    return which


# ---------------------------------------------------------------------------
# Widget logic. Positions ("first", "last") use the order shown in the manual's
# "Reading order" line, which is also the order of the facts list.
# ---------------------------------------------------------------------------
class Widget:
    name = ""
    noun = "item"           # what one item is called in manual text
    reading_order = ""

    def generate(self, spec: PuzzleSpec, rng: random.Random) -> dict:
        raise NotImplementedError

    def items(self, facts: dict) -> list[str]:
        raise NotImplementedError

    def derive(self, facts: dict) -> dict:
        items = self.items(facts)
        d: dict = {f"has:{g}": True for g in items}
        d.update(first=items[0], last=items[-1], count=len(items))
        return d

    def resolve(self, action: Action, facts: dict) -> Action:
        return action

    def known_keys(self, spec: PuzzleSpec) -> set[str]:
        """Every key derive() can return for this puzzle (used by checks)."""
        return {"first", "last", "count"} | {f"has:{g}" for g in spec.pool}


class Wires(Widget):
    name, noun = "wires", "wire"
    reading_order = "Wires are counted from top to bottom."

    def generate(self, spec, rng):
        return {"colors": rng.sample(spec.pool, spec.setup["shown"])}

    def items(self, facts):
        return facts["colors"]

    def resolve(self, action, facts):
        t = action.target
        if "wire" in t:
            return Action("cut", {"color": _pick(facts["colors"], t["wire"])})
        return action


class Keypad(Widget):
    name, noun = "keypad", "symbol"
    reading_order = "The display is read from left to right."

    def generate(self, spec, rng):
        return {"display": rng.sample(spec.pool, spec.setup["shown"])}

    def items(self, facts):
        return facts["display"]

    def derive(self, facts):
        d = super().derive(facts)
        disp = facts["display"]
        d.update(display=list(disp), reversed=list(reversed(disp)), sorted=sorted(disp))
        return d

    def resolve(self, action, facts):
        t = action.target
        if "keys_from" in t:
            return Action("type", {"keys": self.derive(facts)[t["keys_from"]]})
        return action

    def known_keys(self, spec):
        return super().known_keys(spec) | {"display", "reversed", "sorted"}


class Icons(Widget):
    name, noun = "icons", "button"
    reading_order = "Buttons are counted left to right, top row first."

    def generate(self, spec, rng):
        return {"icons": rng.sample(spec.pool, spec.setup["shown"])}

    def items(self, facts):
        return facts["icons"]

    def derive(self, facts):
        d = super().derive(facts)
        d.update({f"position_of:{g}": i + 1 for i, g in enumerate(facts["icons"])})
        return d

    def resolve(self, action, facts):
        if action.verb == "press_all":
            # Glosses sort like their English words in every pool (test_alphabet_order_...).
            order = action.target.get("order")
            if order in ORDERS:
                return Action("press_all", {"icons": sorted(facts["icons"], reverse=ORDERS[order])})
            return action
        return Action("press", {"icon": _pick(facts["icons"], action.target["icon"])})

    def known_keys(self, spec):
        return super().known_keys(spec) | {f"position_of:{g}" for g in spec.pool}


class Dial(Widget):
    name, noun = "dial", "picture"
    reading_order = "Pictures are counted clockwise, starting at the top."

    def generate(self, spec, rng):
        options = rng.sample(spec.pool, spec.setup["shown"])
        return {"options": options, "needle": rng.choice(options)}

    def items(self, facts):
        return facts["options"]

    def derive(self, facts):
        d = super().derive(facts)
        d["needle"] = facts["needle"]
        return d

    def resolve(self, action, facts):
        to = action.target["to"]
        if to in ALPHA:
            return Action("turn", {"to": (min if to == "alpha_first" else max)(facts["options"])})
        return Action("turn", {"to": _pick(facts["options"], to)})

    def known_keys(self, spec):
        return super().known_keys(spec) | {"needle"}


class Switches(Widget):
    name, noun = "switches", "switch"
    reading_order = "Switches are counted from left to right."

    def generate(self, spec, rng):
        labels = rng.sample(spec.pool, spec.setup["shown"])
        return {"switches": [{"label": g, "state": rng.choice(["on", "off"])} for g in labels]}

    def items(self, facts):
        return [s["label"] for s in facts["switches"]]

    def derive(self, facts):
        d = super().derive(facts)
        d["count_on"] = sum(s["state"] == "on" for s in facts["switches"])
        d.update({f"state_of:{s['label']}": s["state"] for s in facts["switches"]})
        return d

    def resolve(self, action, facts):
        label = _pick(self.items(facts), action.target["switch"])
        state = action.target["state"]
        if state == "flip":
            now = next(s["state"] for s in facts["switches"] if s["label"] == label)
            state = "off" if now == "on" else "on"
        return Action("set", {"switch": label, "state": state})

    def known_keys(self, spec):
        return super().known_keys(spec) | {"count_on"} | {f"state_of:{g}" for g in spec.pool}


class BigButton(Widget):
    name, noun = "big_button", "face"
    reading_order = "Faces are counted in the order the screen shows them."

    def generate(self, spec, rng):
        return {"faces": rng.sample(spec.pool, spec.setup["shown"])}

    def items(self, facts):
        return facts["faces"]

    def derive(self, facts):
        d = super().derive(facts)
        d["faces"] = list(facts["faces"])
        return d

    def resolve(self, action, facts):
        return Action("hold", {"release_on": _pick(facts["faces"], action.target["release_on"])})

    def known_keys(self, spec):
        return super().known_keys(spec) | {"faces"}


WIDGETS: dict[str, Widget] = {w.name: w for w in (Wires(), Keypad(), Icons(), Dial(), Switches(), BigButton())}


# ---------------------------------------------------------------------------
# Rules, modules, draw
# ---------------------------------------------------------------------------
def cond_holds(cond: list, derived: dict) -> bool:
    # A missing key (e.g. state_of:lamp when there is no lamp) never matches.
    # Exception: "has:<g>" for an item not shown is False, so "has:yellow == false" works.
    # A position on the right ("first > last") means that derived value, not the word.
    k, op, v = cond
    if k.startswith("has:") and k not in derived:
        return OPS[op](False, v)
    if k not in derived:
        return False
    if k in ("first", "last") and v in ("first", "last"):
        v = derived[v]
    return OPS[op](derived[k], v)


def rule_matches(rule, derived: dict) -> bool:
    return rule.is_else or all(cond_holds(c, derived) for c in rule.when)


@dataclass
class Module:
    spec: PuzzleSpec
    facts: dict
    defused: bool = False
    widget: Widget = field(init=False, repr=False)

    def __post_init__(self):
        self.widget = WIDGETS[self.spec.widget]

    def trace(self) -> list[bool]:
        """Which rules match, in order. The first True is the one that fires."""
        d = self.widget.derive(self.facts)
        return [rule_matches(r, d) for r in self.spec.rules]

    def fired_rule(self) -> int:
        return self.trace().index(True)

    def solution(self) -> Action:
        rule = self.spec.rules[self.fired_rule()]
        return self.widget.resolve(rule.action(), self.facts)

    def check(self, action: Action) -> bool:
        return action == self.solution()


_POOL: dict[str, PuzzleSpec] | None = None


def load_pool() -> dict[str, PuzzleSpec]:
    global _POOL
    if _POOL is None:
        specs = [PuzzleSpec.model_validate(json.loads(p.read_text(encoding="utf-8")))
                 for p in sorted(config.PUZZLE_DIR.glob("*.json"))]
        _POOL = {s.id: s for s in specs}
    return _POOL


def draw(rng: random.Random, level: config.Level,
         weak_topics: set[str] | frozenset[str] = frozenset()) -> list[Module]:
    """Spec §5.4: seeded, >= min(3, n) widgets, at most one hard puzzle, weak topics x2."""
    pool = load_pool()
    n = level.modules
    candidates = [s for s in pool.values() if level.allow_hard or not s.hard]
    weights = [2.0 if s.topic in weak_topics or s.id in weak_topics else 1.0 for s in candidates]
    for _ in range(1000):
        picked: list[PuzzleSpec] = []
        cand, w = list(candidates), list(weights)
        while len(picked) < n:
            i = rng.choices(range(len(cand)), weights=w)[0]
            picked.append(cand.pop(i))
            w.pop(i)
        if len({s.widget for s in picked}) >= min(3, n) and sum(s.hard for s in picked) <= 1:
            return [Module(s, WIDGETS[s.widget].generate(s, rng)) for s in picked]
    raise RuntimeError("could not draw a bomb that meets the draw rules")
