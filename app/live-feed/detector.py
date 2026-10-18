"""Run the Holy-Crap dropping detector on video frames, whole frame or in tiles.

The detector was trained on close-up phone photos, where one dropping fills about a tenth of the picture.
In a whole-pen camera a dropping is a few pixels, so whole-frame inference sees almost nothing. Tiling zooms
into sections of the frame so a dropping looks closer to what the model was trained on. Both modes are here
so they can be compared on the same frames.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
MODEL = REPO / "models" / "dropping4-laptop" / "dropping4_yolo11n_640.onnx"
CLASSES = ["cocci", "healthy", "ncd", "salmo"]          # model output order
ABNORMAL = {"cocci", "ncd", "salmo"}
SIDE = 640


def load_session(model: Path = MODEL):
    """Uses the GPU when onnxruntime-gpu can find CUDA, otherwise the CPU, like the Pi."""
    try:
        import torch  # noqa: F401  loads the CUDA libraries onnxruntime-gpu looks for
    except ImportError:
        pass
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider") if p in ort.get_available_providers()]
    return ort.InferenceSession(str(model), sess_options=opts, providers=providers)


def _letterbox(bgr: np.ndarray):
    h, w = bgr.shape[:2]
    s = min(SIDE / w, SIDE / h)
    nw, nh = round(w * s), round(h * s)
    canvas = np.full((SIDE, SIDE, 3), 114, np.uint8)
    px, py = (SIDE - nw) // 2, (SIDE - nh) // 2
    canvas[py:py + nh, px:px + nw] = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x = canvas[:, :, ::-1].astype(np.float32).transpose(2, 0, 1)[None] / 255.0
    return x, s, px, py


def _run(sess, bgr: np.ndarray, conf: float):
    """One model call. Returns boxes in the coordinates of `bgr` as rows x1, y1, x2, y2, class id, score,
    then the four class scores in CLASSES order (kept for explainability)."""
    x, s, px, py = _letterbox(bgr)
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0][0].T          # (candidates, 8)
    scores = out[:, 4:8]
    cls = scores.argmax(1)
    best = scores.max(1)
    keep = best >= conf
    if not keep.any():
        return np.zeros((0, 10), np.float32)
    cx, cy, w, h = out[keep, 0], out[keep, 1], out[keep, 2], out[keep, 3]
    x1, y1 = (cx - w / 2 - px) / s, (cy - h / 2 - py) / s
    x2, y2 = (cx + w / 2 - px) / s, (cy + h / 2 - py) / s
    return np.concatenate([np.stack([x1, y1, x2, y2, cls[keep], best[keep]], 1), scores[keep]], 1).astype(np.float32)


def _nms(boxes: np.ndarray, iou: float = 0.5) -> np.ndarray:
    if not len(boxes):
        return boxes
    xywh = [[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxes]
    idx = cv2.dnn.NMSBoxes(xywh, boxes[:, 5].tolist(), 0.0, iou)
    return boxes[np.array(idx).reshape(-1)] if len(idx) else boxes[:0]


def detect(sess, bgr: np.ndarray, conf: float = 0.25, tile: int | None = None, overlap: float = 0.25) -> np.ndarray:
    """Whole frame when tile is None. Otherwise square tiles of `tile` source pixels, merged with NMS."""
    if tile is None:
        return _nms(_run(sess, bgr, conf))
    h, w = bgr.shape[:2]
    step = max(1, int(tile * (1 - overlap)))
    found = []
    for y in range(0, max(1, h - tile) + step, step):
        for x in range(0, max(1, w - tile) + step, step):
            x0, y0 = min(x, max(0, w - tile)), min(y, max(0, h - tile))
            crop = bgr[y0:y0 + tile, x0:x0 + tile]
            b = _run(sess, crop, conf)
            if len(b):
                b[:, [0, 2]] += x0
                b[:, [1, 3]] += y0
                found.append(b)
    return _nms(np.concatenate(found)) if found else np.zeros((0, 10), np.float32)
