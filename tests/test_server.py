# Owner: Teammate 1 (Game, scenes, widgets)
import time

import pytest
from fastapi.testclient import TestClient

import random

from escape_pod import config
from escape_pod.puzzles.engine import WIDGETS, Module, load_pool
from escape_pod.web import server
from escape_pod.web.mission import POSITIONS

client = TestClient(server.app)


def _last_state(ws):
    while True:
        m = ws.receive_json()
        if m["type"] == "state":
            return m


def _drain(ws, until):
    """Read states until one satisfies `until` (the server may send several)."""
    for _ in range(20):
        s = _last_state(ws)
        if until(s):
            return s
    raise AssertionError("expected state never arrived")


def _join(code, name, pid=None):
    ws = client.websocket_connect(f"/ws/{code}")
    ws.__enter__()
    ws.send_json({"type": "hello", "name": name, "pid": pid})
    welcome = ws.receive_json()
    assert welcome["type"] == "welcome"
    if pid:
        assert welcome["pid"] == pid
    return ws


def _gate_message(state, kind, **payload):
    return {"type": kind, "round_id": state["round_id"],
            "mission_revision": state["mission"]["revision"], **payload}


def _gate_action(ws, state, kind, **payload):
    ws.send_json(_gate_message(state, kind, **payload))
    return _drain(ws, lambda s: s["mission"]["revision"] > state["mission"]["revision"])


def _open_case(ws, state):
    assert state["armed"]
    return _gate_action(ws, state, "signs", glosses=list(state["mission"]["case_code"]))


def _open_gates(ws, state):
    state = _open_case(ws, state)
    order = server.rooms[state["code"]].mission.wire_order
    for index in order:
        state = _gate_action(ws, state, "signs", glosses=[state["mission"]["wires"][index]])
    return state


def _solve_module(ws, index, module):
    for step in module.widget.steps(module.solution())[0]:
        ws.send_json({"type": "act", "module": index, "action": step.to_json()})


def _arm(ws):
    """The agent's browser is ready: with COUNTDOWN_S = 0 (the test fixture) the clock
    starts at once, and the mission gates open."""
    ws.send_json({"type": "ready"})
    return _drain(ws, lambda s: s["armed"])


def _start_game(level="intermediate", *, open_gates=True, arm=True):
    code = client.post("/api/rooms").json()["code"]
    a = _join(code, "Ana")
    _last_state(a)
    b = _join(code, "Ben")
    a.send_json({"type": "role", "role": "defuser"})
    b.send_json({"type": "role", "role": "expert"})
    b.send_json({"type": "level", "level": level})
    _drain(b, lambda s: s["can_start"] and s["level"] == level)
    b.send_json({"type": "start"})
    sa = _drain(a, lambda s: s["phase"] == "playing")
    sb = _drain(b, lambda s: s["phase"] == "playing")
    if arm:
        sa = _arm(a)
        sb = _drain(b, lambda s: s["armed"])
    if open_gates:
        sa = _open_gates(a, sa)
        sb = _drain(b, lambda s: s["mission"]["stage"] == "modules")
    return code, a, b, sa, sb


def test_manual_and_icons_endpoints():
    assert len(client.get("/api/manual").json()) == 19
    assert "cow" in client.get("/api/icons").json()


def test_unknown_room_is_an_error():
    with client.websocket_connect("/ws/ZZZZ") as ws:
        assert ws.receive_json()["type"] == "error"


def test_third_player_is_refused():
    code = client.post("/api/rooms").json()["code"]
    a, b = _join(code, "A"), _join(code, "B")
    with client.websocket_connect(f"/ws/{code}") as c:
        c.send_json({"type": "hello", "name": "C"})
        assert c.receive_json()["type"] == "error"
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_cannot_start_without_both_roles():
    code = client.post("/api/rooms").json()["code"]
    a = _join(code, "A")
    a.send_json({"type": "role", "role": "defuser"})
    s = _drain(a, lambda s: s["me"]["role"] == "defuser")
    assert not s["can_start"]
    a.send_json({"type": "start"})
    a.send_json({"type": "level", "level": "beginner"})  # forces one more state
    s = _drain(a, lambda s: s["level"] == "beginner")
    assert s["phase"] == "lobby"
    a.__exit__(None, None, None)


