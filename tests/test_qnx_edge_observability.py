from __future__ import annotations

import ctypes
import importlib
import importlib.util
import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest


EDGE = Path(__file__).resolve().parents[1] / "target" / "qnx" / "edge"


def load_edge_module(monkeypatch: pytest.MonkeyPatch, name: str, tmp_path: Path | None = None):
    monkeypatch.syspath_prepend(str(EDGE))
    if tmp_path is not None:
        monkeypatch.setenv("HC_STATE", str(tmp_path / "edge-state.json"))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def load_ortlite_module():
    path = EDGE / "ortlite" / "ortlite.py"
    spec = importlib.util.spec_from_file_location("test_edge_ortlite", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_qnx_launch_path_is_explicit_and_control_never_applies_priority(monkeypatch) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    command = ["python3", "worker.py"]

    argv, active = supervisor.launch_command(
        command, 12, "qnx", on_qnx=True, on_path="/bin/on"
    )
    assert argv == ["/bin/on", "-p", "12", *command]
    assert active is True

    argv, active = supervisor.launch_command(
        command, 12, "control", on_qnx=True, on_path="/bin/on"
    )
    assert argv == command
    assert active is False

    argv, active = supervisor.launch_command(
        command, 12, "qnx", on_qnx=False, on_path="/bin/on"
    )
    assert argv == command
    assert active is False


def test_fault_history_correlates_request_and_respawn_without_claiming_recovery(monkeypatch) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    history = supervisor.FaultHistory(limit=4)

    requested = history.requested(
        "infer", 101, generation=7, fault_id="fault-1", wall=1000.0, monotonic=50.0
    )
    assert requested["state"] == "requested"
    assert requested["requestedAt"] == 1000.0
    assert requested["readyAt"] is None

    respawned = history.respawned(
        "infer",
        101,
        202,
        generation=7,
        detected_wall=1000.2,
        spawned_wall=1000.24,
        detected_monotonic=50.2,
        spawned_monotonic=50.24,
    )
    assert respawned == {
        "faultId": "fault-1",
        "proc": "infer",
        "generation": 7,
        "oldPid": 101,
        "newPid": 202,
        "requestedAt": 1000.0,
        "detectedAt": 1000.2,
        "spawnedAt": 1000.24,
        "readyAt": None,
        "firstResultAt": None,
        "respawnMs": 40.0,
        "recoveryMs": None,
        "state": "respawned",
    }
    assert history.snapshot() == [respawned]


def test_fault_history_is_bounded_and_unrequested_exit_stays_explicit(monkeypatch) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    history = supervisor.FaultHistory(limit=2)
    history.requested("model", 1, wall=1, monotonic=1)
    history.requested("cloud", 2, wall=2, monotonic=2)
    history.requested("site", 3, wall=3, monotonic=3)

    assert [event["proc"] for event in history.snapshot()] == ["cloud", "site"]
    event = history.respawned(
        "infer",
        9,
        10,
        detected_wall=9,
        spawned_wall=9.01,
        detected_monotonic=4,
        spawned_monotonic=4.01,
    )
    assert event["requestedAt"] is None
    assert event["state"] == "respawned"
    assert [item["proc"] for item in history.snapshot()] == ["site", "infer"]


def test_capture_timing_uses_bounded_monotonic_intervals(monkeypatch, tmp_path) -> None:
    uplink = load_edge_module(monkeypatch, "uplink", tmp_path)
    timing = uplink.CaptureTiming(limit=3)
    timing.set_target_period(2000)
    for observed_at in (0.0, 1.0, 3.0, 6.0, 7.0):
        timing.observe(observed_at)

    assert timing.snapshot() == {
        "targetPeriodMs": 2000.0,
        "periodP50Ms": 2000.0,
        "periodP95Ms": 2900.0,
        "periodP99Ms": 2980.0,
        "periodMaxMs": 3000.0,
        "deadlineMisses": 1,
        "deadlineMissPercent": 33.333,
        "sampleCount": 3,
    }
    assert timing.fps() == 0.5


def test_capture_deadline_fields_stay_null_until_target_is_known(monkeypatch, tmp_path) -> None:
    uplink = load_edge_module(monkeypatch, "uplink", tmp_path)
    timing = uplink.CaptureTiming()
    timing.observe(10)
    timing.observe(10.5)

    snapshot = timing.snapshot()
    assert snapshot["targetPeriodMs"] is None
    assert snapshot["deadlineMisses"] is None
    assert snapshot["deadlineMissPercent"] is None
    assert snapshot["sampleCount"] == 1


def test_compact_telemetry_excludes_viewer_and_evidence_payloads(monkeypatch, tmp_path) -> None:
    uplink = load_edge_module(monkeypatch, "uplink", tmp_path)
    with uplink.lock:
        uplink.status.update({
            "thumb": "base64-thumb",
            "full": "base64-frame",
            "spots": [{"patch": "base64-patch"}],
            "results": [{"patch": "base64-result"}],
            "frames": 7,
            "procs": {"infer": {"pid": 42}},
            "modelStats": {"checked": 3, "patch": "base64-model-evidence"},
            "resources": {"processRamBytes": 4096},
        })

    compact = uplink.telemetry_snapshot(now=123.0)
    legacy = uplink.status_snapshot(now=123.0)

    assert compact["statusSchema"] == "holy-crap.edge-telemetry"
    assert compact["statusVersion"] == 1
    assert compact["frames"] == 7
    assert compact["modelStats"] == {"checked": 3}
    assert compact["resources"] == {"processRamBytes": 4096}
    assert compact["faultTestsEnabled"] is False
    for forbidden in ("thumb", "full", "spots", "results"):
        assert forbidden not in compact
        assert forbidden in legacy


def test_pidin_parsers_use_observed_qnx_rows(monkeypatch) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    pid = 14798894
    sched = """     pid tid name                         prio STATE          cpu ExtSched
14798894   1 1018-1655/ncnn_bench          10r RUNNING          0
"""
    rmasks = """     pid tid name
14798894   1 system/bin/python3
\tRunmask     : 0x00000001
\tInherit Mask: 0x00000001
"""
    memory = """     pid tid name                         prio STATE                      code  data        stack
14798894   1 1018-1655/ncnn_bench          10r RUNNING                   6340K   48M    512K/512K
"""
    times = """     pid name                             sid  start time   utime  stime cutime cstime
14798894 1018-1655/ncnn_bench 14798894 Oct 18 17:03  0.497  0.003  0.000  0.000
"""

    assert supervisor.parse_pidin_sched(sched, pid) == (
        {"priority": 10, "policy": "SCHED_RR"}, None
    )
    assert supervisor.parse_pidin_runmask(rmasks) == ("0x00000001", None)
    assert supervisor.parse_pidin_memory(memory, pid) == (48 * 1024 * 1024, None)
    assert supervisor.parse_pidin_times(times, pid) == (0.5, None)


def test_process_sampler_is_round_robin_bounded_and_reports_parse_detail(monkeypatch) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    clock = {"value": 10.0, "cpu": 1.0}
    calls: list[list[str]] = []

    def run(argv, **kwargs):
        calls.append(argv)
        pid = int(argv[2])
        section = argv[3]
        outputs = {
            "sched": f"{pid} 1 worker 7f READY 0\n",
            "rmasks": "Runmask : 0x00000003\n",
            "memory": f"{pid} 1 worker 7f READY 12K 8M 512K/512K\n",
            "times": f"{pid} worker {pid} Oct 18 17:03 {clock['cpu']:.3f} 0.000 0.000 0.000\n",
        }
        return subprocess.CompletedProcess(argv, 0, stdout=outputs[section], stderr="")

    sampler = supervisor.ProcessTelemetrySampler(
        interval=1.0, runner=run, monotonic=lambda: clock["value"], wall=lambda: 1000.0,
    )
    processes = {"infer": {"pid": 77, "priority": 7}}
    first, resources = sampler.sample(processes)
    assert len(calls) == 4
    assert first["infer"]["observed"] == {
        "priority": 7, "policy": "SCHED_FIFO", "runmask": "0x00000003"
    }
    assert first["infer"]["resource"]["ramBytes"] == 8 * 1024 * 1024
    assert resources["processCpuPercent"] is None
    assert resources["cpuPercent"] is None
    assert resources["ramUsedBytes"] is None

    # No second command burst before the bounded interval expires.
    sampler.sample(processes)
    assert len(calls) == 4
    clock.update(value=12.0, cpu=2.0)
    _, resources = sampler.sample(processes)
    assert len(calls) == 8
    assert resources["processCpuPercent"] == 50.0

    broken = supervisor.ProcessTelemetrySampler(
        interval=1.0,
        runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="bad", stderr=""),
        monotonic=lambda: 1.0,
    )
    sampled, broken_resources = broken.sample(processes)
    assert sampled["infer"]["observed"]["priority"] is None
    assert "did not contain" in sampled["infer"]["observedDetail"]
    assert broken_resources["processRamBytes"] is None


