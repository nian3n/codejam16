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

import config
from puzzles.models import Action, PuzzleSpec

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
WIRE_ORDERS = {"top_down": False, "bottom_up": True}  # cut every wire, in reading order or back
SWITCH_ALL = ("on", "off", "flip")  # set {"all": ...}: every switch on, off, or flipped


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

    def steps(self, solution: Action) -> tuple[list[Action], bool]:
        """The clicks that make up a resolved solution, and whether their order matters.

        Most answers are one click. A few are several ("cut the white wire, then the black
        wire", "turn every switch off"): the server checks each click as it comes
        (Module.apply), so the player gets a strike at the first wrong one.
        """
        return [solution], True

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
        if t.get("order") in WIRE_ORDERS:
            # Keep "order" next to the list: phrase() says "every wire, from the bottom",
            # which is what the manual says and what HQ can say without seeing the wires.
            cols = list(facts["colors"])
            return Action("cut", {"order": t["order"], "colors": cols[::-1] if WIRE_ORDERS[t["order"]] else cols})
        return action

    def steps(self, solution):
        t = solution.target
        if "colors" in t:
            return [Action("cut", {"color": c}) for c in t["colors"]], True
        return [solution], True


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
        if all(k.isdigit() for k in disp):
            d["plus_one"] = [str((int(k) + 1) % 10) for k in disp]
        return d

    def resolve(self, action, facts):
        t = action.target
        if "keys_from" in t:
            return Action("type", {"keys": self.derive(facts)[t["keys_from"]]})
        return action

    def known_keys(self, spec):
        return super().known_keys(spec) | {"display", "reversed", "sorted", "plus_one"}


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
        if "icons" in action.target:  # press these pictures, in this order
            return action
        return Action("press", {"icon": _pick(facts["icons"], action.target["icon"])})

    def steps(self, solution):
        if solution.verb == "press" and "icons" in solution.target:
            return [Action("press", {"icon": g}) for g in solution.target["icons"]], True
        return [solution], True

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
        if "all" in action.target:
            # Only the switches that change are clicks; "all" stays for phrase().
            how = action.target["all"]
            now = {s["label"]: s["state"] for s in facts["switches"]}
            want = {g: ("off" if st == "on" else "on") if how == "flip" else how for g, st in now.items()}
            return Action("set", {"all": how, "flips": {g: st for g, st in want.items() if st != now[g]}})
        label = _pick(self.items(facts), action.target["switch"])
        state = action.target["state"]
        if state == "flip":
            now = next(s["state"] for s in facts["switches"] if s["label"] == label)
            state = "off" if now == "on" else "on"
        return Action("set", {"switch": label, "state": state})

    def known_keys(self, spec):
        return super().known_keys(spec) | {"count_on"} | {f"state_of:{g}" for g in spec.pool}

    def steps(self, solution):
        if "flips" in solution.target:  # any order: the end state is what counts
            return [Action("set", {"switch": g, "state": st}) for g, st in solution.target["flips"].items()], False
        return [solution], True


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


def group_of(g: str) -> str | None:
    """The sorter group a gloss belongs to ("healthy"), from the puzzle's setup.groups.

    Widgets get only the facts, never the spec, so the groups are looked up by gloss.
    That works because no gloss is in two pools (test_no_gloss_in_two_pools).
    """
    for spec in load_pool().values():
        for grp in spec.setup.get("groups", []):
            if g in grp["items"]:
                return grp["key"]
    return None


class Sorter(Widget):
    """Pictures on a tray, two boxes below. The player drags each picture into a box.

    The rules say which group goes in the left box ({"left": "treats"}); the other group
    goes right. Each drop is one step, in any order. The facts hold only the pictures:
    the groups stay in the manual, so the agent has to ask which food is which.
    """
    name, noun = "sorter", "picture"
    reading_order = "Pictures on the tray are counted left to right."

    def generate(self, spec, rng):
        groups = [set(g["items"]) for g in spec.setup["groups"]]
        while True:  # both groups on the tray, so both boxes get something
            items = rng.sample(spec.pool, spec.setup["shown"])
            if all(g & set(items) for g in groups):
                return {"items": items}

    def items(self, facts):
        return facts["items"]

    def resolve(self, action, facts):
        left = action.target.get("left")
        if not isinstance(left, str):
            return action  # already resolved, or one drop
        items = facts["items"]
        return Action("sort", {"left": [g for g in items if group_of(g) == left],
                               "right": [g for g in items if group_of(g) != left]})

    def steps(self, solution):
        t = solution.target
        if isinstance(t.get("left"), list):
            return ([Action("sort", {"item": g, "box": "left"}) for g in t["left"]]
                    + [Action("sort", {"item": g, "box": "right"}) for g in t["right"]]), False
        return [solution], True


WIDGETS: dict[str, Widget] = {w.name: w for w in (Wires(), Keypad(), Icons(), Dial(), Switches(), BigButton(), Sorter())}


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
    done: list = field(default_factory=list)  # the right clicks so far (Module.apply)
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

    def apply(self, action: Action) -> str:
        """One click from the player: "step" (right, more to do), "defused" or "strike".

        A one-click answer is one step. A wrong click keeps the progress so far, like a
        cut wire that stays cut.
        """
        solution = self.solution()
        if action == solution:
            # The whole answer in one message (an older client, a test, the answer key):
            # same as making every click that is left.
            self.done.extend(a for a in self.widget.steps(solution)[0] if a not in self.done)
            self.defused = True
            return "defused"
        steps, ordered = self.widget.steps(solution)
        left = list(steps)
        for a in self.done:
            left.remove(a)
        if not (action == left[0] if ordered else action in left):
            return "strike"
        self.done.append(action)
        if len(left) == 1:
            self.defused = True
            return "defused"
        return "step"


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
