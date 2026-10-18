from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import pytest

from holy_crap_simlab.qnx_runner import (
    DEFAULT_SUBMIT_JOB,
    QnxRunner,
    QnxRunnerConfig,
    QnxRunnerError,
    QnxProbeReport,
)

WORKER = Path(__file__).resolve().parents[1] / "target" / "qnx" / "simlab_probe.py"
CLIP_WRAPPER = (
    Path(__file__).resolve().parents[1] / "target" / "qnx" / "clip_assessment_worker.py"
)
RUN_ID = "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c"
MODEL_NAME = "pen-anomaly"
SCENARIO_NAME = "healthy-100"

MODEL_BYTES = b"\x00simlab placeholder model artifact\xff"
SCENARIO_DOC = {"schema_version": 1, "id": "healthy-100", "seed": 104729}


class FakeRunner:
    """Injected subprocess runner: records argv, scripts responses, never touches the network."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.handlers: dict[str, Callable[[list[str]], subprocess.CompletedProcess]] = {}
        self.receipt_bytes: bytes | None = None

    def on(self, first: str, handler: Callable[[list[str]], subprocess.CompletedProcess]) -> None:
        self.handlers[first] = handler

    def __call__(
        self, argv: list[str], timeout: float | None = None
    ) -> subprocess.CompletedProcess:
        argv = [str(part) for part in argv]
        self.calls.append(argv)
        first = argv[0]
        if first in self.handlers:
            return self.handlers[first](argv)
        if first == "scp" and len(argv) >= 2 and argv[-2].endswith("/receipt.json"):
            if self.receipt_bytes is not None:
                Path(argv[-1]).write_bytes(self.receipt_bytes)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
            return subprocess.CompletedProcess(
                argv, 1, stdout="", stderr="scp: receipt.json: No such file"
            )
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def ssh_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[0] == "ssh"]

    def scp_calls(self) -> list[list[str]]:
        return [call for call in self.calls if call[0] == "scp"]


def make_config(tmp_path: Path, **overrides: object) -> QnxRunnerConfig:
    values: dict[str, object] = {
        "mode": "probe",
        "ssh_alias": "qnxpi",
        "ssh_hostname": None,
        "ssh_timeout": 20,
        "command_timeout": 30,
        "submit_job": tmp_path / "submit-job.py",
        "remote_root": "/data/home/qnxuser/simlab-runs",
        "remote_python": "/system/bin/python3",
        "runner_app_dir": "/data/home/qnxuser/qnx-runner-app",
        "runner_spool": "/data/home/qnxuser/qnx-runner",
        "job_timeout": 60,
        "wait_timeout": 120,
        "worker_path": WORKER,
    }
    values.update(overrides)
    return QnxRunnerConfig(**values)


def write_request(tmp_path: Path, **changes: object) -> tuple[Path, dict]:
    request = {
        "run_id": RUN_ID,
        "model": {"name": MODEL_NAME, "sha256": hashlib.sha256(MODEL_BYTES).hexdigest()},
        "scenario": {
            "name": SCENARIO_NAME,
            "sha256": hashlib.sha256(
                json.dumps(SCENARIO_DOC).encode("utf-8")
            ).hexdigest(),
        },
    }
    request.update(changes)
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    return path, request


def stage_files(tmp_path: Path) -> tuple[Path, Path]:
    model = tmp_path / "model.bin"
    model.write_bytes(MODEL_BYTES)
    scenario = tmp_path / "scenario.json"
    scenario.write_text(json.dumps(SCENARIO_DOC), encoding="utf-8")
    return model, scenario


def run_worker(tmp_path: Path, request_path: Path, result: Path) -> subprocess.CompletedProcess:
    model, scenario = stage_files(tmp_path)
    return subprocess.run(
        [
            sys.executable,
            str(WORKER),
            "--request",
            str(request_path),
            "--scenario",
            str(scenario),
            "--model",
            str(model),
            "--result",
            str(result),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def valid_receipt(**changes: object) -> dict:
    receipt = {
        "schema_version": 1,
        "run_id": RUN_ID,
        "model": {
            "name": MODEL_NAME,
            "sha256": hashlib.sha256(MODEL_BYTES).hexdigest(),
            "size_bytes": len(MODEL_BYTES),
        },
        "scenario": {
            "name": SCENARIO_NAME,
            "sha256": hashlib.sha256(json.dumps(SCENARIO_DOC).encode("utf-8")).hexdigest(),
            "size_bytes": len(json.dumps(SCENARIO_DOC).encode("utf-8")),
        },
        "platform": {
            "system": "QNX",
            "machine": "aarch64le",
            "release": "8.0.0",
            "python_version": "3.14.0",
        },
        "started_at": "2026-10-17T20:00:00+00:00",
        "finished_at": "2026-10-17T20:00:01+00:00",
        "inference_performed": False,
        "inference_reason": "No QNX inference runtime is installed or configured.",
    }
    receipt.update(changes)
    return receipt


def configured_runner(tmp_path: Path, fake: FakeRunner, **overrides: object) -> QnxRunner:
    return QnxRunner(make_config(tmp_path, **overrides))


def test_clip_worker_receipt_parses_target_identity_and_live_telemetry(tmp_path: Path) -> None:
    worker_path = "/data/home/qnxuser/holy-crap/clip-worker.py"
    manifest_path = "/data/home/qnxuser/holy-crap/deployment.json"
    manifest = {
        "schema_version": 1,
        "contract": "holy-crap.clip-assessment.v1",
        "platform": "QNX",
        "worker_path": worker_path,
        "worker_sha256": "a" * 64,
    }
    manifest_bytes = (json.dumps(manifest) + "\n").encode()
    job_id = "clip-job-8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c"
    sample = {
        "captured_at": "2026-10-18T12:00:00+00:00",
        "source": "qnx",
        "cpu_percent": 42.5,
        "ram_used_bytes": 1024,
        "ram_total_bytes": 8192,
        "process_cpu_percent": 17.0,
        "process_ram_bytes": 512,
        "detail": "fake target sample",
    }
    envelope = {
        "schema_version": 1,
        "job_id": job_id,
        "executor": "qnx",
        "status": "completed",
        "message": "target complete",
        "target": {
            "executor": "qnx",
            "hostname": "qnx-pi",
            "system": "QNX",
            "release": "8.0.0",
            "machine": "aarch64le",
            "runtime": "Python 3.14.0",
            "verified": True,
        },
        "telemetry_history": [sample],
        "assessment": {"schema_version": 1, "id": "clip-target"},
    }
    fake = FakeRunner()

    def scp(argv: list[str]) -> subprocess.CompletedProcess:
        source, destination = argv[-2:]
        if source.endswith(":" + manifest_path):
            Path(destination).write_bytes(manifest_bytes)
        elif source.endswith("/result-envelope.json"):
            Path(destination).write_text(json.dumps(envelope), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def ssh(argv: list[str]) -> subprocess.CompletedProcess:
        command = " ".join(argv)
        if "SIMLAB_PROBE_PYTHON_BEGIN" in command:
            stdout = "\n".join(
                [
                    "SIMLAB_PROBE_PYTHON_BEGIN",
                    "Python 3.14.0",
                    "SIMLAB_PROBE_PYTHON_END",
                    "SIMLAB_PROBE_RUNNER_BEGIN",
                    "runner: running",
                    "SIMLAB_PROBE_RUNNER_END",
                    "SIMLAB_PROBE_RUNTIMES_BEGIN",
                    "PRESENT /data/home/qnxuser/qnx-runner-app",
                    "PRESENT /data/home/qnxuser/qnx-runner",
                    "SIMLAB_PROBE_RUNTIMES_END",
                ]
            )
            return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")
        if command.endswith("telemetry.json"):
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps({"schema_version": 1, "samples": [sample]}), stderr=""
            )
        if "/state/job-test.json" in command:
            return subprocess.CompletedProcess(
                argv, 0, stdout=json.dumps({"status": "done", "exit_code": 0}), stderr=""
            )
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    fake.on("scp", scp)
    fake.on("ssh", ssh)
    submit = tmp_path / "submit-job.py"
    fake.on(
        str(submit),
        lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="submitted job-test (9 argv elements) to qnxpi\n", stderr=""
        ),
    )
    config = make_config(
        tmp_path,
        mode="worker",
        submit_job=submit,
        clip_worker_remote=worker_path,
        clip_worker_manifest=manifest_path,
        clip_worker_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
    runner = QnxRunner(config)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video bytes")
    live: list[list[dict]] = []

    outcome = runner.assess_clip_on_target(
        job_id=job_id,
        video_path=video,
        request={"profile": "mixed", "segment_start_s": 0, "segment_end_s": 2},
        telemetry=live.append,
        runner=fake,
    )

    assert outcome.status == "completed"
    assert outcome.target["system"] == "QNX"
    assert outcome.telemetry_history == [sample]
    assert live == [[sample]]
    video_uploads = [call for call in fake.scp_calls() if call[-1].endswith("/.video.bin.part")]
    assert len(video_uploads) == 1
    assert video_uploads[0][-2] == str(video)


def test_clip_worker_requires_deployment_mode_without_local_fallback(tmp_path: Path) -> None:
    runner = QnxRunner(make_config(tmp_path, mode="probe"))
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"video")

    with pytest.raises(QnxRunnerError, match="not deployment-ready"):
        runner.assess_clip_on_target(
            job_id="clip-job-8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c",
            video_path=video,
            request={},
        )


@pytest.mark.parametrize(
    "target",
    [
        {"executor": "qnx", "system": "QNX", "verified": False},
        {"executor": "local", "system": "QNX", "verified": True},
        {"executor": "qnx", "system": "Darwin", "verified": True},
    ],
)
def test_clip_envelope_rejects_unverified_or_wrong_target_identity(target: dict) -> None:
    job_id = "clip-job-8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c"
    envelope = {
        "schema_version": 1,
        "job_id": job_id,
        "executor": "qnx",
        "status": "blocked",
        "message": "blocked",
        "target": target,
        "telemetry_history": [],
        "assessment": None,
    }

    with pytest.raises(QnxRunnerError, match="did not prove a QNX target identity"):
        QnxRunner._validate_clip_envelope(envelope, job_id)


def test_target_clip_wrapper_fails_closed_off_qnx_and_writes_telemetry(tmp_path: Path) -> None:
    video = tmp_path / "video.bin"
    video.write_bytes(b"video")
    installed_worker = tmp_path / "installed-worker.py"
    installed_worker.write_text("raise SystemExit(99)\n", encoding="utf-8")
    manifest = tmp_path / "deployment.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "contract": "holy-crap.clip-assessment.v1",
                "platform": "QNX",
                "worker_path": str(installed_worker),
                "worker_sha256": hashlib.sha256(installed_worker.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "job_id": "clip-job-8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c",
                "executor": "qnx",
                "worker_contract": "holy-crap.clip-assessment.v1",
                "video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    result = tmp_path / "result-envelope.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(CLIP_WRAPPER),
            "--request",
            str(request),
            "--video",
            str(video),
            "--worker",
            str(installed_worker),
            "--manifest",
            str(manifest),
            "--result",
            str(result),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 2
    envelope = json.loads(result.read_text(encoding="utf-8"))
    assert envelope["status"] == "blocked"
    assert envelope["target"]["system"] != "QNX"
    assert envelope["target"]["verified"] is False
    assert envelope["telemetry_history"]
    assert envelope["telemetry_history"][-1]["process_cpu_percent"] is None
    assert (tmp_path / "telemetry.json").is_file()


# --- worker (real local subprocess, no network) -----------------------------


def test_worker_writes_valid_receipt(tmp_path: Path) -> None:
    request_path, _ = write_request(tmp_path)
    result = tmp_path / "receipt.json"

    proc = run_worker(tmp_path, request_path, result)

    assert proc.returncode == 0, proc.stderr
    receipt = json.loads(result.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 1
    assert receipt["run_id"] == RUN_ID
    assert receipt["model"]["name"] == MODEL_NAME
    assert receipt["model"]["sha256"] == hashlib.sha256(MODEL_BYTES).hexdigest()
    assert receipt["model"]["size_bytes"] == len(MODEL_BYTES)
    assert receipt["scenario"]["name"] == SCENARIO_NAME
    assert receipt["scenario"]["size_bytes"] == len(json.dumps(SCENARIO_DOC).encode("utf-8"))
    assert receipt["inference_performed"] is False
    assert receipt["inference_reason"] == "No QNX inference runtime is installed or configured."
    assert receipt["platform"]["python_version"]
    assert receipt["platform"]["system"]
    started = datetime.fromisoformat(receipt["started_at"])
    finished = datetime.fromisoformat(receipt["finished_at"])
    assert started.tzinfo is not None and finished.tzinfo is not None
    assert finished >= started


def test_worker_rejects_tampered_model_hash(tmp_path: Path) -> None:
    request_path, _ = write_request(tmp_path, model={"name": MODEL_NAME, "sha256": "a" * 64})
    result = tmp_path / "receipt.json"

    proc = run_worker(tmp_path, request_path, result)

    assert proc.returncode != 0
    assert not result.exists()
    assert "model hash mismatch" in proc.stderr


def test_worker_rejects_tampered_scenario_hash(tmp_path: Path) -> None:
    request_path, _ = write_request(
        tmp_path, scenario={"name": SCENARIO_NAME, "sha256": "b" * 64}
    )
    result = tmp_path / "receipt.json"

    proc = run_worker(tmp_path, request_path, result)

    assert proc.returncode != 0
    assert not result.exists()
    assert "scenario hash mismatch" in proc.stderr


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"run_id": "../../etc/passwd"}, "run_id"),
        ({"run_id": "8d3f1a2b9c4e4f5a9b1c2d3e4f5a6b7c"}, "run_id"),
        ({"model": {"name": "bad name!", "sha256": "c" * 64}}, "model name"),
        (
            {"model": {"name": MODEL_NAME, "sha256": "NOTHEXNOTHEXNOTHEX"}},
            "64 lowercase hex",
        ),
    ],
)
def test_worker_rejects_unsafe_request(tmp_path: Path, overrides: dict, message: str) -> None:
    request_path, _ = write_request(tmp_path)
    base = json.loads(request_path.read_text(encoding="utf-8"))
    base.update(overrides)
    request_path.write_text(json.dumps(base), encoding="utf-8")
    result = tmp_path / "receipt.json"

    proc = run_worker(tmp_path, request_path, result)

    assert proc.returncode != 0
    assert not result.exists()
    assert message in proc.stderr


def test_worker_rejects_invalid_scenario_json(tmp_path: Path) -> None:
    request_path, _ = write_request(tmp_path)
    scenario = tmp_path / "scenario.json"
    scenario.write_text("{not json", encoding="utf-8")
    model = tmp_path / "model.bin"
    model.write_bytes(MODEL_BYTES)
    result = tmp_path / "receipt.json"

    proc = subprocess.run(
        [
            sys.executable,
            str(WORKER),
            "--request",
            str(request_path),
            "--scenario",
            str(scenario),
            "--model",
            str(model),
            "--result",
            str(result),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode != 0
    assert not result.exists()


# --- validate_on_target with an injected runner ------------------------------


def test_validate_on_target_exact_argv_without_shell(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.receipt_bytes = json.dumps(valid_receipt()).encode("utf-8")
    runner = configured_runner(tmp_path, fake)
    model, scenario = stage_files(tmp_path)

    def helper_handler(argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            argv, 0, stdout="submitted job-x (7 argv elements) to qnxpi\n", stderr=""
        )

    fake.on(str(make_config(tmp_path).submit_job), helper_handler)

    outcome = runner.validate_on_target(
        run_id=RUN_ID,
        model_path=model,
        model_name=MODEL_NAME,
        scenario_path=scenario,
        scenario_name=SCENARIO_NAME,
        runner=fake,
    )

    run_dir = "/data/home/qnxuser/simlab-runs/run-%s" % RUN_ID
    assert outcome.remote_run_dir == run_dir
    assert outcome.receipt["run_id"] == RUN_ID
    assert "submitted job-x" in outcome.helper_output

    for call in fake.calls:
        assert isinstance(call, list)
        assert not call[:1] == ["sh"]
        assert "shell" not in call[0]
        assert "-c" not in call[:3]

    expected_options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
    assert fake.ssh_calls()[0] == ["ssh", *expected_options, "qnxpi", "mkdir", "-p", run_dir]
    rename_call = fake.ssh_calls()[-1]
    assert rename_call[:4] == ["ssh", *expected_options[:2], "-o"]
    assert rename_call[-1] == (
        "cd %s && mv .model.bin.part model.bin && mv .scenario.json.part scenario.json "
        "&& mv .request.json.part request.json && mv .simlab_probe.py.part simlab_probe.py"
    ) % run_dir

    staging_scps = [call for call in fake.scp_calls() if call[-1].endswith(".part")]
    assert len(staging_scps) == 4
    for call in staging_scps:
        assert call[-1].startswith("qnxpi:%s/." % run_dir)
    staged = [call[-1].rsplit("/", 1)[1] for call in staging_scps]
    assert sorted(staged) == sorted(
        [".model.bin.part", ".scenario.json.part", ".request.json.part", ".simlab_probe.py.part"]
    )
    receipt_scps = [call for call in fake.scp_calls() if call[-2].endswith("/receipt.json")]
    assert len(receipt_scps) == 1

    expected_helper = [
        str(make_config(tmp_path).submit_job),
        "--host",
        "qnxpi",
        "--ssh-option",
        "BatchMode=yes",
        "--ssh-option",
        "ConnectTimeout=20",
        "--cwd",
        run_dir,
        "--timeout",
        "60",
        "--wait",
        "--wait-timeout",
        "120",
        "--",
        "/system/bin/python3",
        "simlab_probe.py",
        "--request",
        "request.json",
        "--scenario",
        "scenario.json",
        "--model",
        "model.bin",
        "--result",
        "receipt.json",
    ]
    assert expected_helper in fake.calls


def test_ssh_and_scp_argv_hostname_override(tmp_path: Path) -> None:
    runner = configured_runner(tmp_path, FakeRunner(), ssh_hostname="192.168.4.248")

    assert runner._ssh_argv("uname", "-a") == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "HostName=192.168.4.248",
        "qnxpi",
        "uname",
        "-a",
    ]
    assert runner._scp_argv("local.bin", "qnxpi:/data/x.bin") == [
        "scp",
        "-q",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=20",
        "-o",
        "HostName=192.168.4.248",
        "local.bin",
        "qnxpi:/data/x.bin",
    ]


def test_hostname_override_is_forwarded_to_runner_helper(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.receipt_bytes = json.dumps(valid_receipt()).encode("utf-8")
    config = make_config(tmp_path, ssh_hostname="169.254.55.180")
    runner = QnxRunner(config)
    model, scenario = stage_files(tmp_path)
    fake.on(
        str(config.submit_job),
        lambda argv: subprocess.CompletedProcess(argv, 0, stdout="submitted\n", stderr=""),
    )

    runner.validate_on_target(
        run_id=RUN_ID,
        model_path=model,
        model_name=MODEL_NAME,
        scenario_path=scenario,
        scenario_name=SCENARIO_NAME,
        runner=fake,
    )

    helper = next(call for call in fake.calls if call[0] == str(config.submit_job))
    hostname_index = helper.index("HostName=169.254.55.180")
    assert helper[hostname_index - 1] == "--ssh-option"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"run_id": "../evil"}, "run_id"),
        ({"run_id": "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7C"}, "run_id"),
        ({"model_name": "pen model!"}, "model name"),
        ({"scenario_name": "../healthy"}, "scenario name"),
    ],
)
def test_rejects_unsafe_identifiers_without_any_subprocess(
    tmp_path: Path, kwargs: dict, message: str
) -> None:
    fake = FakeRunner()
    runner = configured_runner(tmp_path, fake)
    model, scenario = stage_files(tmp_path)
    full: dict[str, object] = {
        "run_id": RUN_ID,
        "model_path": model,
        "model_name": MODEL_NAME,
        "scenario_path": scenario,
        "scenario_name": SCENARIO_NAME,
    }
    full.update(kwargs)

    with pytest.raises(QnxRunnerError, match=message):
        runner.validate_on_target(runner=fake, **full)

    assert fake.calls == []


def test_rejects_missing_model_file_without_any_subprocess(tmp_path: Path) -> None:
    fake = FakeRunner()
    runner = configured_runner(tmp_path, fake)
    _, scenario = stage_files(tmp_path)

    with pytest.raises(QnxRunnerError, match="model file does not exist"):
        runner.validate_on_target(
            run_id=RUN_ID,
            model_path=tmp_path / "missing.tflite",
            model_name=MODEL_NAME,
            scenario_path=scenario,
            scenario_name=SCENARIO_NAME,
            runner=fake,
        )

    assert fake.calls == []


def test_helper_nonzero_raises_with_captured_output(tmp_path: Path) -> None:
    fake = FakeRunner()
    runner = configured_runner(tmp_path, fake)
    model, scenario = stage_files(tmp_path)

    def helper_handler(argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            argv, 2, stdout="submitted job-y\n", stderr="worker failed: model hash mismatch"
        )

    fake.on(str(make_config(tmp_path).submit_job), helper_handler)

    with pytest.raises(QnxRunnerError, match="runner helper exited 2") as excinfo:
        runner.validate_on_target(
            run_id=RUN_ID,
            model_path=model,
            model_name=MODEL_NAME,
            scenario_path=scenario,
            scenario_name=SCENARIO_NAME,
            runner=fake,
        )
    assert "model hash mismatch" in str(excinfo.value)


def test_helper_timeout_raises(tmp_path: Path) -> None:
    fake = FakeRunner()
    runner = configured_runner(tmp_path, fake)
    model, scenario = stage_files(tmp_path)

    def helper_handler(argv: list[str]) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(argv[0], 30)

    fake.on(str(make_config(tmp_path).submit_job), helper_handler)

    with pytest.raises(QnxRunnerError, match="timed out"):
        runner.validate_on_target(
            run_id=RUN_ID,
            model_path=model,
            model_name=MODEL_NAME,
            scenario_path=scenario,
            scenario_name=SCENARIO_NAME,
            runner=fake,
        )


def test_malformed_receipt_raises(tmp_path: Path) -> None:
    fake = FakeRunner()
    fake.receipt_bytes = b"{definitely not json"
    runner = configured_runner(tmp_path, fake)
    model, scenario = stage_files(tmp_path)

    def helper_handler(argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 0, stdout="submitted\n", stderr="")

    fake.on(str(make_config(tmp_path).submit_job), helper_handler)

    with pytest.raises(QnxRunnerError, match="malformed receipt"):
        runner.validate_on_target(
            run_id=RUN_ID,
            model_path=model,
            model_name=MODEL_NAME,
            scenario_path=scenario,
            scenario_name=SCENARIO_NAME,
            runner=fake,
        )


@pytest.mark.parametrize(
    "receipt_changes, message",
    [
        ({"model": {"sha256": "0" * 64}}, "model hash does not match"),
        ({"scenario": {"sha256": "1" * 64}}, "scenario hash does not match"),
        ({"run_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}, "run_id"),
        ({"schema_version": 2}, "schema_version"),
        ({"inference_performed": True}, "inference_performed"),
    ],
)
def test_echoed_receipt_mismatch_raises(
    tmp_path: Path, receipt_changes: dict, message: str
) -> None:
    fake = FakeRunner()
    fake.receipt_bytes = json.dumps(valid_receipt(**receipt_changes)).encode("utf-8")
    runner = configured_runner(tmp_path, fake)
    model, scenario = stage_files(tmp_path)

    def helper_handler(argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(argv, 0, stdout="submitted\n", stderr="")

    fake.on(str(make_config(tmp_path).submit_job), helper_handler)

    with pytest.raises(QnxRunnerError, match=message):
        runner.validate_on_target(
            run_id=RUN_ID,
            model_path=model,
            model_name=MODEL_NAME,
            scenario_path=scenario,
            scenario_name=SCENARIO_NAME,
            runner=fake,
        )


# --- probe_capability ---------------------------------------------------------


def test_probe_capability_uses_one_remote_command_and_parses(tmp_path: Path) -> None:
    fake = FakeRunner()
    runner = configured_runner(tmp_path, fake)

    def ssh_handler(argv: list[str]) -> subprocess.CompletedProcess:
        stdout = "\n".join(
            [
                "SIMLAB_PROBE_PYTHON_BEGIN",
                "Python 3.14.0",
                "SIMLAB_PROBE_PYTHON_END",
                "SIMLAB_PROBE_RUNNER_BEGIN",
                "spool: /data/home/qnxuser/qnx-runner",
                "runner: running (pid 1234)",
                "SIMLAB_PROBE_RUNNER_END",
                "SIMLAB_PROBE_RUNTIMES_BEGIN",
                "ABSENT tflite_runtime",
                "ABSENT onnxruntime",
                "ABSENT cv2",
                "ABSENT numpy",
                "PRESENT /data/home/qnxuser/qnx-runner-app",
                "PRESENT /data/home/qnxuser/qnx-runner",
                "SIMLAB_PROBE_RUNTIMES_END",
            ]
        )
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")

    fake.on("ssh", ssh_handler)

    report = runner.probe_capability(runner=fake)

    assert len(fake.calls) == 1
    command = fake.calls[0][-1]
    assert "status-runner.sh" in command
    assert "import tflite_runtime" in command
    assert "BatchMode=yes" in fake.calls[0]
    assert isinstance(report, QnxProbeReport)
    assert report.reachable
    assert report.python_version == "3.14.0"
    assert report.runner_ok
    assert report.ready
    assert report.runtime_presence["tflite_runtime"] is False
    assert report.runtime_presence["/data/home/qnxuser/qnx-runner-app"] is True
    assert report.capability().status == "ready"


def test_probe_capability_disabled_mode_skips_network(tmp_path: Path) -> None:
    fake = FakeRunner()
    runner = configured_runner(tmp_path, fake, mode="disabled")

    report = runner.probe_capability(runner=fake)

    assert fake.calls == []
    assert not report.reachable
    assert not report.ready
    assert "disabled" in report.detail

    model, scenario = stage_files(tmp_path)
    with pytest.raises(QnxRunnerError, match="disabled"):
        runner.validate_on_target(
            run_id=RUN_ID,
            model_path=model,
            model_name=MODEL_NAME,
            scenario_path=scenario,
            scenario_name=SCENARIO_NAME,
            runner=fake,
        )
    assert fake.calls == []


def test_config_from_env_defaults_and_mode_validation() -> None:
    config = QnxRunnerConfig.from_env({})
    assert config.mode == "disabled"
    assert config.ssh_alias == "qnxpi"
    assert config.ssh_hostname is None
    assert config.ssh_timeout == 20
    assert config.remote_python == "/system/bin/python3"
    assert config.submit_job == DEFAULT_SUBMIT_JOB

    probe_config = QnxRunnerConfig.from_env(
        {
            "QNX_EXECUTOR_MODE": "probe",
            "QNX_SSH_ALIAS": "pi2",
            "QNX_SSH_HOSTNAME": "10.1.2.3",
            "QNX_SSH_TIMEOUT": "9",
            "QNX_JOB_TIMEOUT": "42",
            "QNX_WAIT_TIMEOUT": "77",
        }
    )
    assert probe_config.mode == "probe"
    assert probe_config.ssh_alias == "pi2"
    assert probe_config.ssh_hostname == "10.1.2.3"
    assert probe_config.ssh_timeout == 9
    assert probe_config.job_timeout == 42
    assert probe_config.wait_timeout == 77

    with pytest.raises(QnxRunnerError, match="QNX_EXECUTOR_MODE"):
        QnxRunnerConfig.from_env({"QNX_EXECUTOR_MODE": "inference"})
    with pytest.raises(QnxRunnerError, match="integer"):
        QnxRunnerConfig.from_env({"QNX_SSH_TIMEOUT": "soon"})
