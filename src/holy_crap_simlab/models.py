"""Typed contracts shared by the simulation engine, catalog, and API."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioMode(StrEnum):
    HEALTHY = "healthy"
    OUTBREAK = "outbreak"


class PenRegion(StrictModel):
    id: str
    polygon: list[tuple[float, float]] = Field(min_length=3)


class PenConfig(StrictModel):
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    regions: list[PenRegion] = Field(default_factory=list)


class ObservationConfig(StrictModel):
    sample_interval_s: float = Field(gt=0)
    position_noise_m: float = Field(ge=0)
    miss_probability: float = Field(ge=0, le=1)
    false_positive_rate: float = Field(ge=0, le=1)
    alert_threshold: float = 0.18
    alert_persistence_s: float = Field(default=0, ge=0)
    onset_s: float | None = Field(default=None, ge=0)
    initial_affected_fraction: float = Field(default=0, ge=0, le=1)
    movement_scale_after_onset: float = Field(default=1, ge=0)


class RendererConfig(StrictModel):
    kind: Literal["mock", "video_replay", "blenderproc"]
    version: str
    observation_artifact: str | None = None
    observation_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class Scenario(StrictModel):
    schema_version: Literal[1] = 1
    id: str
    name: str
    description: str
    bird_count: int = Field(ge=1, le=10_000)
    fps: float = Field(gt=0, le=240)
    duration_s: int = Field(ge=1, le=86_400)
    seed: int = Field(ge=0)
    mode: ScenarioMode
    pen: PenConfig
    observation: ObservationConfig
    renderer: RendererConfig

    @computed_field
    @property
    def pen_width_m(self) -> float:
        """Flat API convenience retained for the browser's pen renderer."""
        return self.pen.width_m

    @computed_field
    @property
    def pen_height_m(self) -> float:
        """Flat API convenience retained for the browser's pen renderer."""
        return self.pen.height_m


class ModelArtifact(StrictModel):
    schema_version: Literal[1] = 1
    id: str
    name: str
    version: str
    format: str
    source: str
    sha256: str | None
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


class TruthState(StrEnum):
    SUSCEPTIBLE = "susceptible"
    EXPOSED = "exposed"
    INFECTIOUS = "infectious"
    CLINICAL = "clinical"


class BirdSnapshot(StrictModel):
    id: str
    x: float
    y: float
    heading: float
    truth_state: TruthState
    predicted_abnormal: bool


class PenSnapshot(StrictModel):
    schema_version: Literal[1] = 1
    t_s: int = Field(ge=0)
    birds: list[BirdSnapshot]


class TimelinePoint(StrictModel):
    schema_version: Literal[1] = 1
    t_s: int = Field(ge=0)
    susceptible: int = Field(ge=0)
    exposed: int = Field(ge=0)
    infectious: int = Field(ge=0)
    clinical: int = Field(ge=0)
    abnormal_droppings: int = Field(ge=0)
    truth_score: float = Field(ge=0, le=1)
    predicted_score: float = Field(ge=0, le=1)
    alert: bool


class RunMetrics(StrictModel):
    schema_version: Literal[1] = 1
    detection_delay_s: float | None = Field(default=None, ge=0)
    false_alerts: int = Field(ge=0)
    mean_fps: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    dropped_frames: int = Field(ge=0)
    alert_triggered: bool


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SimulationRun(StrictModel):
    schema_version: Literal[1] = 1
    id: str
    status: RunStatus
    scenario_id: str
    model_id: str
    executor: str
    created_at: datetime = Field(default_factory=utc_now)
    metrics: RunMetrics | None = None
    error: str | None = None


class ResultMetrics(StrictModel):
    detection_delay_s: float | None = Field(default=None, ge=0)
    false_alerts: int = Field(ge=0)
    mean_fps: float = Field(ge=0)
    p95_latency_ms: float = Field(ge=0)
    dropped_frames: int = Field(ge=0)
    alert_triggered: bool


class ResultModelReference(StrictModel):
    name: str
    version: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResultScenarioReference(StrictModel):
    id: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    seed: int = Field(ge=0)


class ResultExecutorReference(StrictModel):
    name: Literal["mock", "workstation", "qnx"]
    version: str
    target: str | None = None
    runtime: str | None = None


class ResultArtifact(StrictModel):
    kind: Literal["timeline", "snapshots", "predictions", "video", "frames", "log", "report", "other"]
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str
    size_bytes: int = Field(ge=0)


class RunResult(StrictModel):
    schema_version: Literal[1] = 1
    run_id: str
    model: ResultModelReference
    scenario: ResultScenarioReference
    executor: ResultExecutorReference
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    metrics: ResultMetrics
    artifacts: list[ResultArtifact]
    error: dict[str, Any] | None = None


class CreateRunRequest(StrictModel):
    scenario_id: str
    model_id: str
    executor: Literal["mock", "qnx"] = "mock"


class VeriImportRequest(StrictModel):
    path: str


class AdapterCapability(StrictModel):
    id: str
    kind: Literal["executor", "importer"]
    status: Literal["ready", "not_configured"]
    description: str


class SystemCapabilities(StrictModel):
    schema_version: Literal[1] = 1
    executors: list[AdapterCapability]
    importers: list[AdapterCapability]


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    schema_version: Literal[1] = 1


class ErrorBody(StrictModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(StrictModel):
    error: ErrorBody
