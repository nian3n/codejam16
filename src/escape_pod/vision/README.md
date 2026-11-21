# Vision: day-one checks

Spec §6.3 asks for these checks. Measured on 2026-11-21 with `mediapipe==0.10.21` and `tensorflow-cpu` 2.19 on x64 Python 3.12. The laptop runs Windows on ARM, so x64 Python ran under emulation.

## 1. Signature

- `serving_default`: input `inputs`, shape `(T, 543, 3)` float32. Output `outputs`, shape `(250,)`.
- The outputs are logits, not probabilities. `recognizer.rank()` applies softmax over the allowed glosses.
- With the default XNNPACK delegate, a clip shorter than 3 frames fails. `WordModel.logits()` pads short clips to 3 frames.
- Latency: about 30 to 75 ms for 3 to 120 frames. The spec target is under 300 ms.

## 2. Mirroring

Not measured yet. The sign-test tool logs `mirror_input` with every attempt. Do the same target-mode run with mirror off and on (key M), then compare the top-1 scores in the logs.

## 3. MediaPipe version

`mediapipe==0.10.21` still has `mp.solutions.holistic`. That version has wheels only for Python 3.9 to 3.12, so the project pins Python 3.12. There are no wheels for Windows on ARM. On those laptops, use an x64 Python (see the README).

## 4. Left-handed signers

`landmarks.left_handed()` mirrors x and swaps the two hand blocks. Key H in the sign-test tool turns it on. Not measured yet with a left-handed signer.

## Label map

All word-model glosses in the 18 picture puzzles are in the label map. The one difference is `TV`, which `WordModel` lowercases to `tv`. The core signs `yes`, `no` and `finish` are in the map. The map also has `on`, but not `off`.

## Digits 0–9 (handshape model)

The word model knows no numbers, so a second small model reads the digits from the shape of one hand (spec §6.4). The recognizer uses it when the allowed set has digits, for example on the keypad.

1. Record about 30 samples of each digit per person. Use the same webcam as the demo if you can:

   ```
   uv run --extra vision record-digits --name ana
   ```

   The tool shows a digit. Make the hand shape and hold it still. After 0.6 s it saves the sample and turns the frame green. Move your hand, then do the next digit. One person needs about 10 minutes.
2. Repeat step 1 for each teammate. Ideally, also record one person from outside the team.
3. Train the model:

   ```
   uv run train-digits
   ```

   The tool prints the accuracy and the digits that it confuses. With two or more people, it tests each person on a model that it trained only on the other people. That number tells you how a stranger at the demo will do.
4. Test it live. Press A or Z until the allowed set is "numbers":

   ```
   uv run --extra vision sign-test --set numbers --target
   ```

- **Model:** k nearest neighbors on 63 features. The features are the 21 hand points, moved to the wrist and scaled by the hand size, averaged over the 5 steadiest frames. A left hand is mirrored, so it matches right-hand samples.
- **Files:** the samples go to `data/handshape/<person>/<digit>/`, and the model goes to `models/handshape.npz`. Git ignores both. The samples are landmarks only, with no images. The `--photos` option saves one photo per digit for the glossary. Ask the person first.
- **Mixed sets:** the keypad allows 0–9 plus YES, NO and FINISH. The word model decides how likely the clip is one of the three word signs. The digit model splits the rest of the probability among the digits.
