"""Application service joining scenarios, adapters, and persisted experiment records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

from .adapters import AdapterError, MockExecutor, QnxExecutor, VeriArtifactImporter
from .catalog import Catalog, atomic_json, safe_part
from .clip_assessment import ClipAssessmentService, ClipValidationError
from .dataset_library import DatasetClipRepository
from .media import DemoAssetManifest, DemoAssetRepository, DemoAssetStore
from .models import (
    AdapterCapability,
    ClipAssessment,
    CreateRunRequest,
    DatasetClip,
    MediaAssetInfo,
    ModelArtifact,
    PenSnapshot,
    ResultArtifact,
    ResultExecutorReference,
    ResultMetrics,
    ResultModelReference,
    ResultScenarioReference,
    RunResult,
    RunStatus,
    Scenario,
    SimulationRun,
    TimelinePoint,
    utc_now,
)
from .scenarios import ScenarioRepository


class NotFoundError(LookupError):
    pass


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class SimulationService:
    def __init__(
        self,
        home: Path,
        scenario_directory: Path | None = None,
        demo_assets_directory: Path | None = None,
        dataset_clips_directory: Path | None = None,
        qnx_runner=None,
        qnx_prober=None,
    ) -> None:
        self.catalog = Catalog(home)
        self.scenarios = ScenarioRepository(scenario_directory)
        self.qnx = QnxExecutor(
            qnx_runner,
            catalog=self.catalog,
            scenario_directory=self.scenarios.directory,
            prober=qnx_prober,
        )
        self.executors = {executor.id: executor for executor in (MockExecutor(), self.qnx)}
        self.veri_importer = VeriArtifactImporter(self.catalog)
        self.catalog.seed_mock_model()
        self.media_repository = DemoAssetRepository(demo_assets_directory)
        self.media_store = DemoAssetStore(home)
        self.clip_assessments = ClipAssessmentService(home)
        self.dataset_clips = DatasetClipRepository(dataset_clips_directory)

    def run(self, request: CreateRunRequest) -> SimulationRun:
        scenario = self.scenarios.get(request.scenario_id)
        if scenario is None:
            raise NotFoundError(f"scenario not found: {request.scenario_id}")
        model = self.catalog.get_model(request.model_id)
        if model is None:
            raise NotFoundError(f"model not found: {request.model_id}")
        executor = self.executors[request.executor]
        capability = executor.capability()
        if request.executor == "qnx":
            if capability.status not in ("ready", "probe_only"):
                raise AdapterError(f"executor not configured: {request.executor}")
            if model.size_bytes == 0:
                raise AdapterError(
                    "the built-in zero-byte mock model cannot run on the QNX target; "
                    "register a real model artifact first"
                )
        elif capability.status != "ready":
            raise AdapterError(f"executor not configured: {request.executor}")
        run = SimulationRun(
            id=str(uuid.uuid4()),
            status=RunStatus.RUNNING,
            scenario_id=scenario.id,
            model_id=model.id,
            executor=executor.id,
        )
        self.catalog.save_run(run)
        try:
            if request.executor == "qnx":
                return self._finish_qnx_run(run, scenario, model, executor)
            result = executor.execute(scenario, model)
            run = run.model_copy(update={"status": RunStatus.COMPLETED, "metrics": result.metrics})
            self.catalog.save_run(run, result.timeline, result.snapshots)
            timeline_sha, timeline_size = self.catalog.result_artifact(run.id, "timeline.json")
            snapshots_sha, snapshots_size = self.catalog.result_artifact(run.id, "snapshots.json")
            scenario_payload = scenario.model_dump(
                mode="json", exclude={"pen_width_m", "pen_height_m"}
            )
            scenario_sha = hashlib.sha256(
                json.dumps(scenario_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            self.catalog.save_result(
                RunResult(
                    run_id=run.id,
                    evaluation_kind="prediction",
                    model=ResultModelReference(
                        name=model.name,
                        version=model.version,
                        sha256=model.sha256 or hashlib.sha256(model.id.encode()).hexdigest(),
                    ),
                    scenario=ResultScenarioReference(
                        id=scenario.id,
                        sha256=scenario_sha,
                        seed=scenario.seed,
                    ),
                    executor=ResultExecutorReference(name=executor.id, version=executor.version),
                    created_at=run.created_at,
                    started_at=run.created_at,
                    finished_at=utc_now(),
                    status="completed",
                    metrics=ResultMetrics.model_validate(
                        result.metrics.model_dump(exclude={"schema_version"})
                    ),
                    artifacts=[
                        ResultArtifact(
                            kind="timeline",
                            path="timeline.json",
                            sha256=timeline_sha,
                            media_type="application/json",
                            size_bytes=timeline_size,
                        ),
                        ResultArtifact(
                            kind="snapshots",
                            path="snapshots.json",
                            sha256=snapshots_sha,
                            media_type="application/json",
                            size_bytes=snapshots_size,
                        ),
                    ],
                    error=None,
                )
            )
        except Exception as exc:
            failed = run.model_copy(update={"status": RunStatus.FAILED, "error": str(exc)})
            self.catalog.save_run(failed)
            raise
        return run

    def _finish_qnx_run(
        self, run: SimulationRun, scenario: Scenario, model: ModelArtifact, executor: QnxExecutor
    ) -> SimulationRun:
        outcome = executor.validate_target(scenario, model, run.id)
        host_finished_at = utc_now()
        receipt = outcome.receipt
        if receipt.get("run_id") != run.id:
            raise AdapterError("QNX receipt run_id does not match the requested run")
        if receipt.get("inference_performed") is not False:
            raise AdapterError("QNX receipt must report inference_performed=false")
        directory = self.catalog.runs_dir / safe_part(run.id)
        atomic_json(directory / "receipt.json", receipt)
        _write_text(directory / "run.log", outcome.helper_output)
        scenario_path = executor.canonical_scenario_path(scenario)
        scenario_sha = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
        run = run.model_copy(update={"status": RunStatus.COMPLETED})
        self.catalog.save_run(run, [], [])
        receipt_sha, receipt_size = self.catalog.result_artifact(run.id, "receipt.json")
        log_sha, log_size = self.catalog.result_artifact(run.id, "run.log")
        platform = receipt.get("platform") if isinstance(receipt.get("platform"), dict) else {}
        target_parts = [
            part for part in (platform.get("system"), platform.get("release")) if isinstance(part, str) and part
        ]
        target = " ".join(target_parts) or None
        machine = platform.get("machine")
        if isinstance(machine, str) and machine:
            target = f"{target} ({machine})" if target else machine
        python = platform.get("python_version")
        runtime = f"Python {python}" if isinstance(python, str) and python else None
        self.catalog.save_result(
            RunResult(
                run_id=run.id,
                evaluation_kind="target_probe",
                model=ResultModelReference(
                    name=model.name,
                    version=model.version,
                    sha256=model.sha256 or hashlib.sha256(model.id.encode()).hexdigest(),
                ),
                scenario=ResultScenarioReference(
                    id=scenario.id,
                    sha256=scenario_sha,
                    seed=scenario.seed,
                ),
                executor=ResultExecutorReference(
                    name=executor.id,
                    version=executor.version,
                    target=target,
                    runtime=runtime,
                ),
                created_at=run.created_at,
                # QNX target clocks may be unset after boot. The user-facing
                # run envelope therefore uses the lab host's UTC clock. Raw
                # target timestamps remain unchanged in receipt.json.
                started_at=run.created_at,
                finished_at=host_finished_at,
                status="completed",
                metrics=None,
                artifacts=[
                    ResultArtifact(
                        kind="report",
                        path="receipt.json",
                        sha256=receipt_sha,
                        media_type="application/json",
                        size_bytes=receipt_size,
                    ),
                    ResultArtifact(
                        kind="log",
                        path="run.log",
                        sha256=log_sha,
                        media_type="text/plain",
                        size_bytes=log_size,
                    ),
                ],
                error=None,
            )
        )
        return run

    def require_run(self, run_id: str) -> SimulationRun:
        run = self.catalog.get_run(run_id)
        if run is None:
            raise NotFoundError(f"run not found: {run_id}")
        return run

    def get_result(self, run_id: str) -> RunResult:
        self.require_run(run_id)
        result = self.catalog.get_result(run_id)
        if result is None:
            raise NotFoundError(f"result not found for run: {run_id}")
        return result

    def timeline(self, run_id: str) -> list[TimelinePoint]:
        self.require_run(run_id)
        return self.catalog.get_timeline(run_id) or []

    def snapshots(self, run_id: str) -> list[PenSnapshot]:
        self.require_run(run_id)
        return self.catalog.get_snapshots(run_id) or []

    def import_veri(self, path: Path) -> ModelArtifact:
        return self.veri_importer.import_directory(path)

    def qnx_capability(self) -> AdapterCapability:
        return self.executors["qnx"].capability()

    def media_manifest(self, asset_id: str) -> DemoAssetManifest | None:
        return self.media_repository.get(asset_id)

    def media_assets(self) -> list[MediaAssetInfo]:
        assets: list[MediaAssetInfo] = []
        for manifest in self.media_repository.list():
            state = self.media_store.state(manifest)
            assets.append(
                MediaAssetInfo(
                    id=manifest.id,
                    title=manifest.title,
                    description=manifest.description,
                    media_type=manifest.media_type,
                    width=manifest.width,
                    height=manifest.height,
                    filename=manifest.filename,
                    sha256=manifest.sha256,
                    expected_size_bytes=manifest.file_size_bytes,
                    installed=state.installed,
                    verified=state.valid,
                    size_bytes=state.size_bytes,
                    duration_s=manifest.duration_s,
                    frame_rate_fps=manifest.frame_rate_fps,
                    frame_count=manifest.frame_count,
                    codec=manifest.codec,
                    content_url=f"/api/v1/media/{manifest.id}/content",
                    source_url=str(manifest.source_url),
                    dataset_url=str(manifest.dataset_url),
                    doi=manifest.doi,
                    license=str(manifest.license),
                    license_url=str(manifest.license_url),
                    attribution=manifest.attribution,
                    creators=list(manifest.creators),
                    limitations=list(manifest.limitations),
                )
            )
        return assets

    def assess_clip_upload(self, stream, filename: str, media_type: str) -> ClipAssessment:
        return self.clip_assessments.assess_upload(stream, filename, media_type)

    def assess_demo_clip(self, asset_id: str) -> ClipAssessment:
        manifest = self.media_manifest(asset_id)
        if manifest is None:
            raise NotFoundError(f"media asset not found: {asset_id}")
        if not manifest.media_type.startswith("video/"):
            raise ClipValidationError(f"demo media is not a video: {asset_id}")
        state = self.media_store.state(manifest)
        if not state.valid:
            raise NotFoundError(
                f"media content is not installed or failed hash verification: {asset_id}"
            )
        if any(
            value is None
            for value in (
                manifest.duration_s,
                manifest.frame_rate_fps,
            )
        ):
            raise ClipValidationError(f"demo video metadata is incomplete: {asset_id}")
        return self.clip_assessments.assess_demo(
            path=state.path,
            filename=manifest.filename,
            media_type=manifest.media_type,
            asset_id=manifest.id,
            duration_s=manifest.duration_s,
            width=manifest.width,
            height=manifest.height,
            fps=manifest.frame_rate_fps,
        )

    def list_clip_assessments(self) -> list[ClipAssessment]:
        return self.clip_assessments.store.list()

    def list_dataset_clips(self) -> list[DatasetClip]:
        return [self._dataset_clip_state(clip) for clip in self.dataset_clips.list()]

    def require_dataset_clip(self, clip_id: str) -> DatasetClip:
        clip = self.dataset_clips.get(clip_id)
        if clip is None:
            raise NotFoundError(f"dataset clip not found: {clip_id}")
        return self._dataset_clip_state(clip)

    def _dataset_clip_state(self, clip: DatasetClip) -> DatasetClip:
        if not clip.demo_asset_id:
            return clip
        manifest = self.media_manifest(clip.demo_asset_id)
        if manifest is None:
            return clip
        state = self.media_store.state(manifest)
        if not state.valid:
            return clip
        return clip.model_copy(
            update={
                "bytes_available": True,
                "content_url": f"/api/v1/media/{manifest.id}/content",
                "expected_size_bytes": state.size_bytes,
            }
        )

    def assess_catalog_clip(self, clip_id: str) -> ClipAssessment:
        clip = self.require_dataset_clip(clip_id)
        if not clip.assessable:
            raise ClipValidationError(
                f"catalog entry {clip.id!r} is {clip.status} and cannot be assessed"
            )
        if clip.bytes_available and clip.demo_asset_id:
            return self.assess_demo_clip(clip.demo_asset_id)
        synthetic_sha256 = self.dataset_clips.synthetic_sha256(clip)
        return self.clip_assessments.assess_catalog_mock(clip, synthetic_sha256)

    def require_clip_assessment(self, assessment_id: str) -> ClipAssessment:
        result = self.clip_assessments.store.get(assessment_id)
        if result is None:
            raise NotFoundError(f"clip assessment not found: {assessment_id}")
        return result

    def clip_content_path(self, assessment_id: str) -> tuple[ClipAssessment, Path]:
        assessment = self.require_clip_assessment(assessment_id)
        return assessment, self.clip_assessments.store.content_path(assessment)
