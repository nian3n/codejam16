# codejam16: Keep Moving and Nobody Explodes

Source code for CodeJam 16. Keep Moving and Nobody Explodes is a two-player bomb-defusal game for ASL vocabulary practice. The game recognizes single signs. It does not translate ASL.

- The **field agent** (the defuser) is on site with the bomb and signs what they see.
- The **HQ handler** (the expert) sees only the field manual and tells the agent what to do.

They talk only through a silent video link, so the agent signs. The name is a play on words: the players move their hands instead of talking. The Python package keeps its old name, `escape_pod`.

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
5. Allow the camera when the browser asks. When two players are in the room, each player sees the other's video.
6. Each player takes one role. Then click **Start the game**.

### Two laptops on the same Wi-Fi

Browsers allow the camera only on `localhost` or on HTTPS. For video between two laptops, use HTTPS:

1. Start the server: `uv run escape-pod --host 0.0.0.0 --https`
2. The server prints the address for the other players, for example `https://192.168.1.20:8000`.
3. Each player opens that address. The browser shows a certificate warning, because the certificate is self-signed. Click **Advanced**, then **Continue**.

The first `--https` start makes the certificate in `etc/tls/`. Git ignores that folder. If your laptop gets a new IP address, delete `etc/tls/` to make a new certificate.

The video goes directly between the two browsers. The game server never receives it.

### Deploy online (players on different networks)

The repo has a `Dockerfile` and a `render.yaml` for Render. Render gives the game a public HTTPS address, so the camera works with no certificate warning.

1. Get a free TURN relay. Sign up at metered.ca and make a TURN credential. Copy its username and password.
2. Sign in at render.com with GitHub.
3. Click **New**, then **Blueprint**. Select this repo.
4. When Render asks for `TURN_USERNAME` and `TURN_CREDENTIAL`, paste the username and the password. Leave `METERED_APP` and `METERED_API_KEY` empty.
5. Click **Apply**. The first build takes a few minutes.
6. Open the address that Render shows, for example `https://escape-pod.onrender.com`. Send the invite link to the other player.

Render builds again after each push to the branch in `render.yaml`. The free plan stops the server after 15 minutes with no visitors. The next visit then waits about one minute. A restart also removes all rooms.

The TURN relay forwards the video only when the two browsers cannot connect directly, for example on phone data. The video stays encrypted end to end. Without the Metered values, the game still runs, but video can fail on strict networks.

To test the image on your laptop: `docker build -t escape-pod .` and then `docker run -p 8000:8000 escape-pod`.

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
