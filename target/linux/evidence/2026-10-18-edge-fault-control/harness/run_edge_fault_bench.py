"""Run the isolated Linux control-path fault and load benchmark.

This never claims QNX behavior.  It exercises the edge process topology on
Linux, where qnxipc uses its localhost TCP fallback and scheduling is control.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib


GIB = 1024**3
PER_PROCESS_AS_BYTES = 8 * GIB
AGGREGATE_ABORT_BYTES = int(7.5 * GIB)
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
CRASHABLE = ("infer", "model", "cloud", "site")
IPC_NAMES = {
    "model": "hc/model",
    "cloud": "hc/cloud",
}


def json_dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def append_jsonl(path: Path, value: object) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def limited_child() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (PER_PROCESS_AS_BYTES, PER_PROCESS_AS_BYTES))


def read_proc_stat(pid: int) -> dict | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        close = text.rfind(")")
        tail = text[close + 2 :].split()
        return {
            "ppid": int(tail[1]),
            "ticks": int(tail[11]) + int(tail[12]),
            "rss_bytes": int(tail[21]) * PAGE_SIZE,
        }
    except (OSError, ValueError, IndexError):
        return None


def process_table() -> dict[int, dict]:
    table = {}
    for item in Path("/proc").iterdir():
        if item.name.isdigit():
            row = read_proc_stat(int(item.name))
            if row is not None:
                table[int(item.name)] = row
    return table


def tree_file_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def descendants(roots: set[int], table: dict[int, dict]) -> set[int]:
    found = set(roots)
    changed = True
    while changed:
        changed = False
        for pid, row in table.items():
            if row["ppid"] in found and pid not in found:
                found.add(pid)
                changed = True
    return found


def thermal_c() -> float | None:
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except (OSError, ValueError):
        return None


def fetch_json(url: str, *, data: bytes | None = None, timeout: float = 1.0) -> dict:
    request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read())
    if not isinstance(body, dict):
        raise ValueError("endpoint did not return a JSON object")
    return body


def slim_status(status: dict) -> dict:
    return {
        "frames": status.get("frames"),
        "fps": status.get("fps"),
        "dropped": status.get("dropped"),
        "warm": status.get("warm"),
        "total": status.get("total"),
        "source": status.get("source"),
        "nativeIpc": status.get("nativeIpc"),
        "schedulerProfile": status.get("schedulerProfile"),
        "qnxPrioritiesActive": status.get("qnxPrioritiesActive"),
        "captureTiming": status.get("captureTiming"),
        "modelStats": status.get("modelStats"),
        "procs": status.get("procs"),
        "faults": status.get("faults"),
        "resultsCount": len(status.get("results") or []),
        "latestResult": {
            key: (status.get("results") or [{}])[0].get(key)
            for key in ("id", "t", "checked", "verdict", "cls", "score")
        }
        if status.get("results")
        else None,
    }


def ipc_port(name: str, base: int) -> int:
    return base + zlib.crc32(name.encode()) % 2000


class Benchmark:
    def __init__(
        self,
        stage: Path,
        baseline_s: float,
        stress_s: float,
        original_source_sha256: str,
        reference_clip_sha256: str,
    ):
        self.stage = stage.resolve()
        self.results = self.stage / "results"
        self.results.mkdir(exist_ok=False)
        self.samples_path = self.results / "samples.jsonl"
        self.events_path = self.results / "events.jsonl"
        self.supervisor: subprocess.Popen | None = None
        self.stress: list[subprocess.Popen] = []
        self.abort = threading.Event()
        self.stop_monitor = threading.Event()
        self.monitor_thread: threading.Thread | None = None
        self.previous_ticks: dict[int, tuple[int, int]] = {}
        self.baseline_s = baseline_s
        self.stress_s = stress_s
        self.status_url = "http://127.0.0.1:18088"
        self.infer_url = "http://127.0.0.1:18770"
        self.ipc_base = 46000
        self.phase = "startup"
        self.original_source_sha256 = original_source_sha256
        self.reference_clip_sha256 = reference_clip_sha256
        self.stage_file_bytes = tree_file_bytes(self.stage)
        self.stage_scan_monotonic = time.monotonic()

    def record_event(self, kind: str, **details: object) -> None:
        append_jsonl(
            self.events_path,
            {"monotonicNs": time.monotonic_ns(), "wallTime": time.time(), "kind": kind, **details},
        )

    def managed_roots(self) -> set[int]:
        roots = {process.pid for process in self.stress if process.poll() is None}
        if self.supervisor is not None and self.supervisor.poll() is None:
            roots.add(self.supervisor.pid)
        return roots

    def stop_group(self, process: subprocess.Popen, sig: int) -> None:
        if process.poll() is None:
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass

    def cleanup(self) -> None:
        self.stop_monitor.set()
        for process in self.stress:
            self.stop_group(process, signal.SIGTERM)
        if self.supervisor is not None:
            self.stop_group(self.supervisor, signal.SIGTERM)
        deadline = time.monotonic() + 5
        all_processes = self.stress + ([self.supervisor] if self.supervisor is not None else [])
        for process in all_processes:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                self.stop_group(process, signal.SIGKILL)
        if self.monitor_thread is not None:
            self.monitor_thread.join(timeout=3)

    def monitor(self) -> None:
        while not self.stop_monitor.wait(0.2):
            monotonic_ns = time.monotonic_ns()
            table = process_table()
            managed = descendants(self.managed_roots(), table)
            rss = sum(table[pid]["rss_bytes"] for pid in managed if pid in table)
            if time.monotonic() - self.stage_scan_monotonic >= 2:
                self.stage_file_bytes = tree_file_bytes(self.stage)
                self.stage_scan_monotonic = time.monotonic()
            combined_bytes = rss + self.stage_file_bytes
            cpu = {}
            for pid in managed:
                row = table.get(pid)
                if row is None:
                    continue
                prior = self.previous_ticks.get(pid)
                if prior is not None and monotonic_ns > prior[0]:
                    elapsed_s = (monotonic_ns - prior[0]) / 1e9
                    cpu[str(pid)] = round((row["ticks"] - prior[1]) / CLOCK_TICKS / elapsed_s * 100, 3)
                self.previous_ticks[pid] = (monotonic_ns, row["ticks"])
            try:
                status = slim_status(fetch_json(f"{self.status_url}/status"))
                status_error = None
            except Exception as error:
                status = None
                status_error = f"{type(error).__name__}: {error}"
            cloud_queue = self.stage / "cloud-queue.jsonl"
            try:
                queue_lines = sum(1 for _ in cloud_queue.open())
                queue_bytes = cloud_queue.stat().st_size
            except OSError:
                queue_lines = 0
                queue_bytes = 0
            append_jsonl(
                self.samples_path,
                {
                    "monotonicNs": monotonic_ns,
                    "wallTime": time.time(),
                    "phase": self.phase,
                    "managedPids": sorted(managed),
                    "aggregateRssBytes": rss,
                    "stageFileBytes": self.stage_file_bytes,
                    "combinedRssAndStageFileBytes": combined_bytes,
                    "perPidCpuPercent": cpu,
                    "temperatureC": thermal_c(),
                    "cloudQueueLines": queue_lines,
                    "cloudQueueBytes": queue_bytes,
                    "status": status,
                    "statusError": status_error,
                },
            )
            if combined_bytes >= AGGREGATE_ABORT_BYTES:
                self.record_event(
                    "aggregate-memory-abort",
                    rssBytes=rss,
                    stageFileBytes=self.stage_file_bytes,
                    combinedBytes=combined_bytes,
                    thresholdBytes=AGGREGATE_ABORT_BYTES,
                )
                self.abort.set()
                for process in self.stress:
                    self.stop_group(process, signal.SIGKILL)
                if self.supervisor is not None:
                    self.stop_group(self.supervisor, signal.SIGKILL)
                return

    def wait_status(self, timeout: float = 40.0) -> dict:
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            if self.abort.is_set():
                raise RuntimeError("aggregate memory watchdog aborted the benchmark")
            try:
                status = fetch_json(f"{self.status_url}/status")
                if status.get("procs"):
                    return status
            except Exception as error:
                last_error = error
            time.sleep(0.1)
        raise RuntimeError(f"status did not become ready: {last_error}")

    def start_pipeline(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "HC_MODEL": str(self.stage / "edge" / "dropping4_yolo11n_640.onnx"),
                "HC_THREADS": "2",
                "HC_PORT": "18088",
                "HC_INFER_PORT": "18770",
                "HC_WATCH_PORT": "18089",
                "INFER_URL": self.infer_url,
                "HC_IPC_BASE": str(self.ipc_base),
                "HC_SHM_PATH": str(self.stage / "hc-frames"),
                "HC_STATE": str(self.stage / "edge-state.json"),
                "HC_CLOUD_QUEUE": str(self.stage / "cloud-queue.jsonl"),
                "HC_SITE_CONF": str(self.stage / "site-disabled.json"),
                "HC_UPLINK": self.status_url,
                "CLOUD_URL": "http://127.0.0.1:1/api/edge/ingest",
            }
        )
        log = (self.results / "supervisor.log").open("wb")
        command = [
            str(self.stage / "venv" / "bin" / "python"),
            str(self.stage / "edge" / "supervisor.py"),
            "--camera",
            "replay",
            "--mov",
            str(self.stage / "replay-argb.mov"),
            "--rate",
            "5",
            "--scheduling",
            "control",
        ]
        self.supervisor = subprocess.Popen(
            command,
            cwd=self.stage / "edge",
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            preexec_fn=limited_child,
        )
        self.record_event("pipeline-start", pid=self.supervisor.pid, argv=command)
        self.monitor_thread = threading.Thread(target=self.monitor, name="resource-monitor", daemon=True)
        self.monitor_thread.start()
        status = self.wait_status()
        self.record_event("status-ready", status=slim_status(status))

    def hold_phase(self, name: str, seconds: float) -> None:
        self.phase = name
        self.record_event("phase-start", phase=name, seconds=seconds)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.abort.is_set():
                raise RuntimeError("aggregate memory watchdog aborted the benchmark")
            if self.supervisor is None or self.supervisor.poll() is not None:
                raise RuntimeError("supervisor exited during benchmark")
            time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
        status = self.wait_status()
        self.record_event("phase-end", phase=name, status=slim_status(status))

    def start_stress(self) -> None:
        for cpu in (2, 3):
            log = (self.results / f"stress-cpu{cpu}.log").open("wb")
            process = subprocess.Popen(
                [sys.executable, str(self.stage / "stress_worker.py"), "--cpu", str(cpu)],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                preexec_fn=limited_child,
            )
            self.stress.append(process)
        self.record_event("stress-start", pids=[process.pid for process in self.stress], cpus=[2, 3], nice=19)

    def stop_stress(self) -> None:
        for process in self.stress:
            self.stop_group(process, signal.SIGTERM)
        for process in self.stress:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.stop_group(process, signal.SIGKILL)
        self.record_event("stress-stop", returncodes=[process.poll() for process in self.stress])

    def probe_worker(self, process: str) -> bool:
        if process == "infer":
            try:
                fetch_json(self.infer_url, timeout=0.4)
                return True
            except Exception:
                return False
        ipc_name = IPC_NAMES.get(process)
        if ipc_name is None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", ipc_port(ipc_name, self.ipc_base)), timeout=0.3):
                return True
        except OSError:
            return False

    @staticmethod
    def newest_result_key(status: dict) -> tuple | None:
        results = status.get("results") or []
        if not results:
            return None
        result = results[0]
        return result.get("id"), result.get("t"), result.get("checked"), result.get("score")

    def crash_once(self, process: str, regime: str) -> None:
        before = self.wait_status()
        before_pids = {name: details.get("pid") for name, details in before["procs"].items()}
        old_pid = before_pids.get(process)
        before_result = self.newest_result_key(before)
        started_ns = time.monotonic_ns()
        response = fetch_json(f"{self.status_url}/crash?proc={process}", data=b"{}", timeout=2)
        response_ns = time.monotonic_ns()
        pid_changed_ns = None
        probe_ready_ns = None
        first_result_ns = None
        event = None
        after = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                current = fetch_json(f"{self.status_url}/status", timeout=0.5)
            except Exception:
                time.sleep(0.025)
                continue
            current_pid = (current.get("procs", {}).get(process) or {}).get("pid")
            if current_pid and current_pid != old_pid and pid_changed_ns is None:
                pid_changed_ns = time.monotonic_ns()
            if pid_changed_ns is not None and probe_ready_ns is None and self.probe_worker(process):
                probe_ready_ns = time.monotonic_ns()
            if self.newest_result_key(current) not in (None, before_result) and first_result_ns is None:
                first_result_ns = time.monotonic_ns()
            for candidate in reversed(current.get("faults") or []):
                if candidate.get("proc") == process and candidate.get("oldPid") == old_pid:
                    event = candidate
                    break
            after = current
            if event and event.get("state") == "respawned" and pid_changed_ns is not None:
                if process == "site" or probe_ready_ns is not None:
                    break
            time.sleep(0.025)
        if after is None:
            raise RuntimeError(f"no status after crashing {process}")
        after_pids = {name: details.get("pid") for name, details in after.get("procs", {}).items()}
        unrelated_changes = {
            name: {"before": pid, "after": after_pids.get(name)}
            for name, pid in before_pids.items()
            if name != process and after_pids.get(name) != pid
        }
        record = {
            "regime": regime,
            "process": process,
            "oldPid": old_pid,
            "newPid": after_pids.get(process),
            "requestResponse": response,
            "rawFaultEvent": event,
            "applicationReadyAt": event.get("readyAt") if event else None,
            "applicationFirstResultAt": event.get("firstResultAt") if event else None,
            "applicationRecoveryMs": event.get("recoveryMs") if event else None,
            "externalMonotonic": {
                "requestStartedNs": started_ns,
                "httpResponseNs": response_ns,
                "pidChangedNs": pid_changed_ns,
                "workerProbeReadyNs": probe_ready_ns,
                "firstNewResultNs": first_result_ns,
                "httpResponseMs": round((response_ns - started_ns) / 1e6, 3),
                "pidChangeMs": round((pid_changed_ns - started_ns) / 1e6, 3) if pid_changed_ns else None,
                "workerProbeReadyMs": round((probe_ready_ns - started_ns) / 1e6, 3) if probe_ready_ns else None,
                "firstNewResultMs": round((first_result_ns - started_ns) / 1e6, 3) if first_result_ns else None,
            },
            "unrelatedPidChanges": unrelated_changes,
            "before": slim_status(before),
            "after": slim_status(after),
        }
        append_jsonl(self.results / "fault-tests.jsonl", record)
        self.record_event("fault-test", **record)
        time.sleep(2)

    def run(self) -> None:
        metadata = {
            "claimBoundary": "Linux TCP fallback and application supervisor; not QNX evidence",
            "temporaryCompatibilityChanges": [
                "ortlite Session is backed by Linux onnxruntime Python instead of QNX libhcort.so",
                "shared-memory file and HTTP/TCP ports are redirected into the isolated benchmark namespace",
                "TCP fallback uses CRC32 port assignment because the production byte-sum mapping collides for hc/cloud and hc/watch",
                "TCP fallback serves each persistent client in a thread because the production single-connection loop starves supervisor health behind spotter",
            ],
            "perProcessAddressSpaceLimitBytes": PER_PROCESS_AS_BYTES,
            "aggregateAbortBytes": AGGREGATE_ABORT_BYTES,
            "aggregateGuardIncludes": "process-tree RSS plus all regular-file logical bytes under the tmpfs stage",
            "originalDatasetSourceSha256": self.original_source_sha256,
            "referenceBaselineClipSha256": self.reference_clip_sha256,
            "containerVersionDrift": {
                "sameSourceAndSegment": True,
                "byteIdenticalToReference": sha256(self.stage / "source.mp4") == self.reference_clip_sha256,
                "derivation": "ffmpeg 8.0.1 source-copy of 0-20s; 20.08s, 502 frames, 6,061,986 bytes",
            },
            "sourceMp4": {
                "path": str(self.stage / "source.mp4"),
                "sha256": sha256(self.stage / "source.mp4"),
            },
            "replayMov": {
                "path": str(self.stage / "replay-argb.mov"),
                "sha256": sha256(self.stage / "replay-argb.mov"),
            },
            "model": {
                "path": str(self.stage / "edge" / "dropping4_yolo11n_640.onnx"),
                "sha256": sha256(self.stage / "edge" / "dropping4_yolo11n_640.onnx"),
            },
            "edgeFiles": {
                str(path.relative_to(self.stage)): sha256(path)
                for path in sorted((self.stage / "edge").rglob("*.py"))
            },
            "startedWallTime": time.time(),
            "python": sys.version,
        }
        json_dump(self.results / "metadata.json", metadata)
        self.start_pipeline()
        self.hold_phase("warmup", 15)
        self.hold_phase("unloaded", self.baseline_s)
        self.start_stress()
        self.hold_phase("stress", self.stress_s)
        for process in CRASHABLE:
            self.phase = f"fault-stress-{process}"
            self.crash_once(process, "stress")
        self.stop_stress()
        self.hold_phase("recovery", 10)
        final = self.wait_status()
        json_dump(self.results / "final-status.json", slim_status(final))
        self.record_event("benchmark-complete", status=slim_status(final))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--baseline-seconds", type=float, default=55)
    parser.add_argument("--stress-seconds", type=float, default=55)
    parser.add_argument("--original-source-sha256", required=True)
    parser.add_argument("--reference-clip-sha256", required=True)
    args = parser.parse_args()
    benchmark = Benchmark(
        args.stage,
        args.baseline_seconds,
        args.stress_seconds,
        args.original_source_sha256,
        args.reference_clip_sha256,
    )
    try:
        benchmark.run()
    except Exception as error:
        benchmark.record_event("benchmark-failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        benchmark.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
