# XP history graph: design

Status: approved in chat, 2026-11-21.

## Intent

Players see how their XP grew over their rounds. The lobby shows a graph for the profile that the player picked on the home screen. It builds on the XP and levels design (`2026-11-21-xp-levels-design.md`).

## Approaches

1. **History in the browser profile (picked).** Each saved round gets a time. The lobby draws the graph from `localStorage`. No server change.
2. **History on the server.** Rejected. It needs a database, and the free Render instance loses its memory on a restart.

## Design

- **Saved round:** `ep:round-xp:<profile id>:<round id>` holds JSON `{"xp", "signs", "won", "at"}` in place of a bare number. `xp` is the round total minus the sign part, as before. `signs` is the sign part, so a graph point shows the full round. `at` is the save time in ms. A bare number (an older round) still counts toward the total.
- **History:** a start point ("earlier progress") plus one point per timed round, in time order. Each point has the total XP after that round. The start point is the current total minus the full XP of the timed rounds. It holds the older rounds and the practice credits.
- **Limit:** the graph shows the last 30 rounds. Older timed rounds go into the start point.
- **Graph:** plain SVG in the lobby, under the level bar. Dashed lines mark each level threshold in range. Each point has a tooltip, for example "21 Nov · Defused · +183 XP". With no timed rounds, the graph area shows "Play a round to start your history."
- **Profile:** the graph follows the picked profile. The data stays in one browser.

## Left to the builder

The look of the graph in the dark theme, and its size on small screens.
