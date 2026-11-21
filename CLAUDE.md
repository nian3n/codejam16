# Keep Moving and Nobody Explodes: Project Spec (ASL)

You help a team of 4 build a hackathon game. In the game, two players practice **American Sign Language (ASL)** vocabulary: one player signs to the other through the webcam. Read this whole file before you write code.

- **Change, November 2026:** the game is now a **two-player web app**. The earlier version was a pygame window with one player and an LLM alien. That version is gone. The LLM alien comes back in a later phase (§8).
- Build in the milestone order in §15. Keep the game runnable at every milestone. Keep `uv run pytest` passing.
- Each teammate owns an area (§14). Unless told otherwise, ask which teammate you help. Then edit only that area's files.
- Shared files change only with a heads-up to the team. Add fields, never rename them. The shared files are `src/escape_pod/config.py`, `src/escape_pod/puzzles/models.py`, `src/escape_pod/signs/vocab.json` and the WebSocket messages in §4.2.
- Every source file starts with a `# Owner: Teammate N (Area)` line, or `// Owner: ...` in JavaScript.
- If something here is ambiguous, pick the simplest option that keeps the interfaces in §4. Note it in a code comment, and tell the human.
- Never put API keys in code or in git. They go in `etc/.env` (§12).

---

## 1. The game

The game is inspired by *Keep Talking and Nobody Explodes*. Two players join one room in their browsers. Each player takes one role.

- **Defuser** (on screen: **Field agent**): sees the bomb, but not the manual. Signs what they see to the webcam, one sign at a time. Clicks the bomb to act.
- **Expert** (on screen: **Handler**. The game no longer says "HQ": players did not know it means headquarters): sees the manual, but never the bomb. Reads the signs, finds the page and tells the defuser what to do in English text.

Each game **draws modules from a pool of 20 puzzles**. **Every puzzle teaches a different vocabulary topic** (colors, numbers, animals and so on). Every word in a puzzle is a sign the recognizer knows (§5.1).

One exchange:

1. The defuser **signs the items on one module**, one sign per capture (for example CAT, DOG, COW).
2. The **sign recognizer** (§6) shows its best guesses as chips. The defuser picks the right guess on each chip or deletes it. Typing a sign is the fallback.
3. The confirmed signs (English glosses) go to the expert. The expert's manual highlights the pages that contain those words.
4. The expert reads the rules on that page and types an instruction ("Press the cow.").
5. The defuser **acts** by clicking. The **server checks the action with the rule engine**. A correct action defuses the module. A wrong one is a strike.

The device is neutralized if the players defuse all modules before the timer runs out, with fewer than 3 strikes. Then the players see a round report, and they can play again with a new draw. A full game takes 5 to 10 minutes.

Each puzzle has its own topic, so the signs alone identify the manual page. Signing RED, BLUE, GREEN can only mean the colors puzzle. The defuser does not need to sign words like "wire" or "button".

### Non-negotiable design rules

1. **Code decides right and wrong.** The server's rule engine (§5) decides every action. No client, player or LLM decides success.
2. **One source of truth.** Each puzzle's JSON rules produce both the engine's solution and the manual page.
3. **The expert never gets the bomb's facts** from the server during play. The expert learns only what the defuser signs.
4. **The player confirms every recognized sign** before it goes out. A recognition mistake costs a retry, never a strike.
5. **Learner-friendly failure.** An unclear description gets a question, never a wrong instruction.
6. **Nothing blocks the server's event loop.** Run recognition, retrieval and LLM calls in a worker, and send the results when they are ready.
7. **One topic per puzzle**, and every puzzle word must be recognizable (§13).
8. **Webcam video goes only to the other player, peer to peer (WebRTC).** The game server never receives, relays or stores a frame. It passes only the small set-up messages. No part of the game saves video, unless the player opts in to evaluation recordings.

---

## 2. Tech stack

| Part | Tool |
|---|---|
| Language | Python 3.11+ |
| Packages | `uv` (`pyproject.toml` and `uv.lock`) |
| Server | `fastapi` with WebSockets, run by `uvicorn` |
| Client | plain HTML, CSS and JavaScript ES modules. No build step, no framework |
| Video | WebRTC between the two browsers (`web/static/rtc.js`). Set-up messages go over the game WebSocket |
| Video relay | TURN from Metered Open Relay (free tier), through `/api/ice` (`web/ice.py`). Without Metered keys: STUN only (`config.ICE_SERVERS`) |
| Hosting | Render (free web service) from `render.yaml` and the `Dockerfile`. One instance only, because rooms live in memory |
| HTTPS | the host adds HTTPS. For LAN play, `--https` makes a self-signed certificate (`cryptography`) in `etc/tls/`. Browsers allow the camera only on HTTPS or `localhost` |
| Puzzle models | `pydantic` v2 |
| Icons | emoji placeholders in `assets/icons.json`. Replace them with CC0 PNGs (Kenney) later |
| Landmarks | MediaPipe Holistic (543 landmarks per frame: face, both hands, pose). Where it runs is open (§6.0) |
| Word signs | `sign/kaggle-asl-signs-1st-place` from Hugging Face: `model.tflite` (11.2 MB) + `sign_to_prediction_index_map.json`, 250 signs, MIT license |
| Numbers 0–9 | the ready-made "ASL Landmark MLP" (`nocontextdoruk/asl-landmark-mlp`, CC BY-NC 4.0) on MediaPipe hand landmarks (§6.4). Fallback: our own k-NN on team recordings |
| Retrieval (phase 2) | `sentence-transformers` (`all-MiniLM-L6-v2`), NumPy cosine similarity |
| LLM (phase 2) | provider SDK behind `brain/llm.py`, JSON output checked with `pydantic` |
| Tests | `pytest`, with FastAPI's `TestClient` for WebSocket tests |

