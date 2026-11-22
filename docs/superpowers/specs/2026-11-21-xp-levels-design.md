# XP and levels: design

Status: draft, for approval.

## Intent

Today, the practice progress bar stops at 50 credits (100 %, "Accomplished"). After that, a player has nothing to work toward. The end screen shows only one line: "Defused 2 of 4 · Strikes 1 · Time left 1:20". It does not show what the round gave the player.

The team wants progress over many games:

- Players earn XP and climb through levels with no cap.
- At the end of each round, won or lost, the player sees the XP from that round, part by part, and how far they are from the next level.

## Goals

- XP for confirmed signs (practice), for defused modules, for a win, and for time left on the clock after a win (the user picked "time left", not "time played").
- Levels with no cap. Each level needs more XP than the one before.
- A round summary on the end screen, with each XP part, the new total and a level bar.
- Old progress carries over. No player starts again from zero.

## Non-goals

- Accounts, or progress that moves between browsers or devices. Profiles stay in `localStorage`, as today.
- Leaderboards, badges or unlocks.
- XP for time played. It pays a player who waits for the bomb to go off.

## Anti-goals

- A reload, a reconnect or a second tab must never count the same round twice.
- No client decides how much XP a round gives (design rule 1: code on the server decides results).

## Approaches

1. **The server works out the round's XP, and the browser keeps the total (picked).** The server knows the true result: strikes, time left, defused modules. It adds a breakdown to the end-of-round state. The browser saves it under the round id and adds it to the profile total. This is how the sign credits work today. Pytest can test the rules.
2. **The browser works out the XP from the end state.** No server change. But the rules would be JavaScript that pytest does not cover, and the round-id guard is still necessary.
3. **Profiles on the server.** Rejected. Rooms live in memory on one free Render instance, so a restart would erase all levels. This needs a database.

## Design

### XP sources

| Part | XP | When |
|---|---|---|
| Sign | 5 for each practice credit | as today: each confirmed sign that a defused module, the case lock or the wire tray proves. Also each approved word in solo practice |
| Module defused | 10 each | end of round, won or lost |
| Bomb defused | Beginner 50, Intermediate 75, Advanced 100, Custom 75 | end of round, win only |
| Time left | 1 for each full 2 s left | end of round, win only |

All numbers are constants in one place (`web/xp.py`), so the team can tune them.

Who gets what: both players get the module, win and time XP, because they play as a team. Each player gets sign XP only for their own credits, as today. A game that ends with "Exit game" gives no end-of-round XP. Credits that were already saved stay.

### Levels

- Level 1 starts at 0 XP. To go from level n to level n + 1, a player needs `250 + 100 × (n − 1)` XP: 250, 350, 450 and so on. A typical Intermediate win gives about 200 XP, so the first levels take one or two games, and later levels take longer.
- Titles change every few levels: Beginner (1–2), Developing (3–4), Practiced (5–6), Skilled (7–9), Accomplished (10 and up). The bar shows, for example, "Level 3 · Developing · 120 / 450 XP".

### Server

- A new module, `web/xp.py`, with `round_xp(room, player) -> dict`. It returns `{"round_id": ..., "parts": [{"label": "Modules defused (4)", "xp": 40}, ...], "total": n}`.
- The sign part in `parts` counts this player's credits whose key starts with this round's id. It is for display only (see below).
- When the phase is `escaped` or `boom`, each player's state has `round_xp`. It stays in the state until "Back to the lobby".

### Browser (`progress.js`)

- The total XP is `5 × (number of credits) + the sum of the saved round results`.
- A round result is saved as `ep:round-xp:<profile id>:<round id>` with the value of `total − sign part`. Sign XP comes from the credits, so this split counts it once only. A second save of the same round writes the same key with the same value.
- Old credits are already in `localStorage`, so they become sign XP with no migration step.
- The progress bar shows the level, the title and the XP to the next level, in place of the percent.

### End screen

The end card shows the parts, the round total, and the level bar. When the player goes up a level, it shows "Level up!" with the new level.

```
DEFUSED · +185 XP
  Signs confirmed (14)     +70
  Modules defused (4)      +40
  Bomb defused             +50
  Time left 1:20           +25
  ─────────────────────────────
  Level 3 ████████░░  420 / 450 XP
```

A loss shows the same card without the win and time lines.

## Left to the builder

- The look of the summary card and the level-up line. Keep the tactical theme.
- Where the summary sits on small screens.
- The update of the spec in `CLAUDE.md` (§9.2 round report, §4.2 state fields).
