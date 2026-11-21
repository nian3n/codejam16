# Owner: Teammate 4 (Puzzles and brain)
"""A scripted HQ for the solo game: it reads the agent's signs and answers from the manual.

The bot is a human HQ without the human. It knows the 20 manual pages and nothing about
the bomb (spec rule 3): it sees only the glosses the agent sends and whether the last
action defused a module or cost a strike. It never checks the signs against the real
module. A wrong but clear sign gives a wrong instruction, on purpose: the solo game is
there to practice signing properly.

One exchange per module:
  round 0  the agent signs one or more items; each gloss is in exactly one pool, so the
           page with the most words is the module (test_no_gloss_in_two_pools).
  round 1  the bot asks for every item in reading order (the widget's reading_order).
  round 2  dials: which picture the needle points at; switches: which ones are on.
Then the bot builds a Module from the signed facts and answers with the rule engine and
phrase(), so the bot, the manual and the server's check never disagree.

Pure logic, no I/O: the server calls reply() inline (rule 6 holds, it takes microseconds).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal

from escape_pod.puzzles.engine import Module, load_pool
from escape_pod.puzzles.models import PuzzleSpec
from escape_pod.puzzles.phrase import phrase, word

BOT_NAME = "HQ bot"
CORE = {"yes", "no", "finish"}

GREETING = "HQ here. Which module do you need help with? Sign one thing you see on it."
NEXT = "Good work. Which module is next? Sign one thing you see on it."


@dataclass(frozen=True)
class Script:
    items: str                                   # what the items are called in replies
    q1: str                                      # {n}: how many items the module shows
    q2: str | None = None                        # the second question, if the widget has one
    key: str = ""                                # the facts key for round 1 (not dial/switches)


SCRIPTS: dict[str, Script] = {
    "wires": Script("wire colors", "Sign the wire colors, top to bottom.", key="colors"),
    "keypad": Script("numbers", "Sign the {n} numbers on the display, left to right.", key="display"),
    "icons": Script("pictures", "Sign the {n} pictures, left to right, top row first.", key="icons"),
    "dial": Script("pictures", "Sign the {n} pictures, clockwise from the top.",
                   "Which picture does the needle point at?"),
    "switches": Script("switch labels", "Sign the switch labels, left to right.",
                       "Now sign only the switches that are on. Sign NO if none is on."),
    "big_button": Script("faces", "Sign the faces in the order the screen shows them.", key="faces"),
}


def _unique(words: list[str]) -> list[str]:
    return list(dict.fromkeys(words))


def _recast(spec: PuzzleSpec, facts: dict) -> str:
    w = lambda g: word(g, spec)  # noqa: E731
    if spec.widget == "dial":
        return f"You see: {', '.join(map(w, facts['options']))}. The needle points at {w(facts['needle'])}."
    if spec.widget == "switches":
        return "You see: " + ", ".join(f"{w(s['label'])} ({s['state']})" for s in facts["switches"]) + "."
    return f"You see: {', '.join(map(w, facts[SCRIPTS[spec.widget].key]))}."


class HqBot:
    def __init__(self, pool: dict[str, PuzzleSpec] | None = None):
        self.pool = pool or load_pool()
        self.owner = {g: spec for spec in self.pool.values() for g in spec.pool}
        self.page: PuzzleSpec | None = None   # the open page; None at round 0
        self.round = 1
        self.items: list[str] = []            # round 1 answer, kept for round 2
        self.last: PuzzleSpec | None = None   # the page of the last instruction, until its result

    @property
    def stage(self) -> Literal["module", "details"]:
        return "module" if self.page is None else "details"

    def greeting(self) -> str:
        return GREETING

    # -- helpers -----------------------------------------------------------------
    def _script(self) -> Script:
        assert self.page is not None
        return SCRIPTS[self.page.widget]

    def _question(self) -> str:
        s = self._script()
        assert self.page is not None
        return s.q1.format(n=self.page.setup["shown"]) if self.round == 1 else str(s.q2)

    def _open(self, spec: PuzzleSpec) -> str:
        if spec is not self.last:
            # The agent moved on to another module: a later result is not about the
            # instruction the bot gave before, so it must not close or replace this page.
            self.last = None
        self.page, self.round, self.items = spec, 1, []
        return f"That is the {spec.title}. {self._question()}"

    def _answer(self, facts: dict) -> str:
        assert self.page is not None
        module = Module(self.page, facts)
        text = f"{_recast(self.page, facts)} {phrase(module.solution(), module)}"
        self.last, self.page, self.round, self.items = self.page, None, 1, []
        return text

    # -- the exchange ------------------------------------------------------------
    def reply(self, glosses: list[str]) -> str:
        raw = [g.strip().lower() for g in glosses if g and g.strip()]
        known = [g for g in raw if g in self.owner and g not in CORE]
        if self.page is None:
            return self._find(known)
        page = self.page
        mine = [g for g in known if g in page.pool]
        # NO (maybe twice, or beside YES or FINISH) and no label: every switch is off.
        if page.widget == "switches" and self.round == 2 and "no" in raw and not known:
            return self._answer({"switches": [{"label": g, "state": "off"} for g in self.items]})
        if not mine:
            if known:  # every word is from another page: the agent moved to another module
                return self._find(known)
            return f"I did not see any {self._script().items} from the {page.title}. {self._question()}"
        return self._round1(mine) if self.round == 1 else self._round2(mine, known)

    def _find(self, known: list[str]) -> str:
        if not known:
            self.page = None
            return "I do not know that word. Sign one thing from the module again."
        votes = Counter(self.owner[g].id for g in known)
        best = max(votes.values())
        top = [spec for spec in self.pool.values() if votes.get(spec.id) == best]
        if len(top) > 1:
            self.page = None
            return f"Is it the {top[0].title} or the {top[1].title}? Sign one more thing from the module."
        return self._open(top[0])

    def _round1(self, mine: list[str]) -> str:
        assert self.page is not None
        n, got = self.page.setup["shown"], _unique(mine)
        if len(got) != n:
            return f"I need {n} different {self._script().items}. You signed {len(got)}. Sign all {n} again."
        s = self._script()
        if s.q2 is None:
            return self._answer({s.key: got})
        self.items, self.round = got, 2
        return s.q2

    def _round2(self, mine: list[str], known: list[str]) -> str:
        assert self.page is not None
        if self.page.widget == "dial":
            got = _unique(mine)
            if len(got) != 1 or got[0] not in self.items:
                return "Sign the one picture that the needle points at."
            return self._answer({"options": self.items, "needle": got[0]})
        # switches: every signed word must be one of the labels from round 1
        if any(g not in self.items for g in known):
            return "Sign only the switches that are on, or NO if none is on."
        on = set(mine)
        return self._answer({"switches": [{"label": g, "state": "on" if g in on else "off"} for g in self.items]})

    def on_result(self, defused: bool) -> str | None:
        """The agent acted after an instruction. None when there was no instruction to judge."""
        spec, self.last = self.last, None
        if spec is None:
            return None
        if defused:
            self.page = None
            return NEXT
        # The bot cannot tell which sign was wrong: it trusts the signs. Ask for the details again.
        self._open(spec)
        return f"That was a strike. Check the {spec.title} again. {self._question()}"

