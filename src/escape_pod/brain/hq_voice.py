# Owner: Teammate 4 (Puzzles and brain)
"""The solo bot's nervous voice: a few shaky words around the bot's real sentence.

HqBot.reply() stays exact and testable; this only decorates its text for the feed. The
bot's sentence is never changed or cut, so the instruction the player reads is still
word for word what phrase() and the manual say (spec rules 1 and 2). The nerves grow
with the danger: a little shaky at the start, worse after a strike or with under a third
of the time left, full panic at the last strike or the last 30 s.
"""
from __future__ import annotations

import random
import re

from escape_pod.brain.hq_bot import GREETING

CALM, SHAKY, PANIC = 0, 1, 2

# What kind of line the bot is saying, from its own wording (hq_bot.py).
VERBS = ("press", "cut", "turn", "type", "set", "hold", "flip")

OPENERS = {
    "greeting": [
        ["Is this thing on? Okay.", "Hi. Hello. Okay.", "Right, um."],
        ["Is this on? Oh good. Okay.", "Um. Hi. Okay, okay.", "Uh, can you hear me?"],
        ["Okay okay okay.", "Is this on?! Good!", "Oh boy. Oh boy."],
    ],
    "question": [
        ["Okay.", "Um.", "Right.", "Let me see.", ""],
        ["Uh, okay.", "Um, um.", "Hang on, hang on.", "O-okay.", "Right, right."],
        ["Quick!", "Uh, uh!", "Oh no, okay!", "F-fast!", "Hurry, hurry!"],
    ],
    "instruction": [
        ["Got it.", "Okay, the manual says:", "Here goes.", ""],
        ["I think, I think I have it.", "Okay, the manual says:", "Deep breath.", "O-okay."],
        ["THIS ONE!", "Okay, okay, okay!", "I hope I am right!", "N-now!"],
    ],
    "strike": [
        ["Oh no.", "Oops.", "Hmm."],
        ["Oh no. Oh no.", "W-what happened?", "That was loud."],
        ["NO NO NO!", "Oh no, oh no, oh no!", "We are running out of tries!"],
    ],
    "relief": [
        ["Phew.", "Nice.", "Yes!"],
        ["Phew! Oh, phew.", "Yes. Okay. Yes.", "My hands are shaking."],
        ["YES! Phew!", "Oh thank goodness!", "Okay! Okay! Next!"],
    ],
}
CLOSERS = {
    "greeting": [["", "Take your time."], ["", "No pressure. Ha."], ["Hurry!", "Please be quick!"]],
    "question": [["", ""], ["", "Carefully.", "Please."], ["Hurry!", "Quick, please!", "Fast!"]],
    "instruction": [["", "Careful."], ["Careful!", "I think.", "Please be right."], ["NOW!", "Go, go, go!", "Please work!"]],
    "strike": [["", ""], ["", "We can do this."], ["Faster!", "Come on, come on!"]],
    "relief": [["", ""], ["", "My hands are sweaty."], ["Keep going!", "Hurry!"]],
}
OPENER_ODDS = (0.6, 0.85, 1.0)
CLOSER_ODDS = (0.25, 0.5, 0.8)


def mood(strikes: int, left_s: float, total_s: float) -> int:
    if strikes >= 2 or left_s <= 30:
        return PANIC
    if strikes >= 1 or left_s <= total_s / 3:
        return SHAKY
    return CALM


def kind_of(text: str) -> str:
    if text == GREETING:
        return "greeting"
    if text.startswith("That was a strike"):
        return "strike"
    if text.startswith("Good work"):
        return "relief"
    last = re.split(r"(?<=[.?!])\s+", text.strip())[-1].lower()
    if last.startswith(VERBS) and not last.endswith("?"):
        return "instruction"
    return "question"


def nervous(text: str, level: int, rng: random.Random) -> str:
    kind = kind_of(text)
    level = max(CALM, min(PANIC, level))
    opener = rng.choice(OPENERS[kind][level]) if rng.random() < OPENER_ODDS[level] else ""
    closer = rng.choice(CLOSERS[kind][level]) if rng.random() < CLOSER_ODDS[level] else ""
    return " ".join(p for p in (opener, text, closer) if p)
