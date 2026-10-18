"""Application service joining scenarios, adapters, and persisted experiment records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from .adapters import AdapterError, MockExecutor, QnxExecutor, VeriArtifactImporter
from .catalog import Catalog, atomic_json, safe_part
from .media import DemoAssetManifest, DemoAssetRepository, DemoAssetStore
from .models import (
    AdapterCapability,
    CreateRunRequest,
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


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
                started_at=_parse_iso(receipt.get("started_at")) or run.created_at,
                finished_at=_parse_iso(receipt.get("finished_at")),
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
                    installed=state.installed,
                    verified=state.valid,
                    size_bytes=state.size_bytes,
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
