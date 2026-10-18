#!/system/bin/python3
"""Crash one disposable child, restart it, and measure each recovery boundary."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


POLL_SECONDS = 0.001
TIMEOUT_SECONDS = 10.0


def wait_for_payload(path: Path, generation: int, after_ns: int = 0) -> tuple[dict[str, object], int]:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if int(payload["generation"]) == generation and int(payload["monotonic_ns"]) >= after_ns:
                return payload, time.monotonic_ns()
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"timed out waiting for generation {generation} at {path}")


def spawn(worker: Path, ready: Path, result: Path, generation: int) -> tuple[subprocess.Popen[bytes], int]:
    requested_ns = time.monotonic_ns()
    child = subprocess.Popen(
        [sys.executable, str(worker), str(ready), str(result), str(generation)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    return child, requested_ns


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fault_supervisor.py OUTPUT_DIR", file=sys.stderr)
        return 64
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).with_name("fault_worker.py").resolve()
    ready = output / "worker-ready.json"
    result = output / "worker-result.json"

    child: subprocess.Popen[bytes] | None = None
    timeline: dict[str, object] = {
        "tool": "disposable_process_isolation_eval",
        "supervisor_pid": os.getpid(),
        "poll_interval_ms": POLL_SECONDS * 1000.0,
        "fault_signal": "SIGKILL",
    }
    try:
        child, initial_spawn_ns = spawn(worker, ready, result, 1)
        initial_ready, initial_ready_seen_ns = wait_for_payload(ready, 1)
        initial_result, initial_result_seen_ns = wait_for_payload(result, 1)
        timeline["initial"] = {
            "spawn_requested_ns": initial_spawn_ns,
            "pid": child.pid,
            "ready_payload_ns": int(initial_ready["monotonic_ns"]),
            "ready_observed_ns": initial_ready_seen_ns,
            "first_result_payload_ns": int(initial_result["monotonic_ns"]),
            "first_result_observed_ns": initial_result_seen_ns,
        }
        time.sleep(0.25)

        kill_requested_ns = time.monotonic_ns()
        os.kill(child.pid, signal.SIGKILL)
        returncode = child.wait(timeout=TIMEOUT_SECONDS)
        death_observed_ns = time.monotonic_ns()
        old_pid = child.pid

        child, respawn_requested_ns = spawn(worker, ready, result, 2)
        restarted_ready, restarted_ready_seen_ns = wait_for_payload(ready, 2, respawn_requested_ns)
        restarted_result, restarted_result_seen_ns = wait_for_payload(result, 2, respawn_requested_ns)
        timeline["fault"] = {
            "target_pid": old_pid,
            "kill_requested_ns": kill_requested_ns,
            "death_observed_ns": death_observed_ns,
            "returncode": returncode,
        }
        timeline["recovery"] = {
            "spawn_requested_ns": respawn_requested_ns,
            "replacement_pid": child.pid,
            "ready_payload_ns": int(restarted_ready["monotonic_ns"]),
            "ready_observed_ns": restarted_ready_seen_ns,
            "first_result_payload_ns": int(restarted_result["monotonic_ns"]),
            "first_result_observed_ns": restarted_result_seen_ns,
            "detect_ms": round((death_observed_ns - kill_requested_ns) / 1_000_000.0, 3),
            "spawn_call_gap_ms": round((respawn_requested_ns - death_observed_ns) / 1_000_000.0, 3),
            "ready_from_fault_ms": round((restarted_ready_seen_ns - kill_requested_ns) / 1_000_000.0, 3),
            "first_result_from_fault_ms": round((restarted_result_seen_ns - kill_requested_ns) / 1_000_000.0, 3),
        }
        print(json.dumps(timeline, sort_keys=True))
        return 0
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2.0)


if __name__ == "__main__":
    raise SystemExit(main())

