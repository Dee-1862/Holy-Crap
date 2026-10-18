"""Train one Big Broiler model: behaviour classifier (--task cls) or chicken detector (--task det).

Evaluates on the held-out test videos and exports ONNX. Metrics go to Veri (prefixed with
--name) when $VERI_METRICS_FILE is set. Several of these run in parallel, one per GPU.

  python train_behavior.py --task cls --data work_bb/behaviour --name cls_n --model yolo11n-cls.pt
  python train_behavior.py --task det --data work_bb/chickens/data.yaml --name det --model yolo11n.pt
"""
import argparse
import json
import os
import shutil
import traceback
from pathlib import Path

from ultralytics import YOLO

import train as base  # log(), pipe_transport_loading()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["cls", "det"], required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--hours", type=float, default=None)
    ap.add_argument("--imgsz", type=int, default=None)
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--gpus", type=int, default=1, help=">1 = multi-GPU (DDP); batch is per GPU")
    ap.add_argument("--export-sizes", default=None)
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("VERI_OUTPUT_DIR", "outputs")))
    args = ap.parse_args()
    out = args.out / args.name
    out.mkdir(parents=True, exist_ok=True)
    imgsz = args.imgsz or (224 if args.task == "cls" else 640)
    batch = args.batch or (256 if args.task == "cls" else 32)

    try:
        shm_gb = shutil.disk_usage("/dev/shm").total / 1e9
    except OSError:
        shm_gb = None
    if shm_gb is not None and shm_gb < 1:
        base.pipe_transport_loading()

    def on_epoch(trainer):
        m = dict(trainer.metrics)
        loss = trainer.label_loss_items(trainer.tloss, prefix="train")
        m.update(loss if isinstance(loss, dict) else {"train_loss": float(trainer.tloss)})
        base.log(step=trainer.epoch + 1, **{f"{args.name}_{k}": float(v) for k, v in m.items()})

    model = YOLO(args.model)
    model.add_callback("on_fit_epoch_end", on_epoch)
    kw = dict(data=args.data, epochs=args.epochs, imgsz=imgsz, batch=batch * max(1, args.gpus),
              workers=args.workers, patience=15, seed=0, project=str(out), name="train", exist_ok=True, plots=True)
    if args.gpus > 1:
        kw["device"] = list(range(args.gpus))  # DDP; our callback doesn't run in the DDP workers
    if args.hours:
        kw["time"] = args.hours
    print(f"[{args.name}] training {args.model} imgsz={imgsz} batch={kw['batch']} gpus={args.gpus} "
          f"hours={args.hours}", flush=True)
    stop = None
    if args.gpus > 1:
        import csv
        import threading

        stop = threading.Event()
        rc, logged = out / "train" / "results.csv", set()

        def follow():  # DDP workers don't run our callback; follow results.csv instead
            while True:
                if rc.exists():
                    for row in csv.DictReader(open(rc)):
                        row = {k.strip(): v for k, v in row.items()}
                        e = int(float(row.pop("epoch")))
                        if e not in logged:
                            logged.add(e)
                            base.log(step=e, **{f"{args.name}_{k}": float(v) for k, v in row.items() if v})
                if stop.wait(20):
                    break

        t = threading.Thread(target=follow, daemon=True)
        t.start()
    model.train(**kw)
    if stop:
        stop.set()
        t.join()

    best = out / "train" / "weights" / "best.pt"
    model = YOLO(str(best))
    summary = {"name": args.name, "model": args.model, "task": args.task}
    test = model.val(data=args.data, split="test", imgsz=imgsz, batch=batch, workers=args.workers,
                     project=str(out), name="test", exist_ok=True, plots=True)
    if args.task == "cls":
        names = model.names
        cm = test.confusion_matrix.matrix  # rows = predicted, cols = true
        per_class = {names[i]: float(cm[i, i] / max(1, cm[:, i].sum())) for i in range(len(names))}
        summary["test"] = {"top1": float(test.top1), "top5": float(test.top5),
                           "per_class_recall": per_class,
                           "macro_recall": sum(per_class.values()) / len(per_class)}
        base.log(step=None, **{f"{args.name}_test_top1": float(test.top1),
                               f"{args.name}_test_macro_recall": summary["test"]["macro_recall"]})
    else:
        summary["test"] = {"mAP50": float(test.box.map50), "mAP50_95": float(test.box.map),
                           "precision": float(test.box.mp), "recall": float(test.box.mr)}
        base.log(step=None, **{f"{args.name}_test_mAP50": float(test.box.map50),
                               f"{args.name}_test_mAP50_95": float(test.box.map)})

    sizes = args.export_sizes or ("224" if args.task == "cls" else "640,416,320")
    exports = {}
    for s in [int(x) for x in sizes.split(",")]:
        try:
            p = YOLO(str(best)).export(format="onnx", imgsz=s, opset=17, simplify=True)
            dst = out / "export" / f"{args.name}_{s}.onnx"
            dst.parent.mkdir(exist_ok=True)
            shutil.copy(p, dst)
            exports[s] = str(dst)
        except Exception:
            exports[s] = "FAILED: " + traceback.format_exc(limit=1).strip().splitlines()[-1]
        print(f"[{args.name}] export {s} {exports[s]}", flush=True)
    summary["exports"] = exports
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"[{args.name}] SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
