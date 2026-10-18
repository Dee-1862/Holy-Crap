"""Cloud section: forwards results and farmer actions to the console (local or deployed on Vercel).

Receives events (name hc/cloud), keeps them in a small file backed list and a sender thread posts them in
batches to CLOUD_URL. If the network is down the events wait on disk and go out when it is back, oldest
dropped past `MAX`. Nothing else on the Pi waits for the network.

    CLOUD_URL   default the laptop console on the direct cable, e.g. https://holy-crap.vercel.app/api/edge/ingest
    EDGE_TOKEN  optional shared secret, sent as the x-edge-token header
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

import qnxipc

CLOUD_URL = os.environ.get("CLOUD_URL", "http://169.254.199.21:3000/api/edge/ingest")
TOKEN = os.environ.get("EDGE_TOKEN", "")
SAVED = Path(os.environ.get("HC_CLOUD_QUEUE", Path.home() / "hc-cloud-queue.jsonl"))
MAX = 500
lock = threading.Lock()
waiting: list[dict] = []
status = {"sent": 0, "failed": 0, "lastOk": 0.0, "lastError": ""}
try:
    waiting = [json.loads(l) for l in SAVED.read_text().splitlines() if l][-MAX:]
except (OSError, ValueError):
    pass


def save() -> None:
    SAVED.write_text("".join(json.dumps(e) + "\n" for e in waiting))


def on_event(msg: bytes) -> bytes:
    e = json.loads(msg)
    with lock:
        waiting.append(e)
        del waiting[:-MAX]
        save()
    return json.dumps({"waiting": len(waiting), **status}).encode()


def sender() -> None:
    delay = 2.0
    while True:
        time.sleep(delay)
        with lock:
            batch = waiting[:50]
        if not batch:
            continue
        body = json.dumps({"device": "qnxpi-win", "sentAt": time.time(), "events": batch}).encode()
        req = urllib.request.Request(CLOUD_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "x-edge-token": TOKEN})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                r.read()
            with lock:
                del waiting[:len(batch)]
                save()
            status.update(sent=status["sent"] + len(batch), lastOk=time.time())
            delay = 2.0
        except OSError as e:
            status.update(failed=status["failed"] + 1, lastError=e.__class__.__name__)
            delay = min(60.0, delay * 2)                 # back off while the network is down


def main():
    threading.Thread(target=sender, daemon=True, name="cloud-sender").start()
    qnxipc.Server("hc/cloud").serve(on_event)


if __name__ == "__main__":
    main()
