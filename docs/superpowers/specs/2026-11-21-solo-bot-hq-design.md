# Solo game with a bot HQ: design

Date: 2026-11-21. Status: built. Revised after the first playtest (see the next section).

## Revision after the playtest

The playtest found that signing every item before any answer was too hard. The bot now follows the page's rules, one question at a time:

- It reads the rules in order. For the next condition it cannot decide yet, it asks one question.
- A condition that is false skips its rule. The first rule that holds gives the instruction.
- If the action names a position ("press the last button"), the bot also asks for that item.
- The item from round 0 counts as a fact: "there is a cat".
- Questions say "Tell me…", not "Sign…". For example: "Do you see DOG?", "Tell me the color of the top wire.", "Tell me the picture that the needle points at.", "Is the LAMP switch on?" and "Tell me which switches are on. Tell me NO if none is on."
- The answer is YES, NO or an item. Signing the item that the bot asked about also means YES.
- The keypad asks for the whole display at once.
- After a strike, the bot walks the same page again from the start.
- The frame above the chips reads "My answer:" instead of "Here is what I see:".

Over 600 random modules, a perfect player needs 3.4 exchanges on average, and 6 at most. The sections below describe the first version. Where they differ, this section wins.

Also from the playtest: the G key opens the glossary. The glossary button moved to the side panel for one round, then went back to the top bar. The LAMP icon (a light bulb) now shows its word.

After the second playtest, an "INITIALIZING" screen shows between Start and the timer. It loads the hand tracker and the word model, so the first sign does not wait about 6 s.

## Intent

One person can play the real game alone. The player is the field agent. A scripted bot takes the HQ seat. The point is sign practice: the player must sign correctly to get a correct instruction. The two-player game stays as it is.

## Goals

- A player can start a solo game from the home screen and play it to the end without a second person.
- Each module takes at least 2 exchanges: one to name the module, and one or more to give the details.
- The bot reads only what the player signs, like a human HQ. It never reads the bomb's facts (spec rule 3).
- The bot gives instructions from the rule engine (spec rule 1 and rule 2).

## Non-goals

- No LLM. The LLM alien (spec §8) can later replace the bot's wording, with this script as the fallback.
- No signed replies from the bot. Replies are text.
- No change to the two-player game.

## Anti-goals

- The bot must not correct the player with the real facts. A wrong but clear sign gives a wrong instruction, and the wrong action is a strike. The user chose this: "Whole point is to sign properly." The sign chips still let the player fix a wrong recognizer guess before sending (rule 4).
- The bot must not help the player find the module. It does not know which puzzles are on the bomb.

## Approaches considered

- **A. Scripted bot on the server (chosen).** It reuses the rule engine, `phrase()` and the game's sign composer. It works offline and replies at once.
- B. Scripted bot in the browser. Rejected: it needs a second copy of the rule engine in JavaScript, and the client would decide the answer.
- C. LLM alien. Rejected for now: it needs an API key, a network, a verify step and money. It fits later, on top of A.

## The exchange

### Round 0: name the module

The page shows the frame "I need help with:" above the chips. The player signs one or more items from one module and presses Send.

- Each word is in exactly one pool (`test_no_gloss_in_two_pools`). The bot maps each word to its puzzle. The puzzle with the most words wins.
- No word matches a puzzle: "I do not know that word. Sign one thing from the module again."
- A tie between puzzles: "Is it the {title A} or the {title B}? Sign one more thing from the module."
- A match: the bot names the page and asks the first detail question: "That is the {title}. {question}"

The bot does not know which puzzles are on this bomb. A misread word can open a page for a module the player does not have. The player sees the page title in the reply and starts again.

### Rounds 1 and 2: the details

The page shows the frame "Here is what I see:" above the chips. The player signs and presses Send.

| Widget | Round 1 question | Round 2 question | Facts |
|---|---|---|---|
| wires | "Sign the wire colors, top to bottom." | none | `colors` |
| keypad | "Sign the {n} numbers on the display, left to right." | none | `display` |
| icons | "Sign the {n} pictures, left to right, top row first." | none | `icons` |
| dial | "Sign the {n} pictures, clockwise from the top." | "Which picture does the needle point at?" | `options`, `needle` |
| switches | "Sign the switch labels, left to right." | "Now sign only the switches that are on. Sign NO if none is on." | `switches` |
| big_button | "Sign the faces in the order the screen shows them." | none | `faces` |

`{title}` comes from the puzzle file. `{n}` is `spec.setup["shown"]`. The reading orders match `Widget.reading_order` in `puzzles/engine.py`.

**Checks on each answer.** The bot keeps only the words from the open page's pool, in the order the player signed them. Then it checks the answer:

