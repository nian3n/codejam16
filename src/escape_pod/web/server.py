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
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Literal

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from escape_pod import config
from escape_pod.brain.hq_bot import BOT_NAME, HqBot
from escape_pod.brain.hq_voice import mood, nervous
from escape_pod.manual.build import all_pages
from escape_pod.manual.solve import sheet_markdown
from escape_pod.puzzles.engine import Module, draw
from escape_pod.puzzles.models import Action
from escape_pod.web.ice import ice_servers
from escape_pod.web.mission import Mission
from escape_pod.web.practice import router as practice_router, warm_model

STATIC = config.STATIC_DIR
CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O, so codes are easy to read aloud
ROLES = ("defuser", "expert")
MAX_SIGNS, MAX_GLOSS_LEN, MAX_TEXT_LEN, MAX_CHAT = 12, 24, 300, 200
MAX_RTC_BYTES = 64_000  # an SDP offer is a few KB; this only stops abuse
ROOM_IDLE_S = 2 * 3600  # forget a room 2 h after its last player left
ARM_TIMEOUT_S = 45.0    # the timer starts even if the agent's browser never says "ready"
COUNTDOWN_S = 3.0       # "ready" starts a 3-2-1 that both players see, then the clock
BOT_DELAY_S = 1.0       # the solo bot "thinks" this long before each reply (tests set 0)
MAX_ROOMS = 1000        # a public server refuses new rooms past this (after pruning)

app = FastAPI(title="Keep Moving and Nobody Explodes")
app.state.debug = False


@app.middleware("http")
async def revalidate_pages(request, call_next):
    """The page and its ES modules: the browser must check each one before it uses a cached copy.

    Without a Cache-Control header, browsers guess a freshness time and may run an old
    module beside a new one after a deploy. One missing export then stops every script
    on the page. no-cache still allows a cheap 304 when the file did not change.
    """
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response
app.mount("/static", StaticFiles(directory=STATIC), name="static")
# Glossary clips (signs/fetch_popsign.py). check_dir=False: a fresh clone without clips still starts.
app.mount("/signs", StaticFiles(directory=config.SIGN_CLIPS_DIR, check_dir=False), name="signs")
app.include_router(practice_router)  # solo practice: score landmark clips with the word model


@dataclass
class Player:
    pid: str
    name: str
    role: str | None = None
    ws: WebSocket | None = None
    practice_credits: set[str] = field(default_factory=set)