def test_expert_never_sees_the_bomb():
    _, a, b, sa, sb = _start_game()
    assert "bomb" in sa and len(sa["bomb"]) == 4
    assert "bomb" not in sb
    assert sorted(sa["case_tray"]["cuts"]) == list(range(4))
    assert "case_tray" not in sb
    assert sb["progress"] == {"total": 4, "defused": 0}
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_full_game_signs_reply_strike_and_escape():
    code, a, b, sa, _ = _start_game()
    mods = server.rooms[code].modules
    # Defuser signs, expert sees the signs and replies.
    a.send_json({"type": "signs", "glosses": ["CAT", " dog "]})
    sb = _drain(b, lambda s: s["chat"][-1].get("glosses") == ["cat", "dog"])
    assert sb["chat"][-1]["kind"] == "signs"
    b.send_json({"type": "say", "text": "Press the dog."})
    _drain(a, lambda s: any(m["kind"] == "say" for m in s["chat"]))
    # The expert cannot act on the bomb.
    b.send_json({"type": "act", "module": 0, "action": mods[0].solution().to_json()})
    b.send_json({"type": "say", "text": "ping"})
    sb = _drain(b, lambda s: s["chat"][-1].get("text") == "ping")
    assert sb["progress"]["defused"] == 0
    # A wrong action is a strike.
    a.send_json({"type": "act", "module": 0, "action": {"verb": "nope", "target": {}}})
    sa = _drain(a, lambda s: s["strikes"] == 1)
    # Correct actions defuse every module -> escaped.
    for i, m in enumerate(mods):
        _solve_module(a, i, m)
    sa = _drain(a, lambda s: s["phase"] == "escaped")
    assert sa["progress"]["defused"] == 4
    assert sa["chat"][-1]["text"] == "All modules defused. Device neutralized."
    sb = _drain(b, lambda s: s["phase"] == "escaped")
    assert "bomb" in sb  # debrief: both see the bomb at the end
    assert sb["case_tray"] == sa["case_tray"]
    # Play again -> back to the lobby with the same roles.
    a.send_json({"type": "again"})
    sa = _drain(a, lambda s: s["phase"] == "lobby")
    assert sa["can_start"]
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_three_strikes_is_boom():
    _, a, b, _, _ = _start_game()
    for _ in range(3):
        a.send_json({"type": "act", "module": 0, "action": {"verb": "cut", "target": {"color": "nothing"}}})
    s = _drain(a, lambda s: s["phase"] == "boom")
    assert s["strikes"] == 3
    assert s["chat"][-1]["text"] == "Three strikes. Detonation!"
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_rejoin_with_pid_keeps_the_seat():
    code = client.post("/api/rooms").json()["code"]
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "hello", "name": "A"})
        pid = ws.receive_json()["pid"]
        ws.send_json({"type": "role", "role": "expert"})
        _drain(ws, lambda s: s["me"]["role"] == "expert")
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "hello", "name": "A", "pid": pid})
        assert ws.receive_json()["pid"] == pid
        s = _last_state(ws)
        assert s["me"]["role"] == "expert" and len(s["players"]) == 1


def test_practice_credit_follows_the_exchange_and_survives_a_reconnect():
    with client:
        code, agent, hq, sa, sh = _start_game()
        room = server.rooms[code]
        round_id = sa["round_id"]
        credit = f"{round_id}:0"
        module = room.modules[0]
        wrong = {"type": "act", "round_id": round_id, "module": 0, "action": {"verb": "wrong", "target": {}}}
        hq_online = True
        try:
            assert len(sa["practice_credits"]) == 7 and not sh["practice_credits"]
            agent.send_json({"type": "practice_saved", "credits": sa["practice_credits"]})
            agent.send_json({"type": "signs", "glosses": module.widget.items(module.facts)})
            _drain(hq, lambda s: s["chat"][-1]["kind"] == "signs" and "mission_stage" not in s["chat"][-1])
            hq.send_json({"type": "say", "text": "Try the matching control."})
            _drain(agent, lambda s: s["chat"][-1]["kind"] == "say")
            agent.send_json(wrong)
            assert _drain(agent, lambda s: s["strikes"] == 1)["practice_credits"] == []

            _solve_module(agent, 1, room.modules[1])
            assert _drain(agent, lambda s: s["progress"]["defused"] == 1)["practice_credits"] == []

            hq.__exit__(None, None, None)
            hq_online = False
            _drain(agent, lambda s: not s["players"][1]["online"])
            _solve_module(agent, 0, module)
            _solve_module(agent, 0, module)
            assert _drain(agent, lambda s: s["progress"]["defused"] == 2)["practice_credits"] == [credit]

            with client.websocket_connect(f"/ws/{code}") as returning_hq:
                returning_hq.send_json({"type": "hello", "name": "Ben", "pid": sh["me"]["pid"]})
                assert returning_hq.receive_json()["pid"] == sh["me"]["pid"]
                assert _last_state(returning_hq)["practice_credits"] == [credit]
                returning_hq.send_json({"type": "practice_saved", "credits": [credit, credit]})
                returning_hq.send_json({"type": "say", "text": "Back online."})
                assert _drain(returning_hq, lambda s: s["chat"][-1].get("text") == "Back online.")["practice_credits"] == []

                room.deadline = time.monotonic()
                assert _drain(agent, lambda s: s["phase"] == "boom")["practice_credits"] == [credit]
                agent.send_json({"type": "again"})
                _drain(agent, lambda s: s["phase"] == "lobby")
                agent.send_json({"type": "start"})
                new = _drain(agent, lambda s: s["phase"] == "playing")
                assert new["round_id"] != round_id and new["practice_credits"] == [credit]
                new = _open_gates(agent, _arm(agent))
                agent.send_json(wrong)  # Ignore even a strike from the last round.
                agent.send_json({"type": "signs", "glosses": ["hello"]})
                check = _drain(agent, lambda s: s["chat"][-1].get("glosses") == ["hello"])
                assert check["progress"]["defused"] == check["strikes"] == 0
        finally:
            if hq_online:
                hq.__exit__(None, None, None)
            agent.__exit__(None, None, None)


