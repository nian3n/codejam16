# Owner: Teammate 4 (Puzzles and brain)
import json
import random

import pytest

from escape_pod import config
from escape_pod.manual.build import all_pages, page_markdown
from escape_pod.manual.solve import sheet_markdown, solve_module
from escape_pod.puzzles.engine import WIDGETS, Module, draw, load_pool
from escape_pod.puzzles.models import Action
from escape_pod.puzzles.phrase import phrase, word

POOL = load_pool()
ICONS = json.loads(config.ICONS_FILE.read_text(encoding="utf-8"))


def test_pool_has_20_unique_topics():
    assert len(POOL) == 20  # alphabet (letters) was replaced by senses
    assert len({s.topic for s in POOL.values()}) == 20


def test_no_gloss_in_two_pools():
    seen = {}
    for s in POOL.values():
        for g in s.pool:
            assert g not in seen, f"{g} is in {seen.get(g)} and {s.id}"
            seen[g] = s.id


def test_every_picture_gloss_has_an_icon():
    for s in POOL.values():
        if s.widget in ("icons", "dial", "switches", "big_button"):
            missing = [g for g in s.pool if g not in ICONS]
            assert not missing, f"{s.id} has no icon for {missing}"


@pytest.mark.parametrize("pid", sorted(POOL))
def test_rules_use_only_derived_keys(pid):
    spec = POOL[pid]
    known = WIDGETS[spec.widget].known_keys(spec)
    for r in spec.rules:
        for key, _, _ in r.when or []:
            assert key in known, f"{pid}: rule uses unknown key {key}"


@pytest.mark.parametrize("pid", sorted(POOL))
def test_500_seeds_give_a_valid_target(pid):
    spec = POOL[pid]
    w = WIDGETS[spec.widget]
    for seed in range(500):
        m = Module(spec, w.generate(spec, random.Random(seed)))
        sol = m.solution()
        t = sol.target
        items = w.items(m.facts)
        # The resolved target is always something that is on the module.
        if sol.verb == "cut":
            assert t["color"] in items
        elif sol.verb == "type":
            assert sorted(t["keys"]) == sorted(items)
        elif sol.verb == "press":
            assert t["icon"] in items
        elif sol.verb == "press_all":
            assert sorted(t["icons"]) == sorted(items) and t["icons"] in (sorted(items), sorted(items, reverse=True))
        elif sol.verb == "turn":
            assert t["to"] in items
        elif sol.verb == "set":
            assert t["switch"] in items and t["state"] in ("on", "off")
            now = next(s["state"] for s in m.facts["switches"] if s["label"] == t["switch"])
            assert t["state"] != now, "a switch action must change the switch"
        elif sol.verb == "hold":
            assert t["release_on"] in items
        assert m.check(sol)
        assert phrase(sol, m).endswith(".")


def test_every_rule_can_fire():
    """No dead rules: across many seeds, each rule of each puzzle fires at least once."""
    for spec in POOL.values():
        w = WIDGETS[spec.widget]
        fired = {Module(spec, w.generate(spec, random.Random(s))).fired_rule() for s in range(3000)}
        assert fired == set(range(len(spec.rules))), f"{spec.id}: rules {set(range(len(spec.rules))) - fired} never fire"


def test_known_answers():
    pets = POOL["pets_farm"]
    m = Module(pets, {"icons": ["cat", "pig", "dog", "hen"]})
    assert phrase(m.solution(), m) == "Press the dog."
    m = Module(pets, {"icons": ["duck", "pig", "horse", "hen"]})
    assert phrase(m.solution(), m) == "Press the buttons in this order: duck, hen, horse, pig."  # horse rule
    m = Module(pets, {"icons": ["duck", "pig", "donkey", "hen"]})
    assert phrase(m.solution(), m) == "Press the hen."
    nums = POOL["numbers"]
    m = Module(nums, {"display": ["7", "4", "2"]})
    assert phrase(m.solution(), m) == "Type 2, 4, 7."
    m = Module(nums, {"display": ["1", "4", "2"]})
    assert phrase(m.solution(), m) == "Type 1, 4, 2."
    wires = POOL["colors"]
    m = Module(wires, {"colors": ["green", "black", "brown", "orange"]})
    assert phrase(m.solution(), m) == "Cut the orange wire."  # no yellow -> last wire


