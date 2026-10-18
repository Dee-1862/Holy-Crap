"""Build two datasets from the Big Broiler release (AGPL-3.0, Cardoen et al. 2025):

1. behaviour/  - Ultralytics classification folders of single-bird crops, 7 classes:
                 inactive, eating, drinking, moving, preening, panting, other
2. chickens/   - YOLO detection dataset (1 class "chicken") from setups 2 and 3, where
                 nearly every bird in a frame is labelled (setup 1 labels ~10 of ~140 birds).

Videos are fetched one by one straight out of the remote zip (HTTP range requests),
decoded, sampled and deleted, so peak disk stays small. Split is by video: the 10-clip
multi-annotator holdout (092-101) is test, ~10% of the rest is val.

  python prepare_behavior.py --out work_bb --smoke 3   # 3 short clips, local test
  python prepare_behavior.py --out work_bb             # all 102 clips
"""
import argparse
import csv
import io
import json
import os
import random
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from prepare_data import HttpFile, fetch_member

URL = "https://datasets.ilabt.imec.be/broilertracking/big-broiler_v1.zip"
CLASSES = ["inactive", "eating", "drinking", "moving", "preening", "panting", "other"]
ACTION_TO_CLASS = {
    "Inactive": "inactive", "Resting": "inactive", "Sleeping": "inactive",
    "Eat": "eating", "Drink": "drinking",
    "Locomotion": "moving", "Explor_Forag": "moving", "Running": "moving",
    "Scratching": "moving", "Short_Leg_Move": "moving",
    "Preening": "preening", "Panting": "panting",
}
SKIP_ACTIONS = {"Out_Of_Sight", "Video_Problem"}
PRIORITY = ["panting", "drinking", "eating", "moving", "preening", "inactive", "other"]
TEST_IDS = set(range(92, 102))
CROP_STEP = {"panting": 5, "drinking": 10, "eating": 15}  # denser sampling for rarer classes
DEFAULT_CROP_STEP = 25  # 1 fps at 25 fps
DET_STEP = 25
CROP_SIZE = 224
DET_MAX_SIDE = 1280


def label_of(row):
    acts = (row.get("actions_ground") or row.get("actions_annotator_1") or "").replace(";", ",")
    acts = [a.strip() for a in acts.split(",") if a.strip()]
    if not acts or any(a in SKIP_ACTIONS for a in acts):
        return None
    classes = {ACTION_TO_CLASS.get(a, "other") for a in acts}
    return next(c for c in PRIORITY if c in classes)


