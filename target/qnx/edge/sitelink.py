"""Site section: shows this Pi on the deployed console (Vercel) with no laptop in between.

Once a second it reads this Pi's status from the uplink section (127.0.0.1:8088), posts the parts the Pi page shows
to SITE/api/edge/bridge, and passes any Crash presses made on the site back to the uplink. Every FRAME_EVERY seconds
it also sends a small colour JPEG of the newest camera frame and where recent spots were, for the site's live camera
view. It only makes outgoing https requests, so it works behind any Wi-Fi router or phone hotspot, whatever address
the Pi gets.

Settings live in ~/hc-site.json, never in the repository:
    {"site": "https://your-site.vercel.app", "token": "optional EDGE_TOKEN", "bypass": "optional Vercel bypass secret"}
Without that file the section waits quietly. scripts/edge_bridge.py runs the same loop from a laptop.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.request
from pathlib import Path

CONF = Path(os.environ.get("HC_SITE_CONF", Path.home() / "hc-site.json"))
UPLINK = os.environ.get("HC_UPLINK", "http://127.0.0.1:8088")
KEEP = ("procs", "fps", "frames", "now", "started", "nativeIpc", "modelStats", "crashes", "total", "source")
FRAME_EVERY = float(os.environ.get("HC_FRAME_EVERY", "2"))


def request(url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 5) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None or url.endswith("/crash") else "GET")
    req.add_header("content-type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def bridge_once(pi: str, site: str, headers: dict, frame=None) -> list[str]:
    """One round: push the Pi's status, carry back Crash presses. Returns the sections it killed.
    frame, when given, is called with the status and returns the live camera picture to send along, or None."""
    status = request(f"{pi}/status", timeout=3)
    out = {k: status[k] for k in KEEP if k in status}
    if frame and (pic := frame(status)):
        out["frame"] = pic
    reply = request(f"{site}/api/edge/bridge", {"status": out}, headers, timeout=8)
    killed = []
    for cmd in reply.get("commands", []):
        proc = cmd.get("proc", "")
        try:
            request(f"{pi}/crash?proc={proc}", {}, timeout=3)
        except Exception:                       # killing the uplink itself gives no answer, that is fine
            pass
        killed.append(proc)
    return killed


def headers_for(conf: dict) -> dict:
    h = {}
    if conf.get("token"):
        h["x-edge-token"] = conf["token"]
    if conf.get("bypass"):
        h["x-vercel-protection-bypass"] = conf["bypass"]
    return h


class Picture:
    """The newest camera frame as a small JPEG, at most every FRAME_EVERY seconds, with the latest spots."""

    def __init__(self):
        self.last, self.frames = 0.0, None

    def __call__(self, status: dict) -> dict | None:
        if time.time() - self.last < FRAME_EVERY:
            return None
        self.last = time.time()
        try:
            import livejpeg                              # numpy and libturbojpeg, only on the Pi
            from shm import Frames
            if self.frames is None:
                self.frames = Frames()
            got = livejpeg.snapshot(self.frames)
        except Exception:                                # no frame ring yet (camera starting) or it was recreated
            self.frames = None
            return None
        if not got or time.time() - got[1]["t"] > 5:
            # the camera section makes a fresh frame file each time it starts, so an old picture means
            # this is still the previous file: open it again next time
            self.frames = None
            return None
        jpg, hd = got
        since = status.get("procs", {}).get("camera", {}).get("started") or 0     # not spots kept from older runs
        spots = [{k: s.get(k) for k in ("id", "cx", "cy", "t")} for s in status.get("spots", []) if (s.get("t") or 0) >= since][-12:]
        return {"jpeg": base64.b64encode(jpg).decode(), "t": hd["t"], "w": hd["w"], "h": hd["h"],
                "source": status.get("source", ""), "spots": spots}


def main():
    last_error = ""
    picture = Picture()
    while True:
        t0 = time.time()
        try:
            conf = json.loads(CONF.read_text())
            killed = bridge_once(UPLINK, conf["site"].rstrip("/"), headers_for(conf), picture)
            for proc in killed:
                print(f"crash requested on the site: {proc}", flush=True)
            last_error = ""
        except FileNotFoundError:
            time.sleep(10)                       # not set up on this Pi yet
            continue
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if msg != last_error:                # say it once, not every second while the network is down
                print(f"site link: {msg}", flush=True)
                last_error = msg
        time.sleep(max(0.0, 1.0 - (time.time() - t0)))


if __name__ == "__main__":
    main()
