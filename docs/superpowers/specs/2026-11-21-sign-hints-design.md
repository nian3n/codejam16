# Sign hints: the handler reads the signs first

## Why

The handler sees every confirmed sign as text, so the handler never has to read a sign. The game should train both players. The handler must try to read the signs on the video first. When the handler is stuck for a while, they can ask for the words that the model detected.

The user approved this design earlier in the session. The wire tray part is new: it follows from the two-player gates.

## Goals

- In a two-player game, the handler does not get the words of a signs message by default.
- The handler can reveal the words of one message, 20 s after it arrives.
- The server enforces this. The words are not in the handler's data before the hint.

## Non-goals

- No time cost for now. `HELP_COSTS_S` can add one later.
- No change to solo games with Rob.
- No change to the agent's view. The agent sees their own words.

## Approaches

1. **A hint button that unlocks after a wait (chosen).** The handler tries to read the video first.
2. **A hint button that works at once.** We rejected this: players would click it every time.
3. **A hint with a time cost only.** We rejected this: players with time to spare would still skip the video.

## Behavior

- A signs message on the handler's screen reads "Ana sent 3 signs", with no words. The manual does not highlight pages for a hidden message.
- Each hidden message has a "Show the words" button. It unlocks 20 s after the message arrives (`HINT_WAIT_S`), and it shows a countdown.
- A click sends `{"type": "hint", "msg": <chat index>}`. The server rejects it before the wait ends, and for a message that is not a sign message.
- After the hint, the handler sees the words of that message and the page highlights, as before. Both players see "<handler> used a hint."
- When the game ends, the handler sees all words, for the debrief.
- The gates use the same rule. At the wire tray, the handler sees only how many colors arrived (`colors_received`). The ranking marks only the colors from messages that the handler revealed.

## State changes (§4.2)

- For the handler in a two-player game, a hidden signs chat entry has `count` and `hint_in_s` (seconds until the hint unlocks, 0 when ready) instead of `glosses`. A revealed entry has `glosses` and `hinted: true`.
- The handler's wire tray view has `colors_received` instead of `signed_colors`.
