"""Spot finder section: receives small grey frames by message passing, flags new still spots.

Frame events go to the uplink for the dashboard. New spots also go to the model section with the shared
memory slot of the full frame, so the model cuts its own full resolution patch. Each send is answered
or fails at once, so a slow or crashed model never holds up the camera.

It keeps its floor background in memory. After a restart it rebuilds it from the next 15 frames.
"""
from __future__ import annotations

import base64
import json
import os
import time

import qnxipc
from stillspot import StillSpots


class Link:
    """A client that reconnects on the next message after its server was restarted."""

    def __init__(self, name: str):
        self.name, self.c = name, None

    def send(self, event: dict) -> bool:
        try:
            if self.c is None:
                self.c = qnxipc.Client(self.name, wait=0)
            self.c.send(json.dumps(event).encode())
            return True
        except OSError:
            self.c = None
            return False


def main():
    state = {"det": None, "frames": 0, "spots": 0}
    uplink, model = Link("hc/uplink"), Link("hc/model")

    def handle(msg: bytes) -> bytes:
        n = int.from_bytes(msg[:2], "little")
        head = json.loads(msg[2:2 + n])
        frame = msg[2 + n:]
        w, h = head["w"], head["h"]
        if state["det"] is None:
            # camera overlay text, as x0,y0,x1,y1 shares; the default fits the PIO and NESTLER cameras' date and label
            boxes = os.environ.get("HC_IGNORE", "0,0,0.45,0.12;0.68,0.68,0.88,0.82")
            state["det"] = StillSpots(w, h, ignore_boxes=tuple(tuple(map(float, b.split(","))) for b in boxes.split(";") if b))
        t0 = time.perf_counter()
        new = state["det"].update(frame)
        ms = (time.perf_counter() - t0) * 1000
        state["frames"] += 1
        for s in new:
            state["spots"] += 1
            s["id"] = f"P{int(head['t']) % 100000:05d}{state['spots'] % 100:02d}"
            s["crop"] = base64.b64encode(state["det"].crop(frame, s)).decode()
            s["t"] = head["t"]
        if new and "slot" in head:
            model.send({"kind": "candidates", "slot": head["slot"], "seq": head["seq"], "t": head["t"],
                        "spots": [{k: s[k] for k in ("id", "cx", "cy", "w", "h", "area")} for s in new], "small": [w, h]})
        uplink.send({"kind": "frame", "k": head["k"], "t": head["t"], "ms": round(ms, 1), "dropped": head["dropped"],
                     "w": w, "h": h, "thumb": base64.b64encode(frame).decode() if state["frames"] % 2 else None,
                     "spots": new, "warm": state["frames"] > 15, "source": head.get("source", "replay"),
                     "full": [head.get("fullW"), head.get("fullH")]})
        return json.dumps({"spots": len(new)}).encode()

    qnxipc.Server("hc/spotter").serve(handle)


if __name__ == "__main__":
    main()
