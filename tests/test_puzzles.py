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
        if s.widget in ("icons", "dial", "switches", "big_button", "sorter"):
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
            cut = t["colors"] if "colors" in t else [t["color"]]
            assert cut and set(cut) <= set(items) and len(set(cut)) == len(cut)
        elif sol.verb == "type":
            assert len(t["keys"]) == len(items) and set(t["keys"]) <= set(spec.pool)
        elif sol.verb == "press":
            pressed = t["icons"] if "icons" in t else [t["icon"]]
            assert pressed and set(pressed) <= set(items) and len(set(pressed)) == len(pressed)
        elif sol.verb == "press_all":
            assert sorted(t["icons"]) == sorted(items) and t["icons"] in (sorted(items), sorted(items, reverse=True))
        elif sol.verb == "turn":
            assert t["to"] in items
        elif sol.verb == "set":
            flips = t["flips"] if "flips" in t else {t["switch"]: t["state"]}
            assert flips, "a switch action must change at least one switch"
            for label, state in flips.items():
                now = next(s["state"] for s in m.facts["switches"] if s["label"] == label)
                assert state in ("on", "off") and state != now, "a switch action must change the switch"
        elif sol.verb == "hold":
            assert t["release_on"] in items
        assert m.check(sol)
        assert phrase(sol, m).endswith(".")
        # Played click by click, the steps of the solution defuse the module.
        steps, _ = w.steps(sol)
        results = [m.apply(a) for a in steps]
        assert results == ["step"] * (len(steps) - 1) + ["defused"] and m.defused


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
    m = Module(wires, {"colors": ["brown", "black", "green", "orange"]})
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
    m = Module(POOL["senses"], {"options": ["think", "smile", "hear", "look"], "needle": "look"})
    assert phrase(m.solution(), m) == "Turn the dial to the hear picture."
    m = Module(POOL["weather_sky"], {"options": ["moon", "sun", "cloud", "rain", "snow"], "needle": "cloud"})
    assert phrase(m.solution(), m) == "Turn the dial to the sun."
    spec = POOL["pets_farm"]
    assert phrase(spec.rules[2].action(), spec=spec) == "Press all the buttons in alphabetical order (A to Z)."
    spec = POOL["clothes"]
    assert phrase(spec.rules[2].action(), spec=spec) == "Press all the buttons in reverse alphabetical order (Z to A)."
    spec = POOL["senses"]
    assert phrase(spec.rules[3].action(), spec=spec) == "Turn the dial to the picture that comes first in the alphabet."


def test_alphabet_order_of_glosses_matches_the_english_words():
    # The engine sorts glosses; players sort the English words. They must agree in every pool.
    for spec in POOL.values():
        assert sorted(spec.pool) == sorted(spec.pool, key=lambda g: word(g, spec).lower()), spec.id


def _mod(pid, facts):
    return Module(POOL[pid], facts)


def test_wires_in_order_wrong_order_is_a_strike_and_keeps_progress():
    m = _mod("colors", {"colors": ["green", "white", "black", "orange"]})
    assert m.solution().target["colors"] == ["white", "black"]
    assert phrase(m.solution(), m) == "Cut the white wire, then the black wire."
    assert m.apply(Action("cut", {"color": "black"})) == "strike"
    assert m.apply(Action("cut", {"color": "white"})) == "step" and not m.defused
    assert m.apply(Action("cut", {"color": "white"})) == "strike"  # already cut
    assert m.apply(Action("cut", {"color": "black"})) == "defused"


def test_cut_every_wire_from_the_bottom():
    m = _mod("colors", {"colors": ["green", "brown", "yellow", "orange"]})
    assert m.solution().target["colors"] == ["orange", "yellow", "brown", "green"]
    assert phrase(m.solution(), m) == "Cut every wire, from the bottom to the top."
    assert phrase(m.spec.rules[m.fired_rule()].action(), spec=m.spec) == phrase(m.solution(), m)


def test_icons_in_order():
    m = _mod("wild_animals", {"icons": ["owl", "giraffe", "wolf", "elephant"]})
    assert phrase(m.solution(), m) == "Press the elephant, then the giraffe."
    assert m.apply(Action("press", {"icon": "elephant"})) == "step"
    assert m.apply(Action("press", {"icon": "giraffe"})) == "defused"


