"""Uplink process: collects events from the other processes and serves them to the dashboard.

Receives by message passing (name hc/uplink) and serves HTTP on port 8088:
    GET  /status            processes, frame rate, latest picture, flagged spots (JSON)
    POST /crash?proc=NAME   kill that process with SIGKILL, for the restart demo
Spots are saved to disk as they come, so they survive this process being restarted.
"""
from __future__ import annotations

import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qnxipc

SAVED = Path(os.environ.get("HC_STATE", Path.home() / "hc-edge-state.json"))
lock = threading.Lock()
status = {"procs": {}, "frames": 0, "fps": 0.0, "ms": 0.0, "dropped": 0, "thumb": None, "w": 0, "h": 0,
          "warm": False, "lastFrame": 0.0, "spots": [], "total": 0, "crashes": [], "started": time.time()}
try:
    saved = json.loads(SAVED.read_text())
    status["spots"], status["total"] = saved["spots"][-200:], saved["total"]
except (OSError, ValueError, KeyError, TypeError):
    pass
recent: list[float] = []


def on_event(msg: bytes) -> bytes:
    e = json.loads(msg)
    with lock:
        if e["kind"] == "frame":
            now = time.time()
            recent.append(now)
            del recent[:-20]
            status.update(frames=status["frames"] + 1, ms=e["ms"], dropped=e["dropped"], warm=e["warm"], lastFrame=now,
                          fps=round((len(recent) - 1) / (recent[-1] - recent[0]), 2) if len(recent) > 1 else 0.0)
            if e["thumb"]:
                status.update(thumb=e["thumb"], w=e["w"], h=e["h"])
            if e["spots"]:
                status["spots"] = (status["spots"] + e["spots"])[-200:]
                status["total"] += len(e["spots"])
                SAVED.write_text(json.dumps({"spots": status["spots"], "total": status["total"]}))
        elif e["kind"] == "health":
            status["procs"] = e["procs"]
    return b"ok"


class Http(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if urlparse(self.path).path != "/status":
            return self._send(404, {"error": "not found"})
        with lock:
            self._send(200, {**status, "now": time.time(), "uplinkPid": os.getpid(), "nativeIpc": qnxipc.ON_QNX})

    def do_POST(self):
        u = urlparse(self.path)
        name = parse_qs(u.query).get("proc", [""])[0]
        with lock:
            pid = status["procs"].get(name, {}).get("pid")
        if u.path != "/crash" or not pid:
            return self._send(400, {"error": "unknown process"})
        with lock:
            status["crashes"] = (status["crashes"] + [{"proc": name, "pid": pid, "t": time.time()}])[-20:]
        os.kill(pid, signal.SIGKILL)
        self._send(200, {"killed": name, "pid": pid})

    def log_message(self, *a):
        pass


def main():
    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("HC_PORT", "8088"))), Http)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    qnxipc.Server("hc/uplink").serve(on_event)


if __name__ == "__main__":
    main()
