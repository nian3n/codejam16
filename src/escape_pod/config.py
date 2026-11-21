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
CORE_SIGNS = ("yes", "no", "finish")   # confirm a guess, retry, send (spec §6.2)
SIGN_CLIPS_DIR = PACKAGE_DIR / "signs" / "clips"   # glossary clips from PopSign (signs/fetch_popsign.py)
MANUAL_PAGES_DIR = ROOT / "docs" / "manual"
ETC_DIR = ROOT / "etc"
ENV_FILE = ETC_DIR / ".env"
TLS_DIR = ETC_DIR / "tls"                # self-signed cert for --https (git-ignored with etc/)
MODELS_DIR = ROOT / "models"             # git-ignored; uv run download-models fills it
ISLR_DIR = MODELS_DIR / "islr"
HANDSHAPE_FILE = MODELS_DIR / "handshape.npz"   # our own digit model, the fallback (uv run train-digits)
DIGIT_MLP_FILE = MODELS_DIR / "digits" / "asl_mlp.npz"  # ready-made digit model (uv run download-models)
HANDSHAPE_DATA_DIR = ROOT / "data" / "handshape"  # recorded digit samples, git-ignored (uv run record-digits)
LOGS_DIR = ROOT / "logs"                 # git-ignored

# Sign recognition (spec §6). Thresholds are first guesses; tune them with sign-test.
MIRROR_INPUT = False      # flip the frame before MediaPipe (the display is always mirrored)
LEFT_HANDED = False       # mirror landmark x and swap the two hand blocks
SEG_STILL_S = 0.4         # a sign ends when the hands stay still this long
SEG_MIN_S = 0.3           # ignore clips shorter than this
SEG_MAX_S = 3.0           # ignore clips longer than this
SEG_MOVE = 0.006          # mean hand movement per frame (image widths) that counts as moving
MANUAL_CAPTURE_S = 2.5    # Space: fixed capture window

# WebRTC video between the two players. On one Wi-Fi the browsers find each other
# without help. A public STUN server lets them connect across different networks; it
# sees only the players' public IP addresses, never the video. Set ICE_SERVERS = []
# to stay fully local.
ICE_SERVERS = [{"urls": "stun:stun.l.google.com:19302"}]
# TURN relay (web/ice.py): Metered Open Relay. Set both in etc/.env or the host's env.
METERED_APP_ENV = "METERED_APP"
METERED_API_KEY_ENV = "METERED_API_KEY"
# Or a fixed TURN login (Metered dashboard > TURN credentials). TURN_URLS is optional,
# comma-separated; the default is Metered's global relay.
TURN_USERNAME_ENV = "TURN_USERNAME"
TURN_CREDENTIAL_ENV = "TURN_CREDENTIAL"
TURN_URLS_ENV = "TURN_URLS"
METERED_TURN_URLS = [
    "turn:global.relay.metered.ca:80",
    "turn:global.relay.metered.ca:80?transport=tcp",
    "turn:global.relay.metered.ca:443",
    "turns:global.relay.metered.ca:443?transport=tcp",
]

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
    name: Literal["beginner", "intermediate", "advanced", "custom"]
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
    # "bomb", not "module": the defuser never says which module they sign (no selection
    # step), so even at Beginner the recognizer chooses among the whole bomb's words.
    "beginner": Level("beginner", 3, False, 600, "bomb", True, True, True),
    "intermediate": Level("intermediate", 4, False, 300, "bomb", True, False, True),
    "advanced": Level("advanced", 4, True, 180, "all", False, False, False),
}

# The lobby's "Custom" level: the players pick the module count and the time. Everything
# else is as at Intermediate (no hard puzzles, the bomb's words). 5 modules is the most
# the bomb case holds (2 rows of 3 slots, one is the timer).
CUSTOM_MODULES = (1, 5)
CUSTOM_TIMER_S = (60, 1200)  # 1 to 20 minutes


def custom_level(modules: int, timer_s: int) -> Level:
    return Level("custom", modules, False, timer_s, "bomb", True, False, True)
