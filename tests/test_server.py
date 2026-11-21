# Owner: Teammate 1 (Game, scenes, widgets)
from contextlib import contextmanager

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


def test_video_signals_reach_only_the_other_seat():
    _, a, b, _, _ = _start_game()
    session = "00000000-0000-4000-8000-000000000000"
    try:
        offer = {"type": "video", "session": session, "signal": "offer", "sdp": "example SDP"}
        a.send_json({**offer, "sdp": {"invalid": True}})
        a.send_json({**offer, "room": "OTHER", "extra": "discarded"})
        assert b.receive_json() == offer
        answer = {**offer, "signal": "answer"}
        b.send_json(answer)
        assert a.receive_json() == answer  # The offer was never echoed to its sender.

        # The expert can independently send an offer for their own camera.
        b.send_json(offer)
        assert a.receive_json() == offer
    finally:
        a.__exit__(None, None, None)
        b.__exit__(None, None, None)


@contextmanager
def _guided_pair():
    with client:
        code = client.post("/api/rooms?mode=guided").json()["code"]
        with client.websocket_connect(f"/ws/{code}") as a, client.websocket_connect(f"/ws/{code}") as b:
            a.send_json({"type": "hello", "name": "Child"})
            assert a.receive_json()["type"] == "welcome"
            b.send_json({"type": "hello", "name": "Parent"})
            assert b.receive_json()["type"] == "welcome"
            a.send_json({"type": "role", "role": "defuser"})
            b.send_json({"type": "role", "role": "expert"})
            _drain(b, lambda s: s["can_start"])
            a.send_json({"type": "start"})
            sa = _drain(a, lambda s: s["phase"] == "playing")
            sb = _drain(b, lambda s: s["phase"] == "playing")
            yield a, b, sa, sb


def _guided_press(ws, state, control):
    ws.send_json({"type": "guided_action", "turn": state["guided"]["turn"], "control": control})


def test_guided_practice_privacy_feedback_completion_and_swap():
    with _guided_pair() as (a, b, sa, sb):
        practice = sa["guided"]
        assert practice["step"] == "practice" and sa["remaining_s"] == 0
        assert practice["clue"]["text"] == "Press blue 3"
        assert "controls" not in practice and "clue" not in sb["guided"]
        b.send_json({"type": "guided_begin"})
        _guided_press(a, sa, "blue-3")  # The signer has no authority to operate the panel.
        b.send_json({"type": "guided_repeat", "turn": practice["turn"]})
        sa = _drain(a, lambda s: s["guided"]["repeat"] == 1)
        assert sa["guided"]["clue"] == practice["clue"]
        _guided_press(b, sa, "blue-1")
        sa = _drain(a, lambda s: s["guided"]["feedback"] == "try_again")
        assert sa["guided"]["turn"] == practice["turn"]
        _guided_press(b, sa, "blue-3")
        sa = _drain(a, lambda s: s["guided"]["step"] == "ready")
        assert sa["remaining_s"] == 0
        a.send_json({"type": "guided_begin"})
        sa = _drain(a, lambda s: s["guided"]["step"] == "timed")
        sb = _drain(b, lambda s: s["guided"]["step"] == "timed")
        assert sa["remaining_s"] > 0 and "clue" not in sb["guided"]
        for solved in range(1, 4):
            answer = sa["guided"]["clue"]["picture"]["id"]
            _guided_press(b, sa, answer)
            _guided_press(b, sa, answer)  # An old confirmation cannot count for the next clue.
            sa = _drain(a, lambda s: s["guided"]["solved"] == solved)
        sb = _drain(b, lambda s: s["phase"] == "escaped")
        assert len(sb["guided"]["review"]) == 4
        assert sb["guided"]["step"] == "unlocked" and sb["remaining_s"] > 0
        b.send_json({"type": "guided_swap"})
        sa = _drain(a, lambda s: s["phase"] == "lobby")
        sb = _drain(b, lambda s: s["phase"] == "lobby")
        assert sa["me"]["role"] == "expert" and sb["me"]["role"] == "defuser"
        assert sa["guided"]["swapped"]


def test_guided_timeout_restarts_same_clues_without_timer(monkeypatch):
    monkeypatch.setattr(server, "TIMED_SECONDS", 0.05)
    with _guided_pair() as (a, b, sa, _):
        _guided_press(b, sa, "blue-3")
        _drain(b, lambda s: s["guided"]["step"] == "ready")
        b.send_json({"type": "guided_begin"})
        timed = _drain(a, lambda s: s["guided"]["step"] == "timed")
        timeout = _drain(b, lambda s: s["guided"]["step"] == "timeout")
        assert timeout["remaining_s"] == 0 and "clue" not in timeout["guided"]
        a.send_json({"type": "guided_retry"})
        retry = _drain(a, lambda s: s["guided"]["step"] == "untimed")
        assert retry["remaining_s"] == 0 and retry["phase"] == "playing"
        assert retry["guided"]["clue"] == timed["guided"]["clue"]


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
