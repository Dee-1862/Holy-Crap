"""FastAPI surface for local simulation-lab clients."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .adapters import AdapterError
from .catalog import CatalogConflict
from .models import (
    AdapterCapability,
    CreateRunRequest,
    ErrorBody,
    ErrorResponse,
    HealthResponse,
    MediaAssetInfo,
    ModelArtifact,
    PenSnapshot,
    RunResult,
    Scenario,
    SimulationRun,
    SystemCapabilities,
    TimelinePoint,
    VeriImportRequest,
)
from .service import NotFoundError, SimulationService


def _error(status: int, code: str, message: str, details: list[dict] | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json", exclude_none=True))


def create_app(
    home: Path | None = None,
    scenario_directory: Path | None = None,
    demo_assets_directory: Path | None = None,
    qnx_runner=None,
    qnx_prober=None,
) -> FastAPI:
    resolved_home = home or Path(os.getenv("HOLY_CRAP_HOME", ".simlab"))
    service = SimulationService(
        resolved_home,
        scenario_directory,
        demo_assets_directory=demo_assets_directory,
        qnx_runner=qnx_runner,
        qnx_prober=qnx_prober,
    )
    application = FastAPI(title="Holy Crap Simulation Lab", version="0.1.0")
    application.state.service = service
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @application.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return _error(404, "not_found", str(exc))

    @application.exception_handler(AdapterError)
    async def adapter_error_handler(_request: Request, exc: AdapterError) -> JSONResponse:
        return _error(422, "adapter_error", str(exc))

    @application.exception_handler(CatalogConflict)
    async def catalog_conflict_handler(_request: Request, exc: CatalogConflict) -> JSONResponse:
        return _error(422, "catalog_conflict", str(exc))

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": list(error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return _error(422, "validation_error", "request validation failed", details)

    @application.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/api/v1/system/capabilities", response_model=SystemCapabilities)
    def capabilities() -> SystemCapabilities:
        return SystemCapabilities(
            executors=[item.capability() for item in service.executors.values()],
            importers=[service.veri_importer.capability()],
        )

    @application.post("/api/v1/system/qnx/probe", response_model=AdapterCapability)
    def qnx_probe() -> AdapterCapability:
        return service.qnx_capability()

    @application.get("/api/v1/scenarios", response_model=list[Scenario])
    def scenarios() -> list[Scenario]:
        return service.scenarios.list()

    @application.get("/api/v1/models", response_model=list[ModelArtifact])
    def models() -> list[ModelArtifact]:
        return service.catalog.list_models()

    @application.post("/api/v1/models/upload", response_model=ModelArtifact, status_code=201)
    def upload_model(
        file: UploadFile = File(...),
        name: str = Form(..., min_length=1),
        version: str = Form(..., min_length=1),
        source: str = Form("upload"),
    ) -> ModelArtifact:
        filename = Path(file.filename or "model.bin").name
        return service.catalog.register_stream(
            file.file,
            name=name,
            version=version,
            filename=filename,
            source=source,
        )

    @application.post("/api/v1/models/import-veri", response_model=ModelArtifact, status_code=201)
    def import_veri(request: VeriImportRequest) -> ModelArtifact:
        return service.import_veri(Path(request.path))

    @application.get("/api/v1/runs", response_model=list[SimulationRun])
    def runs() -> list[SimulationRun]:
        return service.catalog.list_runs()

    @application.post("/api/v1/runs", response_model=SimulationRun, status_code=201)
    def create_run(request: CreateRunRequest) -> SimulationRun:
        return service.run(request)

    @application.get("/api/v1/runs/{run_id}", response_model=SimulationRun)
    def get_run(run_id: str) -> SimulationRun:
        return service.require_run(run_id)

    @application.get("/api/v1/runs/{run_id}/result", response_model=RunResult)
    def get_result(run_id: str) -> RunResult:
        return service.get_result(run_id)

    @application.get("/api/v1/runs/{run_id}/timeline", response_model=list[TimelinePoint])
    def get_timeline(run_id: str) -> list[TimelinePoint]:
        return service.timeline(run_id)

    @application.get("/api/v1/runs/{run_id}/snapshots", response_model=list[PenSnapshot])
    def get_snapshots(run_id: str) -> list[PenSnapshot]:
        return service.snapshots(run_id)

    @application.get("/api/v1/media", response_model=list[MediaAssetInfo])
    def media() -> list[MediaAssetInfo]:
        return service.media_assets()

    @application.get("/api/v1/media/{asset_id}/content")
    def media_content(asset_id: str) -> FileResponse:
        manifest = service.media_manifest(asset_id)
        if manifest is None:
            raise NotFoundError(f"media asset not found: {asset_id}")
        state = service.media_store.state(manifest)
        if not state.valid:
            raise NotFoundError(
                f"media content is not installed or failed hash verification: {asset_id}"
            )
        return FileResponse(state.path, media_type=manifest.media_type)

    return application