def process_video(args):
    """Download one clip, sample crops (all setups) and detector frames (setups 2/3), delete it."""
    import cv2

    url, info, rows, stem, split, out = args
    out = Path(out)
    setup = stem.split("_")[1]
    tmp = out / "tmp" / f"{stem}.mp4"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(fetch_member(url, info))

    by_frame = defaultdict(list)
    for r in rows:
        by_frame[int(r["frame"])].append(r)
    want_det = setup in ("2", "3")
    stats = Counter()
    cap = cv2.VideoCapture(str(tmp))
    frame_idx = -1
    last = max(by_frame) if by_frame else -1
    while frame_idx < last:
        if not cap.grab():
            break
        frame_idx += 1
        rs = by_frame.get(frame_idx)
        if not rs:
            continue
        crops = []
        for r in rs:
            c = label_of(r)
            if c and frame_idx % CROP_STEP.get(c, DEFAULT_CROP_STEP) == 0:
                crops.append((r, c))
        det = want_det and frame_idx % DET_STEP == 0
        if not crops and not det:
            continue
        ok, img = cap.retrieve()
        if not ok:
            continue
        h, w = img.shape[:2]
        for r, c in crops:
            x1, y1, x2, y2 = (float(r[k]) for k in ("x1", "y1", "x2", "y2"))
            cx, cy = (x1 + x2) / 2 * w, (y1 + y2) / 2 * h
            side = max((x2 - x1) * w, (y2 - y1) * h) * 1.15
            if side < 12:
                continue
            a, b = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
            crop = img[b:int(min(h, cy + side / 2)), a:int(min(w, cx + side / 2))]
            if crop.size == 0:
                continue
            crop = cv2.resize(crop, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_AREA)
            p = out / "behaviour" / split / c / f"{stem}_{frame_idx}_{r['track']}.jpg"
            p.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(p), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            stats[f"crop_{split}_{c}"] += 1
        if det:
            s = DET_MAX_SIDE / max(h, w)
            small = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA) if s < 1 else img
            name = f"{stem}_{frame_idx}"
            ip = out / "chickens" / "images" / split / f"{name}.jpg"
            lp = out / "chickens" / "labels" / split / f"{name}.txt"
            ip.parent.mkdir(parents=True, exist_ok=True)
            lp.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(ip), small, [cv2.IMWRITE_JPEG_QUALITY, 90])
            lines = []
            for r in rs:
                x1, y1, x2, y2 = (min(1.0, max(0.0, float(r[k]))) for k in ("x1", "y1", "x2", "y2"))
                if x2 > x1 and y2 > y1:
                    lines.append(f"0 {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
            lp.write_text("\n".join(lines) + "\n")
            stats[f"det_{split}_frames"] += 1
            stats[f"det_{split}_boxes"] += len(lines)
    cap.release()
    tmp.unlink()
    return stem, dict(stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("work_bb"))
    ap.add_argument("--smoke", type=int, default=0, help="only N shortest clips")
    ap.add_argument("--workers", type=int, default=min(24, os.cpu_count() or 4))
    ap.add_argument("--cap", type=int, default=25000, help="max train crops per behaviour class")
    args = ap.parse_args()
    out = args.out.resolve()

    f = HttpFile(URL)
    z = zipfile.ZipFile(io.BufferedReader(f, buffer_size=1 << 20))
    infos = {i.filename: i for i in z.infolist()}
    videos = sorted(n for n in infos if n.endswith(".mp4"))
    if args.smoke:
        videos = sorted(videos, key=lambda n: infos[n].compress_size)[: args.smoke]
    stems = [Path(v).stem for v in videos]
    rng = random.Random(0)
    non_test = [s for s in stems if int(s[:3]) not in TEST_IDS]
    val = set(rng.sample(non_test, max(1, len(non_test) // 10))) if len(non_test) > 1 else set()

    def split_of(s):
        return "test" if int(s[:3]) in TEST_IDS else "val" if s in val else "train"

    if args.smoke:  # make sure every split exists in a tiny run
        order = ["train", "val", "test"]
        split_of = lambda s, _m={s: order[i % 3] for i, s in enumerate(stems)}: _m[s]  # noqa: E731

    jobs = []
    for v, s in zip(videos, stems):
        ann = f"big-broiler/annotations/{s}.csv"
        rows = list(csv.DictReader(io.StringIO(fetch_member(f.url, infos[ann]).decode())))
        jobs.append((f.url, infos[v], rows, s, split_of(s), str(out)))
    print(f"{len(jobs)} clips; splits {Counter(j[4] for j in jobs)}", flush=True)

    total = Counter()
    with ProcessPoolExecutor(args.workers) as ex:
        for stem, st in ex.map(process_video, jobs):
            total.update(st)
            print(f"done {stem}: {sum(v for k, v in st.items() if k.startswith('crop'))} crops, "
                  f"{sum(v for k, v in st.items() if k.startswith('det') and k.endswith('frames'))} det frames", flush=True)

    # Cap the biggest classes in train so "inactive" (~half of all labels) doesn't swamp the rest.
    rng = random.Random(0)
    for cdir in (out / "behaviour" / "train").glob("*"):
        files = sorted(cdir.glob("*.jpg"))
        if len(files) > args.cap:
            for p in rng.sample(files, len(files) - args.cap):
                p.unlink()
            total[f"crop_train_{cdir.name}_capped_to"] = args.cap

    det = out / "chickens"
    (det / "data.yaml").write_text(
        f"path: {det.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames: {{0: chicken}}\n")
    (out / "stats_behaviour.json").write_text(json.dumps(dict(sorted(total.items())), indent=2))
    print(json.dumps(dict(sorted(total.items())), indent=2))


if __name__ == "__main__":
    main()