def test_switch_patterns_take_any_order():
    sw = lambda *on: [{"label": g, "state": "on" if g in on else "off"} for g in ("bed", "chair", "lamp", "tv")]
    m = _mod("home_things", {"switches": sw("bed", "chair", "lamp", "tv")})
    assert phrase(m.solution(), m) == "Turn every switch off."
    assert m.solution().target["flips"] == {"bed": "off", "chair": "off", "lamp": "off", "tv": "off"}
    assert m.apply(Action("set", {"switch": "tv", "state": "off"})) == "step"
    assert m.apply(Action("set", {"switch": "bed", "state": "on"})) == "strike"
    for g in ("lamp", "chair"):
        assert m.apply(Action("set", {"switch": g, "state": "off"})) == "step"
    assert m.apply(Action("set", {"switch": "bed", "state": "off"})) == "defused"


def test_opposites_flip_every_switch():
    sw = [{"label": "wet", "state": "on"}, {"label": "dry", "state": "off"},
          {"label": "loud", "state": "off"}, {"label": "open", "state": "on"}]
    m = _mod("opposites", {"switches": sw})
    assert phrase(m.solution(), m) == "Flip every switch."
    assert m.solution().target["flips"] == {"wet": "off", "dry": "on", "loud": "on", "open": "off"}


def test_keypad_plus_one():
    m = _mod("numbers", {"display": ["5", "9", "2"]})
    assert m.solution() == Action("type", {"keys": ["6", "0", "3"]})
    assert phrase(m.spec.rules[m.fired_rule()].action(), spec=m.spec) == (
        "Add 1 to each number on the display and type the result (9 becomes 0).")


def test_a_one_click_answer_is_one_step():
    m = _mod("pets_farm", {"icons": ["cat", "dog", "pig", "duck"]})
    assert m.apply(Action("press", {"icon": "cow"})) == "strike" and not m.defused
    assert m.apply(m.solution()) == "defused" and m.defused


def test_the_whole_answer_at_once_also_defuses():
    m = _mod("colors", {"colors": ["green", "white", "black", "orange"]})
    assert m.apply(m.solution()) == "defused" and m.defused
    m = _mod("colors", {"colors": ["green", "white", "black", "orange"]})
    m.apply(Action("cut", {"color": "white"}))
    assert m.apply(m.solution()) == "defused"


@pytest.mark.parametrize("n", range(config.CUSTOM_MODULES[0], config.CUSTOM_MODULES[1] + 1))
def test_custom_levels_draw_1_to_5_modules(n):
    lv = config.custom_level(n, 120)
    assert lv.name == "custom" and lv.timer_s == 120 and not lv.allow_hard
    for seed in range(50):
        mods = draw(random.Random(seed), lv)
        assert len(mods) == n and len({m.spec.id for m in mods}) == n
        assert len({m.spec.widget for m in mods}) >= min(3, n)


# ---------------------------------------------------------------------------
# Sorter: drag each picture into the left or the right box (food: healthy or treats)
# ---------------------------------------------------------------------------
def _food(items):
    return Module(POOL["food"], {"items": items})


def test_the_sorter_shows_both_groups_every_time():
    spec = POOL["food"]
    groups = [set(g["items"]) for g in spec.setup["groups"]]
    for seed in range(500):
        items = WIDGETS["sorter"].generate(spec, random.Random(seed))["items"]
        assert len(items) == 4 == len(set(items))
        assert all(g & set(items) for g in groups)


def test_the_sorter_resolves_each_group_to_a_box():
    m = _food(["pizza", "apple", "carrot", "chocolate"])  # pizza: the treats go left
    assert m.solution() == Action("sort", {"left": ["pizza", "chocolate"], "right": ["apple", "carrot"]})
    assert phrase(m.solution(), m) == ("Put the pizza and the chocolate in the left box. "
                                       "Put the apple and the carrot in the right box.")


def test_the_sorter_takes_one_drop_at_a_time_in_any_order():
    m = _food(["pizza", "apple", "carrot", "chocolate"])

    def drop(g, box):
        return m.apply(Action("sort", {"item": g, "box": box}))

    assert drop("carrot", "right") == "step"
    assert drop("apple", "left") == "strike"      # wrong box: a strike, the progress stays
    assert drop("chocolate", "left") == "step"
    assert drop("apple", "right") == "step"
    assert drop("pizza", "left") == "defused"


def test_the_sorter_manual_lists_the_groups():
    p = next(p for p in all_pages() if p["id"] == "food")
    assert "Healthy food: apple, carrot, cereal, nuts." in p["reading_order"]
    assert "Treats: pizza, french fries, ice cream, chocolate." in p["reading_order"]
    assert p["rules"][0] == {"if": "pizza is shown",
                             "then": "Put the treats in the left box and the healthy food in the right box."}
    assert p["rules"][1]["if"] == "the first picture is a healthy food"
