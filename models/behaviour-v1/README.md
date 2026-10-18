# behaviour-v1: chicken detector + behaviour classifier

Trained on Veri (job `239ab41a5b75`, 4x A10G, ~44 min per model) from the Big Broiler dataset (Cardoen et al., CV4Animals 2025, AGPL-3.0). The split is by video, so these are honest numbers: the 10 held-out test clips (092–101, labelled by three annotators) were never seen in training.

## Pipeline on the Pi
```
frame -> chicken detector -> crop each bird -> behaviour classifier -> per-group metrics vs baseline
```
Example per-group metrics: % inactive, eating time, drinking time, panting rate, % moving. Alert when a group deviates from its own normal for that age and time of day. These are early-warning signs, not a diagnosis.

## Files
| File | Size | What |
|---|---|---|
| `chicken_yolo11n_{640,416,320}.onnx` | ~10.5 MB | 1-class chicken detector |
| `behaviour7_yolo11n-cls_224.onnx` | 6.2 MB | **Pi behaviour classifier** (small, fast) |
| `behaviour7_yolo11s-cls_224.onnx` | 21.8 MB | Larger behaviour classifier (more accurate, slower) |
| `test_metrics.json` | | Held-out test metrics for all three models |
| `SHA256SUMS` | | Checksums |

All files are ONNX opset 17 with static batch 1, exported by Ultralytics 8.3.253.

## Held-out test results
**Chicken detector** (610 test frames): mAP50 **0.927**, mAP50-95 0.562, precision 0.83, recall 0.93.

**Behaviour classifiers** (6,724 bird crops from the test clips):

| | YOLO11n-cls (Pi) | YOLO11s-cls |
|---|---|---|
| top-1 accuracy | 0.686 | **0.701** |
| top-5 accuracy | 0.988 | 0.991 |
| macro recall | 0.566 | **0.629** |
| inactive | **0.82** | 0.71 |
| **panting** | 0.80 | **0.83** |
| drinking | 0.69 | **0.87** |
| preening | **0.73** | 0.71 |
| eating | 0.45 | **0.75** |
| moving | 0.35 | **0.42** |
| other | 0.12 | 0.11 |

What the numbers mean in practice:
- **Panting (~0.8 recall)** and **inactive (0.82 for the n model)** are the two illness-relevant signals, and both are reliable.
- **Eating, drinking and moving** are much better with the s model. If the Pi has time per frame, use YOLO11s-cls for those.
- **"other"** is a grab-bag of rare actions (stretching, feather pecking, sneezing…) and isn't usable on its own.

## I/O format
- **Classifier**
  - Input `images`: float32 `[1, 3, 224, 224]`, RGB, values 0–1. Use a square crop around the bird box (box + ~15% margin), resized to 224.
  - Output `[1, 7]`: class probabilities in id order: 0 drinking, 1 eating, 2 inactive, 3 moving, 4 other, 5 panting, 6 preening.
- **Detector**
  - Input `[1, 3, S, S]`: letterboxed, RGB, values 0–1.
  - Output `[1, 5, N]` with N = 8400 / 3549 / 2100: center x, center y, width, height, chicken score.
  - Postprocess: apply a confidence threshold, then NMS.

## Known limitations
- **Detector confidence scores run low.** On 15 test frames it found 62% of the labelled birds at confidence 0.05, and only 26% at 0.35. The test recall of 0.93 is measured at a very low threshold. **Start with conf ≈ 0.05–0.1** and tune on real footage. Crowded or overlapping birds are often merged or missed.
- The detector was trained on setups 2 and 3 only (small pens). In setup 1, most birds are unlabelled, so those frames were excluded from detector training.
- These are Belgian research-pen broilers, aged 10–40 days. A different barn, camera angle or breed will reduce accuracy.
- Behaviour is classified from **one frame**. Short actions like sneezing or head shaking need temporal models, which is future work.

## Reproduce
- `training/prepare_behavior.py` builds the crops and detector frames.
- `training/run_behavior.sh` with `SAFE4=1 PREPARED=1` trains all three models on one 4-GPU node.
- `training/train_behavior.py` trains, tests and exports a single model.
