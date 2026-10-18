"""Inference section: runs the dropping detector on the Pi itself, so nothing depends on the laptop.

Same HTTP API as laptop/infer_server.py, on 127.0.0.1:8770:
    POST /infer?w=128&h=128     body: raw RGB bytes of the patch the model section cut out
    ->   {"model", "boxes": [{"box", "cls", "score"}], "best": {class: score}, "ms"}
ONNX Runtime 1.24.4 comes from QNX's open source packages (oss.qnx.com, 8.0.5 extra). Its Python module is
broken there, so this goes through ortlite (a small C bridge). Resizing and box filtering use numpy only.
It runs in its own supervised user process, providing a fault-containment boundary from the camera and watch processes.

The model input side comes from HC_MODEL_SIDE (default 640, e.g. 320 for the pinned QNX model) and is
reported in the GET/POST metadata so a deployment probe can verify the model shape the server is using.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "ortlite"))
from ortlite import Session  # noqa: E402

MODEL = Path(os.environ.get("HC_MODEL", HERE / "dropping4_yolo11n_640.onnx"))
CLASSES = ["cocci", "healthy", "ncd", "salmo"]
CONF = 0.15

# One rule for every accepted side: 32 through 4096 and a multiple of 32 (YOLO-safe strides).
MIN_SIDE, MAX_SIDE, STRIDE, DEFAULT_SIDE = 32, 4096, 32, 640


def model_side(env: Mapping[str, str] | None = None) -> int:
    """Configured model input side from HC_MODEL_SIDE, default 640.

    Validated eagerly at import so a bad deployment fails before serving:
    32 through 4096 and divisible by 32.
    """
    raw = (os.environ if env is None else env).get("HC_MODEL_SIDE")
    if raw is None:
        return DEFAULT_SIDE
    try:
        side = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"HC_MODEL_SIDE must be an integer input side, got {raw!r}") from None
    if side < MIN_SIDE or side > MAX_SIDE or side % STRIDE:
        raise ValueError(
            f"HC_MODEL_SIDE must be {MIN_SIDE}..{MAX_SIDE} and a multiple of {STRIDE}, got {raw!r}"
        )
    return side


SIDE = model_side()


def letterbox(rgb: np.ndarray):
    """Bilinear resize into the configured square with grey padding, as the detector was trained. Returns input, scale, pads."""
    h, w = rgb.shape[:2]
    s = min(SIDE / w, SIDE / h)
    nw, nh = round(w * s), round(h * s)
    ys = (np.arange(nh) + 0.5) / s - 0.5
    xs = (np.arange(nw) + 0.5) / s - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 1); y1 = np.clip(y0 + 1, 0, h - 1); fy = np.clip(ys - y0, 0, 1)[:, None, None]
    x0 = np.clip(np.floor(xs).astype(int), 0, w - 1); x1 = np.clip(x0 + 1, 0, w - 1); fx = np.clip(xs - x0, 0, 1)[None, :, None]
    img = rgb.astype(np.float32)
    top = img[y0][:, x0] * (1 - fx) + img[y0][:, x1] * fx
    bottom = img[y1][:, x0] * (1 - fx) + img[y1][:, x1] * fx
    resized = top * (1 - fy) + bottom * fy
    canvas = np.full((SIDE, SIDE, 3), 114, np.float32)
    px, py = (SIDE - nw) // 2, (SIDE - nh) // 2
    canvas[py:py + nh, px:px + nw] = resized
    return (canvas / 255.0).transpose(2, 0, 1)[None], s, px, py


def nms(b: np.ndarray, iou: float = 0.5) -> np.ndarray:
    order = np.argsort(-b[:, 5])
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        rest = order[1:]
        xx1 = np.maximum(b[i, 0], b[rest, 0]); yy1 = np.maximum(b[i, 1], b[rest, 1])
        xx2 = np.minimum(b[i, 2], b[rest, 2]); yy2 = np.minimum(b[i, 3], b[rest, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        area = lambda k: (b[k, 2] - b[k, 0]) * (b[k, 3] - b[k, 1])
        order = rest[inter / (area(i) + area(rest) - inter + 1e-9) < iou]
    return b[keep]


def detect(sess: Session, rgb: np.ndarray) -> np.ndarray:
    """Boxes [x1, y1, x2, y2, class id, score] in patch pixels, same decoding as app/live-feed/detector.py."""
    x, s, px, py = letterbox(rgb)
    out = sess.run(x)[0].T                                   # (candidates, 8): cx, cy, w, h, four class scores
    scores = out[:, 4:8]
    cls, best = scores.argmax(1), scores.max(1)
    keep = best >= CONF
    if not keep.any():
        return np.zeros((0, 6), np.float32)
    cx, cy, w, h = out[keep, 0], out[keep, 1], out[keep, 2], out[keep, 3]
    b = np.stack([(cx - w / 2 - px) / s, (cy - h / 2 - py) / s, (cx + w / 2 - px) / s, (cy + h / 2 - py) / s, cls[keep], best[keep]], 1)
    return nms(b)


def model_info() -> dict:
    """GET metadata; side lets a deployment probe verify which model shape the server is using."""
    return {"model": MODEL.name, "on": "pi", "side": SIDE, "classes": CLASSES}


def main():
    # ONNX Runtime prints its whole operator registry once on load, keep that out of the log
    devnull, saved = os.open(os.devnull, os.O_WRONLY), os.dup(2)
    os.dup2(devnull, 2)
    try:
        sess = Session(str(MODEL), threads=int(os.environ.get("HC_THREADS", "2")))
    finally:
        os.dup2(saved, 2)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            q = parse_qs(urlparse(self.path).query)
            try:
                w, h = int(q["w"][0]), int(q["h"][0])
                rgb = np.frombuffer(self.rfile.read(int(self.headers["Content-Length"])), np.uint8).reshape(h, w, 3)
            except (KeyError, ValueError):
                return self._send(400, {"error": "need w, h and w*h*3 bytes of RGB"})
            t0 = time.perf_counter()
            boxes = detect(sess, rgb)
            best = {c: 0.0 for c in CLASSES}
            out = []
            for x1, y1, x2, y2, c, sc in boxes:
                name = CLASSES[int(c)]
                best[name] = max(best[name], round(float(sc), 3))
                out.append({"box": [round(float(x1) / w, 3), round(float(y1) / h, 3), round(float(x2) / w, 3), round(float(y2) / h, 3)],
                            "cls": name, "score": round(float(sc), 3)})
            out.sort(key=lambda b: -b["score"])
            self._send(200, {"model": MODEL.name, "on": "pi", "side": SIDE, "boxes": out[:5], "best": best, "ms": round((time.perf_counter() - t0) * 1000, 1)})

        def do_GET(self):
            self._send(200, model_info())

        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    port = int(os.environ.get("HC_INFER_PORT", "8770"))
    print(f"inference on the Pi: {MODEL.name} on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
