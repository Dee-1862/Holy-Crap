"""Model section: cuts a full resolution patch around each candidate spot and gets the detector's verdict.

Receives candidates from the spot finder (name hc/model) with the shared memory slot of the full frame.
The patch is cut out straight away, before the camera reuses that slot, and the reply goes back at once.
The verdict is fetched by a small pool of threads, so a slow model never blocks the spot finder. At most
`--pending` patches wait at a time. A newer one replaces the oldest instead of building a queue.

Until a QNX inference runtime is ported, the detector runs on the laptop (laptop/infer_server.py) and
INFER_URL points at it. Without it, every patch goes on as "not checked", with its appearance still measured.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import qnxipc
from shm import Frames
from spotter import Link

INFER_URL = os.environ.get("INFER_URL", "http://169.254.199.21:8770")
PATCH = 128                       # full resolution pixels, about 10 percent of a 1280 wide frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--pending", type=int, default=6)
    args = ap.parse_args()
    explain = Link("hc/explain")
    pool = ThreadPoolExecutor(args.threads, thread_name_prefix="model")
    busy = threading.Semaphore(args.pending)
    stats = {"patches": 0, "stale": 0, "skipped": 0, "checked": 0, "unreachable": 0}
    frames = {"f": None}

    def verdict(spot: dict, rgb: bytes, side: int, t: float) -> None:
        try:
            try:
                req = urllib.request.Request(f"{INFER_URL}/infer?w={side}&h={side}", data=rgb, method="POST")
                with urllib.request.urlopen(req, timeout=4) as r:
                    model = json.loads(r.read())
                stats["checked"] += 1
            except OSError as e:
                model = {"error": f"model not reachable: {e.__class__.__name__}"}
                stats["unreachable"] += 1
            explain.send({"kind": "patch", "spot": spot, "t": t, "side": side, "rgb": base64.b64encode(rgb).decode(),
                          "model": model, "stats": stats})
        finally:
            busy.release()

    def handle(msg: bytes) -> bytes:
        e = json.loads(msg)
        if frames["f"] is None:
            frames["f"] = Frames()
        for spot in e["spots"][:4]:
            cut = frames["f"].crop_rgb(e["slot"], spot["cx"], spot["cy"], PATCH)
            if cut is None:
                stats["stale"] += 1                    # the camera already reused that slot
                continue
            if not busy.acquire(blocking=False):
                stats["skipped"] += 1                  # model busy, skip instead of queueing
                continue
            stats["patches"] += 1
            pool.submit(verdict, spot, cut[0], cut[1], e["t"])
        return b"ok"

    qnxipc.Server("hc/model").serve(handle)


if __name__ == "__main__":
    main()
