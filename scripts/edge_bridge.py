"""Bridge the QNX Pi to a deployed console (Vercel), run on the laptop the Pi is cabled to.

    python scripts/edge_bridge.py --site https://your-site.vercel.app

Once a second it reads the Pi's status (target/qnx/edge/uplink.py), posts the parts the Pi page shows to
SITE/api/edge/bridge, and passes any Crash presses made on the site back to the Pi. Standard library only.
    --pi      the Pi's uplink, default the direct cable address
    EDGE_TOKEN  optional shared secret, set the same value on the Vercel project
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

KEEP = ("procs", "fps", "frames", "now", "started", "nativeIpc", "modelStats", "crashes", "total", "source")


def request(url: str, body: dict | None = None, token: str = "", timeout: float = 5) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None or url.endswith("/crash") else "GET")
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("x-edge-token", token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="the deployed console, e.g. https://holy-crap.vercel.app")
    ap.add_argument("--pi", default=os.environ.get("EDGE_URL", "http://169.254.237.143:8088"))
    ap.add_argument("--every", type=float, default=1.0)
    args = ap.parse_args()
    site, token = args.site.rstrip("/"), os.environ.get("EDGE_TOKEN", "")
    print(f"bridging {args.pi} to {site}", flush=True)
    while True:
        t0 = time.time()
        try:
            status = request(f"{args.pi}/status", timeout=3)
            slim = {k: status[k] for k in KEEP if k in status}
            reply = request(f"{site}/api/edge/bridge", {"status": slim}, token, timeout=8)
            for cmd in reply.get("commands", []):
                proc = cmd.get("proc", "")
                print(f"crash requested on the site: {proc}", flush=True)
                try:
                    request(f"{args.pi}/crash?proc={proc}", {}, timeout=3)
                except Exception as e:                  # the uplink killing itself gives no answer, that is fine
                    print(f"  {proc}: {e}", flush=True)
        except Exception as e:
            print(f"{time.strftime('%H:%M:%S')} {type(e).__name__}: {e}", flush=True)
        time.sleep(max(0.0, args.every - (time.time() - t0)))


if __name__ == "__main__":
    main()
