"""Try inference changes on pen scale tiles without retraining, and score each one.

    python training/pen_tweaks.py MODEL.pt [--out training/work/pen/tweaks.json]

Changes tried, alone and together:
- zoom: cut each 640 tile into k by k parts and enlarge each to 640, so a small dropping looks bigger
- size: drop boxes larger than a dropping can be in a pen frame
- litter: keep a box only if it sits on floor coloured background and is not part of a large
  moving blob (a bird). Both checks use the clip's median background, which the Pi can keep too.

Scored on pen_test (test droppings pasted on the held out farm) and pen_test_real (same farm,
nothing pasted). A predicted box counts as a hit when its centre falls inside a pasted dropping's
box grown by 4 pixels. Classes are ignored here, the question is only where droppings are.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from pen_scale import WORK, litter_colour

PEN = WORK / "yolo" / "pen"
MAX_SIDE = 48                         # pixels in a 1280 wide frame, the largest pasted dropping is 30


def predict(model: YOLO, tile: np.ndarray, zoom: int, conf: float, imgsz: int = 640) -> np.ndarray:
    """Boxes [x1, y1, x2, y2, score] in tile pixels."""
    if zoom == 1:
        r = model.predict(tile, imgsz=imgsz, conf=conf, verbose=False)[0]
        return np.hstack([r.boxes.xyxy.cpu().numpy(), r.boxes.conf.cpu().numpy()[:, None]])
    size = 640 // zoom + 32
    starts = np.linspace(0, 640 - size, zoom).astype(int)
    parts, origins = [], []
    for y in starts:
        for x in starts:
            parts.append(cv2.resize(tile[y:y + size, x:x + size], (640, 640), interpolation=cv2.INTER_LINEAR))
            origins.append((x, y))
    out = []
    for r, (x, y) in zip(model.predict(parts, imgsz=imgsz, conf=conf, verbose=False), origins):
        b = r.boxes.xyxy.cpu().numpy() * size / 640 + np.array([x, y, x, y])
        out.append(np.hstack([b, r.boxes.conf.cpu().numpy()[:, None]]))
    b = np.vstack(out) if out else np.zeros((0, 5))
    keep = cv2.dnn.NMSBoxes(b[:, :4].tolist(), b[:, 4].tolist(), conf, 0.4) if len(b) else []
    return b[np.array(keep, int).ravel()] if len(keep) else np.zeros((0, 5))


class Scene:
    """What the median background says about one tile: where the floor is and where something big moved in."""

    def __init__(self, frames_dir: Path, meta: dict, tile: np.ndarray, litter_cache: dict):
        bg = cv2.imread(str(frames_dir / meta["bg"]))
        if meta["bg"] not in litter_cache:
            litter_cache[meta["bg"]] = litter_colour(bg)
        litter = litter_cache[meta["bg"]]
        x0, y0 = meta["x0"], meta["y0"]
        part = np.zeros_like(tile)
        crop = bg[y0:y0 + 640, x0:x0 + 640]
        part[: crop.shape[0], : crop.shape[1]] = crop
        lab = cv2.cvtColor(cv2.GaussianBlur(part, (0, 0), 3), cv2.COLOR_BGR2LAB).astype(np.float32)
        floor = (np.abs(lab[..., 0] - litter[0]) < 40) & (np.hypot(lab[..., 1] - litter[1], lab[..., 2] - litter[2]) < 12)
        self.floor = cv2.dilate(floor.astype(np.uint8), np.ones((9, 9), np.uint8))
        changed = (cv2.absdiff(tile, part).max(2) > 25).astype(np.uint8)
        changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        _, self.blobs, stats, _ = cv2.connectedComponentsWithStats(changed)
        self.blob_area = stats[:, cv2.CC_STAT_AREA]

    def keep(self, box) -> bool:
        x1, y1, x2, y2 = (int(v) for v in box[:4])
        cx, cy = min(639, (x1 + x2) // 2), min(639, (y1 + y2) // 2)
        if not self.floor[cy, cx]:
            return False
        win = self.blobs[max(0, y1):y2 + 1, max(0, x1):x2 + 1]
        ids = np.unique(win[win > 0])
        big = max((self.blob_area[i] for i in ids), default=0)
        return big < 1600                       # a blob bigger than 40 by 40 is a bird or a person, not a dropping


def load_gt(label: Path) -> np.ndarray:
    rows = [list(map(float, l.split()[1:])) for l in label.read_text().splitlines() if l.strip()]
    g = np.array(rows).reshape(-1, 4) * 640
    return np.stack([g[:, 0] - g[:, 2] / 2, g[:, 1] - g[:, 3] / 2, g[:, 0] + g[:, 2] / 2, g[:, 1] + g[:, 3] / 2], 1) if len(g) else np.zeros((0, 4))


def ap_and_points(preds, n_gt):
    """preds: list of (score, hit). Returns average precision and precision and recall at a few cutoffs."""
    if not preds:
        return 0.0, {}
    p = sorted(preds, key=lambda t: -t[0])
    hits = np.array([h for _, h in p], float)
    tp = np.cumsum(hits)
    rec = tp / max(1, n_gt)
    prec = tp / np.arange(1, len(p) + 1)
    ap = float(np.trapezoid(np.maximum.accumulate(prec[::-1])[::-1], rec)) if len(p) > 1 else 0.0
    points = {}
    scores = np.array([s for s, _ in p])
    for c in (0.25, 0.4, 0.55):
        k = int((scores >= c).sum())
        points[c] = {"recall": round(float(tp[k - 1] / n_gt) if k else 0.0, 3),
                     "precision": round(float(tp[k - 1] / k) if k else 0.0, 3)}
    return round(ap, 4), points


def run(model, variant, cache, imgsz=640):
    zoom, size_on, litter_on = variant
    frames_dir = WORK / "frames" / "test"
    res = {}
    for split in ("test", "test_real"):
        d = PEN / split
        meta = {m["tile"]: m for m in json.loads((d / "tiles.json").read_text())}
        preds, n_gt, n_boxes, n_tiles = [], 0, 0, 0
        for img in sorted((d / "images").glob("*.jpg")):
            tile = cv2.imread(str(img))
            key = (split, img.stem, zoom)
            if key not in cache:
                cache[key] = predict(model, tile, zoom, 0.1, imgsz)
            boxes = cache[key]
            if size_on and len(boxes):
                side = np.maximum(boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1])
                boxes = boxes[side <= MAX_SIDE]
            if litter_on and len(boxes):
                scene = Scene(frames_dir, meta[img.stem], tile, cache.setdefault("litter", {}))
                boxes = boxes[[scene.keep(b) for b in boxes]] if len(boxes) else boxes
            n_tiles += 1
            if split == "test_real":
                n_boxes += int((boxes[:, 4] >= 0.4).sum()) if len(boxes) else 0
                continue
            gt = load_gt(d / "labels" / f"{img.stem}.txt")
            n_gt += len(gt)
            used = set()
            for b in boxes[np.argsort(-boxes[:, 4])] if len(boxes) else []:
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                hit = False
                for j, g in enumerate(gt):
                    if j not in used and g[0] - 4 <= cx <= g[2] + 4 and g[1] - 4 <= cy <= g[3] + 4:
                        used.add(j)
                        hit = True
                        break
                preds.append((float(b[4]), hit))
        if split == "test":
            res["ap"], res["at"] = ap_and_points(preds, n_gt)
        else:
            res["real_boxes_per_tile_conf0.4"] = round(n_boxes / n_tiles, 3)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights")
    ap.add_argument("--out", type=Path, default=WORK / "tweaks.json")
    ap.add_argument("--zooms", default="1,2,3")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()
    model = YOLO(args.weights)
    cache: dict = {}
    rows = []
    for zoom in map(int, args.zooms.split(",")):
        for size_on, litter_on in ((False, False), (True, False), (False, True), (True, True)):
            r = run(model, (zoom, size_on, litter_on), cache, args.imgsz)
            row = {"zoom": zoom, "size_filter": size_on, "litter_filter": litter_on, **r}
            rows.append(row)
            print(json.dumps(row), flush=True)
    args.out.write_text(json.dumps({"model": args.weights, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
