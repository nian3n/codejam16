# XP History Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A lobby graph of the picked profile's XP over its rounds.

**Architecture:** `xp_store.js` saves each round as JSON with a time and builds the history (pure, Node-tested). A new `xp_chart.js` draws it as SVG in a `#xp-history` box in the lobby.

**Spec:** `docs/superpowers/specs/2026-11-21-xp-history-design.md`

## Review Focus

- A profile with older bare-number rounds and new JSON rounds: the total and the start point must both be right.
- More than 30 timed rounds: the last point still equals the total.
- A corrupt saved value (not a number, not JSON): it counts as 0 and the graph still draws.

### Task 1: History data

**Files:** modify `src/web/static/xp_store.js`, `src/web/static/app.js` (pass `won`). Test: `tests/test_xp_levels.py`.

**Produces:** `saveRoundXp(storage, profileId, round, now = Date.now())` saving `{xp, signs, won, at}`, where `won` is true when a part is labeled "Bomb defused". `history(storage, profileId, limit = 30) -> {start: number, rounds: [{at, gain, total, won}]}`. `totalXp` reads both formats.

- [ ] Write the failing tests: `test_history_orders_rounds_by_time`, `test_history_mixes_old_and_new_rounds`, `test_history_keeps_the_last_30`, `test_corrupt_round_counts_as_zero`, `test_empty_profile_has_no_rounds`. Each checks that the last point's `total` (or `start` when there are no rounds) equals `totalXp`.
- [ ] Run them. Expected: FAIL.
- [ ] Implement. Run `uv run pytest -q`. Expected: all pass. Commit.

### Task 2: Lobby graph

**Files:** create `src/web/static/xp_chart.js` (`renderXpHistory(box, hist)`). Modify `index.html` (`<div id="xp-history" class="xp-history"></div>` in the lobby card, after `.lobby-top`), `progress.js` (render the graph in `renderProgress` while the lobby shows), `style.css`.

- [ ] Draw: a polyline of the totals, a dot per point with a `<title>` tooltip ("21 Nov · Defused · +183 XP"), dashed level lines with labels (`levelFor` thresholds), and the empty text.
- [ ] Check in the browser: a new profile shows the empty text. After two solo rounds, the graph shows two points. A profile switch on the home screen changes the graph.
- [ ] Update `CLAUDE.md` §9.2. Run `uv run pytest -q`. Commit.
