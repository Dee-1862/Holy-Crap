#!/system/bin/python3
"""Measure every native QNX MsgSend round trip for one exact payload size."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qnxipc  # noqa: E402


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def server(name: str) -> int:
    qnxipc.Server(name).serve(lambda data: data[:16])
    return 0


def client(csv_path: Path, iterations: int, payload_bytes: int) -> int:
    name = f"hc/eval/{os.getpid()}"
    child = subprocess.Popen(
        [sys.executable, __file__, "server", name],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        connection = qnxipc.Client(name)
        payload = bytes(payload_bytes)
        for _ in range(20):
            connection.send(payload)
        calls_us: list[float] = []
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["call_index", "payload_bytes", "round_trip_us"])
            for index in range(iterations):
                started = time.perf_counter_ns()
                reply = connection.send(payload)
                elapsed_us = (time.perf_counter_ns() - started) / 1000.0
                if len(reply) != 16:
                    raise RuntimeError(f"unexpected reply length {len(reply)}")
                calls_us.append(elapsed_us)
                writer.writerow([index, payload_bytes, f"{elapsed_us:.3f}"])
        print(
            json.dumps(
                {
                    "tool": "qnx_msgsend_eval",
                    "native_qnx_message_passing": qnxipc.ON_QNX,
                    "payload_bytes": payload_bytes,
                    "reply_bytes": 16,
                    "warmups": 20,
                    "iterations": iterations,
                    "round_trip_us": {
                        "mean": round(statistics.fmean(calls_us), 3),
                        "p50": round(percentile(calls_us, 0.50), 3),
                        "p95": round(percentile(calls_us, 0.95), 3),
                        "p99": round(percentile(calls_us, 0.99), 3),
                        "max": round(max(calls_us), 3),
                    },
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2.0)


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "server":
        return server(sys.argv[2])
    if len(sys.argv) != 4:
        print("usage: ipc_eval.py CALLS.CSV ITERATIONS PAYLOAD_BYTES", file=sys.stderr)
        return 64
    return client(Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))


if __name__ == "__main__":
    raise SystemExit(main())
