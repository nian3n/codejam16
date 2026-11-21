# Tactical Theme and New Name Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the web client as a tactical bomb operation and rename the game to "Keep Moving and Nobody Explodes", with no change to game logic.

**Architecture:** Task 1 changes the words: the name, the agent and HQ roles, and the endings, in the client, the server's event text and the docs. Task 2 changes the look. A new set of CSS tokens and a few small DOM hooks (an alarm light, a mission line, LIVE tags and a `critical` body class) carry the theme. The page draws everything with CSS and SVG.

**Tech Stack:** plain HTML, CSS and ES modules (no build step), FastAPI, pytest, Playwright (scratch checks only).

**Spec:** `docs/superpowers/specs/2026-11-21-tactical-theme-design.md`

## Global Constraints

- Name, exactly: `Keep Moving and Nobody Explodes`. Short code: `KMNE`.
- Role labels: `Field agent` (role value `defuser`) and `HQ handler` (role value `expert`). The role values and all WebSocket messages stay the same.
- End titles: `DEVICE NEUTRALIZED` (phase `escaped`) and `DETONATION` (phase `boom`).
- Tagline: `No words. Only hands. Keep moving.`
- Do not rename the package `escape_pod`, the folders or the commands.
- No outside images, fonts or sounds. Use only CSS, inline SVG and emoji.
- Do not copy the logo, fonts or bomb art of *Keep Talking and Nobody Explodes*.
- Effects stay at the edges. Never draw them over a module, the manual text or the video.
- `@media (prefers-reduced-motion: reduce)`: no pulse and no blink.
- Each file keeps its `Owner:` line. User-facing text follows STE (short sentences, no semicolons).

## Review Focus

1. **The game ends or returns to the lobby under 30 seconds.** The `critical` class must go away, or the next lobby keeps the fast red alarm. Task 2 checks that `body.critical` is gone in the lobby.
2. **A narrow window (under 1000 px, the existing breakpoint).** The stripes and the alarm must not cover the bomb or cause horizontal scroll. Task 2 takes a 900 px screenshot.
3. **A player with reduced motion turned on.** The alarm and the LIVE tag must stand still. Task 2 checks with `reduced_motion="reduce"`.
4. **No video yet, or the camera blocked.** The LIVE tag must not claim a live feed. It shows only while the remote video plays. Task 2 checks the lobby with one player.
5. **The manual over a dark textured page.** The page text keeps its paper background and dark ink. Task 2 checks the expert screenshot.

---

### Task 1: New name and story wording

**Files:**
- Modify: `src/escape_pod/web/static/index.html` (title, logo, tagline, role cards)
- Modify: `src/escape_pod/web/static/app.js` (`setupGame` role label, `renderEnd` titles)
- Modify: `src/escape_pod/web/static/lobby.js` (hints), `feed.js` (composer labels)
- Modify: `src/escape_pod/web/server.py` (`FastAPI(title=...)`, the win and loss event text)
- Modify: `src/escape_pod/__init__.py`, `src/escape_pod/web/tls.py` (certificate name), `src/escape_pod/manual/build.py` (index heading). Then run `uv run build-manual`.
- Modify: `README.md`, `CLAUDE.md` (title, §1 win condition, §10 end screen, role names in §1 and §10)
- Test: `tests/test_server.py`

**Interfaces:**
- Produces: the end-screen titles and role labels above. Task 2 styles them and does not change the words.

- [ ] **Step 1: Write the failing test.** In the existing scripted full-game test that reaches `escaped`, assert the last chat event: `assert s["chat"][-1]["text"] == "All modules defused. Device neutralized."`. In the three-strikes test, assert `"Three strikes. Detonation!"`.
- [ ] **Step 2: Run** `uv run pytest tests/test_server.py -q`. Expected: the two tests fail on the old text.
- [ ] **Step 3: Change the server text.** Win: `All modules defused. Device neutralized.` Three strikes: `Three strikes. Detonation!` Time out: `Time ran out. Detonation!` Title: `Keep Moving and Nobody Explodes`.
- [ ] **Step 4: Change the client words.**
  - Logo: two lines, `KEEP MOVING` and `and nobody explodes` (the second line smaller).
  - Role cards: `Field agent`, "You are on site with the bomb. Sign what you see. You cut, press and turn." and `HQ handler`, "You have the field manual. You never see the bomb. Tell the agent what to do."
  - Top bar role: `Field agent` / `HQ handler`.
  - End titles: as in Global Constraints.
