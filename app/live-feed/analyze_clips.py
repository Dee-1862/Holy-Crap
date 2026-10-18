"""Analyze each live feed clip once, ahead of time, and save the result next to it.

    python app/live-feed/analyze_clips.py [clip id ...]

For every clip it samples frames (twice a second for short clips, every two seconds for long feeds) and records
  activity    how much of the picture changed since the previous sample (flock motion, as a percent)
  raw         how many boxes the zoomed detector gave before any filtering
  detections  boxes that pass the size and litter checks in spots.py
  spots       places where boxes kept landing over several samples, with a small crop of each

The motion signal is dependable. The spots come from a detector trained on close-up photos, adapted with the
steps in spots.py. On pasted droppings from a held out farm those steps find about 3 in 10 droppings with about
2 in 3 boxes correct. No real droppings in these clips are labelled, so the spots shown here are unverified.
"""
from __future__ import annotations

import base64
import json
import sys
import time

import cv2
import numpy as np

import detector as D
import spots as S
from clips import CLIPS, MEDIA

CONF = 0.25
LONG = 600            # clips longer than this many seconds are sampled more slowly
SEGMENT = 300         # seconds of video behind each background image


def activity(prev: np.ndarray | None, gray: np.ndarray) -> float:
    if prev is None:
        return 0.0
    return float((cv2.absdiff(prev, gray) > 18).mean() * 100)


def to_width(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    return frame if w == S.FRAME_W else cv2.resize(frame, (S.FRAME_W, round(h * S.FRAME_W / w)), interpolation=cv2.INTER_LINEAR)


def background_at(cap, fps: float, start: float, end: float) -> S.Background:
    frames = []
    for t in np.linspace(start, max(start, end - 0.5), 21):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
        ok, f = cap.read()
        if ok:
            frames.append(to_width(f))
    return S.Background(frames)


def crop_of(frame: np.ndarray, b) -> str:
    """A 64 pixel square around the spot, enlarged to 160, as a data URL for the dashboard."""
    cx, cy = int((b[0] + b[2]) / 2), int((b[1] + b[3]) / 2)
    h, w = frame.shape[:2]
    x0, y0 = min(max(0, cx - 32), w - 64), min(max(0, cy - 32), h - 64)
    crop = cv2.resize(frame[y0:y0 + 64, x0:x0 + 64], (160, 160), interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def analyze(clip: dict, sess) -> dict:
    path = MEDIA / "clips" / f"{clip['id']}.mp4"
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    length = n / fps
    rate = 0.5 if length > LONG else 2.0
    step = max(1, round(fps / rate))
    seg_len = SEGMENT if length > LONG else length + 1
    bg_cap = cv2.VideoCapture(str(path))
    acts, raws, dets, times, found = [], [], [], [], []
    prev, seg, bg, persist = None, -1, None, S.Persistence()
    t0, idx = time.time(), 0
    while idx < n:
        if idx % step:
            ok = cap.grab()                                       # skip without decoding into an image
            idx += 1
            if not ok:
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        if int(t // seg_len) != seg:
            seg = int(t // seg_len)
            bg = background_at(bg_cap, fps, seg * seg_len, min(length, (seg + 1) * seg_len))
        frame = to_width(frame)
        H, W = frame.shape[:2]
        gray = cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame, (160, int(160 * H / W))), cv2.COLOR_BGR2GRAY), (5, 5), 0)
        times.append(round(t, 3))
        acts.append(round(activity(prev, gray), 2))
        prev = gray
        raw, kept = S.filtered(sess, frame, bg, CONF)
        raws.append(len(raw))
        dets.append([[round(float(b[0]) / W, 4), round(float(b[1]) / H, 4), round(float(b[2]) / W, 4), round(float(b[3]) / H, 4),
                      D.CLASSES[int(b[4])], round(float(b[5]), 2)] for b in kept])
        for b in persist.update(kept):
            found.append({"t": round(t, 2), "box": [round(float(b[0]) / W, 4), round(float(b[1]) / H, 4), round(float(b[2]) / W, 4), round(float(b[3]) / H, 4)],
                          "cls": D.CLASSES[int(b[4])], "score": round(float(b[5]), 2), "crop": crop_of(frame, b)})
        if len(times) % 200 == 0:
            print(f"  {clip['id']}: {t / 60:.1f} of {length / 60:.1f} min, {len(found)} spots", flush=True)
        idx += 1
    cap.release()
    duration = min(length, idx / fps)
    result = {
        "id": clip["id"], "width": S.FRAME_W, "height": H, "duration": round(duration, 2), "rate": rate, "times": times,
        "model": "dropping4-laptop 640 onnx, zoomed, size and litter filtered", "conf": CONF,
        "activity": acts, "raw": raws, "detections": dets, "spots": found,
        "summary": {"samples": len(acts),
                    "meanRawBoxesPerFrame": round(float(np.mean(raws)), 1) if raws else 0,
                    "meanBoxesPerFrame": round(float(np.mean([len(d) for d in dets])), 2) if dets else 0,
                    "spots": len(found),
                    "meanActivity": round(float(np.mean(acts)), 2) if acts else 0},
    }
    print(f"{clip['id']}: {len(acts)} samples, {result['summary']['meanRawBoxesPerFrame']} raw and "
          f"{result['summary']['meanBoxesPerFrame']} kept boxes a frame, {len(found)} spots, {time.time() - t0:.0f}s", flush=True)
    return result


def main() -> None:
    out = MEDIA / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    sess = D.load_session()
    print("detector running on", sess.get_providers()[0], flush=True)
    only = set(sys.argv[1:])
    for clip in CLIPS:
        if only and clip["id"] not in only:
            continue
        if (MEDIA / "clips" / f"{clip['id']}.mp4").exists():
            (out / f"{clip['id']}.json").write_text(json.dumps(analyze(clip, sess), separators=(",", ":")))


if __name__ == "__main__":
    main()
