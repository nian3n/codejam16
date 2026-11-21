# Owner: Teammate 1 (Game, scenes, widgets)
from fastapi.testclient import TestClient

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
