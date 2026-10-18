from __future__ import annotations

import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from holy_crap_simlab.api import create_app
from holy_crap_simlab.qnx_runner import (
    QnxRunner,
    QnxRunnerConfig,
    QnxRunnerError,
    normalize_edge_crash_response,
    normalize_edge_status,
    normalize_edge_status_payload,
)
from holy_crap_simlab.service import QnxFaultTestError

FAULT_HEADERS = {"X-Holy-Crap-Fault-Test": "confirm"}


@pytest.fixture(autouse=True)
def _edge_env_guard(monkeypatch) -> None:
    monkeypatch.setenv("QNX_EXECUTOR_MODE", "disabled")
    monkeypatch.setenv("QNX_EDGE_FAULT_TESTS", "0")


def make_config(**overrides: object) -> QnxRunnerConfig:
    values: dict[str, object] = {
        "mode": "probe",
        "ssh_alias": "qnxpi",
        "ssh_timeout": 20,
        "command_timeout": 30,
        "edge_status_timeout": 5,
        "edge_fault_tests": False,
    }
    values.update(overrides)
    return QnxRunnerConfig(**values)


class FakeRunner:
    """Injected subprocess runner: records argv, scripts responses, never touches the network."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.handler: Callable[[list[str]], subprocess.CompletedProcess] | None = None

    def __call__(
        self, argv: list[str], timeout: float | None = None
    ) -> subprocess.CompletedProcess:
        argv = [str(part) for part in argv]
        self.calls.append(argv)
        if self.handler is not None:
            return self.handler(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def ssh_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[0] == "ssh"]


def edge_status_payload(**overrides: object) -> dict:
    payload = {
        "statusSchema": "holy-crap.edge-telemetry",
        "statusVersion": 1,
        "faultTestsEnabled": False,
        "nativeIpc": True,
        "source": "replay",
        "frames": 120,
        "fps": 2.0,
        "dropped": 0,
        "warm": True,
        "lastFrame": 1769000000.0,
        "now": 1769000002.5,
        "procs": {
            "infer": {
                "pid": 101,
                "priority": 7,
                "restarts": 1,
                "started": 1768999900.0,
                "lastExit": 1,
                "downFor": 120.5,
                "ready": True,
            },
            "camera": {
                "pid": 102,
                "priority": 20,
                "restarts": 0,
                "started": 1768999901.0,
                "lastExit": None,
            },
        },
        "schedulerProfile": "qnx",
        "qnxPrioritiesActive": True,
        "captureTiming": {
            "targetPeriodMs": 500.0,
            "periodP50Ms": 502.0,
            "periodP95Ms": 510.0,
            "periodP99Ms": 515.0,
            "periodMaxMs": 522.0,
            "deadlineMisses": 2,
            "deadlineMissPercent": 1.7,
            "sampleCount": 118,
        },
        "crashes": [{"proc": "infer", "pid": 100, "t": 1768999800.0}],
        "resources": {
            "cpuPercent": 33.2,
            "ramUsedBytes": 123456,
            "ramTotalBytes": 456789,
        },
    }
    payload.update(overrides)
    return payload


def runtime_app(
    tmp_path: Path, scenario_directory: Path, fake: FakeRunner, **config_overrides: object
) -> TestClient:
    runner = QnxRunner(make_config(**config_overrides), subprocess_runner=fake)
    return TestClient(
        create_app(tmp_path / "simlab-edge", scenario_directory, qnx_runner=runner)
    )


def serve(fake: FakeRunner, stdout: str, returncode: int = 0, stderr: str = "") -> None:
    fake.handler = lambda argv: subprocess.CompletedProcess(
        argv, returncode, stdout=stdout, stderr=stderr
    )


def serve_edge_status_and_crash(
    fake: FakeRunner,
    crash_payload: object,
    *,
    crash_returncode: int = 0,
) -> None:
    status_output = json.dumps(edge_status_payload(faultTestsEnabled=True))
    crash_output = (
        crash_payload if isinstance(crash_payload, str) else json.dumps(crash_payload)
    )

    def respond(argv: list[str]) -> subprocess.CompletedProcess:
        source = argv[-1]
        if "/telemetry" in source:
            return subprocess.CompletedProcess(argv, 0, stdout=status_output, stderr="")
        assert "/crash" in source
        return subprocess.CompletedProcess(
            argv, crash_returncode, stdout=crash_output, stderr=""
        )

    fake.handler = respond


# --- GET /api/v1/system/qnx/runtime -------------------------------------------


def test_runtime_disabled_returns_not_configured_without_network(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    with runtime_app(tmp_path, scenario_directory, fake, mode="disabled") as client:
        response = client.get("/api/v1/system/qnx/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["runtime_scope"] == "edge_stream"
    assert body["status"] == "not_configured"
    assert body["capture"] is None
    assert body["processes"] == []
    assert body["resources"] is None
    assert body["latest_fault"] is None
    assert body["fault_tests_enabled"] is False
    assert body["target_fault_tests_enabled"] is None
    assert "disabled" in body["detail"]
    assert fake.calls == []


def test_runtime_unreachable_ssh_returns_typed_unreachable(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    serve(fake, "", returncode=255, stderr="ssh: connect to host qnxpi failed: no route\n")
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        response = client.get("/api/v1/system/qnx/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unreachable"
    assert "no route" in body["detail"]
    assert body["capture"] is None
    assert body["processes"] == []
    assert len(fake.ssh_calls()) == 1


def test_runtime_normalizes_valid_status_and_keeps_observed_scheduling_null(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    serve(fake, json.dumps(edge_status_payload()))
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        response = client.get("/api/v1/system/qnx/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["runtime_scope"] == "edge_stream"
    assert body["native_ipc"] is True
    assert body["source_mode"] == "replay"
    assert body["scheduler_profile"] == "qnx"
    assert body["qnx_priorities_active"] is True
    assert body["target_fault_tests_enabled"] is False

    capture = body["capture"]
    assert capture["frames"] == 120
    assert capture["fps"] == 2.0
    assert capture["dropped"] == 0
    assert capture["warm"] is True
    assert capture["last_frame_age_s"] == pytest.approx(2.5)
    assert capture["target_period_ms"] == 500.0
    assert capture["period_p50_ms"] == 502.0
    assert capture["period_p99_ms"] == 515.0
    assert capture["period_max_ms"] == 522.0
    assert capture["deadline_misses"] == 2
    assert capture["deadline_miss_percent"] == 1.7
    assert capture["sample_count"] == 118

    by_name = {process["name"]: process for process in body["processes"]}
    infer = by_name["infer"]
    assert infer["pid"] == 101
    # The supervisor's configured priority is reported; observed scheduling
    # fields remain honest nulls until target inspection proves them.
    assert infer["configured_priority"] == 7
    assert infer["observed_priority"] is None
    assert infer["scheduling_policy"] is None
    assert infer["runmask"] is None
    assert infer["restarts"] == 1
    assert infer["last_exit"] == 1
    assert infer["respawn_ms"] == 120.5
    assert infer["ready"] is True
    started = datetime.fromisoformat(infer["started_at"])
    assert started == datetime.fromtimestamp(1768999900.0, timezone.utc)
    assert by_name["camera"]["configured_priority"] == 20
    assert by_name["camera"]["last_exit"] is None
    assert by_name["camera"]["observed_priority"] is None

    resources = body["resources"]
    assert resources["source"] == "qnx"
    assert resources["cpu_percent"] == 33.2
    assert resources["ram_used_bytes"] == 123456
    assert resources["ram_total_bytes"] == 456789

    fault = body["latest_fault"]
    assert fault["process"] == "infer"
    assert fault["old_pid"] == 100
    assert fault["state"] == "requested"
    assert fault["ready_at"] is None
    assert fault["recovery_ms"] is None

    target = body["target"]
    assert target["executor"] == "qnx"
    assert target["hostname"] == "qnxpi"
    assert target["verified"] is False
    assert body["fault_tests_enabled"] is False
    assert "not the clip-assessment worker" in body["detail"]


@pytest.mark.parametrize(
    ("host_gate", "target_gate", "effective"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
def test_runtime_fault_gate_requires_host_and_target(
    tmp_path: Path,
    scenario_directory: Path,
    host_gate: bool,
    target_gate: bool,
    effective: bool,
) -> None:
    fake = FakeRunner()
    serve(fake, json.dumps(edge_status_payload(faultTestsEnabled=target_gate)))
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=host_gate
    ) as client:
        body = client.get("/api/v1/system/qnx/runtime").json()

    assert body["target_fault_tests_enabled"] is target_gate
    assert body["fault_tests_enabled"] is effective


def test_runtime_legacy_status_without_target_gate_fails_closed(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    payload = edge_status_payload()
    payload.pop("faultTestsEnabled")
    serve(fake, json.dumps(payload))
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        body = client.get("/api/v1/system/qnx/runtime").json()

    assert body["target_fault_tests_enabled"] is None
    assert body["fault_tests_enabled"] is False


def test_runtime_keeps_unreported_restart_counts_null(
    tmp_path: Path, scenario_directory: Path
) -> None:
    payload = edge_status_payload()
    payload["procs"]["infer"].pop("restarts")
    fake = FakeRunner()
    serve(fake, json.dumps(payload))
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        body = client.get("/api/v1/system/qnx/runtime").json()

    infer = next(
        process for process in body["processes"] if process["name"] == "infer"
    )
    assert infer["restarts"] is None
    assert body["status"] == "ready"


def test_runtime_malformed_restart_count_is_null_and_marks_snapshot_partial(
    tmp_path: Path, scenario_directory: Path
) -> None:
    payload = edge_status_payload()
    payload["procs"]["infer"]["restarts"] = "zero"
    fake = FakeRunner()
    serve(fake, json.dumps(payload))
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        body = client.get("/api/v1/system/qnx/runtime").json()

    infer = next(
        process for process in body["processes"] if process["name"] == "infer"
    )
    assert infer["restarts"] is None
    assert body["status"] == "partial"
    assert "normalization warnings" in body["detail"]


@pytest.mark.parametrize("missing_key", ["source", "frames", "fps", "dropped"])
def test_runtime_missing_essential_field_is_partial(
    tmp_path: Path, scenario_directory: Path, missing_key: str
) -> None:
    payload = edge_status_payload()
    payload.pop(missing_key)
    fake = FakeRunner()
    serve(fake, json.dumps(payload))
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        body = client.get("/api/v1/system/qnx/runtime").json()

    assert body["status"] == "partial"
    assert "missing essential fields" in body["detail"]


def test_runtime_exposes_target_schema_correlation_model_timing_and_nested_resources(
    tmp_path: Path, scenario_directory: Path
) -> None:
    payload = edge_status_payload()
    payload.pop("resources")
    payload.update(
        {
            "statusSchema": "holy-crap.edge-status",
            "statusVersion": 2,
            "correlation": {
                "jobId": "clip-job-example",
                "clipSha256": "a" * 64,
                "modelSha256": "b" * 64,
                "workerSha256": "c" * 64,
            },
            "modelStats": {
                "inferenceTiming": {
                    "sampleCount": 24,
                    "lastMs": 12.5,
                    "p50Ms": 10.0,
                    "p95Ms": 18.0,
                    "p99Ms": 20.0,
                    "maxMs": 22.0,
                },
                "resources": {
                    "cpuPercent": 21.0,
                    "ramUsedBytes": 654321,
                },
            },
        }
    )
    fake = FakeRunner()
    serve(fake, json.dumps(payload))
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        body = client.get("/api/v1/system/qnx/runtime").json()

    assert body["status"] == "ready"
    assert body["target_status_schema"] == "holy-crap.edge-status"
    assert body["target_status_version"] == 2
    assert body["correlation"] == {
        "job_id": "clip-job-example",
        "clip_sha256": "a" * 64,
        "model_sha256": "b" * 64,
        "worker_sha256": "c" * 64,
    }
    assert body["model_timing"]["sample_count"] == 24
    assert body["model_timing"]["last_ms"] == 12.5
    assert body["model_timing"]["p50_ms"] == 10.0
    assert body["model_timing"]["p95_ms"] == 18.0
    assert body["model_timing"]["p99_ms"] == 20.0
    assert body["model_timing"]["max_ms"] == 22.0
    assert body["resources"]["cpu_percent"] == 21.0
    assert body["resources"]["ram_used_bytes"] == 654321


def test_runtime_reports_observed_scheduling_separately_from_configured(
    tmp_path: Path, scenario_directory: Path
) -> None:
    payload = edge_status_payload()
    payload["procs"]["infer"]["observed"] = {
        "priority": 7,
        "policy": "SCHED_FIFO",
        "runmask": "0x3",
    }
    payload["procs"]["infer"]["observedDetail"] = "pidin observed"
    fake = FakeRunner()
    serve(fake, json.dumps(payload))
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        body = client.get("/api/v1/system/qnx/runtime").json()

    infer = next(process for process in body["processes"] if process["name"] == "infer")
    assert infer["configured_priority"] == 7
    assert infer["observed_priority"] == 7
    assert infer["scheduling_policy"] == "SCHED_FIFO"
    assert infer["runmask"] == "0x3"
    assert infer["observation_detail"] == "pidin observed"


@pytest.mark.parametrize(
    "stdout, expected_detail",
    [
        ("{not json", "not valid JSON"),
        ("[]", "not a JSON object"),
        ("", "empty output"),
        ("{}", "missing expected fields"),
        (json.dumps({"procs": [], "frames": 3}), "missing expected fields"),
    ],
)
def test_runtime_malformed_target_json_returns_partial_not_500(
    tmp_path: Path, scenario_directory: Path, stdout: str, expected_detail: str
) -> None:
    fake = FakeRunner()
    serve(fake, stdout)
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        response = client.get("/api/v1/system/qnx/runtime")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert expected_detail in body["detail"]
    assert body["schema_version"] == 1


def test_runtime_polling_never_triggers_fault_tests(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    serve(fake, json.dumps(edge_status_payload()))
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        response = client.get("/api/v1/system/qnx/runtime")

    assert response.status_code == 200
    joined = " ".join(" ".join(call) for call in fake.calls)
    assert "/crash" not in joined
    assert len(fake.ssh_calls()) == 1


# --- POST /api/v1/system/qnx/fault-tests/{process_name} ------------------------


def test_fault_test_disabled_fails_closed_without_subprocess(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    with runtime_app(tmp_path, scenario_directory, fake) as client:
        response = client.post(
            "/api/v1/system/qnx/fault-tests/infer", headers=FAULT_HEADERS
        )

    assert response.status_code == 403
    assert "disabled" in response.json()["error"]["message"]
    assert fake.calls == []


@pytest.mark.parametrize(
    "process_name",
    ["camera", "watch", "supervisor", "infer; rm -rf /", "1"],
)
def test_fault_test_invalid_process_rejected_before_any_subprocess(
    tmp_path: Path, scenario_directory: Path, process_name: str
) -> None:
    fake = FakeRunner()
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        response = client.post(
            "/api/v1/system/qnx/fault-tests/%s" % process_name,
            headers=FAULT_HEADERS,
        )

    assert response.status_code == 422
    assert "not allowed" in response.json()["error"]["message"]
    assert fake.calls == []


def test_fault_test_path_like_process_rejected_before_any_subprocess(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        response = client.post(
            "/api/v1/system/qnx/fault-tests/../infer", headers=FAULT_HEADERS
        )

    # The router itself refuses path traversal; either way no subprocess runs.
    assert response.status_code in (404, 422)
    assert fake.calls == []


def test_fault_test_allowlisted_uses_safe_argv_and_normalizes_response(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    serve_edge_status_and_crash(
        fake, {"accepted": True, "killed": "infer", "pid": 101}
    )
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        response = client.post(
            "/api/v1/system/qnx/fault-tests/infer", headers=FAULT_HEADERS
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["process"] == "infer"
    assert body["accepted"] is True
    assert body["pid"] == 101

    calls = fake.ssh_calls()
    assert len(calls) == 2
    call = calls[1]
    assert call[:5] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
    assert call[5] == "qnxpi"
    assert call[6] == "/system/bin/python3"
    assert call[7] == "-c"
    code = call[8]
    assert "crash?proc=infer" in code
    assert 'method="POST"' in code
    assert "urlopen" in code
    assert "http://127.0.0.1:8088/crash" in code
    for part in call:
        assert isinstance(part, str)
        assert "shell" not in part.lower()


def test_fault_test_target_refusal_returns_safe_error(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    serve_edge_status_and_crash(
        fake, {"accepted": False, "error": "unknown process"}, crash_returncode=2
    )
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        response = client.post(
            "/api/v1/system/qnx/fault-tests/infer", headers=FAULT_HEADERS
        )

    assert response.status_code == 502
    assert "unknown process" in response.json()["error"]["message"]
    assert len(fake.ssh_calls()) == 2


def test_fault_test_unrecognized_target_response_normalizes_to_rejection(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    serve_edge_status_and_crash(fake, "not json")
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        response = client.post(
            "/api/v1/system/qnx/fault-tests/infer", headers=FAULT_HEADERS
        )

    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert "unrecognized target response" in body["detail"]


def test_fault_test_requires_deliberate_action_header_before_runner(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        response = client.post("/api/v1/system/qnx/fault-tests/infer")

    assert response.status_code == 403
    assert "X-Holy-Crap-Fault-Test" in response.json()["error"]["message"]
    assert fake.calls == []


def test_fault_test_requires_target_gate_before_crash(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    serve(fake, json.dumps(edge_status_payload(faultTestsEnabled=False)))
    with runtime_app(
        tmp_path, scenario_directory, fake, edge_fault_tests=True
    ) as client:
        response = client.post(
            "/api/v1/system/qnx/fault-tests/infer", headers=FAULT_HEADERS
        )

    assert response.status_code == 403
    assert "disabled on the QNX target" in response.json()["error"]["message"]
    assert len(fake.ssh_calls()) == 1
    assert "/telemetry" in fake.ssh_calls()[0][-1]


# --- runner-level normalization and argv ---------------------------------------


def test_edge_status_fetch_is_argv_only_and_target_localhost(tmp_path: Path) -> None:
    fake = FakeRunner()
    serve(fake, json.dumps(edge_status_payload()))
    runner = QnxRunner(make_config(), subprocess_runner=fake)

    outcome = runner.edge_status()

    assert json.loads(outcome.output)["nativeIpc"] is True
    call = fake.ssh_calls()[0]
    assert call[0] == "ssh"
    assert call[5] == "qnxpi"
    assert call[6] == "/system/bin/python3"
    assert call[7] == "-c"
    assert "http://127.0.0.1:8088/telemetry" in call[8]
    assert "urllib" in call[8]
    assert "Content-Length" in call[8]
    assert "1048577" in call[8]


@pytest.mark.parametrize(
    ("content_length", "body", "expected"),
    [
        (str(1024 * 1024 + 1), b"", "Content-Length exceeds limit"),
        ("10", b"{}", "truncated edge telemetry body"),
    ],
)
def test_edge_status_remote_reader_rejects_oversized_or_truncated_responses(
    monkeypatch, capsys, content_length: str, body: bytes, expected: str
) -> None:
    class Response:
        headers = {"Content-Length": content_length}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit: int) -> bytes:
            assert limit == 1024 * 1024 + 1
            return body

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    runner = QnxRunner(make_config())

    with pytest.raises(SystemExit) as excinfo:
        exec(runner._edge_status_remote_code(), {})

    assert excinfo.value.code == 1
    assert expected in capsys.readouterr().err


def test_runtime_without_live_pid_or_contract_is_partial() -> None:
    payload = edge_status_payload()
    payload.pop("statusSchema")
    payload.pop("statusVersion")
    for process in payload["procs"].values():
        process["pid"] = None

    response = normalize_edge_status_payload(
        payload, ssh_alias="qnxpi", fault_tests_enabled=True
    )

    assert response.status.value == "partial"
    assert "live process PID" in response.detail
    assert "status schema" in response.detail
    assert response.fault_tests_enabled is False


def test_runtime_splits_success_and_failure_model_outcomes() -> None:
    payload = edge_status_payload()
    payload["modelStats"] = {
        "checked": 12,
        "unreachable": 3,
        "workerErrors": 2,
        "evicted": 4,
        "dropped": 1,
        "successfulInferenceTiming": {"sampleCount": 12, "p50Ms": 8.5},
        "failedAttemptTiming": {"sampleCount": 5, "p50Ms": 4001.0},
    }

    response = normalize_edge_status_payload(
        payload, ssh_alias="qnxpi", fault_tests_enabled=False
    )

    timing = response.model_timing
    assert timing is not None
    assert timing.sample_count == 12
    assert timing.p50_ms == 8.5
    assert timing.failed_sample_count == 5
    assert timing.failed_p50_ms == 4001.0
    assert timing.checked == 12
    assert timing.unreachable == 3
    assert timing.worker_errors == 2
    assert timing.evicted == 4
    assert timing.dropped == 1


def test_edge_status_nonzero_exit_raises_with_detail(tmp_path: Path) -> None:
    fake = FakeRunner()
    serve(fake, "", returncode=1, stderr="SIMLAB_EDGE_FETCH_ERROR: ConnectionRefusedError: refused\n")
    runner = QnxRunner(make_config(), subprocess_runner=fake)

    with pytest.raises(QnxRunnerError, match="ConnectionRefusedError"):
        runner.edge_status()


def test_normalize_edge_status_never_raises(tmp_path: Path) -> None:
    response = normalize_edge_status(
        "{broken", ssh_alias="qnxpi", fault_tests_enabled=False
    )
    assert response.status.value == "partial"
    assert "not valid JSON" in response.detail

    payload = normalize_edge_status_payload(
        ["not", "an", "object"], ssh_alias="qnxpi", fault_tests_enabled=True
    )
    assert payload.status.value == "partial"
    assert payload.fault_tests_enabled is False
    assert payload.target_fault_tests_enabled is None


def test_normalize_edge_crash_response_never_raises() -> None:
    accepted = normalize_edge_crash_response(
        "infer", {"killed": "infer", "pid": 101}, '{"killed": "infer", "pid": 101}'
    )
    assert accepted.accepted is True
    assert accepted.process == "infer"
    assert accepted.pid == 101

    explicit_refusal = normalize_edge_crash_response(
        "infer",
        {
            "accepted": False,
            "killed": "infer",
            "pid": 101,
            "error": "supervisor rejected stale generation",
        },
    )
    assert explicit_refusal.accepted is False
    assert explicit_refusal.pid is None
    assert "stale generation" in (explicit_refusal.detail or "")

    refused = normalize_edge_crash_response("infer", {"error": "unknown process"})
    assert refused.accepted is False
    assert "unknown process" in (refused.detail or "")

    garbage = normalize_edge_crash_response("infer", None, "not json")
    assert garbage.accepted is False
    assert "unrecognized target response" in (garbage.detail or "")


@pytest.mark.parametrize(
    "payload, expected_detail",
    [
        ({"killed": "model", "pid": 101}, "instead of"),
        ({"killed": "infer", "pid": 0}, "positive pid"),
        ({"killed": "infer", "pid": -1}, "positive pid"),
        ({"killed": "infer", "pid": True}, "positive pid"),
        ({"killed": "infer", "pid": "101"}, "positive pid"),
    ],
)
def test_normalize_edge_crash_requires_exact_process_and_positive_pid(
    payload: dict, expected_detail: str
) -> None:
    response = normalize_edge_crash_response("infer", payload, json.dumps(payload))

    assert response.process == "infer"
    assert response.accepted is False
    assert response.pid is None
    assert expected_detail in (response.detail or "")


def test_service_fault_test_checks_allowlist_before_configuration(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeRunner()
    with runtime_app(
        tmp_path, scenario_directory, fake, mode="disabled", edge_fault_tests=False
    ) as client:
        service = client.app.state.service
        with pytest.raises(QnxFaultTestError) as excinfo:
            service.qnx_fault_test("camera")
    assert excinfo.value.status_code == 422
    assert fake.calls == []


def test_runner_edge_crash_rejects_disabled_gate_before_ssh() -> None:
    fake = FakeRunner()
    runner = QnxRunner(make_config(edge_fault_tests=False), subprocess_runner=fake)

    with pytest.raises(QnxRunnerError, match="fault tests are disabled"):
        runner.edge_crash("infer")

    assert fake.calls == []


# --- configuration from environment -------------------------------------------


def test_config_env_edge_settings() -> None:
    config = QnxRunnerConfig.from_env({})
    assert config.edge_status_url == "http://127.0.0.1:8088/telemetry"
    assert config.edge_crash_url == "http://127.0.0.1:8088/crash"
    assert config.edge_status_timeout == 10
    assert config.edge_fault_tests is False

    config = QnxRunnerConfig.from_env(
        {
            "QNX_EDGE_STATUS_TIMEOUT": "7",
            "QNX_EDGE_FAULT_TESTS": "1",
        }
    )
    assert config.edge_status_timeout == 7
    assert config.edge_fault_tests is True

    for value in ("true", "yes", "on", " 1", "1 ", "01"):
        config = QnxRunnerConfig.from_env({"QNX_EDGE_FAULT_TESTS": value})
        assert config.edge_fault_tests is False

    with pytest.raises(QnxRunnerError, match="QNX_EDGE_STATUS_URL"):
        QnxRunnerConfig.from_env(
            {"QNX_EDGE_STATUS_URL": "http://example.com/status"}
        )
