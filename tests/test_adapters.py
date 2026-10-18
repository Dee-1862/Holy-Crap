from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from holy_crap_simlab.adapters import AdapterError, MockExecutor, QnxExecutor, VeriArtifactImporter
from holy_crap_simlab.catalog import Catalog
from holy_crap_simlab.qnx_runner import (
    QnxProbeReport,
    QnxRunnerConfig,
    QnxRunnerError,
    QnxValidationOutcome,
)
from holy_crap_simlab.scenarios import ScenarioRepository

ROOT = Path(__file__).resolve().parents[1]


def manifest_for(model_bytes: bytes, model_file: str = "pen-model.tflite") -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "pen-anomaly",
        "version": "2026-10-17",
        "model_file": model_file,
        "sha256": hashlib.sha256(model_bytes).hexdigest(),
        "format": "tflite",
        "input": {
            "width": 320,
            "height": 320,
            "channels": 3,
            "dtype": "uint8",
            "layout": "NHWC",
            "color_space": "RGB",
            "normalization": {"kind": "none"},
        },
        "output": {
            "task": "anomaly_score",
            "dtype": "float32",
            "interpretation": "pen-level anomaly score",
            "threshold": 0.5,
        },
        "labels": ["expected", "anomalous"],
        "provenance": {"producer": "training-workstream", "training_run": "local-test"},
        "metrics": {"validation_auc": 0.8},
        "compatibility": {"runtimes": [], "quantization": "none"},
        "created_at": "2026-10-17T12:00:00Z",
    }


def test_imports_completed_local_veri_directory(tmp_path: Path) -> None:
    output = tmp_path / "veri-output"
    output.mkdir()
    model_bytes = b"finished tflite artifact"
    (output / "pen-model.tflite").write_bytes(model_bytes)
    (output / "model.json").write_text(
        json.dumps(manifest_for(model_bytes)),
        encoding="utf-8",
    )

    model = VeriArtifactImporter(Catalog(tmp_path / "catalog")).import_directory(output)

    assert model.source == "veri-local"
    assert model.format == "tflite"
    assert model.sha256 == hashlib.sha256(model_bytes).hexdigest()


