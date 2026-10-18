# Audit: dropping4-pen on real held-out pen frames (2026-10-18)

**Question:** does the pen droppings model (`models/dropping4-pen` on the `ui` branch) find real droppings in whole-pen footage?

**Setup:** 40 frames, 4 from each of the 10 held-out Big Broiler clips (092–101). The pen model has never seen this camera. Frames are 1280 px wide, run as 640 px tiles at confidence 0.25, the same settings as the live feed. Every box was reviewed by eye on zoomed crops (`dropping4-pen-fp-sheet.jpg`, where the number after each index is the confidence).

## Result: 34 boxes, 0 on a dropping

| Box is on | Count |
|---|---|
| Birds (feathers, dye marks, heads, leg tags) | 25 |
| Pen wall screw holes and marks | 6 |
| Equipment and overlay (drinker holder, feeder, timestamp text) | 3 |
| A dropping on the litter | **0** |

**Precision on real frames: 0/34. False alarms: 0.85 per frame.** The model's reported pen mAP50 of 0.875 was measured on *pasted* Machuve droppings, so it does not reflect real use.

## Why
1. **The training pastes don't look like pen droppings.** Machuve close-ups are bright, and many are yellow or green. Shrunk to 10–30 px, they become small colourful blobs, so the model fires on colourful or dark small things such as dye marks, heads, holes and drinker parts.
2. **Real droppings in the background frames were trained as "not a dropping".** Real droppings in the litter were never labelled, so every background frame taught the model to ignore them.
3. **The evaluation used the same synthetic process** as training, so it could not reveal points 1 and 2.

## Can we label real pen droppings here?
Not reliably. Even at full 2688 px resolution (`bigbroiler-093-litter-fullres.jpg`), individual droppings cannot be told apart from the shavings. A test set labelled from this footage would be guesses, so we did not make one.

## What this means
- **Whole-pen camera:** use it for **activity and behaviour**. The `models/behaviour-v1` models were tested on exactly these held-out clips. Do not show dropping detections from this view as observations.
- **Droppings:** only the **close-up** model is validated (`models/dropping4-laptop`, test mAP50 0.873 on close-ups). It needs a close view: a low camera, a dropping board or tray, or a manure belt.
- **To fix the pen model properly (beyond the hackathon):** collect footage where droppings are visible (higher resolution or closer camera), label real droppings, and evaluate on real labelled held-out cameras. If synthetic pasting is used, make it realistic (blending, camera blur and noise, the colours of real pen droppings) and never treat unlabelled real frames as dropping-free.