@dataclass
class Room:
    code: str
    players: dict[str, Player] = field(default_factory=dict)
    phase: Literal["lobby", "playing", "escaped", "boom"] = "lobby"
    level: str = "intermediate"
    custom_modules: int = 3     # the "custom" level (config.custom_level)
    custom_timer_s: int = 600
    seed: int = 0
    round_id: str | None = None
    mission: Mission | None = None
    signed_modules: set[int] = field(default_factory=set)
    replied_modules: set[int] = field(default_factory=set)
    modules: list[Module] = field(default_factory=list)
    strikes: int = 0
    deadline: float = 0.0
    ended_left: float = 0.0
    timed_out: bool = False
    chat: list[dict] = field(default_factory=list)
    timer_task: asyncio.Task | None = None
    # "Initializing": the clock waits until the agent's browser has loaded the hand tracker
    # and the server has loaded the word model ({"type": "ready"}), or ARM_TIMEOUT_S.
    # The mission gates (case lock, wire tray) open with the clock: they check armed.
    armed: bool = False
    countdown_end: float | None = None  # monotonic time the 3-2-1 ends; None before "ready"
    voice_rng: random.Random = field(default_factory=random.Random)  # the solo bot's nervous words
    timer_s: float = 0.0
    last_seen: float = field(default_factory=time.monotonic)  # for pruning idle rooms
    # Solo: one human (the defuser) and the scripted bot in the HQ seat. The bot is not
    # in `players`, so the video code never waits for a second person.
    solo: bool = False
    bot: HqBot | None = None
    bot_queue: list[Callable[[], str | None]] = field(default_factory=list)  # replies still to give
    bot_task: asyncio.Task | None = None  # set while the bot is "typing"

    def remaining(self) -> float:
        if self.phase == "playing" and not self.armed:
            return self.timer_s
        if self.phase == "playing":
            return max(0.0, self.deadline - time.monotonic())
        return self.ended_left

    def role_taken(self, role: str, by_other_than: str) -> bool:
        return any(p.role == role and p.pid != by_other_than for p in self.players.values())

    def can_start(self) -> bool:
        if self.solo:
            return self.phase == "lobby" and self.role_taken("defuser", "")
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
        "round_id": room.round_id,
        "practice_credits": sorted(me.practice_credits),
        "level": room.level,
        "levels": {**{k: {"modules": l.modules, "timer_s": l.timer_s, "hard": l.allow_hard}
                      for k, l in config.LEVELS.items()},
                   "custom": {"modules": room.custom_modules, "timer_s": room.custom_timer_s, "hard": False,
                              "range": {"modules": config.CUSTOM_MODULES, "timer_s": config.CUSTOM_TIMER_S}}},
        "can_start": room.can_start(),
        "remaining_s": round(room.remaining(), 2),
        "armed": room.armed,
        **({"countdown_s": round(max(0.0, room.countdown_end - time.monotonic()), 2)}
           if room.phase == "playing" and not room.armed and room.countdown_end is not None else {}),
        "timed_out": room.timed_out,
        "strikes": room.strikes,
        "max_strikes": config.MAX_STRIKES,
        "chat": room.chat,
        "debug": app.state.debug,
        "solo": room.solo,
        "bot_name": BOT_NAME,  # the solo handler's name, for the page text
    }
    if room.mission is not None:
        v["mission"] = room.mission.view(me.role)
        if (room.mission.stage != "case_lock"
                and (room.phase in ("escaped", "boom")
                     or (me.role == "defuser" and room.mission.stage == "modules"))):
            # The cut tray remains part of the physical case after its gate.
            v["case_tray"] = {"wires": room.mission.colors, "cuts": room.mission.cuts}
    if room.bot is not None and room.mission is not None and room.mission.stage == "modules":
        v["bot_stage"] = room.bot.stage  # which frame the composer shows: module or details
        v["bot_typing"] = room.bot_task is not None  # the feed shows "…" until the reply
        if room.bot.page is not None and room.bot.page.widget == "keypad":
            # Every keypad question is answered with digits, YES or NO: offer only those,
            # so the recognizer picks among 13 signs, not the whole bomb.
            v["bot_words"] = sorted(set(room.bot.page.pool) | set(config.CORE_SIGNS))
    if room.modules:
        v["progress"] = {"total": len(room.modules), "defused": sum(m.defused for m in room.modules)}
    # Only the defuser sees the bomb. At the end both see it, for the debrief.
    if (room.modules and room.mission is not None and room.mission.stage == "modules"
            and (me.role == "defuser" or room.phase in ("escaped", "boom"))):
        v["bomb"] = [{"id": m.spec.id, "title": m.spec.title, "widget": m.spec.widget,
                      "target_words": m.spec.target_words, "pool": m.spec.pool,
                      "facts": shown_facts(m), "defused": m.defused,
                      "done": [a.to_json() for a in m.done]} for m in room.modules]
    return v


def shown_facts(m) -> dict:
    """The facts the bomb draws. A switch shows the lever where the agent's right clicks
    put it. m.facts keep the start state, because the answer key and solution() read it."""
    if m.spec.widget != "switches" or not m.done:
        return m.facts
    now = {a.target["switch"]: a.target["state"] for a in m.done}
    return {**m.facts, "switches": [{**s, "state": now.get(s["label"], s["state"])} for s in m.facts["switches"]]}


async def broadcast(room: Room):
    for p in list(room.players.values()):
        ws = p.ws
        if ws is None:
            continue
        try:
            await ws.send_json(view(room, p))
        except Exception:
            if p.ws is ws:
                p.ws = None


# ---------------------------------------------------------------------------
# Game flow
# ---------------------------------------------------------------------------
def end_game(room: Room, result: Literal["escaped", "boom"], why: str):
    room.ended_left = room.remaining()
    room.phase = result
    room.say({"kind": "event", "text": why})
    stop_bot(room)  # no "…" and no late reply after the end
    if room.timer_task and room.timer_task is not asyncio.current_task():
        room.timer_task.cancel()
    room.timer_task = None


