"""Teach the dropping detector the size droppings have in a pen camera.

The close-up model fails on pen footage: a dropping fills a tenth of a close-up photo but only
8 to 30 pixels of a pen frame, and the model boxes hens and drinkers instead. This script builds
a pen-scale training set by pasting real labelled droppings, shrunk to pen size, onto empty litter
in real barn video frames, then mixes it with the original close-up data.

Keeping it honest:
- Droppings come from the Machuve split used by training/prepare_data.py. Train droppings go
  into train tiles, val into val, test into test. The test droppings were never trained on.
- Backgrounds come from a different farm for test. PIO (one commercial house) is train and val.
  NESTLER (another farm) is test only.
- The pasted test set is synthetic. It measures whether the model can find a dropping of pen size
  on litter it never saw, not field accuracy. Real NESTLER frames with nothing pasted are kept as
  a second test to count boxes the model puts on birds and equipment.

    python training/pen_scale.py bank      cut droppings out of the close-up photos
    python training/pen_scale.py frames    sample background frames from the barn videos
    python training/pen_scale.py build     write the YOLO dataset (close-ups plus pen tiles)
    python training/pen_scale.py all       all three
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data-visualization" / "data" / "raw"                 # Machuve zips, md5 checked by the audit
SPLIT_CSV = REPO / "data-visualization" / "results" / "farm_hashes.csv"
VIDEOS = REPO / "app" / "console" / "media" / "raw"
WORK = REPO / "training" / "work" / "pen"
CLASSES = ["cocci", "healthy", "ncd", "salmo"]
TILE = 640
FRAME_W = 1280                    # pen frames are handled at this width, the Pi camera's 720p mode
SIZE_PX = (8, 30)                 # longest side of a pasted dropping in a 1280 wide pen frame
SEED = 0


# ---------------------------------------------------------------- 1. droppings bank
def cutout(img: np.ndarray, box) -> np.ndarray | None:
    """Cut one dropping out of its labelled box with GrabCut, as BGRA trimmed to the dropping."""
    x1, y1, x2, y2 = box
    pad = max(6, (x2 - x1) // 8)
    X1, Y1 = max(0, x1 - pad), max(0, y1 - pad)
    X2, Y2 = min(img.shape[1], x2 + pad), min(img.shape[0], y2 + pad)
    crop = img[Y1:Y2, X1:X2].copy()
    if min(crop.shape[:2]) < 24 or x2 - x1 < 12 or y2 - y1 < 12:
        return None
    mask = np.zeros(crop.shape[:2], np.uint8)
    try:
        cv2.grabCut(crop, mask, (x1 - X1, y1 - Y1, x2 - x1, y2 - y1),
                    np.zeros((1, 65)), np.zeros((1, 65)), 3, cv2.GC_INIT_WITH_RECT)
    except cv2.error:
        return None
    fg = np.isin(mask, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n < 2:
        return None
    fg = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    share = fg.sum() / ((x2 - x1) * (y2 - y1))
    if not 0.15 < share < 0.95:                                    # GrabCut took nothing or the whole box
        return None
    ys, xs = np.nonzero(fg)
    alpha = cv2.GaussianBlur(fg.astype(np.float32), (0, 0), 1.5)
    out = np.dstack([crop, (alpha * 255).astype(np.uint8)])
    return out[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def bank_job(job):
    cls, stem, split, lines = job
    with zipfile.ZipFile(RAW / f"{cls}.zip") as z:
        names = [n for n in z.namelist() if n.endswith(f"/{stem}.jpg")]
        if not names:
            return []
        img = cv2.imdecode(np.frombuffer(z.read(names[0]), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    H, W = img.shape[:2]
    if max(H, W) > 1600:                                           # GrabCut on 3200 px photos is slow and needs no detail
        s = 1600 / max(H, W)
        img, H, W = cv2.resize(img, (round(W * s), round(H * s)), interpolation=cv2.INTER_AREA), round(H * s), round(W * s)
    done = []
    for k, (cx, cy, bw, bh) in enumerate(lines[:2]):
        box = (int((cx - bw / 2) * W), int((cy - bh / 2) * H), int((cx + bw / 2) * W), int((cy + bh / 2) * H))
        rgba = cutout(img, box)
        if rgba is None:
            continue
        name = f"{cls}_{stem.split('.')[-1]}_{k}.png"
        cv2.imwrite(str(WORK / "bank" / split / name), rgba)
        done.append({"file": name, "cls": cls, "split": split, "photo": f"{cls}/{stem}.jpg"})
    return done


def cmd_bank(args):
    split_of = pd.read_csv(SPLIT_CSV).set_index(["cls", "stem"]).split.to_dict()
    labels = zipfile.ZipFile(RAW / "imgObjDet_Yolo.zip")
    rng = random.Random(SEED)
    cap = {"train": 500, "val": 60, "test": 120}                   # photos per class and split
    jobs = []
    for cls in CLASSES:
        by_split = {"train": [], "val": [], "test": []}
        for name in labels.namelist():
            p = name.split("/")
            if len(p) != 3 or p[1] != cls or not p[2].endswith(".txt") or p[2] == "classes.txt":
                continue
            stem = p[2][:-4]
            split = split_of.get((cls, stem))
            lines = [tuple(map(float, l.split()[1:])) for l in labels.read(name).decode(errors="ignore").splitlines() if len(l.split()) == 5]
            if split in by_split and lines:
                by_split[split].append((cls, stem, split, lines))
        for split, js in by_split.items():
            rng.shuffle(js)
            jobs += js[:cap[split]]
    for split in ("train", "val", "test"):
        (WORK / "bank" / split).mkdir(parents=True, exist_ok=True)
    index = []
    with ProcessPoolExecutor(args.workers) as ex:
        for i, got in enumerate(ex.map(bank_job, jobs, chunksize=4)):
            index += got
            if i % 250 == 0:
                print(f"bank: {i}/{len(jobs)} photos, {len(index)} droppings", flush=True)
    (WORK / "bank" / "index.json").write_text(json.dumps(index, indent=0))
    df = pd.DataFrame(index)
    print(df.groupby(["split", "cls"]).size().unstack(), flush=True)


# ---------------------------------------------------------------- 2. background frames
TEST_CAMERAS = ("10.2.39.190_", "20250319_", "20250320_")     # the NESTLER cameras behind the live feed clips
VAL_CAMERAS = ("10.2.39.193_",)
HELD_OUT_PIO = ("0002.mp4",)                                   # the broiler house feed shown live, never trained on


def video_sources() -> dict[str, list[Path]]:
    """Split by camera, never by frame, so no camera view is in two splits.

    Five PIO videos (a white broiler house) and two NESTLER cameras train, one NESTLER camera validates.
    Every video shown in the live feed is held out: PIO 0002 and the NESTLER live feed cameras. NESTLER
    birds are dark and brown, the kind the close-up model mistakes for droppings, so some are negatives.
    """
    pio = sorted(p for p in (VIDEOS / "pio").rglob("*.mp4"))
    nestler = sorted(p for p in (VIDEOS / "nestler").rglob("*.mp4"))
    test = [p for p in nestler if p.name.startswith(TEST_CAMERAS)] + [p for p in pio if p.name in HELD_OUT_PIO]
    val = [p for p in nestler if p.name.startswith(VAL_CAMERAS)]
    train = [p for p in pio if p.name not in HELD_OUT_PIO] + [p for p in nestler if p not in test and p not in val]
    return {"train": train, "val": val, "test": test}


def decode_every(path: Path, every_s: float, limit: int) -> list[tuple[int, np.ndarray]]:
    """Decode straight through with ffmpeg and keep one frame every few seconds.
    Seeking in the PIO HEVC files returns grey half decoded frames, so nothing here seeks."""
    import subprocess
    import imageio_ffmpeg
    cap = cv2.VideoCapture(str(path))
    w, h = int(cap.get(3)), int(cap.get(4))
    cap.release()
    H = round(h * FRAME_W / w) // 2 * 2
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(path), "-an",
           "-vf", f"fps=1/{every_s},scale={FRAME_W}:{H}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    frames, size = [], FRAME_W * H * 3
    while len(frames) < limit:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        frames.append((round(len(frames) * every_s * 1000), np.frombuffer(buf, np.uint8).reshape(H, FRAME_W, 3).copy()))
    proc.kill()
    return frames


def sample_frames(job):
    """Save frames from one video at 1280 wide plus its median background (birds move, litter stays)."""
    path, split, every_s, limit = job
    frames = decode_every(path, every_s, limit)          # index is milliseconds into the video
    if len(frames) < 3:
        return path.name, 0
    tag = f"{split}_{path.parent.name}_{path.stem}".replace(" ", "_")[:90]
    out = WORK / "frames" / split
    bg = np.median(np.stack([f for _, f in frames[:: max(1, len(frames) // 25)]]), 0).astype(np.uint8)
    cv2.imwrite(str(out / f"{tag}__bg.png"), bg)
    for i, f in frames:
        cv2.imwrite(str(out / f"{tag}__{i:07d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return path.name, len(frames)


def cmd_frames(args):
    jobs = []
    for split, paths in video_sources().items():
        (WORK / "frames" / split).mkdir(parents=True, exist_ok=True)
        for p in paths:
            short = "nestler" in p.parts                                # NESTLER clips last under a minute
            jobs.append((p, split, 1.0 if short else args.every, 400 if short else 600))
    print({s: len(v) for s, v in video_sources().items()}, "videos", flush=True)
    with ProcessPoolExecutor(min(args.workers, 8)) as ex:
        for name, k in ex.map(sample_frames, jobs):
            print(f"frames: {name} {k}", flush=True)


# ---------------------------------------------------------------- 3. the dataset
def litter_colour(bg: np.ndarray) -> np.ndarray:
    """The most common colour in the lower part of the empty background, which is the floor in these cameras."""
    lab = cv2.cvtColor(cv2.GaussianBlur(bg, (0, 0), 3), cv2.COLOR_BGR2LAB)[bg.shape[0] // 3:].reshape(-1, 3)
    q = (lab // 12).astype(np.int32)
    keys, counts = np.unique(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2], return_counts=True)
    k = keys[np.argmax(counts)]
    return np.median(lab[(q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]) == k], 0)


def litter_mask(frame: np.ndarray, bg: np.ndarray, litter: np.ndarray) -> np.ndarray:
    """Floor pixels with no bird on them right now, where a dropping can sit visibly."""
    free = cv2.absdiff(frame, bg).max(2) < 25
    lab = cv2.cvtColor(cv2.GaussianBlur(bg, (0, 0), 3), cv2.COLOR_BGR2LAB).astype(np.float32)
    floor = np.abs(lab[..., 0] - litter[0]) < 40
    floor &= np.hypot(lab[..., 1] - litter[1], lab[..., 2] - litter[2]) < 12
    return cv2.erode((free & floor).astype(np.uint8), np.ones((9, 9), np.uint8))


def paste(tile: np.ndarray, free: np.ndarray, drop: np.ndarray, rng: random.Random):
    """Shrink one dropping to pen size, match it to the local light and blend it in. Returns its box or None."""
    L = rng.uniform(*SIZE_PX)
    h, w = drop.shape[:2]
    s = L / max(h, w)
    dw, dh = max(3, round(w * s)), max(3, round(h * s))
    d = cv2.resize(drop, (dw, dh), interpolation=cv2.INTER_AREA).astype(np.float32)
    ys, xs = np.nonzero(free[: TILE - dh, : TILE - dw])
    if len(xs) == 0:
        return None
    k = rng.randrange(len(xs))
    x, y = int(xs[k]), int(ys[k])
    region = tile[y:y + dh, x:x + dw].astype(np.float32)
    a = d[..., 3:] / 255.0
    if a.max() < 0.3:
        return None
    rgb = d[..., :3]
    # the close-ups were lit by a phone flash, the barn is not: scale to the litter's brightness
    gain = (region.mean() + 1) / (rgb[a[..., 0] > 0.5].mean() + 1) * rng.uniform(0.55, 0.95)
    rgb = np.clip(rgb * gain, 0, 255)
    if rng.random() < 0.5:
        rgb = cv2.GaussianBlur(rgb, (0, 0), rng.uniform(0.3, 0.9))
    tile[y:y + dh, x:x + dw] = (rgb * a + region * (1 - a)).astype(np.uint8)
    yy, xx = np.nonzero(a[..., 0] > 0.35)
    return x + xx.min(), y + yy.min(), x + xx.max() + 1, y + yy.max() + 1


def build_pen_tiles(split: str, count: int, out: Path, paste_on: bool, seed: int) -> list[str]:
    rng = random.Random(seed)
    frames = sorted(p for p in (WORK / "frames" / split).glob("*.jpg"))
    bank = [b for b in json.loads((WORK / "bank" / "index.json").read_text()) if b["split"] == split]
    by_cls = {c: [b for b in bank if b["cls"] == c] for c in CLASSES}
    img_dir, lbl_dir = out / "images", out / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    bgs: dict[str, np.ndarray] = {}
    litters: dict[str, np.ndarray] = {}
    paths, meta = [], []
    for i in range(count):
        fp = rng.choice(frames)
        tag = fp.name.split("__")[0]
        if tag not in bgs:
            bgs[tag] = cv2.imread(str(fp.parent / f"{tag}__bg.png"))
            litters[tag] = litter_colour(bgs[tag])
        frame = cv2.imread(str(fp))
        H, W = frame.shape[:2]
        x0, y0 = rng.randrange(0, max(1, W - TILE + 1)), rng.randrange(0, max(1, H - TILE + 1))
        tile = np.zeros((TILE, TILE, 3), np.uint8)
        part = frame[y0:y0 + TILE, x0:x0 + TILE]
        tile[: part.shape[0], : part.shape[1]] = part
        free = np.zeros((TILE, TILE), np.uint8)
        free[: part.shape[0], : part.shape[1]] = litter_mask(part, bgs[tag][y0:y0 + TILE, x0:x0 + TILE], litters[tag])
        lines = []
        n = 0 if (not paste_on or rng.random() < 0.2) else rng.randint(1, 6)   # one tile in five stays empty
        for _ in range(n):
            cls = rng.choice(CLASSES) if rng.random() < 0.5 else rng.choice(["cocci", "healthy", "salmo"])
            if not by_cls[cls]:
                continue
            b = rng.choice(by_cls[cls])
            drop = cv2.imread(str(WORK / "bank" / split / b["file"]), cv2.IMREAD_UNCHANGED)
            box = paste(tile, free, drop, rng)
            if box is None:
                continue
            x1, y1, x2, y2 = box
            free[max(0, y1 - 6):y2 + 6, max(0, x1 - 6):x2 + 6] = 0
            lines.append(f"{CLASSES.index(cls)} {(x1 + x2) / 2 / TILE:.6f} {(y1 + y2) / 2 / TILE:.6f} {(x2 - x1) / TILE:.6f} {(y2 - y1) / TILE:.6f}")
        ok, buf = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(60, 92)])
        name = f"pen_{split}_{i:05d}"
        (img_dir / f"{name}.jpg").write_bytes(buf.tobytes())
        (lbl_dir / f"{name}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        paths.append(str(img_dir / f"{name}.jpg"))
        meta.append({"tile": name, "frame": fp.name, "bg": f"{tag}__bg.png", "x0": x0, "y0": y0})
    (out / "tiles.json").write_text(json.dumps(meta))             # where each tile came from, for background checks
    return paths


def closeup_job(job):
    cls, stem, split, lines = job
    img_dir = WORK / "yolo" / "closeup" / split / "images"
    dst = img_dir / f"{stem}.jpg"
    if not dst.exists():
        with zipfile.ZipFile(RAW / f"{cls}.zip") as z:
            names = [n for n in z.namelist() if n.endswith(f"/{stem}.jpg")]
            if not names:
                return None
            from PIL import Image
            with Image.open(io.BytesIO(z.read(names[0]))) as im:   # same handling as prepare_data.py: no EXIF rotation
                im.draft("RGB", (1280, 1280))
                im = im.convert("RGB")
                s = 1280 / max(im.size)
                if s < 1:
                    im = im.resize((round(im.width * s), round(im.height * s)), Image.BILINEAR)
                im.save(dst, quality=90)
    (WORK / "yolo" / "closeup" / split / "labels" / f"{stem}.txt").write_text(
        "\n".join(f"{CLASSES.index(cls)} {cx} {cy} {bw} {bh}" for cx, cy, bw, bh in lines) + "\n")
    return str(dst)


def cmd_build(args):
    split_of = pd.read_csv(SPLIT_CSV).set_index(["cls", "stem"]).split.to_dict()
    labels = zipfile.ZipFile(RAW / "imgObjDet_Yolo.zip")
    jobs = []
    for name in labels.namelist():
        p = name.split("/")
        if len(p) != 3 or not p[2].endswith(".txt") or p[2] == "classes.txt":
            continue
        cls, stem = p[1], p[2][:-4]
        lines = [l.split()[1:] for l in labels.read(name).decode(errors="ignore").splitlines() if len(l.split()) == 5]
        split = split_of.get((cls, stem))
        if lines and split in ("train", "val", "test") and (split == "test" or not args.test_only):
            jobs.append((cls, stem, split, lines))
    for split in ("train", "val", "test"):
        for sub in ("images", "labels"):
            (WORK / "yolo" / "closeup" / split / sub).mkdir(parents=True, exist_ok=True)
    lists = {"train": [], "val": [], "test": []}
    with ProcessPoolExecutor(args.workers) as ex:
        for job, path in zip(jobs, ex.map(closeup_job, jobs, chunksize=8)):
            if path:
                reps = 3 if (job[2] == "train" and job[0] == "ncd") else 1   # same NCD oversampling as before
                lists[job[2]] += [path] * reps
    print({k: len(v) for k, v in lists.items()}, "close-up entries", flush=True)

    pen = WORK / "yolo" / "pen"
    if not args.test_only:                                          # the tests need no training frames
        lists["train"] += build_pen_tiles("train", args.pen_train, pen / "train", True, SEED)
        lists["val"] += build_pen_tiles("val", args.pen_val, pen / "val", True, SEED + 1)
    pen_test = build_pen_tiles("test", args.pen_test, pen / "test", True, SEED + 2)        # synthetic, other farm
    real_test = build_pen_tiles("test", args.pen_test, pen / "test_real", False, SEED + 3)  # nothing pasted

    y = WORK / "yolo"
    for k, v in lists.items():
        (y / f"{k}.txt").write_text("\n".join(v) + "\n")
    (y / "pen_test.txt").write_text("\n".join(pen_test) + "\n")
    (y / "pen_test_real.txt").write_text("\n".join(real_test) + "\n")
    names = f"names: {dict(enumerate(CLASSES))}\n"
    for tag, val in (("data", "val.txt"), ("closeup_test", "test.txt"), ("pen_test", "pen_test.txt"), ("pen_test_real", "pen_test_real.txt")):
        (y / f"{tag}.yaml").write_text(f"path: {y.as_posix()}\ntrain: {(y / 'train.txt').as_posix()}\nval: {(y / val).as_posix()}\n{names}")
    print({k: len(v) for k, v in lists.items()}, "entries with pen tiles", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["bank", "frames", "build", "all"])
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--every", type=float, default=6.0, help="seconds between sampled PIO frames")
    ap.add_argument("--pen-train", type=int, default=6000)
    ap.add_argument("--pen-val", type=int, default=600)
    ap.add_argument("--pen-test", type=int, default=600)
    ap.add_argument("--test-only", action="store_true", help="build only the test sets")
    args = ap.parse_args()
    for step in (["bank", "frames", "build"] if args.cmd == "all" else [args.cmd]):
        globals()[f"cmd_{step}"](args)


if __name__ == "__main__":
    sys.exit(main())