- Add a package with `uv add <name>`. Add a test-only package with `uv add --dev <name>`. Do not use `pip` or `requirements.txt`.
- The LLM API key comes from the environment variable named in `config.LLM_API_KEY_ENV`. Put it in `etc/.env`, never in code.
- Credits and licenses are in §17. They must appear in the README and on an in-game credits screen.

---

## 3. Project layout

```
pyproject.toml              uv project: dependencies, commands (§12)
uv.lock                     exact versions (commit it)
README.md                   set up, run, ownership, credits
CLAUDE.md                   this spec
etc/                        secrets. Git ignores everything here except .env.example
  .env.example              copy to etc/.env and fill in
docs/
  manual/                   generated manual pages (uv run build-manual), committed
tests/                      pytest tests
src/escape_pod/
  config.py                 shared: paths, levels, limits, loads etc/.env
  puzzles/                  T4
    models.py               Action, Rule, PuzzleSpec (shared)
    data/*.json             the 20 puzzle files
    engine.py               load_pool, draw, Module, widget logic, rule evaluation
    phrase.py               English wording for instructions and rule conditions
  manual/                   T4
    build.py                rules -> English manual pages (static)
    solve.py                answer key for one drawn bomb (dynamic)
  web/                      T1
    server.py               rooms, roles, game state, timer, checks
    static/
      index.html, style.css
      app.js                entry point: connection, screens
      core.js               helpers and the shared client store
      lobby.js              room code, roles, level, start
      bomb.js               defuser view: bomb casing, timer, module slots
      widgets/              one file per widget, registered in widgets/index.js
      manual_view.js        expert view
      feed.js               messages, sign composer, reply box
  assets/                   T1/T2: icons.json now, PNGs, sounds and fonts later (CC0)
  signs/                    T2 (not built yet): vocab.json, sign animations
  vision/                   T3 (not built yet): see §6.0 for where it goes
  brain/                    T3 + T4 (phase 2): retriever, LLM answer, verify
tools/                      T3 + T4 (not built yet): download, record, train, evals, check_puzzles
models/                     downloaded or trained models, git-ignored
logs/                       session logs, git-ignored
```

Rule of thumb: Python code and the data that the game loads go in `src/escape_pod/`. Files that people read go in `docs/`. Secrets go in `etc/`.

---

## 4. Interfaces (do not change signatures without telling the team)

### 4.1 Python

```python
# escape_pod.puzzles.engine
def load_pool() -> dict[str, PuzzleSpec]: ...
def draw(rng: random.Random, level: Level, weak_topics: set[str] = frozenset()) -> list[Module]: ...

class Module:
    spec: PuzzleSpec
    facts: dict
    defused: bool
    def solution(self) -> Action: ...          # resolved: {"icon": "cow"}, never {"icon": "last"}
    def check(self, action: Action) -> bool: ...
    def apply(self, action: Action) -> str: ...   # one click: "step", "defused" or "strike" (the server uses this)
    def fired_rule(self) -> int: ...           # index of the rule that fires

# escape_pod.puzzles.phrase
def phrase(action: Action, module: Module | None = None, spec: PuzzleSpec | None = None) -> str: ...
#   with module: "Press the cow."   without: "Press the last button." (manual wording)

# escape_pod.manual
def build.all_pages() -> list[dict]: ...      # what /api/manual serves
def solve.sheet_markdown(modules) -> str: ... # answer key

# vision (T3, §6)
@dataclass
class Guess:
    gloss: str          # "cat"
    score: float        # probability among the allowed set, 0..1
def recognize(clip: np.ndarray, allowed: set[str]) -> list[Guess]: ...   # clip: (T, 543, 3) float32, best first
class Segmenter:
    def push(self, frame_landmarks: np.ndarray) -> np.ndarray | None: ... # a finished clip, or None

# brain (phase 2, §7 and §8)
def retrieve(glosses: list[str]) -> list[tuple[str, float]]: ...       # (puzzle_id, score), best first
def answer(glosses: list[str], page_id: str, history: list) -> Answer: ...
def verify(answer: Answer, module: Module) -> Verdict: ...
```

### 4.2 WebSocket messages (`/ws/<CODE>`)

The client sends `{"type": "hello", "name": ..., "pid": ...}` first. The server answers `{"type": "welcome", "pid": ...}`. The client keeps `pid` to rejoin the same seat after a reload.

| Client sends | Who | Phase |
|---|---|---|
| `{"type": "role", "role": "defuser" \| "expert"}` | anyone | lobby |
| `{"type": "level", "level": "beginner" \| "intermediate" \| "advanced"}`, or `{"type": "level", "level": "custom", "modules": 1-5, "timer_s": 60-1200}` (both fields optional, out-of-range values ignored) | anyone | lobby |
| `{"type": "start"}` | anyone, when both roles are taken | lobby |
| `{"type": "signs", "glosses": ["cat", "dog"]}` | defuser | playing |
| `{"type": "say", "text": "Press the dog."}` | expert | playing |
| `{"type": "act", "module": 0, "action": {"verb": "press", "target": {"icon": "dog"}}}` | defuser | playing |
| `{"type": "ready"}`: the agent's hand tracker and the word model are loaded. The server counts 3-2-1 (`countdown_s` in the state), then the clock starts (`armed` becomes true). Without `ready`, the count starts after 45 s | defuser | playing |
| `{"type": "again"}` | anyone | escaped or boom |
| `{"type": "exit"}`: ends the game for both players. Both go back to the lobby with their roles | anyone | playing |
| `{"type": "leave"}`: frees the seat and the role. A running game ends. The last player out deletes the room | anyone | any |
| `{"type": "rtc", "data": {"sid": ..., "description" \| "candidate": ...}}` | anyone | any |

