# Dropping detector models (YOLO11n, 4 classes)

Two trained versions of the same detector. Both used the same data, the same code (`training/`) and the same held-out test set (679 farm images never used in training).

| Folder | Trained on | Epochs (best) | Test mAP50 | Test mAP50-95 | Use for |
|---|---|---|---|---|---|
| [`dropping4-laptop/`](dropping4-laptop/) | Local RTX 3060 | 69 (49), early-stopped | **0.873** | 0.573 | **Default for the Pi** |
| [`dropping4-veri/`](dropping4-veri/) | Veri, A10G (job `abe1b30a56c4`) | 20 (19), 30-min cap | 0.854 | 0.573 | Veri track; near-identical accuracy |

Per-class test mAP50-95 (laptop / Veri):

| Class | Laptop | Veri |
|---|---|---|
| cocci | 0.653 | 0.652 |
| healthy | 0.700 | 0.697 |
| ncd | 0.341 | 0.345 |
| salmo | 0.598 | 0.598 |

## Classes
| id | class | product meaning |
|---|---|---|
| 0 | `cocci` | abnormal (coccidiosis-like) |
| 1 | `healthy` | normal |
| 2 | `ncd` | abnormal (Newcastle-like) |
| 3 | `salmo` | abnormal (salmonella-like) |

Per BIBLE.md, the product shows **normal / abnormal**. Disease names are only a hint for vet review, not a diagnosis.

## Files in each folder
- `dropping4_yolo11n_{640,416,320}.onnx`: ONNX opset 17, static batch 1, about 10.5 MB each. Use 640 for best accuracy and 320 for best speed on the Pi.
- `dropping4_yolo11n.pt`: Ultralytics weights, 5.5 MB. Use it to re-export, e.g. to TFLite if ONNX Runtime does not run on QNX 8.0.0.
- `test_metrics.json`: held-out test metrics, best epoch, and validation score at that epoch.
- `results.png`: training curves. `confusion_matrix_normalized.png`: validation confusion matrix.
- `SHA256SUMS`: checksums.

## Input / output (ONNX Runtime / C++)
- **Input** `images`: float32 `[1, 3, S, S]`, S = 640 / 416 / 320. RGB, values 0–1 (pixel / 255), NCHW. Letterbox the frame to S×S keeping aspect ratio, and pad with gray (114/255).
- **Output** `output0`: float32 `[1, 8, N]`, N = 8400 / 3549 / 2100 candidates.
  - Rows 0–3: box center x, center y, width, height in input pixels (letterboxed space).
  - Rows 4–7: class scores for cocci, healthy, ncd, salmo, already sigmoid. There is no objectness score.
- **Postprocess:** for each candidate take the max class score, keep it if score ≥ 0.25, run NMS (IoU 0.45–0.7), then undo the letterbox scale and padding.

## Quick test on a laptop
```python
from ultralytics import YOLO
m = YOLO("models/dropping4-laptop/dropping4_yolo11n_640.onnx", task="detect")
m.predict("dropping_photo.jpg", conf=0.25, save=True)
```

## Caveats
- The split is random by photo, so the same farm or visit can appear in both train and test. Real-barn accuracy will be lower.
- Training images are close-up phone photos from Tanzanian farms, so the camera must be close to the floor.
- NCD is the weak class: 384 boxes, mAP50-95 about 0.34.
- The PCR lab-confirmed evaluation has not been run yet.

## Provenance
- Data: Machuve et al., Zenodo [10.5281/zenodo.4628934](https://doi.org/10.5281/zenodo.4628934), CC BY 4.0. Farm images with official YOLO boxes; 80/10/10 split by class, seed 0; NCD oversampled 3× in train only.
- Base model: YOLO11n COCO-pretrained (Ultralytics 8.3.253, AGPL-3.0). Settings: 640 px, AdamW (auto), patience 20.
