"""Site section: shows this Pi on the deployed console (Vercel) with no laptop in between.

Once a second it reads this Pi's status from the uplink section (127.0.0.1:8088), posts the parts the Pi page shows
to SITE/api/edge/bridge, and passes any Crash presses made on the site back to the uplink. Two more threads feed the site's live
camera view: one takes small colour JPEGs of the newest camera frame, 4 a second while someone has that view open,
and the other uploads them to SITE/api/edge/frame as one bundle a second. It only makes outgoing https requests, so
it works behind any Wi-Fi router or phone hotspot, whatever address the Pi gets.

Settings live in ~/hc-site.json, never in the repository:
    {"site": "https://your-site.vercel.app", "token": "optional EDGE_TOKEN", "bypass": "optional Vercel bypass secret"}
Without that file the section waits quietly. scripts/edge_bridge.py runs the same loop from a laptop.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONF = Path(os.environ.get("HC_SITE_CONF", Path.home() / "hc-site.json"))
UPLINK = os.environ.get("HC_UPLINK", "http://127.0.0.1:8088")
KEEP = ("procs", "fps", "frames", "now", "started", "nativeIpc", "modelStats", "crashes", "total", "source")
FPS = float(os.environ.get("HC_FRAME_FPS", "4"))     # camera view pictures a second while someone watches
BUNDLE = 1.0                                        # seconds between uploads
IDLE_EVERY = 5.0                                    # seconds between pictures while nobody watches
GREY = os.environ.get("HC_FRAME_GREY", "0") == "1"    # HC_FRAME_GREY=1 for a grey live view: no colour conversion, smaller JPEGs (models keep colour)
ENHANCE = os.environ.get("HC_FRAME_ENHANCE", "1") != "0"  # auto levels + light sharpening, for the viewer only


def request(url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 5) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None or url.endswith("/crash") else "GET")
    req.add_header("content-type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def bridge_once(pi: str, site: str, headers: dict, seen: dict | None = None) -> list[str]:
    """One round: push the Pi's status, carry back Crash presses. Returns the sections it killed.
    seen, when given, keeps the full status for the picture thread."""
    status = request(f"{pi}/status", timeout=3)
    if seen is not None:
        seen["status"] = status
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


class Picture:
    """The newest camera frame as a small JPEG, 384 by 216."""

    def __init__(self):
        self.frames = None

    def __call__(self) -> tuple[bytes, dict] | None:
        try:
            import livejpeg                              # numpy and libturbojpeg, only on the Pi
            from shm import Frames
            if self.frames is None:
                self.frames = Frames()
            got = livejpeg.snapshot(self.frames, step=6, quality=70, grey=GREY, enhanced=ENHANCE)
        except Exception:                                # no frame ring yet (camera starting) or it was recreated
            self.frames = None
            return None
        if not got or time.time() - got[1]["t"] > 5:
            # the camera section makes a fresh frame file each time it starts, so an old picture means
            # this is still the previous file: open it again next time
            self.frames = None
            return None
        return got


def take_pictures(shots: dict):
    """Picture thread. FPS pictures a second while someone has the camera view open, one every IDLE_EVERY seconds
    otherwise. The upload thread takes them away in bundles."""
    picture, last = Picture(), 0.0
    while True:
        t0 = time.time()
        # checked every tick, so a new viewer gets fast pictures within a second, not after the idle wait
        if t0 - last >= (1 / FPS if shots["watching"] else IDLE_EVERY) and (got := picture()):
            last = t0
            jpg, hd = got
            with shots["lock"]:
                shots["list"] = (shots["list"] + [{"jpeg": base64.b64encode(jpg).decode(), "t": hd["t"]}])[-int(2 * FPS):]
                shots["w"], shots["h"] = hd["w"], hd["h"]
        time.sleep(max(0.0, 1 / FPS - (time.time() - t0)))


def upload_pictures(shots: dict, seen: dict):
    """Upload thread. Sends what the picture thread took as one bundle a second over one kept open https connection,
    so the round trip to the site is paid once a bundle, not once a picture. The page plays a bundle back at the pace
    it was taken, about a second behind live. The site answers with whether someone has the camera view open."""
    conn = None
    while True:
        t0 = time.time()
        with shots["lock"]:
            batch, shots["list"] = shots["list"], []
        if batch:
            try:
                conf = json.loads(CONF.read_text())
                site = urllib.parse.urlsplit(conf["site"])
                if conn is None:
                    make = http.client.HTTPSConnection if site.scheme == "https" else http.client.HTTPConnection
                    conn = make(site.netloc, timeout=8)
                body = {"frames": batch, "w": shots["w"], "h": shots["h"], "source": (seen.get("status") or {}).get("source", "")}
                conn.request("POST", "/api/edge/frame", json.dumps(body), {"content-type": "application/json", **headers_for(conf)})
                shots["watching"] = bool(json.loads(conn.getresponse().read() or b"{}").get("watching"))
            except Exception:                    # network down or the site closed the connection: reconnect next time
                if conn is not None:
                    conn.close()
                conn, shots["watching"] = None, False
        time.sleep(max(0.0, BUNDLE - (time.time() - t0)))


def main():
    last_error = ""
    seen: dict = {}
    shots = {"lock": threading.Lock(), "list": [], "w": 0, "h": 0, "watching": False}
    threading.Thread(target=take_pictures, args=(shots,), daemon=True).start()
    threading.Thread(target=upload_pictures, args=(shots, seen), daemon=True).start()
    while True:
        t0 = time.time()
        try:
            conf = json.loads(CONF.read_text())
            killed = bridge_once(UPLINK, conf["site"].rstrip("/"), headers_for(conf), seen)
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
