"""Fine-tune the dropping detector on close-ups plus pen scale tiles, then score it the same way as before.

    python training/pen_scale.py all
    python training/pen_train.py --epochs 40

Starts from the final close-up model (models/dropping4-laptop), so close-up skill is kept while it learns
pen sized droppings and that hens and drinkers are not droppings. Early stopping watches the validation
camera, which is not in training. Writes the run (with results.csv, the per epoch curves) to
training/work/pen/runs and the scores of old and new model to training/work/pen/eval.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
from pen_scale import WORK  # noqa: E402

START = Path(os.environ.get("PEN_START", REPO / "models" / "dropping4-laptop" / "dropping4_yolo11n.pt"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--cache", default="disk", help="disk, ram, or none")
    ap.add_argument("--name", default="pen1")
    ap.add_argument("--workers", type=int, default=2, help="each worker loads CUDA, on Windows more than 2 can exhaust the page file")
    args = ap.parse_args()
    model = YOLO(str(START))
    model.train(data=str(WORK / "yolo" / "data.yaml"), imgsz=640, epochs=args.epochs, batch=args.batch, workers=args.workers,
                patience=args.patience, cache=False if args.cache == "none" else args.cache, project=str(WORK / "runs"), name=args.name, exist_ok=True,
                lr0=0.002, cos_lr=True, seed=0, deterministic=True, plots=True)
    best = WORK / "runs" / args.name / "weights" / "best.pt"
    subprocess.run([sys.executable, str(HERE / "pen_eval.py"), str(START), str(best), "--out", str(WORK / "eval.json")], check=True)
    for w, tag in ((START, "before"), (best, "after")):
        subprocess.run([sys.executable, str(HERE / "pen_tweaks.py"), str(w), "--zooms", "1,2,3",
                        "--out", str(WORK / f"tweaks_{tag}.json")], check=True, cwd=HERE)
    print(json.dumps(json.loads((WORK / "eval.json").read_text()), indent=1))


if __name__ == "__main__":
    main()
