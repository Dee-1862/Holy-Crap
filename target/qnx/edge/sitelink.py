"""Site section: shows this Pi on the deployed console (Vercel) with no laptop in between.

Once a second it reads this Pi's status from the uplink section (127.0.0.1:8088), posts the parts the Pi page shows
to SITE/api/edge/bridge, and passes any Crash presses made on the site back to the uplink. It only makes outgoing
https requests, so it works behind any Wi-Fi router or phone hotspot, whatever address the Pi gets.

Settings live in ~/hc-site.json, never in the repository:
    {"site": "https://your-site.vercel.app", "token": "optional EDGE_TOKEN", "bypass": "optional Vercel bypass secret"}
Without that file the section waits quietly. scripts/edge_bridge.py runs the same loop from a laptop.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

CONF = Path(os.environ.get("HC_SITE_CONF", Path.home() / "hc-site.json"))
UPLINK = os.environ.get("HC_UPLINK", "http://127.0.0.1:8088")
KEEP = ("procs", "fps", "frames", "now", "started", "nativeIpc", "modelStats", "crashes", "total", "source")


def request(url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 5) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None or url.endswith("/crash") else "GET")
    req.add_header("content-type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def bridge_once(pi: str, site: str, headers: dict) -> list[str]:
    """One round: push the Pi's status, carry back Crash presses. Returns the sections it killed."""
    status = request(f"{pi}/status", timeout=3)
    reply = request(f"{site}/api/edge/bridge", {"status": {k: status[k] for k in KEEP if k in status}}, headers, timeout=8)
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


def main():
    last_error = ""
    while True:
        t0 = time.time()
        try:
            conf = json.loads(CONF.read_text())
            killed = bridge_once(UPLINK, conf["site"].rstrip("/"), headers_for(conf))
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
