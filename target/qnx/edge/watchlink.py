"""Stopwatch section: serves the M5 StopWatch straight from the Pi, so alerts reach the farmer without the cloud.

Receives explained results (name hc/watch) and answers the same API the console gives the watch, on port 8089:
    GET  /api/watch                      specs that passed the explain section's checks, with reasons and scores
    POST /api/specimens/ID/check|normal  the farmer's buttons, kept here and passed to the cloud section
    POST /api/pens/ID/vet                a vet request, same
Point the watch at it by setting the console address in app/watch/console/secrets.h to http://PI:8089.
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import qnxipc
from spotter import Link

PEN = "A1"                         # the pen this Pi's camera watches, as on the dashboard floor plan
KEYS = ["healthy", "coccidiosis", "salmonella", "ncd"]
BEST = {"healthy": "healthy", "coccidiosis": "cocci", "salmonella": "salmo", "ncd": "ncd"}
lock = threading.Lock()
specs: list[dict] = []
states: dict[str, int] = {}
vet: dict | None = None
cloud = Link("hc/cloud")


def to_watch(r: dict) -> dict:
    best = r.get("best") or {}
    total = sum(best.values()) or 1
    k = r["cls"] or "healthy"
    grade = 8 if k == "healthy" else max(2, min(6, 10 - round(r["score"] * 7)))
    sub = r["sub"]
    return {"id": r["id"], "pen": PEN, "k": k, "grade": grade, "conf": round(r["score"] * 100),
            "mins": max(0, round((time.time() - r["t"]) / 60)), "st": states.get(r["id"], 0),
            "p": [round(best.get(BEST[x], 0) / total * 100) for x in KEYS],
            "sub": [sub["color"], 5, sub["urates"], sub["blood"], 5],      # consistency and foam are not measured
            "rg": [round(r["cx"] * 100), round(r["cy"] * 100)], "why": [w[:71] for w in r["why"][:3]]}


def on_result(msg: bytes) -> bytes:
    r = json.loads(msg)
    if r.get("verdict") in ("alert", "normal"):
        with lock:
            specs.insert(0, r)
            del specs[24:]
    return b"ok"


class Http(BaseHTTPRequestHandler):
    def _send(self, body: dict, code: int = 200):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] != "/api/watch":
            return self._send({"error": "not found"}, 404)
        with lock:
            out = [to_watch(r) for r in specs]
            v = {"pen": vet["pen"], "ago": round((time.time() - vet["t"]) / 60)} if vet else None
        self._send({"pens": [], "specs": out, "vet": v, "source": "pi"})

    def do_POST(self):
        global vet
        p = self.path.strip("/").split("/")
        if len(p) == 4 and p[:2] == ["api", "specimens"] and p[3] in ("check", "normal"):
            with lock:
                states[p[2]] = 1 if p[3] == "check" else 2
            cloud.send({"kind": "action", "id": p[2], "action": p[3], "t": time.time()})
            return self._send({"ok": True, "id": p[2], "state": p[3]})
        if len(p) == 4 and p[:2] == ["api", "pens"] and p[3] == "vet":
            with lock:
                dup = vet is not None and vet["pen"] == p[2] and time.time() - vet["t"] < 60
                if not dup:
                    vet = {"pen": p[2], "t": time.time()}
            if not dup:
                cloud.send({"kind": "vet", "pen": p[2], "t": time.time()})
            return self._send({"duplicate": dup, "call": {"pen": p[2], "delivered": "logged"}})
        self._send({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


def main():
    threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", 8089), Http).serve_forever, daemon=True).start()
    qnxipc.Server("hc/watch").serve(on_result)


if __name__ == "__main__":
    main()
