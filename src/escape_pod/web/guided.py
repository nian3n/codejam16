# Owner: Teammate 1 (Game, scenes, widgets)
"""Private signer clues and the shared round state for the guided game."""
from dataclasses import dataclass, field
import random
from typing import Literal

TIMED_SECONDS = 120
NUMBERS = {1: "one", 2: "two", 3: "three"}


@dataclass(frozen=True)
class Control:
    color: str
    number: int | None = None

    @property
    def id(self):
        return f"{self.color}-{self.number}" if self.number else f"{self.color}-wire"

    def panel_view(self):
        return {"id": self.id, "color": self.color, "number": self.number}

    def clue_view(self):
        if self.number:
            text = f"Press {self.color} {self.number}"
            spelling = f"press {self.color} {NUMBERS[self.number]}"
        else:
            text = f"Cut {self.color}"
            spelling = text.lower()
        return {"text": text, "spelling": spelling, "picture": self.panel_view()}


COLORS = ("blue", "teal", "amber")
BUTTONS = tuple(Control(color, number) for color in COLORS for number in NUMBERS)
WIRES = (Control("red"), Control("green"), Control("yellow"))
PRACTICE = BUTTONS[2]


@dataclass
class GuidedRound:
    step: Literal["practice", "ready", "timed", "untimed", "unlocked", "timeout"] = "practice"
    deck: list[Control] = field(default_factory=list)
    index: int = 0
    turn: int = 0
    repeat: int = 0
    feedback: str = ""
    swapped: bool = False

    @property
    def clue(self):
        if self.step == "practice":
            return PRACTICE
        if self.step in ("timed", "untimed"):
            return self.deck[self.index]
        return None

    def begin_practice(self):
        self.step = "practice"
        buttons = [button for button in BUTTONS if button != PRACTICE]
        color_to_fingerspell = random.choice([button for button in buttons if button.color in ("teal", "amber")])
        other_button = random.choice([button for button in buttons if button != color_to_fingerspell])
        self.deck = [color_to_fingerspell, other_button, random.choice(WIRES)]
        random.shuffle(self.deck)
        self.move_to_next_clue()
        self.index = 0
        self.feedback = ""

    def move_to_next_clue(self):
        self.turn += 1
        self.repeat = 0

    def view(self, role):
        state = {
            "step": self.step,
            "turn": self.turn,
            "repeat": self.repeat,
            "feedback": self.feedback,
            "swapped": self.swapped,
            "solved": self.index,
            "total": len(self.deck),
        }
        if role == "defuser" and self.clue:
            state["clue"] = self.clue.clue_view()
        elif role == "expert":
            state["controls"] = [control.panel_view() for control in (*BUTTONS, *WIRES)]
        if self.step == "unlocked":
            state["review"] = [control.clue_view() for control in (PRACTICE, *self.deck)]
        return state
