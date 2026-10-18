"""Typed contracts shared by the simulation engine, catalog, and API."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


PROXY_SHA256_PLACEHOLDER = "TO_BE_FILLED_BY_ORCHESTRATOR"
_SHA256_PATTERN = r"[a-f0-9]{64}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioMode(StrEnum):
    HEALTHY = "healthy"
    OUTBREAK = "outbreak"


class SimulationProfile(StrEnum):
    """Deterministic demo profile requested by the UI for one assessment."""

    HEALTHY = "healthy"
    MIXED = "mixed"
    CONCERNING = "concerning"


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
    evaluation_kind: Literal["prediction", "target_probe"] = "prediction"
    model: ResultModelReference
    scenario: ResultScenarioReference
    executor: ResultExecutorReference
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    metrics: ResultMetrics | None = None
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
    status: Literal["ready", "probe_only", "unreachable", "runtime_missing", "not_configured"]
    description: str
    details: dict[str, Any] | None = None


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


class MediaAssetInfo(StrictModel):
    """Typed reference-media metadata served by the media API."""

    id: str
    title: str
    description: str
    media_type: str
    width: int
    height: int
    filename: str
    sha256: str
    expected_size_bytes: int
    installed: bool
    verified: bool
    size_bytes: int
    duration_s: float | None
    frame_rate_fps: float | None
    frame_count: int | None
    codec: str | None
    content_url: str
    source_url: str
    dataset_url: str
    doi: str
    license: str
    license_url: str
    attribution: str
    creators: list[str]
    limitations: list[str]


class DatasetClip(StrictModel):
    """Human-reviewed media entry available to the simulation dashboard."""

    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str
    dataset_name: str
    status: Literal["ready", "cataloged", "reference_only", "rejected"]
    review_verdict: str
    camera_fit: str
    best_use: list[str]
    limitations: list[str]
    source_url: str
    dataset_url: str
    license: str
    doi: str | None = None
    media_kind: Literal["video", "images"]
    media_type: str | None = None
    filename: str | None = None
    duration_s: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0)
    expected_size_bytes: int | None = Field(default=None, ge=0)
    byte_range_start: int | None = Field(default=None, ge=0)
    byte_range_end: int | None = Field(default=None, ge=0)
    demo_asset_id: str | None = None
    assessable: bool
    bytes_available: bool = False
    content_url: str | None = None
    installed_size_bytes: int | None = Field(default=None, ge=0)


class ClipVideo(StrictModel):
    """Immutable input video associated with one aggregate assessment."""

    name: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)
    media_type: str
    duration_s: float | None = Field(default=None, gt=0)
    segment_start_s: float = Field(default=0.0, ge=0)
    segment_end_s: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: float | None = Field(default=None, gt=0)
    source: Literal["upload", "demo", "dataset", "catalog_mock"]
    demo_asset_id: str | None = None
    catalog_clip_id: str | None = None
    bytes_available: bool = True
    content_url: str | None
    metadata_source: Literal["ffprobe", "demo_manifest", "catalog", "unavailable"]
    metadata_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _truthful_content_state(self) -> ClipVideo:
        if self.source == "catalog_mock":
            if self.bytes_available or self.content_url is not None or self.size_bytes != 0:
                raise ValueError("catalog mocks cannot claim video bytes or playable content")
            if not self.catalog_clip_id or self.metadata_source != "catalog":
                raise ValueError("catalog mocks require catalog provenance")
        elif not self.bytes_available or self.content_url is None:
            raise ValueError("uploaded, demo, and dataset videos require available content bytes")
        if self.segment_end_s is not None and self.segment_end_s <= self.segment_start_s:
            raise ValueError("assessment segment end must be after its start")
        if self.duration_s is not None:
            if self.segment_start_s >= self.duration_s:
                raise ValueError("assessment segment start must be before source duration")
            if self.segment_end_s is not None and self.segment_end_s > self.duration_s:
                raise ValueError("assessment segment end cannot exceed source duration")
        return self


class ClipModuleArtifactSlot(StrictModel):
    """A deliberately empty slot that a future real model artifact may fill."""

    required_for_real_mode: bool
    status: Literal["not_configured", "configured"]
    model_id: str | None = None
    expected_formats: list[str] = Field(default_factory=list)
    compatibility_verified: bool = False


class ClipModule(StrictModel):
    id: str
    label: str
    mode: Literal["mock", "partial", "real"]
    version: str
    status: Literal["completed", "not_configured", "failed"]
    adapter: str
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    artifact: ClipModuleArtifactSlot
    notice: str


class ClipActivitySummary(StrictModel):
    score: float = Field(ge=0, le=1)
    category: Literal["low", "typical", "high"]
    motion_coverage: float = Field(ge=0, le=1)
    zone_scores: dict[str, float]
    sampled_frames: int = Field(default=0, ge=0)
    bird_observations: int = Field(default=0, ge=0)
    behavior_distribution: dict[str, float] = Field(default_factory=dict)


class ClipAppearanceSummary(StrictModel):
    score: float = Field(ge=0, le=1)
    category: Literal["review", "mixed", "typical-looking"]
    notes: list[str]


class NormalizedBoundingBox(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _inside_frame(self) -> NormalizedBoundingBox:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("normalized bounding box must stay inside the frame")
        return self


class VideoAnnotation(StrictModel):
    """One sampled-frame observation that can be overlaid on assessed video.

    Chicken observations are deliberately not track IDs. Dropping observations
    may share a candidate ID when the stationary detector retained the same
    location across multiple sampled frames.
    """

    id: str = Field(min_length=1)
    kind: Literal["chicken", "dropping"]
    timestamp_s: float = Field(ge=0)
    bbox: NormalizedBoundingBox
    detection_confidence: float = Field(ge=0, le=1)
    label: str | None = None
    label_confidence: float | None = Field(default=None, ge=0, le=1)
    scores: dict[str, float] = Field(default_factory=dict)
    candidate_id: str | None = None
    sample_index: int = Field(ge=0)
    observation_state: Literal["observed", "carried_forward"] = "observed"
    active_from_s: float | None = Field(default=None, ge=0)
    active_until_s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _candidate_link_matches_kind(self) -> VideoAnnotation:
        if self.kind == "dropping" and not self.candidate_id:
            raise ValueError("dropping annotations require candidate_id")
        if self.kind == "chicken" and self.candidate_id is not None:
            raise ValueError("chicken annotations cannot reference a feces candidate")
        if self.kind == "chicken" and self.observation_state != "observed":
            raise ValueError("chicken annotations cannot be carried forward")
        if self.observation_state == "carried_forward":
            if self.kind != "dropping" or self.active_from_s is None or self.active_until_s is None:
                raise ValueError("carried annotations require a dropping and an active interval")
            if self.active_from_s < self.timestamp_s:
                raise ValueError("carried annotation cannot begin before its evidence timestamp")
            if self.active_until_s < self.active_from_s:
                raise ValueError("carried annotation interval must be ordered")
        if any(score < 0 or score > 1 for score in self.scores.values()):
            raise ValueError("annotation scores must be probabilities between zero and one")
        return self


class FecesCropReference(StrictModel):
    """Lazy crop contract passed from detection to feces appearance classification."""

    source_video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    timestamp_s: float = Field(ge=0)
    bbox: NormalizedBoundingBox
    color_space: Literal["RGB"] = "RGB"
    # 320 matches the committed dropping4_yolo11n_320 model; historical
    # assessments persisted 224 and must remain readable.
    target_width: int = 320
    target_height: int = 320
    materialized: bool = False


class FecesClassifierModel(StrictModel):
    """Provenance of the feces appearance model, whether or not it ran."""

    id: str
    version: str
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    format: str
    input_size: list[int]
    runtime: str


class FecesProvenance(StrictModel):
    """Where each stage of a feces candidate's evidence actually came from."""

    location_source: Literal["observed_video", "deterministic_overlay"]
    appearance_input: Literal["observed_crop", "curated_proxy"]
    classification_source: Literal["deterministic_mock", "live_model_run"]