- [ ] **Step 5: Change the docs.** Run `uv run build-manual`, then `git diff --stat docs/manual`. Expected: only the index heading changes.
- [ ] **Step 6: Run** `uv run pytest -q`. Expected: all tests pass.
- [ ] **Step 7: Commit** with the message `Rename to Keep Moving and Nobody Explodes, agent and HQ wording`.

### Task 2: Tactical operation look

**Files:**
- Modify: `src/escape_pod/web/static/style.css` (tokens, background, frames, manual, video, motion)
- Modify: `src/escape_pod/web/static/index.html` (add `<div class="alarm" aria-hidden="true"></div>` as the first child of `body`, and `<span id="op-line" class="op-line"></span>` in the top bar)
- Modify: `src/escape_pod/web/static/app.js` (`tickTimer`, `setupGame`)
- Modify: `src/escape_pod/web/static/rtc.js` (LIVE tag and channel label in the dock)

**Interfaces:**
- Consumes: the Task 1 labels.
- Produces these DOM hooks:
  - `.alarm`: a fixed red light, top right.
  - `body.critical`: on only while `phase === "playing"` and less than 30 s are left.
  - `#op-line`: text `OPERATION KMNE-<CODE> · AGENT <name> · HQ <name>`.
  - `.live-tag`: text `● LIVE · AGENT CAM`, or `● LIVE · HQ LINK` when the other player is the expert. It shows only while the remote video has a `srcObject`.
  - `.manual` and `.page`: a CSS `::before` stamp with the text `CLASSIFIED`.

- [ ] **Step 1: Restyle with CSS.**
  - Tokens: concrete grays for `--bg`, `--bg2` and `--card`, hazard yellow `--haz: #f2c230`, and alarm red as `--warn`.
  - The body background: layered gradients that look like a concrete wall and a steel floor. The blue radial gradient goes away.
  - Hazard stripes: a `repeating-linear-gradient(45deg, var(--haz) 0 14px, #111 14px 28px)` border strip on `.bomb`, `.lobby-card` and `.home-card`, outside the content box.
  - `.alarm`: a slow red pulse every 2 s. With `body.critical`, the pulse runs every 0.6 s.
  - The top bar and `.op-line` use a monospace font.
  - Camera corner brackets around `.remote-wrap`.
  - The manual keeps its paper background, with a red rotated `CLASSIFIED` stamp in a corner.
  - With `prefers-reduced-motion: reduce`, set `animation: none` on `.alarm` and `.live-tag`.
- [ ] **Step 2: Add the hooks in JS.**
  - In `tickTimer`, toggle `document.body.classList` `critical` with the condition above.
  - In `setupGame`, fill `#op-line`.
  - In `rtc.js`, add the `.live-tag` to `.remote-wrap`. Toggle it in `ontrack`, `dropPeer` and `onRoomState`.
- [ ] **Step 3: Check syntax.** Run `node --check` on `.mjs` copies of every changed JS file. Expected: no output.
- [ ] **Step 4: Run the browser check.** Use a scratch Playwright script with two headless Edge players and fake cameras, as in the earlier video checks. It must assert all of the following:
  - The lobby with one player has no visible `.live-tag`. With two players, the tag is visible.
  - In a game, after the client store's deadline is forced under 30 s, `body.critical` is on. After "Exit game", it is off.
  - With `reduced_motion="reduce"`, the computed `animation-name` of `.alarm` is `none`.
  - At 900 px width, `document.documentElement.scrollWidth <= 900`.
  - The script saves screenshots of the home, lobby, agent, HQ and end screens.
  - Look at each screenshot. The text, the modules, the manual and the video must be easy to read.
- [ ] **Step 5: Run** `uv run pytest -q`. Expected: all tests pass.
- [ ] **Step 6: Commit** with the message `Tactical operation theme`.
