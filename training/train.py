"""Train a 4-class YOLO11n dropping detector, evaluate it, and export ONNX/TFLite.

Writes everything to $VERI_OUTPUT_DIR (or --out). Metrics go to Veri via veri_sdk
when $VERI_METRICS_FILE is set.

  python train.py --data work/yolo/data.yaml --pcr work/pcr --epochs 2 --imgsz 320   # smoke
  python train.py --data work/yolo/data.yaml --pcr work/pcr --hours 2                 # full
"""
import argparse
import json
import os
import re
import shutil
import traceback
from pathlib import Path

from ultralytics import YOLO

try:
    import veri_sdk
except ImportError:
    veri_sdk = None

CLASSES = ["cocci", "healthy", "ncd", "salmo"]


def log(step=None, **scalars):
    clean = {re.sub(r"[^0-9A-Za-z]+", "_", k).strip("_"): v for k, v in scalars.items()}
    if veri_sdk:
        veri_sdk.log_metrics(step=step, **clean)
    print("metrics", step, json.dumps(clean, default=float), flush=True)


def on_fit_epoch_end(trainer):
    scalars = dict(trainer.metrics)
    scalars.update(trainer.label_loss_items(trainer.tloss, prefix="train"))
    log(step=trainer.epoch + 1, **{k: float(v) for k, v in scalars.items()})


def eval_pcr(model, pcr_dir, imgsz):
    """Image-level disease accuracy on lab-confirmed (PCR) images: class of the top box."""
    confusion = {t: {p: 0 for p in CLASSES + ["none"]} for t in CLASSES}
    for true in CLASSES:
        paths = sorted((pcr_dir / true).glob("*.jpg"))
        for i in range(0, len(paths), 32):
            for r in model.predict([str(p) for p in paths[i:i + 32]], imgsz=imgsz, conf=0.1, verbose=False):
                if len(r.boxes):
                    pred = CLASSES[int(r.boxes.cls[r.boxes.conf.argmax()])]
                else:
                    pred = "none"
                confusion[true][pred] += 1
    total = sum(sum(row.values()) for row in confusion.values())
    correct = sum(confusion[c][c] for c in CLASSES)
    recall = {c: confusion[c][c] / max(1, sum(confusion[c].values())) for c in CLASSES}
    abnormal = [c for c in CLASSES if c != "healthy"]
    # normal/abnormal view: healthy vs any disease (what the product shows)
    tp = sum(confusion[t][p] for t in abnormal for p in abnormal)
    fn = sum(confusion[t][p] for t in abnormal for p in ["healthy", "none"])
    tn = confusion["healthy"]["healthy"] + confusion["healthy"]["none"]
    fp = sum(confusion["healthy"][p] for p in abnormal)
    return {
        "images": total,
        "accuracy_4class": correct / max(1, total),
        "recall": recall,
        "abnormal_sensitivity": tp / max(1, tp + fn),
        "abnormal_specificity": tn / max(1, tn + fp),
        "confusion": confusion,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--pcr", type=Path)
    ap.add_argument("--model", default="yolo11n.pt")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--hours", type=float, default=None, help="wall-clock cap; overrides --epochs")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--workers", type=int, default=min(16, os.cpu_count() or 4))
    ap.add_argument("--cache", default="ram", help="ram | disk | none; ram avoids re-decoding JPEGs each epoch")
    ap.add_argument("--export-sizes", default="640,416,320")
    ap.add_argument("--formats", default="onnx,tflite,tflite_int8")
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("VERI_OUTPUT_DIR", "outputs")))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.model)
    model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
    train_kw = dict(data=args.data, epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                    workers=args.workers, patience=20, seed=0, project=str(args.out), name="train",
                    exist_ok=True, plots=True, cache=False if args.cache == "none" else args.cache)
    print(f"cpu_count={os.cpu_count()} workers={args.workers} cache={args.cache}", flush=True)
    if args.hours:
        train_kw["time"] = args.hours
    model.train(**train_kw)

    best = args.out / "train" / "weights" / "best.pt"
    model = YOLO(str(best))
    summary = {"weights": str(best)}

    test = model.val(data=args.data, split="test", imgsz=args.imgsz, project=str(args.out), name="test",
                     exist_ok=True, plots=True)
    summary["test_box"] = {
        "mAP50": float(test.box.map50),
        "mAP50_95": float(test.box.map),
        "per_class_mAP50_95": {CLASSES[i]: float(m) for i, m in zip(test.box.ap_class_index, test.box.maps[test.box.ap_class_index])},
    }
    log(step=None, test_mAP50=summary["test_box"]["mAP50"], test_mAP50_95=summary["test_box"]["mAP50_95"])

    if args.pcr and args.pcr.exists():
        summary["pcr"] = eval_pcr(model, args.pcr, args.imgsz)
        log(step=None, pcr_accuracy_4class=summary["pcr"]["accuracy_4class"],
            pcr_abnormal_sensitivity=summary["pcr"]["abnormal_sensitivity"],
            pcr_abnormal_specificity=summary["pcr"]["abnormal_specificity"])

    exports = {}
    for size in [int(s) for s in args.export_sizes.split(",") if s]:
        for fmt, kw in [("onnx", {}), ("tflite", {}), ("tflite_int8", {"int8": True, "data": args.data})]:
            if fmt not in args.formats.split(","):
                continue
            key = f"{fmt}_{size}"
            try:
                path = YOLO(str(best)).export(format=fmt.split("_")[0], imgsz=size, **kw)
                dst = args.out / "export" / f"dropping4_{key}{Path(path).suffix}"
                dst.parent.mkdir(exist_ok=True)
                shutil.copy(path, dst)
                exports[key] = str(dst)
            except Exception:
                exports[key] = "FAILED: " + traceback.format_exc(limit=1).strip().splitlines()[-1]
            print("export", key, exports[key], flush=True)
    summary["exports"] = exports

    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
