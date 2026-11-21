# Owner: Teammate 1 (Game, scenes, widgets)
"""The case and wire tray that the agent opens before reaching the module board."""
from dataclasses import dataclass, field
from random import Random
from typing import Literal

from escape_pod.puzzles.engine import WIDGETS, load_pool
from escape_pod.vision.handshape import DIGITS

POSITIONS = ("first", "second", "third", "fourth")
LOCK_LENGTH = 3


@dataclass
class Mission:
    code: str
    colors: list[str]
    wire_order: list[int]
    stage: Literal["case_lock", "wire_tray", "modules"] = "case_lock"
    revision: int = 0  # Every new gate input must answer the last acknowledged state.
    lock_confirmed: int = 0
    cuts: list[int] = field(default_factory=list)
    confirmed_color: str | None = None
    feedback: str = ""

    @classmethod
    def draw(cls, rng: Random) -> "Mission":
        code = "".join(rng.choices(DIGITS, k=LOCK_LENGTH))
        colors = WIDGETS["wires"].generate(load_pool()["colors"], rng)["colors"]
        return cls(code, colors, rng.sample(range(len(POSITIONS)), len(POSITIONS)))

    @property
    def position_order(self) -> list[str]:
        return [POSITIONS[index] for index in self.wire_order]

    def confirm(self, glosses: list[str]) -> list[str]:
        """Return the confirmed vocabulary to share with HQ; only matching digits fill slots."""
        self.revision += 1
        if self.stage == "case_lock":
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

        self.confirmed_color = None
        if len(glosses) != 1 or glosses[0] not in load_pool()["colors"].pool:
            self.feedback = "Confirm one wire color at a time."
            return []
        self.confirmed_color = glosses[0]
        self.feedback = "Color confirmed. Select the wire."
        return glosses

    def cut(self, index: int) -> Literal["retry", "strike", "cut"]:
        self.revision += 1
        if self.confirmed_color is None:
            self.feedback = "Sign the wire color first"
            return "retry"
        color, self.confirmed_color = self.confirmed_color, None
        if color != self.colors[index]:
            self.feedback = "The selected wire differs from your confirmed color. Sign again."
            return "strike"
        if index != self.wire_order[len(self.cuts)]:
            self.feedback = "Wrong position. Check the order with HQ, then sign again."
            return "strike"
        self.cuts.append(index)
        self.feedback = "Wire accepted. Confirm the next color."
        if len(self.cuts) == len(self.wire_order):
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
                payload["case_code"] = self.code
            elif self.stage == "wire_tray":
                payload.update(wires=self.colors, cuts=self.cuts, confirmed_color=self.confirmed_color)
        elif role == "expert" and self.stage == "wire_tray":
            payload["wire_rule"] = self.position_order
        return payload
