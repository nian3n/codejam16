# Tactical theme and new name: design

Date: 2026-11-21. Owner: Teammate 1 (web app). Size: a small change (a restyle with no new game logic).

## Intent

The game looks like a plain app on a blue gradient. It must feel like a tense bomb job, so that a demo audience understands "bomb" in one second.

The new name is **Keep Moving and Nobody Explodes**. The name is a play on words: the players move their hands instead of talking. The game is for demos only. The name is the user's decision.

## Story

- The **defuser** is a **field agent**. The agent finds a bomb on site and is the only person there.
- The **expert** is the **HQ handler**. The handler has the field manual and is far away.
- The only link between them is a silent video channel, so the agent signs.
- The video dock becomes the agent's body camera and the HQ link.
- The story does not name a target. Nothing in the game needs a specific "precious thing".

## Goals

- Direction A, "tactical operation", on every screen: home, lobby, defuser view, expert view and the end screen.
- A dark concrete and steel room background, drawn in CSS. No more blue gradient.
- A red alarm light that pulses slowly. Under 30 seconds left, it pulses faster.
- Yellow and black hazard stripes on the edges of the main frames.
- Monospace "mission" text in the top bar, for example `OPERATION KMNE · AGENT ANA · HQ BEN`.
- Camera-style frames on the video, with a blinking "● LIVE" tag and a channel label: `AGENT CAM` or `HQ LINK`.
- The manual becomes a stamped CLASSIFIED field manual. The text stays easy to read.
- Agent and HQ wording on the role cards, the hints and the end screens.
- End screens: "DEVICE NEUTRALIZED" for a win, "DETONATION" for a loss.
- The new name in the logo, the page title, the server title, the README and the spec.

## Non-goals

- No change to the rules, the puzzles, the widgets or the server checks.
- No change to the WebSocket messages. The role values stay `defuser` and `expert`. Only the labels on screen change.
- No rename of the Python package `escape_pod`, the folders or the commands. That rename touches every teammate's imports.
- No image files, sounds or fonts from outside. Everything is CSS, SVG and emoji, so there is nothing to license.

## Anti-goals

- No copy of the logo, fonts, bomb art or layout of *Keep Talking and Nobody Explodes*. The agent and HQ theme is our own.
- The theme must not hurt the game. Glosses, timer digits, buttons and the manual stay easy to read. The effects stay at the edges, never on top of a module or the video.
- No motion for players who ask for less. With `prefers-reduced-motion`, the alarm does not pulse and the LIVE tag does not blink.

## Approaches

| | Direction | Trade-off |
|---|---|---|
| **A (picked)** | Tactical operation: concrete room, red alarm, hazard stripes, HUD text | The most tension and the fastest "bomb" read for a demo |
| B | Spy thriller: dark room, one warm lamp, paper dossier | Stylish but calm. Less urgency |
| C | HQ control room: radar grid, monitor wall, green and amber | Fits the story, but looks the most like a normal app |

The user picked A.

## Calls left to the builder

- The exact colors, the concrete texture (CSS gradients and noise) and the stripe width.
- The role card wording, inside the story above.
- The tagline on the home screen. Proposal: "No words. Only hands. Keep moving."
- The short code in the top bar. Proposal: `KMNE` plus the room code.

## Check

- `uv run pytest` passes. The tests do not check text on screen, but the server's win message changes.
- Two headless browsers play a game with live video. Screenshots of each screen show the new theme, with the text easy to read.
