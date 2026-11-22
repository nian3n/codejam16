# Solo Game with a Bot HQ: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One player can play a full game alone. The player signs to a scripted bot that sits in the HQ seat.

**Architecture:** `HqBot` in `brain/hq_bot.py` is a pure state machine. It turns signed glosses into an English reply. It uses the rule engine and `phrase()`, and it never reads the bomb. `server.py` gets solo rooms: one human defuser and a bot that is not in `room.players`. The client adds a "Play solo" button, a solo lobby, a camera that runs without a peer connection, and the "I need help with:" and "Here is what I see:" frames over the existing sign chips.

**Tech Stack:** Python 3.11, FastAPI WebSockets, pytest with TestClient. Vanilla ES modules (no build step). Node for `node --check`. Playwright (msedge) for one e2e check.

**Spec:** `docs/superpowers/specs/2026-11-21-solo-bot-hq-design.md`. The project spec is `CLAUDE.md`.

## Global Constraints

- The branch is `solo-bot`. It starts from `game-signs` (commit 5fec87d). Do not merge or push.
- Every new source file starts with an Owner line. For `brain/`, use `# Owner: Teammate 4 (Puzzles and brain)`. For web files, keep the existing line.
- The bot never reads `room.modules` facts. It gets only the glosses and the result of each action (spec rule 3).
- The WebSocket messages only gain fields. `signs` and `say` keep their shape (CLAUDE.md §4.2).
- No blocking work in the event loop (rule 6). `HqBot.reply` is pure and fast, so the server calls it inline.
- Use `uv run`, never pip. Before you run uv, stop any running `escape-pod` process (`Stop-Process -Name escape-pod`), because Windows locks the exe.
- Check each changed JS file with `node --check --input-type=module < file`.
- Write commit messages, `.md` text and user-facing text in STE: short sentences, active voice, no semicolons and no contractions. End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Use the English word for each gloss in replies: `phrase.word(g, spec)` (for example, `frenchfries` becomes "french fries", and digits stay as they are).

## Review Focus

1. **Core signs in answers.** A player can sign YES or FINISH among the items, or NO in a round that is not the switches round. The bot must ignore core words in the vote and the count, except NO alone in the switches round 2. Covered by `test_core_words_are_ignored_outside_switches`.
2. **Repeated words.** The recognizer can give DOG twice. Round 1 needs `n` *different* words, and the bot must say so. Covered by `test_round1_needs_n_different_words`.
3. **A strike or a defuse before any instruction.** The player can click the bomb before the bot answers. Then `on_result` must return `None` and must not change the stage. Covered by `test_result_without_an_instruction_is_silent`.
4. **A second person joins a solo room** through its invite link. The server must refuse them. Covered by `test_solo_room_refuses_a_second_player`.
5. **Play again.** After "Back to the lobby" and Start, the new game must have a new bot at round 0, not the old page. Covered by `test_solo_again_starts_a_fresh_bot`.

---

### Task 1: The bot (`HqBot`)

**Files:**
- Create: `src/brain/__init__.py` (Owner line only)
- Create: `src/brain/hq_bot.py`
- Test: `tests/test_hq_bot.py`

**Interfaces:**
- Consumes: `engine.load_pool() -> dict[str, PuzzleSpec]`, `engine.Module(spec, facts)`, `Module.solution() -> Action`, `phrase.phrase(action, module) -> str`, `phrase.word(g, spec) -> str`, `engine.draw(rng, level)`, `config.LEVELS`.
- Produces:
  - `class HqBot` with `__init__(self, pool: dict[str, PuzzleSpec] | None = None)`. The default is `load_pool()`.
  - `stage -> Literal["module", "details"]` (property).
  - `page -> PuzzleSpec | None` (the open page, or `None` at round 0).
  - `greeting() -> str`.
  - `reply(glosses: list[str]) -> str`.
  - `on_result(defused: bool) -> str | None`.
  - Constants: `BOT_NAME = "HQ bot"`, `CORE = {"yes", "no", "finish"}`.

**State:** `page`, `round` (1 or 2), `facts` (the partial facts), and `last` (the spec of the last page that got an instruction, or `None`).

**Copy (exact).** `{title}` is `spec.title`, and `{n}` is `spec.setup["shown"]`. `{items}` per widget: wires "wire colors", keypad "numbers", icons "pictures", dial "pictures", switches "switch labels", big_button "faces".

