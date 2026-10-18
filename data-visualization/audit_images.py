"""Image level audits for the Holy-Crap detector, run on the public Zenodo photos (CC BY 4.0).

  python audit_images.py all     run everything below in order, resumable
  python audit_images.py farm    hash every farm photo, to look for near duplicates across train, val and test
  python audit_images.py pcr     run the detector on the lab confirmed (PCR) photos and keep the scores
  python audit_images.py farmtest  re-score the held out farm test photos with the detector
  python audit_images.py pairs   save thumbnails of closest cross split pairs, for checking by eye
  python audit_images.py clean   delete the downloaded zips (data/raw), keeping results/

Each class zip is downloaded in large parallel chunks, which is gentle on Zenodo (it rate limits many small
requests), then checked against the md5 Zenodo lists, then read photo by photo. Results go to results/*.csv
(small, committed). The zips go to data/raw (ignored by git, about 13 GB) and can be removed with `clean`.

The split is rebuilt exactly as training/prepare_data.py builds it: class by class, 80/10/10 by photo,
random.Random(0) on the sorted stems, from the official label file.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import shutil
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DATA, RAW, RESULTS = HERE / "data", HERE / "data" / "raw", HERE / "results"
FARM_REC, PCR_REC = "4628934", "5801834"
CLASSES = ["cocci", "healthy", "ncd", "salmo"]          # model output order, same as training/prepare_data.py
SEED = 0
MODEL = REPO / "models" / "dropping4-laptop" / "dropping4_yolo11n_640.onnx"      # the default final model


# ---------------------------------------------------------------- downloading, politely and verified
def zenodo_files(rec: str) -> dict[str, dict]:
    cache = DATA / f"zenodo_{rec}.json"
    DATA.mkdir(exist_ok=True)
    try:
        with urllib.request.urlopen(f"https://zenodo.org/api/records/{rec}", timeout=30) as r:
            data = json.load(r)
        cache.write_text(json.dumps(data))
    except OSError:
        data = json.loads(cache.read_text())
    return {f["key"]: {"size": f["size"], "md5": f["checksum"].split(":")[1]} for f in data["files"]}


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download_chunked(url: str, dest: Path, size: int, workers: int = 12, chunk: int = 16 << 20) -> None:
    """Parallel range downloads into one file. Resumable: finished chunks are remembered in a .state file."""
    RAW.mkdir(parents=True, exist_ok=True)
    part, state = dest.with_name(dest.name + ".part"), dest.with_name(dest.name + ".state")
    done = set(json.loads(state.read_text())) if state.exists() and part.exists() else set()
    if not part.exists() or part.stat().st_size != size:
        with open(part, "wb") as f:
            f.truncate(size)
        done = set()
    chunks = [(i, i * chunk, min(size, (i + 1) * chunk) - 1) for i in range((size + chunk - 1) // chunk)]
    todo = [c for c in chunks if c[0] not in done]
    lock, t0 = threading.Lock(), time.time()

    def fetch(c):
        i, a, b = c
        for attempt in range(10):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Range": f"bytes={a}-{b}"}), timeout=120) as r:
                    body = r.read()
                if len(body) != b - a + 1:
                    raise IOError("short read")
                with open(part, "r+b") as f:
                    f.seek(a); f.write(body)
                with lock:
                    done.add(i); state.write_text(json.dumps(sorted(done)))
                return len(body)
            except HTTPError as e:
                time.sleep(int(e.headers.get("Retry-After", 20 * (attempt + 1))) if e.code == 429 else 5 * (attempt + 1))
            except Exception:
                time.sleep(5 * (attempt + 1))
        raise RuntimeError(f"chunk {i} of {dest.name} kept failing")

    got = 0
    with ThreadPoolExecutor(workers) as ex:
        for n, fut in enumerate(as_completed([ex.submit(fetch, c) for c in todo]), 1):
            got += fut.result()
            if n % 20 == 0 or n == len(todo):
                print(f"  {dest.name}: {n}/{len(todo)} chunks, {got / 1e6 / max(1e-9, time.time() - t0):.1f} MB/s", flush=True)
    part.replace(dest)
    state.unlink(missing_ok=True)


def ensure_zip(rec: str, name: str) -> Path:
    info, dest = zenodo_files(rec)[name], RAW / name
    if dest.exists() and md5_of(dest) == info["md5"]:
        return dest
    print(f"downloading {name} ({info['size'] / 1e6:.0f} MB)", flush=True)
    dest.unlink(missing_ok=True)
    download_chunked(f"https://zenodo.org/records/{rec}/files/{name}?download=1", dest, info["size"])
    got = md5_of(dest)
    if got != info["md5"]:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"md5 mismatch for {name}: got {got}, Zenodo lists {info['md5']}")
    print(f"  {name}: md5 matches the value Zenodo lists", flush=True)
    return dest


_tls = threading.local()
def local_zip(path: Path) -> zipfile.ZipFile:
    """One ZipFile per thread, so threads never share a file position."""
    cache = _tls.__dict__.setdefault("zips", {})
    if path not in cache:
        cache[path] = zipfile.ZipFile(path)
    return cache[path]


# ---------------------------------------------------------------- hashing and the split
def dhash256(im: Image.Image) -> str:
    """256 bit difference hash. Near duplicates differ in a few bits, unrelated photos in about 128."""
    a = np.asarray(im.convert("L").resize((17, 16), Image.LANCZOS), dtype=np.int16)
    return np.packbits((a[:, 1:] > a[:, :-1]).ravel()).tobytes().hex()


def load_small(data: bytes, side: int):
    im = Image.open(io.BytesIO(data))
    size = im.size
    im.draft("RGB", (side, side))
    return im.convert("RGB"), size


def rebuild_split() -> dict[tuple[str, str], str]:
    """(class, stem) -> train, val or test, exactly as training/prepare_data.py does it."""
    label_zip = ensure_zip(FARM_REC, "imgObjDet_Yolo.zip")
    labelled: dict[str, set[str]] = {c: set() for c in CLASSES}
    with zipfile.ZipFile(label_zip) as z:
        for name in z.namelist():
            p = name.split("/")
            if len(p) != 3 or not p[2].endswith(".txt") or p[2] == "classes.txt":
                continue
            if any(len(line.split()) == 5 for line in z.read(name).decode(errors="ignore").splitlines()):
                labelled[p[1]].add(p[2][:-4])
    split_of = {}
    for cls in CLASSES:
        stems = sorted(labelled[cls])
        random.Random(SEED).shuffle(stems)
        n = max(1, len(stems) // 10)
        for name, part in (("test", stems[:n]), ("val", stems[n:2 * n]), ("train", stems[2 * n:])):
            for s in part:
                split_of[(cls, s)] = name
    return split_of


def done_keys(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    with open(path, newline="") as f:
        return {row[key] for row in csv.DictReader(f)}


def run_pool(jobs, work, out_path: Path, fields: list[str], workers: int, label: str):
    """Run work(job) on a thread pool and append each result row to out_path as it finishes."""
    RESULTS.mkdir(exist_ok=True)
    new = not out_path.exists()
    t0, n, failed = time.time(), 0, 0
    with open(out_path, "a", newline="") as f, ThreadPoolExecutor(workers) as ex:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        futs = {ex.submit(work, j): j for j in jobs}
        for fut in as_completed(futs):
            try:
                w.writerow(fut.result()); n += 1
            except Exception as e:
                failed += 1; print(f"  failed {futs[fut]}: {e}", flush=True)
            if (n + failed) % 200 == 0:
                f.flush()
                print(f"{label}: {n} done, {failed} failed, {n / max(1e-9, time.time() - t0):.1f} photos/s, {len(jobs) - n - failed} to go", flush=True)
    print(f"{label}: finished, {n} done, {failed} failed in {time.time() - t0:.0f}s", flush=True)


# ---------------------------------------------------------------- farm photos: hashes
def cmd_farm(args):
    split_of = rebuild_split()
    out = RESULTS / "farm_hashes.csv"
    have = done_keys(out, "member")
    for cls in CLASSES:
        path = ensure_zip(FARM_REC, f"{cls}.zip")
        members = sorted(i.filename for i in local_zip(path).infolist() if i.filename.lower().endswith(".jpg"))
        members = [m for m in members if f"{cls}/{m}" not in have][: args.limit or None]
        print(f"{cls}: {len(members)} photos to hash", flush=True)

        def work(member, cls=cls, path=path):
            im, (w, h) = load_small(local_zip(path).read(member), 256)
            stem = Path(member).stem
            return {"member": f"{cls}/{member}", "cls": cls, "stem": stem, "split": split_of.get((cls, stem), "unlabelled"),
                    "width": w, "height": h, "dhash": dhash256(im)}

        run_pool(members, work, out, ["member", "cls", "stem", "split", "width", "height", "dhash"], args.workers, f"farm {cls}")


# ---------------------------------------------------------------- PCR photos: detector scores and hashes
def letterbox(im: Image.Image, side: int = 640) -> np.ndarray:
    s = min(side / im.width, side / im.height)
    nw, nh = round(im.width * s), round(im.height * s)
    canvas = Image.new("RGB", (side, side), (114, 114, 114))
    canvas.paste(im.resize((nw, nh), Image.BILINEAR), ((side - nw) // 2, (side - nh) // 2))
    return np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0


def cmd_pcr(args):
    import onnxruntime as ort
    opts = ort.SessionOptions(); opts.intra_op_num_threads = 1
    sess = ort.InferenceSession(str(MODEL), sess_options=opts, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0].name
    out = RESULTS / "pcr_predictions.csv"
    have = done_keys(out, "member")
    for cls in CLASSES:
        path = ensure_zip(PCR_REC, f"pcr{cls}.zip")
        members = sorted(i.filename for i in local_zip(path).infolist() if i.filename.lower().endswith(".jpg"))
        members = [m for m in members if f"{cls}/{m}" not in have][: args.limit or None]
        print(f"pcr{cls}: {len(members)} photos to score", flush=True)

        def work(member, cls=cls, path=path):
            im, (w, h) = load_small(local_zip(path).read(member), 640)
            scores = sess.run(None, {inp: letterbox(im)})[0][0][4:8].max(axis=1)     # best score per class over all candidates
            row = {"member": f"{cls}/{member}", "true": cls, "width": w, "height": h, "dhash": dhash256(im)}
            row.update({f"max_{c}": round(float(s), 4) for c, s in zip(CLASSES, scores)})
            return row

        run_pool(members, work, out, ["member", "true", "width", "height", "dhash"] + [f"max_{c}" for c in CLASSES], args.workers, f"pcr {cls}")


# ---------------------------------------------------------------- farm test photos: re-score the held out split
def cmd_farmtest(args):
    """Score the held out farm test photos with the same detector, so test accuracy is recomputed here."""
    import onnxruntime as ort
    split_of = rebuild_split()
    opts = ort.SessionOptions(); opts.intra_op_num_threads = 1
    sess = ort.InferenceSession(str(MODEL), sess_options=opts, providers=["CPUExecutionProvider"])
    inp = sess.get_inputs()[0].name
    out = RESULTS / "farm_test_predictions.csv"
    have = done_keys(out, "member")
    for cls in CLASSES:
        path = ensure_zip(FARM_REC, f"{cls}.zip")
        members = sorted(i.filename for i in local_zip(path).infolist()
                         if i.filename.lower().endswith(".jpg") and split_of.get((cls, Path(i.filename).stem)) == "test")
        members = [m for m in members if f"{cls}/{m}" not in have][: args.limit or None]
        print(f"{cls}: {len(members)} test photos to score", flush=True)

        def work(member, cls=cls, path=path):
            im, (w, h) = load_small(local_zip(path).read(member), 640)
            scores = sess.run(None, {inp: letterbox(im)})[0][0][4:8].max(axis=1)
            row = {"member": f"{cls}/{member}", "true": cls, "width": w, "height": h}
            row.update({f"max_{c}": round(float(s), 4) for c, s in zip(CLASSES, scores)})
            return row

        run_pool(members, work, out, ["member", "true", "width", "height"] + [f"max_{c}" for c in CLASSES], args.workers, f"farmtest {cls}")


# ---------------------------------------------------------------- thumbnails of cross split pairs
def hash_matrix(hexes) -> np.ndarray:
    return np.frombuffer(b"".join(bytes.fromhex(h) for h in hexes), dtype=np.uint64).reshape(len(hexes), 4)


def nearest(a: np.ndarray, b: np.ndarray):
    """For each row of a, the smallest Hamming distance to any row of b and which row."""
    dist, idx = np.empty(len(a), dtype=np.int32), np.empty(len(a), dtype=np.int32)
    for i in range(len(a)):
        d = np.bitwise_count(a[i] ^ b).sum(axis=1)
        idx[i] = int(d.argmin()); dist[i] = int(d[idx[i]])
    return dist, idx


def cmd_pairs(args):
    import pandas as pd
    df = pd.read_csv(RESULTS / "farm_hashes.csv")
    df = df[df.split.isin(["train", "val", "test"])].reset_index(drop=True)
    tr, te = df[df.split == "train"].reset_index(drop=True), df[df.split == "test"].reset_index(drop=True)
    dist, idx = nearest(hash_matrix(te.dhash), hash_matrix(tr.dhash))
    order = np.argsort(dist)
    picks, seen = [], set()
    for target in (0, 6, 12, 20, 30, 45):                       # a spread of distances so the threshold can be judged by eye
        k = int(order[int(np.argmin(np.abs(dist[order] - target)))])
        if k not in seen:
            seen.add(k); picks.append(k)
    out = HERE / "figures" / "pairs"; out.mkdir(parents=True, exist_ok=True)
    meta = []
    for n, k in enumerate(picks):
        a, b = te.iloc[k], tr.iloc[int(idx[k])]
        for tag, row in (("test", a), ("train", b)):
            path = ensure_zip(FARM_REC, f"{row.cls}.zip")
            im, _ = load_small(local_zip(path).read(row.member.split("/", 1)[1]), 320)
            im.thumbnail((240, 240)); im.save(out / f"pair{n}_{tag}.jpg", quality=85)
        meta.append({"pair": n, "distance": int(dist[k]), "test": a.member, "train": b.member})
    (out / "pairs.json").write_text(json.dumps(meta, indent=2))
    print("saved", len(meta), "pairs to", out)


def cmd_clean(args):
    shutil.rmtree(RAW, ignore_errors=True)
    print("removed", RAW)


def cmd_all(args):
    cmd_farm(args); cmd_pcr(args); cmd_farmtest(args); cmd_pairs(args)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", choices=["all", "farm", "pcr", "farmtest", "pairs", "clean"])
    ap.add_argument("--workers", type=int, default=8, help="threads that decode photos")
    ap.add_argument("--limit", type=int, default=0, help="photos per class, for a smoke test")
    args = ap.parse_args()
    {"all": cmd_all, "farm": cmd_farm, "pcr": cmd_pcr, "farmtest": cmd_farmtest, "pairs": cmd_pairs, "clean": cmd_clean}[args.job](args)
