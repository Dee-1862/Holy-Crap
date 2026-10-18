"""Analyze each live feed clip once, ahead of time, and save the result next to it.

    python app/live-feed/analyze_clips.py

For every clip it samples two frames a second and records
  activity    how much of the picture changed since the previous sample (flock motion, as a percent)
  detections  the dropping detector's raw boxes, run in tiles (see detector.py)

The activity signal is dependable. The detector boxes are NOT: tried on these barn clips they land on birds,
feeders and wire mesh, not droppings, because the detector was trained on close-up photos. They are saved so the
dashboard can show them behind an "experimental" switch, and the clip summary says so.
"""
from __future__ import annotations

import json
import time

import cv2
import numpy as np

import detector as D
from clips import CLIPS, MEDIA

RATE = 2.0           # samples per second
CONF = 0.40
TILE_FRACTION = 0.4  # tile edge as a share of the short side of the frame


def activity(prev: np.ndarray | None, gray: np.ndarray) -> float:
    if prev is None:
        return 0.0
    diff = cv2.absdiff(prev, gray)
    return float((diff > 18).mean() * 100)


def analyze(clip: dict, sess) -> dict:
    path = MEDIA / "clips" / f"{clip['id']}.mp4"
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(3)), int(cap.get(4))
    duration = n / fps
    tile = int(min(w, h) * TILE_FRACTION)
    step = max(1, round(fps / RATE))
    acts, dets, times, prev, idx = [], [], [], None, 0
    t0 = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            gray = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (160, int(160 * h / w))), cv2.COLOR_BGR2GRAY), (5, 5), 0)
            times.append(round(idx / fps, 3))                    # the exact time of this sample in the clip
            acts.append(round(activity(prev, gray), 2))
            prev = gray
            b = D.detect(sess, frame, conf=CONF, tile=tile)
            dets.append([[round(float(x1) / w, 4), round(float(y1) / h, 4), round(float(x2) / w, 4), round(float(y2) / h, 4),
                          D.CLASSES[int(c)], round(float(s), 2)] for x1, y1, x2, y2, c, s in b])
        idx += 1
    cap.release()
    duration = idx / fps                                         # what actually decoded, which can differ from the header
    counts = [len(d) for d in dets]
    result = {
        "id": clip["id"], "width": w, "height": h, "duration": round(duration, 2), "rate": RATE, "times": times,
        "model": "dropping4-laptop 640 onnx", "tile": tile, "conf": CONF,
        "activity": acts, "detections": dets,
        "summary": {"samples": len(acts), "meanBoxesPerFrame": round(float(np.mean(counts)), 1) if counts else 0,
                    "meanActivity": round(float(np.mean(acts)), 2) if acts else 0},
    }
    print(f"{clip['id']}: {len(acts)} samples, {result['summary']['meanBoxesPerFrame']} boxes a frame, "
          f"{result['summary']['meanActivity']}% mean motion, {time.time() - t0:.0f}s", flush=True)
    return result


def main() -> None:
    out = MEDIA / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    sess = D.load_session()
    for clip in CLIPS:
        if (MEDIA / "clips" / f"{clip['id']}.mp4").exists():
            (out / f"{clip['id']}.json").write_text(json.dumps(analyze(clip, sess), separators=(",", ":")))


if __name__ == "__main__":
    main()
