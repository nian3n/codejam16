# Owner: Teammate 1 (Game, scenes, widgets)
"""The case lock and the wire tray rules (spec 2026-11-21-two-player-gates-design)."""
import random

import pytest

from puzzles.engine import load_pool
from web.mission import Mission

COLORS = load_pool()["colors"].pool


def _tray(wheels=True, seed=3):
    m = Mission.draw(random.Random(seed), wheels=wheels)
    if wheels:
        assert m.try_code(m.code) == "open"
    else:
        m.confirm(list(m.code))
    assert m.stage == "wire_tray"
    return m


def test_draw_ranks_all_colors():
    m = Mission.draw(random.Random(1), wheels=True)
    assert sorted(m.rank) == sorted(COLORS)
    assert m.wire_order == sorted(range(4), key=lambda i: m.rank.index(m.colors[i]))
    assert m.cut_colors == [m.colors[i] for i in m.wire_order]
    assert "2" not in m.code


def test_try_code_opens_or_strikes():
    m = Mission.draw(random.Random(1), wheels=True)
    wrong = "".join("1" if d != "1" else "3" for d in m.code)
    assert m.try_code(wrong) == "strike" and m.stage == "case_lock"
    assert m.try_code(m.code) == "open"
    assert m.stage == "wire_tray" and m.lock_confirmed == 3


@pytest.mark.parametrize("bad", ["43", "abc", "4345", 434, None, ["4", "3", "4"]])
def test_bad_code_is_a_retry(bad):
    m = Mission.draw(random.Random(1), wheels=True)
    revision = m.revision
    assert m.try_code(bad) == "retry" and m.stage == "case_lock"
    assert m.revision == revision + 1  # the client gets a fresh revision to answer


def test_solo_lock_takes_signs_and_no_code():
    m = Mission.draw(random.Random(1), wheels=False)
    assert m.try_code(m.code) == "retry" and m.stage == "case_lock"
    assert m.confirm(list(m.code)) == list(m.code) and m.stage == "wire_tray"


def test_wheels_lock_passes_digits_unchecked():
    # Two players: the agent's digits go to the handler as signed; only the wheels open the case.
    m = Mission.draw(random.Random(1), wheels=True)
    wrong = ["1" if d != "1" else "3" for d in m.code]
    assert m.confirm(wrong) == wrong and m.stage == "case_lock" and m.lock_confirmed == 0
    assert m.confirm(["red"]) == [] and m.confirm(list("0134")) == []
    assert m.try_code(m.code) == "open" and m.stage == "wire_tray"


def test_tray_signs_collect_colors():
    m = _tray()
    off_tray = next(c for c in COLORS if c not in m.colors)
    assert m.confirm([m.colors[2], off_tray, m.colors[2]]) == [m.colors[2], off_tray, m.colors[2]]
    assert m.signed_colors == [m.colors[2]] and not m.tray_ready
    assert m.confirm(["cat"]) == []  # not a color: nothing to share
    m.confirm(m.colors)
    assert sorted(m.signed_colors) == sorted(m.colors) and m.tray_ready


def test_cut_waits_for_all_four_colors():
    m = _tray()
    m.confirm(m.colors[:3])
    assert m.cut(m.wire_order[0]) == "retry" and not m.cuts
    m.confirm(m.colors[3:])
    wrong = m.wire_order[1]
    assert m.cut(wrong) == "strike" and not m.cuts
    for index in m.wire_order:
        assert m.cut(index) == "cut"
    assert m.stage == "modules"


def test_views_split_the_code():
    m = Mission.draw(random.Random(1), wheels=True)
    agent, handler = m.view("defuser"), m.view("expert")
    assert agent["case_code"] == m.code and "lock_wheels" not in agent
    assert handler["lock_wheels"] is True and "case_code" not in handler
    solo = Mission.draw(random.Random(1), wheels=False)
    assert solo.view("defuser")["case_code"] == solo.code and "lock_wheels" not in solo.view("defuser")
    m.try_code(m.code)
    m.confirm(m.colors[:2])
    agent, handler = m.view("defuser"), m.view("expert")
    assert agent["wires"] == m.colors and agent["signed_colors"] == m.colors[:2]
    assert handler["wire_rank"] == m.rank and handler["colors_received"] == 2
    assert "signed_colors" not in handler  # the handler reads the colors on the video
    assert "wires" not in handler and "cuts" not in handler and "case_code" not in handler
