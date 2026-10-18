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
    ap.add_argument("--start", default=str(START), help="weights to start from, e.g. yolo11s.pt for the larger model")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--lr0", type=float, default=0.002, help="low because it starts from a trained dropping model")
    ap.add_argument("--data", default="data.yaml", help="data.yaml, or data_more.yaml for the extra pen tiles")
    ap.add_argument("--hours", type=float, default=None, help="wall clock cap on training, overrides epochs")
    ap.add_argument("--resume", action="store_true", help="continue runs/NAME from its last.pt with its saved settings")
    args = ap.parse_args()
    run = WORK / "runs" / args.name
    if args.resume:
        YOLO(str(run / "weights" / "last.pt")).train(resume=True)
    else:
        train(args)
    evaluate(args, run)


def train(args):
    model = YOLO(args.start)
    extra = {"time": args.hours} if args.hours else {}
    model.train(data=str(WORK / "yolo" / args.data), imgsz=args.imgsz, epochs=args.epochs, batch=args.batch, workers=args.workers,
                patience=args.patience, cache=False if args.cache == "none" else args.cache, project=str(WORK / "runs"), name=args.name, exist_ok=True,
                lr0=args.lr0, cos_lr=True, seed=0, deterministic=True, plots=True, **extra)


def evaluate(args, run):
    best = run / "weights" / "best.pt"
    subprocess.run([sys.executable, str(HERE / "pen_eval.py"), str(START), str(best), "--imgsz", str(args.imgsz), "--out", str(run / "eval.json")], check=True)
    for w, tag, size in ((START, "before", 640), (best, "after", args.imgsz)):
        subprocess.run([sys.executable, str(HERE / "pen_tweaks.py"), str(w), "--zooms", "1,2,3", "--imgsz", str(size),
                        "--out", str(run / f"tweaks_{tag}.json")], check=True, cwd=HERE)
    print(json.dumps(json.loads((run / "eval.json").read_text()), indent=1))


if __name__ == "__main__":
    main()
