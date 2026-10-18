"""Application service joining scenarios, adapters, and persisted experiment records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from .adapters import AdapterError, MockExecutor, QnxExecutor, VeriArtifactImporter
from .catalog import Catalog, atomic_json, safe_part
from .clip_assessment import (
    ClipAssessmentService,
    ClipValidationError,
    VideoProbe,
    probe_video,
)
from .dataset_library import DatasetClipRepository
from .dataset_videos import DatasetVideoLookupError, LocalDatasetVideoStore
from .farmer_alerts import FarmerAlertNotifier
from .media import DemoAssetManifest, DemoAssetRepository, DemoAssetStore
from .models import (
    AdapterCapability,
    ClipAssessment,
    ClipAssessmentJob,
    ClipAssessmentTarget,
    CreateRunRequest,
    DatasetClip,
    MediaAssetInfo,
    ModelArtifact,
    PenSnapshot,
    ProxySpecimenPoolSummary,
    QnxEvidenceDocument,
    QnxEvidenceResponse,
    ResultArtifact,
    ResultExecutorReference,
    ResultMetrics,
    ResultModelReference,
    ResultScenarioReference,
    ResourceTelemetrySample,
    RunResult,
    RunStatus,
    Scenario,
    SimulationRun,
    TimelinePoint,
    utc_now,
)
from .proxy_specimens import ProxySpecimenManifest, ProxySpecimenRepository
from .qnx_runner import QnxRunnerError
from .scenarios import ScenarioRepository
from .telemetry import LocalTelemetrySampler, local_target_identity


class NotFoundError(LookupError):
    pass


class QnxAssessmentBlocked(RuntimeError):
    """The target was contacted but could not execute the configured contract."""


def default_qnx_evidence_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "target"
        / "qnx"
        / "evidence"
        / "dropping4-laptop-final-320.json"
    )


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
        proxy_specimens_directory: Path | None = None,
        qnx_evidence_path: Path | None = None,
        dataset_videos_directory: Path | None = None,
        farmer_alert_notifier: FarmerAlertNotifier | None = None,
    ) -> None:
        self.catalog = Catalog(home)
        self.scenarios = ScenarioRepository(scenario_directory)
        self.qnx = QnxExecutor(
            qnx_runner,
            catalog=self.catalog,
            scenario_directory=self.scenarios.directory,
            prober=qnx_prober,
        )
        self.qnx_runner = self.qnx.runner
        self.executors = {executor.id: executor for executor in (MockExecutor(), self.qnx)}
        self.veri_importer = VeriArtifactImporter(self.catalog)
        self.catalog.seed_mock_model()
        self.media_repository = DemoAssetRepository(demo_assets_directory)
        self.media_store = DemoAssetStore(home)
        self.proxy_repository = ProxySpecimenRepository(proxy_specimens_directory)
        self.clip_assessments = ClipAssessmentService(
            home, proxy_repository=self.proxy_repository
        )
        self.dataset_clips = DatasetClipRepository(dataset_clips_directory)
        self.dataset_videos = LocalDatasetVideoStore(
            root=dataset_videos_directory, home=home
        )
        self._dataset_video_probe_cache: dict[
            tuple[Path, int, int], VideoProbe
        ] = {}
        self._assessment_jobs: dict[str, ClipAssessmentJob] = {}
        self._assessment_jobs_lock = threading.Lock()
        self._assessment_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="clip-assessment"
        )
        self.qnx_evidence_path = qnx_evidence_path or default_qnx_evidence_path()
        self.farmer_alert_notifier = farmer_alert_notifier or FarmerAlertNotifier(
            evidence_dir=Path(home) / "farmer-evidence"
        )

    def close(self) -> None:
        self._assessment_executor.shutdown(wait=False, cancel_futures=True)

    def _update_assessment_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress_percent: int | None = None,
        stage: str | None = None,
        message: str | None = None,
        assessment_id: str | None = None,
        target: ClipAssessmentTarget | None = None,
        telemetry: ResourceTelemetrySample | None = None,
        telemetry_history: list[ResourceTelemetrySample] | None = None,
        effective_executor: str | None = None,
    ) -> ClipAssessmentJob:
        with self._assessment_jobs_lock:
            current = self._assessment_jobs[job_id]
            percent = current.progress_percent
            if progress_percent is not None:
                percent = max(percent, min(100, max(0, int(progress_percent))))
            updates = {
                "progress_percent": percent,
                "updated_at": utc_now(),
            }
            if status is not None:
                updates["status"] = status
            if stage is not None:
                updates["stage"] = stage
            if message is not None:
                updates["message"] = message
            if assessment_id is not None:
                updates["assessment_id"] = assessment_id
            if target is not None:
                updates["target"] = target
            if telemetry is not None:
                updates["telemetry"] = telemetry
                history = list(current.telemetry_history)
                if not history or history[-1].captured_at != telemetry.captured_at:
                    history.append(telemetry)
                updates["telemetry_history"] = history[-240:]
            if telemetry_history is not None:
                updates["telemetry_history"] = telemetry_history[-240:]
                updates["telemetry"] = telemetry_history[-1] if telemetry_history else None
            if effective_executor is not None:
                updates["effective_executor"] = effective_executor
            updated = current.model_copy(update=updates)
            self._assessment_jobs[job_id] = updated
            return updated

    def _start_assessment_job(
        self,
        work: Callable[[str, Callable[[int, str, str], None]], ClipAssessment],
        *,
        executor: str = "local",
    ) -> ClipAssessmentJob:
        now = utc_now()
        job = ClipAssessmentJob(
            id=f"clip-job-{uuid.uuid4()}",
            status="queued",
            progress_percent=0,
            stage="queued",
            message="Assessment queued",
            executor=executor,
            requested_executor=executor,
            effective_executor="local" if executor == "local" else None,
            target=(
                local_target_identity()
                if executor == "local"
                else ClipAssessmentTarget(
                    executor="qnx",
                    hostname=self.qnx_runner.config.ssh_alias,
                    verified=False,
                    detail="QNX target identity is pending a verified worker receipt.",
                )
            ),
            created_at=now,
            updated_at=now,
        )
        with self._assessment_jobs_lock:
            self._assessment_jobs[job.id] = job

        def run() -> None:
            sampler = LocalTelemetrySampler() if executor == "local" else None
            self._update_assessment_job(
                job.id,
                status="running",
                progress_percent=1,
                stage="preparing",
                message="Preparing assessment inputs",
                telemetry=sampler.sample(force=True) if sampler else None,
            )

            def progress(percent: int, stage: str, message: str) -> None:
                self._update_assessment_job(
                    job.id,
                    status="running",
                    progress_percent=percent,
                    stage=stage,
                    message=message,
                    telemetry=sampler.sample() if sampler else None,
                )

            try:
                assessment = work(job.id, progress)
            except Exception as exc:  # keep background failures observable to the UI
                blocked = isinstance(exc, QnxAssessmentBlocked) or (
                    executor == "qnx"
                    and "not deployment-ready" in str(exc)
                )
                self._update_assessment_job(
                    job.id,
                    status="failed",
                    stage="blocked" if blocked else "failed",
                    message=str(exc) or "Assessment failed",
                    telemetry=sampler.sample(force=True) if sampler else None,
                )
                return
            try:
                try:
                    video_path = self.clip_assessments.store.content_path(assessment)
                except ClipValidationError:
                    video_path = None
                farmer_alert = self.farmer_alert_notifier.notify(
                    assessment, video_path=video_path
                )
            except Exception:
                farmer_alert = "failed"
            alert_message = {
                "sent": "Assessment complete; farmer text sent",
                "skipped": "Assessment complete; no farmer text needed",
                "failed": "Assessment complete; farmer text could not be sent",
            }[farmer_alert]
            self._update_assessment_job(
                job.id,
                status="completed",
                progress_percent=100,
                stage="completed",
                message=alert_message,
                assessment_id=assessment.id,
                telemetry=sampler.sample(force=True) if sampler else None,
            )

        self._assessment_executor.submit(run)
        return job

    def require_clip_assessment_job(self, job_id: str) -> ClipAssessmentJob:
        with self._assessment_jobs_lock:
            job = self._assessment_jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"clip assessment job not found: {job_id}")
        return job

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

    @staticmethod
    def _validate_clip_executor(executor: str) -> None:
        if executor not in ("local", "qnx"):
            raise ClipValidationError("executor must be 'local' or 'qnx'")

    @classmethod
    def _require_synchronous_local(cls, executor: str) -> None:
        cls._validate_clip_executor(executor)
        if executor == "qnx":
            raise ClipValidationError(
                "QNX clip execution requires the asynchronous clip-assessment job endpoint "
                "so target progress, identity, and telemetry remain observable"
            )

    def _qnx_assessment_work(
        self, video_path: Path, request: dict
    ) -> Callable[[str, Callable[[int, str, str], None]], ClipAssessment]:
        """Build a fail-closed QNX job; this closure never calls local inference."""

        def work(
            job_id: str, progress: Callable[[int, str, str], None]
        ) -> ClipAssessment:
            def live_telemetry(samples: list[dict]) -> None:
                parsed = [ResourceTelemetrySample.model_validate(sample) for sample in samples]
                self._update_assessment_job(job_id, telemetry_history=parsed)

            try:
                outcome = self.qnx_runner.assess_clip_on_target(
                    job_id=job_id,
                    video_path=video_path,
                    request=request,
                    progress=progress,
                    telemetry=live_telemetry,
                )
            except QnxRunnerError as exc:
                raise RuntimeError(str(exc)) from exc
            target = ClipAssessmentTarget.model_validate(outcome.target)
            if (
                target.executor != "qnx"
                or target.system != "QNX"
                or target.verified is not True
            ):
                raise RuntimeError(
                    "QNX clip result did not prove a verified QNX executor identity"
                )
            telemetry = [
                ResourceTelemetrySample.model_validate(sample)
                for sample in outcome.telemetry_history
            ]
            self._update_assessment_job(
                job_id,
                target=target,
                telemetry_history=telemetry,
                effective_executor="qnx",
            )
            if outcome.status == "blocked":
                raise QnxAssessmentBlocked(outcome.message)
            if outcome.status != "completed":
                raise RuntimeError(outcome.message)
            try:
                assessment = ClipAssessment.model_validate(outcome.assessment)
            except Exception as exc:
                raise RuntimeError(
                    "QNX worker returned an invalid clip assessment: %s" % exc
                ) from exc
            self.clip_assessments.store.save(assessment)
            return assessment

        return work

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

    def assess_clip_upload(
        self, stream, filename: str, media_type: str, profile: str = "mixed",
        segment_start_s: float | None = None,
        segment_end_s: float | None = None,
        progress: Callable[[int, str, str], None] | None = None,
        executor: str = "local",
    ) -> ClipAssessment:
        self._require_synchronous_local(executor)
        return self.clip_assessments.assess_upload(
            stream, filename, media_type, profile, segment_start_s, segment_end_s, progress
        )

    def start_clip_upload_assessment_job(
        self, stream, filename: str, media_type: str, profile: str = "mixed",
        segment_start_s: float | None = None,
        segment_end_s: float | None = None,
        executor: str = "local",
    ) -> ClipAssessmentJob:
        # Ingest synchronously while UploadFile is valid; expensive inference runs later.
        self._validate_clip_executor(executor)
        stored = self.clip_assessments.store.ingest_stream(
            stream, filename=filename, media_type=media_type
        )
        if executor == "qnx":
            return self._start_assessment_job(
                self._qnx_assessment_work(
                    stored.path,
                    {
                        "source": "upload",
                        "filename": filename,
                        "media_type": media_type,
                        "profile": profile,
                        "segment_start_s": segment_start_s,
                        "segment_end_s": segment_end_s,
                    },
                ),
                executor="qnx",
            )
        return self._start_assessment_job(
            lambda _job_id, progress: self.clip_assessments.assess_stored_upload(
                stored, filename, media_type, profile, segment_start_s, segment_end_s, progress
            ),
            executor="local",
        )

    def assess_demo_clip(
        self, asset_id: str, profile: str = "mixed",
        segment_start_s: float | None = None,
        segment_end_s: float | None = None,
        progress: Callable[[int, str, str], None] | None = None,
        executor: str = "local",
    ) -> ClipAssessment:
        self._require_synchronous_local(executor)
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
            profile=profile,
            segment_start_s=segment_start_s,
            segment_end_s=segment_end_s,
            progress=progress,
        )

    def start_demo_clip_assessment_job(
        self, asset_id: str, profile: str = "mixed",
        segment_start_s: float | None = None,
        segment_end_s: float | None = None,
        executor: str = "local",
    ) -> ClipAssessmentJob:
        # Validate before returning 202 so bad IDs/ranges remain normal API errors.
        self._validate_clip_executor(executor)
        manifest = self.media_manifest(asset_id)
        if manifest is None:
            raise NotFoundError(f"media asset not found: {asset_id}")
        state = self.media_store.state(manifest)
        if not state.valid:
            raise NotFoundError(
                f"media content is not installed or failed hash verification: {asset_id}"
            )
        if executor == "qnx":
            return self._start_assessment_job(
                self._qnx_assessment_work(
                    state.path,
                    {
                        "source": "demo",
                        "asset_id": asset_id,
                        "filename": manifest.filename,
                        "media_type": manifest.media_type,
                        "profile": profile,
                        "segment_start_s": segment_start_s,
                        "segment_end_s": segment_end_s,
                    },
                ),
                executor="qnx",
            )
        return self._start_assessment_job(
            lambda _job_id, progress: self.assess_demo_clip(
                asset_id, profile, segment_start_s, segment_end_s, progress
            ),
            executor="local",
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
        if clip.demo_asset_id:
            manifest = self.media_manifest(clip.demo_asset_id)
            if manifest is not None:
                state = self.media_store.state(manifest)
                if state.valid:
                    return clip.model_copy(
                        update={
                            "bytes_available": True,
                            "content_url": f"/api/v1/media/{manifest.id}/content",
                            "expected_size_bytes": state.size_bytes,
                            "installed_size_bytes": state.size_bytes,
                            "duration_s": clip.duration_s or manifest.duration_s,
                            "width": clip.width or manifest.width,
                            "height": clip.height or manifest.height,
                            "fps": clip.fps or manifest.frame_rate_fps,
                        }
                    )
        if clip.filename:
            try:
                video = self.dataset_videos.find(clip.filename)
            except DatasetVideoLookupError:
                return clip
            if video is not None:
                metadata = self._probe_dataset_video(video.path)
                return clip.model_copy(
                    update={
                        "bytes_available": True,
                        "content_url": f"/api/v1/dataset-clips/{clip.id}/content",
                        "installed_size_bytes": video.size_bytes,
                        "duration_s": clip.duration_s or metadata.duration_s,
                        "width": clip.width or metadata.width,
                        "height": clip.height or metadata.height,
                        "fps": clip.fps or metadata.fps,
                    }
                )
        return clip

    def _probe_dataset_video(self, path: Path) -> VideoProbe:
        """Read local container metadata once per unchanged installed file."""

        try:
            stat = path.stat()
        except OSError:
            return VideoProbe(warnings=("installed dataset video could not be inspected",))
        key = (path, stat.st_size, stat.st_mtime_ns)
        cached = self._dataset_video_probe_cache.get(key)
        if cached is not None:
            return cached
        metadata = probe_video(path)
        self._dataset_video_probe_cache = {
            existing_key: value
            for existing_key, value in self._dataset_video_probe_cache.items()
            if existing_key[0] != path
        }
        # A failed or incomplete probe may be transient (for example ffprobe
        # was unavailable during startup), so only memoize useful metadata.
        if metadata.duration_s is not None:
            self._dataset_video_probe_cache[key] = metadata
        return metadata

    def dataset_clip_content_path(self, clip_id: str) -> tuple[DatasetClip, Path, str]:
        clip = self.dataset_clips.get(clip_id)
        if clip is None:
            raise NotFoundError(f"dataset clip not found: {clip_id}")
        if clip.demo_asset_id:
            manifest = self.media_manifest(clip.demo_asset_id)
            if manifest is not None:
                state = self.media_store.state(manifest)
                if state.valid:
                    return clip, state.path, manifest.media_type
        if not clip.filename:
            raise NotFoundError(f"dataset clip has no local video file: {clip_id}")
        try:
            video = self.dataset_videos.find(clip.filename)
        except DatasetVideoLookupError as exc:
            raise NotFoundError(
                f"dataset clip video is not safely available: {clip_id}"
            ) from exc
        if video is None:
            raise NotFoundError(f"dataset clip video is not installed locally: {clip_id}")
        return clip, video.path, clip.media_type or "application/octet-stream"

    def assess_catalog_clip(
        self, clip_id: str, profile: str = "mixed",
        segment_start_s: float | None = None,
        segment_end_s: float | None = None,
        progress: Callable[[int, str, str], None] | None = None,
        executor: str = "local",
    ) -> ClipAssessment:
        self._require_synchronous_local(executor)
        clip = self.require_dataset_clip(clip_id)
        if not clip.assessable:
            raise ClipValidationError(
                f"catalog entry {clip.id!r} is {clip.status} and cannot be assessed"
            )
        if clip.bytes_available and clip.demo_asset_id:
            return self.assess_demo_clip(
                clip.demo_asset_id, profile, segment_start_s, segment_end_s, progress
            )
        if clip.bytes_available:
            _, path, media_type = self.dataset_clip_content_path(clip.id)
            return self.clip_assessments.assess_dataset(
                clip=clip,
                path=path,
                media_type=media_type,
                profile=profile,
                segment_start_s=segment_start_s,
                segment_end_s=segment_end_s,
                progress=progress,
            )
        synthetic_sha256 = self.dataset_clips.synthetic_sha256(clip)
        return self.clip_assessments.assess_catalog_mock(
            clip, synthetic_sha256, profile, segment_start_s, segment_end_s, progress
        )

    def start_catalog_clip_assessment_job(
        self, clip_id: str, profile: str = "mixed",
        segment_start_s: float | None = None,
        segment_end_s: float | None = None,
        executor: str = "local",
    ) -> ClipAssessmentJob:
        self._validate_clip_executor(executor)
        clip = self.require_dataset_clip(clip_id)
        if not clip.assessable:
            raise ClipValidationError(
                f"catalog entry {clip.id!r} is {clip.status} and cannot be assessed"
            )
        if executor == "qnx":
            if not clip.bytes_available:
                raise ClipValidationError(
                    "QNX execution requires installed video bytes; catalog mocks cannot run on QNX"
                )
            _, path, media_type = self.dataset_clip_content_path(clip.id)
            return self._start_assessment_job(
                self._qnx_assessment_work(
                    path,
                    {
                        "source": "dataset",
                        "catalog_clip_id": clip.id,
                        "filename": clip.filename,
                        "media_type": media_type,
                        "profile": profile,
                        "segment_start_s": segment_start_s,
                        "segment_end_s": segment_end_s,
                    },
                ),
                executor="qnx",
            )
        return self._start_assessment_job(
            lambda _job_id, progress: self.assess_catalog_clip(
                clip_id, profile, segment_start_s, segment_end_s, progress
            ),
            executor="local",
        )

    def proxy_specimen(self, asset_id: str) -> ProxySpecimenManifest | None:
        return self.proxy_repository.get(asset_id)

    def proxy_specimen_summary(self) -> ProxySpecimenPoolSummary:
        return self.proxy_repository.summary()

    def proxy_specimen_content(self, asset_id: str) -> tuple[ProxySpecimenManifest, Path]:
        manifest = self.proxy_repository.get(asset_id)
        if manifest is None:
            raise NotFoundError(f"proxy specimen not found: {asset_id}")
        path = self.proxy_repository.verified_path(manifest)
        if path is None:
            raise NotFoundError(
                f"proxy specimen bytes are unavailable or failed hash verification: {asset_id}"
            )
        return manifest, path

    def qnx_evidence(self) -> QnxEvidenceResponse:
        if not self.qnx_evidence_path.is_file():
            raise NotFoundError("QNX evidence document is not available")
        document = QnxEvidenceDocument.model_validate_json(
            self.qnx_evidence_path.read_text(encoding="utf-8")
        )
        return QnxEvidenceResponse(evidence=document, claims=document.claims)

    def require_clip_assessment(self, assessment_id: str) -> ClipAssessment:
        result = self.clip_assessments.store.get(assessment_id)
        if result is None:
            raise NotFoundError(f"clip assessment not found: {assessment_id}")
        return result

    def clip_content_path(self, assessment_id: str) -> tuple[ClipAssessment, Path]:
        assessment = self.require_clip_assessment(assessment_id)
        return assessment, self.clip_assessments.store.content_path(assessment)
