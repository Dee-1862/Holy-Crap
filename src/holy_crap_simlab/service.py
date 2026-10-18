"""Application service joining scenarios, adapters, and persisted experiment records."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

from .adapters import AdapterError, MockExecutor, QnxExecutor, VeriArtifactImporter
from .catalog import Catalog
from .models import (
    CreateRunRequest,
    ModelArtifact,
    PenSnapshot,
    ResultArtifact,
    ResultExecutorReference,
    ResultMetrics,
    ResultModelReference,
    ResultScenarioReference,
    RunResult,
    RunStatus,
    SimulationRun,
    TimelinePoint,
    utc_now,
)
from .scenarios import ScenarioRepository


class NotFoundError(LookupError):
    pass


class SimulationService:
    def __init__(self, home: Path, scenario_directory: Path | None = None) -> None:
        self.catalog = Catalog(home)
        self.scenarios = ScenarioRepository(scenario_directory)
        self.executors = {executor.id: executor for executor in (MockExecutor(), QnxExecutor())}
        self.veri_importer = VeriArtifactImporter(self.catalog)
        self.catalog.seed_mock_model()

    def run(self, request: CreateRunRequest) -> SimulationRun:
        scenario = self.scenarios.get(request.scenario_id)
        if scenario is None:
            raise NotFoundError(f"scenario not found: {request.scenario_id}")
        model = self.catalog.get_model(request.model_id)
        if model is None:
            raise NotFoundError(f"model not found: {request.model_id}")
        executor = self.executors[request.executor]
        if executor.capability().status != "ready":
            raise AdapterError(f"executor not configured: {request.executor}")
        run = SimulationRun(
            id=str(uuid.uuid4()),
            status="running",
            scenario_id=scenario.id,
            model_id=model.id,
            executor=executor.id,
        )
        self.catalog.save_run(run)
        try:
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
                    executor=ResultExecutorReference(name="mock", version="0.1.0"),
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

    def require_run(self, run_id: str) -> SimulationRun:
        run = self.catalog.get_run(run_id)
        if run is None:
            raise NotFoundError(f"run not found: {run_id}")
        return run

    def timeline(self, run_id: str) -> list[TimelinePoint]:
        self.require_run(run_id)
        return self.catalog.get_timeline(run_id) or []

    def snapshots(self, run_id: str) -> list[PenSnapshot]:
        self.require_run(run_id)
        return self.catalog.get_snapshots(run_id) or []

    def import_veri(self, path: Path) -> ModelArtifact:
        return self.veri_importer.import_directory(path)