def test_answer_key_needs_debug():
    code, a, b, _, _ = _start_game()
    assert client.get(f"/api/rooms/{code}/answer-key").status_code == 403
    server.app.state.debug = True
    try:
        r = client.get(f"/api/rooms/{code}/answer-key")
        assert r.status_code == 200 and "Do this:" in r.text
    finally:
        server.app.state.debug = False
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def _next_of(ws, kind):
    for _ in range(20):
        m = ws.receive_json()
        if m["type"] == kind:
            return m
    raise AssertionError(f"no {kind} message")


def test_rtc_relay_goes_only_to_the_other_player():
    with client:
        code = client.post("/api/rooms").json()["code"]
        a, b = _join(code, "A"), _join(code, "B")
        sa = _drain(a, lambda s: len(s["players"]) == 2)
        sb = _drain(b, lambda s: len(s["players"]) == 2)
        # Exactly one polite peer, and each player knows which entry is them.
        assert sa["me"]["polite"] != sb["me"]["polite"]
        assert [p["you"] for p in sa["players"]].count(True) == 1
        assert "ice_servers" not in sa  # served by /api/ice now
        offer = {"sid": "s1", "description": {"type": "offer", "sdp": "v=0..."}}
        a.send_json({"type": "rtc", "data": offer})
        assert _next_of(b, "rtc")["data"] == offer
        # Too large or not an object: dropped. A's next message proves nothing came back to A.
        a.send_json({"type": "rtc", "data": {"sid": "s1", "junk": "x" * 70_000}})
        a.send_json({"type": "rtc", "data": "not a dict"})
        b.send_json({"type": "rtc", "data": {"sid": "s2", "candidate": {"candidate": "c"}}})
        assert _next_of(a, "rtc")["data"]["sid"] == "s2"
        a.send_json({"type": "level", "level": "advanced"})
        m = b.receive_json()
        assert m["type"] == "state", "the oversized rtc message must not reach B"
        a.__exit__(None, None, None)
        b.__exit__(None, None, None)


def test_healthz():
    assert client.get("/healthz").json()["ok"] is True


@pytest.fixture(autouse=True)
def _no_fixed_turn_login(monkeypatch):
    # etc/.env may hold a real fixed TURN login (config.py loads it at import). The ICE
    # tests expect none unless they set one.
    for name in ("TURN_USERNAME", "TURN_CREDENTIAL", "TURN_URLS"):
        monkeypatch.delenv(name, raising=False)


def test_ice_without_metered_is_stun_only(monkeypatch):
    monkeypatch.delenv("METERED_APP", raising=False)
    monkeypatch.delenv("METERED_API_KEY", raising=False)
    assert client.get("/api/ice").json() == server.config.ICE_SERVERS


def test_ice_with_metered_hides_the_key(monkeypatch):
    from escape_pod.web import ice

    turn = [{"urls": "stun:stun.relay.metered.ca:80"},
            {"urls": "turn:global.relay.metered.ca:80", "username": "u", "credential": "c"}]
    calls = []
    monkeypatch.setenv("METERED_APP", "myapp")
    monkeypatch.setenv("METERED_API_KEY", "secret-key")
    monkeypatch.setattr(ice, "_cache", None)
    monkeypatch.setattr(ice, "_fetch_metered", lambda app, key: calls.append((app, key)) or turn)
    r = client.get("/api/ice")
    assert r.json() == turn and "secret-key" not in r.text
    client.get("/api/ice")
    assert calls == [("myapp", "secret-key")]  # cached: Metered is asked once


def test_ice_falls_back_when_metered_fails(monkeypatch):
    from escape_pod.web import ice

    def boom(app, key):
        raise OSError("network down")

    monkeypatch.setenv("METERED_APP", "myapp")
    monkeypatch.setenv("METERED_API_KEY", "k")
    monkeypatch.setattr(ice, "_cache", None)
    monkeypatch.setattr(ice, "_fetch_metered", boom)
    assert client.get("/api/ice").json() == server.config.ICE_SERVERS


def test_idle_rooms_are_pruned_but_live_ones_stay():
    old = client.post("/api/rooms").json()["code"]
    live = client.post("/api/rooms").json()["code"]
    ws = _join(live, "A")
    later = server.time.monotonic() + server.ROOM_IDLE_S + 1
    server.prune_rooms(now=later)
    assert old not in server.rooms and live in server.rooms
    ws.__exit__(None, None, None)


