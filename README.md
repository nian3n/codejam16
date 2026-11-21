# codejam16: Escape Pod

Source code for CodeJam 16. Escape Pod is a two-player bomb-defusal game for ASL vocabulary practice. The game recognizes single signs. It does not translate ASL.

- The **defuser** sees the bomb and signs what they see.
- The **expert** sees only the manual and tells the defuser what to do.

For now, the defuser types each sign. Webcam sign recognition and the LLM alien come later. The full spec is in `CLAUDE.md`.

## Set up

1. Install [uv](https://docs.astral.sh/uv/).
2. Install the packages: `uv sync`
3. If you need API keys, copy `etc/.env.example` to `etc/.env` and fill it in. Git ignores `etc/.env`.

## Run the game

1. Start the server: `uv run escape-pod`
2. Open `http://localhost:8000` in two browser tabs, one for each player.
3. In the first tab, type a name and click **Create a room**.
4. In the second tab, type the 4-letter room code and click **Join**.
5. Each player takes one role. Then click **Start the game**.

To play on two laptops on the same Wi-Fi, run `uv run escape-pod --host 0.0.0.0`. The second player then opens `http://<your-ip>:8000`.

To see the answer key for a live bomb, run `uv run escape-pod --debug`. Then click **Answer key (debug)** in the top bar.

## Test the sign model

The sign-test tool shows what the ASL model recognizes when you sign to the webcam. The project uses Python 3.12, because MediaPipe does not support 3.13 yet.

1. Install the vision packages: `uv sync --extra vision`
2. Download the model (11 MB, one time): `uv run download-models`
3. Start the tool: `uv run sign-test --target --set pets_farm`
4. Sign the word that the tool shows. Lift your hands into view, sign, then lower your hands or hold still.
5. Press **A** or **Z** to change the word set. Press **Q** to quit. The tool then prints your score per word.

Other keys:

- **N** skips a word.
- **X** removes your last attempt from the score.
- **Space** records 2.5 seconds after a 3-2-1 countdown. Use it if the tool does not notice your signs.
- **M** mirrors the camera input. Please score one set with M off and one set with M on.
- **H** turns on left-handed mode.

The tool writes each attempt to `logs/sign-test-<time>.jsonl`. Send that file to the team. It holds the guesses and the settings. It holds no images.

**Windows on ARM** (for example, a Surface or a Snapdragon laptop): MediaPipe has no ARM wheels. Use an x64 Python, which Windows runs under emulation:

1. `uv venv -p cpython-3.12-windows-x86_64-none`
2. `uv sync --extra vision`

## Commands

| Command | What it does |
|---|---|
| `uv sync` | installs the packages (first time, and after each pull) |
| `uv run escape-pod` | starts the game server |
| `uv run build-manual` | rebuilds `docs/manual/` after a rule change |
| `uv run answer-key --seed 7` | prints the answer key for one bomb |
| `uv sync --extra vision` | also installs MediaPipe, OpenCV and TFLite |
| `uv run download-models` | downloads the sign model to `models/` |
| `uv run sign-test` | starts the sign-model test tool |
| `uv run pytest` | runs the tests |
| `uv add <package>` | adds a package (`uv add --dev` for test-only packages) |

## Layout

| Path | What it holds | Owner |
|---|---|---|
| `src/escape_pod/config.py` | paths, levels, limits. Loads `etc/.env` | shared |
| `src/escape_pod/puzzles/` | the 20 puzzle files, the rule engine and the English wording | Teammate 4 |
| `src/escape_pod/manual/` | the static manual builder and the answer-key builder | Teammate 4 |
| `src/escape_pod/web/server.py` | rooms, roles and game state (FastAPI and WebSockets) | Teammate 1 |
| `src/escape_pod/web/static/` | the browser client. One file per screen, one file per widget in `widgets/` | Teammate 1 |
| `src/escape_pod/assets/` | `icons.json`: placeholder emoji for each word | Teammate 1 |
| `src/escape_pod/vision/` | landmarks, segmenter, sign model, recognizer, the sign-test tool | Teammate 3 |
| `docs/manual/` | the generated manual pages (committed) | Teammate 4 |
| `etc/` | secrets. Only `.env.example` is in git | everyone |
| `tests/` | pytest tests | everyone |

Not built yet: `signs/` (Teammate 2), the handshape classifier (Teammate 3), `brain/` (Teammates 3 and 4), `tools/`. See `CLAUDE.md` §3 and §14.
