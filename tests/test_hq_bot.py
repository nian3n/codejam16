# Owner: Teammate 4 (Puzzles and brain)
"""The scripted bot HQ (brain/hq_bot.py): it walks the rules and asks only what it needs."""
import random

import pytest

from escape_pod.brain.hq_bot import HqBot
from escape_pod.puzzles.engine import WIDGETS, Module, load_pool
from escape_pod.puzzles.phrase import phrase

POOL = load_pool()


def answer(key: str, module) -> list[str]:
    """What a perfect agent signs for the fact `key`, read from the real module."""
    f, w = module.facts, module.widget
    items = w.items(f)
    if key.startswith("has:"):
        return ["yes"] if key[4:] in items else ["no"]
    if key == "first":
        return [items[0]]
    if key == "last":
        return [items[-1]]
    if key == "needle":
        return [f["needle"]]
    if key.startswith("state_of:"):
        return ["yes"] if any(s["label"] == key[9:] and s["state"] == "on" for s in f["switches"]) else ["no"]
    if key == "count_on":
        return [s["label"] for s in f["switches"] if s["state"] == "on"] or ["no"]
    if key == "display":
        return list(f["display"])
    if key == "items":
        return list(reversed(items))  # any order: the bot sorts them
    raise ValueError(key)


def play(bot, module, first=None) -> list[str]:
    """Round 0 with one item, then answer every question. Returns the bot's replies."""
    replies = [bot.reply([first or module.widget.items(module.facts)[0]])]
    while bot.stage == "details":
        replies.append(bot.reply(answer(bot.pending, module)))
        assert len(replies) < 12, replies
    return replies


def make(spec_id, facts):
    return Module(POOL[spec_id], facts)


@pytest.mark.parametrize("spec_id", sorted(POOL))
def test_every_puzzle_gives_the_engine_instruction(spec_id):
    spec = POOL[spec_id]
    for seed in range(60):
        module = Module(spec, WIDGETS[spec.widget].generate(spec, random.Random(seed)))
        replies = play(HqBot(), module)
        assert replies[0].startswith(f"That is the {spec.title}.")
        assert replies[-1].endswith(phrase(module.solution(), module)), (seed, replies)
        assert not any("Sign" in r for r in replies)  # the bot says "Tell me", not "Sign"


def test_most_modules_need_few_exchanges():
    lengths = []
    for spec in POOL.values():
        for seed in range(30):
            module = Module(spec, WIDGETS[spec.widget].generate(spec, random.Random(seed)))
            lengths.append(len(play(HqBot(), module)))
    assert sum(lengths) / len(lengths) <= 4, sum(lengths) / len(lengths)


def test_the_animal_panel_example():
    m = make("pets_farm", {"icons": ["cat", "hen", "duck", "pig"]})
    bot = HqBot()
    assert bot.reply(["cat"]) == "That is the Animal panel. Do you see DOG?"
    assert bot.reply(["no"]) == "Do you see COW?"
    assert bot.reply(["no"]) == "Do you see HORSE?"
    assert bot.reply(["no"]) == "Tell me the bottom-right picture."
    assert bot.reply(["pig"]) == "Press the pig." == phrase(m.solution(), m)


def test_the_round0_item_answers_a_condition():
    bot = HqBot()
    assert bot.reply(["blue"]) == "That is the Wire panel. Is there a red wire?"
    assert bot.reply(["yes"]).startswith("Cut the")
    bot = HqBot()
    assert bot.reply(["red", "blue"]).startswith("That is the Wire panel. Cut the")


def test_signing_the_item_means_yes_and_other_words_are_asked_again():
    bot = HqBot()
    bot.reply(["cat"])
    assert bot.reply(["dog"]).startswith("Press the dog")
    bot = HqBot()
    bot.reply(["cat"])
    assert bot.reply(["pig"]) == "Tell me YES or NO. Do you see DOG?"
    assert bot.reply(["yes", "no"]) == "Tell me YES or NO. Do you see DOG?"


def test_unknown_word_and_tie():
    bot = HqBot()
    assert bot.reply(["hello"]) == "I do not know that word. Tell me one thing from the module again."
    tie = bot.reply(["cat", "red"])
    assert tie.startswith(("Is it the Animal panel or the Wire panel?", "Is it the Wire panel or the Animal panel?"))
    assert bot.stage == "module"