def test_ice_with_a_fixed_turn_login(monkeypatch):
    for k in ("METERED_APP", "METERED_API_KEY", "TURN_URLS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("TURN_USERNAME", "user1")
    monkeypatch.setenv("TURN_CREDENTIAL", "pass1")
    servers = client.get("/api/ice").json()
    turn = servers[-1]
    assert servers[:-1] == server.config.ICE_SERVERS
    assert turn["username"] == "user1" and turn["credential"] == "pass1"
    assert turn["urls"] == server.config.METERED_TURN_URLS
    monkeypatch.setenv("TURN_URLS", "turn:a.example:3478, turns:a.example:5349")
    assert client.get("/api/ice").json()[-1]["urls"] == ["turn:a.example:3478", "turns:a.example:5349"]


def test_exit_ends_the_game_for_both_and_keeps_roles():
    code, a, b, sa, sb = _start_game()
    b.send_json({"type": "exit"})
    for ws in (a, b):
        s = _drain(ws, lambda s: s["phase"] == "lobby")
        assert "bomb" not in s and s["chat"][-1]["text"] == "Ben ended the game."
    assert server.rooms[code].timer_task is None
    assert {p.role for p in server.rooms[code].players.values()} == {"defuser", "expert"}
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_exit_is_ignored_outside_a_game():
    code = client.post("/api/rooms").json()["code"]
    a = _join(code, "A")
    _last_state(a)
    a.send_json({"type": "exit"})
    a.send_json({"type": "level", "level": "advanced"})
    assert _last_state(a)["level"] == "advanced"  # the exit caused no state message
    a.__exit__(None, None, None)


def test_leave_in_the_lobby_frees_the_seat_and_the_role():
    code = client.post("/api/rooms").json()["code"]
    a, b = _join(code, "Ana"), _join(code, "Ben")
    b.send_json({"type": "role", "role": "expert"})
    _drain(a, lambda s: any(p["role"] == "expert" for p in s["players"]))
    b.send_json({"type": "leave"})
    s = _drain(a, lambda s: len(s["players"]) == 1)
    assert s["chat"][-1]["text"] == "Ben left the room."
    c = _join(code, "Cy")  # the seat is free again, and so is the expert role
    c.send_json({"type": "role", "role": "expert"})
    s = _drain(a, lambda s: any(p["name"] == "Cy" and p["role"] == "expert" for p in s["players"]))
    b.__exit__(None, None, None)
    a.__exit__(None, None, None)
    c.__exit__(None, None, None)


def test_leave_during_a_game_ends_it_and_last_one_out_deletes_the_room():
    code, a, b, sa, sb = _start_game()
    a.send_json({"type": "leave"})
    a.send_json({"type": "role", "role": "expert"})  # ignored: Ana is gone
    s = _drain(b, lambda s: s["phase"] == "lobby")
    assert [p["name"] for p in s["players"]] == ["Ben"]
    assert s["chat"][-1]["text"] == "Ana left the room. The game ended."
    b.send_json({"type": "leave"})
    b.send_json({"type": "level", "level": "beginner"})
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)
    assert code not in server.rooms


# ---------------------------------------------------------------------------
# Solo rooms: one field agent, the scripted bot in the HQ seat
# ---------------------------------------------------------------------------
from escape_pod.brain.hq_bot import BOT_NAME, HqBot  # noqa: E402
from test_hq_bot import answer  # noqa: E402


@pytest.fixture(autouse=True)
def _fast_bot(monkeypatch):
    monkeypatch.setattr(server, "BOT_DELAY_S", 0)  # the 1 s "thinking" pause, off in tests
    monkeypatch.setattr(server, "COUNTDOWN_S", 0)  # "ready" starts the clock at once (see _arm)


def _start_solo(level="beginner", *, open_gates=True):
    code = client.post("/api/rooms", json={"solo": True}).json()["code"]
    a = _join(code, "Ana")
    _drain(a, lambda s: s["solo"] and s["me"]["role"] == "defuser" and s["can_start"])
    a.send_json({"type": "level", "level": level})
    a.send_json({"type": "start"})
    state = _arm(a)
    return code, a, _open_gates(a, state) if open_gates else state


def _bot_said(ws, n_before):
    return _drain(ws, lambda s: len(s["chat"]) > n_before and s["chat"][-1].get("from") == BOT_NAME)


def _talk(code, ws, s, m):
    """Name module m with its first item, then answer each of the bot's questions."""
    msg = [m.widget.items(m.facts)[0]]
    while True:
        n = len(s["chat"])
        ws.send_json({"type": "signs", "glosses": msg})
        s = _bot_said(ws, n)
        if s["bot_stage"] == "module":
            return s
        msg = answer(server.rooms[code].bot.pending, m)