| Where | Text |
|---|---|
| greeting | "HQ here. Which module do you need help with? Sign one thing you see on it." |
| round 0, no match | "I do not know that word. Sign one thing from the module again." |
| round 0, tie | "Is it the {title A} or the {title B}? Sign one more thing from the module." (titles in pool order) |
| page opened | "That is the {title}. {question}" |
| wires Q1 | "Sign the wire colors, top to bottom." |
| keypad Q1 | "Sign the {n} numbers on the display, left to right." |
| icons Q1 | "Sign the {n} pictures, left to right, top row first." |
| dial Q1 | "Sign the {n} pictures, clockwise from the top." |
| dial Q2 | "Which picture does the needle point at?" |
| switches Q1 | "Sign the switch labels, left to right." |
| switches Q2 | "Now sign only the switches that are on. Sign NO if none is on." |
| big_button Q1 | "Sign the faces in the order the screen shows them." |
| round 1, wrong count | "I need {n} different {items}. You signed {k}. Sign all {n} again." |
| no word from the page, no other page | "I did not see any {items} from the {title}. {question}" |
| dial Q2 bad | "Sign the one picture that the needle points at." |
| switches Q2 bad | "Sign only the switches that are on, or NO if none is on." |
| instruction | "{recast} {phrase(solution, module)}" |
| defuse | "Good work. Which module is next? Sign one thing you see on it." |
| strike | "That was a strike. Check the {title} again. {Q1}" |

**Recast** joins `word(g, spec)` values with ", ". Formats: icons, wires, keypad and big_button: "You see: red, blue, green, white." Dial: "You see: apple, pizza, nuts, carrot. The needle points at pizza." Switches: "You see: lamp (on), bed (off), chair (off), tv (on)."

**Reply algorithm:**
1. Lowercase and strip the glosses. Drop the empty ones.
2. Words that map to a page, in order, are `items`. Drop the core words, except for step 5.
3. **Round 0:** vote over `items` by page. Most words wins. Then open that page at round 1.
4. **Details stage:**
   - Keep the words of `items` that are in `page.pool`.
   - **Module change:** none is in the pool, and `items` is not empty. Treat the message as round 0.
   - None is in the pool, and `items` is empty: send "I did not see any…".
5. In the **switches round 2**, if the raw glosses are exactly `["no"]`, every switch is off.
6. When the facts are complete:
   - Build `Module(page, facts)` and reply with the instruction.
   - Set `last = page`, then go back to round 0.
- Facts keys per widget: `colors`, `display`, `icons`, `options` + `needle`, `switches: [{label, state}]`, `faces`.

- [ ] **Step 1: Write the failing tests in `tests/test_hq_bot.py`**

```python
def signs_for(module) -> list[list[str]]:
    """The messages a perfect player sends after round 0, from module.facts."""

def test_every_puzzle_gives_the_engine_instruction():
    # For every spec in load_pool() and seeds 0..49: Module(spec, widget.generate(spec, rng)).
    # bot.reply([first item]) must start with f"That is the {spec.title}."
    # Then send signs_for(module) one by one. The last reply must end with
    # phrase(module.solution(), module), and bot.stage must be "module".

def test_unknown_word_and_tie():
    assert bot.reply(["hello"]) == "I do not know that word. Sign one thing from the module again."
    assert bot.reply(["cat", "red"]).startswith("Is it the Animal panel or the Wire panel?") or \
           bot.reply(["cat", "red"]).startswith("Is it the Wire panel or the Animal panel?")
    assert bot.stage == "module"

def test_round1_needs_n_different_words():
    bot.reply(["cat"])
    assert bot.reply(["cat", "dog", "dog", "cow"]) == "I need 4 different pictures. You signed 3. Sign all 4 again."

def test_dial_asks_for_the_needle_and_checks_it():
    # senses: options [see, hear, taste, smile]. A needle "look" (not among them) -> "Sign the one picture that the needle points at."
    # A needle "hear" -> an instruction that ends with phrase(Module(senses, facts).solution(), ...)

def test_switches_on_and_no():
    # home_things labels [lamp, bed, tv, chair], round 2 ["no"] -> every state "off" in the recast.
    # Round 2 ["lamp", "tv"] -> "lamp (on)" and "tv (on)" in the recast.

def test_core_words_are_ignored_outside_switches():
    bot.reply(["yes", "cat"]); assert bot.page.id == "pets_farm"
    assert "You see: cat, dog, cow, pig." in bot.reply(["cat", "finish", "dog", "cow", "pig"])

def test_module_change_in_details():
    bot.reply(["cat"])
    assert bot.reply(["red"]).startswith("That is the Wire panel.")

def test_wrong_sign_gives_the_instruction_for_the_signed_facts():
    # The true module has cow. The player signs horse instead. The reply equals the
    # instruction for Module(pets_farm, {"icons": signed}), not for the true module.

def test_strike_reopens_the_last_page_and_defuse_goes_back():
    # After an instruction: on_result(False) == "That was a strike. Check the Animal panel again. Sign the 4 pictures, left to right, top row first."
    # bot.stage == "details" and bot.page.id == "pets_farm".
    # After the next instruction: on_result(True) starts with "Good work." and bot.stage == "module".

def test_result_without_an_instruction_is_silent():
    assert HqBot().on_result(False) is None
```

