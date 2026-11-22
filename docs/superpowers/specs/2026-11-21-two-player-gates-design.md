# Two-player gates: both players take part

> **Change, 2026-11-22:** the case lock now goes the other way. The agent sees the code on the tag and signs it. The digits go to the handler without a check, as a signs message. The handler sets the code on wheels in the manual and sends `lock`, which opens the case remotely. So only the agent signs. The agent gets the digit practice points. The handler can type at the case lock. CLAUDE.md §4.2 has the current messages. The Gate 1 section below describes the first version.

## Why

In a two-player game, the agent does almost all of the work in the two gates before the modules.

- At the case lock, the agent signs the code on the tag. The handler only watches.
- At the wire tray, the handler copies a fixed position order from the manual.

The modules train only one direction: the agent signs and the handler reads. The gates can train both directions before the modules start.

## Goals

- Each gate needs both players.
- Gate 1 trains reading signs. Gate 2 trains making signs.
- The server decides right and wrong, as everywhere in the game (spec rule 1).

## Non-goals

- No new recognition model, and no recognition on the handler's camera.
- No change to the modules.
- The hint feature is a separate design. It comes after this work.

## Approaches

1. **Swap the direction at the case lock, and add a color rule at the tray (chosen).** The handler signs the code, and the agent reads it and sets the lock. At the tray, the agent signs the colors, and the handler applies a color order from the manual.
2. **Split the code.** The agent and the handler each see part of the code, and both sign. We rejected this. It gives two copies of the same task, and it adds no practice in reading signs.
3. **Read the handler's signs with the digit model.** We rejected this for now. The agent's clicks already prove that the code passed between the players. It can come later as feedback for the handler.

## Gate 1: the case lock (two players)

- Only the handler sees the code, for example "434". The agent's case shows the lock without the tag.
- The handler's screen shows the code and the glossary picture of each digit. A handler who does not know the signs can copy the pictures.
- The handler signs the 3 digits to the camera. The agent reads them on the video.
- The agent sets 3 digit wheels on the lock with clicks, then clicks "Open".
- The server checks the code. A wrong code is a strike, and the wheels stay as they are.
- During this gate, the server ignores the handler's `say` messages and quick replies. A typed "434" would skip the sign.
- The code still never uses 2, so the solo game and the two-player game share one rule.

New client message: `{"type": "lock", "code": "434", "round_id": ..., "mission_revision": ...}`, from the defuser, at the case lock, in a two-player room only.

## Gate 2: the wire tray (both modes)

- At the start of each round, the server draws a ranking of all 8 colors. Only the handler sees it, as a manual rule: "Cut the wires in this order of colors: red, black, ...".
- The agent signs the colors of the 4 wires and sends them, the same as on the modules. The confirmed colors go to the handler.
- The cut buttons unlock when the signed colors include all 4 colors on the tray. Wrong colors do not count, and they cost nothing (spec rule 4).
- The handler finds the 4 colors in the ranking and tells the agent the cut order.
- The agent cuts the wires with clicks. Each cut is one step. The server checks each cut against the ranking. A wrong cut is a strike, and the wire stays.

In solo play, Rob uses the same ranking. When the agent has signed the 4 colors, Rob says the order, for example "Cut red, then blue, then white, then green."

## Solo case lock

This does not change. The agent signs the code on the tag, and the digit model reads it. Rob cannot sign, so the reading direction does not work in solo play.

## State changes (§4.2)

- At the case lock in a two-player room, the expert gets `case_code`, and the defuser does not. The defuser gets `lock_wheels: true`.
- At the wire tray, the defuser gets `wires`, `cuts` and `signed_colors`. The expert gets `wire_rank` (the 8 colors) and `signed_colors`.
- The server no longer sends the old position order (`wire_rule`).

## Left to the builder

- The look of the digit wheels and of the handler's code card. Use the workbench style.
- The exact wording of the feedback lines, following STE.
