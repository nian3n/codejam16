# Two-player gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both players take part in the case lock and the wire tray.

**Architecture:** `web/mission.py` holds the gate rules. In a two-player room, only the handler sees the code. The agent sets it on wheels, and `try_code` checks it. The wire tray needs the agent to sign all 4 colors before cuts unlock, and a per-round color ranking decides the cut order. `server.py` routes the new `lock` message and blocks the handler's chat at the case lock. The client draws the wheels, the handler's code card and the ranking page.

**Tech Stack:** FastAPI WebSockets, vanilla ES modules, pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-two-player-gates-design.md`

## Global Constraints

- The server decides right and wrong (spec rule 1). The expert never gets the bomb's facts (rule 3). The tray colors are not bomb facts, but the expert view must not get `wires` or `cuts` during play.
- A recognition mistake never costs a strike (rule 4): wrong signed colors cost nothing.
- The case code never uses 2 (`LOCK_DIGITS`).
- Every gate input carries `round_id` and `mission_revision`. The server ignores a stale one.
- UI text says "handler" and "Rob", never "HQ". No typed sign input.
- Solo case lock does not change.

## Review Focus

1. The handler types in the chat during the case lock: the server ignores it. Test: `test_handler_cannot_type_at_the_case_lock`.
2. The agent sends `lock` in a solo room, or `signs` at a two-player case lock: the server ignores both. Test: `test_lock_message_only_in_two_player_rooms`.
3. The agent cuts before all 4 colors are signed: a retry, not a strike. Test: `test_cut_waits_for_all_four_colors`.
4. A malformed code ("43", "abc", 434 as a number): a retry, not a strike. Test: `test_bad_code_is_a_retry`.
5. A reload during the tray keeps `signed_colors`. Covered by the rejoin check in the rewritten two-player gate test.

---

### Task 1: Mission rules

**Files:**
- Modify: `src/escape_pod/web/mission.py`
- Test: `tests/test_mission.py` (new)

**Interfaces:**
- Produces: `Mission.draw(rng, wheels: bool) -> Mission`. `Mission.rank: list[str]` (all 8 colors). `Mission.wire_order -> list[int]` (a property now: the tray indexes sorted by rank). `Mission.signed_colors: list[str]`. `Mission.tray_ready -> bool`. `Mission.cut_colors -> list[str]` (the colors in cut order). `Mission.try_code(code) -> Literal["retry", "strike", "open"]`. `Mission.confirm(glosses) -> list[str]`. `Mission.cut(index) -> Literal["retry", "strike", "cut"]`. `view(role)` as in the spec's state changes.
- Remove: `confirmed_color`, `position_order`, and `wire_rule` in the view.

- [ ] **Step 1: Write the failing tests** in `tests/test_mission.py`:
  - `test_draw_ranks_all_colors`: `rank` is a permutation of the colors pool. `wire_order` sorts the tray by rank.
  - `test_try_code_opens_or_strikes`: wheels mission. The right code gives "open" and the stage `wire_tray`. A wrong 3-digit code gives "strike" and keeps the stage.
  - `test_bad_code_is_a_retry`: "43", "abc", 434, None give "retry".
  - `test_tray_signs_collect_colors`: `confirm(["red"])` adds only tray colors, without repeats. A color not on the tray is not added and costs nothing.
  - `test_cut_waits_for_all_four_colors`: `cut` before `tray_ready` gives "retry". After it, a wrong index gives "strike", and the right order gives 4 "cut" and the stage `modules`.
  - `test_views_split_the_code`: wheels mission. The defuser view has `lock_wheels` and no `case_code`. The expert view has `case_code`. Solo (`wheels=False`): the defuser has `case_code`. At the tray, the expert view has `wire_rank` and `signed_colors`, and no `wires`.
- [ ] **Step 2:** Run `uv run pytest tests/test_mission.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces above. `confirm` at the case lock works only when `wheels` is False. It accepts 1 to 4 color glosses at the tray.
- [ ] **Step 4:** Run `uv run pytest tests/test_mission.py -q`. Expected: PASS.

### Task 2: Server and Rob

**Files:**
- Modify: `src/escape_pod/web/server.py` (`start_game`, `handle_gate`, `handle`)
- Modify: `src/escape_pod/brain/hq_bot.py` (`wire_tray_prompt()`, new `wire_order_prompt(colors)`)
- Modify: `tests/test_server.py`, `tests/test_hq_bot.py` if it calls `wire_tray_prompt`
- Modify: `CLAUDE.md` §4.2 Mission paragraph and the `lock` row

**Interfaces:**
- Consumes: Task 1.
- Produces: the client message `{"type": "lock", "code": "434", "round_id", "mission_revision"}`. The digit credits `"{round_id}:case_lock:{slot}"` go to the expert after a two-player unlock.

- [ ] **Step 1: Write the failing tests:** `test_handler_cannot_type_at_the_case_lock` and `test_lock_message_only_in_two_player_rooms`. Rewrite the helpers: two-player `_open_case` sends `lock`, solo `_open_case` signs. `_open_gates` signs the 4 colors and then cuts in `wire_order`. Rewrite `test_two_player_gates_use_the_manual_and_restore_the_agent_seat` and the solo full-game test for the new flow.
- [ ] **Step 2:** Run `uv run pytest tests/test_server.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `Mission.draw(rng, wheels=not room.solo)`.
  - `lock` in `handle_gate`. A strike calls `strike(room)`. "open" says "Case unlocked. The wire tray is open." and credits the expert.
  - Tray signs only collect colors. When the tray becomes ready, Rob says `wire_order_prompt(mission.cut_colors)`.
  - Ignore `say` at the case lock.
- [ ] **Step 4:** Run `uv run pytest -q`. Expected: all pass.
- [ ] **Step 5:** Commit "Two-player gates: server rules".

### Task 3: Client

**Files:**
- Modify: `src/escape_pod/web/static/mission.js` (wheels, clickable wires, handler's code card and ranking page)
- Modify: `src/escape_pod/web/static/game_signs.js` (tray: up to 4 signs, sent to the handler. Wheels lock: no signing)
- Modify: `src/escape_pod/web/static/workbench.js` (case note), `feed.js` (reply box off at the case lock), `style.css` (wheels, code card)

- [ ] **Step 1:** Build it. The wheel values live in `store.local.lockWheels`, which resets per `round_id`. The digit pictures come from `/signs/pictures/<d>.png`.
- [ ] **Step 2:** Browser check with two players: the handler sees the code and the pictures, and cannot type. The agent sets the wheels and opens the case. A wrong code is a strike. The agent signs 4 colors (sent as chat glosses through the test socket, because the fake camera has no hands). The handler sees the ranking. The cuts unlock, and the right order reaches the modules. Run a solo check too.
- [ ] **Step 3:** Commit "Two-player gates: wheels, code card and ranking page".
