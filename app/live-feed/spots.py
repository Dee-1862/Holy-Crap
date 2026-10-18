"""Find droppings in a pen camera with the close-up detector, by zooming in and filtering what it says.

Measured on pasted droppings from a farm the model never saw (training/pen_tweaks.py), these steps
took average precision from 0.025 to 0.27 and cut boxes on real frames by about seven times:

1. zoom     cut the 1280 wide frame into overlapping squares about 245 pixels wide and enlarge each to 640
2. size     drop boxes longer than 48 pixels, a dropping in a pen camera is 8 to 30
3. litter   keep a box only on floor coloured background and outside any large changed blob (a bird)
4. persist  report a spot only when boxes land in the same place in most recent samples, because a
            dropping stays put and a bird does not. This step is new here and not in the measured numbers.

Everything except the detector call is plain image arithmetic the Pi can do at low resolution.
"""
from __future__ import annotations

import cv2
import numpy as np

import detector as D

FRAME_W = 1280
CROP = 640 // 3 + 32
MAX_SIDE = 48
BIG_BLOB = 1600


def litter_colour(bg: np.ndarray) -> np.ndarray:
    """Most common colour in the lower two thirds of the empty background, which is the floor."""
    lab = cv2.cvtColor(cv2.GaussianBlur(bg, (0, 0), 3), cv2.COLOR_BGR2LAB)[bg.shape[0] // 3:].reshape(-1, 3)
    q = (lab // 12).astype(np.int32)
    key = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    keys, counts = np.unique(key, return_counts=True)
    return np.median(lab[key == keys[np.argmax(counts)]], 0)


class Background:
    """Median of frames spread over a stretch of video. Birds move, so they drop out and the floor stays."""

    def __init__(self, frames: list[np.ndarray]):
        self.image = np.median(np.stack(frames), 0).astype(np.uint8)
        litter = litter_colour(self.image)
        lab = cv2.cvtColor(cv2.GaussianBlur(self.image, (0, 0), 3), cv2.COLOR_BGR2LAB).astype(np.float32)
        floor = (np.abs(lab[..., 0] - litter[0]) < 40) & (np.hypot(lab[..., 1] - litter[1], lab[..., 2] - litter[2]) < 12)
        self.floor = cv2.dilate(floor.astype(np.uint8), np.ones((9, 9), np.uint8))


def zoomed(sess, frame: np.ndarray, conf: float) -> np.ndarray:
    h, w = frame.shape[:2]
    xs = np.linspace(0, w - CROP, max(2, round(w / (CROP - 32)))).astype(int)
    ys = np.linspace(0, h - CROP, max(2, round(h / (CROP - 32)))).astype(int)
    found = []
    for y in ys:
        for x in xs:
            crop = cv2.resize(frame[y:y + CROP, x:x + CROP], (640, 640), interpolation=cv2.INTER_LINEAR)
            b = D._run(sess, crop, conf)
            if len(b):
                b[:, :4] = b[:, :4] * CROP / 640 + np.array([x, y, x, y])
                found.append(b)
    return D._nms(np.concatenate(found), 0.4) if found else np.zeros((0, 6), np.float32)


def filtered(sess, frame: np.ndarray, bg: Background, conf: float) -> tuple[np.ndarray, np.ndarray]:
    """The zoomed detector's boxes [x1, y1, x2, y2, class, score], and the ones that pass the size and litter checks."""
    raw = zoomed(sess, frame, conf)
    if not len(raw):
        return raw, raw
    side = np.maximum(raw[:, 2] - raw[:, 0], raw[:, 3] - raw[:, 1])
    boxes = raw[side <= MAX_SIDE]
    if not len(boxes):
        return raw, boxes
    changed = (cv2.absdiff(frame, bg.image).max(2) > 25).astype(np.uint8)
    changed = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    _, blobs, stats, _ = cv2.connectedComponentsWithStats(changed)
    area = stats[:, cv2.CC_STAT_AREA]
    keep = []
    h, w = frame.shape[:2]
    for b in boxes:
        x1, y1, x2, y2 = (int(v) for v in b[:4])
        cx, cy = min(w - 1, max(0, (x1 + x2) // 2)), min(h - 1, max(0, (y1 + y2) // 2))
        win = blobs[max(0, y1):y2 + 1, max(0, x1):x2 + 1]
        big = max((area[i] for i in np.unique(win[win > 0])), default=0)
        keep.append(bool(bg.floor[cy, cx]) and big < BIG_BLOB)
    return raw, boxes[np.array(keep)]


class Persistence:
    """Report a spot when boxes keep landing within a few pixels of it in most of the recent samples."""

    def __init__(self, window: int = 6, need: int = 4, radius: float = 12):
        self.window, self.need, self.radius = window, need, radius
        self.history: list[np.ndarray] = []
        self.reported: list[tuple[float, float]] = []

    def update(self, boxes: np.ndarray) -> list[np.ndarray]:
        self.history = (self.history + [boxes])[-self.window:]
        new = []
        for b in boxes:
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            if any(np.hypot(cx - x, cy - y) < self.radius * 2 for x, y in self.reported):
                continue
            seen = sum(any(np.hypot(cx - (o[0] + o[2]) / 2, cy - (o[1] + o[3]) / 2) < self.radius for o in past) for past in self.history)
            if seen >= self.need:
                self.reported.append((cx, cy))
                new.append(b)
        return new
