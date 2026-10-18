"""Blind the PCR annotated Machuve photos for grading.

    python dataset/grading/prepare.py --key KEY_DIR

Reads the four PCR zips (Zenodo 5801834, CC BY 4.0) from data-visualization/data/raw and writes
    dataset/grading/work/images/HC-xxxx.jpg   longest side 768, re-encoded, no metadata, git ignored
    dataset/grading/work/queues/<rater>.txt   every ID once in that rater's own random order
    KEY_DIR/key.csv                           ID -> source zip, member, PCR class, original md5, repeat_of

Raters never see file names, classes or the key. The key stays outside the repository until all grading is
done, then score.py reads it. About 10 percent of photos appear a second time under a new ID (repeat_of), so
each rater's agreement with itself can be measured. Seeds are fixed, so the run can be reproduced.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import random
import zipfile
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data-visualization" / "data" / "raw"
WORK = Path(__file__).resolve().parent / "work"
ZIPS = {"pcrcocci": "coccidiosis", "pcrhealthy": "healthy", "pcrncd": "ncd", "pcrsalmo": "salmonella"}
RATERS = ["rater-a", "rater-b", "rater-c"]
SEED, REPEAT_SHARE, SIDE = 20261018, 0.10, 768


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="folder for key.csv, outside the repository")
    args = ap.parse_args()
    key_dir = Path(args.key)
    key_dir.mkdir(parents=True, exist_ok=True)
    (WORK / "images").mkdir(parents=True, exist_ok=True)
    (WORK / "queues").mkdir(parents=True, exist_ok=True)

    photos = []                                            # (zip, member, class)
    for z, cls in ZIPS.items():
        with zipfile.ZipFile(RAW / f"{z}.zip") as zf:
            photos += [(z, i.filename, cls) for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith(".jpg")]
    photos.sort()
    rng = random.Random(SEED)
    repeats = rng.sample(range(len(photos)), round(len(photos) * REPEAT_SHARE))
    items = [(p, None) for p in photos] + [(photos[i], i) for i in repeats]
    ids = [f"HC-{n:04d}" for n in rng.sample(range(1, 10000), len(items))]   # random, says nothing about order

    rows, first_id = [], {}
    open_zips = {z: zipfile.ZipFile(RAW / f"{z}.zip") for z in ZIPS}
    for idx, ((z, member, cls), rep) in enumerate(items):
        raw = open_zips[z].read(member)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((SIDE, SIDE), Image.LANCZOS)
        im.save(WORK / "images" / f"{ids[idx]}.jpg", quality=85)          # a fresh file carries no EXIF
        if rep is None:
            first_id[idx] = ids[idx]
        rows.append({"id": ids[idx], "zip": z, "member": member, "pcr_class": cls,
                     "md5": hashlib.md5(raw).hexdigest(), "repeat_of": "" if rep is None else rep})
    for r in rows:                                         # point repeats at the first ID of the same photo
        if r["repeat_of"] != "":
            r["repeat_of"] = first_id[int(r["repeat_of"])]
    with open(key_dir / "key.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for n, rater in enumerate(RATERS):                     # each rater gets its own order
        order = ids[:]
        random.Random(SEED + n + 1).shuffle(order)
        (WORK / "queues" / f"{rater}.txt").write_text("\n".join(order) + "\n")
    print(f"{len(photos)} photos, {len(repeats)} hidden repeats, {len(items)} images per rater")


if __name__ == "__main__":
    main()