def test_solo_room_starts_with_one_player_and_greets():
    _, a, s = _start_solo(open_gates=False)
    last = s["chat"][-1]
    assert (last["kind"], last["from"]) == ("say", BOT_NAME) and HqBot().case_lock_prompt() in last["text"]
    assert s["mission"]["stage"] == "case_lock" and len(s["players"]) == 1
    a.__exit__(None, None, None)


def test_solo_bot_answers_signs(monkeypatch):
    monkeypatch.setattr(server.random, "randrange", lambda *_: 1)
    _, a, s = _start_solo()
    first = s["bomb"][0]
    item = server.rooms[s["code"]].modules[0].widget.items(first["facts"])[0]
    a.send_json({"type": "signs", "glosses": [item]})
    s2 = _bot_said(a, len(s["chat"]))
    assert s2["chat"][-2]["kind"] == "signs"
    assert f"That is the {first['title']}." in s2["chat"][-1]["text"]
    assert s2["bot_stage"] == "details"
    a.__exit__(None, None, None)


def test_solo_full_game_reaches_escaped(monkeypatch):
    seeds = iter((1, 2))
    monkeypatch.setattr(server.random, "randrange", lambda *_: next(seeds))
    code, a, s = _start_solo(open_gates=False)
    original = s
    round_id = s["round_id"]
    assert HqBot().case_lock_prompt() in s["chat"][-1]["text"]
    s = _open_case(a, s)
    assert len(set(s["mission"]["wires"])) == 4
    for _ in range(4):
        # The solo player uses only the bot's positional prompt and the visible tray.
        prompt = s["chat"][-1]["text"]
        index = next(i for i, position in enumerate(POSITIONS) if f"the {position} wire" in prompt)
        s = _gate_action(a, s, "signs", glosses=[s["mission"]["wires"][index]])
    assert s["mission"]["stage"] == "modules" and HqBot().greeting() in s["chat"][-1]["text"]
    gate_credits = s["practice_credits"]
    assert len(gate_credits) == 7
    for i, m in enumerate(server.rooms[code].modules):
        s = _talk(code, a, s, m)
        _solve_module(a, i, m)
        s = _drain(a, lambda s, i=i: s["progress"]["defused"] == i + 1)
    assert s["phase"] == "escaped" and not s["timed_out"]
    assert s["practice_credits"] == sorted(
        gate_credits + [f"{round_id}:{i}" for i in range(len(server.rooms[code].modules))]
    )
    a.send_json({"type": "again"})
    assert "mission" not in _drain(a, lambda s: s["phase"] == "lobby")
    a.send_json({"type": "start"})
    _drain(a, lambda s: s["phase"] == "playing")
    replay = _arm(a)
    assert replay["round_id"] != round_id
    assert replay["mission"]["case_code"] != original["mission"]["case_code"]
    assert replay["mission"]["stage"] == "case_lock"
    assert replay["mission"]["lock_confirmed"] == replay["mission"]["cut_count"] == 0
    a.send_json(_gate_message(original, "signs", glosses=list(original["mission"]["case_code"])))
    # A current-round password attempt is a barrier after the ignored old round input.
    replay = _gate_action(a, replay, "signs", glosses=["no"])
    assert replay["mission"]["revision"] == 1
    assert replay["mission"]["lock_confirmed"] == 0
    a.__exit__(None, None, None)


def test_solo_strike_gets_a_bot_reply():
    code, a, s = _start_solo()
    m = server.rooms[code].modules[0]
    s = _talk(code, a, s, m)
    a.send_json({"type": "act", "module": 0, "action": {"verb": "nope", "target": {}}})
    s = _drain(a, lambda s: s["strikes"] == 1 and s["chat"][-1].get("from") == BOT_NAME)
    assert f"That was a strike. Let us check the {m.spec.title} again." in s["chat"][-1]["text"]
    assert s["bot_stage"] == "details"
    a.__exit__(None, None, None)


def test_solo_room_refuses_a_second_player():
    code, a, _ = _start_solo()
    with client.websocket_connect(f"/ws/{code}") as ws:
        ws.send_json({"type": "hello", "name": "Ben"})
        assert ws.receive_json() == {"type": "error", "text": "This is a solo room."}
    a.__exit__(None, None, None)


def test_solo_ignores_role_and_say():
    code, a, s = _start_solo()
    a.send_json({"type": "say", "text": "Press the dog."})
    a.send_json({"type": "role", "role": "expert"})
    a.send_json({"type": "signs", "glosses": ["hello"]})
    s = _bot_said(a, len(s["chat"]))
    assert not any(m.get("text") == "Press the dog." for m in s["chat"])
    assert s["me"]["role"] == "defuser"
    a.__exit__(None, None, None)