class ProxySpecimenReference(StrictModel):
    """A curated proxy photo standing in for a feces crop from the video."""

    asset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    sha256: str
    content_url: str | None = None
    bytes_available: bool = False
    source_dataset: str
    source_url: str
    license: str
    attribution: str
    expected_demo_class: Literal[
        "cocci", "healthy", "ncd", "salmo", "unknown_abnormal"
    ]
    mapping_method: Literal["sha256-seeded"] = "sha256-seeded"
    substitution_reason: str

    @model_validator(mode="after")
    def _hash_is_placeholder_or_hex(self) -> ProxySpecimenReference:
        if self.sha256 != PROXY_SHA256_PLACEHOLDER and not re.fullmatch(
            _SHA256_PATTERN, self.sha256
        ):
            raise ValueError(
                "proxy specimen sha256 must be a 64-character hex digest or the "
                f"placeholder {PROXY_SHA256_PLACEHOLDER!r}"
            )
        return self


class ProxySpecimenDatasetCount(StrictModel):
    """Metadata-only count for one source dataset in the proxy pool."""

    dataset: str
    count: int = Field(ge=0)


class ProxySpecimenPoolSummary(StrictModel):
    """Cheap inventory that never reads or decodes specimen image bytes."""

    total: int = Field(ge=0)
    selectable_total: int = Field(ge=0)
    bytes_present: int = Field(ge=0)
    verified_cached: int = Field(ge=0)
    by_expected_class: dict[str, int]
    selectable_by_expected_class: dict[str, int]
    by_dataset: list[ProxySpecimenDatasetCount]
    catalogs_supported: bool = True


