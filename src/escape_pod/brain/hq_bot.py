# Owner: Teammate 4 (Puzzles and brain)
"""A scripted HQ for the solo game: it reads the agent's signs and answers from the manual.

The bot is a human HQ without the human. It knows the 20 manual pages and nothing about
the bomb (spec rule 3): it sees only the glosses the agent sends and whether the last
action defused a module or cost a strike. It never checks the answers against the real
module. A wrong but clear sign gives a wrong instruction, on purpose: the solo game is
there to practice signing properly.

One exchange per module:
  round 0  the agent signs one or more items; each gloss is in exactly one pool, so the
           page with the most words is the module (test_no_gloss_in_two_pools). The
           items also count as facts: "there is a cat".
  then     the bot walks the page's rules in order, like a human HQ reading the manual,
           and asks only for the fact that the next undecided condition needs ("Do you
           see DOG?", "Tell me the color of the top wire."). A false condition skips its
           rule. The first rule that holds gives the action; if its target is a position
           ("press the last button") the bot asks for that item too.
Playtesting showed that signing every item before any answer was too slow, so the bot
asks the fewest questions the rules allow.

Conditions use engine.cond_holds() and the wording comes from phrase(), so the bot, the
manual and the server's check never disagree.

Pure logic, no I/O: the server calls reply() inline (rule 6 holds, it takes microseconds).
"""
from __future__ import annotations

from collections import Counter
from typing import Literal

from escape_pod.puzzles.engine import ALPHA, ORDERS, WIDGETS, cond_holds, load_pool
from escape_pod.puzzles.models import Action, PuzzleSpec
from escape_pod.puzzles.phrase import phrase, word

BOT_NAME = "Rob"  # the solo handler. Players found "HQ" unclear, so the bot has a name
CORE = {"yes", "no", "finish"}
POSITIONS = ("first", "last")

GREETING = f"{BOT_NAME} here. Which module do you need help with? Tell me one thing you see on it."
NEXT = "Good work. Which module is next? Tell me one thing you see on it."
UNKNOWN = "I do not know that word. Tell me one thing from the module again."

# How to name the first and the last item of each widget, in the manual's reading order.
PLACES = {
    "wires": ("the color of the top wire", "the color of the bottom wire"),
    "keypad": ("the first number on the display, on the left", "the last number on the display, on the right"),
    "icons": ("the top-left picture", "the bottom-right picture"),
    "dial": ("the picture at the top of the dial", "the last picture, going clockwise from the top"),
    "switches": ("the label of the leftmost switch", "the label of the rightmost switch"),
    "big_button": ("the face marked 1", "the face marked {n}"),
    "sorter": ("the picture on the far left of the tray", "the picture on the far right of the tray"),
}
NOUNS = {"wires": "wire color", "keypad": "number", "icons": "picture", "dial": "picture",
         "switches": "switch label", "big_button": "face", "sorter": "picture"}
TARGET_SLOTS = ("icon", "wire", "to", "release_on", "switch")


def _sign(g: str, spec: PuzzleSpec) -> str:
    """A gloss in sign-name capitals, as the glossary and the chips show it: DOG, FRENCH FRIES."""
    return word(g, spec).upper()


def _an(text: str) -> str:
    return ("an " if text[:1].lower() in "aeiou" else "a ") + text