def test_solo_again_starts_a_fresh_bot(monkeypatch):
    monkeypatch.setattr(server.random, "randrange", lambda *_: 1)
    code, a, s = _start_solo()
    m = server.rooms[code].modules[0]
    a.send_json({"type": "signs", "glosses": [m.widget.items(m.facts)[0]]})
    _drain(a, lambda s: s.get("bot_stage") == "details")
    a.send_json({"type": "exit"})
    s = _drain(a, lambda s: s["phase"] == "lobby")
    assert "bot_stage" not in s and s["can_start"]
    a.send_json({"type": "start"})
    s = _drain(a, lambda s: s["phase"] == "playing")
    assert s["mission"]["stage"] == "case_lock" and HqBot().case_lock_prompt() in s["chat"][-1]["text"]
    assert server.rooms[code].bot.page is None
    a.__exit__(None, None, None)


def test_two_player_rooms_have_no_bot():
    _, a, b, sa, sb = _start_game()
    assert sa["solo"] is False and "bot_stage" not in sa and "bot_stage" not in sb
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_two_player_gates_use_the_manual_and_restore_the_agent_seat(monkeypatch):
    # The level draw and both gates share this RNG seed. This draw includes a leading zero and a repeat.
    monkeypatch.setattr(server.random, "randrange", lambda *_: 1302)  # 1302: the code "007" (no 2 since Nov 2026)
    with client:
        code, agent, hq, start, hq_start = _start_game(open_gates=False)
        pid = start["me"]["pid"]
        try:
            assert start["mission"]["case_code"] == "007"
            assert start["mission"]["lock_confirmed"] == 0 and "bomb" not in start
            assert set(hq_start["mission"]) == {"stage", "revision", "lock_confirmed", "cut_count"}
            assert "bomb" not in hq_start
            agent.send_json({"type": "act", "module": 0, "action": {"verb": "wrong", "target": {}}})
            state = start
            assert state["mission"]["lock_confirmed"] == state["strikes"] == 0
            deadline = server.rooms[code].deadline

            hq.send_json(_gate_message(state, "signs", glosses=["0"]))
            hq.send_json({"type": "say", "text": "Read the tag left to right."})
            responded = _drain(hq, lambda s: s["chat"][-1].get("text") == "Read the tag left to right.")
            assert responded["mission"]["lock_confirmed"] == 0
            state = _gate_action(agent, state, "signs", glosses=["9"])
            assert state["mission"]["lock_confirmed"] == state["strikes"] == 0
            assert not state["practice_credits"]
            assert "retry" in state["mission"]["feedback"]
            first_zero = _gate_message(state, "signs", glosses=["0"])
            state = _gate_action(agent, state, "signs", glosses=["0"])
            assert state["practice_credits"] == [f"{start['round_id']}:case_lock:0"]
            agent.send_json(first_zero)
            state = _gate_action(agent, state, "signs", glosses=["cat"])
            assert state["mission"]["lock_confirmed"] == 1
            agent.__exit__(None, None, None)
            agent = None
            agent = _join(code, "Ana", pid)
            resumed = _last_state(agent)
            assert resumed["mission"] == state["mission"]
            assert resumed["mission"]["lock_confirmed"] == 1
            assert resumed["practice_credits"] == state["practice_credits"]
            state = _gate_action(agent, resumed, "signs", glosses=["0"])
            assert state["mission"]["lock_confirmed"] == 2
            state = _gate_action(agent, state, "signs", glosses=["7"])
            manual = _drain(hq, lambda s: s["mission"]["stage"] == "wire_tray")
            assert set(manual["mission"]) == {"stage", "revision", "lock_confirmed", "cut_count", "wire_rule"}
            assert "bomb" not in manual and "bomb" not in state
            assert "wire_rule" not in state["mission"]
            assert sorted(manual["mission"]["wire_rule"]) == sorted(POSITIONS)
            order = [POSITIONS.index(position) for position in manual["mission"]["wire_rule"]]
            wires = state["mission"]["wires"]
            assert len(set(wires)) == 4 and set(wires) <= set(load_pool()["colors"].pool)

            state = _gate_action(agent, state, "wire_cut", wire=order[0])
            assert state["mission"]["feedback"] == "Sign the wire color first" and state["strikes"] == 0
            state = _gate_action(agent, state, "signs", glosses=["cat"])
            assert state["mission"]["confirmed_color"] is None and state["strikes"] == 0
            assert len(state["practice_credits"]) == 3
            state = _gate_action(agent, state, "signs", glosses=[wires[order[1]]])
            assert "does not match" in state["mission"]["feedback"] and state["strikes"] == 1
            assert state["mission"]["cuts"] == [] and len(state["practice_credits"]) == 3

            first_cut = _gate_message(state, "signs", glosses=[wires[order[0]]])
            state = _gate_action(agent, state, "signs", glosses=[wires[order[0]]])
            assert state["mission"]["cuts"] == order[:1] and len(state["practice_credits"]) == 4
            shared = _drain(hq, lambda s: s["mission"]["cut_count"] == 1)
            assert shared["strikes"] == 1 and not shared["practice_credits"]
            agent.send_json(first_cut)
            agent.send_json(_gate_message(state, "wire_cut", wire=order[0]))
            state = _gate_action(agent, state, "signs", glosses=[wires[order[2]]])
            assert state["strikes"] == 2 and state["mission"]["cuts"] == order[:1]
            agent.__exit__(None, None, None)
            agent = None
            agent = _join(code, "Ana", pid)
            resumed = _last_state(agent)
            assert resumed["mission"] == state["mission"]
            assert resumed["practice_credits"] == state["practice_credits"]
            state = resumed
            for index in order[1:]:
                state = _gate_action(agent, state, "signs", glosses=[wires[index]])
            assert state["mission"]["stage"] == "modules" and "bomb" in state
            assert state["mission"]["cut_count"] == 4 and state["strikes"] == 2
            assert state["progress"] == {"total": 4, "defused": 0}
            assert len(state["practice_credits"]) == 7
            assert server.rooms[code].deadline == deadline
            # HQ's last view keeps only the public stage counts and the confirmed chat.
            public = _drain(hq, lambda s: s["mission"]["stage"] == "modules")
            assert set(public["mission"]) == set(hq_start["mission"]) and "bomb" not in public
        finally:
            if agent is not None:
                agent.__exit__(None, None, None)
            hq.__exit__(None, None, None)


