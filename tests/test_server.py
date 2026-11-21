# Owner: Teammate 1 (Game, scenes, widgets)
import time

import pytest
from fastapi.testclient import TestClient

import random

from escape_pod import config
from escape_pod.puzzles.engine import WIDGETS, Module, load_pool
from escape_pod.web import server

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


def _join(code, name):
    ws = client.websocket_connect(f"/ws/{code}")
    ws.__enter__()
    ws.send_json({"type": "hello", "name": name})
    assert ws.receive_json()["type"] == "welcome"
    return ws


def _start_game(level="intermediate"):
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
    return code, a, b, sa, sb


def test_manual_and_icons_endpoints():
    assert len(client.get("/api/manual").json()) == 20
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
    assert sb["progress"] == {"total": 4, "defused": 0}
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_full_game_signs_reply_strike_and_escape():
    code, a, b, sa, _ = _start_game()
    mods = server.rooms[code].modules
    # Defuser signs, expert sees the signs and replies.
    a.send_json({"type": "signs", "glosses": ["CAT", " dog "]})
    sb = _drain(b, lambda s: any(m["kind"] == "signs" for m in s["chat"]))
    assert [m for m in sb["chat"] if m["kind"] == "signs"][0]["glosses"] == ["cat", "dog"]
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
        a.send_json({"type": "act", "module": i, "action": m.solution().to_json()})
    sa = _drain(a, lambda s: s["phase"] == "escaped")
    assert sa["progress"]["defused"] == 4
    assert sa["chat"][-1]["text"] == "All modules defused. Device neutralized."
    sb = _drain(b, lambda s: s["phase"] == "escaped")
    assert "bomb" in sb  # debrief: both see the bomb at the end
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
        correct = {"type": "act", "round_id": round_id, "module": 0, "action": module.solution().to_json()}
        hq_online = True
        try:
            agent.send_json({"type": "ready"})
            agent.send_json({"type": "signs", "glosses": module.widget.items(module.facts)})
            _drain(hq, lambda s: s["chat"][-1]["kind"] == "signs")
            hq.send_json({"type": "say", "text": "Try the matching control."})
            _drain(agent, lambda s: s["chat"][-1]["kind"] == "say")
            agent.send_json({**correct, "action": {"verb": "wrong", "target": {}}})
            assert _drain(agent, lambda s: s["strikes"] == 1)["practice_credits"] == []

            other = room.modules[1].solution().to_json()
            agent.send_json({**correct, "module": 1, "action": other})
            assert _drain(agent, lambda s: s["progress"]["defused"] == 1)["practice_credits"] == []

            hq.__exit__(None, None, None)
            hq_online = False
            _drain(agent, lambda s: not s["players"][1]["online"])
            agent.send_json(correct)
            agent.send_json(correct)
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
                agent.send_json(correct)  # Ignore a confirmation from the last round.
                agent.send_json({"type": "ready"})
                assert _drain(agent, lambda s: s["armed"])["progress"]["defused"] == 0
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


def _start_solo(level="beginner"):
    code = client.post("/api/rooms", json={"solo": True}).json()["code"]
    a = _join(code, "Ana")
    _drain(a, lambda s: s["solo"] and s["me"]["role"] == "defuser" and s["can_start"])
    a.send_json({"type": "level", "level": level})
    a.send_json({"type": "start"})
    return code, a, _drain(a, lambda s: s["phase"] == "playing")


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
    _, a, s = _start_solo()
    last = s["chat"][-1]
    assert (last["kind"], last["from"]) == ("say", BOT_NAME) and HqBot().greeting() in last["text"]
    assert s["bot_stage"] == "module" and len(s["players"]) == 1
    a.__exit__(None, None, None)


def test_solo_bot_answers_signs():
    _, a, s = _start_solo()
    first = s["bomb"][0]
    item = server.rooms[s["code"]].modules[0].widget.items(first["facts"])[0]
    a.send_json({"type": "signs", "glosses": [item]})
    s2 = _bot_said(a, len(s["chat"]))
    assert s2["chat"][-2]["kind"] == "signs"
    assert f"That is the {first['title']}." in s2["chat"][-1]["text"]
    assert s2["bot_stage"] == "details"
    a.__exit__(None, None, None)


def test_solo_full_game_reaches_escaped():
    code, a, s = _start_solo()
    round_id = s["round_id"]
    for i, m in enumerate(server.rooms[code].modules):
        s = _talk(code, a, s, m)
        a.send_json({"type": "act", "module": i, "action": m.solution().to_json()})
        s = _drain(a, lambda s, i=i: s["progress"]["defused"] == i + 1)
    assert s["phase"] == "escaped"
    assert s["practice_credits"] == [f"{round_id}:{i}" for i in range(len(server.rooms[code].modules))]
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


def test_solo_again_starts_a_fresh_bot():
    code, a, s = _start_solo()
    m = server.rooms[code].modules[0]
    a.send_json({"type": "signs", "glosses": [m.widget.items(m.facts)[0]]})
    _drain(a, lambda s: s.get("bot_stage") == "details")
    a.send_json({"type": "exit"})
    s = _drain(a, lambda s: s["phase"] == "lobby")
    assert "bot_stage" not in s and s["can_start"]
    a.send_json({"type": "start"})
    s = _drain(a, lambda s: s["phase"] == "playing")
    assert s["bot_stage"] == "module" and HqBot().greeting() in s["chat"][-1]["text"]
    a.__exit__(None, None, None)


def test_two_player_rooms_are_unchanged():
    _, a, b, sa, sb = _start_game()
    assert sa["solo"] is False and "bot_stage" not in sa and "bot_stage" not in sb
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


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
    assert time.monotonic() - t0 >= 0.3
    assert done["bot_typing"] is False and done["bot_stage"] == "details"
    a.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Initializing: the timer waits until the agent's tracker and the sign model are ready
# ---------------------------------------------------------------------------
def test_the_timer_waits_for_the_agent_to_be_ready():
    code, a, b, sa, sb = _start_game()
    full = config.LEVELS["intermediate"].timer_s
    assert sa["armed"] is False and sa["remaining_s"] == full
    time.sleep(0.3)
    assert server.rooms[code].remaining() == full  # frozen while initializing
    b.send_json({"type": "ready"})  # HQ cannot start the clock
    b.send_json({"type": "say", "text": "ping"})
    _drain(b, lambda s: s["chat"][-1].get("text") == "ping")
    assert server.rooms[code].armed is False
    a.send_json({"type": "ready"})
    s = _drain(b, lambda s: s["armed"])
    time.sleep(0.3)
    assert server.rooms[code].remaining() < full
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_the_timer_starts_anyway_after_a_while(monkeypatch):
    monkeypatch.setattr(server, "ARM_TIMEOUT_S", 0.3)
    code, a, b, sa, sb = _start_game()
    # b sent "start", so the timer task runs on b's TestClient loop; only b's socket can
    # receive that task's broadcast here (the real server has one loop for every socket).
    _drain(b, lambda s: s["armed"])
    a.__exit__(None, None, None)
    b.__exit__(None, None, None)


def test_a_defused_switch_shows_its_new_position():
    code, a, b, sa, sb = _start_game()
    room = server.rooms[code]
    spec = load_pool()["home_things"]
    rng = random.Random(1)
    while True:  # a module whose answer sets a switch to the other state
        m = Module(spec, WIDGETS["switches"].generate(spec, rng))
        sol = m.solution()
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
