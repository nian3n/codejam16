# Owner: shared (all teammates; add fields, never rename them)
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Code and the data the game loads at runtime live in the package (src/escape_pod/).
# Things people read or keep private live at the repo root (docs/, etc/).
PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent.parent
PUZZLE_DIR = PACKAGE_DIR / "puzzles" / "data"
ICONS_FILE = PACKAGE_DIR / "assets" / "icons.json"
STATIC_DIR = PACKAGE_DIR / "web" / "static"
MANUAL_PAGES_DIR = ROOT / "docs" / "manual"
ETC_DIR = ROOT / "etc"
ENV_FILE = ETC_DIR / ".env"
MODELS_DIR = ROOT / "models"             # git-ignored; uv run download-models fills it
ISLR_DIR = MODELS_DIR / "islr"
LOGS_DIR = ROOT / "logs"                 # git-ignored

# Sign recognition (spec §6). Thresholds are first guesses; tune them with sign-test.
CORE_SIGNS = ("yes", "no", "finish")
MIRROR_INPUT = False      # flip the frame before MediaPipe (the display is always mirrored)
LEFT_HANDED = False       # mirror landmark x and swap the two hand blocks
SEG_STILL_S = 0.4         # a sign ends when the hands stay still this long
SEG_MIN_S = 0.3           # ignore clips shorter than this
SEG_MAX_S = 3.0           # ignore clips longer than this
SEG_MOVE = 0.006          # mean hand movement per frame (image widths) that counts as moving
MANUAL_CAPTURE_S = 2.5    # Space: fixed capture window

# Secrets: put them in etc/.env (git-ignored; copy etc/.env.example). Never in code.
# The provider is not chosen yet, so the variable name is generic.
LLM_API_KEY_ENV = "LLM_API_KEY"


def load_env(path: Path = ENV_FILE) -> None:
    """Read KEY=VALUE lines from etc/.env into os.environ.

    A real environment variable wins over the file, so CI or a shell export can
    override it. Tiny on purpose: no python-dotenv dependency for a few keys.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_env()

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
