"""Retrain the photo classifiers earlier papers used, on our split, and test them on the same photos as our detector.

    python training/benchmark_classifiers.py cache     decode every farm and lab-confirmed photo once, 240 by 240
    python training/benchmark_classifiers.py train     train each model with three seeds, score every test photo
    python training/benchmark_classifiers.py export    ONNX files of seed 0, for timing on the Pi
    python training/benchmark_classifiers.py all

Why: published accuracies on the Machuve photos (about 98 to 99%) come from different splits and setups, so they
cannot be compared with ours directly. Here every model gets the same training photos (the split in
data-visualization/results/farm_hashes.csv, the one our detector was trained on), the same 679 held-out farm test
photos and the same 1,255 lab-confirmed (PCR) photos from Zenodo 5801834, which no model ever trains on.

Models, all ImageNet pretrained (torchvision) and fine-tuned whole:
    mobilenet_v2      recommended for deployment by Machuve et al. 2022
    efficientnet_b0   the classifier stage of the YOLO11 plus EfficientNet-B0 pipeline (AgriEngineering 2025)
    resnet50          a heavier reference

Photos are resized to 224 by 224 without keeping the aspect ratio, as in the 224 pixel Kaggle copy those papers
used. Training augmentation is crops, flips and small brightness and contrast changes, no hue change, because
colour is the main sign of disease. The epoch with the best validation accuracy is kept.

Needs the photo zips from data-visualization/audit_images.py in data-visualization/data/raw (about 13 GB, git ignored)
and a CUDA PyTorch. Writes small CSV files to data-visualization/results/.
"""
from __future__ import annotations

import argparse
import io
import json
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data-visualization" / "data" / "raw"
RESULTS = REPO / "data-visualization" / "results"
WORK = REPO / "training" / "work" / "bench"
CLASSES = ["cocci", "healthy", "ncd", "salmo"]          # same order as the detector
MODELS = ["mobilenet_v2", "efficientnet_b0", "resnet50"]
SEEDS = [0, 1, 2]
CACHE_SIDE, SIDE = 240, 224
EPOCHS, BATCH = 20, 64


# ---------------------------------------------------------------- photos, decoded once
_tls = threading.local()


def decode(zpath: Path, member: str) -> np.ndarray:
    zips = _tls.__dict__.setdefault("zips", {})            # one open zip per thread, so threads never share a position
    if zpath not in zips:
        zips[zpath] = zipfile.ZipFile(zpath)
    im = Image.open(io.BytesIO(zips[zpath].read(member)))
    im.draft("RGB", (CACHE_SIDE * 2, CACHE_SIDE * 2))      # fast JPEG downscale while decoding
    return np.asarray(im.convert("RGB").resize((CACHE_SIDE, CACHE_SIDE), Image.BILINEAR), dtype=np.uint8)


def cache_set(name: str, rows: pd.DataFrame, zip_of) -> None:
    out = WORK / f"{name}.npz"
    if out.exists():
        print(name, "already cached", flush=True)
        return
    jobs = [(zip_of(r), r.member.split("/", 1)[1]) for r in rows.itertuples()]
    t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        imgs = list(ex.map(lambda j: decode(*j), jobs))
    np.savez(out, x=np.stack(imgs), y=rows.cls.map(CLASSES.index).to_numpy(), member=rows.member.to_numpy(),
             split=rows.split.to_numpy())
    print(f"{name}: {len(imgs)} photos cached in {time.time() - t0:.0f} s", flush=True)


def cmd_cache(_):
    WORK.mkdir(parents=True, exist_ok=True)
    farm = pd.read_csv(RESULTS / "farm_hashes.csv")
    farm = farm[farm.split.isin(["train", "val", "test"])]
    cache_set("farm", farm, lambda r: RAW / f"{r.cls}.zip")
    pcr = pd.read_csv(RESULTS / "pcr_predictions.csv").rename(columns={"true": "cls"}).assign(split="pcr")
    cache_set("pcr", pcr, lambda r: RAW / f"pcr{r.cls}.zip")


# ---------------------------------------------------------------- training
def build(name: str, torch, tv):
    w = {"mobilenet_v2": tv.models.MobileNet_V2_Weights.IMAGENET1K_V2, "efficientnet_b0": tv.models.EfficientNet_B0_Weights.IMAGENET1K_V1,
         "resnet50": tv.models.ResNet50_Weights.IMAGENET1K_V2}[name]
    m = getattr(tv.models, name)(weights=w)
    if name == "resnet50":
        m.fc = torch.nn.Linear(m.fc.in_features, len(CLASSES))
    else:
        m.classifier[-1] = torch.nn.Linear(m.classifier[-1].in_features, len(CLASSES))
    return m


def batches(x, y, idx, bs):
    for i in range(0, len(idx), bs):
        j = idx[i:i + bs]
        yield x[j], y[j]