- [ ] **Step 2: Run the tests and make sure they fail.**
Run: `uv run pytest tests/test_hq_bot.py -q`
Expected: FAIL with `ModuleNotFoundError: brain`.

- [ ] **Step 3: Implement `HqBot` in `src/brain/hq_bot.py`.** Follow the algorithm and the copy above. Put the per-widget questions, the `{items}` nouns and the fact builders in one dict keyed by widget, not in an if-chain. The engine keeps the fact keys.

- [ ] **Step 4: Run the tests and make sure they pass.**
Run: `uv run pytest tests/test_hq_bot.py -q`
Expected: all pass. Then run `uv run pytest -q`. Expected: no failures.

- [ ] **Step 5: Commit.**
```bash
git add src/brain tests/test_hq_bot.py docs/superpowers
git commit -m "Bot HQ: a scripted HQ that reads the signs and gives the instruction"
```

### Task 2: Solo rooms on the server

**Files:**
- Modify: `src/web/server.py` (`Room`, `view`, `start_game`, `handle`, `act` callers, `create_room`, `ws_room`)
- Modify: `CLAUDE.md` §4.2 (new fields)
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `HqBot`, `HqBot.reply`, `HqBot.on_result`, `HqBot.greeting`, `HqBot.stage`, `BOT_NAME` from Task 1.
- Produces:
  - `POST /api/rooms` takes an optional JSON body `{"solo": true}` and returns `{"code"}`.
  - The state gets `"solo": bool` (always) and `"bot_stage": "module" | "details"` (solo rooms in play only).
  - Bot messages are chat entries `{"kind": "say", "from": "HQ bot", "text": ...}`.

**Behavior:**
- `Room` gets `solo: bool = False` and `bot: HqBot | None = None`.
- `can_start()` in a solo room: phase lobby and one defuser.
- `ws_room`: the first player in a solo room gets `role = "defuser"` at once. A second new player gets the error "This is a solo room." and the socket closes.
- `handle`: in a solo room, ignore `role` and `say`.
  - On `signs`, record the signs first. Then record the bot's reply as a `say` from `BOT_NAME`.
- `start_game`: in a solo room, set `room.bot = HqBot()`. Record `bot.greeting()` as a `say` after the "armed" event.
- After `act()` in a solo room, the server must know the result:
  - `act` returns `bool | None`: `True` defused, `False` strike, `None` ignored.
  - If the game is still `playing` and `on_result(...)` returns text, record it.
- `back_to_lobby` sets `room.bot = None`.

- [ ] **Step 1: Write the failing tests in `tests/test_server.py`**

```python
def _start_solo(level="beginner"):
    code = client.post("/api/rooms", json={"solo": True}).json()["code"]
    a = _join(code, "Ana")
    s = _drain(a, lambda s: s["solo"] and s["me"]["role"] == "defuser" and s["can_start"])
    a.send_json({"type": "level", "level": level}); a.send_json({"type": "start"})
    return code, a, _drain(a, lambda s: s["phase"] == "playing")

def test_solo_room_starts_with_one_player_and_greets():
    # state["chat"][-1] == {"kind": "say", "from": "HQ bot", "text": HqBot().greeting(), ...}; state["bot_stage"] == "module"

def test_solo_bot_answers_signs():
    # Sign bomb[0]'s first item -> last chat entry is a say from "HQ bot" starting with "That is the {title}."
    # and bot_stage == "details".

def test_solo_full_game_reaches_escaped():
    # For each module in state["bomb"]: sign round 0 and the detail rounds from its facts
    # (reuse signs_for from test_hq_bot via a module built from the bomb entry), then send
    # the act for server.rooms[code].modules[i].solution(). Final phase == "escaped".

def test_solo_room_refuses_a_second_player():
    # A second _join-like connect gets {"type": "error", "text": "This is a solo room."}

def test_solo_again_starts_a_fresh_bot():
    # Open a page (sign one item), send {"type": "exit"} to go back to the lobby, then start again.
    # The new state has bot_stage == "module", and the last chat entry is the greeting.

def test_two_player_rooms_are_unchanged():
    # _start_game() state has solo False and no "bot_stage".
```

