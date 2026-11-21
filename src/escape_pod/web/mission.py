# Owner: Teammate 1 (Game, scenes, widgets)
"""The case and wire tray that the agent opens before reaching the module board."""
from dataclasses import dataclass, field
from random import Random
from typing import Literal

from escape_pod.puzzles.engine import WIDGETS, load_pool
from escape_pod.vision.handshape import DIGITS

LOCK_LENGTH = 3
# The case code never uses 2: the digit model rarely reads a signed 2 (playtest, Nov 2026).
# game_signs.js leaves 2 out of the case lock's allowed words too.
LOCK_DIGITS = tuple(d for d in DIGITS if d != "2")


@dataclass
class Mission:
    """Two gates before the module board (spec 2026-11-21-two-player-gates-design).

    Case lock. Two players (wheels=True): only the handler sees the code and signs it;
    the agent reads the video and sets the code on wheels (try_code). Solo: the agent
    signs the code on the tag and the digit model reads it (confirm).
    Wire tray: the agent signs the four wire colors (confirm). Once all four arrived,
    the cuts unlock. The handler's manual has a ranking of all 8 colors, drawn per
    round; the cut order is the tray's colors in that ranking (wire_order).
    """
    code: str
    colors: list[str]
    rank: list[str]
    wheels: bool = False
    stage: Literal["case_lock", "wire_tray", "modules"] = "case_lock"
    revision: int = 0  # Every new gate input must answer the last acknowledged state.
    lock_confirmed: int = 0
    cuts: list[int] = field(default_factory=list)
    signed_colors: list[str] = field(default_factory=list)  # tray colors the agent signed, first time each
    feedback: str = ""

    @classmethod
    def draw(cls, rng: Random, wheels: bool = False) -> "Mission":
        code = "".join(rng.choices(LOCK_DIGITS, k=LOCK_LENGTH))
        pool = load_pool()["colors"].pool
        colors = WIDGETS["wires"].generate(load_pool()["colors"], rng)["colors"]
        return cls(code, colors, rng.sample(pool, len(pool)), wheels)

    @property
    def wire_order(self) -> list[int]:
        """Tray indexes in cut order: the tray's colors sorted by the round's ranking."""
        return sorted(range(len(self.colors)), key=lambda i: self.rank.index(self.colors[i]))

    @property
    def cut_colors(self) -> list[str]:
        return [self.colors[i] for i in self.wire_order]

    @property
    def tray_ready(self) -> bool:
        return set(self.colors) <= set(self.signed_colors)

    def try_code(self, code) -> Literal["retry", "strike", "open"]:
        """The agent's wheels (two players only). A malformed code is a retry, never a strike."""
        self.revision += 1
        if (not self.wheels or self.stage != "case_lock" or not isinstance(code, str)
                or len(code) != LOCK_LENGTH or not all(d in DIGITS for d in code)):
            self.feedback = "Set all three wheels, then open the lock."
            return "retry"
        if code != self.code:
            self.feedback = "The lock did not open. Watch your handler sign the code again."
            return "strike"
        self.lock_confirmed = LOCK_LENGTH
        self.stage = "wire_tray"
        self.feedback = ""
        return "open"

    def confirm(self, glosses: list[str]) -> list[str]:
        """Return the confirmed vocabulary to share with the handler (empty: nothing to share)."""
        self.revision += 1
        if self.stage == "case_lock":
            if self.wheels:
                return []  # two players: the handler signs the code, the agent sets wheels
            remaining = len(self.code) - self.lock_confirmed
            if not 1 <= len(glosses) <= remaining or any(g not in DIGITS for g in glosses):
                self.feedback = "Confirm one digit per slot, in order."
                return []
            self.feedback = ""
            for digit in glosses:
                if digit != self.code[self.lock_confirmed]:
                    self.feedback = "That digit did not match. Check the tag and retry the next slot."
                    break
                self.lock_confirmed += 1
            if self.lock_confirmed == len(self.code):
                self.stage = "wire_tray"
            return glosses

        pool = load_pool()["colors"].pool
        if not 1 <= len(glosses) <= len(self.colors) or any(g not in pool for g in glosses):
            self.feedback = "Sign wire colors only, up to four."
            return []
        # A color that is not on the tray costs nothing (a recognition slip, spec rule 4).
        for color in glosses:
            if color in self.colors and color not in self.signed_colors:
                self.signed_colors.append(color)
        self.feedback = ("All four colors sent. Cut the wires in the order your handler gives."
                         if self.tray_ready else "Sign the colors of all four wires.")
        return glosses

    def cut(self, index: int) -> Literal["retry", "strike", "cut"]:
        self.revision += 1
        if not self.tray_ready:
            self.feedback = "Sign the colors of all four wires first."
            return "retry"
        if index != self.wire_order[len(self.cuts)]:
            self.feedback = "Wrong wire. Check the order with your handler."
            return "strike"
        self.cuts.append(index)
        self.feedback = "Wire cut. Cut the next one."
        if len(self.cuts) == len(self.colors):
            self.stage = "modules"
            self.feedback = ""
        return "cut"

    def view(self, role: str | None) -> dict:
        payload = {
            "stage": self.stage,
            "revision": self.revision,
            "lock_confirmed": self.lock_confirmed,
            "cut_count": len(self.cuts),
        }
        if role == "defuser":
            payload["feedback"] = self.feedback
            if self.stage == "case_lock":
                payload.update({"lock_wheels": True} if self.wheels else {"case_code": self.code})
            elif self.stage == "wire_tray":
                payload.update(wires=self.colors, cuts=self.cuts, signed_colors=self.signed_colors)
        elif role == "expert":
            if self.stage == "case_lock" and self.wheels:
                payload["case_code"] = self.code
            elif self.stage == "wire_tray":
                # Only the count: the handler reads the colors on the video (or with a hint).
                payload.update(wire_rank=self.rank, colors_received=len(self.signed_colors))
        return payload
