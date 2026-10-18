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
import behaviour as B
import os
import spots as S
from clips import MEDIA

CONF = 0.25
PEN_MODEL = D.REPO / "models" / "dropping4-pen" / "dropping4pen_yolo11n_640.onnx"
PEN_METRICS = PEN_MODEL.parent / "test_metrics.json"
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


CROP_PX = 96          # window of the frame shown when a spot is opened, enlarged three times


def explain(frame: np.ndarray, b, bg: S.Background, seen: int) -> dict:
    """What the dashboard shows when a spot is opened: a zoomed crop, where the box sits in it, and the measured
    reasons. Every number here is measured from the pixels or read from the model, nothing is written by hand."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in b[:4])
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    x0, y0 = min(max(0, cx - CROP_PX // 2), w - CROP_PX), min(max(0, cy - CROP_PX // 2), h - CROP_PX)
    crop = cv2.resize(frame[y0:y0 + CROP_PX, x0:x0 + CROP_PX], (CROP_PX * 3, CROP_PX * 3), interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB).astype(np.float32)
    inner = np.zeros((h, w), bool)
    inner[max(0, y1):y2, max(0, x1):x2] = True
    ring = np.zeros((h, w), bool)
    ring[max(0, y1 - 10):y2 + 10, max(0, x1 - 10):x2 + 10] = True
    ring &= ~inner
    a, r = lab[inner].mean(0), lab[ring].mean(0)
    changed = float(np.abs(frame[inner].astype(np.int16) - bg.image[inner].astype(np.int16)).max(1).mean())
    return {
        "crop": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode(),
        "cropBox": [round((x1 - x0) / CROP_PX, 3), round((y1 - y0) / CROP_PX, 3), round((x2 - x0) / CROP_PX, 3), round((y2 - y0) / CROP_PX, 3)],
        "sizePx": int(max(x2 - x1, y2 - y1)),
        "darker": round(float(r[0] - a[0]) * 100 / 255, 1),           # lightness below the litter around it, percent
        "colourShift": round(float(np.hypot(*(a[1:] - r[1:]))), 1),   # distance in the a and b colour channels
        "vsBackground": round(changed, 1),                             # mean change from the empty floor image, 0 to 255
        "seen": int(seen),
        "scores": {c: round(float(p), 3) for c, p in zip(D.CLASSES, b[6:10])},
    }


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
    # Rishit's bird models, only where they fit (white broilers). They drop dropping boxes that sit on a bird,
    # and give the flock behaviour every BEHAVIOUR_EVERY seconds. HC_NO_BIRD_FILTER=1 turns the filter off to compare.
    birds_on = clip["id"] in B.BIRD_CLIPS
    bird_filter = birds_on and os.environ.get("HC_NO_BIRD_FILTER") != "1"
    det_b, cls_b = B.load() if birds_on else (None, None)
    beh = {"classes": B.BEHAVIOURS, "times": [], "shares": [], "birds": [], "classified": []}
    on_birds = 0
    every = 10.0 if length <= LONG else 30.0
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
        if birds_on:
            flock = B.birds(det_b, frame)
            if bird_filter and len(kept):
                mask = np.array([not B.on_bird(b, flock) for b in kept])
                on_birds += int((~mask).sum())
                kept = kept[mask]
            if not beh["times"] or t - beh["times"][-1] >= every:
                ids = B.behaviour(cls_b, frame, flock, seed=len(beh["times"]))
                counts = np.bincount(ids, minlength=len(B.BEHAVIOURS)) if ids else np.zeros(len(B.BEHAVIOURS), int)
                beh["times"].append(round(t, 2))
                beh["birds"].append(int(len(flock)))
                beh["classified"].append(len(ids))
                beh["shares"].append([round(float(c) / max(1, len(ids)), 3) for c in counts])
        dets.append([[round(float(b[0]) / W, 4), round(float(b[1]) / H, 4), round(float(b[2]) / W, 4), round(float(b[3]) / H, 4),
                      D.CLASSES[int(b[4])], round(float(b[5]), 2)] for b in kept])
        for b, seen in persist.update(kept):
            found.append({"t": round(t, 2), "box": [round(float(b[0]) / W, 4), round(float(b[1]) / H, 4), round(float(b[2]) / W, 4), round(float(b[3]) / H, 4)],
                          "cls": D.CLASSES[int(b[4])], "score": round(float(b[5]), 2), "window": persist.window, **explain(frame, b, bg, seen)})
        if len(times) % 200 == 0:
            print(f"  {clip['id']}: {t / 60:.1f} of {length / 60:.1f} min, {len(found)} spots", flush=True)
        idx += 1
    cap.release()
    duration = min(length, idx / fps)
    result = {
        "id": clip["id"], "width": S.FRAME_W, "height": H, "duration": round(duration, 2), "rate": rate, "times": times,
        "model": MODEL_NAME, "conf": CONF, "evaluation": EVALUATION,
        "activity": acts, "raw": raws, "detections": dets, "spots": found,
        "behaviour": beh if birds_on else None, "birdFilter": {"on": bird_filter, "removedBoxes": on_birds},
        "summary": {"samples": len(acts),
                    "meanRawBoxesPerFrame": round(float(np.mean(raws)), 1) if raws else 0,
                    "meanBoxesPerFrame": round(float(np.mean([len(d) for d in dets])), 2) if dets else 0,
                    "spots": len(found),
                    "meanActivity": round(float(np.mean(acts)), 2) if acts else 0},
    }
    print(f"{clip['id']}: {len(acts)} samples, {result['summary']['meanRawBoxesPerFrame']} raw and "
          f"{result['summary']['meanBoxesPerFrame']} kept boxes a frame, {len(found)} spots, {time.time() - t0:.0f}s", flush=True)
    return result


MODEL_NAME = "dropping4-laptop 640 onnx, zoomed, size and litter filtered"
EVALUATION = None


CLOSEUP_SESSION = None


def closeup_of(photo: str) -> dict | None:
    """The real close-up photo a test dropping was cut from, judged by the close-up model (dropping4-laptop).
    This is the second step the system is built for: the pen camera finds a spot, a close-up judges it."""
    global CLOSEUP_SESSION
    import zipfile
    sys.path.insert(0, str(D.REPO / "training"))
    from pen_scale import RAW
    cls = photo.split("/")[0]
    try:
        with zipfile.ZipFile(RAW / f"{cls}.zip") as z:
            name = next(n for n in z.namelist() if n.endswith("/" + photo.split("/")[1]))
            img = cv2.imdecode(np.frombuffer(z.read(name), np.uint8), cv2.IMREAD_COLOR)
    except (OSError, StopIteration):
        return None                                               # Machuve zips not on this machine
    if CLOSEUP_SESSION is None:
        CLOSEUP_SESSION = D.load_session()                        # the close-up model, not the pen model
    h, w = img.shape[:2]
    s = 640 / max(h, w)
    small = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    boxes = D.detect(CLOSEUP_SESSION, small, conf=0.1)
    ok, buf = cv2.imencode(".jpg", cv2.resize(small, (round(small.shape[1] * 0.6), round(small.shape[0] * 0.6))), [cv2.IMWRITE_JPEG_QUALITY, 82])
    out = {"img": "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode(), "box": None, "scores": None}
    if len(boxes):
        b = boxes[np.argmax(boxes[:, 5])]
        H, W = small.shape[:2]
        out["box"] = [round(float(b[0]) / W, 4), round(float(b[1]) / H, 4), round(float(b[2]) / W, 4), round(float(b[3]) / H, 4)]
        out["scores"] = {c: round(float(p), 3) for c, p in zip(D.CLASSES, b[6:10])}
    return out


def score_truth(truth: list[dict], spots: list[dict]) -> list[dict]:
    """A pasted dropping counts as found when a spot lands inside its box, grown by 1 percent of the frame, after it appeared."""
    used, out = set(), []
    for t in truth:
        x1, y1, x2, y2 = t["box"]
        hit = None
        for k, s in enumerate(spots):
            cx, cy = (s["box"][0] + s["box"][2]) / 2, (s["box"][1] + s["box"][3]) / 2
            if k not in used and s["t"] >= t["t"] and x1 - 0.01 <= cx <= x2 + 0.01 and y1 - 0.01 <= cy <= y2 + 0.01:
                used.add(k)
                hit = s["t"]
                break
        if hit is not None:
            spots[k]["truth"] = {"cls": t["cls"], "photo": t["photo"], "closeup": closeup_of(t["photo"])}   # answer key and its source photo
        out.append({**t, "foundAt": hit})
    return out


def main() -> None:
    global MODEL_NAME, EVALUATION
    out = MEDIA / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    pen = "--closeup" not in sys.argv
    if pen:                                                      # the pen scale model from training/pen_train.py
        S.CROP, S.USE_LITTER, S.FLOOR_ONLY = 640, False, True
        sess = D.load_session(PEN_MODEL)
        MODEL_NAME = "dropping4-pen 640 onnx, 640 squares at camera size, size filtered"
        if PEN_METRICS.exists():
            m = json.loads(PEN_METRICS.read_text())
            EVALUATION = {"heldOut": True, "recall": m["pen_test_recall_any_class"], "precision": m["pen_test_precision_any_class"],
                          "realBoxesPerTile": m["pen_test_real_boxes_per_tile_conf0.25"],
                          "note": "Measured on test droppings pasted onto held out cameras, including this feed's camera. Pasted droppings are a stand in, real ones in these videos are not labelled."}
    else:
        sess = D.load_session()
    print("detector running on", sess.get_providers()[0], flush=True)
    only = {a for a in sys.argv[1:] if not a.startswith("--")}
    for clip in json.loads((MEDIA / "clips.json").read_text()):          # every installed clip, including test clips
        if only and clip["id"] not in only:
            continue
        if (MEDIA / "clips" / f"{clip['id']}.mp4").exists():
            result = analyze(clip, sess)
            truth_file = out / f"{clip['id']}.truth.json"
            if truth_file.exists():
                result["truth"] = score_truth(json.loads(truth_file.read_text()), result["spots"])
                hits = sum(1 for t in result["truth"] if t["foundAt"] is not None)
                print(f"  answer key: found {hits} of {len(result['truth'])} pasted droppings", flush=True)
            (out / f"{clip['id']}.json").write_text(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
