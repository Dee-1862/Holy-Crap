"""Bridge the QNX Pi to a deployed console (Vercel) from the laptop the Pi is cabled to.

    python scripts/edge_bridge.py --site https://your-site.vercel.app

Same loop as the Pi's own site section (target/qnx/edge/sitelink.py), for when the Pi has no internet of its own.
    --pi            the Pi's uplink, default the direct cable address
    EDGE_TOKEN      optional shared secret, set the same value on the Vercel project
    VERCEL_BYPASS   the project's "Protection Bypass for Automation" secret, only needed when the site address
                    is behind Vercel Authentication (preview and branch addresses are by default)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "target" / "qnx" / "edge"))
from sitelink import bridge_once, headers_for  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="the deployed console, e.g. https://holy-crap.vercel.app")
    ap.add_argument("--pi", default=os.environ.get("EDGE_URL", "http://169.254.237.143:8088"))
    ap.add_argument("--every", type=float, default=1.0)
    args = ap.parse_args()
    site = args.site.rstrip("/")
    headers = headers_for({"token": os.environ.get("EDGE_TOKEN", ""), "bypass": os.environ.get("VERCEL_BYPASS", "")})
    print(f"bridging {args.pi} to {site}", flush=True)
    while True:
        t0 = time.time()
        try:
            for proc in bridge_once(args.pi, site, headers):
                print(f"crash requested on the site: {proc}", flush=True)
        except Exception as e:
            hint = ""
            if "401" in str(e) and "x-vercel-protection-bypass" not in headers:
                hint = " (the site is behind Vercel Authentication: use the production address, turn protection off, or set VERCEL_BYPASS)"
            print(f"{time.strftime('%H:%M:%S')} {type(e).__name__}: {e}{hint}", flush=True)
        time.sleep(max(0.0, args.every - (time.time() - t0)))


if __name__ == "__main__":
    main()
