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
