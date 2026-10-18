# dropping4-e37: YOLO11n poultry dropping detector (interim snapshot)

Interim checkpoint taken at **epoch 37 of 100** while training continues on the laptop (RTX 3060). A final model will replace it. The point of this snapshot is so the Pi integration can start now.

## What it does
It detects droppings and classifies each one into 4 classes:

| id | class | meaning |
|---|---|---|
| 0 | `cocci` | coccidiosis-like appearance |
| 1 | `healthy` | normal dropping |
| 2 | `ncd` | Newcastle-disease-like appearance |
| 3 | `salmo` | salmonella-like appearance |

Product wording (BIBLE.md): show **abnormal / normal**, not disease names. Any class other than `healthy` counts as abnormal.

## Files
| File | Size | Use |
|---|---|---|
| `dropping4_yolo11n_640.onnx` | 10.6 MB | Most accurate |
| `dropping4_yolo11n_416.onnx` | 10.5 MB | Pi middle ground |
| `dropping4_yolo11n_320.onnx` | 10.5 MB | Fastest on Pi |
| `dropping4_yolo11n.pt` | 5.5 MB | Ultralytics/PyTorch weights (re-export, TFLite conversion) |
| `test_metrics.json` | | Held-out test results (640 ONNX) |
| `SHA256SUMS` | | Checksums |

ONNX files: opset 17, static batch 1, exported with Ultralytics 8.3.253.

## Input / output (for the C++ / ONNX Runtime side)
- **Input** `images`: float32 `[1, 3, S, S]` (S = 640 / 416 / 320), **RGB**, values **0–1** (divide by 255), NCHW. Letterbox the frame to S×S keeping aspect ratio and pad with gray (114).
- **Output** `output0`: float32 `[1, 8, N]` with N = 8400 / 3549 / 2100 candidate boxes.
  - Rows 0–3: box center x, center y, width, height in **input pixels** (letterboxed space).
  - Rows 4–7: per-class scores for cocci, healthy, ncd, salmo (already sigmoid). There is **no separate objectness** score.
- **Postprocess:** for each candidate, take max class score → keep if ≥ conf (start at 0.25) → NMS with IoU 0.45–0.7 → undo the letterbox to get frame coordinates.

## Accuracy
Held-out **test** split: 679 farm images never used in training. 640 ONNX on CPU:

| | mAP50 | mAP50-95 |
|---|---|---|
| **all** | **0.845** | **0.561** |
| cocci | 0.820 | 0.629 |
| healthy | 0.867 | 0.685 |
| ncd | 0.782 | 0.346 |
| salmo | 0.913 | 0.585 |

Precision 0.839, recall 0.782.

Caveats:
- The split is random by photo, so the same farm/visit can appear in train and test. Expect real-barn performance to be lower.
- The images are close-up phone photos, so the camera must be close to the floor.
- NCD is the rare class (384 boxes).
- The PCR lab-confirmed check has not been run yet.

## Provenance
- Data: Machuve et al., Zenodo 10.5281/zenodo.4628934 (CC BY 4.0): farm images with official YOLO boxes. The split is 80/10/10 by class, seed 0, with NCD oversampled 3× in train only.
- Training: `training/train.py` from YOLO11n COCO-pretrained, 640 px, batch 16, local RTX 3060.

## Quick test on a laptop
```python
from ultralytics import YOLO
m = YOLO("dropping4_yolo11n_640.onnx", task="detect")
m.predict("some_dropping_photo.jpg", conf=0.25, save=True)
```