- [ ] **Step 2: Run them and make sure they fail.**
Run: `uv run pytest tests/test_server.py -q -k solo`
Expected: FAIL (`KeyError: 'solo'`).

- [ ] **Step 3: Implement the behavior above in `server.py`.** `create_room` reads the body with an optional `Body(None)` dict, so the old no-body POST still works.

- [ ] **Step 4: Run the tests and make sure they pass.**
Run: `uv run pytest -q`
Expected: no failures.

- [ ] **Step 5: Update CLAUDE.md §4.2.** Document:
  - the `{"solo": true}` body on `POST /api/rooms`
  - the `solo` and `bot_stage` state fields
  - the "HQ bot" `say` entries

- [ ] **Step 6: Commit.**
```bash
git add src/web/server.py tests/test_server.py CLAUDE.md
git commit -m "Server: solo rooms with the bot in the HQ seat"
```

### Task 3: The solo game in the browser

**Files:**
- Modify: `src/web/static/index.html` (home button)
- Modify: `src/web/static/app.js` (button handler)
- Modify: `src/web/static/lobby.js` (solo lobby)
- Modify: `src/web/static/rtc.js` (camera with no peer)
- Modify: `src/web/static/game_signs.js` (frame line)
- Modify: `src/web/static/style.css` (frame line style)
- Modify: `CLAUDE.md` §8 and §10
- Test: `C:\Users\dty47\AppData\Local\Temp\claude\081b90d764f0526e\8f231284-7ed7-457c-be0f-ac8a16b2483e\scratchpad\solo_e2e.py` (Playwright, not committed)

**Interfaces:**
- Consumes: the `solo`, `bot_stage` and `say` entries from Task 2, and `POST /api/rooms {"solo": true}`.

**Behavior:**
- **Home:** add a button `#create-solo` with the text "Play solo (bot HQ)", under "Create a room". It posts `{"solo": true}`, then calls `connect(code)`.
- **Lobby, when `s.solo` is true:**
  - Hide `.roles`, `#copy-link` and `#lobby-video`.
  - The hint reads "Solo game: you are the field agent. A bot plays HQ. Pick a level and start."
- **rtc.js `onRoomState`:** when `s.solo` is true:
  - Call `startCamera(false)` once, with no peer connection.
  - Do not show the "Waiting for the other player..." status.
  - Hide the remote video. Keep the self-view.
  - `localCameraVideo()` must then return the self-view element.
- **game_signs.js:** in a solo room, show a line `#sign-frame` above the chips:
  - "I need help with:" when `bot_stage` is "module"
  - "Here is what I see:" when `bot_stage` is "details"
  - `renderSignChips()` updates it.
- **Feed:** no change. A `say` from "HQ bot" already renders as "HQ bot (HQ)".

- [ ] **Step 1: Make the changes above.** Then run `node --check --input-type=module < <file>` for each changed JS file.
Expected: no output from any of them.

- [ ] **Step 2: Write `solo_e2e.py` in the scratchpad.** Use Playwright with msedge headless and a fake camera (`--use-fake-device-for-media-stream`). Start `uv run ksne --port 8099` first. The script does these steps:
  1. Click `#create-solo`.
  2. Check that `.roles` is hidden.
  3. Click `#start`.
  4. Check that `#sign-frame` reads "I need help with:".
  5. Open "No camera? Type the signs instead". Type the first pool word of `state.bomb[0]` and press Enter. Click `#send-signs`.
  6. Check that the feed shows "HQ bot (HQ)" with "That is the".
  7. Check that `#sign-frame` reads "Here is what I see:".

- [ ] **Step 3: Run it.**
Run: `uv run python <scratchpad>\solo_e2e.py`
Expected: it prints `OK`, and the console shows no page errors.

- [ ] **Step 4: Update CLAUDE.md.**
  - §8: the scripted bot HQ (`brain/hq_bot.py`) is the first version of the bot seat. The LLM alien can later reword its replies.
  - §10: the Home screen has a "Play solo (bot HQ)" button.
  - §10: the solo lobby has only the level picker and Start.
  - §10: in a solo game, the sign composer shows "I need help with:" and "Here is what I see:".

- [ ] **Step 5: Run the full suite.** Run `uv run pytest -q`. Expected: no failures.

- [ ] **Step 6: Commit.**
```bash
git add src/web/static CLAUDE.md
git commit -m "Solo game in the browser: Play solo button, solo lobby, sign frames"
```
