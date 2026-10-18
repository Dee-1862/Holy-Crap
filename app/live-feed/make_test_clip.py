"""Make a labelled test feed: real held out barn video with known droppings pasted in at known times.

    python app/live-feed/make_test_clip.py

Takes three minutes of the PIO 0002 feed (never used in training), and at set times drops in droppings cut from
Machuve test photos (never used in training). Each dropping is blended only where no bird is standing, so birds
walk over it as they would a real one. The times and places are saved as an answer key, and the dashboard marks
the clip as a test, so a viewer can see the detector find them and count what it missed.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from clips import MEDIA, REPO
from fetch_clips import ffmpeg

sys.path.insert(0, str(REPO / "training"))
from pen_scale import WORK, litter_colour  # noqa: E402

SOURCE = MEDIA / "clips" / "pio-0002.mp4"
ID = "test-a1"
START_S, LENGTH_S, DROPS, SEED = 1800, 180, 10, 7


def main():
    rng = random.Random(SEED)
    cap = cv2.VideoCapture(str(SOURCE))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.set(cv2.CAP_PROP_POS_MSEC, START_S * 1000)
    frames = []
    for _ in range(int(LENGTH_S * fps)):
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    H, W = frames[0].shape[:2]
    bg = np.median(np.stack(frames[:: max(1, len(frames) // 40)]), 0).astype(np.uint8)
    litter = litter_colour(bg)
    lab = cv2.cvtColor(cv2.GaussianBlur(bg, (0, 0), 3), cv2.COLOR_BGR2LAB).astype(np.float32)
    floor = (np.abs(lab[..., 0] - litter[0]) < 40) & (np.hypot(lab[..., 1] - litter[1], lab[..., 2] - litter[2]) < 12)
    floor = cv2.erode(floor.astype(np.uint8), np.ones((25, 25), np.uint8))
    floor[: H // 8] = 0                                            # keep clear of the timestamp overlay

    bank = [b for b in json.loads((WORK / "bank" / "index.json").read_text()) if b["split"] == "test"]
    ys, xs = np.nonzero(floor)
    drops = []
    for k in range(DROPS):
        b = rng.choice(bank)
        img = cv2.imread(str(WORK / "bank" / "test" / b["file"]), cv2.IMREAD_UNCHANGED)
        L = rng.uniform(14, 28)
        s = L / max(img.shape[:2])
        img = cv2.resize(img, (max(3, round(img.shape[1] * s)), max(3, round(img.shape[0] * s))), interpolation=cv2.INTER_AREA)
        i = rng.randrange(len(xs))
        x, y = int(xs[i]) - img.shape[1] // 2, int(ys[i]) - img.shape[0] // 2
        region = bg[y:y + img.shape[0], x:x + img.shape[1]].astype(np.float32)
        a = img[..., 3:].astype(np.float32) / 255
        rgb = img[..., :3].astype(np.float32)
        gain = (region.mean() + 1) / (rgb[a[..., 0] > 0.5].mean() + 1) * rng.uniform(0.55, 0.95)
        t = round(10 + k * (LENGTH_S - 40) / DROPS + rng.uniform(0, 8), 1)
        drops.append({"t": t, "x": x, "y": y, "rgb": np.clip(rgb * gain, 0, 255), "a": a, "cls": b["cls"], "photo": b["photo"],
                      "box": [round(x / W, 4), round(y / H, 4), round((x + img.shape[1]) / W, 4), round((y + img.shape[0]) / H, 4)]})

    out = MEDIA / "clips" / f"{ID}.mp4"
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n, f in enumerate(frames):
        t = n / fps
        for d in drops:
            if t < d["t"]:
                continue
            h, w = d["a"].shape[:2]
            reg = f[d["y"]:d["y"] + h, d["x"]:d["x"] + w].astype(np.float32)
            free = (np.abs(reg - bg[d["y"]:d["y"] + h, d["x"]:d["x"] + w]).max(2, keepdims=True) < 30).astype(np.float32)  # no bird here now
            a = d["a"] * free
            f[d["y"]:d["y"] + h, d["x"]:d["x"] + w] = (d["rgb"] * a + reg * (1 - a)).astype(np.uint8)
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    proc.wait()

    truth = [{"t": d["t"], "box": d["box"], "cls": d["cls"], "photo": d["photo"]} for d in drops]
    (MEDIA / "analysis").mkdir(exist_ok=True)
    (MEDIA / "analysis" / f"{ID}.truth.json").write_text(json.dumps(truth, indent=1))
    manifest = [c for c in json.loads((MEDIA / "clips.json").read_text()) if c["id"] != ID]
    manifest.insert(0, {"id": ID, "pen": "A1", "title": "Test, 10 droppings pasted in",
                        "view": "Three held out minutes of the Pen A1 feed with test droppings added at known times. An answer key checks the detector.",
                        "source": "PIO 0002 with Machuve test droppings", "sourceUrl": "https://zenodo.org/records/16686320",
                        "license": "CC BY 4.0", "bytes": out.stat().st_size, "test": True})
    (MEDIA / "clips.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {out.name}, {len(frames)} frames, {len(truth)} droppings at", [d["t"] for d in truth])


if __name__ == "__main__":
    main()