def test_crash_allowlist_excludes_capture_and_supervision(monkeypatch, tmp_path) -> None:
    uplink = load_edge_module(monkeypatch, "uplink", tmp_path)
    processes = {
        "infer": {"pid": 10, "generation": 1},
        "model": {"pid": 11, "generation": 1},
        "camera": {"pid": 12, "generation": 1},
        "supervisor": {"pid": 13, "generation": 1},
    }

    assert uplink.crash_allowed("infer", processes) is True
    assert uplink.crash_allowed("model", processes) is True
    assert uplink.crash_allowed("camera", processes) is False
    assert uplink.crash_allowed("supervisor", processes) is False
    assert uplink.crash_allowed("site", processes) is False


def test_target_fault_gate_is_disabled_by_default_and_uplink_defaults_to_loopback(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.delenv("HC_EDGE_FAULT_TESTS", raising=False)
    monkeypatch.delenv("HC_EDGE_BIND", raising=False)
    uplink = load_edge_module(monkeypatch, "uplink", tmp_path)
    supervisor = load_edge_module(monkeypatch, "supervisor")

    assert uplink.edge_fault_tests_enabled() is False
    assert supervisor.edge_fault_tests_enabled() is False
    assert uplink.http_bind_host() == "127.0.0.1"
    assert uplink.http_bind_host({"HC_EDGE_BIND": " 192.0.2.5 "}) == "192.0.2.5"
    assert uplink.http_client_is_loopback(("127.0.0.1", 1234)) is True
    assert uplink.http_client_is_loopback(("::1", 1234, 0, 0)) is True
    assert uplink.http_client_is_loopback(("192.0.2.5", 1234)) is False
    assert uplink.http_client_is_loopback(("not-an-address", 1234)) is False


def test_uplink_crash_endpoint_rejects_non_loopback_peer_before_fault_work(
    monkeypatch, tmp_path
) -> None:
    uplink = load_edge_module(monkeypatch, "uplink", tmp_path)
    handler = uplink.Http.__new__(uplink.Http)
    handler.path = "/crash?proc=infer"
    handler.client_address = ("192.0.2.5", 4321)
    responses: list[tuple[int, dict]] = []
    handler._send = lambda code, body: responses.append((code, body))
    monkeypatch.setattr(uplink, "edge_fault_tests_enabled", lambda: True)
    monkeypatch.setattr(
        uplink,
        "request_fault",
        lambda *_args: pytest.fail("non-loopback request reached fault work"),
    )

    handler.do_POST()

    assert responses == [
        (403, {"accepted": False, "error": "fault endpoint is loopback-only"})
    ]


def test_uplink_forwards_pid_and_generation_without_signalling(monkeypatch, tmp_path) -> None:
    uplink = load_edge_module(monkeypatch, "uplink", tmp_path)
    sent: list[dict] = []

    class FakeClient:
        def __init__(self, name, wait):
            assert (name, wait) == ("hc/supervisor", 0)

        def send(self, payload):
            sent.append(json.loads(payload))
            return json.dumps({
                "accepted": True,
                "process": "infer",
                "faultId": "fault-1",
                "pid": 77,
                "generation": 9,
                "killed": "infer",
            }).encode()

        def close(self):
            pass

    monkeypatch.setattr(uplink.qnxipc, "Client", FakeClient)
    reply = uplink.request_fault("infer", 77, 9)

    assert sent == [{
        "kind": "fault-request",
        "proc": "infer",
        "expectedPid": 77,
        "generation": 9,
    }]
    assert reply["accepted"] is True
    assert reply["faultId"] == "fault-1"


class FakeChild:
    def __init__(self, pid: int):
        self.pid = pid
        self.signals: list[int] = []

    def poll(self):
        return None

    def send_signal(self, signum: int) -> None:
        self.signals.append(signum)


def make_fault_controller(supervisor, *, enabled=True, ids=("fault-a", "fault-b")):
    infer = FakeChild(101)
    model = FakeChild(202)
    procs = {"infer": infer, "model": model, "camera": FakeChild(303)}
    info = {
        "infer": {"pid": 101, "generation": 4},
        "model": {"pid": 202, "generation": 8},
        "camera": {"pid": 303, "generation": 2},
    }
    id_values = iter(ids)
    history = supervisor.FaultHistory(limit=8)
    controller = supervisor.FaultController(
        procs, info, history, threading.RLock(), enabled=enabled,
        id_factory=lambda: next(id_values),
    )
    return controller, history, procs


def test_supervisor_fault_gate_fails_closed_without_signalling(monkeypatch) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    controller, history, procs = make_fault_controller(supervisor, enabled=False)

    reply = controller.request("infer", 101, 4)

    assert reply["accepted"] is False
    assert "disabled" in reply["error"]
    assert procs["infer"].signals == []
    assert history.snapshot() == []


@pytest.mark.parametrize(
    ("process", "pid", "generation"),
    [
        ("infer", 999, 4),
        ("infer", 101, 3),
        ("camera", 303, 2),
        ("supervisor", 1, 1),
    ],
)
def test_supervisor_rejects_stale_identity_and_non_crashable_processes(
    monkeypatch, process, pid, generation
) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    controller, history, procs = make_fault_controller(supervisor)

    reply = controller.request(process, pid, generation)

    assert reply["accepted"] is False
    assert all(child.signals == [] for child in procs.values())
    assert history.snapshot() == []


def test_supervisor_owns_exact_child_signal_and_fault_ids_correlate(monkeypatch) -> None:
    supervisor = load_edge_module(monkeypatch, "supervisor")
    controller, history, procs = make_fault_controller(supervisor)

    first = controller.request("infer", 101, 4)
    second = controller.request("model", 202, 8)

    assert first == {
        "accepted": True,
        "process": "infer",
        "faultId": "fault-a",
        "pid": 101,
        "generation": 4,
        "killed": "infer",
    }
    assert second["faultId"] == "fault-b"
    assert first["faultId"] != second["faultId"]
    assert procs["infer"].signals == [signal.SIGKILL]
    assert procs["model"].signals == [signal.SIGKILL]
    assert procs["camera"].signals == []

    event = history.respawned(
        "infer", 101, 111, generation=4,
        detected_wall=100.0, spawned_wall=100.02,
        detected_monotonic=50.0, spawned_monotonic=50.02,
    )
    assert event["faultId"] == "fault-a"
    assert event["generation"] == 4
    assert event["newPid"] == 111
    assert event["state"] == "respawned"


def test_ortlite_serializes_concurrent_runs() -> None:
    ortlite = load_ortlite_module()

    class FakeLibrary:
        def __init__(self):
            self.guard = threading.Lock()
            self.active = 0
            self.max_active = 0

        def hc_run(self, _handle, _input, _shape, _ndim, output, _max_out, out_shape, out_ndim):
            with self.guard:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            time.sleep(0.02)
            np.ctypeslib.as_array((ctypes.c_float * 1).from_address(output))[0] = 1.0
            out_shape[0] = 1
            out_ndim._obj.value = 1
            with self.guard:
                self.active -= 1
            return 1

        def hc_close(self, _handle):
            return None

    session = ortlite.Session.__new__(ortlite.Session)
    session._run_lock = threading.Lock()
    session.lib = FakeLibrary()
    session.h = 1
    session.out = np.empty(8, np.float32)
    barrier = threading.Barrier(6)
    results: list[np.ndarray] = []

    def run_once() -> None:
        barrier.wait()
        results.append(session.run(np.zeros((1, 1), np.float32)))

    threads = [threading.Thread(target=run_once) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert session.lib.max_active == 1
    assert len(results) == 6
    assert all(result.tolist() == [1.0] for result in results)
    session.h = None


def test_model_timing_window_is_bounded_and_keeps_actual_last_sample(monkeypatch) -> None:
    model = load_edge_module(monkeypatch, "model")
    timing = model.TimingWindow(limit=3)
    for milliseconds in (10.0, 40.0, 20.0, 15.0):
        timing.add(milliseconds)

    assert timing.snapshot() == {
        "sampleCount": 3,
        "lastMs": 15.0,
        "p50Ms": 20.0,
        "p95Ms": 38.0,
        "p99Ms": 39.6,
        "maxMs": 40.0,
    }