@pytest.mark.parametrize(
    "manifest, message",
    [
        (None, "must contain model.json"),
        (manifest_for(b"outside", "../outside.tflite"), "inside"),
    ],
)
def test_rejects_incomplete_or_escaping_veri_directory(
    tmp_path: Path, manifest: dict[str, str] | None, message: str
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (tmp_path / "outside.tflite").write_bytes(b"outside")
    if manifest:
        (output / "model.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AdapterError, match=message):
        VeriArtifactImporter(Catalog(tmp_path / "catalog")).import_directory(output)


def test_rejects_manifest_with_wrong_digest(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    model_bytes = b"actual bytes"
    (output / "pen-model.tflite").write_bytes(model_bytes)
    manifest = manifest_for(b"different bytes")
    (output / "model.json").write_text(json.dumps(manifest), encoding="utf-8")
    catalog = Catalog(tmp_path / "catalog")

    with pytest.raises(AdapterError, match="SHA-256"):
        VeriArtifactImporter(catalog).import_directory(output)

    assert catalog.list_models() == []


# --- capability states --------------------------------------------------------


def probe_report(
    *,
    reachable: bool = True,
    python_version: str | None = "3.14.0",
    runner_output: str = "runner: running (pid 1)",
    detail: str = "probe detail",
) -> QnxProbeReport:
    return QnxProbeReport(
        reachable=reachable,
        python_version=python_version,
        runner_output=runner_output,
        runtime_presence={
            "tflite_runtime": False,
            "onnxruntime": False,
            "cv2": False,
            "numpy": False,
        },
        detail=detail,
    )


class FakeProbeClient:
    def __init__(self, mode: str = "probe") -> None:
        self.config = QnxRunnerConfig(mode=mode)

    def validate_on_target(self, **kwargs):
        raise AssertionError("validate_on_target must not be called by capability tests")


def executor_with(prober=None, mode: str = "probe") -> QnxExecutor:
    return QnxExecutor(FakeProbeClient(mode), prober=prober)


def test_mock_executor_capability_is_ready() -> None:
    capability = MockExecutor().capability()

    assert capability.id == "mock"
    assert capability.status == "ready"


def test_qnx_capability_disabled_is_not_configured() -> None:
    capability = executor_with(mode="disabled").capability()

    assert capability.status == "not_configured"
    assert capability.details == {"mode": "disabled"}


def test_qnx_capability_probe_only_when_transport_works() -> None:
    capability = executor_with(prober=lambda: probe_report()).capability()

    assert capability.status == "probe_only"
    assert capability.details["python_version"] == "3.14.0"
    assert capability.details["runner"] == "running"
    assert capability.details["inference_performed"] is False
    assert capability.details["runtimes"]["tflite_runtime"] is False


def test_qnx_capability_unreachable_when_ssh_fails() -> None:
    capability = executor_with(
        prober=lambda: probe_report(reachable=False, python_version=None, runner_output="")
    ).capability()

    assert capability.status == "unreachable"
    assert capability.details["reachable"] is False


def test_qnx_capability_runtime_missing_when_python_absent() -> None:
    capability = executor_with(
        prober=lambda: probe_report(python_version=None)
    ).capability()

    assert capability.status == "runtime_missing"
    assert capability.details["python_version"] is None


def test_qnx_capability_runtime_missing_when_runner_down() -> None:
    capability = executor_with(
        prober=lambda: probe_report(runner_output="runner: not running")
    ).capability()

    assert capability.status == "runtime_missing"
    assert capability.details["runner"] == "not running"


def test_qnx_capability_probe_error_returns_unreachable() -> None:
    def failing_probe() -> QnxProbeReport:
        raise QnxRunnerError("SSH to qnxpi failed")

    capability = executor_with(prober=failing_probe).capability()

    assert capability.status == "unreachable"
    assert "SSH to qnxpi failed" in capability.details["error"]


def test_qnx_capability_is_never_ready() -> None:
    probers = [
        lambda: probe_report(),
        lambda: probe_report(reachable=False, python_version=None, runner_output=""),
        lambda: probe_report(python_version=None),
        lambda: probe_report(runner_output="runner: not running"),
    ]
    for prober in probers:
        assert executor_with(prober=prober).capability().status != "ready"


# --- QNX target validation with a genuine fake client -------------------------


class RecordingFakeClient:
    """Builds a valid receipt from the actual staged bytes; no network, no shell."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.config = QnxRunnerConfig(mode="probe")
        self.failure = failure
        self.calls: list[dict] = []

    def validate_on_target(self, **kwargs) -> QnxValidationOutcome:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        run_id = kwargs["run_id"]
        model_bytes = Path(kwargs["model_path"]).read_bytes()
        scenario_bytes = Path(kwargs["scenario_path"]).read_bytes()
        receipt = {
            "schema_version": 1,
            "run_id": run_id,
            "model": {
                "name": kwargs["model_name"],
                "sha256": hashlib.sha256(model_bytes).hexdigest(),
                "size_bytes": len(model_bytes),
            },
            "scenario": {
                "name": kwargs["scenario_name"],
                "sha256": hashlib.sha256(scenario_bytes).hexdigest(),
                "size_bytes": len(scenario_bytes),
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
        return QnxValidationOutcome(
            receipt=receipt,
            helper_output="fake helper output",
            remote_run_dir="/data/home/qnxuser/simlab-runs/run-%s" % run_id,
        )


def build_executor(tmp_path: Path, client: RecordingFakeClient) -> tuple[QnxExecutor, Catalog]:
    catalog = Catalog(tmp_path / "catalog")
    catalog.seed_mock_model()
    repository = ScenarioRepository(ROOT / "scenarios")
    executor = QnxExecutor(
        client,
        catalog=catalog,
        scenario_directory=repository.directory,
        prober=lambda: probe_report(),
    )
    return executor, catalog


def test_qnx_validate_target_rejects_zero_byte_mock_model(tmp_path: Path) -> None:
    executor, catalog = build_executor(tmp_path, RecordingFakeClient())
    model = catalog.get_model("mock-baseline")
    scenario = ScenarioRepository(ROOT / "scenarios").get("healthy-100")

    with pytest.raises(AdapterError, match="zero-byte"):
        executor.validate_target(scenario, model, "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c")


def test_qnx_validate_target_stages_catalog_blob_and_canonical_scenario(
    tmp_path: Path,
) -> None:
    client = RecordingFakeClient()
    executor, catalog = build_executor(tmp_path, client)
    model_bytes = b"\x00real tflite model bytes\xff"
    import io

    model = catalog.register_stream(
        io.BytesIO(model_bytes),
        name="Pen anomaly model",
        version="2",
        filename="pen.tflite",
        source="teammate",
    )
    scenario = ScenarioRepository(ROOT / "scenarios").get("pio-reference-100")

    outcome = executor.validate_target(scenario, model, "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c")

    assert len(client.calls) == 1
    staged = client.calls[0]
    assert Path(staged["model_path"]).read_bytes() == model_bytes
    assert Path(staged["scenario_path"]) == ROOT / "scenarios" / "pio-reference-100.json"
    assert staged["model_name"] == "Pen-anomaly-model"
    assert staged["scenario_name"] == "pio-reference-100"
    assert staged["run_id"] == "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c"
    assert outcome.receipt["inference_performed"] is False
    assert outcome.receipt["model"]["sha256"] == hashlib.sha256(model_bytes).hexdigest()


def test_qnx_validate_target_raises_when_artifact_bytes_missing(tmp_path: Path) -> None:
    client = RecordingFakeClient()
    executor, catalog = build_executor(tmp_path, client)
    import io

    model = catalog.register_stream(
        io.BytesIO(b"staged bytes"),
        name="Staged model",
        version="1",
        filename="staged.tflite",
        source="teammate",
    )
    blob = catalog.artifact_path(model)
    blob.unlink()
    scenario = ScenarioRepository(ROOT / "scenarios").get("healthy-100")

    with pytest.raises(AdapterError, match="missing from the catalog"):
        executor.validate_target(scenario, model, "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c")

    assert client.calls == []


def test_qnx_validate_target_wraps_transport_failure(tmp_path: Path) -> None:
    client = RecordingFakeClient(failure=QnxRunnerError("runner helper exited 2"))
    executor, catalog = build_executor(tmp_path, client)
    import io

    model = catalog.register_stream(
        io.BytesIO(b"staged bytes"),
        name="Staged model",
        version="1",
        filename="staged.tflite",
        source="teammate",
    )
    scenario = ScenarioRepository(ROOT / "scenarios").get("healthy-100")

    with pytest.raises(AdapterError, match="runner helper exited 2"):
        executor.validate_target(scenario, model, "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c")


def test_qnx_executor_execute_refuses_inference_claims(tmp_path: Path) -> None:
    executor, catalog = build_executor(tmp_path, RecordingFakeClient())
    model = catalog.get_model("mock-baseline")
    scenario = ScenarioRepository(ROOT / "scenarios").get("healthy-100")

    with pytest.raises(AdapterError, match="target_probe"):
        executor.execute(scenario, model)