- Round 1 needs exactly `{n}` different words. Otherwise: "I need {n} {items}. You signed {k}. Sign all {n} again." `{items}` is "wire colors", "numbers", "pictures", "switch labels" or "faces".
- The dial round 2 needs exactly one word, and that word must be one of the round 1 pictures. Otherwise: "Sign the one picture that the needle points at."
- The switches round 2 needs a subset of the round 1 labels, or NO alone. Every label that is not signed is off.
- **Module change.** No word of an answer is from the open page, but the words match another page. Then the bot treats the answer as round 0 and opens that page. The player can then stop work on a hard module and go to another.

### The answer

After the last round, the bot builds `Module(spec, facts)` from the signed facts. It calls `phrase(module.solution(), module)`. It replies with the facts it understood, then the instruction:

"You see a cat, a dog, a cow and a pig. Press the dog."

The bot keeps the last page it gave an instruction for. What it does next depends on the result:

- **A defuse:** the bot goes back to round 0: "Good work. Tell me the next module when you are ready."
- **A strike:** the bot opens the last page again at round 1: "That was a strike. Check the {title} again. {question}" The bot does not say which sign was wrong, because it trusts the signs.
- **No action yet:** the bot stays at round 0. The player can sign the next module, or act first.

The strike and defuse events name a module number, but the bot does not know which page that number is. The bot assumes that the event came from its last instruction. A human HQ would assume the same. If the player wants another module after a strike, they sign its words, and the module-change rule opens that page.

**History.** The bot's lines go into the game's message feed, like a human HQ's messages. The feed keeps every exchange for the whole game. The last reply repeats the facts the bot understood, so the player can compare them with the module and find the wrong sign.

## Where it lives

- **`src/escape_pod/brain/hq_bot.py` (new, Teammate 4).** A pure class `HqBot` with no I/O: `reply(glosses: list[str]) -> str` and a `stage` property ("module" or "details"). It holds the open page and the facts so far. It uses `load_pool()`, `Module` and `phrase()`. Tests call it directly.
- **`web/server.py`.** `Room` gets `solo: bool` and `bot: HqBot | None`. In a solo room:
  - The bot is not an entry in `room.players`. This keeps the WebRTC code from waiting for a second player.
  - The one human is the defuser. `can_start()` needs only the defuser.
  - On a `signs` message, the server records the signs, then records `{"kind": "say", "from": "HQ bot", "text": bot.reply(glosses)}`. It then broadcasts. The bot is fast and does no I/O, so it does not block the event loop (rule 6).
  - `view()` adds `"solo": true` and `"bot_stage"` ("module" or "details"), so the page can show the right frame.
  - `start_game` makes a new `HqBot` for each game.
  - After `act()` in a solo room, the server calls `bot.on_result(defused: bool) -> str` and records the reply as an HQ message.
- **`POST /api/rooms`** takes an optional body `{"solo": true}`.
- **Home screen.** A new "Play solo (bot HQ)" button creates a solo room and joins it.
- **Lobby.** In a solo room, the lobby shows the level picker and Start. The role cards and the video are hidden.
- **`rtc.js`.** In a solo room, it opens the local camera with no peer connection. `localCameraVideo()` then works, so the sign composer can read frames.
- **`game_signs.js`.** It shows "I need help with:" or "Here is what I see:" above the chips, from `bot_stage`. Everything else is the same as in the two-player game.
- **Feed.** The bot's lines show as HQ messages. The reply box and the manual are not shown.

## Constraints

- This work builds on the branch `game-signs` (the webcam sign composer). That branch is not merged yet. The branch `solo-bot` starts from it.
- The recognizer's allowed words are the same as in the game (spec §6.3). NO is a core sign, so the switches round 2 works.
- The keypad uses the typed fallback until the digit model is trained (spec §6.4).
- The WebSocket messages only gain fields (spec §4.2). `signs` and `say` keep their shape.
- Spec rule 8 holds: the camera frames stay in the browser.

## Tests

- `tests/test_hq_bot.py`. For each of the 20 puzzles and many seeds, sign the true facts through the rounds. The bot's instruction must equal `phrase(module.solution(), module)`.
- Wrong count, unknown word, tie, the dial needle not among the pictures, switches with NO, and the module change.
- After a strike, the bot reopens the last page at round 1. After a defuse, it goes back to round 0.
- A wrong but clear sign gives the instruction for the signed facts, not for the true facts.
- `tests/test_server.py`. A solo room starts with one player, the bot replies to `signs`, and the state never holds bomb facts for an expert, because no expert exists. A scripted solo game reaches `escaped`.

## Left to the builder

- The exact wording of the error replies, if it stays short and asks a question (rule 5).
- How the English list of facts reads ("a cat, a dog and a cow"). Use the English-word helper in `puzzles/phrase.py`, which turns `frenchfries` into "french fries".
- The lobby layout for a solo room.

## Open

- CLAUDE.md §8 says the LLM alien may take the expert seat. This bot is the first version of that seat. Update §8 and §10 when this ships.