class FecesClassification(StrictModel):
    label: Literal["Coccidiosis", "Healthy", "New Castle Disease", "Salmonella"] | None = None
    confidence: float = Field(ge=0, le=1)
    mode: Literal["mock", "real"]
    product_label: Literal["normal", "abnormal", "uncertain"] = "uncertain"
    scores: dict[str, float] = Field(default_factory=dict)
    input_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    model: FecesClassifierModel | None = None
    inference_performed: bool = False
    model_detection_bbox: NormalizedBoundingBox | None = None
    fallback_reason: Literal[
        "specimen_unavailable",
        "runtime_unavailable",
        "image_decode_failed",
        "model_inference_failed",
    ] | None = None


class FecesCandidateLifecycle(StrictModel):
    """Offline stationary-candidate lifecycle derived from sampled detections."""

    first_observed_s: float = Field(ge=0)
    confirmed_s: float = Field(ge=0)
    last_observed_s: float = Field(ge=0)
    active_until_s: float = Field(ge=0)
    canonical_bbox: NormalizedBoundingBox
    observation_count: int = Field(ge=2)
    persistence_basis: Literal["stationary_recurrence_across_sampled_frames"] = (
        "stationary_recurrence_across_sampled_frames"
    )

    @model_validator(mode="after")
    def _ordered_evidence_times(self) -> FecesCandidateLifecycle:
        if not (
            self.first_observed_s <= self.confirmed_s <= self.last_observed_s
            <= self.active_until_s
        ):
            raise ValueError("feces lifecycle timestamps must be ordered")
        return self


class FecesCandidate(StrictModel):
    id: str
    timestamp_s: float = Field(ge=0)
    bbox: NormalizedBoundingBox
    detection_confidence: float = Field(ge=0, le=1)
    crop: FecesCropReference
    classification: FecesClassification
    proxy_crop: ProxySpecimenReference | None = None
    provenance: FecesProvenance | None = None
    lifecycle: FecesCandidateLifecycle | None = None