class HqBot:
    def __init__(self, pool: dict[str, PuzzleSpec] | None = None):
        self.pool = pool or load_pool()
        self.owner = {g: spec for spec in self.pool.values() for g in spec.pool}
        self.page: PuzzleSpec | None = None   # the open page; None at round 0
        self.known: dict = {}                 # derived facts so far: "has:cat", "first", "needle", ...
        self.on: set[str] | None = None       # every switch that is on, once the agent listed them
        self.pending: str | None = None       # the fact key the last question asked for
        self.last: PuzzleSpec | None = None   # the page of the last instruction, until its result

    @property
    def stage(self) -> Literal["module", "details"]:
        return "module" if self.page is None else "details"

    def greeting(self) -> str:
        return GREETING

    # -- questions -----------------------------------------------------------------
    def _question(self, key: str) -> str:
        spec = self.page
        assert spec is not None
        w = spec.widget
        if key.startswith("has:"):
            g = key[4:]
            if w == "wires":
                return f"Is there {_an(word(g, spec) + ' wire')}?"
            if w == "keypad":
                return f"Does the display show {_sign(g, spec)}?"
            if w == "switches":
                return f"Do you see {_an(_sign(g, spec) + ' switch')}?"
            return f"Do you see {_sign(g, spec)}?"
        if key in POSITIONS:
            place = PLACES[w][POSITIONS.index(key)].format(n=spec.setup["shown"])
            return f"Tell me {place}."
        if key == "needle":
            return "Tell me the picture that the needle points at."
        if key.startswith("state_of:"):
            return f"Is the {_sign(key[9:], spec)} switch on?"
        if key == "count_on":
            return "Tell me which switches are on. Tell me NO if none is on."
        if key == "display":
            return f"Tell me the {spec.setup['shown']} numbers on the display, left to right."
        if key == "items" and w == "sorter":  # one question answers every sorter rule
            return f"Tell me the {spec.setup['shown']} {spec.setup.get('noun', 'pictures')} on the tray, from left to right."
        if key == "items":  # for an alphabet rule: the order does not matter
            where = " on the dial" if w == "dial" else ""
            return f"Tell me the {spec.setup['shown']} pictures{where}, in any order."
        raise ValueError(key)

    def _ask(self, key: str) -> str:
        if self.page is not None and self.page.widget == "keypad" and key in POSITIONS:
            key = "display"  # 3 numbers answer first, last and every has: at once
        if self.page is not None and self.page.widget == "sorter":
            key = "items"  # the sort needs every picture anyway, so ask for all of them at once
        self.pending = key
        return self._question(key)

    # -- the rule walk -----------------------------------------------------------------
    def _missing(self, cond: list) -> str | None:
        """The fact key this condition still needs, or None when it can be decided."""
        k, _, v = cond
        if k.startswith("state_of:"):
            label = k[9:]
            if self.known.get("has:" + label) is False:
                return None  # no such switch: the engine's missing key never matches
            if k not in self.known and self.on is not None and self.known.get("has:" + label):
                self.known[k] = "on" if label in self.on else "off"
        if k not in self.known:
            return k
        if k in POSITIONS and v in POSITIONS and v not in self.known:
            return v
        return None

    def _derived(self) -> dict:
        # cond_holds treats a missing has:<g> as False, so a known False stays out.
        return {k: v for k, v in self.known.items() if v is not False}

    def _step(self) -> str:
        """Ask for the next fact, or give the instruction."""
        spec = self.page
        assert spec is not None
        for rule in spec.rules:
            if not rule.is_else:
                when = rule.when or []
                decided = [c for c in when if self._missing(c) is None]
                if any(not cond_holds(c, self._derived()) for c in decided):
                    continue  # a known condition is false: skip this rule
                need = next((m for c in when if (m := self._missing(c))), None)
                if need:
                    return self._ask(need)
            return self._act(rule.action())
        raise AssertionError("the last rule is always else")

    def _act(self, action: Action) -> str:
        """Fill in a position target ("the last button"), then give the instruction."""
        spec = self.page
        assert spec is not None
        t = dict(action.target)
        if t.get("order") in ORDERS or t.get("to") in ALPHA:
            if "items" not in self.known:
                return self._ask("items")
            items = self.known["items"]
            if "order" in t:
                t = {"icons": sorted(items, reverse=ORDERS[t["order"]])}
            else:
                t = {"to": (min if t["to"] == "alpha_first" else max)(items)}
        if action.verb == "sort":
            if "items" not in self.known:
                return self._ask("items")
            t = WIDGETS["sorter"].resolve(action, {"items": self.known["items"]}).target
        if "keys_from" in t:
            if "display" not in self.known:
                return self._ask("display")
            t = {"keys": WIDGETS["keypad"].derive({"display": self.known["display"]})[t["keys_from"]]}
        for slot in TARGET_SLOTS:
            if t.get(slot) in POSITIONS:
                pos = t[slot]
                if pos not in self.known:
                    return self._ask(pos)
                if slot == "wire":
                    t = {"color": self.known[pos]}
                else:
                    t[slot] = self.known[pos]
        if t.get("state") == "flip":
            key = f"state_of:{t['switch']}"
            self.known.setdefault(f"has:{t['switch']}", True)
            if self._missing([key, "==", "on"]):
                return self._ask(key)
            t["state"] = "off" if self.known[key] == "on" else "on"
        text = phrase(Action(action.verb, t), spec=spec)
        self.last = spec
        self._close()
        return text

    def _close(self) -> None:
        self.page, self.known, self.on, self.pending = None, {}, None, None

    # -- the exchange ----------------------------------------------------------------
    def _open(self, spec: PuzzleSpec, items: list[str], intro: str = "") -> str:
        if spec is not self.last:
            # The agent moved on to another module: a later result is not about the
            # instruction the bot gave before, so it must not close or replace this page.
            self.last = None
        self._close()
        self.page = spec
        self.known = {f"has:{g}": True for g in items if g in spec.pool}
        return f"{intro or f'That is the {spec.title}.'} {self._step()}"

    def _find(self, known: list[str]) -> str:
        if not known:
            self._close()
            return UNKNOWN
        votes = Counter(self.owner[g].id for g in known)
        best = max(votes.values())
        top = [spec for spec in self.pool.values() if votes.get(spec.id) == best]
        if len(top) > 1:
            self._close()
            return f"Is it the {top[0].title} or the {top[1].title}? Tell me one more thing from the module."
        return self._open(top[0], known)

    def reply(self, glosses: list[str]) -> str:
        raw = [g.strip().lower() for g in glosses if g and g.strip()]
        known = [g for g in raw if g in self.owner and g not in CORE]
        if self.page is None:
            return self._find(known)
        mine = [g for g in known if g in self.page.pool]
        if known and not mine:  # every word is from another page: the agent moved to another module
            return self._find(known)
        key = self.pending
        assert key is not None
        again = self._take(key, raw, mine)
        if again is not None:
            return again
        for g in mine:  # any item the agent names is on the module
            self.known.setdefault(f"has:{g}", True)
        return self._step()

    def _take(self, key: str, raw: list[str], mine: list[str]) -> str | None:
        """Store the answer to `key`. Returns a new question when the answer does not fit."""
        page = self.page
        assert page is not None
        says_yes, says_no = "yes" in raw, "no" in raw
        if key.startswith(("has:", "state_of:")):
            kind, g = key.split(":", 1)
            yes = says_yes or (kind == "has" and g in mine) or (kind == "state_of" and "on" in raw)
            if yes == says_no:  # neither, or both
                return f"Tell me YES or NO. {self._question(key)}"
            if kind == "has":
                self.known[key] = yes
            else:
                self.known[key] = "on" if yes else "off"
                self.known.setdefault(f"has:{g}", True)
            return None
        got = list(dict.fromkeys(mine))
        if key in POSITIONS or key == "needle":
            if len(got) != 1:
                return f"Tell me one {NOUNS[page.widget]}. {self._question(key)}"
            self.known[key] = got[0]
            return None
        if key == "count_on":
            if not got and not says_no:
                return f"Tell me the switch labels, or NO. {self._question(key)}"
            self.known["count_on"] = len(got)
            self.on = set(got)
            self.known.update({f"has:{g}": True for g in got})
            return None
        if key == "items":
            n = page.setup["shown"]
            if len(got) != n:
                return f"I need {n} different pictures. You told me {len(got)}. {self._question(key)}"
            self.known["items"] = got
            self.known.update({f"has:{g}": g in got for g in page.pool})
            if page.widget == "sorter":  # signed left to right
                self.known.update(first=got[0], last=got[-1])
            return None
        if key == "display":
            n = page.setup["shown"]
            if len(got) != n:
                return f"I need {n} different numbers. You told me {len(got)}. {self._question(key)}"
            d = WIDGETS["keypad"].derive({"display": got})
            self.known.update(first=d["first"], last=d["last"], display=got)
            self.known.update({f"has:{g}": g in got for g in page.pool})
            return None
        raise ValueError(key)

    def on_result(self, defused: bool) -> str | None:
        """The agent acted after an instruction. None when there was no instruction to judge."""
        spec, self.last = self.last, None
        if spec is None:
            return None
        if defused:
            self._close()
            return NEXT
        # The bot cannot tell which answer was wrong: it trusts the signs. Walk the page again.
        return self._open(spec, [], f"That was a strike. Let us check the {spec.title} again.")
