"""Model section: cuts a full resolution patch around each candidate spot and gets the detector's verdict.

Receives candidates from the spot finder (name hc/model) with the shared memory slot of the full frame.
The patch is cut out straight away, before the camera reuses that slot, and the reply goes back at once.
The verdict is fetched by a small pool of threads, so a slow model never blocks the spot finder. At most
`--pending` patches wait at a time. A newer one replaces the oldest instead of building a queue.

The detector runs on this Pi in the infer section (infer.py, ONNX Runtime from QNX's open source packages).
INFER_URL can still point at laptop/infer_server.py. If the detector is not answering, every patch goes on as
"not checked", with its appearance still measured.
"""
from __future__ import annotations

import argparse
import base64
from collections import deque
from collections.abc import Callable
import json
import math
import os
import threading
import time
import urllib.request
from typing import Any

import qnxipc
from shm import Frames
from spotter import Link

INFER_URL = os.environ.get("INFER_URL", "http://127.0.0.1:8770")      # the infer section on this Pi
PATCH = 128                       # full resolution pixels, about 10 percent of a 1280 wide frame
TIMING_WINDOW = 240


class LatestWorkPool:
    """Run work concurrently while retaining only the freshest waiting items.

    ``pending`` bounds queued work, not work already claimed by a worker.  When
    that queue is full, submit remains non-blocking and atomically replaces the
    oldest queued item.  A running callback is never cancelled or interrupted.
    """

    def __init__(
        self,
        workers: int,
        pending: int,
        callback: Callable[..., None],
        *,
        error_callback: Callable[[Exception, tuple[Any, ...]], None] | None = None,
        thread_name_prefix: str = "latest-work",
    ):
        if workers < 1:
            raise ValueError("workers must be at least 1")
        if pending < 1:
            raise ValueError("pending must be at least 1")
        self._callback = callback
        self._error_callback = error_callback
        self._pending = pending
        self._queue: deque[tuple[Any, ...]] = deque()
        self._condition = threading.Condition()
        self._shutdown = False
        self._threads = [
            threading.Thread(
                target=self._worker,
                name=f"{thread_name_prefix}_{index}",
                daemon=True,
            )
            for index in range(workers)
        ]
        for thread in self._threads:
            thread.start()

    def submit(self, *args: Any) -> str:
        """Queue work immediately and report whether older work was evicted."""

        with self._condition:
            if self._shutdown:
                return "dropped"
            outcome = "accepted"
            if len(self._queue) >= self._pending:
                self._queue.popleft()
                outcome = "evicted_oldest"
            self._queue.append(args)
            self._condition.notify()
            return outcome

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> int:
        """Stop accepting work and return the number of queued items cancelled."""

        with self._condition:
            self._shutdown = True
            cancelled = len(self._queue) if cancel_pending else 0
            if cancel_pending:
                self._queue.clear()
            self._condition.notify_all()
        if wait:
            current = threading.current_thread()
            for thread in self._threads:
                if thread is not current:
                    thread.join()
        return cancelled

    def _worker(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._shutdown:
                    self._condition.wait()
                if not self._queue:
                    return
                args = self._queue.popleft()
            try:
                self._callback(*args)
            except Exception as exc:
                # Match ThreadPoolExecutor's isolation: one failed item must not
                # terminate a worker and strand future queued work.
                if self._error_callback is not None:
                    try:
                        self._error_callback(exc, args)
                    except Exception:
                        pass
                continue


class TimingWindow:
    """Small bounded latency window suitable for the long-running edge worker."""

    def __init__(self, limit: int = TIMING_WINDOW):
        self._values: deque[float] = deque(maxlen=limit)
        self._last: float | None = None

    def add(self, milliseconds: float) -> None:
        self._last = max(0.0, milliseconds)
        self._values.append(self._last)

    def snapshot(self) -> dict:
        values = sorted(self._values)
        return {
            "sampleCount": len(values),
            "lastMs": round(self._last, 3) if self._last is not None else None,
            "p50Ms": self._percentile(values, 0.50),
            "p95Ms": self._percentile(values, 0.95),
            "p99Ms": self._percentile(values, 0.99),
            "maxMs": round(max(values), 3) if values else None,
        }

    @staticmethod
    def _percentile(values: list[float], share: float) -> float | None:
        if not values:
            return None
        position = (len(values) - 1) * share
        low, high = math.floor(position), math.ceil(position)
        value = values[low] if low == high else values[low] + (values[high] - values[low]) * (position - low)
        return round(value, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=3)
    ap.add_argument("--pending", type=int, default=6)
    args = ap.parse_args()
    explain, uplink = Link("hc/explain"), Link("hc/uplink")
    stats = {
        "patches": 0,
        "stale": 0,
        "evicted": 0,
        "dropped": 0,
        "skipped": 0,  # legacy alias for newly dropped work, not evictions
        "checked": 0,
        "unreachable": 0,
        "workerErrors": 0,
    }
    stats_lock = threading.Lock()
    successful_inference_timing = TimingWindow()
    failed_attempt_timing = TimingWindow()
    frames = {"f": None}

    def stats_snapshot() -> dict:
        return {
            **stats,
            # Legacy consumers treated inferenceTiming as successful latency.
            "inferenceTiming": successful_inference_timing.snapshot(),
            "successfulInferenceTiming": successful_inference_timing.snapshot(),
            "failedAttemptTiming": failed_attempt_timing.snapshot(),
        }

    def checked_model_response(value: object) -> dict:
        if not isinstance(value, dict):
            raise ValueError("model response was not an object")
        boxes = value.get("boxes", [])
        if not isinstance(boxes, list):
            raise ValueError("model boxes were not a list")
        if boxes:
            first = boxes[0]
            if (not isinstance(first, dict) or not isinstance(first.get("box"), list)
                    or len(first["box"]) != 4
                    or not all(isinstance(item, (int, float)) and not isinstance(item, bool)
                               for item in first["box"])
                    or not isinstance(first.get("score"), (int, float))
                    or isinstance(first.get("score"), bool)
                    or not isinstance(first.get("cls"), str)):
                raise ValueError("model response contained a malformed box")
        return value

    def verdict(spot: dict, rgb: bytes, side: int, t: float) -> None:
        started = time.monotonic()
        try:
            req = urllib.request.Request(f"{INFER_URL}/infer?w={side}&h={side}", data=rgb, method="POST")
            with urllib.request.urlopen(req, timeout=4) as r:
                model = checked_model_response(json.loads(r.read()))
            elapsed_ms = (time.monotonic() - started) * 1000
            with stats_lock:
                stats["checked"] += 1
                successful_inference_timing.add(elapsed_ms)
                snapshot = stats_snapshot()
        except Exception as e:
            elapsed_ms = (time.monotonic() - started) * 1000
            unreachable = isinstance(e, OSError)
            model = {"error": "%s: %s" % (
                "model not reachable" if unreachable else "model response failed",
                e.__class__.__name__,
            )}
            with stats_lock:
                stats["unreachable" if unreachable else "workerErrors"] += 1
                failed_attempt_timing.add(elapsed_ms)
                snapshot = stats_snapshot()
        delivered = explain.send({"kind": "patch", "spot": spot, "t": t, "side": side, "rgb": base64.b64encode(rgb).decode(),
                                  "model": model, "stats": snapshot})
        uplink.send({"kind": "model-stats", "modelStats": snapshot})
        if not delivered:
            raise OSError("explain worker unavailable")

    def worker_error(exc: Exception, args: tuple[Any, ...]) -> None:
        with stats_lock:
            stats["workerErrors"] += 1
            snapshot = stats_snapshot()
        uplink.send({"kind": "model-stats", "modelStats": snapshot})
        if len(args) != 4:
            return
        spot, rgb, side, observed_at = args
        try:
            explain.send({
                "kind": "patch", "spot": spot, "t": observed_at, "side": side,
                "rgb": base64.b64encode(rgb).decode(),
                "model": {"error": "model worker failed: %s" % exc.__class__.__name__},
                "stats": snapshot,
            })
        except Exception:
            pass

    pool = LatestWorkPool(
        args.threads, args.pending, verdict,
        error_callback=worker_error, thread_name_prefix="model",
    )

    def handle(msg: bytes) -> bytes:
        e = json.loads(msg)
        if frames["f"] is None:
            frames["f"] = Frames()
        for spot in e["spots"][:4]:
            cut = frames["f"].crop_rgb(e["slot"], spot["cx"], spot["cy"], PATCH)
            if cut is None:
                with stats_lock:
                    stats["stale"] += 1                # the camera already reused that slot
                continue
            with stats_lock:
                stats["patches"] += 1
            outcome = pool.submit(spot, cut[0], cut[1], e["t"])
            if outcome != "accepted":
                with stats_lock:
                    if outcome == "evicted_oldest":
                        stats["evicted"] += 1
                    else:
                        stats["patches"] -= 1
                        stats["dropped"] += 1
                        stats["skipped"] += 1
        with stats_lock:
            snapshot = stats_snapshot()
        uplink.send({"kind": "model-stats", "modelStats": snapshot})
        return b"ok"

    qnxipc.Server("hc/model").serve(handle)


if __name__ == "__main__":
    main()