class ClipFecesSummary(StrictModel):
    candidate_count: int = Field(ge=0)
    class_distribution: dict[
        Literal["Coccidiosis", "Healthy", "New Castle Disease", "Salmonella"], int
    ]
    candidates: list[FecesCandidate]


class ClipOverallSummary(StrictModel):
    review_state: Literal["synthetic-demo-only", "non-diagnostic-review"]
    notes: list[str]


class ClipPenAssessment(StrictModel):
    """Pen-level policy result computed from deterministic demo evidence."""

    state: Literal["normal", "watch", "review"]
    score: float = Field(ge=0, le=1)
    policy_id: Literal["demo-pen-v1"] = "demo-pen-v1"
    reasons: list[str]
    activity_contribution: float = Field(ge=0, le=1)
    feces_contribution: float = Field(ge=0, le=1)
    evidence_mode: Literal["hybrid_simulation"] = "hybrid_simulation"
    non_diagnostic: bool = True


class ClipSummary(StrictModel):
    activity: ClipActivitySummary
    appearance: ClipAppearanceSummary
    feces: ClipFecesSummary
    overall: ClipOverallSummary
    pen_assessment: ClipPenAssessment | None = None


class ClipAssessment(StrictModel):
    """One aggregate, pen-level result for an entire video clip."""

    schema_version: Literal[1] = 1
    id: str
    status: Literal["completed", "failed"]
    created_at: datetime = Field(default_factory=utc_now)
    video: ClipVideo
    modules: list[ClipModule]
    summary: ClipSummary
    video_annotations: list[VideoAnnotation] = Field(default_factory=list)
    non_diagnostic_notice: str
    profile: SimulationProfile = SimulationProfile.MIXED


class ClipAssessmentTarget(StrictModel):
    """Identity reported by the machine that actually executed an assessment."""

    executor: Literal["local", "qnx"]
    hostname: str | None = None
    system: str | None = None
    release: str | None = None
    machine: str | None = None
    runtime: str | None = None
    verified: bool = False
    detail: str | None = None


class ResourceTelemetrySample(StrictModel):
    """A truthful, point-in-time resource sample from the selected executor."""

    captured_at: datetime = Field(default_factory=utc_now)
    source: Literal["local", "qnx"]
    cpu_percent: float | None = Field(default=None, ge=0)
    ram_used_bytes: int | None = Field(default=None, ge=0)
    ram_total_bytes: int | None = Field(default=None, ge=0)
    process_cpu_percent: float | None = Field(default=None, ge=0)
    process_ram_bytes: int | None = Field(default=None, ge=0)
    detail: str | None = None


class ClipAssessmentJob(StrictModel):
    """Ephemeral progress state for one background clip assessment."""

    schema_version: Literal[1] = 1
    id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress_percent: int = Field(ge=0, le=100)
    stage: str
    message: str
    executor: Literal["local", "qnx"] = "local"
    requested_executor: Literal["local", "qnx"] = "local"
    effective_executor: Literal["local", "qnx"] | None = "local"
    target: ClipAssessmentTarget | None = None
    telemetry: ResourceTelemetrySample | None = None
    telemetry_history: list[ResourceTelemetrySample] = Field(default_factory=list)
    assessment_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class QnxEvidenceClaim(StrictModel):
    """One checked claim in the QNX target evidence document."""

    id: str
    status: Literal["verified", "os_supported_only", "planned", "unsupported_guard"]
    summary: str
    detail: dict[str, Any] | None = None


class QnxEvidenceDocument(StrictModel):
    """Checked, read-only QNX target evidence."""

    schema_version: Literal[1] = 1
    evidence_id: str
    verified_at: str
    thesis: str
    platform: dict[str, str]
    claims: list[QnxEvidenceClaim]


class QnxEvidenceResponse(StrictModel):
    """The checked evidence JSON plus per-claim status."""

    evidence: QnxEvidenceDocument
    claims: list[QnxEvidenceClaim]