def expire_if_due(room: Room) -> bool:
    if room.phase != "playing" or not room.armed or room.remaining() > 0:
        return False
    room.timed_out = True
    end_game(room, "boom", "Time ran out. Detonation!")
    return True


def arm(room: Room) -> None:
    """Start the clock."""
    room.armed = True
    room.deadline = time.monotonic() + room.timer_s


def start_countdown(room: Room) -> None:
    """The agent is ready: count 3-2-1, so nobody is caught out when signing goes live."""
    if COUNTDOWN_S <= 0:  # no count configured (the tests): start the clock now
        arm(room)
    elif room.countdown_end is None:
        room.countdown_end = time.monotonic() + COUNTDOWN_S


async def watch_timer(room: Room):
    waited = 0.0
    while room.phase == "playing" and not room.armed:
        await asyncio.sleep(0.05)
        waited += 0.05
        if room.phase != "playing" or room.armed:
            break
        if room.countdown_end is None and waited >= ARM_TIMEOUT_S:
            start_countdown(room)
            await broadcast(room)
        elif room.countdown_end is not None and time.monotonic() >= room.countdown_end:
            arm(room)
            await broadcast(room)
    while room.phase == "playing":
        await asyncio.sleep(min(0.25, room.remaining()))
        if expire_if_due(room):
            await broadcast(room)


def room_level(room: Room) -> config.Level:
    if room.level == "custom":
        return config.custom_level(room.custom_modules, room.custom_timer_s)
    return config.LEVELS[room.level]


def start_game(room: Room):
    level = room_level(room)
    room.seed = random.randrange(1_000_000)
    rng = random.Random(room.seed)
    room.modules = draw(rng, level)
    room.mission = Mission.draw(rng)
    room.round_id = uuid.uuid4().hex
    room.signed_modules.clear()
    room.replied_modules.clear()
    room.strikes = 0
    room.chat = []
    room.phase = "playing"
    room.timer_s = float(level.timer_s or 600)
    room.armed = False  # the clock starts after {"type": "ready"} and a 3-2-1 (see arm)
    room.countdown_end = None
    room.ended_left = 0.0
    room.timed_out = False
    room.say({"kind": "event", "text": f"The bomb is armed: {len(room.modules)} modules. Good luck!"})
    if room.solo:
        room.bot = HqBot()  # a fresh bot per game: no page from the last game
        bot_say(room, room.bot.case_lock_prompt())
    room.timer_task = asyncio.create_task(watch_timer(room))


def back_to_lobby(room: Room, why: str | None = None):
    """Stop any game and return the room to the lobby. Roles stay as they are."""
    if room.timer_task:
        room.timer_task.cancel()
    room.timer_task = None
    room.phase, room.modules, room.chat, room.strikes = "lobby", [], [], 0
    room.round_id = None
    room.armed = False
    room.countdown_end = None
    room.ended_left = 0.0
    room.timed_out = False
    room.mission = None
    stop_bot(room)
    room.bot = None
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


def bot_say(room: Room, text: str) -> None:
    # The bot's sentence stays word for word; hq_voice only adds nervous words around it.
    level = mood(room.strikes, room.remaining(), room.timer_s or 1.0)
    room.say({"kind": "say", "from": BOT_NAME, "text": nervous(text, level, room.voice_rng)})


def bot_later(room: Room, answer: Callable[[], str | None]) -> None:
    """Queue one bot reply. It comes BOT_DELAY_S later, in order, like a person typing.

    The bot's state moves only when the reply is given, so bot_stage and the reply
    always match, and signs sent while the bot "types" queue behind it.
    """
    room.bot_queue.append(answer)
    if room.bot_task is None:
        room.bot_task = asyncio.create_task(_bot_worker(room, room.bot))