@pytest.mark.parametrize("stage", ["case_lock", "wire_tray", "modules"])
@pytest.mark.parametrize("solo", [True, False])
def test_timeout_blocks_input_and_reports_the_same_outcome(stage, solo):
    with client:
        if solo:
            code, agent, start = _start_solo(open_gates=False)
            hq = None
        else:
            code, agent, hq, start, _ = _start_game(open_gates=False)
        try:
            if stage == "case_lock":
                state = start
                pending = _gate_message(state, "signs", glosses=list(state["mission"]["case_code"]))
            elif stage == "wire_tray":
                state = _open_case(agent, start)
                index = server.rooms[code].mission.wire_order[0]
                pending = _gate_message(state, "signs", glosses=[state["mission"]["wires"][index]])
            else:
                state = _open_gates(agent, start)
                module = server.rooms[code].modules[0]
                step = module.widget.steps(module.solution())[0][0]
                pending = {"type": "act", "module": 0, "action": step.to_json(), "round_id": state["round_id"]}
            server.rooms[code].deadline = time.monotonic() - 1
            agent.send_json(pending)
            ended = _drain(agent, lambda s: s["phase"] == "boom")
            assert ended["timed_out"] and ended["practice_credits"] == state["practice_credits"]
            assert ended["remaining_s"] == 0 and ended["mission"] == state["mission"]
            assert ended["progress"] == state["progress"]
            assert ended["chat"][-1]["text"] == "Time ran out. Detonation!"
            if hq:
                shared = _drain(hq, lambda s: s["phase"] == "boom")
                assert shared["timed_out"] and shared["round_id"] == ended["round_id"]
        finally:
            agent.__exit__(None, None, None)
            if hq:
                hq.__exit__(None, None, None)


