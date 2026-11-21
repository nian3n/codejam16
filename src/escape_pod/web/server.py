# Owner: Teammate 1 (Game, scenes, widgets)
"""Two-player web server: lobby, roles, one shared bomb (FastAPI + WebSockets).

Roles (spec change, Nov 2026: two humans now, the LLM alien comes later):
  defuser - sees the bomb, signs what they see (typed for now), clicks to act.
  expert  - sees only the manual and the signs, types replies. Never gets bomb facts.

The server owns all game state and decides right and wrong with the rule engine
(spec design rule 1). Clients only render what the server sends them.

    uv run escape-pod [--host 0.0.0.0] [--port 8000] [--debug]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from escape_pod import config
from escape_pod.manual.build import all_pages
from escape_pod.manual.solve import sheet_markdown
from escape_pod.puzzles.engine import Module, draw
from escape_pod.puzzles.models import Action
from escape_pod.web.guided import BUTTONS, TIMED_SECONDS, WIRES, GuidedRound
from escape_pod.web.practice import router as practice_router

STATIC = config.STATIC_DIR
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O, so codes are easy to read aloud
ROLES = ("defuser", "expert")
MAX_SIGNS, MAX_GLOSS_LEN, MAX_TEXT_LEN, MAX_CHAT = 12, 24, 300, 200

app = FastAPI(title="Escape Pod")
app.state.debug = False
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.include_router(practice_router)


@dataclass
class Player:
    pid: str
    name: str
    role: str | None = None
    ws: WebSocket | None = None


@dataclass
class Room:
    code: str
    players: dict[str, Player] = field(default_factory=dict)
    phase: Literal["lobby", "playing", "escaped", "boom"] = "lobby"
    level: str = "intermediate"
    seed: int = 0
    modules: list[Module] = field(default_factory=list)
    strikes: int = 0
    deadline: float = 0.0
    ended_left: float = 0.0
    chat: list[dict] = field(default_factory=list)
    timer_task: asyncio.Task | None = None
    guided: GuidedRound | None = None

    def remaining(self) -> float:
        if self.phase == "playing" and self.deadline:
            return max(0.0, self.deadline - time.monotonic())
        return self.ended_left

    def role_taken(self, role: str, by_other_than: str) -> bool:
        return any(p.role == role and p.pid != by_other_than for p in self.players.values())

    def can_start(self) -> bool:
        return self.phase == "lobby" and all(self.role_taken(r, "") for r in ROLES) and (
            self.guided is None or self.both_online()
        )

    def both_online(self) -> bool:
        return all(any(p.role == role and p.ws is not None for p in self.players.values()) for role in ROLES)

    def say(self, entry: dict):
        entry["t"] = round(time.time(), 3)
        self.chat.append(entry)
        del self.chat[:-MAX_CHAT]


rooms: dict[str, Room] = {}


# ---------------------------------------------------------------------------
# Views: what each player is allowed to see
# ---------------------------------------------------------------------------
def view(room: Room, me: Player) -> dict:
    v = {
        "type": "state",
        "code": room.code,
        "me": {"pid": me.pid, "name": me.name, "role": me.role},
        "players": [{"name": p.name, "role": p.role, "online": p.ws is not None} for p in room.players.values()],
        "phase": room.phase,
        "level": room.level,
        "levels": {k: {"modules": l.modules, "timer_s": l.timer_s, "hard": l.allow_hard}
                   for k, l in config.LEVELS.items()},
        "can_start": room.can_start(),
        "remaining_s": round(room.remaining(), 2),
        "strikes": room.strikes,
        "max_strikes": config.MAX_STRIKES,
        "chat": room.chat,
        "debug": app.state.debug,
    }
    if room.modules:
        v["progress"] = {"total": len(room.modules), "defused": sum(m.defused for m in room.modules)}
    # Only the defuser sees the bomb. At the end both see it, for the debrief.
    if room.modules and (me.role == "defuser" or room.phase in ("escaped", "boom")):
        v["bomb"] = [{"id": m.spec.id, "title": m.spec.title, "widget": m.spec.widget,
                      "target_words": m.spec.target_words, "pool": m.spec.pool,
                      "facts": m.facts, "defused": m.defused} for m in room.modules]
    if room.guided:
        v["guided"] = room.guided.view(me.role)
        if room.phase == "lobby":
            v["guided"].pop("clue", None)
    return v


async def broadcast(room: Room):
    for p in list(room.players.values()):
        if p.ws is None:
            continue
        try:
            await p.ws.send_json(view(room, p))
        except Exception:
            p.ws = None


# ---------------------------------------------------------------------------
# Game flow
# ---------------------------------------------------------------------------
def end_game(room: Room, result: Literal["escaped", "boom"], why: str):
    room.ended_left = room.remaining()
    room.phase = result
    room.say({"kind": "event", "text": why})
    if room.timer_task and room.timer_task is not asyncio.current_task():
        room.timer_task.cancel()
    room.timer_task = None


async def watch_timer(room: Room):
    while room.phase == "playing":
        await asyncio.sleep(0.25)
        if room.phase == "playing" and room.remaining() <= 0:
            expire_round(room)
            await broadcast(room)


def expire_round(room: Room):
    if room.guided:
        room.guided.step = "timeout"
        room.guided.feedback = ""
        end_game(room, "boom", "The panel went dark.")
    else:
        end_game(room, "boom", "Time ran out. BOOM!")


def start_game(room: Room):
    level = config.LEVELS[room.level]
    room.seed = random.randrange(1_000_000)
    room.modules = draw(random.Random(room.seed), level)
    room.strikes = 0
    room.chat = []
    room.phase = "playing"
    room.deadline = time.monotonic() + (level.timer_s or 600)
    room.say({"kind": "event", "text": f"The bomb is armed: {len(room.modules)} modules. Good luck!"})
    room.timer_task = asyncio.create_task(watch_timer(room))


def act(room: Room, index: int, action: Action):
    m = room.modules[index]
    if m.defused:
        return
    if m.check(action):
        m.defused = True
        room.say({"kind": "event", "text": f"Module {index + 1} defused!"})
        if all(x.defused for x in room.modules):
            end_game(room, "escaped", "All modules defused. The pod launches!")
    else:
        room.strikes += 1
        room.say({"kind": "event", "text": f"Strike {room.strikes} of {config.MAX_STRIKES}!", "strike": True})
        if room.strikes >= config.MAX_STRIKES:
            end_game(room, "boom", "Three strikes. BOOM!")


def clean_glosses(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = [str(g).strip().lower()[:MAX_GLOSS_LEN] for g in raw[:MAX_SIGNS]]
    return [g for g in out if g]


async def handle(room: Room, me: Player, msg: dict):
    kind = msg.get("type")
    if kind == "role" and room.phase == "lobby":
        role = msg.get("role")
        if role in ROLES and not room.role_taken(role, me.pid):
            me.role = role
    elif room.guided:
        if not handle_guided(room, room.guided, me, msg):
            return
    elif kind == "level" and room.phase == "lobby" and msg.get("level") in config.LEVELS:
        room.level = msg["level"]
    elif kind == "start" and room.can_start():
        start_game(room)
    elif kind == "signs" and room.phase == "playing" and me.role == "defuser":
        glosses = clean_glosses(msg.get("glosses"))
        if glosses:
            room.say({"kind": "signs", "from": me.name, "glosses": glosses})
    elif kind == "say" and room.phase == "playing" and me.role == "expert":
        text = str(msg.get("text", "")).strip()[:MAX_TEXT_LEN]
        if text:
            room.say({"kind": "say", "from": me.name, "text": text})
    elif kind == "act" and room.phase == "playing" and me.role == "defuser":
        i = msg.get("module")
        a = msg.get("action")
        if isinstance(i, int) and 0 <= i < len(room.modules) and isinstance(a, dict):
            try:
                action = Action.from_json(a)
            except (KeyError, TypeError, ValueError):
                return
            act(room, i, action)
    elif kind == "again" and room.phase in ("escaped", "boom"):
        room.phase, room.modules, room.chat, room.strikes = "lobby", [], [], 0
    else:
        return
    await broadcast(room)


def handle_guided(room: Room, game: GuidedRound, me: Player, msg: dict) -> bool:
    kind = msg.get("type")
    if me.role not in ROLES:
        return False
    if room.phase == "playing" and game.step == "timed" and room.remaining() <= 0:
        expire_round(room)
        return True

    if kind == "start" and room.can_start():
        game.begin_practice()
        room.phase = "playing"
        room.deadline = room.ended_left = 0
        room.chat.clear()
        return True
    if kind == "guided_begin" and room.phase == "playing" and game.step == "ready" and room.both_online():
        game.step = "timed"
        game.feedback = ""
        game.move_to_next_clue()
        room.deadline = time.monotonic() + TIMED_SECONDS
        room.timer_task = asyncio.create_task(watch_timer(room))
        return True
    if kind == "guided_retry" and room.phase == "boom" and game.step == "timeout":
        game.step = "untimed"
        game.index = 0
        game.feedback = ""
        game.move_to_next_clue()
        room.phase = "playing"
        room.deadline = room.ended_left = 0
        room.chat.clear()
        return True
    if (kind == "again" and room.phase in ("escaped", "boom")) or (
        kind == "guided_swap" and room.phase == "escaped"
    ):
        swapped = game.swapped
        if kind == "guided_swap":
            for player in room.players.values():
                player.role = "expert" if player.role == "defuser" else "defuser"
            swapped = not swapped
        room.phase = "lobby"
        room.guided = GuidedRound(swapped=swapped, turn=game.turn)
        return True
    if me.role != "expert" or room.phase != "playing" or msg.get("turn") != game.turn or not game.clue:
        return False
    if kind == "guided_repeat":
        game.repeat += 1
        return True
    if kind != "guided_action":
        return False
    control = msg.get("control")
    if not any(option.id == control for option in (*BUTTONS, *WIRES)):
        return False
    if control != game.clue.id:
        game.feedback = "try_again"
        return True

    game.move_to_next_clue()
    game.feedback = "correct"
    if game.step == "practice":
        game.step = "ready"
    else:
        game.index += 1
        if game.index == len(game.deck):
            game.step = "unlocked"
            end_game(room, "escaped", "The room unlocked.")
    return True


async def relay_video(room: Room, me: Player, msg: dict):
    """Forward WebRTC setup only to the other seat during play."""
    if room.phase != "playing" or me.role not in ROLES:
        return
    peer = next((p.ws for p in room.players.values()
                 if p.role in ROLES and p.role != me.role), None)
    signal, session = msg.get("signal"), msg.get("session")
    if peer is None or not isinstance(session, str) or len(session) != 36:
        return
    payload = {"type": "video", "signal": signal, "session": session}
    if signal in ("offer", "answer"):
        sdp = msg.get("sdp")
        if not isinstance(sdp, str) or not 0 < len(sdp) <= 24_000:
            return
        payload["sdp"] = sdp
    elif signal != "stop":
        return
    try:
        await peer.send_json(payload)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass  # The recipient may have disconnected during the send.


# ---------------------------------------------------------------------------
# HTTP + WebSocket routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/manual")
def manual():
    return all_pages()


@app.get("/api/icons")
def icons():
    return json.loads(config.ICONS_FILE.read_text(encoding="utf-8"))


@app.post("/api/rooms")
def create_room(mode: Literal["classic", "guided"] = "classic"):
    while True:
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(4))
        if code not in rooms:
            break
    rooms[code] = Room(code, guided=GuidedRound() if mode == "guided" else None)
    return {"code": code}


@app.get("/api/rooms/{code}/answer-key", response_class=PlainTextResponse)
def answer_key(code: str):
    """The dynamic answer key for the live bomb. Only with --debug: it shows the answers."""
    room = rooms.get(code.upper())
    if not app.state.debug:
        raise HTTPException(403, "Start the server with --debug to see the answer key.")
    if room is None or not room.modules:
        raise HTTPException(404, "No bomb in this room yet.")
    return sheet_markdown(room.modules, f"Room {room.code}, seed {room.seed}, level {room.level}.")


@app.websocket("/ws/{code}")
async def ws_room(ws: WebSocket, code: str):
    await ws.accept()
    room = rooms.get(code.upper())
    if room is None:
        await ws.send_json({"type": "error", "text": "That room does not exist."})
        await ws.close()
        return
    try:
        hello = await ws.receive_json()
    except (WebSocketDisconnect, ValueError):
        return
    pid = str(hello.get("pid") or "")
    name = str(hello.get("name") or "").strip()[:20] or "Player"
    me = room.players.get(pid)
    if me is None:
        if len(room.players) >= 2:
            await ws.send_json({"type": "error", "text": "This room already has two players."})
            await ws.close()
            return
        me = Player(uuid.uuid4().hex, name)
        room.players[me.pid] = me
    elif me.ws is not None:
        try:  # same player opened a second tab: the newest tab wins
            await me.ws.close(code=4000)
        except Exception:
            pass
    me.ws = ws
    await ws.send_json({"type": "welcome", "pid": me.pid})
    await broadcast(room)
    try:
        while True:
            msg = await ws.receive_json()
            if me.ws is not ws:
                break
            if isinstance(msg, dict):
                if msg.get("type") == "video":
                    await relay_video(room, me, msg)
                else:
                    await handle(room, me, msg)
    except (WebSocketDisconnect, ValueError, RuntimeError):
        pass
    finally:
        # Rooms stay in memory after everyone leaves, so a page reload can rejoin.
        # Fine for a hackathon; a long-running server would expire idle rooms.
        if me.ws is ws:
            me.ws = None
            await broadcast(room)


def main():
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 so other laptops on the Wi-Fi can join")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--debug", action="store_true", help="enable the answer key at /api/rooms/<code>/answer-key")
    ap.add_argument("--ssl-certfile", help="certificate for HTTPS camera access over Wi-Fi")
    ap.add_argument("--ssl-keyfile", help="private key for the HTTPS certificate")
    a = ap.parse_args()
    if bool(a.ssl_certfile) != bool(a.ssl_keyfile):
        ap.error("--ssl-certfile and --ssl-keyfile must be used together")
    app.state.debug = a.debug
    uvicorn.run(app, host=a.host, port=a.port, ssl_certfile=a.ssl_certfile, ssl_keyfile=a.ssl_keyfile)


if __name__ == "__main__":
    main()
