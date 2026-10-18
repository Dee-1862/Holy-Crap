"""Rishit's behaviour-v1 models on video frames: find each bird, then say what it is doing.

Chicken detector (1 class) and a 7 class behaviour classifier, both trained on Big Broiler (white broilers in small
research pens, AGPL-3.0). They hold up on the PIO broiler house, which looks similar, and not on the NESTLER pens of
brown and black layers, where the detector boxes the white drinkers instead. So they run only on BIRD_CLIPS.
See models/behaviour-v1/README.md for the test numbers.
"""
from __future__ import annotations

import cv2
import numpy as np

import detector as D

DIR = D.REPO / "models" / "behaviour-v1"
BEHAVIOURS = ["drinking", "eating", "inactive", "moving", "other", "panting", "preening"]
BIRD_CLIPS = {"pio-0002", "test-a1", "bb-093", "bb-101"}   # white broilers, close to what the models were trained on
CONF = 0.1                                       # the README says the detector's scores run low, start near 0.05 to 0.1


def load():
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    mk = lambda f: ort.InferenceSession(str(DIR / f), sess_options=opts, providers=["CPUExecutionProvider"])
    return mk("chicken_yolo11n_640.onnx"), mk("behaviour7_yolo11s-cls_224.onnx")


def _birds_in(det, img: np.ndarray) -> np.ndarray:
    x, s, px, py = D._letterbox(img)
    o = det.run(None, {det.get_inputs()[0].name: x})[0][0].T          # (N, 5): cx, cy, w, h, score
    o = o[o[:, 4] >= CONF]
    return np.stack([(o[:, 0] - o[:, 2] / 2 - px) / s, (o[:, 1] - o[:, 3] / 2 - py) / s,
                     (o[:, 0] + o[:, 2] / 2 - px) / s, (o[:, 1] + o[:, 3] / 2 - py) / s, o[:, 4]], 1) if len(o) else np.zeros((0, 5))


def birds(det, frame: np.ndarray) -> np.ndarray:
    """Bird boxes [x1, y1, x2, y2, score] in frame pixels. The whole frame finds big birds near the camera,
    overlapping 640 squares find small ones far away."""
    h, w = frame.shape[:2]
    found = [_birds_in(det, frame)]
    for y in sorted({0, max(0, h - 640)}):
        for x in sorted({0, max(0, w - 640)}):
            b = _birds_in(det, frame[y:y + 640, x:x + 640])
            b[:, [0, 2]] += x
            b[:, [1, 3]] += y
            found.append(b)
    b = np.concatenate(found)
    if not len(b):
        return b
    keep = cv2.dnn.NMSBoxes([[float(r[0]), float(r[1]), float(r[2] - r[0]), float(r[3] - r[1])] for r in b], b[:, 4].tolist(), CONF, 0.5)
    return b[np.array(keep).reshape(-1)]


def behaviour(cls, frame: np.ndarray, boxes: np.ndarray, limit: int = 60, seed: int = 0) -> list[int]:
    """Behaviour class id for up to `limit` birds (a random sample when there are more)."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(boxes))[:limit]
    h, w = frame.shape[:2]
    out = []
    for i in idx:
        x1, y1, x2, y2 = boxes[i, :4]
        side = max(x2 - x1, y2 - y1) * 1.15                             # square crop, box plus 15 percent
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        X1, Y1 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        crop = frame[Y1:int(min(h, cy + side / 2)), X1:int(min(w, cx + side / 2))]
        if crop.size == 0:
            continue
        x = cv2.resize(crop, (224, 224))[:, :, ::-1].astype(np.float32).transpose(2, 0, 1)[None] / 255
        out.append(int(np.argmax(cls.run(None, {cls.get_inputs()[0].name: x})[0][0])))
    return out


def on_bird(box, birds_: np.ndarray, shrink: float = 0.15) -> bool:
    """True when the centre of a dropping box sits inside a bird box (trimmed so a dropping beside a bird survives)."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for x1, y1, x2, y2, _ in birds_:
        dx, dy = (x2 - x1) * shrink, (y2 - y1) * shrink
        if x1 + dx <= cx <= x2 - dx and y1 + dy <= cy <= y2 - dy:
            return True
    return False
