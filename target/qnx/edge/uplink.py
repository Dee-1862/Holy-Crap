"""Uplink process: collects events from the other processes and serves them to the dashboard.

Receives by message passing (name hc/uplink) and serves HTTP on port 8088:
    GET  /status            processes, frame rate, latest picture, flagged spots (JSON)
    GET  /telemetry         compact metrics only; no image or evidence payloads
    POST /crash?proc=NAME   ask the supervisor to run an explicitly enabled fault test
Spots are saved to disk as they come, so they survive this process being restarted.
"""
from __future__ import annotations

from collections import deque
import copy
import ipaddress
import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qnxipc

SAVED = Path(os.environ.get("HC_STATE", Path.home() / "hc-edge-state.json"))
CRASHABLE = frozenset({"infer", "model", "cloud", "site"})
CAPTURE_WINDOW = 240
lock = threading.Lock()
status = {"procs": {}, "frames": 0, "fps": 0.0, "ms": 0.0, "dropped": 0, "thumb": None, "w": 0, "h": 0,
          "warm": False, "lastFrame": 0.0, "spots": [], "total": 0, "results": [], "source": "", "full": None,
          "modelStats": None, "crashes": [], "faults": [], "captureTiming": None, "resources": None,
          "schedulerProfile": None, "qnxPrioritiesActive": None, "started": time.time()}
try:
    saved = json.loads(SAVED.read_text())
    status["spots"], status["total"] = saved["spots"][-200:], saved["total"]
except (OSError, ValueError, KeyError, TypeError):
    pass


