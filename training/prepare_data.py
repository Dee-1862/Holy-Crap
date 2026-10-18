"""Build a YOLO dataset from the Machuve poultry fecal images on Zenodo (CC BY 4.0).

Farm images (record 4628934) have official YOLO boxes (imgObjDet_Yolo.zip) and are
split 80/10/10 into train/val/test. PCR lab-confirmed images (record 5801834) have
no boxes; they are kept as an image-level test set for disease labels.

Class ids come from the folder name; the class id inside each label file is ignored.

  python prepare_data.py --out ./work --mode smoke   # ~40 images/class via HTTP range reads
  python prepare_data.py --out ./work --mode full    # all images (~8.4 GB farm + ~4.4 GB PCR)
"""
import argparse
import io
import json
import os
import random
import shutil
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

CLASSES = ["cocci", "healthy", "ncd", "salmo"]
FARM_REC, PCR_REC = "4628934", "5801834"
SEED = 0


def zenodo_url(rec, name):
    return f"https://zenodo.org/records/{rec}/files/{name}?download=1"


class HttpFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests (for reading a few zip members)."""

    def __init__(self, url):
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req) as r:
            self.url, self.size = r.geturl(), int(r.headers["Content-Length"])
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(req) as r:
            data = r.read()
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def remote_zip(rec, name):
    return zipfile.ZipFile(io.BufferedReader(HttpFile(zenodo_url(rec, name)), buffer_size=1 << 20))


def download(rec, name, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    print(f"downloading {name} ...", flush=True)
    tmp = dest.with_suffix(".part")
    with urllib.request.urlopen(zenodo_url(rec, name)) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, length=1 << 22)
    tmp.rename(dest)
    return dest


def resize_job(args):
    """Downscale one image so its longest side is <= max_side.

    EXIF orientation is deliberately NOT applied and EXIF is dropped on save: the boxes
    were drawn on the raw pixel grid, and keeping EXIF would let OpenCV rotate the image
    away from its labels.
    """
    src, dst, max_side = args
    with Image.open(src) as im:
        orient = im.getexif().get(0x0112, 1)
        im.draft("RGB", (max_side, max_side))
        im = im.convert("RGB")
        scale = max_side / max(im.size)
        if scale < 1:
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.BILINEAR)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, quality=90)
    return orient


def read_labels(out):
    """Return {(cls, stem): [box lines with class id remapped]} from imgObjDet_Yolo.zip."""
    z = zipfile.ZipFile(download(FARM_REC, "imgObjDet_Yolo.zip", out / "raw" / "imgObjDet_Yolo.zip"))
    labels = {}
    for name in z.namelist():
        parts = name.split("/")
        if len(parts) != 3 or not parts[2].endswith(".txt") or parts[2] == "classes.txt":
            continue
        cls, stem = parts[1], parts[2][:-4]
        boxes = []
        for line in z.read(name).decode(errors="ignore").splitlines():
            p = line.split()
            if len(p) == 5:
                boxes.append(" ".join([str(CLASSES.index(cls))] + p[1:]))
        if boxes:
            labels[(cls, stem)] = boxes
    return labels


def collect(rec, zip_name, prefix, out, mode, per_class, staging):
    """Fetch images of one class zip into staging/, return {stem: path}."""
    dest = staging / zip_name[:-4]
    if mode == "smoke":
        z = remote_zip(rec, zip_name)
        members = sorted(n for n in z.namelist() if n.lower().endswith(".jpg"))
        random.Random(SEED).shuffle(members)
        for n in members[:per_class]:
            (dest / Path(n).name).parent.mkdir(parents=True, exist_ok=True)
            (dest / Path(n).name).write_bytes(z.read(n))
    else:
        zpath = download(rec, zip_name, out / "raw" / zip_name)
        with zipfile.ZipFile(zpath) as z:
            for n in z.namelist():
                if n.lower().endswith(".jpg"):
                    (dest / Path(n).name).parent.mkdir(parents=True, exist_ok=True)
                    with z.open(n) as s, open(dest / Path(n).name, "wb") as d:
                        shutil.copyfileobj(s, d)
        zpath.unlink()  # keep peak disk use low
    return {p.stem: p for p in dest.glob("*.jpg")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("work"))
    ap.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    ap.add_argument("--per-class", type=int, default=40, help="smoke mode only")
    ap.add_argument("--max-side", type=int, default=1280)
    ap.add_argument("--ncd-oversample", type=int, default=3, help="repeat NCD train images N times")
    ap.add_argument("--no-pcr", action="store_true")
    args = ap.parse_args()

    out = args.out.resolve()
    staging, yolo, pcr_dir = out / "staging", out / "yolo", out / "pcr"
    labels = read_labels(out)
    print("label files with boxes:", Counter(c for c, _ in labels), flush=True)

    jobs, splits, stats = [], {"train": [], "val": [], "test": []}, Counter()
    workers = os.cpu_count() or 4
    for cls in CLASSES:
        imgs = collect(FARM_REC, f"{cls}.zip", cls, out, args.mode, args.per_class, staging)
        stems = sorted(s for s in imgs if (cls, s) in labels)
        stats[f"farm_{cls}_images"] = len(imgs)
        stats[f"farm_{cls}_labelled"] = len(stems)
        random.Random(SEED).shuffle(stems)
        n_val = n_test = max(1, len(stems) // 10)
        groups = {"test": stems[:n_test], "val": stems[n_test:n_test + n_val], "train": stems[n_test + n_val:]}
        for split, ss in groups.items():
            for s in ss:
                img = yolo / "images" / split / f"{s}.jpg"
                lbl = yolo / "labels" / split / f"{s}.txt"
                lbl.parent.mkdir(parents=True, exist_ok=True)
                lbl.write_text("\n".join(labels[(cls, s)]) + "\n")
                jobs.append((imgs[s], img, args.max_side))
                reps = args.ncd_oversample if (split == "train" and cls == "ncd") else 1
                splits[split] += [str(img)] * reps

        if not args.no_pcr:
            pimgs = collect(PCR_REC, f"pcr{cls}.zip", cls, out, args.mode, max(1, args.per_class // 4), staging)
            stats[f"pcr_{cls}_images"] = len(pimgs)
            jobs += [(p, pcr_dir / cls / f"{s}.jpg", args.max_side) for s, p in pimgs.items()]

        with ProcessPoolExecutor(workers) as ex:
            orients = list(ex.map(resize_job, jobs, chunksize=8))
        stats.update(f"exif_orientation_{o}" for o in orients)
        jobs = []
        shutil.rmtree(staging, ignore_errors=True)
        print(f"{cls}: done", flush=True)

    for split, paths in splits.items():
        (yolo / f"{split}.txt").write_text("\n".join(paths) + "\n")
        stats[f"{split}_entries"] = len(paths)
    (yolo / "data.yaml").write_text(
        f"path: {yolo.as_posix()}\ntrain: {(yolo / 'train.txt').as_posix()}\n"
        f"val: {(yolo / 'val.txt').as_posix()}\ntest: {(yolo / 'test.txt').as_posix()}\n"
        f"names: {dict(enumerate(CLASSES))}\n"
    )
    (out / "stats.json").write_text(json.dumps(stats, indent=2, sort_keys=True))
    print(json.dumps(stats, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