async def _bot_worker(room: Room, bot: HqBot | None) -> None:
    while room.bot_queue:
        await asyncio.sleep(BOT_DELAY_S)
        if room.bot is not bot or room.phase != "playing":
            room.bot_queue.clear()
            break
        text = room.bot_queue.pop(0)()
        if text:
            bot_say(room, text)
        if not room.bot_queue:
            room.bot_task = None
        await broadcast(room)
    room.bot_task = None


def stop_bot(room: Room) -> None:
    room.bot_queue.clear()
    if room.bot_task and room.bot_task is not asyncio.current_task():
        room.bot_task.cancel()
    room.bot_task = None


def strike(room: Room) -> None:
    room.strikes += 1
    room.say({"kind": "event", "text": f"Strike {room.strikes} of {config.MAX_STRIKES}!", "strike": True})
    if room.strikes >= config.MAX_STRIKES:
        end_game(room, "boom", "Three strikes. Detonation!")


def act(room: Room, index: int, action: Action) -> bool | None:
    """True: defused. False: a strike. None: nothing to judge yet (the module was already
    defused, or the click was a right step of a longer answer, see Module.apply)."""
    m = room.modules[index]
    if m.defused:
        return None
    result = m.apply(action)
    if result == "step":
        return None
    ok = result == "defused"
    if ok:
        m.defused = True
        # A solved module confirms the outcome of a signed clue and the handler's reply.
        if room.solo or index in room.replied_modules:
            credit = f"{room.round_id}:{index}"
            for player in room.players.values():
                if player.role in ROLES:
                    player.practice_credits.add(credit)
        room.say({"kind": "event", "text": f"Module {index + 1} defused!"})
        if all(x.defused for x in room.modules):
            end_game(room, "escaped", "All modules defused. Device neutralized.")
    else:
        strike(room)
    return ok


def clean_glosses(raw) -> list[str]:
    if not isinstance(raw, list):
        return []
    out = [str(g).strip().lower()[:MAX_GLOSS_LEN] for g in raw[:MAX_SIGNS]]
    return [g for g in out if g]


