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
import os
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
from escape_pod.web.ice import ice_servers

STATIC = config.STATIC_DIR
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O, so codes are easy to read aloud
ROLES = ("defuser", "expert")
MAX_SIGNS, MAX_GLOSS_LEN, MAX_TEXT_LEN, MAX_CHAT = 12, 24, 300, 200
MAX_RTC_BYTES = 64_000  # an SDP offer is a few KB; this only stops abuse
ROOM_IDLE_S = 2 * 3600  # forget a room 2 h after its last player left
MAX_ROOMS = 1000        # a public server refuses new rooms past this (after pruning)

app = FastAPI(title="Keep Moving and Nobody Explodes")
app.state.debug = False
app.mount("/static", StaticFiles(directory=STATIC), name="static")


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
    last_seen: float = field(default_factory=time.monotonic)  # for pruning idle rooms

    def remaining(self) -> float:
        if self.phase == "playing":
            return max(0.0, self.deadline - time.monotonic())
        return self.ended_left

    def role_taken(self, role: str, by_other_than: str) -> bool:
        return any(p.role == role and p.pid != by_other_than for p in self.players.values())

    def can_start(self) -> bool:
        return self.phase == "lobby" and all(self.role_taken(r, "") for r in ROLES)

    def say(self, entry: dict):
        entry["t"] = round(time.time(), 3)
        self.chat.append(entry)
        del self.chat[:-MAX_CHAT]


rooms: dict[str, Room] = {}


def prune_rooms(now: float | None = None) -> None:
    """Forget rooms nobody has been connected to for ROOM_IDLE_S.

    On a public server the rooms dict would otherwise grow forever. A room with a
    player online is never pruned, however old it is.
    """
    now = time.monotonic() if now is None else now
    for code, room in list(rooms.items()):
        online = any(p.ws is not None for p in room.players.values())
        if not online and now - room.last_seen > ROOM_IDLE_S:
            if room.timer_task:
                room.timer_task.cancel()
            del rooms[code]


