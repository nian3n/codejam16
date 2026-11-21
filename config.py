# Owner: shared (all teammates; add fields, never rename them)
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent
PUZZLE_DIR = ROOT / "puzzles" / "data"
MANUAL_PAGES_DIR = ROOT / "manual" / "pages"
ICONS_FILE = ROOT / "assets" / "icons.json"

MAX_STRIKES = 3


@dataclass(frozen=True)
class Level:
    name: Literal["beginner", "intermediate", "advanced"]
    modules: int
    allow_hard: bool
    timer_s: int | None
    allowed_scope: Literal["module", "bomb", "all"]
    briefing: bool
    sign_cards: bool
    recast: bool


# Spec §9.1. Beginner uses 3 modules (spec: 2-3) and a 10 min timer (spec: off or 10 min);
# the web lobby always runs a timer, so "off" is not offered yet.
LEVELS = {
    "beginner": Level("beginner", 3, False, 600, "module", True, True, True),
    "intermediate": Level("intermediate", 4, False, 300, "bomb", True, False, True),
    "advanced": Level("advanced", 4, True, 180, "all", False, False, False),
}
