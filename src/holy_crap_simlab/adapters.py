"""Boundaries to simulation executors and completed training artifacts."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .catalog import Catalog
from .engine import SimulationResult, simulate
from .models import AdapterCapability, ModelArtifact, Scenario


class AdapterError(ValueError):
    pass


class Executor(ABC):
    id: str

    @abstractmethod
    def capability(self) -> AdapterCapability: ...

    @abstractmethod
    def execute(self, scenario: Scenario, model: ModelArtifact) -> SimulationResult: ...


class MockExecutor(Executor):
    id = "mock"

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
    """Future boundary for SSH/SCP deployment and Sensor Framework file-camera playback.

    The Pi remains a real execution target rather than a simulated device. This stub deliberately
    performs no network access until target discovery, artifact deployment, invocation, and result
    collection are designed and configured.
    """

    id = "qnx"

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            id=self.id,
            kind="executor",
            status="not_configured",
            description="QNX Pi execution via SSH/SCP and file-camera playback (not configured)",
        )

    def execute(self, scenario: Scenario, model: ModelArtifact) -> SimulationResult:
        raise AdapterError("the QNX executor is not configured")


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
