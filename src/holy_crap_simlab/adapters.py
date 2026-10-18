"""Boundaries to simulation executors and completed training artifacts."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .catalog import Catalog, safe_part
from .engine import SimulationResult, simulate
from .models import AdapterCapability, ModelArtifact, Scenario
from .qnx_runner import (
    QnxProbeReport,
    QnxRunner,
    QnxRunnerError,
    QnxValidationOutcome,
)
from .scenarios import ScenarioRepository


class AdapterError(ValueError):
    pass


class Executor(ABC):
    id: str
    version: str = "0.1.0"

    @abstractmethod
    def capability(self) -> AdapterCapability: ...

    @abstractmethod
    def execute(self, scenario: Scenario, model: ModelArtifact) -> SimulationResult: ...


class MockExecutor(Executor):
    id = "mock"
    version = "0.1.0"

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            id=self.id,
            kind="executor",
            status="ready",
            description="Deterministic local control simulator",
        )

    def execute(self, scenario: Scenario, model: ModelArtifact) -> SimulationResult:
        return simulate(scenario, model.id)


class QnxExecutor(Executor):
    """Honest boundary to the headless QNX Pi: target validation, never inference.

    The Pi has no TensorFlow Lite, ONNX, OpenCV, or NumPy runtime, so every QNX
    run is a target probe: it proves that one exact model artifact and one
    canonical scenario JSON reached the physical target and were processed
    there, using the dependency-free `target/qnx/simlab_probe.py` worker
    through the persistent qnx-runner.

    Capability status follows a strict ladder:

    - `not_configured`: QNX_EXECUTOR_MODE is disabled; no Pi contact.
    - `unreachable`: SSH/runner contact failed or timed out.
    - `runtime_missing`: reachable but Python or the persistent runner is
      missing, so the probe worker cannot run.
    - `probe_only`: SSH, Python, and the runner all work, so target validation
      runs can complete. This is the highest status QNX can reach.
    - `ready`: never reported until actual inference exists on the Pi.
    """

    id = "qnx"
    version = "0.1.0"

    PROBE_SSH_TIMEOUT = 10
    PROBE_COMMAND_TIMEOUT = 15

    def __init__(
        self,
        runner: QnxRunner | None = None,
        catalog: Catalog | None = None,
        scenario_directory: Path | None = None,
        prober: object | None = None,
    ) -> None:
        self._runner = runner or QnxRunner()
        self._catalog = catalog
        self._scenario_directory = scenario_directory
        self._prober = prober

    def capability(self) -> AdapterCapability:
        config = self._runner.config
        if not config.enabled:
            return AdapterCapability(
                id=self.id,
                kind="executor",
                status="not_configured",
                description=(
                    "QNX target validation is disabled (QNX_EXECUTOR_MODE=%r); no Pi "
                    "contact is attempted until it is set to 'probe'" % config.mode
                ),
                details={"mode": config.mode},
            )
        try:
            report = self._probe()
        except (QnxRunnerError, OSError, TimeoutError) as exc:
            return AdapterCapability(
                id=self.id,
                kind="executor",
                status="unreachable",
                description="QNX Pi probe failed: %s" % exc,
                details={"error": str(exc)},
            )
        return self._capability_from_report(report)

    def _probe(self) -> QnxProbeReport:
        if self._prober is not None:
            return self._prober()  # type: ignore[return-value]
        config = self._runner.config
        probe_config = replace(
            config,
            ssh_timeout=min(config.ssh_timeout, self.PROBE_SSH_TIMEOUT),
            command_timeout=min(config.command_timeout, self.PROBE_COMMAND_TIMEOUT),
        )
        return QnxRunner(probe_config).probe_capability()

    def _capability_from_report(self, report: QnxProbeReport) -> AdapterCapability:
        if not report.reachable:
            return AdapterCapability(
                id=self.id,
                kind="executor",
                status="unreachable",
                description=report.detail,
                details={"reachable": False, "detail": report.detail},
            )
        if not report.python_ok:
            return AdapterCapability(
                id=self.id,
                kind="executor",
                status="runtime_missing",
                description="QNX Pi has no working Python; the probe worker cannot run",
                details={"python_version": None, "runtimes": report.runtime_presence},
            )
        if not report.runner_ok:
            return AdapterCapability(
                id=self.id,
                kind="executor",
                status="runtime_missing",
                description="QNX persistent runner is not running; jobs cannot be submitted",
                details={
                    "python_version": report.python_version,
                    "runner": "not running",
                    "runner_output": report.runner_output,
                },
            )
        return AdapterCapability(
            id=self.id,
            kind="executor",
            status="probe_only",
            description=(
                "QNX target validation works (SSH, Python, runner), but the Pi has "
                "no inference runtime; QNX never reports ready until actual inference exists"
            ),
            details={
                "python_version": report.python_version,
                "runner": "running",
                "runtimes": report.runtime_presence,
                "inference_performed": False,
            },
        )

    def execute(self, scenario: Scenario, model: ModelArtifact) -> SimulationResult:
        raise AdapterError(
            "the QNX target has no inference runtime; QNX runs are target-validation "
            "probes (evaluation_kind=target_probe) and cannot produce predictions"
        )

    def canonical_scenario_path(self, scenario: Scenario) -> Path:
        directory = self._scenario_directory
        if directory is None:
            directory = ScenarioRepository.default_directory()
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("id") == scenario.id:
                return path
        raise AdapterError(f"canonical scenario file not found for scenario {scenario.id}")

    def validate_target(
        self, scenario: Scenario, model: ModelArtifact, run_id: str
    ) -> QnxValidationOutcome:
        """Run the QNX target probe for one exact catalog model and canonical scenario.

        The built-in zero-byte mock model is rejected outright: it has no real
        artifact bytes to stage on the Pi.
        """
        if model.size_bytes == 0:
            raise AdapterError(
                "the built-in zero-byte mock model cannot be validated on the QNX "
                "target; register a real model artifact first"
            )
        if self._catalog is None:
            raise AdapterError("QNX target validation requires the artifact catalog")
        blob = self._catalog.artifact_path(model)
        if blob is None or not blob.is_file():
            raise AdapterError(
                "model artifact bytes are missing from the catalog for %s; "
                "re-register the model before QNX target validation" % model.id
            )
        scenario_path = self.canonical_scenario_path(scenario)
        try:
            return self._runner.validate_on_target(
                run_id=run_id,
                model_path=blob,
                model_name=safe_part(model.name),
                scenario_path=scenario_path,
                scenario_name=scenario.id,
            )
        except QnxRunnerError as exc:
            raise AdapterError(str(exc)) from exc


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Normalization(ManifestModel):
    kind: Literal["none", "scale_offset", "mean_std"]
    scale: float | list[float] | None = None
    offset: float | list[float] | None = None
    mean: list[float] | None = None
    std: list[float] | None = None


class InputTensor(ManifestModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    channels: int = Field(ge=1, le=4)
    dtype: Literal["uint8", "int8", "float16", "float32"]
    layout: Literal["NHWC", "NCHW"]
    color_space: Literal["RGB", "BGR", "GRAY"]
    normalization: Normalization


class OutputTensor(ManifestModel):
    task: Literal["classification", "detection", "segmentation", "embedding", "anomaly_score"]
    dtype: Literal["uint8", "int8", "float16", "float32"]
    interpretation: str
    threshold: float | None = None
    shape: list[int] | None = None


class Provenance(ManifestModel):
    producer: str
    training_run: str
    dataset_revision: str | None = None
    source_commit: str | None = None
    export_tool: str | None = None
    notes: str | None = None


class RuntimeCompatibility(ManifestModel):
    name: str
    version: str
    platform: str | None = None
    verified: bool = False


class Compatibility(ManifestModel):
    runtimes: list[RuntimeCompatibility]
    quantization: Literal["none", "float16", "dynamic", "int8", "uint8"]
    required_operators: list[str] = Field(default_factory=list)
    notes: str | None = None


class VeriManifest(ManifestModel):
    schema_version: Literal[1]

    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str
    model_file: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    format: Literal["tflite", "onnx"]
    input: InputTensor
    output: OutputTensor
    labels: list[str]
    provenance: Provenance
    metrics: dict[str, float]
    compatibility: Compatibility
    created_at: datetime


class VeriArtifactImporter:
    """Import a completed local Veri output directory without API or credential access."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            id="veri-local",
            kind="importer",
            status="ready",
            description="Import a completed local Veri artifact directory",
        )

    def import_directory(self, directory: Path) -> ModelArtifact:
        root = directory.expanduser().resolve()
        if not root.is_dir():
            raise AdapterError(f"Veri output directory does not exist: {directory}")
        manifest_path = root / "model.json"
        if not manifest_path.is_file():
            raise AdapterError("Veri output directory must contain model.json")
        try:
            manifest = VeriManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AdapterError(f"invalid model.json: {exc}") from exc
        model_path = (root / manifest.model_file).resolve()
        if root not in model_path.parents or not model_path.is_file():
            raise AdapterError("model_file must reference a file inside the Veri output directory")
        if model_path.suffix.lower() != f".{manifest.format}":
            raise AdapterError("model_file extension does not match the declared format")
        digest = hashlib.sha256()
        with model_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != manifest.sha256:
            raise AdapterError("model_file SHA-256 does not match model.json")
        return self.catalog.register_file(
            model_path,
            name=manifest.name,
            version=manifest.version,
            source="veri-local",
        )
