"""Runs the trained dropping detector for the Pi's model section, until a QNX inference runtime is ported.

    python target/qnx/edge/laptop/infer_server.py            listens on port 8770

The Pi sends a full resolution RGB patch cut around a candidate spot:
    POST /infer?w=128&h=128     body: raw RGB bytes
and gets back the detector's boxes on that patch and its best score for each class. The patch is enlarged
to the model's 640 input, so a dropping of 10 to 30 pixels looks closer to the close-up photos it learned on.
"""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "app" / "live-feed"))
import detector as D  # noqa: E402

MODEL = Path(os.environ.get("HC_MODEL", D.MODEL))
sess = D.load_session(MODEL)
CONF = 0.15


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            w, h = int(q["w"][0]), int(q["h"][0])
            body = self.rfile.read(int(self.headers["Content-Length"]))
            rgb = np.frombuffer(body, np.uint8).reshape(h, w, 3)
        except (KeyError, ValueError):
            return self._send(400, {"error": "need w, h and w*h*3 bytes of RGB"})
        t0 = time.perf_counter()
        boxes = D.detect(sess, np.ascontiguousarray(rgb[:, :, ::-1]), conf=CONF)
        best = {c: 0.0 for c in D.CLASSES}
        out = []
        for x1, y1, x2, y2, c, s in boxes:
            name = D.CLASSES[int(c)]
            best[name] = max(best[name], round(float(s), 3))
            out.append({"box": [round(float(x1) / w, 3), round(float(y1) / h, 3), round(float(x2) / w, 3), round(float(y2) / h, 3)],
                        "cls": name, "score": round(float(s), 3)})
        out.sort(key=lambda b: -b["score"])
        self._send(200, {"model": MODEL.name, "boxes": out[:5], "best": best, "ms": round((time.perf_counter() - t0) * 1000, 1)})

    def do_GET(self):
        self._send(200, {"model": MODEL.name, "classes": D.CLASSES})

    def _send(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("HC_INFER_PORT", "8770"))
    print(f"dropping detector {MODEL.name} on port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