@pytest.mark.parametrize("level", list(config.LEVELS))
def test_draw_rules(level):
    lv = config.LEVELS[level]
    for seed in range(200):
        mods = draw(random.Random(seed), lv)
        assert len(mods) == lv.modules
        assert len({m.spec.id for m in mods}) == lv.modules
        assert len({m.spec.widget for m in mods}) >= min(3, lv.modules)
        assert sum(m.spec.hard for m in mods) <= (1 if lv.allow_hard else 0)


def test_draw_is_seeded():
    lv = config.LEVELS["intermediate"]
    a = [(m.spec.id, m.facts) for m in draw(random.Random(42), lv)]
    b = [(m.spec.id, m.facts) for m in draw(random.Random(42), lv)]
    assert a == b


def test_manual_pages_build():
    pages = all_pages()
    assert len(pages) == 20
    for p in pages:
        text = page_markdown(p)
        assert p["title"] in text and "Otherwise" in text


def test_answer_key_matches_engine():
    mods = draw(random.Random(7), config.LEVELS["advanced"])
    for m in mods:
        s = solve_module(m)
        assert s["instruction"] == phrase(m.solution(), m)
        assert s["rules"][s["fired"] - 1]["matched"]
    assert "Do this:" in sheet_markdown(mods)


def test_verb_puzzles_say_picture_and_noun_puzzles_do_not():
    from escape_pod.puzzles.models import Action
    from escape_pod.puzzles.phrase import phrase, word
    assert phrase(Action("press", {"icon": "dance"}), spec=POOL["actions"]) == "Press the dance picture."
    assert phrase(Action("turn", {"to": "listen"}), spec=POOL["senses"]) == "Turn the dial to the listen picture."
    assert phrase(Action("press", {"icon": "cow"}), spec=POOL["pets_farm"]) == "Press the cow."


def test_order_rules():
    """Press all in alphabetical order (icons), and the first or last picture in the alphabet (dials)."""
    m = Module(POOL["pets_farm"], {"icons": ["pig", "horse", "duck", "hen"]})
    assert m.solution() == Action("press_all", {"icons": ["duck", "hen", "horse", "pig"]})
    assert phrase(m.solution(), m) == "Press the buttons in this order: duck, hen, horse, pig."
    m = Module(POOL["clothes"], {"icons": ["hat", "shoe", "jeans", "zipper"]})
    assert m.solution().target["icons"] == ["zipper", "shoe", "jeans", "hat"]
    m = Module(POOL["food"], {"options": ["pizza", "nuts", "carrot", "apple", "cereal"], "needle": "pizza"})
    assert phrase(m.solution(), m) == "Turn the dial to the apple."
    m = Module(POOL["weather_sky"], {"options": ["moon", "sun", "cloud", "rain", "snow"], "needle": "cloud"})
    assert phrase(m.solution(), m) == "Turn the dial to the sun."
    spec = POOL["pets_farm"]
    assert phrase(spec.rules[2].action(), spec=spec) == "Press all the buttons in alphabetical order (A to Z)."
    spec = POOL["clothes"]
    assert phrase(spec.rules[2].action(), spec=spec) == "Press all the buttons in reverse alphabetical order (Z to A)."
    spec = POOL["food"]
    assert phrase(spec.rules[2].action(), spec=spec) == "Turn the dial to the picture that comes first in the alphabet."


def test_alphabet_order_of_glosses_matches_the_english_words():
    # The engine sorts glosses; players sort the English words. They must agree in every pool.
    for spec in POOL.values():
        assert sorted(spec.pool) == sorted(spec.pool, key=lambda g: word(g, spec).lower()), spec.id
