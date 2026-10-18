"""Spot finder process: receives frames by message passing, flags new still spots, tells the uplink.

It keeps its floor background in memory. After a restart it rebuilds it from the next 15 frames, so a
crash costs a few seconds of warm up and nothing else.
"""
from __future__ import annotations

import base64
import json
import time

import qnxipc
from stillspot import StillSpots


def main():
    state = {"det": None, "uplink": None, "frames": 0}

    def tell(event: dict) -> None:
        try:
            if state["uplink"] is None:
                state["uplink"] = qnxipc.Client("hc/uplink", wait=0)
            state["uplink"].send(json.dumps(event).encode())
        except OSError:
            state["uplink"] = None                     # uplink is down, the event is lost, keep going

    def handle(msg: bytes) -> bytes:
        n = int.from_bytes(msg[:2], "little")
        head = json.loads(msg[2:2 + n])
        frame = msg[2 + n:]
        w, h = head["w"], head["h"]
        if state["det"] is None:
            state["det"] = StillSpots(w, h)
        t0 = time.perf_counter()
        new = state["det"].update(frame)
        ms = (time.perf_counter() - t0) * 1000
        state["frames"] += 1
        for s in new:
            s["crop"] = base64.b64encode(state["det"].crop(frame, s)).decode()
            s["t"] = head["t"]
        thumb = None
        if state["frames"] % 2 == 1:                   # every other frame goes to the dashboard as a picture
            thumb = base64.b64encode(frame).decode()
        tell({"kind": "frame", "k": head["k"], "t": head["t"], "ms": round(ms, 1), "dropped": head["dropped"],
              "w": w, "h": h, "thumb": thumb, "spots": new, "warm": state["frames"] > 15})
        return json.dumps({"spots": len(new)}).encode()

    qnxipc.Server("hc/spotter").serve(handle)


if __name__ == "__main__":
    main()