The server forwards an `rtc` message to the other player as `{"type": "rtc", "data": ...}`, without a state broadcast. It drops messages over 64 KB. The state has `me.polite` (exactly one player is polite, for WebRTC "perfect negotiation") and `you: true` on the player's own entry in `players`.

After each change, the server sends each player its own `{"type": "state", ...}`. Only the defuser's state has `bomb` (the modules and their facts), until the game ends. The server ignores any message that is wrong for the sender's role or the phase. It can also send `{"type": "error", "text": ...}`, for example when the room is full.

**Solo rooms:** `POST /api/rooms` with the body `{"solo": true}` makes a room for one player. The player is the defuser at once, and a second player gets the error "This is a solo room." The scripted bot Rob (`brain/hq_bot.py`) takes the handler seat, but it is not in `players`. Its lines are chat entries `{"kind": "say", "from": "Rob", "text": ...}`. They follow each `signs` message and each action that defuses a module or costs a strike. In a solo room, the server ignores `role` and `say`. The state always has `solo` (true or false). In a solo game, it also has `bot_stage`: `"module"` (the bot waits for one item of a module) or `"details"` (the bot waits for the items of the open page).

HTTP: `GET /api/manual`, `GET /api/icons`, `POST /api/rooms` → `{"code"}`, `GET /api/ice` (STUN/TURN servers) and `GET /healthz`. Also `GET /api/rooms/<CODE>/answer-key`, which works only with `--debug`. The server forgets a room 2 hours after its last player leaves.

### 4.3 Shared models

```python
# escape_pod.puzzles.models
@dataclass(frozen=True)
class Action:
    verb: str            # see the widget table in §5.2
    target: dict         # {"color": "blue"}, {"keys": ["4", "7"]}, {"icon": "cow"}

class PuzzleSpec(BaseModel):
    id: str
    title: str
    widget: Literal["wires", "keypad", "icons", "dial", "switches", "big_button"]
    topic: str                       # unique across the pool
    hard: bool = False
    looks_like: str                  # 1-2 sentences for the manual and the index
    pool: list[str]                  # the glosses this puzzle can show (each in signs/vocab.json)
    target_words: Literal["color", "name", "digits", "letters", "position", "state"]
    setup: dict                      # {"shown": 4}
    rules: list[Rule]                # last rule must be an "else"

# escape_pod.brain.models (phase 2)
class Answer(BaseModel):
    page_id: str
    facts: dict
    recast: str          # "You see a cat, a dog, a cow and a pig."
    action: Action
    english: str         # "Press the cow."

class Verdict(BaseModel):
    kind: Literal["ok", "ask_sure", "ask_which", "ask_more", "corrected"]
    english: str | None = None
    field: str | None = None
    action: Action | None = None
    candidates: list[str] = []
```

---

## 5. Puzzles (Teammate 4)

### 5.1 The pool: 20 puzzles, 20 topics

All 20 puzzles exist in `src/escape_pod/puzzles/data/`. Every word is one of the 250 glosses in the sign model's label map, except the digits, which use the handshape classifier (§6.4). In November 2026, the `senses` puzzle replaced the `alphabet` (fingerspelling) puzzle: the game reads digits, not letters. Gloss spellings follow the label map (for example `icecream`, `frenchfries`, `tv`). **Nobody has checked the pools against `sign_to_prediction_index_map.json` yet.** Do that when the model is downloaded.

| id | Topic | Widget | Pool (glosses) |
|---|---|---|---|
| `colors` | Colors | wires | red, blue, green, yellow, black, white, brown, orange |
| `numbers` | Numbers 0–9 | keypad | 0–9 (handshapes) |
| `pets_farm` | Pets and farm animals | icons | cat, dog, cow, pig, horse, duck, hen, donkey |
| `senses` | Senses | dial | see, look, hear, listen, taste, touch, smile, think |
| `wild_animals` | Wild animals | icons | lion, tiger, zebra, giraffe, elephant, alligator, wolf, owl |
| `family` | Family | icons | mom, dad, grandma, grandpa, brother, aunt, uncle |
| `people_jobs` | People and jobs | icons | fireman, police, cowboy, clown, boy, girl, man, child |
| `body` | Body parts | icons | ear, eye, nose, mouth, tooth, tongue, hair, arm, finger, feet |
| `food` | Food | dial | apple, carrot, cereal, pizza, frenchfries, icecream, chocolate, nuts |
| `clothes` | Clothes | icons | hat, shirt, shoe, jacket, jeans, mitten, pajamas, zipper |
| `weather_sky` | Weather and sky | dial | sun, moon, cloud, rain, snow |
| `transport` | Transport | dial | car, boat, airplane, helicopter |
| `feelings` | Feelings | big_button | happy, sad, mad, sleepy, hungry, thirsty, sick |
| `actions` | Actions | icons | jump, dance, sleep, read, cry, kiss, hide, ride |
| `home_things` | Things at home | switches | bed, chair, table, lamp, tv, radio, refrigerator, drawer |
| `places` | Places | switches | bedroom, backyard, pool, store, farm, outside, stairs, closet |
| `toys` | Toys and play | icons | doll, toy, balloon, puzzle, gift |
| `school` | School things | icons | book, pen, pencil, scissors, flag |
| `opposites` | Opposites | switches | up, down, open, close, wet, dry, clean, dirty, loud, quiet |
| `time_words` | Time words | icons | morning, night, now, later, yesterday, tomorrow |

- Hard puzzles: `feelings`, `time_words`.
- Each module shows 4 items from its pool. Keypads show 3, dials show 4–5.
- Instructions name targets with the topic's own words. The colors puzzle says "the blue wire", not "the second wire".
- Signs with motion are fine, because the word model reads whole clips. Only the handshape classifier is limited to still signs. The digits 0–9 are all still signs.

### 5.2 Widgets

The Python side of a widget (`puzzles/engine.py`) has the logic hooks: `generate`, `items`, `derive`, `resolve`. The browser side (`web/static/widgets/<name>.js`) draws the widget and turns clicks into actions.

