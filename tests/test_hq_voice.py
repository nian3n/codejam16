# Owner: Teammate 4 (Puzzles and brain)
import random

import pytest

from escape_pod.brain.hq_bot import BOT_NAME
from escape_pod.brain.hq_voice import CALM, PANIC, SHAKY, mood, nervous

LINES = [
    f"{BOT_NAME} here. Which module do you need help with? Tell me one thing you see on it.",
    "That is the Animal panel. Do you see DOG?",
    "Press the cow.",
    "That was a strike. Let us check the Wire panel again. Tell me the color of the top wire.",
    "Good work. Which module is next? Tell me one thing you see on it.",
]


@pytest.mark.parametrize("level", [CALM, SHAKY, PANIC])
@pytest.mark.parametrize("text", LINES)
def test_the_real_sentence_is_always_there_unchanged(text, level):
    for seed in range(40):
        out = nervous(text, level, random.Random(seed))
        assert text in out and len(out) <= len(text) + 80


def test_the_voice_changes_the_text_most_of_the_time():
    outs = {nervous("Press the cow.", SHAKY, random.Random(s)) for s in range(30)}
    assert len(outs) > 5


def test_panic_sounds_worse_than_calm():
    calm = " ".join(nervous("Press the cow.", CALM, random.Random(s)) for s in range(50))
    panic = " ".join(nervous("Press the cow.", PANIC, random.Random(s)) for s in range(50))
    assert panic.count("!") > calm.count("!")


def test_mood_follows_strikes_and_time():
    assert mood(strikes=0, left_s=290, total_s=300) == CALM
    assert mood(strikes=1, left_s=290, total_s=300) == SHAKY
    assert mood(strikes=0, left_s=80, total_s=300) == SHAKY
    assert mood(strikes=2, left_s=290, total_s=300) == PANIC
    assert mood(strikes=0, left_s=25, total_s=300) == PANIC
