"""Start the edge pipeline as separate processes, each at its own priority, and restart any that dies.

    python3 supervisor.py --camera replay --mov /data/share/sensor/simulator_camera.barn.mov
    python3 supervisor.py --camera live --unit 4

This pipeline uses separate process boundaries and message passing so a worker failure can be detected and
that worker can be restarted without intentionally terminating the other application workers. This is an
application-level containment claim only; it does not claim isolation from every driver or kernel failure.

Priorities use QNX's real time scheduler (`on -p`, higher runs first, normal is 10), so the farmer's alerts
and the camera always run before the heavy model work:
    watch 21, camera 20, spotter 12, uplink 11, cloud 11, explain 9, model 8
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import qnxipc

HERE = Path(__file__).resolve().parent
PY = sys.executable
FAULT_HISTORY = 20
CRASHABLE = frozenset({"infer", "model", "cloud", "site"})
PIDIN_SAMPLE_INTERVAL_S = 2.0
PIDIN_TIMEOUT_S = 0.75


def _size_bytes(value: str) -> int | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMG]?)", value.strip(), re.IGNORECASE)
    if match is None:
        return None
    scale = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[match.group(2).upper()]
    return round(float(match.group(1)) * scale)


def parse_pidin_sched(output: str, pid: int) -> tuple[dict, str | None]:
    """Parse the first observed thread row from ``pidin -p PID sched``."""
    row = re.compile(r"^\s*%d\s+\d+\s+\S+\s+(\d+)([A-Za-z]?)\s+" % pid)
    for line in output.splitlines():
        match = row.match(line)
        if match is None:
            continue
        suffix = match.group(2).lower()
        policies = {"r": "SCHED_RR", "f": "SCHED_FIFO", "o": "SCHED_OTHER"}
        policy = policies.get(suffix)
        detail = None if policy is not None else "pidin sched policy suffix was not recognized"
        return {"priority": int(match.group(1)), "policy": policy}, detail
    return {"priority": None, "policy": None}, "pidin sched did not contain the requested PID"


def parse_pidin_runmask(output: str) -> tuple[str | None, str | None]:
    match = re.search(r"^\s*Runmask\s*:\s*(0x[0-9a-fA-F]+)\s*$", output, re.MULTILINE)
    if match is None:
        return None, "pidin rmasks did not report a runmask"
    return match.group(1).lower(), None


def parse_pidin_memory(output: str, pid: int) -> tuple[int | None, str | None]:
    """Read the process-row data column, not a guessed system-memory total."""
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 8 or fields[0] != str(pid) or not fields[1].isdigit():
            continue
        value = _size_bytes(fields[6])
        if value is not None:
            return value, None
        return None, "pidin memory data column had an unknown unit"
    return None, "pidin memory did not contain the requested PID"


def parse_pidin_times(output: str, pid: int) -> tuple[float | None, str | None]:
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 9 or fields[0] != str(pid):
            continue
        try:
            return float(fields[-4]) + float(fields[-3]), None
        except ValueError:
            return None, "pidin times CPU fields were malformed"
    return None, "pidin times did not contain the requested PID"


class ProcessTelemetrySampler:
    """Round-robin, low-rate observations of supervised QNX processes.

    Only one process is inspected per interval.  Commands have short timeouts,
    and sampling is called with a copied supervisor snapshot outside its lock.
    System-wide CPU and RAM remain intentionally unreported.
    """

    def __init__(self, *, interval: float = PIDIN_SAMPLE_INTERVAL_S,
                 timeout: float = PIDIN_TIMEOUT_S, runner=None,
                 monotonic=None, wall=None):
        self.interval = interval
        self.timeout = timeout
        self.runner = runner or subprocess.run
        self.monotonic = monotonic or time.monotonic
        self.wall = wall or time.time
        self._next = 0.0
        self._cursor = 0
        self._cache: dict[str, dict] = {}
        self._cpu: dict[str, tuple[int, float, float]] = {}

    def _command(self, pid: int, section: str) -> tuple[str, str | None]:
        try:
            result = self.runner(
                ["pidin", "-p", str(pid), section], capture_output=True, text=True,
                timeout=self.timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return "", "%s failed: %s" % (section, type(exc).__name__)
        if result.returncode != 0:
            return "", "%s exited %d" % (section, result.returncode)
        return result.stdout or "", None

    def _sample_one(self, name: str, pid: int, now: float) -> None:
        errors: list[str] = []
        outputs = {}
        for section in ("sched", "rmasks", "memory", "times"):
            outputs[section], error = self._command(pid, section)
            if error:
                errors.append(error)
        observed, error = parse_pidin_sched(outputs["sched"], pid)
        if error:
            errors.append(error)
        runmask, error = parse_pidin_runmask(outputs["rmasks"])
        if error:
            errors.append(error)
        ram_bytes, error = parse_pidin_memory(outputs["memory"], pid)
        if error:
            errors.append(error)
        cpu_total, error = parse_pidin_times(outputs["times"], pid)
        if error:
            errors.append(error)
        cpu_percent = None
        previous = self._cpu.get(name)
        if cpu_total is not None:
            if previous is not None and previous[0] == pid and now > previous[1]:
                cpu_percent = max(0.0, 100.0 * (cpu_total - previous[2]) / (now - previous[1]))
            self._cpu[name] = (pid, now, cpu_total)
        self._cache[name] = {
            "pid": pid,
            "observed": {**observed, "runmask": runmask},
            "resource": {
                "cpuPercent": round(cpu_percent, 3) if cpu_percent is not None else None,
                "ramBytes": ram_bytes,
                "sampledAt": self.wall(),
            },
            "observedDetail": "; ".join(dict.fromkeys(errors))[:512] if errors else "pidin observed",
        }

    def sample(self, processes: dict[str, dict]) -> tuple[dict[str, dict], dict]:
        now = self.monotonic()
        live = [(name, entry.get("pid")) for name, entry in sorted(processes.items())
                if isinstance(entry.get("pid"), int) and entry["pid"] > 0]
        if live and now >= self._next:
            name, pid = live[self._cursor % len(live)]
            self._cursor += 1
            self._next = now + self.interval
            self._sample_one(name, pid, now)
        enriched = {name: dict(entry) for name, entry in processes.items()}
        for name, entry in enriched.items():
            cached = self._cache.get(name)
            if cached is not None and cached["pid"] == entry.get("pid"):
                entry.update({key: value for key, value in cached.items() if key != "pid"})
            else:
                entry.update({
                    "observed": {"priority": None, "policy": None, "runmask": None},
                    "resource": {"cpuPercent": None, "ramBytes": None, "sampledAt": None},
                    "observedDetail": "not sampled yet",
                })
        current = [entry["resource"] for entry in enriched.values()
                   if isinstance(entry.get("resource"), dict)]
        cpu_values = [item["cpuPercent"] for item in current if item.get("cpuPercent") is not None]
        ram_values = [item["ramBytes"] for item in current if item.get("ramBytes") is not None]
        resources = {
            "cpuPercent": None,
            "ramUsedBytes": None,
            "ramTotalBytes": None,
            "processCpuPercent": round(sum(cpu_values), 3) if cpu_values else None,
            "processRamBytes": sum(ram_values) if ram_values else None,
            "detail": "latest pidin samples (not simultaneous): %d/%d CPU and %d/%d data-column memory observations; system totals unavailable"
                      % (len(cpu_values), len(live), len(ram_values), len(live)),
        }
        return enriched, resources


def edge_fault_tests_enabled(environment: dict[str, str] | None = None) -> bool:
    """Target-side destructive-test gate; absent and malformed values fail closed."""
    environment = os.environ if environment is None else environment
    return environment.get("HC_EDGE_FAULT_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}


def launch_command(command: list[str], priority: int, scheduling: str, *, on_qnx: bool,
                   on_path: str | None) -> tuple[list[str], bool]:
    """Return the exact launch argv and whether the configured QNX priority path is active.

    This reports only what this supervisor can prove from its own launch path. It does not infer an
    observed thread policy, priority, or runmask.
    """
    active = scheduling == "qnx" and on_qnx and bool(on_path)
    return (([on_path or "on", "-p", str(priority)] + command) if active else list(command), active)


class FaultHistory:
    """Thread-safe, bounded crash/respawn accounting using monotonic elapsed time internally."""

    def __init__(self, limit: int = FAULT_HISTORY):
        self._events: deque[dict] = deque(maxlen=limit)
        self._lock = threading.Lock()

    def requested(self, process: str, pid: int, generation: int = 1, *, fault_id: str | None = None,
                  wall: float | None = None, monotonic: float | None = None) -> dict:
        wall = time.time() if wall is None else wall
        monotonic = time.monotonic() if monotonic is None else monotonic
        event = {
            "faultId": fault_id or uuid.uuid4().hex,
            "proc": process,
            "generation": generation,
            "oldPid": pid,
            "newPid": None,
            "requestedAt": wall,
            "detectedAt": None,
            "spawnedAt": None,
            "readyAt": None,
            "firstResultAt": None,
            "respawnMs": None,
            "recoveryMs": None,
            "state": "requested",
            "_requestedMonotonic": monotonic,
        }
        with self._lock:
            self._events.append(event)
        return self._public(event)

    def failed(self, fault_id: str) -> dict | None:
        """Mark a recorded request whose exact-child signal failed."""
        with self._lock:
            event = next((candidate for candidate in reversed(self._events)
                          if candidate["faultId"] == fault_id), None)
            if event is None:
                return None
            event["state"] = "signal_failed"
            return self._public(event)

    def respawned(self, process: str, old_pid: int, new_pid: int, *, generation: int = 1,
                  detected_wall: float,
                  spawned_wall: float, detected_monotonic: float, spawned_monotonic: float) -> dict:
        with self._lock:
            event = next((candidate for candidate in reversed(self._events)
                          if candidate["proc"] == process and candidate["oldPid"] == old_pid
                          and candidate["generation"] == generation
                          and candidate["state"] == "requested"), None)
            if event is None:
                event = {
                    "faultId": None,
                    "proc": process,
                    "generation": generation,
                    "oldPid": old_pid,
                    "newPid": None,
                    "requestedAt": None,
                    "detectedAt": None,
                    "spawnedAt": None,
                    "readyAt": None,
                    "firstResultAt": None,
                    "respawnMs": None,
                    "recoveryMs": None,
                    "state": "detected",
                    "_requestedMonotonic": None,
                }
                self._events.append(event)
            event.update(
                newPid=new_pid,
                detectedAt=detected_wall,
                spawnedAt=spawned_wall,
                respawnMs=round(max(0.0, spawned_monotonic - detected_monotonic) * 1000, 3),
                state="respawned",
            )
            return self._public(event)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [self._public(event) for event in self._events]

    @staticmethod
    def _public(event: dict) -> dict:
        return {key: value for key, value in event.items() if not key.startswith("_")}


class FaultController:
    """Atomically verify and signal only the exact child currently owned by this supervisor."""

    def __init__(self, procs: dict, info: dict, history: FaultHistory, process_lock: threading.RLock,
                 *, enabled: bool, id_factory=None):
        self.procs = procs
        self.info = info
        self.history = history
        self.process_lock = process_lock
        self.enabled = enabled
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex)

    @staticmethod
    def _reject(error: str, process: object = None) -> dict:
        response = {"accepted": False, "error": error}
        if isinstance(process, str):
            response["process"] = process
        return response

    def handle(self, msg: bytes) -> bytes:
        try:
            request = json.loads(msg)
        except (ValueError, TypeError):
            return json.dumps(self._reject("invalid request JSON")).encode()
        if not isinstance(request, dict) or request.get("kind") != "fault-request":
            return json.dumps(self._reject("invalid fault request")).encode()
        return json.dumps(self.request(
            request.get("proc"), request.get("expectedPid"), request.get("generation")
        )).encode()

    def request(self, process: object, expected_pid: object, generation: object) -> dict:
        if not self.enabled:
            return self._reject("target fault tests disabled", process)
        if process not in CRASHABLE:
            return self._reject("process is not fault-test allowlisted", process)
        if (not isinstance(expected_pid, int) or isinstance(expected_pid, bool) or expected_pid <= 0
                or not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0):
            return self._reject("expectedPid and generation must be positive integers", process)

        # The lock covers lookup, identity/generation validation, history insertion, and signal delivery.
        # A respawn cannot replace this Popen between validation and signal.
        with self.process_lock:
            child = self.procs.get(process)
            current = self.info.get(process)
            if child is None or not isinstance(current, dict):
                return self._reject("process is not currently supervised", process)
            if (child.pid != expected_pid or current.get("pid") != expected_pid
                    or current.get("generation") != generation or child.poll() is not None):
                return self._reject("stale pid or generation", process)

            fault_id = self.id_factory()
            self.history.requested(process, expected_pid, generation, fault_id=fault_id)
            try:
                child.send_signal(signal.SIGKILL)
            except OSError as exc:
                self.history.failed(fault_id)
                return {
                    "accepted": False,
                    "process": process,
                    "faultId": fault_id,
                    "error": ("signal failed: %s" % exc)[:160],
                }
            # Keep the legacy fields while the host normalizer migrates. They describe the exact
            # child that the supervisor just signalled; the uplink never signals a PID itself.
            return {
                "accepted": True,
                "process": process,
                "faultId": fault_id,
                "pid": expected_pid,
                "generation": generation,
                "killed": process,
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", choices=["replay", "live"], default="replay")
    ap.add_argument("--mov", default="/data/share/sensor/simulator_camera.barn.mov")
    ap.add_argument("--unit", type=int, default=4)       # the Camera Module 3 on the second port
    ap.add_argument("--rate", type=float, default=2.0)
    ap.add_argument("--scheduling", choices=["qnx", "control"], default="qnx",
                    help="qnx applies configured `on -p` priorities; control launches every section normally")
    args = ap.parse_args()
    if args.rate <= 0:
        ap.error("--rate must be greater than zero")
    camera = ([str(HERE / "cam" / "hccam"), "-u", str(args.unit), "-r", str(args.rate)] if args.camera == "live"
              else [PY, str(HERE / "camera.py"), "--mov", args.mov, "--rate", str(args.rate)])
    # name: (priority, command). Servers first so the senders have somewhere to report, camera last.
    sections = {
        "uplink": (11, [PY, str(HERE / "uplink.py")]),
        "cloud": (11, [PY, str(HERE / "cloudlink.py")]),
        "watch": (21, [PY, str(HERE / "watchlink.py")]),
        "site": (10, [PY, str(HERE / "sitelink.py")]),       # the deployed console over Wi-Fi, idle until ~/hc-site.json exists
        "explain": (9, [PY, str(HERE / "explain.py")]),
        "infer": (7, [PY, str(HERE / "infer.py")]),          # the detector, on the Pi, lowest priority
        "model": (8, [PY, str(HERE / "model.py")]),
        "spotter": (12, [PY, str(HERE / "spotter.py")]),
        "camera": (20, camera),
    }
    on_path = shutil.which("on")
    priority_mode_active = args.scheduling == "qnx" and qnxipc.ON_QNX and bool(on_path)
    faults = FaultHistory()
    procs, info = {}, {}
    process_lock = threading.RLock()
    fault_controller = FaultController(
        procs, info, faults, process_lock, enabled=edge_fault_tests_enabled()
    )
    telemetry_sampler = ProcessTelemetrySampler()

    # Register before starting the supervised sections so every deliberate fault can be timestamped here.
    fault_server = qnxipc.Server("hc/supervisor")
    threading.Thread(target=fault_server.serve, args=(fault_controller.handle,), daemon=True).start()

    def start(name: str) -> subprocess.Popen:
        prio, cmd = sections[name]
        argv, _ = launch_command(cmd, prio, args.scheduling, on_qnx=qnxipc.ON_QNX, on_path=on_path)
        return subprocess.Popen(argv, cwd=HERE)

    for name, (prio, _) in sections.items():
        with process_lock:
            procs[name] = start(name)
            info[name] = {"pid": procs[name].pid, "generation": 1, "priority": prio, "restarts": 0,
                          "started": time.time(), "lastExit": None, "downFor": None}
        time.sleep(0.4)
    print("started", {n: p.pid for n, p in procs.items()}, "scheduler", args.scheduling,
          "QNX priorities", "active" if priority_mode_active else "inactive", flush=True)

    telemetry_lock = threading.Lock()
    telemetry_stop = threading.Event()
    telemetry_state = {"procs": {}, "resources": {
        "cpuPercent": None, "ramUsedBytes": None, "ramTotalBytes": None,
        "processCpuPercent": None, "processRamBytes": None,
        "detail": "pidin sampler has not completed a sample",
    }}

    def sample_telemetry() -> None:
        while not telemetry_stop.is_set():
            with process_lock:
                sample_input = {name: dict(process_info) for name, process_info in info.items()}
            sampled, resources = telemetry_sampler.sample(sample_input)
            with telemetry_lock:
                telemetry_state["procs"] = sampled
                telemetry_state["resources"] = resources
            telemetry_stop.wait(0.1)

    threading.Thread(
        target=sample_telemetry, name="pidin-telemetry", daemon=True
    ).start()

    # A clean stop takes every section down with it, so a restart never leaves two copies fighting over ports.
    def stop(signum, _frame):
        telemetry_stop.set()
        with process_lock:
            children = list(procs.values())
        for p in children:
            p.terminate()
        for p in children:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print(f"stopped by signal {signum}", flush=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    uplink, cloud, last_cloud = None, None, 0.0
    while True:
        for name in tuple(sections):
            with process_lock:
                p = procs[name]
                code = p.poll()
                if code is None:
                    continue
                old_pid = p.pid
                old_generation = info[name]["generation"]
                detected_wall, detected_monotonic = time.time(), time.monotonic()
                replacement = start(name)
                spawned_wall, spawned_monotonic = time.time(), time.monotonic()
                procs[name] = replacement
                fault = faults.respawned(
                    name, old_pid, replacement.pid, generation=old_generation,
                    detected_wall=detected_wall,
                    spawned_wall=spawned_wall,
                    detected_monotonic=detected_monotonic,
                    spawned_monotonic=spawned_monotonic,
                )
                i = info[name]
                i.update(pid=replacement.pid, generation=old_generation + 1,
                         restarts=i["restarts"] + 1, started=spawned_wall, lastExit=code,
                         downFor=fault["respawnMs"])
            print(f"{name} exited with {code}, restarted as pid {replacement.pid}", flush=True)
        fault_snapshot = faults.snapshot()
        legacy_crashes = [{"proc": event["proc"], "pid": event["oldPid"],
                           "t": event["requestedAt"] or event["detectedAt"]}
                          for event in fault_snapshot]
        with process_lock:
            process_snapshot = {name: dict(process_info) for name, process_info in info.items()}
        # pidin runs on a low-rate background thread. Merge only observations
        # whose PID still matches the supervisor's current child generation.
        with telemetry_lock:
            sampled_processes = telemetry_state["procs"]
            resource_snapshot = dict(telemetry_state["resources"])
        for name, current in process_snapshot.items():
            sampled = sampled_processes.get(name)
            if isinstance(sampled, dict) and sampled.get("pid") == current.get("pid"):
                for key in ("observed", "resource", "observedDetail"):
                    if key in sampled:
                        current[key] = sampled[key]
        current_resources = [entry.get("resource") for entry in process_snapshot.values()
                             if isinstance(entry.get("resource"), dict)]
        current_cpu = [item["cpuPercent"] for item in current_resources
                       if item.get("cpuPercent") is not None]
        current_ram = [item["ramBytes"] for item in current_resources
                       if item.get("ramBytes") is not None]
        resource_snapshot.update({
            "processCpuPercent": round(sum(current_cpu), 3) if current_cpu else None,
            "processRamBytes": sum(current_ram) if current_ram else None,
            "detail": "latest matching-PID pidin samples (not simultaneous): %d/%d CPU and %d/%d data-column memory observations; system totals unavailable"
                      % (len(current_cpu), len(process_snapshot), len(current_ram), len(process_snapshot)),
        })
        health = json.dumps({
            "kind": "health",
            "procs": process_snapshot,
            "t": time.time(),
            "schedulerProfile": args.scheduling,
            "qnxPrioritiesActive": priority_mode_active,
            "captureTiming": {"targetPeriodMs": round(1000.0 / args.rate, 3)},
            "resources": resource_snapshot,
            "faults": fault_snapshot,
            # Kept in its original shape for older dashboards; the richer fault timeline is authoritative.
            "crashes": legacy_crashes,
        }).encode()
        try:
            if uplink is None:
                uplink = qnxipc.Client("hc/uplink", wait=0)
            uplink.send(health)
        except OSError:
            uplink = None
        monotonic_now = time.monotonic()
        if monotonic_now - last_cloud > 15:
            last_cloud = monotonic_now
            try:
                if cloud is None:
                    cloud = qnxipc.Client("hc/cloud", wait=0)
                cloud.send(health)
            except OSError:
                cloud = None
        time.sleep(0.1)


if __name__ == "__main__":
    main()