def percentile(values: list[float], share: float) -> float | None:
    """Linear percentile for a small bounded sample without a third-party dependency."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * share
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


class CaptureTiming:
    """Bounded arrival-interval statistics; elapsed calculations use a monotonic clock."""

    def __init__(self, limit: int = CAPTURE_WINDOW):
        self._intervals_ms: deque[float] = deque(maxlen=limit)
        self._last_monotonic: float | None = None
        self.target_period_ms: float | None = None

    def set_target_period(self, milliseconds: object) -> None:
        if isinstance(milliseconds, (int, float)) and not isinstance(milliseconds, bool) and milliseconds > 0:
            self.target_period_ms = float(milliseconds)

    def observe(self, monotonic: float | None = None) -> None:
        monotonic = time.monotonic() if monotonic is None else monotonic
        if self._last_monotonic is not None:
            self._intervals_ms.append(max(0.0, monotonic - self._last_monotonic) * 1000)
        self._last_monotonic = monotonic

    def snapshot(self) -> dict:
        values = list(self._intervals_ms)
        misses = (sum(value > self.target_period_ms for value in values)
                  if self.target_period_ms is not None else None)
        return {
            "targetPeriodMs": round(self.target_period_ms, 3) if self.target_period_ms is not None else None,
            "periodP50Ms": self._rounded_percentile(values, 0.50),
            "periodP95Ms": self._rounded_percentile(values, 0.95),
            "periodP99Ms": self._rounded_percentile(values, 0.99),
            "periodMaxMs": round(max(values), 3) if values else None,
            "deadlineMisses": misses,
            "deadlineMissPercent": round(100.0 * misses / len(values), 3) if values and misses is not None else None,
            "sampleCount": len(values),
        }

    def fps(self) -> float:
        values = list(self._intervals_ms)
        return round(1000.0 / (sum(values) / len(values)), 2) if values and sum(values) > 0 else 0.0

    @staticmethod
    def _rounded_percentile(values: list[float], share: float) -> float | None:
        value = percentile(values, share)
        return round(value, 3) if value is not None else None


capture_timing = CaptureTiming()

TELEMETRY_KEYS = (
    "procs", "frames", "fps", "ms", "dropped", "warm", "lastFrame", "total", "source",
    "modelStats", "crashes", "faults", "captureTiming", "resources", "schedulerProfile",
    "qnxPrioritiesActive", "started",
)
MODEL_COUNTER_KEYS = (
    "patches", "stale", "evicted", "dropped", "skipped", "checked", "unreachable",
    "workerErrors",
)
MODEL_TIMING_KEYS = (
    "inferenceTiming", "successfulInferenceTiming", "failedAttemptTiming",
)
TIMING_VALUE_KEYS = ("sampleCount", "lastMs", "p50Ms", "p95Ms", "p99Ms", "maxMs")


def compact_model_stats(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    compact = {
        key: value[key] for key in MODEL_COUNTER_KEYS
        if isinstance(value.get(key), (int, float)) and not isinstance(value.get(key), bool)
    }
    for key in MODEL_TIMING_KEYS:
        timing = value.get(key)
        if isinstance(timing, dict):
            compact[key] = {
                field: timing[field] for field in TIMING_VALUE_KEYS
                if isinstance(timing.get(field), (int, float))
                and not isinstance(timing.get(field), bool)
            }
    return compact


def _common_snapshot_locked(*, now: float | None = None) -> dict:
    """Copy the bounded telemetry fields while holding ``lock``.

    The caller serializes and writes this copy after releasing the lock.  In
    particular, no thumbnail, full frame, candidate patch, result row, or
    base64 evidence can enter the compact endpoint.
    """
    snapshot = {key: copy.deepcopy(status.get(key)) for key in TELEMETRY_KEYS}
    snapshot["modelStats"] = compact_model_stats(status.get("modelStats"))
    snapshot.update({
        "statusSchema": "holy-crap.edge-telemetry",
        "statusVersion": 1,
        "now": time.time() if now is None else now,
        "uplinkPid": os.getpid(),
        "nativeIpc": qnxipc.ON_QNX,
        "faultTestsEnabled": edge_fault_tests_enabled(),
    })
    return snapshot


def telemetry_snapshot(*, now: float | None = None) -> dict:
    with lock:
        return _common_snapshot_locked(now=now)


def status_snapshot(*, now: float | None = None) -> dict:
    """Compatibility snapshot, including the legacy viewer/evidence fields."""
    with lock:
        snapshot = copy.deepcopy(status)
        snapshot.update({
            "statusSchema": "holy-crap.edge-status",
            "statusVersion": 2,
            "now": time.time() if now is None else now,
            "uplinkPid": os.getpid(),
            "nativeIpc": qnxipc.ON_QNX,
            "faultTestsEnabled": edge_fault_tests_enabled(),
        })
        return snapshot


def edge_fault_tests_enabled(environment: dict[str, str] | None = None) -> bool:
    """Target-side destructive-test gate; absent and malformed values fail closed."""
    environment = os.environ if environment is None else environment
    return environment.get("HC_EDGE_FAULT_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}


def http_bind_host(environment: dict[str, str] | None = None) -> str:
    """Keep status and fault controls on loopback unless an operator explicitly overrides it."""
    environment = os.environ if environment is None else environment
    configured = environment.get("HC_EDGE_BIND")
    return configured.strip() if configured and configured.strip() else "127.0.0.1"


def http_client_is_loopback(client_address: object) -> bool:
    """Fail closed unless the HTTP peer is an IPv4 or IPv6 loopback address."""
    if not isinstance(client_address, tuple) or not client_address:
        return False
    host = client_address[0]
    if not isinstance(host, str):
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def crash_allowed(process: object, processes: dict) -> bool:
    """Only isolated, supervised workers are eligible; camera and supervisor are never kill targets."""
    if not isinstance(process, str) or process not in CRASHABLE:
        return False
    info = processes.get(process, {})
    pid, generation = info.get("pid"), info.get("generation")
    return (
        isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
        and isinstance(generation, int) and not isinstance(generation, bool) and generation > 0
    )


def request_fault(process: str, pid: int, generation: int) -> dict:
    """Ask the owning supervisor to verify and signal its current child."""
    client = None
    try:
        client = qnxipc.Client("hc/supervisor", wait=0)
        raw = client.send(json.dumps({
            "kind": "fault-request",
            "proc": process,
            "expectedPid": pid,
            "generation": generation,
        }).encode())
        reply = json.loads(raw)
        if not isinstance(reply, dict):
            raise ValueError("supervisor reply is not an object")
        if reply.get("accepted") is True and reply.get("process") != process:
            return {"accepted": False, "process": process, "error": "supervisor process mismatch"}
        return reply
    except (OSError, ValueError, TypeError) as exc:
        return {"accepted": False, "process": process, "error": str(exc)[:160]}
    finally:
        if client is not None:
            client.close()


def on_event(msg: bytes) -> bytes:
    e = json.loads(msg)
    with lock:
        if e["kind"] == "frame":
            now = time.time()
            capture_timing.observe()
            status.update(frames=status["frames"] + 1, ms=e["ms"], dropped=e["dropped"], warm=e["warm"], lastFrame=now,
                          fps=capture_timing.fps(), captureTiming=capture_timing.snapshot())
            status.update(source=e.get("source", ""), full=e.get("full"))
            if e["thumb"]:
                status.update(thumb=e["thumb"], w=e["w"], h=e["h"])
            if e["spots"]:
                status["spots"] = (status["spots"] + e["spots"])[-200:]
                status["total"] += len(e["spots"])
                SAVED.write_text(json.dumps({"spots": status["spots"], "total": status["total"]}))
        elif e["kind"] == "explained":
            status["results"] = ([e] + status["results"])[:24]
            status["modelStats"] = e.get("modelStats")
        elif e["kind"] == "model-stats":
            status["modelStats"] = e.get("modelStats")
        elif e["kind"] == "health":
            status["procs"] = e["procs"]
            status["schedulerProfile"] = e.get("schedulerProfile")
            status["qnxPrioritiesActive"] = e.get("qnxPrioritiesActive")
            status["resources"] = e.get("resources")
            target_timing = e.get("captureTiming")
            if isinstance(target_timing, dict):
                capture_timing.set_target_period(target_timing.get("targetPeriodMs"))
                status["captureTiming"] = capture_timing.snapshot()
            faults = e.get("faults")
            if isinstance(faults, list):
                status["faults"] = faults[-20:]
            crashes = e.get("crashes")
            if isinstance(crashes, list):
                status["crashes"] = crashes[-20:]
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
        path = urlparse(self.path).path
        if path not in ("/status", "/telemetry"):
            return self._send(404, {"error": "not found"})
        snapshot = telemetry_snapshot() if path == "/telemetry" else status_snapshot()
        self._send(200, snapshot)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != "/crash":
            return self._send(404, {"error": "not found"})
        if not http_client_is_loopback(self.client_address):
            return self._send(403, {"accepted": False, "error": "fault endpoint is loopback-only"})
        if not edge_fault_tests_enabled():
            return self._send(403, {"accepted": False, "error": "target fault tests disabled"})
        name = parse_qs(u.query).get("proc", [""])[0]
        with lock:
            current = dict(status["procs"].get(name, {})) if crash_allowed(name, status["procs"]) else None
        if current is None:
            return self._send(400, {"accepted": False, "error": "unknown or unsupervised process"})
        reply = request_fault(name, current["pid"], current["generation"])
        self._send(200 if reply.get("accepted") is True else 409, reply)

    def log_message(self, *a):
        pass


def main():
    server = ThreadingHTTPServer((http_bind_host(), int(os.environ.get("HC_PORT", "8088"))), Http)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    qnxipc.Server("hc/uplink").serve(on_event)


if __name__ == "__main__":
    main()
