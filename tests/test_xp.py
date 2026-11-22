# Owner: Teammate 1 (Game, scenes, widgets)
"""Round XP (spec 2026-11-21-xp-levels-design): the server's breakdown at the end of a round."""
import time

from web import server
from web.xp import round_xp
from test_server import _drain, _fast_bot, _solve_module, _start_solo, _talk  # noqa: F401


def test_win_parts():
    r = round_xp("intermediate", defused=4, won=True, seconds_left=81.9, signs=14)
    assert r["parts"] == [{"label": "Signs confirmed (14)", "xp": 70}, {"label": "Modules defused (4)", "xp": 40},
                          {"label": "Bomb defused", "xp": 75}, {"label": "Time left 1:22", "xp": 40}]
    assert r["signs_xp"] == 70 and r["total"] == 225


def test_loss_has_no_win_or_time():
    r = round_xp("advanced", defused=1, won=False, seconds_left=50, signs=0)
    assert r["parts"] == [{"label": "Modules defused (1)", "xp": 10}] and r["total"] == 10
    assert r["signs_xp"] == 0


def test_custom_win_counts_as_intermediate():
    assert round_xp("custom", 0, True, 0, 0)["total"] == 75


def _win(code, a, s):
    for i, m in enumerate(server.rooms[code].modules):
        s = _talk(code, a, s, m)
        _solve_module(a, i, m)
        s = _drain(a, lambda s, i=i: s["progress"]["defused"] == i + 1)
    assert s["phase"] == "escaped"
    return s


def _labels(s):
    return [p["label"] for p in s["round_xp"]["parts"]]


def test_no_round_xp_while_playing():
    code, a, s = _start_solo()
    assert "round_xp" not in s
    a.__exit__(None, None, None)


def test_round_xp_in_state_after_a_win():
    code, a, s = _start_solo()
    s = _win(code, a, s)
    xp = s["round_xp"]
    assert xp["round_id"] == s["round_id"]
    assert "Bomb defused" in _labels(s)
    assert xp["total"] == sum(p["xp"] for p in xp["parts"])
    a.__exit__(None, None, None)


def test_sign_count_survives_the_ack():
    code, a, s = _start_solo()
    gate_credits = list(s["practice_credits"])
    assert gate_credits
    a.send_json({"type": "practice_saved", "credits": gate_credits})
    s = _win(code, a, s)
    modules = len(server.rooms[code].modules)
    assert f"Signs confirmed ({len(gate_credits) + modules})" in _labels(s)
    a.__exit__(None, None, None)


def test_timeout_gives_no_win_parts():
    code, a, s = _start_solo()
    server.rooms[code].deadline = time.monotonic() - 1
    a.send_json({"type": "signs", "glosses": ["cat"]})
    s = _drain(a, lambda s: s["phase"] == "boom")
    labels = _labels(s)
    assert "Bomb defused" not in labels and not any(label.startswith("Time left") for label in labels)
    a.__exit__(None, None, None)


def test_again_clears_round_xp():
    code, a, s = _start_solo()
    s = _win(code, a, s)
    a.send_json({"type": "again"})
    assert "round_xp" not in _drain(a, lambda s: s["phase"] == "lobby")
    a.__exit__(None, None, None)


def test_two_players_each_get_round_xp():
    from test_server import _start_game
    code, a, b, sa, sb = _start_game()  # the gates are open: the handler signed the code, the agent the colors
    room = server.rooms[code]
    for i, m in enumerate(room.modules):
        a.send_json({"type": "signs", "glosses": [m.widget.items(m.facts)[0]]})
        b.send_json({"type": "say", "text": f"Module {i + 1}: do it."})
        _drain(b, lambda s, i=i: s["chat"][-1].get("text") == f"Module {i + 1}: do it.")
        _solve_module(a, i, m)
        sa = _drain(a, lambda s, i=i: s["progress"]["defused"] == i + 1)
    sb = _drain(b, lambda s: s["phase"] == "escaped")
    modules = len(room.modules)
    lock, tray = len(room.mission.code), len(room.mission.colors)
    assert f"Signs confirmed ({tray + modules})" in _labels(sa)
    assert f"Signs confirmed ({lock + modules})" in _labels(sb)
    for s in (sa, sb):
        assert "Bomb defused" in _labels(s) and f"Modules defused ({modules})" in _labels(s)
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)
