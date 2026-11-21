# codejam16: Escape Pod

Source code for CodeJam 16. Escape Pod is a two-player bomb-defusal game for ASL vocabulary practice. The game recognizes single signs. It does not translate ASL.

- The **defuser** sees the bomb and signs what they see.
- The **expert** sees only the manual and tells the defuser what to do.

For now, the defuser types each sign. Webcam sign recognition and the LLM alien come later. The full spec is in `CLAUDE.md`.

## Set up

1. Make a virtual environment: `python -m venv .venv`
2. Install the packages: `.venv/Scripts/python -m pip install -r requirements.txt`

## Run the game

1. Start the server: `.venv/Scripts/python -m web.server`
2. Open `http://localhost:8000` in two browser tabs, one for each player.
3. In the first tab, type a name and click **Create a room**.
4. In the second tab, type the 4-letter room code and click **Join**.
5. Each player takes one role. Then click **Start the game**.

To play on two laptops on the same Wi-Fi, start the server with `--host 0.0.0.0`. The second player then opens `http://<your-ip>:8000`.

To see the answer key for a live bomb, start the server with `--debug`. Then click **Answer key (debug)** in the top bar.

## Manuals

- **Static manual:** `manual/pages/`, one page for each of the 20 puzzles, and `MANUAL.md` with all of them. The pages come from `puzzles/data/*.json`. To build them again after a rule change, run `.venv/Scripts/python -m manual.build`.
- **Answer key for one bomb:** `.venv/Scripts/python -m manual.solve --seed 7 --level intermediate`. The key shows each rule, which conditions are true, which rule fires, and the exact instruction.

## Tests

Run `.venv/Scripts/python -m pytest`.

## Layout

| Path | What it holds |
|---|---|
| `puzzles/data/` | the 20 puzzle files (rules as data) |
| `puzzles/engine.py` | the rule engine, widget logic and draw |
| `puzzles/phrase.py` | the English wording for the manual and the instructions |
| `manual/` | the static manual builder and the answer-key builder |
| `web/server.py` | the rooms, the roles and the game state (FastAPI and WebSockets) |
| `web/static/` | the browser client: lobby, bomb and manual |
| `assets/icons.json` | placeholder emoji icons for each word |
| `demo/quick_demo.py` | the earlier one-file pygame demo (throwaway) |
