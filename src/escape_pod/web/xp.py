# Owner: Teammate 1 (Game, scenes, widgets)
"""XP for one round (spec 2026-11-21-xp-levels-design).

The server decides what a round is worth, because only it knows the true result. The
browser keeps the running total in localStorage (static/progress.js). Sign XP is already
saved there as practice credits, so `signs_xp` tells the browser which part not to save twice.
"""
import math

SIGN_XP = 5
MODULE_XP = 10
WIN_XP = {"beginner": 50, "intermediate": 75, "advanced": 100, "custom": 75}
SECONDS_PER_XP = 2


def round_xp(level: str, defused: int, won: bool, seconds_left: float, signs: int) -> dict:
    parts = []

    def add(label: str, xp: int):
        if xp > 0:
            parts.append({"label": label, "xp": xp})

    add(f"Signs confirmed ({signs})", signs * SIGN_XP)
    add(f"Modules defused ({defused})", defused * MODULE_XP)
    if won:
        add("Bomb defused", WIN_XP.get(level, WIN_XP["intermediate"]))
        # The label rounds up, as the clock on screen does. The XP counts full seconds only.
        shown = max(0, math.ceil(seconds_left))
        add(f"Time left {shown // 60}:{shown % 60:02d}", max(0, int(seconds_left)) // SECONDS_PER_XP)
    return {"parts": parts, "signs_xp": signs * SIGN_XP, "total": sum(p["xp"] for p in parts)}
