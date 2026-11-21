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

## Commands

| Command | What it does |
|---|---|
| `uv sync` | installs the packages (first time, and after each pull) |
| `uv run escape-pod` | starts the game server |
| `uv run build-manual` | rebuilds `docs/manual/` after a rule change |
| `uv run answer-key --seed 7` | prints the answer key for one bomb |
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
| `docs/manual/` | the generated manual pages (committed) | Teammate 4 |
| `etc/` | secrets. Only `.env.example` is in git | everyone |
| `tests/` | pytest tests | everyone |

Not built yet: `signs/` (Teammate 2), the recognizer (Teammate 3), `brain/` (Teammates 3 and 4), `tools/`. See `CLAUDE.md` §3 and §14.