# ---------------------------------------------------------------------------
# Views: what each player is allowed to see
# ---------------------------------------------------------------------------
def view(room: Room, me: Player) -> dict:
    other = next((p for p in room.players.values() if p.pid != me.pid), None)
    v = {
        "type": "state",
        "code": room.code,
        # polite: WebRTC "perfect negotiation" needs exactly one polite peer. Comparing
        # the two pids gives each browser a different answer without any extra message.
        "me": {"pid": me.pid, "name": me.name, "role": me.role,
               "polite": other is not None and me.pid > other.pid},
        "players": [{"name": p.name, "role": p.role, "online": p.ws is not None, "you": p.pid == me.pid}
                    for p in room.players.values()],
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
            end_game(room, "boom", "Time ran out. Detonation!")
            await broadcast(room)


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


def back_to_lobby(room: Room, why: str | None = None):
    """Stop any game and return the room to the lobby. Roles stay as they are."""
    if room.timer_task:
        room.timer_task.cancel()
    room.timer_task = None
    room.phase, room.modules, room.chat, room.strikes = "lobby", [], [], 0
    if why:
        room.say({"kind": "event", "text": why})


def leave(room: Room, me: Player):
    """The player clicked "Leave room": free the seat and the role.

    A game in progress cannot go on with one player, so it ends. A room with nobody
    left is deleted at once (no reload can rejoin a seat the player gave up).
    """
    room.players.pop(me.pid, None)
    if room.phase == "playing":
        back_to_lobby(room, f"{me.name} left the room. The game ended.")
    else:
        back_to_lobby(room, f"{me.name} left the room.")
    if not room.players:
        rooms.pop(room.code, None)


def act(room: Room, index: int, action: Action):
    m = room.modules[index]
    if m.defused:
        return
    if m.check(action):
        m.defused = True
        room.say({"kind": "event", "text": f"Module {index + 1} defused!"})
        if all(x.defused for x in room.modules):
            end_game(room, "escaped", "All modules defused. Device neutralized.")
    else:
        room.strikes += 1
        room.say({"kind": "event", "text": f"Strike {room.strikes} of {config.MAX_STRIKES}!", "strike": True})
        if room.strikes >= config.MAX_STRIKES:
            end_game(room, "boom", "Three strikes. Detonation!")


def clean_glosses(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = [str(g).strip().lower()[:MAX_GLOSS_LEN] for g in raw[:MAX_SIGNS]]
    return [g for g in out if g]


async def relay_rtc(room: Room, me: Player, data) -> None:
    """Pass WebRTC set-up messages (offer, answer, ICE candidates) to the other player.

    Only these small text messages go through the server. The video itself flows
    browser to browser, so the server never receives or stores a webcam frame.
    """
    if not isinstance(data, dict) or len(json.dumps(data)) > MAX_RTC_BYTES:
        return
    for p in room.players.values():
        if p.pid != me.pid and p.ws is not None:
            try:
                await p.ws.send_json({"type": "rtc", "data": data})
            except Exception:
                p.ws = None


async def handle(room: Room, me: Player, msg: dict):
    kind = msg.get("type")
    if me.pid not in room.players:
        return  # this player left; ignore what the closing socket still sends
    if kind == "leave":
        leave(room, me)
    elif kind == "rtc":
        await relay_rtc(room, me, msg.get("data"))
        return  # no state change, so no broadcast
    elif kind == "role" and room.phase == "lobby":
        role = msg.get("role")
        if role in ROLES and not room.role_taken(role, me.pid):
            me.role = role
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
        back_to_lobby(room)
    elif kind == "exit" and room.phase == "playing":
        back_to_lobby(room, f"{me.name} ended the game.")
    else:
        return
    await broadcast(room)


# ---------------------------------------------------------------------------
# HTTP + WebSocket routes
# ---------------------------------------------------------------------------
@app.api_route("/", methods=["GET", "HEAD"])  # Render probes the port with HEAD
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/healthz")
def healthz():
    """For the host's health check (render.yaml)."""
    return {"ok": True, "rooms": len(rooms)}


@app.get("/api/ice")
async def ice():
    """STUN/TURN servers for WebRTC. TURN logins come from Metered when etc/.env has
    METERED_APP and METERED_API_KEY; the API key itself never reaches the browser."""
    return await ice_servers()


@app.get("/api/manual")
def manual():
    return all_pages()


@app.get("/api/icons")
def icons():
    return json.loads(config.ICONS_FILE.read_text(encoding="utf-8"))


@app.post("/api/rooms")
def create_room():
    prune_rooms()
    if len(rooms) >= MAX_ROOMS:
        raise HTTPException(503, "The server is full. Try again later.")
    while True:
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(4))
        if code not in rooms:
            break
    rooms[code] = Room(code)
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
        if room.players:  # replaces an old "... left the room." note in the lobby
            room.say({"kind": "event", "text": f"{name} joined."})
        me = Player(uuid.uuid4().hex, name)
        room.players[me.pid] = me
    elif me.ws is not None:
        try:  # same player opened a second tab: the newest tab wins
            await me.ws.close()
        except Exception:
            pass
    me.ws = ws
    room.last_seen = time.monotonic()
    await ws.send_json({"type": "welcome", "pid": me.pid})
    await broadcast(room)
    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict):
                room.last_seen = time.monotonic()
                await handle(room, me, msg)
    except (WebSocketDisconnect, ValueError, RuntimeError):
        pass
    finally:
        # Rooms stay in memory after everyone leaves, so a page reload can rejoin.
        # prune_rooms() forgets them ROOM_IDLE_S later.
        room.last_seen = time.monotonic()
        if me.ws is ws:
            me.ws = None
            await broadcast(room)


def main():
    import uvicorn

    ap = argparse.ArgumentParser()
    # HOST / PORT env vars: cloud hosts (Render, Fly) tell the app which port to use this way.
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                    help="use 0.0.0.0 so other laptops on the Wi-Fi can join")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument("--debug", action="store_true", help="enable the answer key at /api/rooms/<code>/answer-key")
    ap.add_argument("--https", action="store_true",
                    help="serve HTTPS with a self-signed certificate (browsers allow the camera only on "
                         "localhost or HTTPS, so a second laptop needs this)")
    a = ap.parse_args()
    app.state.debug = a.debug
    ssl = {}
    if a.https:
        from escape_pod.web.tls import ensure_cert

        cert, key = ensure_cert()
        ssl = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
    scheme = "https" if a.https else "http"
    if a.host == "0.0.0.0":
        from escape_pod.web.tls import lan_ips

        for ip in lan_ips():
            print(f"Other players on this Wi-Fi: {scheme}://{ip}:{a.port}", flush=True)
        if not a.https:
            print("Note: browsers block the camera on http://<ip>. Add --https for video between laptops.", flush=True)
    uvicorn.run(app, host=a.host, port=a.port, **ssl)


if __name__ == "__main__":
    main()
