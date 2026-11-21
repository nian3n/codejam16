# Escape Pod — Project Spec (ASL)

You are helping a team of 4 build a hackathon game in **Python** where players practise **American Sign Language (ASL)** by signing to an alien through their webcam. Read this whole file before writing code.

- This spec **replaces** every earlier spec (the JRPG and the French/Spanish/German versions). Start a fresh repo.
- Build in the milestone order in §15. Keep the game runnable at every milestone, and keep `python -m pytest` passing.
- Each teammate owns an area (§14). Unless told otherwise, ask which teammate you're helping, and only edit that area's files. Shared files (`config.py`, `brain/models.py`, `puzzles/models.py`, `game/state.py`, `signs/vocab.json`) change only with a heads-up: add fields, never rename them.
- Every source file starts with a `# Owner: Teammate N (Area)` line.
- If something here is ambiguous, pick the simplest option that keeps the interfaces in §4 intact, note it in a code comment, and tell the human.

---

## 1. The game

A three-scene game inspired by *Keep Talking and Nobody Explodes*.

- The player is trapped in an alien escape pod with a bomb. An alien on the comm link has the defusal manual but **can't see the bomb**, and it only understands **ASL**. The player sees the bomb but **can't read the manual's rules**.
- The player **signs** what they see, one sign at a time, to the webcam. The alien **replies in English text** on screen.
- Each game **draws modules from a pool of 20 puzzles**. **Every puzzle teaches a different vocabulary topic** (colors, numbers, animals, …), and every word used is a sign the recognizer knows (§5.1).
- **Three scenes** (§10): the **bomb scene** (the drawn modules and the webcam), the **manual scene** (the alien's manual with all 20 puzzles; the alien identifies the page) and the **glossary scene** (every word with how to sign it).
- Each exchange:
  1. On the bomb scene, the player selects a module and **signs the items they see**, one sign per capture (e.g. CAT, DOG, COW).
  2. The **sign recognizer** (MediaPipe landmarks + a pretrained TFLite model, §6) shows its best guesses; the player confirms each one (sign YES or click) or retries (sign NO).
  3. The confirmed signs (English glosses) go to the alien. The game switches to the manual scene, where **retrieval (RAG)** finds the matching page among all 20 and the alien opens it.
  4. The **LLM answers** from that page in English, as structured JSON.
  5. **Code verifies** the answer against the real module. A wrong answer is never shown.
  6. The alien's reply appears as **English text**. The game returns to the bomb scene and the player **acts** by clicking. A correct action defuses the module; a wrong one is a strike.
- Defuse all modules before the timer runs out with fewer than 3 strikes → the pod launches. Then a round report, then play again with a new draw.
- A full game takes 5–10 minutes.

Because every puzzle has its own topic, the signs alone identify the manual page: signing RED, BLUE, GREEN can only mean the colors puzzle. That is what makes retrieval reliable without the player signing words like "wire" or "button".

### Non-negotiable design rules

1. **Code decides right and wrong.** Solutions come from the rule engine (§5). The LLM never decides whether the player succeeded.
2. **One source of truth.** Each puzzle's JSON rules produce both the code's solution and the manual page.
3. **Verify before showing.** Every LLM answer is checked by code (§8.2). If it's wrong, the alien shows the code's answer instead.
4. **The player confirms every recognized sign** before it's sent. Recognition mistakes cost a retry, never a strike.
5. **Learner-friendly failure.** An unclear or mismatched description gets a question, never a wrong instruction.
6. **The game loop never blocks.** Camera processing, recognition, retrieval and LLM calls run off the game thread; the game polls results each frame.
7. **One topic per puzzle**, and every puzzle word must be recognizable (§13).
8. **Webcam frames never leave the laptop** and are not saved unless the player opts in for evaluation recordings.

---

## 2. Tech stack

| Part | Tool |
|---|---|
| Language | Python 3.11+ |
| Game / UI | `pygame-ce` |
| Webcam | `opencv-python` (capture), shown mirrored on screen |
| Landmarks | `mediapipe` Holistic (543 landmarks per frame: face, both hands, pose) |
| Word signs | `sign/kaggle-asl-signs-1st-place` from Hugging Face: `model.tflite` (11.2 MB) + `sign_to_prediction_index_map.json`, 250 signs, MIT license |
| TFLite runtime | `ai-edge-litert` (or `tensorflow`'s `tf.lite.Interpreter`) |
| Numbers and letters | Own small classifier on MediaPipe hand landmarks (`scikit-learn`), trained on team recordings (§6.4) |
| Retrieval | `sentence-transformers` (`all-MiniLM-L6-v2`); NumPy cosine similarity |
| LLM | Provider SDK behind `brain/llm.py`; JSON output validated with `pydantic` v2 |
| Sound | `pygame.mixer` (sound effects, music; optional English voice is out of scope) |
| Tests | `pytest` |

- API key from the environment variable named in `config.LLM_API_KEY_ENV`; never in code.
- `tools/download_models.py` fetches the sign model and the embedding model once. After that, everything except the LLM works offline.
- Credits and licenses are in §17 and must appear in the README and on an in-game credits screen.

---

## 3. Project layout

```
main.py                     # T1  entry point, CLI flags (§12)
config.py                   # shared
requirements.txt
README.md                   # setup, run, ownership, credits

game/                       # T1
  scenes.py                 #   state machine (§10.1), main loop, scene switching
  bomb_scene.py             #   modules, select/zoom, clicks, webcam panel, sign confirm chips
  manual_scene.py           #   index of 20 puzzles, page flipping, open page
  glossary_scene.py         #   words, topics, sign animations
  hud.py, report.py, learner_ui.py
  state.py                  #   GameState, ExchangeLog (shared)

vision/                     # T3
  camera.py                 #   capture thread, frame queue
  landmarks.py              #   MediaPipe Holistic -> (543, 3) arrays, NaN for missing parts
  segmenter.py              #   decides when a sign starts and ends (§6.2)
  word_model.py             #   TFLite word-sign model wrapper (§6.3)
  handshape.py              #   numbers/letters classifier (§6.4)
  recognizer.py             #   recognize(clip, allowed) -> ranked guesses

puzzles/                    # T4 (engine, data) + T1 (widgets)
  models.py                 #   PuzzleSpec, Action, Rule (shared)
  data/*.json               #   20 puzzle files
  engine.py                 #   load_pool, draw, Module, rule evaluation
  phrase.py                 #   phrase(action, module) -> English instruction
  widgets/                  #   T1: wires, keypad, icons, dial, switches, big_button

manual/                     # T4
  build.py                  #   rules -> English manual pages
  pages/                    #   generated, git-ignored

brain/                      # T4 + T3 (retriever)
  models.py                 #   Answer, Verdict, AlienLine (shared)
  llm.py, retriever.py (T3), answer.py, verify.py, lines.py, mock.py

signs/                      # T2
  vocab.json                #   every gloss the game uses (§11) (shared)
  media/                    #   per-gloss sign animations for the glossary and briefing
  build_media.py            #   reference clips -> landmark animations

assets/                     # T1/T2  icons, module art, sound effects, music, fonts (CC0)
models/                     # downloaded / trained models, git-ignored
tools/
  download_models.py        # T3
  record_samples.py         # T3  record team sign samples for eval and the handshape classifier
  train_handshape.py        # T3
  eval_signs.py             # T3
  eval_retrieval.py         # T3
  check_puzzles.py          # T4
tests/
logs/
```

---

## 4. Interfaces (do not change signatures without telling the team)

```python
# vision/recognizer.py
@dataclass
class Guess:
    gloss: str          # "cat"
    score: float        # probability among the allowed set, 0..1

def recognize(clip: np.ndarray, allowed: set[str]) -> list[Guess]: ...   # clip: (T, 543, 3) float32, best first

# vision/segmenter.py
class Segmenter:
    def push(self, frame_landmarks: np.ndarray) -> np.ndarray | None: ...  # returns a finished clip, or None

# puzzles/engine.py
def load_pool() -> dict[str, PuzzleSpec]: ...
def draw(rng: random.Random, level: Level, weak_topics: set[str] = frozenset()) -> list[Module]: ...

class Module:
    spec: PuzzleSpec
    facts: dict
    defused: bool
    def solution(self) -> Action: ...
    def check(self, action: Action) -> bool: ...

# puzzles/phrase.py
def phrase(action: Action, module: Module) -> str: ...        # "Press the cow."

# brain
def retrieve(glosses: list[str]) -> list[tuple[str, float]]: ...       # (puzzle_id, score), best first
def answer(glosses: list[str], page_id: str, history: list[Exchange]) -> Answer: ...
def verify(answer: Answer, module: Module) -> Verdict: ...
def line(key: str, **values) -> AlienLine: ...                         # fixed alien lines
```

### Shared models

```python
# puzzles/models.py
@dataclass(frozen=True)
class Action:
    verb: str            # see widget table §5.2
    target: dict         # {"wire": 2}, {"color": "blue"}, {"keys": ["4", "7"]}, {"icon": "cow"}

class PuzzleSpec(BaseModel):
    id: str
    title: str
    widget: Literal["wires", "keypad", "icons", "dial", "switches", "big_button"]
    topic: str                       # unique across the pool
    hard: bool = False
    looks_like: str                  # 1-2 sentences for the manual and the index
    pool: list[str]                  # the glosses this puzzle can show (each in signs/vocab.json)
    target_words: Literal["color", "name", "digits", "letters", "position", "state"]
    setup: dict
    rules: list[Rule]                # last rule must be an "else"

# brain/models.py
class Answer(BaseModel):
    page_id: str
    facts: dict          # what the player signed, as facts: {"icons": ["cat", "dog", "cow", "pig"]}
    recast: str          # "You see a cat, a dog, a cow and a pig."
    action: Action
    english: str         # "Press the cow."

class Verdict(BaseModel):
    kind: Literal["ok", "ask_sure", "ask_which", "ask_more", "corrected"]
    english: str | None = None
    field: str | None = None
    action: Action | None = None
    candidates: list[str] = []

class AlienLine(BaseModel):
    text: str                        # English shown on screen
    signs: list[str] = []            # glosses in the line the player can tap to see in the glossary
```

---

## 5. Puzzles

### 5.1 The pool: 20 puzzles, 20 topics

Every word below is one of the 250 glosses in the sign model's label map, except numbers and letters, which use the handshape classifier (§6.4). Gloss spellings follow the label map (e.g. `icecream`, `frenchfries`, `tv`); check them against `sign_to_prediction_index_map.json`.

| # | id | Topic | Widget | Pool (glosses) | Example alien line |
|---|---|---|---|---|---|
| 1 | `colors` | Colors | wires | red, blue, green, yellow, black, white, brown, orange | "Cut the blue wire." |
| 2 | `numbers` | Numbers 0–9 | keypad | 0–9 (handshapes) | "Type 4, 7, 2." |
| 3 | `alphabet` | Fingerspelling | keypad (letters) | A–Z except J and Z (handshapes) | "Type B, A, D." |
| 4 | `pets_farm` | Pets and farm animals | icons | cat, dog, cow, pig, horse, duck, hen, donkey | "Press the cow." |
| 5 | `wild_animals` | Wild animals | icons | lion, tiger, zebra, giraffe, elephant, alligator, wolf, owl | "Press the giraffe." |
| 6 | `family` | Family | icons | mom, dad, grandma, grandpa, brother, aunt, uncle | "Press grandma." |
| 7 | `people_jobs` | People and jobs | icons | fireman, police, cowboy, clown, boy, girl, man, child | "Press the police officer." |
| 8 | `body` | Body parts | icons | ear, eye, nose, mouth, tooth, tongue, hair, arm, finger, feet | "Press the nose." |
| 9 | `food` | Food | dial | apple, carrot, cereal, pizza, frenchfries, icecream, chocolate, nuts | "Turn the dial to the pizza." |
| 10 | `clothes` | Clothes | icons | hat, shirt, shoe, jacket, jeans, mitten, pajamas, zipper | "Press the jacket." |
| 11 | `weather_sky` | Weather and sky | dial | sun, moon, cloud, rain, snow | "Turn the dial to the snow." |
| 12 | `transport` | Transport | dial | car, boat, airplane, helicopter | "Turn the dial to the boat." |
| 13 | `feelings` | Feelings | big_button | happy, sad, mad, sleepy, hungry, thirsty, sick | "Hold the button and let go when the face is sleepy." |
| 14 | `actions` | Actions | icons | jump, dance, sleep, read, cry, kiss, hide, ride | "Press the one who is dancing." |
| 15 | `home_things` | Things at home | switches | bed, chair, table, lamp, tv, radio, refrigerator, drawer | "Switch on the lamp." |
| 16 | `places` | Places | switches | bedroom, backyard, pool, store, farm, outside, stairs, closet | "Turn off the backyard light." |
| 17 | `toys` | Toys and play | icons | doll, toy, balloon, puzzle, gift | "Press the balloon." |
| 18 | `school` | School things | icons | book, pen, pencil, scissors, flag | "Press the scissors." |
| 19 | `opposites` | Opposites | switches | up, down, open, close, wet, dry, clean, dirty, loud, quiet | "Set the left lever to down." |
| 20 | `time_words` | Time words | icons | morning, night, now, later, yesterday, tomorrow | "Press tomorrow." |

- Hard puzzles: `alphabet`, `feelings`, `time_words` (abstract or timing-based).
- Each module shows 4 items from its pool (dials and switches show 4–5). Setups must make the target unambiguous.
- Signs that involve motion (most of them) are fine: the word model reads whole clips. Only the handshape classifier is limited to still signs, which is why J and Z are excluded.
- Instructions name targets with the topic's own words (`target_words`): the colors puzzle says "the blue wire", not "the second wire".

### 5.2 Widgets

Each widget class in `puzzles/widgets/` has **logic hooks** for the engine and **drawing and clicks** for the game.

```python
class Widget:
    name: str
    def generate(self, spec: PuzzleSpec, rng) -> dict: ...         # facts, drawn from spec.pool
    def derive(self, facts: dict) -> dict: ...                     # flat values rules may test
    def resolve(self, action: Action, facts: dict) -> Action: ...  # symbolic targets -> concrete
    def draw(self, surface, rect, facts, state) -> None: ...
    def click(self, pos, rect, facts, state) -> Action | None: ...
```

| Widget | Facts | Derived keys | Verbs |
|---|---|---|---|
| wires | `colors: [..]` (unique) | `count`, `first`, `last`, `has:<color>` | `cut {color: c}` or `{wire: int\|"first"\|"last"}` |
| keypad | `display: [..]` (digits or letters shown) | `count`, `first`, `last`, `has:<x>`, `reversed`, `sorted` | `type {keys: [..]}` or `{keys_from: "<derived>"}` |
| icons | `icons: [4 glosses]` | `has:<g>`, `position_of:<g>`, `first`, `last` | `press {icon: g}` |
| dial | `options: [..]`, `needle: g` | `needle`, `has:<g>` | `turn {to: g}` |
| switches | `switches: [{label, state}]` | `count_on`, `state_of:<label>` | `set {switch: label, state: "on"\|"off"\|"up"\|"down"}` |
| big_button | `faces: [..]` (sequence shown while held) | `faces`, `first`, `last` | `hold {release_on: g}` |

Rules are data: `[derived_key, op, value]` conditions (ops `== != < <= > >= in`), ANDed within a rule, first match wins, last rule is `else`. **No `eval`.** One action per puzzle.

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

### 5.4 Draw rules and manual

- `draw` is seeded (`--seed`), takes the module count and hard-puzzle limit from the `Level` (§9), uses at least `min(3, n)` widgets, at most one hard puzzle, and doubles the weight of `weak_topics`.
- `manual/build.py` writes one English page per puzzle: title, "How to recognize it" (from `looks_like` and the pool), and the rules in plain English, using the same wording helpers as `phrase()`.

---

## 6. Sign recognition (Teammate 3)

### 6.1 Pipeline

```
webcam (OpenCV, 30 fps)
  -> MediaPipe Holistic per frame -> (543, 3) landmarks, NaN where a part isn't detected
  -> Segmenter: detects when a sign starts and ends -> clip (T, 543, 3)
  -> word model (TFLite, 250 glosses)  or  handshape classifier (numbers, letters)
  -> scores restricted to the allowed glosses -> top 3 guesses
  -> player confirms (sign YES / click) or retries (sign NO)
```

Run camera capture and MediaPipe in their own thread; send finished clips to a worker for recognition. Show the camera mirrored with the hand skeleton drawn on it, so players see what the model sees.

### 6.2 Capturing one sign

The player needs both hands to sign, so **don't use hold-to-sign**. Instead:

- **Auto mode (default):** a sign starts when at least one hand is detected and moving above the waist, and ends when the hands drop or stay still for 0.4 s. Ignore clips under 0.3 s or over 3 s.
- **Manual fallback:** press Space (or click) to start a 2.5 s capture window with a visible 3-2-1 countdown.
- After each clip, show the top 3 guesses as chips. Signing **YES** or clicking a chip confirms; signing **NO** discards. YES and NO are in the model's vocabulary.
- The confirmed signs build up a list shown on screen ("You signed: CAT · DOG · COW"). A "Send" button (or signing **FINISH**, also in the vocabulary) sends it to the alien.

### 6.3 The word model

`models/islr/model.tflite` and `models/islr/sign_to_prediction_index_map.json`, from `sign/kaggle-asl-signs-1st-place` on Hugging Face (winning solution of Google's Kaggle "Isolated Sign Language Recognition" competition, trained on PopSign data).

The competition required models to take **one clip of MediaPipe Holistic landmarks**, shaped `(frames, 543, 3)` float32 with x, y, z and NaN for undetected parts, and to return 250 scores. Landmark order per frame, as in the competition data:

| Rows | Part | Count |
|---|---|---|
| 0–467 | face | 468 |
| 468–488 | left hand | 21 |
| 489–521 | pose | 33 |
| 522–542 | right hand | 21 |

```python
# vision/landmarks.py
import mediapipe as mp, numpy as np
holistic = mp.solutions.holistic.Holistic(refine_face_landmarks=False)   # 468 face points, not 478

def to_array(results) -> np.ndarray:
    def block(lms, n):
        if lms is None:
            return np.full((n, 3), np.nan, np.float32)
        return np.array([[p.x, p.y, p.z] for p in lms.landmark], np.float32)
    return np.concatenate([
        block(results.face_landmarks, 468),
        block(results.left_hand_landmarks, 21),
        block(results.pose_landmarks, 33),
        block(results.right_hand_landmarks, 21),
    ])                                                    # (543, 3)

# vision/word_model.py
import json
from ai_edge_litert.interpreter import Interpreter        # or: tf.lite.Interpreter

interp = Interpreter(model_path="models/islr/model.tflite")
print(interp.get_signature_list())                         # confirm input/output names first
runner = interp.get_signature_runner("serving_default")
index = json.load(open("models/islr/sign_to_prediction_index_map.json"))
glosses = [g for g, i in sorted(index.items(), key=lambda kv: kv[1])]

def scores(clip: np.ndarray) -> dict[str, float]:
    out = runner(inputs=clip.astype(np.float32))           # name from get_signature_list()
    logits = next(iter(out.values())).reshape(-1)
    return dict(zip(glosses, logits))
```

Things to verify on day one (write them up in `vision/README.md`):

1. The signature names and shapes printed by `get_signature_list()`.
2. **Mirroring:** run your team's test signs with the raw camera frame and with a horizontally flipped frame; keep whichever scores better, and still display the mirrored image.
3. **MediaPipe version:** `mp.solutions.holistic` is MediaPipe's older API. Pin a `mediapipe` version that still includes it (record the version in `requirements.txt`), or port to the newer Tasks holistic landmarker if it gives the same 543 points.
4. **Left-handed signers:** add a setting that mirrors the landmarks' x coordinates and swaps the two hand blocks, and test which works.

**Restrict the choices.** After getting the 250 scores, keep only the `allowed` glosses and softmax over them:

| Level | Allowed set |
|---|---|
| Beginner | the selected module's `pool` plus core signs (yes, no, finish) |
| Intermediate | the pools of all modules on this bomb plus core signs |
| Advanced | all 250 glosses |

Choosing among 10 signs is much more reliable than among 250. A wrong but allowed sign (e.g. a color that isn't on the module) is still caught later by verification (§8.2).

### 6.4 Numbers and letters (handshape classifier)

The word model doesn't cover numbers or fingerspelling. Train a small classifier:

- `tools/record_samples.py`: each teammate records about 30 samples of each digit 0–9 and each letter except J and Z, using the same camera pipeline.
- Features: the dominant hand's 21 landmarks, translated to the wrist and scaled by hand size (63 numbers), averaged over the steadiest 5 frames of the clip.
- Model: `scikit-learn` k-nearest neighbours or a small MLP, saved to `models/handshape.joblib`.
- `recognizer.recognize` routes to this classifier when the allowed set is digits or letters.

### 6.5 Evaluation (`tools/eval_signs.py`)

- Record a test set with `record_samples.py`: every gloss used in the game, 3 takes each, by at least 3 people, including at least one person outside the team.
- Report top-1 and top-3 accuracy per gloss for each level's allowed set, plus a confusion list. Swap out glosses that are consistently confused within a pool (e.g. two animals with similar signs).
- Report latency from the end of a sign to guesses shown (target: under 300 ms on the demo laptop).

---

## 7. Retrieval (`brain/retriever.py`, Teammate 3)

- **Index:** for each puzzle, embed `title + looks_like + "Words: " + pool` with `all-MiniLM-L6-v2`. 20 vectors in NumPy; build at startup.
- **Query:** the confirmed glosses joined into a string ("cat dog cow pig").
- **Search all 20 pages**, not just the modules on the bomb.
- **Decision** (`config.RETRIEVAL_MIN_SCORE`, `config.RETRIEVAL_MARGIN`; tune with the eval):

| Result | Verdict | Manual scene shows |
|---|---|---|
| best < MIN_SCORE | `ask_more` ("Show me more signs.") | the alien flipping, then shrugging |
| top two within MARGIN | `ask_which` ("Animals or food?") | both pages side by side |
| best ≠ the selected module's puzzle | `ask_sure` ("Are you sure? Look again.") | the page the alien thinks you mean |
| otherwise | answer call | the alien opening the page |

- Since every gloss belongs to exactly one puzzle's pool, also compute a simple vote: the puzzle owning most of the glosses. If the vote and the embeddings disagree, trust the vote. This keeps retrieval near-perfect while the embedding step still shows the RAG flip.
- **Eval** (`tools/eval_retrieval.py`): for each puzzle, 20 random gloss sets of 1–4 signs from its pool, plus noisy sets with one wrong gloss. Report top-1 accuracy.

---

## 8. Brain (Teammate 4)

### 8.1 Answer (LLM call, `brain/answer.py`)

- **System prompt (static, cacheable):** "You are an alien reading a bomb defusal manual. The human described their module with a list of ASL signs (English glosses). Using only the manual page given, turn the glosses into facts with the canonical values listed, restate what they described in one short, friendly English sentence (`recast`), decide the action the rules give, and write it as one short English instruction naming the target the way the page does. Output JSON matching the schema. If the rules need a fact the human didn't sign, set it to null."
- **User message:** the manual page, the widget's fact schema, the confirmed glosses, the last 3 exchanges on this module.
- **Validation:** pydantic `Answer`; one retry on invalid JSON, then `ask_more`. Drop fact keys the widget doesn't define.

### 8.2 Verify (code, `brain/verify.py`)

1. `answer.page_id` ≠ the selected module's puzzle id → `ask_sure`.
2. Compare facts with `module.facts`. A fact the rules need is missing → `ask_more` naming it ("Which animals do you see?"). A fact is wrong → `ask_sure` naming it.
3. Facts match: action equals `module.solution()` → `ok` with `answer.english`; otherwise → `corrected` with `phrase(module.solution(), module)`.
4. Log every verdict; "the LLM was right X% of the time before verification" is a pitch metric.

On `ok` or `corrected`, the alien shows the recast first at Beginner and Intermediate ("You see a cat, a dog, a cow and a pig. Press the cow."), with each gloss in the line tappable to open the glossary.

### 8.3 Fixed lines (`brain/lines.py`)

`ask_sure`, `ask_more:<field>`, `ask_which`, `select_module`, `defused`, `strike`, `boom`, `escaped`, `briefing_intro`, stored in `brain/lines.json` with placeholders.

### 8.4 Mock modes

- `--mock-signs`: a text box replaces the webcam; typed words are treated as confirmed glosses.
- `--mock-llm`: retrieval by the gloss vote only; the answer reads the selected module's real facts and uses the rule engine and `phrase()`. A full game must run with `--mock-signs --mock-llm` and no network or camera.

---

## 9. Learner support

### 9.1 Levels

```python
@dataclass(frozen=True)
class Level:
    name: Literal["beginner", "intermediate", "advanced"]
    modules: int                 # 2-3 / 4 / 4
    allow_hard: bool             # False / False / True
    timer_s: int | None          # None or 600 / 300 / 180
    allowed_scope: Literal["module", "bomb", "all"]
    briefing: bool               # True / True / False
    sign_cards: bool             # True / False / False
    recast: bool                 # True / True / False
```

| Support | Beginner | Intermediate | Advanced |
|---|---|---|---|
| Briefing before the bomb | Yes: each topic's signs shown and practised | Yes, shown only | No |
| Sign cards beside the selected module | Yes, looping animation per word | No | No |
| Recognizer choices | This module's words | This bomb's words | All 250 |
| Timer | Off or 10 min | 5 min | 3 min |
| Modules per game | 2–3, no hard ones | 4 | 4, hard ones allowed |
| Alien restates what you signed | Yes | Yes | No |

### 9.2 Features

- **Briefing:** before the timer starts, show each drawn module's topic and its signs as looping animations. At Beginner, the player tries each sign once and the recognizer gives a green check, which also warms up the camera pipeline.
- **Sign cards:** at Beginner, the selected module's pool appears beside the camera as small looping animations. Cards show the whole pool, not only the items on the module, so they don't give away which items are there.
- **Glossary links:** every gloss in the alien's text and on the sign cards opens the glossary entry.
- **Retry is free:** a rejected guess or a NO costs nothing. Only wrong actions on the bomb cost strikes.
- **Signing bonus:** each confirmed sign adds `config.SIGN_BONUS_S` seconds when a timer is running.
- **First game:** with no previous report, the first game is one easy module with no timer.
- **Round report:** modules defused, strikes, time, topics practised, every sign confirmed, signs that needed retries (with recognition confidence), and weak topics (saved to `~/.escape_pod/progress.json` to bias the next draw).
- **Wording:** present the game as practising ASL vocabulary. Don't claim it translates ASL; it recognizes single signs.

---

## 10. Scenes and UI (Teammate 1)

### 10.1 States

`TITLE → LEVEL → LOADING → (CAMERA_CHECK) → BRIEFING → BOMB ⇄ MANUAL ⇄ GLOSSARY → (ESCAPED | BOOM) → REPORT`

| Step | Scene | State |
|---|---|---|
| Player signs, confirms each guess, then sends | Bomb | `SIGNING` |
| Retrieve, answer, verify | Manual (auto-switch) | `THINKING` |
| Alien's reply appears | Manual | `REPLYING` |
| Player acts | Bomb (auto-switch after 2 s or on click) | `IDLE` |

Tab toggles bomb and manual; G opens the glossary. Switching never pauses the timer. Three clickable scene tabs at the top show where the player is. If the alien replies while the player is in the glossary, stay there.

`CAMERA_CHECK` runs on first launch: checks that the camera opens, that hands are detected, and that lighting is good enough (show tips if hands are often lost).

### 10.2 Bomb scene (1280×720)

- Left two-thirds: the bomb with the drawn modules. Click one to select it (zoomed). Signing with no module selected shows `select_module`.
- Right third: the webcam panel (mirrored, with hand skeleton), the capture indicator, the top-3 guess chips, the confirmed sign list and the Send button. Sign cards appear below at Beginner.
- Top: timer, strikes, help buttons, level. Bottom: the alien's last reply as text.
- Wrong action: strike sound, red flash. 3 strikes or timer 0 → `BOOM`. All modules defused → `ESCAPED`.

### 10.3 Manual scene

- The index shows all 20 puzzles as thumbnails with their titles.
- During `THINKING`, the alien flips pages; the top 3 retrieval candidates glow, then it opens the best page (or two pages for `ask_which`, or a puzzled look for `ask_sure`).
- An open page shows the title, picture and recognition text; the rules stay covered unless the player buys a manual peek (`config.HELP_COSTS_S`).
- During `REPLYING`, the alien's text appears in a large speech bubble with glosses underlined.

### 10.4 Glossary scene

- Every gloss used by the game, grouped by topic (this game's topics first), plus "Signed this game".
- Each entry: the English word, a looping sign animation (§11), and a "practice" button that runs the recognizer on that one sign and shows a check or a retry.
- Search box; "new" badge on words first met this game. The report links here filtered to weak signs.

Art: CC0 sci-fi UI and icons (Kenney); every gloss in an icon, dial or switch pool needs `assets/icons/<gloss>.png`, and every puzzle a thumbnail `assets/modules/<id>.png`.

---

## 11. Sign vocabulary and media (Teammate 2)

`signs/vocab.json` lists every gloss the game uses:

```json
{
  "cow":   {"en": "cow", "topic": "pets_farm", "source": "word_model", "media": "signs/media/cow.json"},
  "4":     {"en": "four", "topic": "numbers", "source": "handshape", "media": "signs/media/4.json"},
  "yes":   {"en": "yes", "topic": "core", "source": "word_model", "media": "signs/media/yes.json"}
}
```

- `source: word_model` glosses must exist in `sign_to_prediction_index_map.json`; `source: handshape` glosses must exist in the trained classifier.
- **Media:** each gloss needs a short looping demonstration for the glossary, briefing and sign cards. Make them consistent and correct:
  1. Record a fluent (ideally Deaf) signer doing each sign once against a plain background, about 150 signs.
  2. `signs/build_media.py` runs MediaPipe on each clip and saves the landmark sequence (`media/<gloss>.json`).
  3. The game draws the sequence as stylized cartoon hands, arms and face on the alien's body, so every sign has the same look and nobody's real face is shown.
  - Alternative for word-model glosses: PopSign videos are CC BY 4.0 (attribution required). Only use them if you can download just the signs you need; the full dataset is about 1.1 TB.
- Have the signer review every animation and every puzzle pool before the demo (`"reviewed": true` per gloss).

---

## 12. Config, CLI and logs

`config.py`: paths; `LEVELS`; `HELP_COSTS_S`; `SIGN_BONUS_S`; `MAX_STRIKES = 3`; segmenter thresholds; `MIRROR_INPUT`; `LEFT_HANDED`; `RETRIEVAL_MIN_SCORE`; `RETRIEVAL_MARGIN`; `EMBED_MODEL`; `LLM_MODEL`; `LLM_API_KEY_ENV`; camera index; key bindings.

```
python main.py [--level beginner|intermediate|advanced] [--seed N] [--camera N]
               [--mock-signs] [--mock-llm] [--debug] [--start-at bomb]
```

- `--debug`: overlay with landmarks, segmenter state, top-5 raw scores, retrieval scores, verdict and latencies.
- Session log `logs/session-<timestamp>.jsonl`: per exchange, the guesses and confirmed glosses, retrieval scores, answer, verdict, latencies. **No images or landmarks** unless `--record-eval` is passed.

---

## 13. Checks and tests

`tools/check_puzzles.py` (run in tests):
- each puzzle validates, ends with `else`, and has a unique `topic`;
- every gloss in every `pool` is in `signs/vocab.json`, and its `source` model knows it;
- no gloss appears in two pools (except core signs), so the retrieval vote is unambiguous;
- for 500 seeds per puzzle: generation, `solution()`, unambiguous target and `phrase()` all work; rules only use `derive()` keys;
- every manual page builds; icons, thumbnails and media exist.

`tests/`:
- `landmarks.to_array` returns `(543, 3)` with NaN blocks for missing parts and the order in §6.3;
- `word_model` loads and returns 250 scores for a recorded test clip (skips if the model isn't downloaded);
- restricting to an allowed set renormalizes and never returns a gloss outside it;
- segmenter splits a recorded sequence of three signs into three clips;
- rule engine, draw rules, `check()`, `phrase()` and every `verify()` branch;
- retrieval vote and embeddings agree on single-pool gloss sets;
- a scripted full game with `--mock-signs --mock-llm` reaches `ESCAPED` across all three scenes.

---

## 14. Team ownership

| Teammate | Area | Owns |
|---|---|---|
| 1 | Game, three scenes, widgets | `main.py`, `game/`, `puzzles/widgets/`, `assets/` |
| 2 | Sign vocabulary and media | `signs/`, the signer recording session, sound effects and music |
| 3 | Vision and retrieval | `vision/`, `brain/retriever.py`, `tools/download_models.py`, `tools/record_samples.py`, `tools/train_handshape.py`, `tools/eval_*.py` |
| 4 | Puzzles and brain | `puzzles/` (except widgets), `manual/`, `brain/` (except retriever), `tools/check_puzzles.py` |

Once the JSON format and the first widgets work, all four teammates write puzzle files: 5 each.

---

## 15. Milestones

1. **M1 — Playable with typed signs, offline.** Rule engine, `phrase()`, manual builder, 3 puzzles (`colors`, `pets_farm`, `transport`) with their widgets, bomb and manual scenes, timer, strikes, `--mock-signs`, `--mock-llm`. *Done when* a full game can be won and lost by typing glosses.
2. **M2 — Signs from the webcam.** Camera thread, MediaPipe to `(543, 3)`, the TFLite word model with the day-one checks in §6.3, segmenter, guess chips with YES/NO confirm. *Done when* a teammate can sign the 3 puzzles' words and have them confirmed reliably at Beginner.
3. **M3 — RAG and verification.** Embedding index plus vote, real answer call, all verdicts, flip animation, session log. *Done when* signing the wrong topic gets "Are you sure?" with the guessed page shown, and a deliberately broken LLM answer is corrected.
4. **M4 — Full pool.** All 20 puzzles, the handshape classifier for numbers and letters, icons and thumbnails, `check_puzzles.py` clean, sign and retrieval evals run and pools adjusted.
5. **M5 — Learner support and media.** Glossary scene, signer recordings turned into animations, briefing, sign cards, levels, signing bonus, round report and progress file, credits screen.
6. **M6 — Demo hardening.** Test with people outside the team and in venue lighting, latency within target, offline fallbacks (`--mock-signs` if the camera fails), a recorded backup run, Beginner demo path: a judge learns two signs in the briefing, signs them, watches the alien find the page, and defuses a module within the first two minutes.

---

## 16. Don'ts

- Don't let the LLM decide success, strikes or which module is which.
- Don't show an LLM answer before `verify()`.
- Don't send a recognized sign without the player's confirmation.
- Don't use `eval` or Python expressions in puzzle data.
- Don't run MediaPipe, the sign model, retrieval or the LLM on the game thread.
- Don't store or upload webcam frames by default.
- Don't put a gloss the recognizer doesn't know into a puzzle pool.
- Don't claim the game translates ASL; it recognizes single signs for vocabulary practice.
- Don't add features beyond this spec without asking.

---

## 17. Credits and licenses

Show these in the README and on an in-game credits screen.

- **Sign model:** `sign/kaggle-asl-signs-1st-place` on Hugging Face, MIT license; the winning solution of Google's Kaggle "Isolated Sign Language Recognition" competition.
- **Training data behind the model:** PopSign ASL v1.0, Georgia Tech, CC BY 4.0 (https://signdata.cc.gatech.edu/view/datasets/popsign_v1_0/). Required attribution: credit PopSign ASL v1.0 and its authors.
- **MediaPipe:** Google, Apache 2.0.
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`, Apache 2.0.
- **Art and sound:** list each CC0 pack used.
- **Sign demonstrations:** credit the signer who recorded them, with their permission.