| Widget | Facts | Derived keys | Verbs |
|---|---|---|---|
| wires | `colors: [..]` | `count`, `first`, `last`, `has:<color>` | `cut {color: c}` or `{wire: "first"\|"last"}`, or several cuts in a row: `{colors: [c1, c2]}` or `{order: "top_down"\|"bottom_up"}` (every wire) |
| keypad | `display: [..]` | `count`, `first`, `last`, `has:<x>`, `display`, `reversed`, `sorted`, `plus_one` | `type {keys: [..]}` or `{keys_from: "display"\|"reversed"\|"sorted"\|"plus_one"}` (`plus_one`: each digit plus 1, 9 becomes 0) |
| icons | `icons: [4 glosses]` | `has:<g>`, `position_of:<g>`, `first`, `last` | `press {icon: g\|"first"\|"last"}`, or two presses in a row: `press {icons: [g1, g2]}`, or `press_all {order: "alpha"\|"reverse"}` (all 4 buttons in alphabetical order, A to Z or Z to A; resolved to `{icons: [..]}`, sent from the panel's ORDER mode) |
| dial | `options: [..]`, `needle: g` | `needle`, `has:<g>`, `first`, `last` | `turn {to: g\|"first"\|"last"\|"alpha_first"\|"alpha_last"}` (the picture that comes first or last in the alphabet) |
| switches | `switches: [{label, state}]` | `count_on`, `state_of:<label>`, `has:<label>` | `set {switch: label\|"first"\|"last", state: "on"\|"off"\|"flip"}`, or `set {all: "on"\|"off"\|"flip"}` (every switch, in any order; resolved with `flips: {label: state}`) |
| big_button | `faces: [..]` | `faces`, `first`, `last`, `has:<g>` | `hold {release_on: g\|"first"\|"last"}` |

- Rules are data: `[derived_key, op, value]` conditions with the ops `== != < <= > >= in`. The conditions in one rule are ANDed. The first rule that matches wins. The last rule is `else`. **No `eval`.** One action per puzzle.
- **Steps:** some actions take several clicks (the lists above). `Widget.steps()` splits the resolved action into clicks. The server checks each click with `Module.apply()`: a right click counts (the state lists them in `done`), a wrong click is a strike and keeps the progress. Order matters for wires and pictures, not for switches.
- `"first"` and `"last"` follow the reading order that the manual prints for each widget. For example, wires go top to bottom and the dial goes clockwise from the top. `resolve()` turns them into the real item, so `solution()` is always concrete.
- `has:<g>` for an item that is not shown is `false`. Any other missing key never matches.
- `first > last` compares the two derived values, not the words.
- The big button's screen cycles the faces all the time, so the defuser can sign them. (The old spec showed them only while the button was held.)

### 5.3 Puzzle file example

```json
{
  "id": "pets_farm",
  "title": "Animal panel",
  "widget": "icons",
  "topic": "pets and farm animals",
  "hard": false,
  "looks_like": "A panel with four buttons, each showing a pet or farm animal.",
  "pool": ["cat", "dog", "cow", "pig", "horse", "duck", "hen", "donkey"],
  "target_words": "name",
  "setup": {"shown": 4},
  "rules": [
    {"if": [["has:cat", "==", true], ["has:dog", "==", true]], "then": {"verb": "press", "target": {"icon": "dog"}}},
    {"if": [["has:cow", "==", true]], "then": {"verb": "press", "target": {"icon": "cow"}}},
    {"else": {"verb": "press", "target": {"icon": "last"}}}
  ]
}
```

### 5.4 Draw rules and manuals

- `draw` uses a seed. It takes the module count and the hard-puzzle limit from the `Level` (§9). It uses at least `min(3, n)` different widgets and at most one hard puzzle. It doubles the weight of `weak_topics`.
- **Static manual:** `manual/build.py` writes one English page per puzzle to `docs/manual/` and serves the same pages at `/api/manual`. Each page has the title, "How to recognize it" (from `looks_like` and the pool), the reading order and the rules in plain English. It uses the same wording helpers as `phrase()`. Run `uv run build-manual` after any rule change, and commit the pages.
- **Answer key:** `manual/solve.py` takes one drawn bomb. For each module, it shows the facts and the signs to make. It marks each condition of each rule yes or no. Then it shows the rule that fires and the exact instruction.

---

## 6. Sign recognition (Teammate 3)

### 6.0 Decision: where recognition runs

**Split.** The browser runs MediaPipe (`static/tracker_worker.js`, a Web Worker) and sends only landmarks to the server. The Python server runs the word model (`src/escape_pod/vision/`, `POST /api/practice/guess`). No video frame leaves the laptop, so rule 8 holds.

**In the game:** `static/game_signs.js` reads frames from the camera that the video call already opened (`rtc.js` `localCameraVideo()`). It uses the same sequence capture as solo practice (§6.2). Each clip goes to `/api/practice/guess?words=<this bomb's words>`. Each clip becomes a chip with the top 3 guesses. The agent picks the right guess or deletes the chip, then presses "Send to <handler name>". That press confirms the signs (rule 4). When the bomb has a keypad, the server mixes in the digit model (§6.4). The game has no typed fallback: the team removed it in November 2026. Signs come from the camera only.

### 6.1 Pipeline

```
webcam (30 fps)
  -> MediaPipe Holistic per frame -> (543, 3) landmarks, NaN where a part is not detected
  -> Segmenter: detects when a sign starts and ends -> clip (T, 543, 3)
  -> word model (TFLite, 250 glosses)  or  handshape classifier (digits)
  -> scores restricted to the allowed glosses -> top 3 guesses
  -> player confirms (sign YES or click) or retries (sign NO)
```

Show the camera mirrored with the hand skeleton drawn on it, so players see what the model sees.

### 6.2 Capturing signs

The player needs both hands to sign, so **do not use hold-to-sign**.

**Sequence capture (built, `static/sequence.js`, practice "Sequence" mode):** one recording holds many signs.

1. Space starts a recording. For 1 s, a banner says "GET YOUR HANDS READY". Then recording starts.
2. The player signs a word, then makes a **separator**. The separator ends the clip and adds no word:
   - **Hands down:** both hands leave the frame or drop below the waist line for 0.3 s. Shorter dropouts are tracking blips and do not end the sign.
   - **The "next" pose:** both hands open, fingers up, held still for 0.5 s. It is our own signal, not an ASL word. A rule on the landmarks detects it, so the model never sees it. No game word looks like it: FINISH shakes two open hands, and the digit 5 is one hand. The glossary lists it under "game controls".
3. After each sign, a 1 s cooldown starts (from when the hands went down). No new sign starts during it, so hands that leave the frame and come straight back give one word, not two. The banner shows "✓ GOT IT". The code cuts the separator frames off each clip. It drops clips under 0.3 s and marks clips over 3 s as "unclear". Hands that fall fast never start a clip.
4. Each clip goes to `POST /api/practice/guess` at once, while the player signs the next word. It becomes a chip with the top 3 guesses. The player picks a guess or deletes the chip.
5. Space stops the recording. `tests/test_sequence.py` runs the logic in Node with synthetic hands.

**Hand tracking in the browser:** `static/tracker_worker.js` runs MediaPipe Tasks `HolisticLandmarker` (tasks-vision 0.10.21) in a classic Web Worker, and `static/tracker.js` is the page side. It returns the old Holistic shape: 468 face points, 33 pose points, 21 per hand. The old `@mediapipe/holistic` library ran on the main thread and froze the page for about 6 s on its first frame. The worker loads in the background when the player opens training. On the PopSign test video it also scored better: CAT, DOG and COW were all top-1.

The older notes:

- **Auto mode (default):** a sign starts when at least one hand is detected and moving above the waist. It ends when the hands drop or stay still for 0.4 s. Ignore clips under 0.3 s or over 3 s.
- **Manual fallback:** press Space (or click) to start a 2.5 s capture window with a visible 3-2-1 countdown.
- After each clip, show the top 3 guesses as chips. Signing **YES** or clicking a chip confirms. Signing **NO** discards. YES and NO are in the model's vocabulary.
- The confirmed signs build up a list on screen. A "Send to expert" button (or signing **FINISH**, also in the vocabulary) sends it.

### 6.3 The word model

`models/islr/model.tflite` and `models/islr/sign_to_prediction_index_map.json`, from `sign/kaggle-asl-signs-1st-place` on Hugging Face. It is the winning solution of Google's Kaggle "Isolated Sign Language Recognition" competition, trained on PopSign data.

The model takes **one clip of MediaPipe Holistic landmarks**, shaped `(frames, 543, 3)` float32 with x, y, z and NaN for undetected parts. It returns 250 scores. The landmark order per frame:

| Rows | Part | Count |
|---|---|---|
| 0–467 | face | 468 |
| 468–488 | left hand | 21 |
| 489–521 | pose | 33 |
| 522–542 | right hand | 21 |

```python
def to_array(results) -> np.ndarray:
    def block(lms, n):
        if lms is None:
            return np.full((n, 3), np.nan, np.float32)
        return np.array([[p.x, p.y, p.z] for p in lms.landmark], np.float32)
    return np.concatenate([
        block(results.face_landmarks, 468),       # refine_face_landmarks=False: 468 points, not 478
        block(results.left_hand_landmarks, 21),
        block(results.pose_landmarks, 33),
        block(results.right_hand_landmarks, 21),
    ])                                            # (543, 3)
```

Check these on day one, and write the results in a `vision/README.md`:

1. The signature names and shapes from `get_signature_list()`.
2. **Mirroring:** run test signs with the raw frame and with a flipped frame. Keep whichever scores better, and still show the mirrored image.
3. **MediaPipe version:** `mp.solutions.holistic` is the older API. Pin a version that still has it, or use the Tasks holistic landmarker if it gives the same 543 points.
4. **Left-handed signers:** add a setting that mirrors the x coordinates and swaps the two hand blocks. Test which works.

**Restrict the choices.** After you get the 250 scores, keep only the `allowed` glosses and softmax over them:

| Level | Allowed set |
|---|---|
| Beginner | the pools of all modules on this bomb, plus core signs (yes, no, finish). Not one module's pool: the defuser never says which module they sign |
| Intermediate | the pools of all modules on this bomb, plus core signs |
| Advanced | all game words (the glossary words) |

Choosing among 10 signs is much more reliable than among 250.

### 6.4 Numbers (handshape classifier)

The word model does not cover numbers. A second, small model reads the digits from one hand's shape.

- **Model (November 2026):** the ready-made "ASL Landmark MLP" (`nocontextdoruk/asl-landmark-mlp` on Hugging Face, CC BY-NC 4.0). It scores 36 still hand shapes (0–9, A–Z) from 21 MediaPipe hand points, trained on the ASL-HG dataset. The game uses only the 10 digit scores. `uv run download-models` gets the ONNX file and converts it once to NumPy weights (`models/digits/asl_mlp.npz`, `vision/digit_mlp.py`). The server needs no ONNX runtime.
- **Features:** the signing hand's 21 points, moved to the wrist and divided by the 3-D length from the wrist to the middle-finger knuckle, as the model card says. The code averages them over the steadiest 5 frames. A left hand is mirrored to a right hand.
- **Mixing:** `rank_mixed` in `vision/recognizer.py`. The word model's probability for the allowed words stays with those words. The rest goes to the digits, split by the digit model. `/api/practice/guess` mixes when the allowed set has digits.
- **Solo:** while the bot is on the keypad page, the state has `bot_words` (the digits and the core signs), and the page offers only those.
- **Fallback:** our own k-NN (`vision/handshape.py`, `uv run record-digits` and `uv run train-digits`) loads only when the downloaded model is missing.
- **Not measured yet:** the model card reports 100 % on its own dataset. Check it with our cameras and hands (§6.5).

### 6.5 Evaluation (`tools/eval_signs.py`)

- Record a test set: every gloss used in the game, 3 takes each, by at least 3 people. At least one person must be from outside the team.
- Report top-1 and top-3 accuracy per gloss for each level's allowed set, plus a confusion list. Swap out glosses that the model often confuses within a pool.
- Report the time from the end of a sign to the guesses on screen. The target is under 300 ms on the demo laptop.

---

## 7. Retrieval (phase 2, `brain/retriever.py`, Teammate 3)

The expert's manual already highlights the pages that contain the signed words (`pagesFor` in `manual_view.js`). Each gloss is in one pool only, so this vote is exact. Embedding retrieval matters only when the LLM alien plays the expert:

- **Index:** for each puzzle, embed `title + looks_like + "Words: " + pool` with `all-MiniLM-L6-v2`. Build the 20 vectors at startup.
- **Query:** the confirmed glosses joined into a string ("cat dog cow pig"). Search all 20 pages.
- **Decision:** best score under `config.RETRIEVAL_MIN_SCORE` → `ask_more`. Top two within `config.RETRIEVAL_MARGIN` → `ask_which`. Otherwise, answer.
- Also compute the vote (the puzzle that owns most glosses). If the vote and the embeddings disagree, trust the vote.

---

## 8. The LLM alien (phase 2, Teammate 4)

**Built first: the scripted bot handler, Rob** (`brain/hq_bot.py`, design in `docs/superpowers/specs/2026-11-21-solo-bot-hq-design.md`). In a solo room, Rob takes the expert seat. It knows only the manual and the signs, never the bomb. The agent signs one item to name the module. The bot then reads the page's rules in order and asks only for the fact that the next rule needs, one question at a time: "Do you see DOG?", "Tell me the color of the top wire.", "Is the LAMP switch on?". The agent answers with YES, NO or an item. When a rule holds, the bot gives the instruction with `phrase()`. It trusts the signs, so a wrong sign gives a wrong instruction. The bot sounds nervous (`brain/hq_voice.py`): it adds a few shaky words around its sentence, and never changes the sentence. The nerves grow after a strike and when time runs low. After a strike, it walks the same page again. The LLM alien can later reword the bot's replies, with the script as the fallback.

- **Answer (`brain/answer.py`):** the system prompt says that the alien reads a defusal manual and gets a list of ASL glosses. The alien uses only the given page. It turns the glosses into facts and restates them in one short English sentence (`recast`). Then it picks the action that the rules give and writes it as one short instruction. The output is JSON that matches `Answer`. One retry on invalid JSON, then `ask_more`.
- **Verify (`brain/verify.py`):** wrong page → `ask_sure`. A fact the rules need is missing → `ask_more`. A fact is wrong → `ask_sure`. Facts match and action equals `module.solution()` → `ok`. Otherwise → `corrected` with `phrase(module.solution(), module)`. **Never show an LLM answer before `verify()`.**
- Log every verdict. "The LLM was right X% of the time before verification" is a pitch metric.
- A `--mock-llm` mode answers from the rule engine, so the game runs with no network.

---

## 9. Learner support

### 9.1 Levels (`config.LEVELS`)

| | Beginner | Intermediate | Advanced |
|---|---|---|---|
| Modules | 3, no hard ones | 4, no hard ones | 4, at most one hard one |
| Timer | 10 min | 5 min | 3 min |
| Recognizer choices | this bomb's words | this bomb's words | all game words |
| Briefing before the bomb | yes, each topic's signs shown and practiced | yes, shown only | no |
| Sign cards beside the camera | yes | no | no |

**Custom level:** the lobby also has a "Custom" card. The players pick 1 to 5 modules and 1 to 20 minutes, in 1-minute steps. All other settings are as at Intermediate (`config.custom_level`, `CUSTOM_MODULES`, `CUSTOM_TIMER_S`).

### 9.2 Features (M5)

- **Briefing:** before the timer starts, show each drawn module's topic and its signs as looping animations.
- **Sign cards:** at Beginner, the pool of the module being signed shows beside the camera. The cards show the whole pool, so they do not give away which items are on the module.
- **Glossary (built):** the "📖 Glossary (G)" button in the game top bar, or the **G** key, opens the Field Sign Dictionary, for both roles, at any time during a game. The timer keeps running. It lists every game word A to Z, plus YES, NO and FINISH (topic "game controls"), never only this bomb's words (rule 3). A click plays a looping PopSign clip from `signs/clips/` (`uv run fetch-signs`). The digits show a still picture when the team adds one (`signs/clips/pictures/`, with its source and license in `index.json`). Until then, they say "No picture yet". Later: our own signer's animations and a "practice" button.
- **Retry is free:** a rejected guess or a NO costs nothing. Only wrong actions on the bomb cost strikes.
- **Round report:** modules defused, strikes, time, topics practiced, every sign confirmed, and the signs that needed retries.
- **Wording:** present the game as ASL vocabulary practice. Do not claim that it translates ASL. It recognizes single signs.

---

## 10. Screens (Teammate 1)

`HOME → LOBBY → GAME → END → LOBBY`

- **Theme:** a tactical bomb operation. The field agent is on site with the bomb. The handler is far away with the field manual. The only link is a silent video channel. The look is a dark concrete room, a red alarm light, hazard stripes and monospace mission text. The design is in `docs/superpowers/specs/2026-11-21-tactical-theme-design.md`. The code keeps the role values `defuser` and `expert`, and the package name `escape_pod`.
- **Home:** the player types a name, then creates a room or types a 4-letter code to join one. **Play solo** makes a solo room (§4.2). The bot is named Rob (`hq_bot.BOT_NAME`, sent as `bot_name` in the state). Its lobby shows the level picker, Start and the player's own camera, so they can frame their hands. The game also shows the own camera full size. Above the sign chips, a line shows the bot's template: "I need help with:" (name a module with one item) or "My answer:" (the answer to the bot's question). **Practice signs solo** opens solo practice (`practice.js`, `web/practice.py`): pick a game word, watch its glossary clip, sign it, and see the model's confidence. Approved words keep a ✓ in the list. The progress lives in this browser only, and "Reset progress" clears it. The browser runs MediaPipe and sends only landmarks to `POST /api/practice/score`. An invite link `/?room=CODE` fills in the code.
- **Lobby:** the room code, a "Copy invite link" button, two role cards (Defuser, Expert), the level picker and Start. Start works only when two players are in the room and each has a role (in a solo room, at once). No hint line sits under Start. A solo lobby shows no room code and no invite link. "Leave room" goes back to the home screen. A note tells the other player who joined or left.
- **Video (lobby and game):** when two players are in the room, each sees the other's live video, with a small mirrored self-view in the corner. The other player's video is not mirrored, so the signs read as they do face to face. "Camera off" sends black frames. In the lobby, the video sits under the role cards. In the game, it sits at the top of the side panel.
- **Game, defuser:** a metal bomb case with a timer module (red digits, strike lights) and one slot per module. Each module has a status light that turns green when it is defused. The side panel has the video, the sign capture (Space starts and stops a recording, one chip per sign), "Send to <handler name>" and the message feed.
- **Game, expert:** the manual. It has an index of the 20 pages with search on the left and the open page on the right. Pages that match the last signs light up. The side panel has the video, the message feed, a reply box and quick replies ("Which module?", "Sign that again, please.").
- **Initializing (both roles):** after Start, an "INITIALIZING" screen covers the game, and the timer holds the full time. The agent's browser loads the hand tracker and asks the server to load the word model (`GET /api/practice/warmup`), then sends `ready` (`static/init.js`). The screen then shows "GET READY" and a 3-2-1 for both players, so signing never goes live without warning. The server also loads the model in the background when it starts, because the first load takes about 6 s.
- **Both:** the top bar shows the room, the role, the timer, the strikes and "Defused n / m". A strike flashes the screen red. "Exit game" ends the game for both players after a second click, and both go back to the lobby.
- **End:** "DEVICE NEUTRALIZED" or "DETONATION", the stats, and "Back to the lobby". At the end, the server also sends the bomb to the expert, for a debrief.
- Art: every gloss in an icon, dial or switch pool needs an entry in `assets/icons.json` (later, `assets/icons/<gloss>.png`).

---

## 11. Sign vocabulary and media (Teammate 2)

`src/escape_pod/signs/vocab.json` lists every gloss the game uses:

```json
{
  "cow":   {"en": "cow", "topic": "pets_farm", "source": "word_model", "media": "signs/media/cow.json"},
  "4":     {"en": "four", "topic": "numbers", "source": "handshape", "media": "signs/media/4.json"},
  "yes":   {"en": "yes", "topic": "core", "source": "word_model", "media": "signs/media/yes.json"}
}
```

- `source: word_model` glosses must exist in `sign_to_prediction_index_map.json`. `source: handshape` glosses must exist in the trained classifier.
- **Media:** each gloss needs a short looping demonstration for the glossary, the briefing and the sign cards.
  1. Record a fluent (ideally Deaf) signer doing each sign once against a plain background.
  2. `signs/build_media.py` runs MediaPipe on each clip and saves the landmark sequence (`media/<gloss>.json`).
  3. The game draws the sequence as stylized cartoon hands, arms and face, so every sign has the same look and nobody's real face shows.
  - Alternative: PopSign videos are CC BY 4.0 (attribution required). Use them only if you can download just the signs you need. The full dataset is about 1.1 TB.
- Have the signer review every animation and every puzzle pool before the demo (`"reviewed": true` per gloss).

---

## 12. Config, commands and secrets

`src/escape_pod/config.py` holds the paths, `LEVELS`, `MAX_STRIKES` and `LLM_API_KEY_ENV`. Later fields: `HELP_COSTS_S`, `SIGN_BONUS_S`, segmenter thresholds, `MIRROR_INPUT`, `LEFT_HANDED`, `RETRIEVAL_MIN_SCORE`, `RETRIEVAL_MARGIN`, `EMBED_MODEL`, `LLM_MODEL`.

**Secrets:** copy `etc/.env.example` to `etc/.env` and fill it in. `config.py` loads `etc/.env` at import. A real environment variable wins over the file. Git ignores everything in `etc/` except `.env.example`. On Render, set the same variables in the service's Environment tab.

| Variable | Used for |
|---|---|
| `TURN_USERNAME`, `TURN_CREDENTIAL`, `TURN_URLS` | a fixed TURN login for the video (`web/ice.py`). The browser receives it |
| `METERED_APP`, `METERED_API_KEY` | short-lived TURN logins from Metered, instead of a fixed login. The key stays on the server |
| `LLM_API_KEY` | the LLM alien (phase 2) |
| `HOST`, `PORT` | where the server listens. Cloud hosts set `PORT` |

```
uv sync                                   # install everything (first time, and after a pull)
uv run escape-pod [--host 0.0.0.0] [--port 8000] [--debug]
uv run build-manual                       # rebuild docs/manual/ after a rule change
uv run answer-key --seed 7 --level intermediate
uv run pytest
```

- `--host 0.0.0.0` lets a second laptop on the same Wi-Fi join. Add `--https` for video: browsers block the camera on `http://<ip>`.
- `--debug` turns on the answer key for each room. Later it also shows landmarks, raw scores and latencies.
- Session logs go to `logs/session-<timestamp>.jsonl`: guesses, confirmed glosses, actions and latencies. **No images or landmarks** unless the player passes `--record-eval`.

---

## 13. Checks and tests

`tests/test_puzzles.py` (now) and `tools/check_puzzles.py` (later) check that:

- each puzzle validates, ends with `else`, and has a unique `topic`
- no gloss appears in two pools (except core signs)
- every picture gloss has an icon
- rules use only keys that `derive()` can return
- for 500 seeds per puzzle: generation, `solution()`, a target that is on the module, and `phrase()` all work
- every rule can fire (no dead rules)
- the draw rules hold for each level, and the same seed gives the same bomb
- every manual page builds, and the answer key agrees with the engine
- later: every gloss is in `signs/vocab.json`, and its `source` model knows it

`tests/test_server.py` checks the rooms and the roles, and that the expert never gets the bomb. It plays a scripted full game to `escaped`, and three strikes to `boom`. It also checks rejoin with `pid` and the `--debug` gate on the answer key.

Later tests for T3: `to_array` returns `(543, 3)` with NaN blocks in the order in §6.3. Restricting to an allowed set renormalizes and never returns a gloss outside it. The segmenter splits a recording of three signs into three clips.

---

## 14. Team ownership

| Teammate | Area | Owns |
|---|---|---|
| 1 | Web app, screens, widgets | `src/escape_pod/web/` (server and client), `src/escape_pod/assets/` |
| 2 | Sign vocabulary and media | `src/escape_pod/signs/`, the signer recording session, sound effects and music |
| 3 | Vision and retrieval | the recognizer (§6.0 decides the folder), `brain/retriever.py`, `tools/download_models.py`, `tools/record_samples.py`, `tools/train_handshape.py`, `tools/eval_*.py` |
| 4 | Puzzles, manuals and brain | `src/escape_pod/puzzles/`, `src/escape_pod/manual/`, `docs/manual/`, `brain/` (except the retriever), `tools/check_puzzles.py` |

Shared: `config.py`, `puzzles/models.py`, `signs/vocab.json`, the WebSocket messages (§4.2), `pyproject.toml`. Anybody can edit a puzzle file, but tell Teammate 4 and run `uv run build-manual`.

---

## 15. Milestones

1. **M1: two players, typed signs. Done.** Rooms, roles, the lobby, the bomb with all 6 widgets and the manual view. Also the timer, strikes, all 20 puzzles (`senses` later replaced `alphabet`), the static manual and the answer key.
2. **M2: signs from the webcam.** Decide §6.0. Then the camera, MediaPipe to `(543, 3)`, the word model with the day-one checks, the segmenter, and guess chips with YES/NO. *Done when* a teammate can sign the words of 3 puzzles at Beginner, and the game confirms them reliably.
3. **M3: numbers.** The handshape classifier for the digits 0–9. The sign eval runs, and the pools get adjusted. The gloss check against the label map passes.
4. **M4: assets and polish.** CC0 icons and module art in place of emoji, sounds, a credits screen.
5. **M5: learner support and media.** Glossary, signer recordings turned into animations, briefing, sign cards, round report, progress file.
6. **M6: LLM alien (phase 2).** Retrieval, the answer call, `verify()`, `--mock-llm`, as in §7 and §8.
7. **M7: demo hardening.** Test with people outside the team and in venue lighting. Latency within target. A plan for a camera that fails (the typed fallback was removed in November 2026). A recorded backup run.

---

## 16. Open questions

1. **Switch states have no sign.** Switch rules depend on on/off, but no sign in the pools means "on" or "off". Add a sign for it, or change those rules so they do not depend on the state.
2. **Where recognition runs** (§6.0).
3. **How the LLM alien joins** the two-player game (§8).

---

## 17. Don'ts

- Do not let any client, player or LLM decide success, strikes or which module is which. The server decides.
- Do not send the bomb's facts to the expert during play.
- Do not send a recognized sign without the player's confirmation.
- Do not use `eval` or Python expressions in puzzle data.
- Do not block the server's event loop with recognition, retrieval or LLM calls.
- Do not send webcam video through the server, and do not store it by default. Video goes peer to peer only.
- Do not put a gloss the recognizer does not know into a puzzle pool.
- Do not put API keys in code or in git. Use `etc/.env`.
- Do not use `pip` or `requirements.txt`. Use `uv`.
- Do not claim the game translates ASL. It recognizes single signs for vocabulary practice.
- Do not add features beyond this spec without asking.

---

## 18. Credits and licenses

Show these in the README and on an in-game credits screen.

- **Sign model:** `sign/kaggle-asl-signs-1st-place` on Hugging Face, MIT license. It is the winning solution of Google's Kaggle "Isolated Sign Language Recognition" competition.
- **Training data behind the model:** PopSign ASL v1.0, Georgia Tech, CC BY 4.0 (https://signdata.cc.gatech.edu/view/datasets/popsign_v1_0/). Required attribution: credit PopSign ASL v1.0 and its authors. The glossary shows PopSign clips, and `signs/fetch_popsign.py` holds the credit line that the glossary displays.
- **Digit model:** "ASL Landmark MLP" (`nocontextdoruk/asl-landmark-mlp` on Hugging Face), CC BY-NC 4.0: non-commercial use only, with credit. Trained on ASL-HG (Pranto et al., *Data in Brief*, 2026, https://data.mendeley.com/datasets/j4y5w2c8w9/1). Cite both.
- **MediaPipe:** Google, Apache 2.0.
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`, Apache 2.0.
- **Emoji:** the system emoji font of each player's device (placeholder only).
- **Art and sound:** list each CC0 pack used.
- **Sign demonstrations:** credit the signer who recorded them, with their permission.
