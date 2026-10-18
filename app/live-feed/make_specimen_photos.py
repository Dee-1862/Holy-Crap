"""Give every demo specimen a real close-up photo and the close-up model's real reading of it.

    python app/live-feed/make_specimen_photos.py

For each specimen in app/console/src/lib/data.ts it takes a Machuve test photo of the same type (never used in
training) on which the close-up model (dropping4-laptop) agrees with that type, crops it around the model's box,
and saves the crop, the box and the four class scores. Reference examples come from the training split.
Writes app/console/public/specimens/*.jpg and app/console/src/lib/specimen-photos.json. Machuve photos are CC BY 4.0.
"""
from __future__ import annotations

import json
import random
import re
import sys
import zipfile

import cv2
import numpy as np

import detector as D
from clips import REPO

sys.path.insert(0, str(REPO / "training"))
from pen_scale import RAW, split_map  # noqa: E402

CONSOLE = REPO / "app" / "console"
OUT = CONSOLE / "public" / "specimens"
TO_CLASS = {"healthy": "healthy", "coccidiosis": "cocci", "salmonella": "salmo", "ncd": "ncd"}
TO_TYPE = {v: k for k, v in TO_CLASS.items()}


def read(z: zipfile.ZipFile, names: dict[str, str], stem: str):
    return cv2.imdecode(np.frombuffer(z.read(names[f"{stem}.jpg"]), np.uint8), cv2.IMREAD_COLOR)


def judge(sess, img):
    """Close-up model on the whole photo: top box in photo pixels and its four class scores."""
    h, w = img.shape[:2]
    s = 640 / max(h, w)
    small = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    b = D.detect(sess, small, conf=0.25)
    if not len(b):
        return None
    top = b[np.argmax(b[:, 5])]
    return top[:4] / s, dict(zip(D.CLASSES, map(float, top[6:10])))


def crop43(img, box, out_w):
    """A 4 by 3 crop centred on the box with room around it. Returns the image and the box inside it as shares."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = box
    cw = min(w, max((x2 - x1) * 2.2, (y2 - y1) * 2.2 * 4 / 3))
    ch = min(h, cw * 3 / 4)
    cw = ch * 4 / 3
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    X1 = int(min(max(0, cx - cw / 2), w - cw)); Y1 = int(min(max(0, cy - ch / 2), h - ch))
    crop = img[Y1:Y1 + int(ch), X1:X1 + int(cw)]
    crop = cv2.resize(crop, (out_w, out_w * 3 // 4), interpolation=cv2.INTER_AREA)
    rel = [(x1 - X1) / cw, (y1 - Y1) / ch, (x2 - X1) / cw, (y2 - Y1) / ch]
    return crop, [round(float(min(1, max(0, v))), 4) for v in rel]


def main():
    specs = re.findall(r'id: "(E-\d+)", minsAgo: \d+, group: "\w+", type: "(\w+)"', (CONSOLE / "src" / "lib" / "data.ts").read_text())
    split = split_map()
    sess = D.load_session()                                        # the close-up model
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    used, result, refs = set(), {}, {}
    for cls in sorted({TO_CLASS[t] for _, t in specs} | set(TO_CLASS.values())):
        z = zipfile.ZipFile(RAW / f"{cls}.zip")
        names = {n.split("/")[-1]: n for n in z.namelist() if n.endswith(".jpg")}
        test = sorted(s for (c, s), p in split.items() if c == cls and p == "test")
        train = sorted(s for (c, s), p in split.items() if c == cls and p == "train")
        rng.shuffle(test); rng.shuffle(train)
        want = [i for i, t in specs if TO_CLASS[t] == cls]
        for stem in test:
            if not want:
                break
            img = read(z, names, stem)
            got = judge(sess, img) if img is not None else None
            if not got or max(got[1], key=got[1].get) != cls or got[1][cls] < 0.5:
                continue                                           # keep only photos the model reads as this type
            sid = want.pop(0)
            crop, box = crop43(img, got[0], 480)
            cv2.imwrite(str(OUT / f"{sid}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 84])
            total = sum(got[1].values()) or 1
            result[sid] = {"src": f"/specimens/{sid}.jpg", "box": box, "photo": f"{cls}/{stem}.jpg",
                           "scores": {TO_TYPE[c]: round(v, 3) for c, v in got[1].items()},
                           "probs": {TO_TYPE[c]: round(v / total, 3) for c, v in got[1].items()}}
            print(sid, cls, stem, round(got[1][cls], 2), flush=True)
        refs[TO_TYPE[cls]] = []
        for stem in train:
            if len(refs[TO_TYPE[cls]]) == 3:
                break
            img = read(z, names, stem)
            got = judge(sess, img) if img is not None else None
            if not got or max(got[1], key=got[1].get) != cls:
                continue
            crop, _ = crop43(img, got[0], 240)
            k = len(refs[TO_TYPE[cls]])
            cv2.imwrite(str(OUT / f"ref_{cls}_{k}.jpg"), crop, [cv2.IMWRITE_JPEG_QUALITY, 80])
            refs[TO_TYPE[cls]].append(f"/specimens/ref_{cls}_{k}.jpg")
    missing = [i for i, _ in specs if i not in result]
    if missing:
        raise SystemExit(f"no matching photo for {missing}")
    (CONSOLE / "src" / "lib" / "specimen-photos.json").write_text(json.dumps({"specimens": result, "refs": refs}, indent=1))
    print("wrote", len(result), "specimen photos and", sum(map(len, refs.values())), "references")


if __name__ == "__main__":
    main()
