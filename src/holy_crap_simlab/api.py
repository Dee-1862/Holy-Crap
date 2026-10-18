"""FastAPI surface for local simulation-lab clients."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .adapters import AdapterError
from .catalog import CatalogConflict
from .clip_assessment import ClipValidationError
from .models import (
    AdapterCapability,
    ClipAssessment,
    ClipAssessmentJob,
    CreateRunRequest,
    DatasetClip,
    ErrorBody,
    ErrorResponse,
    HealthResponse,
    MediaAssetInfo,
    ModelArtifact,
    PenSnapshot,
    ProxySpecimenPoolSummary,
    QnxEvidenceResponse,
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
    dataset_clips_directory: Path | None = None,
    qnx_runner=None,
    qnx_prober=None,
    proxy_specimens_directory: Path | None = None,
    qnx_evidence_path: Path | None = None,
    dataset_videos_directory: Path | None = None,
) -> FastAPI:
    resolved_home = home or Path(os.getenv("HOLY_CRAP_HOME", ".simlab"))
    service = SimulationService(
        resolved_home,
        scenario_directory,
        demo_assets_directory=demo_assets_directory,
        dataset_clips_directory=dataset_clips_directory,
        proxy_specimens_directory=proxy_specimens_directory,
        qnx_evidence_path=qnx_evidence_path,
        qnx_runner=qnx_runner,
        qnx_prober=qnx_prober,
        dataset_videos_directory=dataset_videos_directory,
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

    @application.exception_handler(ClipValidationError)
    async def clip_validation_error_handler(
        _request: Request, exc: ClipValidationError
    ) -> JSONResponse:
        return _error(422, "clip_validation_error", str(exc))

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

    @application.get("/api/v1/dataset-clips", response_model=list[DatasetClip])
    def dataset_clips() -> list[DatasetClip]:
        return service.list_dataset_clips()

    @application.get("/api/v1/dataset-clips/{clip_id}", response_model=DatasetClip)
    def get_dataset_clip(clip_id: str) -> DatasetClip:
        return service.require_dataset_clip(clip_id)

    @application.get("/api/v1/dataset-clips/{clip_id}/content")
    def dataset_clip_content(clip_id: str) -> FileResponse:
        _clip, path, media_type = service.dataset_clip_content_path(clip_id)
        return FileResponse(path, media_type=media_type)

    @application.get("/api/v1/clip-assessments", response_model=list[ClipAssessment])
    def clip_assessments() -> list[ClipAssessment]:
        return service.list_clip_assessments()

    @application.post(
        "/api/v1/clip-assessments/upload", response_model=ClipAssessment, status_code=201
    )
    def assess_uploaded_clip(
        file: UploadFile = File(...),
        profile: Literal["healthy", "mixed", "concerning"] = Form("mixed"),
        segment_start_s: float | None = Form(None, ge=0),
        segment_end_s: float | None = Form(None, gt=0),
        executor: Literal["local", "qnx"] = Form("local"),
    ) -> ClipAssessment:
        filename = file.filename or ""
        media_type = file.content_type or ""
        return service.assess_clip_upload(
            file.file,
            filename,
            media_type,
            profile,
            segment_start_s,
            segment_end_s,
            executor=executor,
        )

    @application.post(
        "/api/v1/clip-assessments/demo/{asset_id}",
        response_model=ClipAssessment,
        status_code=201,
    )
    def assess_demo_clip(
        asset_id: str,
        profile: Literal["healthy", "mixed", "concerning"] = Query("mixed"),
        segment_start_s: float | None = Query(None, ge=0),
        segment_end_s: float | None = Query(None, gt=0),
        executor: Literal["local", "qnx"] = Query("local"),
    ) -> ClipAssessment:
        return service.assess_demo_clip(
            asset_id, profile, segment_start_s, segment_end_s, executor=executor
        )

    @application.post(
        "/api/v1/clip-assessments/catalog/{clip_id}",
        response_model=ClipAssessment,
        status_code=201,
    )
    def assess_catalog_clip(
        clip_id: str,
        profile: Literal["healthy", "mixed", "concerning"] = Query("mixed"),
        segment_start_s: float | None = Query(None, ge=0),
        segment_end_s: float | None = Query(None, gt=0),
        executor: Literal["local", "qnx"] = Query("local"),
    ) -> ClipAssessment:
        return service.assess_catalog_clip(
            clip_id, profile, segment_start_s, segment_end_s, executor=executor
        )

    @application.post(
        "/api/v1/clip-assessment-jobs/upload",
        response_model=ClipAssessmentJob,
        status_code=202,
    )
    def start_uploaded_clip_assessment(
        file: UploadFile = File(...),
        profile: Literal["healthy", "mixed", "concerning"] = Form("mixed"),
        segment_start_s: float | None = Form(None, ge=0),
        segment_end_s: float | None = Form(None, gt=0),
        executor: Literal["local", "qnx"] = Form("local"),
    ) -> ClipAssessmentJob:
        return service.start_clip_upload_assessment_job(
            file.file,
            file.filename or "",
            file.content_type or "",
            profile,
            segment_start_s,
            segment_end_s,
            executor,
        )

    @application.post(
        "/api/v1/clip-assessment-jobs/demo/{asset_id}",
        response_model=ClipAssessmentJob,
        status_code=202,
    )
    def start_demo_clip_assessment(
        asset_id: str,
        profile: Literal["healthy", "mixed", "concerning"] = Query("mixed"),
        segment_start_s: float | None = Query(None, ge=0),
        segment_end_s: float | None = Query(None, gt=0),
        executor: Literal["local", "qnx"] = Query("local"),
    ) -> ClipAssessmentJob:
        return service.start_demo_clip_assessment_job(
            asset_id, profile, segment_start_s, segment_end_s, executor
        )

    @application.post(
        "/api/v1/clip-assessment-jobs/catalog/{clip_id}",
        response_model=ClipAssessmentJob,
        status_code=202,
    )
    def start_catalog_clip_assessment(
        clip_id: str,
        profile: Literal["healthy", "mixed", "concerning"] = Query("mixed"),
        segment_start_s: float | None = Query(None, ge=0),
        segment_end_s: float | None = Query(None, gt=0),
        executor: Literal["local", "qnx"] = Query("local"),
    ) -> ClipAssessmentJob:
        return service.start_catalog_clip_assessment_job(
            clip_id, profile, segment_start_s, segment_end_s, executor
        )

    @application.get(
        "/api/v1/clip-assessment-jobs/{job_id}",
        response_model=ClipAssessmentJob,
    )
    def get_clip_assessment_job(job_id: str) -> ClipAssessmentJob:
        return service.require_clip_assessment_job(job_id)

    @application.get(
        "/api/v1/clip-assessments/{assessment_id}", response_model=ClipAssessment
    )
    def get_clip_assessment(assessment_id: str) -> ClipAssessment:
        return service.require_clip_assessment(assessment_id)

    @application.get("/api/v1/clip-assessments/{assessment_id}/content")
    def clip_assessment_content(assessment_id: str) -> FileResponse:
        assessment, path = service.clip_content_path(assessment_id)
        return FileResponse(path, media_type=assessment.video.media_type)

    @application.get("/api/v1/proxy-specimens", response_model=ProxySpecimenPoolSummary)
    def proxy_specimens() -> ProxySpecimenPoolSummary:
        return service.proxy_specimen_summary()

    @application.get("/api/v1/proxy-specimens/{asset_id}/content")
    def proxy_specimen_content(asset_id: str) -> FileResponse:
        manifest, path = service.proxy_specimen_content(asset_id)
        return FileResponse(path, media_type=manifest.media_type)

    @application.get("/api/v1/system/qnx/evidence", response_model=QnxEvidenceResponse)
    def qnx_evidence() -> QnxEvidenceResponse:
        return service.qnx_evidence()

    return application