def test_static_files_are_revalidated():
    # Browsers must not run a stale module next to a new one after a deploy: one missing
    # export stops every script on the page (found in playtest: "Play solo" did nothing).
    for path in ("/static/app.js", "/static/glossary.js", "/static/style.css", "/"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path


def test_solo_bot_thinks_before_it_replies(monkeypatch):
    monkeypatch.setattr(server, "BOT_DELAY_S", 0.3)
    code, a, s = _start_solo()
    m = server.rooms[code].modules[0]
    t0 = time.monotonic()
    a.send_json({"type": "signs", "glosses": [m.widget.items(m.facts)[0]]})
    typing = _drain(a, lambda s: s["chat"][-1]["kind"] == "signs")
    assert typing["bot_typing"] is True and typing["bot_stage"] == "module"
    done = _bot_said(a, len(typing["chat"]))
    # Windows clocks tick in about 16 ms steps, so allow a little less than 0.3 s.
    assert time.monotonic() - t0 >= 0.25
    # One item can already decide the page (a rule "if there is a TV"): then the bot gives
    # the instruction at once and goes back to "module". Either way the stage matches the bot.
    assert done["bot_typing"] is False and done["bot_stage"] == server.rooms[code].bot.stage
    a.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Initializing: the timer waits until the agent's tracker and the sign model are ready.
# Then a 3-2-1, then the clock and the mission's case lock.
# ---------------------------------------------------------------------------
def test_the_timer_waits_for_the_agent_to_be_ready(monkeypatch):
    monkeypatch.setattr(server, "COUNTDOWN_S", 0.3)
    code, a, b, sa, sb = _start_game(open_gates=False, arm=False)
    full = config.LEVELS["intermediate"].timer_s
    assert sa["round_id"] == sb["round_id"] and sa["mission"]["stage"] == "case_lock"
    assert sa["armed"] is False and sa["remaining_s"] == full
    time.sleep(0.3)
    assert server.rooms[code].remaining() == full  # frozen while initializing
    # The case lock waits for the clock too.
    a.send_json(_gate_message(sa, "signs", glosses=[sa["mission"]["case_code"][0]]))
    b.send_json({"type": "ready"})  # the handler cannot start the clock
    b.send_json({"type": "say", "text": "ping"})
    s = _drain(b, lambda s: s["chat"][-1].get("text") == "ping")
    assert server.rooms[code].armed is False and "countdown_s" not in s
    assert server.rooms[code].mission.lock_confirmed == 0
    a.send_json({"type": "ready"})
    # Ready starts a 3-2-1 that both players see. The clock holds until it ends.
    s = _drain(a, lambda s: "countdown_s" in s)
    assert s["armed"] is False and 0 < s["countdown_s"] <= server.COUNTDOWN_S and s["remaining_s"] == full
    s = _drain(b, lambda s: s["armed"])
    assert "countdown_s" not in s
    time.sleep(0.3)
    assert server.rooms[code].remaining() < full
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_the_timer_starts_anyway_after_a_while(monkeypatch):
    monkeypatch.setattr(server, "ARM_TIMEOUT_S", 0.3)
    monkeypatch.setattr(server, "COUNTDOWN_S", 0.3)
    code, a, b, sa, sb = _start_game(open_gates=False, arm=False)
    # b sent "start", so the timer task runs on b's TestClient loop; only b's socket can
    # receive that task's broadcast here (the real server has one loop for every socket).
    _drain(b, lambda s: s["armed"])
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_the_case_code_never_uses_2():
    from escape_pod.web.mission import Mission
    for seed in range(500):
        assert "2" not in Mission.draw(random.Random(seed)).code


def test_a_defused_switch_shows_its_new_position():
    code, a, b, sa, sb = _start_game()
    room = server.rooms[code]
    spec = load_pool()["home_things"]
    rng = random.Random(1)
    while True:  # a module whose answer sets a switch to the other state
        m = Module(spec, WIDGETS["switches"].generate(spec, rng))
        sol = m.solution()
        if "switch" not in sol.target:
            continue
        before = next(s["state"] for s in m.facts["switches"] if s["label"] == sol.target["switch"])
        if before != sol.target["state"]:
            break
    room.modules[0] = m
    a.send_json({"type": "act", "module": 0, "action": {"verb": sol.verb, "target": sol.target}})
    s = _drain(a, lambda s: s["bomb"][0]["defused"])
    shown = next(x["state"] for x in s["bomb"][0]["facts"]["switches"] if x["label"] == sol.target["switch"])
    assert shown == sol.target["state"]
    assert next(x["state"] for x in m.facts["switches"] if x["label"] == sol.target["switch"]) == before  # the engine's facts stay
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_a_two_cut_answer_is_checked_click_by_click():
    code, a, b, sa, sb = _start_game()
    m = Module(load_pool()["colors"], {"colors": ["green", "white", "black", "orange"]})
    server.rooms[code].modules[0] = m
    cut = lambda c: a.send_json({"type": "act", "module": 0, "action": {"verb": "cut", "target": {"color": c}}})
    cut("white")
    s = _drain(a, lambda s: s["bomb"][0]["done"])
    assert s["strikes"] == 0 and not s["bomb"][0]["defused"]
    assert s["bomb"][0]["done"] == [{"verb": "cut", "target": {"color": "white"}}]
    cut("black")
    s = _drain(a, lambda s: s["bomb"][0]["defused"])
    assert s["strikes"] == 0 and s["chat"][-1]["text"] == "Module 1 defused!"
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_custom_level_sets_modules_and_time():
    code = client.post("/api/rooms", json={"solo": True}).json()["code"]
    a = _join(code, "Ana")
    _drain(a, lambda s: s["can_start"])
    a.send_json({"type": "level", "level": "custom", "modules": 2, "timer_s": 420})
    s = _drain(a, lambda s: s["level"] == "custom")
    assert s["levels"]["custom"]["modules"] == 2 and s["levels"]["custom"]["timer_s"] == 420
    for bad in ({"modules": 6}, {"modules": 0}, {"timer_s": 30}, {"timer_s": 99999}, {"modules": "3"}):
        a.send_json({"type": "level", "level": "custom", **bad})  # out of range: ignored
    a.send_json({"type": "level", "level": "custom", "modules": 5})  # time stays 420
    s = _drain(a, lambda s: s["levels"]["custom"]["modules"] == 5)
    assert s["levels"]["custom"]["timer_s"] == 420
    a.send_json({"type": "start"})
    s = _drain(a, lambda s: s["phase"] == "playing")
    assert s["mission"]["stage"] == "case_lock" and s["progress"]["total"] == 5
    assert 419 < s["remaining_s"] <= 420
    a.__exit__(None, None, None)
