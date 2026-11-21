# Owner: Teammate 4 (Puzzles and brain)
"""The scripted bot HQ (brain/hq_bot.py): signs in, the rule engine's instruction out."""
import random

import pytest

from escape_pod.brain.hq_bot import HqBot
from escape_pod.puzzles.engine import WIDGETS, Module, load_pool
from escape_pod.puzzles.phrase import phrase

POOL = load_pool()


def signs_for(module) -> list[list[str]]:
    """The messages a perfect player sends after round 0, from module.facts."""
    f, w = module.facts, module.spec.widget
    if w == "dial":
        return [list(f["options"]), [f["needle"]]]
    if w == "switches":
        on = [s["label"] for s in f["switches"] if s["state"] == "on"]
        return [[s["label"] for s in f["switches"]], on or ["no"]]
    key = {"wires": "colors", "keypad": "display", "icons": "icons", "big_button": "faces"}[w]
    return [list(f[key])]


def make(spec_id, facts):
    return Module(POOL[spec_id], facts)


@pytest.mark.parametrize("spec_id", sorted(POOL))
def test_every_puzzle_gives_the_engine_instruction(spec_id):
    spec = POOL[spec_id]
    for seed in range(50):
        module = Module(spec, WIDGETS[spec.widget].generate(spec, random.Random(seed)))
        bot = HqBot()
        first = WIDGETS[spec.widget].items(module.facts)[0]
        assert bot.reply([first]).startswith(f"That is the {spec.title}.")
        assert bot.stage == "details"
        for msg in signs_for(module):
            last = bot.reply(msg)
        assert last.endswith(phrase(module.solution(), module)), (seed, last)
        assert bot.stage == "module"


def test_unknown_word_and_tie():
    bot = HqBot()
    assert bot.reply(["hello"]) == "I do not know that word. Sign one thing from the module again."
    tie = bot.reply(["cat", "red"])
    assert tie.startswith(("Is it the Animal panel or the Wire panel?", "Is it the Wire panel or the Animal panel?"))
    assert tie.endswith("Sign one more thing from the module.")
    assert bot.stage == "module"
    assert bot.reply(["cat", "red", "dog"]).startswith("That is the Animal panel.")


def test_round1_needs_n_different_words():
    bot = HqBot()
    bot.reply(["cat"])
    assert bot.reply(["cat", "dog", "dog", "cow"]) == "I need 4 different pictures. You signed 3. Sign all 4 again."
    assert bot.stage == "details"


def test_dial_asks_for_the_needle_and_checks_it():
    bot = HqBot()
    assert bot.reply(["see"]) == "That is the Sensor dial. Sign the 4 pictures, clockwise from the top."
    assert bot.reply(["see", "hear", "taste", "smile"]) == "Which picture does the needle point at?"
    assert bot.reply(["look"]) == "Sign the one picture that the needle points at."
    reply = bot.reply(["hear"])
    m = make("senses", {"options": ["see", "hear", "taste", "smile"], "needle": "hear"})
    assert reply == f"You see: see, hear, taste, smile. The needle points at hear. {phrase(m.solution(), m)}"


def test_switches_on_and_no():
    labels = ["lamp", "bed", "tv", "chair"]
    bot = HqBot()
    bot.reply(["lamp"])
    assert bot.reply(labels) == "Now sign only the switches that are on. Sign NO if none is on."
    reply = bot.reply(["no"])
    assert reply.startswith("You see: lamp (off), bed (off), TV (off), chair (off).")
    bot.reply(["bed"])
    bot.reply(labels)
    assert bot.reply(["lamp", "dog"]) == "Sign only the switches that are on, or NO if none is on."
    reply = bot.reply(["lamp", "tv"])
    m = make("home_things", {"switches": [{"label": g, "state": "on" if g in ("lamp", "tv") else "off"} for g in labels]})
    assert reply == f"You see: lamp (on), bed (off), TV (on), chair (off). {phrase(m.solution(), m)}"


def test_core_words_are_ignored_outside_switches():
    bot = HqBot()
    bot.reply(["yes", "cat"])
    assert bot.page.id == "pets_farm"
    assert "You see: cat, dog, cow, pig." in bot.reply(["cat", "finish", "dog", "no", "cow", "pig"])


def test_module_change_in_details():
    bot = HqBot()
    bot.reply(["cat"])
    assert bot.reply(["red"]).startswith("That is the Wire panel.")
    assert bot.page.id == "colors"


def test_no_word_from_the_page():
    bot = HqBot()
    bot.reply(["cat"])
    assert bot.reply(["hello"]) == ("I did not see any pictures from the Animal panel. "
                                    "Sign the 4 pictures, left to right, top row first.")


def test_wrong_sign_gives_the_instruction_for_the_signed_facts():
    # The module shows a cow, but the player signs HORSE: the bot trusts the signs.
    true = make("pets_farm", {"icons": ["cow", "pig", "duck", "hen"]})
    signed = make("pets_farm", {"icons": ["horse", "pig", "duck", "hen"]})
    bot = HqBot()
    bot.reply(["pig"])
    reply = bot.reply(["horse", "pig", "duck", "hen"])
    assert reply.endswith(phrase(signed.solution(), signed))
    assert phrase(true.solution(), true) != phrase(signed.solution(), signed)


def test_strike_reopens_the_last_page_and_defuse_goes_back():
    bot = HqBot()
    bot.reply(["cat"])
    bot.reply(["cat", "dog", "cow", "pig"])
    assert bot.on_result(False) == ("That was a strike. Check the Animal panel again. "
                                    "Sign the 4 pictures, left to right, top row first.")
    assert bot.stage == "details" and bot.page.id == "pets_farm"
    bot.reply(["cat", "dog", "cow", "horse"])
    assert bot.on_result(True).startswith("Good work.")
    assert bot.stage == "module"
    assert bot.on_result(True) is None  # one result per instruction


def test_result_without_an_instruction_is_silent():
    bot = HqBot()
    assert bot.on_result(False) is None
    bot.reply(["cat"])
    assert bot.on_result(False) is None and bot.stage == "details"


def test_greeting():
    assert HqBot().greeting() == "HQ here. Which module do you need help with? Sign one thing you see on it."