def handle_gate(room: Room, mission: Mission, me: Player, msg: dict) -> bool:
    revision = msg.get("mission_revision")
    if (not room.armed or msg.get("round_id") != room.round_id
            or type(revision) is not int or revision != mission.revision):
        return False
    stage = mission.stage
    if msg["type"] == "signs":
        previous_digits = mission.lock_confirmed
        glosses = mission.confirm(clean_glosses(msg.get("glosses")))
        if glosses:
            room.say({"kind": "signs", "from": me.name, "glosses": glosses, "mission_stage": stage})
        if stage == "case_lock":
            for slot in range(previous_digits, mission.lock_confirmed):
                me.practice_credits.add(f"{room.round_id}:case_lock:{slot}")
            if mission.stage == "wire_tray":
                room.say({"kind": "event", "text": "Case unlocked. The wire tray is open."})
                if room.bot is not None:
                    bot_say(room, room.bot.wire_tray_prompt(mission.position_order[0]))
            return True
        if not glosses:
            return True
        # Pass the next position to the existing cut check. It compares the
        # confirmed color against that wire and applies the same strike rules.
        index = mission.wire_order[len(mission.cuts)]
    else:
        index = msg.get("wire")
        if (stage != "wire_tray" or type(index) is not int
                or not 0 <= index < len(mission.colors) or index in mission.cuts):
            return False

    outcome = mission.cut(index)
    if outcome == "strike":
        strike(room)
    elif outcome == "cut":
        me.practice_credits.add(f"{room.round_id}:wire_tray:{index}")
        if mission.stage == "modules":
            room.say({"kind": "event", "text": f"Tray cleared. {len(room.modules)} modules are ready."})
            if room.bot is not None:
                bot_say(room, room.bot.greeting())
        elif room.bot is not None:
            bot_say(room, room.bot.wire_tray_prompt(mission.position_order[len(mission.cuts)]))
    return True


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
    if kind == "practice_saved":
        credits = msg.get("credits")
        if isinstance(credits, list):
            # Until the browser confirms storage, a reconnect can replay these credits.
            me.practice_credits.difference_update(credit for credit in credits if isinstance(credit, str))
        return
    if kind in ("signs", "wire_cut", "act", "say", "exit") and expire_if_due(room):
        await broadcast(room)
        return
    mission = room.mission
    if kind == "leave":
        leave(room, me)
    elif kind == "rtc":
        await relay_rtc(room, me, msg.get("data"))
        return  # no state change, so no broadcast
    elif kind == "role" and room.phase == "lobby" and not room.solo:
        role = msg.get("role")
        if role in ROLES and not room.role_taken(role, me.pid):
            me.role = role
    elif kind == "level" and room.phase == "lobby" and msg.get("level") in config.LEVELS:
        room.level = msg["level"]
    elif kind == "level" and room.phase == "lobby" and msg.get("level") == "custom":
        # Optional "modules" and "timer_s"; a value out of range (or not an int) is ignored.
        n, t = msg.get("modules"), msg.get("timer_s")
        lo, hi = config.CUSTOM_MODULES
        if type(n) is int and lo <= n <= hi:
            room.custom_modules = n
        lo, hi = config.CUSTOM_TIMER_S
        if type(t) is int and lo <= t <= hi:
            room.custom_timer_s = t
        room.level = "custom"
    elif kind == "start" and room.can_start():
        start_game(room)
    elif (kind in ("signs", "wire_cut") and room.phase == "playing" and me.role == "defuser"
          and mission is not None and mission.stage != "modules"):
        if not handle_gate(room, mission, me, msg):
            return
    elif kind == "signs" and room.phase == "playing" and me.role == "defuser":
        if "mission_revision" in msg or msg.get("round_id", room.round_id) != room.round_id:
            return
        glosses = clean_glosses(msg.get("glosses"))
        if glosses:
            room.say({"kind": "signs", "from": me.name, "glosses": glosses})
            if not room.solo:
                signed = set(glosses)
                room.signed_modules.update(
                    i for i, m in enumerate(room.modules)
                    if not m.defused and not signed.isdisjoint(m.widget.items(m.facts))
                )
            if room.bot is not None:
                bot = room.bot
                bot_later(room, lambda: bot.reply(glosses))
    elif kind == "say" and room.phase == "playing" and me.role == "expert" and not room.solo:
        text = str(msg.get("text", "")).strip()[:MAX_TEXT_LEN]
        if text:
            room.say({"kind": "say", "from": me.name, "text": text})
            room.replied_modules.update(room.signed_modules)
            room.signed_modules.clear()
    elif (kind == "act" and room.phase == "playing" and me.role == "defuser"
          and mission is not None and mission.stage == "modules"
          and msg.get("round_id", room.round_id) == room.round_id):
        i = msg.get("module")
        a = msg.get("action")
        if isinstance(i, int) and 0 <= i < len(room.modules) and isinstance(a, dict):
            try:
                action = Action.from_json(a)
            except (KeyError, TypeError, ValueError):
                return
            result = act(room, i, action)
            if room.bot is not None and result is not None and room.phase == "playing":
                bot = room.bot
                bot_later(room, lambda: bot.on_result(result))
    elif kind == "ready" and room.phase == "playing" and me.role == "defuser" and not room.armed:
        start_countdown(room)
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
def create_room(body: dict | None = Body(None)):
    prune_rooms()
    if len(rooms) >= MAX_ROOMS:
        raise HTTPException(503, "The server is full. Try again later.")
    while True:
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(4))
        if code not in rooms:
            break
    rooms[code] = Room(code, solo=bool(isinstance(body, dict) and body.get("solo")))
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
        if room.solo and room.players:
            await ws.send_json({"type": "error", "text": "This is a solo room."})
            await ws.close()
            return
        if len(room.players) >= 2:
            await ws.send_json({"type": "error", "text": "This room already has two players."})
            await ws.close()
            return
        if room.players:  # replaces an old "... left the room." note in the lobby
            room.say({"kind": "event", "text": f"{name} joined."})
        me = Player(uuid.uuid4().hex, name, role="defuser" if room.solo else None)
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
            if me.ws is not ws:
                break
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
    # Load the word model in the background now: it takes about 6 s, and the first sign of
    # the first game would otherwise wait for it.
    threading.Thread(target=warm_model, daemon=True, name="warm-model").start()
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