def to_input(xb, torch, dev, train: bool, gen=None):
    """uint8 N,240,240,3 to normalised float N,3,224,224 on the GPU. Train: random crop, flips, brightness, contrast."""
    t = torch.from_numpy(xb).to(dev).permute(0, 3, 1, 2).float() / 255
    if train:
        n = t.shape[0]
        i, j = np.random.randint(0, CACHE_SIDE - SIDE + 1, 2)
        t = t[:, :, i:i + SIDE, j:j + SIDE]
        flip = torch.rand(n, device=dev) < 0.5
        t[flip] = t[flip].flip(3)
        flip = torch.rand(n, device=dev) < 0.5
        t[flip] = t[flip].flip(2)
        b = 1 + (torch.rand(n, 1, 1, 1, device=dev) - 0.5) * 0.3
        c = 1 + (torch.rand(n, 1, 1, 1, device=dev) - 0.5) * 0.3
        mean = t.mean((1, 2, 3), keepdim=True)
        t = ((t - mean) * c + mean * b).clamp(0, 1)
    else:
        t = torch.nn.functional.interpolate(t, size=(SIDE, SIDE), mode="bilinear", align_corners=False)
    m = torch.tensor([0.485, 0.456, 0.406], device=dev).view(1, 3, 1, 1)
    s = torch.tensor([0.229, 0.224, 0.225], device=dev).view(1, 3, 1, 1)
    return (t - m) / s


def predict(model, x, torch, dev):
    model.eval()
    out = []
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        for xb, _ in batches(x, np.zeros(len(x)), np.arange(len(x)), 128):
            out.append(torch.softmax(model(to_input(xb, torch, dev, False)).float(), 1).cpu().numpy())
    return np.concatenate(out)


def train_one(name: str, seed: int, farm, pcr, torch, tv, dev):
    torch.manual_seed(seed); np.random.seed(seed)
    x, y, split = farm["x"], farm["y"], farm["split"]
    tr, va = np.where(split == "train")[0], np.where(split == "val")[0]
    model = build(name, torch, tv).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3 if name != "resnet50" else 5e-4, weight_decay=1e-4)
    steps = EPOCHS * ((len(tr) + BATCH - 1) // BATCH)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=opt.param_groups[0]["lr"], total_steps=steps, pct_start=0.1)
    scaler = torch.amp.GradScaler()
    lossf = torch.nn.CrossEntropyLoss()
    best, best_state, log = -1.0, None, []
    t0 = time.time()
    for ep in range(1, EPOCHS + 1):
        model.train()
        order = np.random.permutation(tr)
        total = 0.0
        for xb, yb in batches(x, y, order, BATCH):
            with torch.autocast("cuda", dtype=torch.float16):
                loss = lossf(model(to_input(xb, torch, dev, True)), torch.from_numpy(yb).to(dev))
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt); scaler.update(); sched.step()
            total += float(loss) * len(yb)
        acc = float((predict(model, x[va], torch, dev).argmax(1) == y[va]).mean())
        log.append({"model": name, "seed": seed, "epoch": ep, "train_loss": total / len(tr), "val_acc": acc})
        if acc > best:
            best, best_state = acc, {k: v.detach().clone() for k, v in model.state_dict().items()}
        print(f"  {name} seed {seed} epoch {ep}: loss {total / len(tr):.3f} val {acc:.4f}", flush=True)
    model.load_state_dict(best_state)
    torch.save(best_state, WORK / f"{name}_seed{seed}.pt")
    rows = []
    for setname, d, keep in (("farm_test", farm, split == "test"), ("pcr", pcr, np.ones(len(pcr["y"]), bool))):
        p = predict(model, d["x"][keep], torch, dev)
        for mem, t, pr in zip(d["member"][keep], d["y"][keep], p):
            rows.append({"model": name, "seed": seed, "set": setname, "member": mem, "true": CLASSES[t],
                         **{f"p_{c}": round(float(v), 4) for c, v in zip(CLASSES, pr)}})
    print(f"{name} seed {seed}: best val {best:.4f}, {time.time() - t0:.0f} s", flush=True)
    return rows, log


def cmd_train(args):
    import torch
    import torchvision as tv
    dev = "cuda"
    torch.backends.cudnn.benchmark = True
    farm, pcr = dict(np.load(WORK / "farm.npz", allow_pickle=True)), dict(np.load(WORK / "pcr.npz", allow_pickle=True))
    pred_path, log_path = RESULTS / "benchmark_predictions.csv", RESULTS / "benchmark_training_log.csv"
    done = set()
    if pred_path.exists():
        old = pd.read_csv(pred_path)
        done = set(zip(old.model, old.seed))
    for name in args.models or MODELS:
        for seed in SEEDS:
            if (name, seed) in done:
                print(name, seed, "already done", flush=True)
                continue
            rows, log = train_one(name, seed, farm, pcr, torch, tv, dev)
            pd.DataFrame(rows).to_csv(pred_path, mode="a", header=not pred_path.exists(), index=False)
            pd.DataFrame(log).to_csv(log_path, mode="a", header=not log_path.exists(), index=False)


def cmd_export(_):
    import torch
    import torchvision as tv
    meta = {}
    for name in MODELS:
        m = build(name, torch, tv)
        m.load_state_dict(torch.load(WORK / f"{name}_seed0.pt", map_location="cpu"))
        m.eval()
        out = WORK / f"{name}_224.onnx"
        torch.onnx.export(m, torch.zeros(1, 3, SIDE, SIDE), str(out), input_names=["images"], output_names=["logits"],
                          opset_version=17, dynamo=False)
        meta[name] = {"onnx": out.name, "params": sum(p.numel() for p in m.parameters()), "bytes": out.stat().st_size}
        print(name, meta[name], flush=True)
    (RESULTS / "benchmark_models.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("job", choices=["cache", "train", "export", "all"])
    ap.add_argument("--models", nargs="*")
    a = ap.parse_args()
    if a.job in ("cache", "all"):
        cmd_cache(a)
    if a.job in ("train", "all"):
        cmd_train(a)
    if a.job in ("export", "all"):
        cmd_export(a)
