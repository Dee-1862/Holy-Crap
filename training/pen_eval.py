"""Score a dropping model on close-ups and on pen scale tiles, before and after pen training.

    python training/pen_eval.py MODEL.pt [MODEL.pt ...] --out training/work/pen/eval.json

Three tests, all built by pen_scale.py and never trained on:
- closeup_test: the held out Machuve test photos, 4 classes, the number the original model reported
- pen_test: test droppings pasted onto frames from a farm not used in training (synthetic)
- pen_test_real: frames from that farm with nothing pasted, every box there is counted
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ultralytics import YOLO

from pen_scale import WORK

Y = WORK / "yolo"


def boxes_per_tile(model: YOLO, listfile: Path, conf: float, imgsz: int) -> float:
    paths = [p for p in listfile.read_text().split() if p]
    total = 0
    for i in range(0, len(paths), 32):
        for r in model.predict(paths[i:i + 32], imgsz=imgsz, conf=conf, verbose=False):
            total += len(r.boxes)
    return total / len(paths)


def score(weights: str, imgsz: int) -> dict:
    m = YOLO(weights)
    out = {"model": weights, "imgsz": imgsz}
    v = m.val(data=str(Y / "closeup_test.yaml"), imgsz=imgsz, batch=16, workers=1, verbose=False, plots=False)
    out["closeup_test_map50"] = round(float(v.box.map50), 4)
    out["closeup_test_map50_95"] = round(float(v.box.map), 4)
    # where a dropping is matters more than its disease name at pen scale, so score it as one class too
    v = m.val(data=str(Y / "pen_test.yaml"), imgsz=imgsz, batch=16, workers=1, single_cls=True, verbose=False, plots=False)
    out["pen_test_map50_any_class"] = round(float(v.box.map50), 4)
    out["pen_test_recall_any_class"] = round(float(v.box.mr), 4)
    out["pen_test_precision_any_class"] = round(float(v.box.mp), 4)
    v = m.val(data=str(Y / "pen_test.yaml"), imgsz=imgsz, batch=16, workers=1, verbose=False, plots=False)
    out["pen_test_map50_4class"] = round(float(v.box.map50), 4)
    for conf in (0.25, 0.4):
        out[f"pen_test_real_boxes_per_tile_conf{conf}"] = round(boxes_per_tile(m, Y / "pen_test_real.txt", conf, imgsz), 3)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", nargs="+")
    ap.add_argument("--out", type=Path, default=Y.parent / "eval.json")
    ap.add_argument("--imgsz", type=int, default=640, help="for the new model, the old one is always scored at 640")
    args = ap.parse_args()
    rows = [score(w, 640 if i == 0 and len(args.weights) > 1 else args.imgsz) for i, w in enumerate(args.weights)]
    args.out.write_text(json.dumps(rows, indent=2))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