def test_core_words_alone_do_not_open_a_page():
    bot = HqBot()
    assert bot.reply(["yes"]) == "I do not know that word. Tell me one thing from the module again."


def test_dial_needle():
    bot = HqBot()
    assert bot.reply(["car"]) == "That is the Travel dial. Tell me the picture that the needle points at."
    assert bot.reply(["see"]).startswith("That is the Sensor dial.")  # another page: module change
    bot = HqBot()
    bot.reply(["car"])
    assert bot.reply(["boat", "car"]) == "Tell me one picture. Tell me the picture that the needle points at."
    assert bot.reply(["car"]) == "Turn the dial to the boat."  # the rule: needle on car -> boat


def test_switches_state_and_count():
    bot = HqBot()
    assert bot.reply(["lamp"]) == "That is the Home power board. Is the LAMP switch on?"
    assert bot.reply(["yes"]) == "Tell me which switches are on. Tell me NO if none is on."
    for msg in (["no"], ["no", "no"], ["yes", "no"][1:]):
        b = HqBot()
        b.reply(["bed"])
        b.reply(["no"])  # no lamp
        assert b.pending == "count_on"
        assert b.reply(msg) is not None and b.pending != "count_on"


def test_module_change_in_details():
    bot = HqBot()
    bot.reply(["cat"])
    assert bot.reply(["red"]).startswith("That is the Wire panel.")
    assert bot.page.id == "colors"


def test_wrong_answer_gives_the_instruction_for_what_was_signed():
    # The module shows a dog, but the agent answers NO: the bot trusts the signs.
    true = make("pets_farm", {"icons": ["cat", "dog", "cow", "pig"]})
    bot = HqBot()
    bot.reply(["cat"])
    assert bot.reply(["no"]) == "Do you see COW?"
    assert bot.reply(["yes"]) == "Press the cow."
    assert phrase(true.solution(), true) == "Press the dog."


def test_strike_starts_the_page_again_and_defuse_goes_back():
    bot = HqBot()
    bot.reply(["cat"])
    bot.reply(["yes"])
    assert bot.on_result(False) == "That was a strike. Let us check the Animal panel again. Do you see CAT?"
    assert bot.stage == "details" and bot.page.id == "pets_farm"
    bot.reply(["yes"])
    bot.reply(["yes"])
    assert bot.on_result(True).startswith("Good work.")
    assert bot.stage == "module"
    assert bot.on_result(True) is None  # one result per instruction


def test_result_without_an_instruction_is_silent():
    bot = HqBot()
    assert bot.on_result(False) is None
    bot.reply(["cat"])
    assert bot.on_result(False) is None and bot.stage == "details"


def test_a_result_after_the_player_moved_on_keeps_the_new_page():
    for defused in (True, False):
        bot = HqBot()
        bot.reply(["cat", "dog"])  # instruction at once: press the dog
        assert bot.stage == "module"
        bot.reply(["red"])
        assert bot.on_result(defused) is None
        assert bot.page.id == "colors"


def test_greeting():
    assert HqBot().greeting() == "HQ here. Which module do you need help with? Tell me one thing you see on it."


def test_alphabet_rules_ask_for_every_picture():
    bot = HqBot()
    bot.reply(["horse"])
    assert bot.reply(["no"]) == "Do you see COW?"
    assert bot.reply(["no"]) == "Tell me the 4 pictures, in any order."
    assert bot.reply(["pig", "horse"]) == "I need 4 different pictures. You told me 2. Tell me the 4 pictures, in any order."
    assert bot.reply(["pig", "horse", "hen", "duck"]) == "Press the buttons in this order: duck, hen, horse, pig."
    bot = HqBot()
    bot.reply(["nuts"])
    assert bot.reply(["no"]) == "Tell me the picture that the needle points at."
    assert bot.reply(["nuts"]) == "Tell me the 5 pictures on the dial, in any order."
    assert bot.reply(["chocolate", "nuts", "carrot", "apple", "cereal"]) == "Turn the dial to the apple."
