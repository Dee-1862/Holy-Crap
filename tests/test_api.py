from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from holy_crap_simlab.api import create_app
from holy_crap_simlab.qnx_runner import (
    QnxClipAssessmentOutcome,
    QnxProbeReport,
    QnxRunnerConfig,
    QnxRunnerError,
    QnxValidationOutcome,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _qnx_network_guard(monkeypatch) -> None:
    monkeypatch.setenv("QNX_EXECUTOR_MODE", "disabled")


def probe_only_report() -> QnxProbeReport:
    return QnxProbeReport(
        reachable=True,
        python_version="3.14.0",
        runner_output="spool: /data/home/qnxuser/qnx-runner\nrunner: running (pid 1234)",
        runtime_presence={
            "tflite_runtime": False,
            "onnxruntime": False,
            "cv2": False,
            "numpy": False,
        },
        detail=(
            "QNX Pi probe: ssh=ok, python=3.14.0, runner=running, "
            "cv2=absent, numpy=absent, onnxruntime=absent, tflite_runtime=absent"
        ),
    )


class FakeQnxClient:
    """Genuine fake QnxRunner: builds a real receipt from the staged bytes, never touches SSH."""

    def __init__(
        self,
        failure: Exception | None = None,
        receipt_timestamps: tuple[str, str] = (
            "2026-10-17T20:00:00+00:00",
            "2026-10-17T20:00:01+00:00",
        ),
    ) -> None:
        self.config = QnxRunnerConfig(mode="probe")
        self.failure = failure
        self.receipt_timestamps = receipt_timestamps
        self.calls: list[dict] = []

    def validate_on_target(self, **kwargs) -> QnxValidationOutcome:
        self.calls.append(kwargs)
        if self.failure is not None:
            raise self.failure
        run_id = kwargs["run_id"]
        model_bytes = Path(kwargs["model_path"]).read_bytes()
        scenario_bytes = Path(kwargs["scenario_path"]).read_bytes()
        receipt = {
            "schema_version": 1,
            "run_id": run_id,
            "model": {
                "name": kwargs["model_name"],
                "sha256": hashlib.sha256(model_bytes).hexdigest(),
                "size_bytes": len(model_bytes),
            },
            "scenario": {
                "name": kwargs["scenario_name"],
                "sha256": hashlib.sha256(scenario_bytes).hexdigest(),
                "size_bytes": len(scenario_bytes),
            },
            "platform": {
                "system": "QNX",
                "machine": "aarch64le",
                "release": "8.0.0",
                "python_version": "3.14.0",
            },
            "started_at": self.receipt_timestamps[0],
            "finished_at": self.receipt_timestamps[1],
            "inference_performed": False,
            "inference_reason": "No QNX inference runtime is installed or configured.",
        }
        return QnxValidationOutcome(
            receipt=receipt,
            helper_output="submitted fake probe job to qnxpi\n",
            remote_run_dir="/data/home/qnxuser/simlab-runs/run-%s" % run_id,
        )


def qnx_client(
    tmp_path: Path,
    scenario_directory: Path,
    fake: FakeQnxClient,
    prober=None,
) -> TestClient:
    return TestClient(
        create_app(
            tmp_path / "simlab-qnx",
            scenario_directory,
            qnx_runner=fake,
            qnx_prober=prober or probe_only_report,
        )
    )


def test_health_capabilities_and_seed_data(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok", "schema_version": 1}
    capabilities = client.get("/api/v1/system/capabilities").json()
    assert {item["id"]: item["status"] for item in capabilities["executors"]} == {
        "mock": "ready",
        "qnx": "not_configured",
    }
    assert capabilities["importers"][0]["id"] == "veri-local"
    assert {item["id"] for item in client.get("/api/v1/scenarios").json()} == {
        "healthy-100",
        "outbreak-100",
        "pio-reference-100",
    }
    assert client.get("/api/v1/models").json()[0]["id"] == "mock-baseline"


def test_clip_assessment_job_reports_real_monotonic_progress(
    client: TestClient, monkeypatch
) -> None:
    service = client.app.state.service
    clip = next(item for item in service.list_dataset_clips() if item.assessable)
    template = service.clip_assessments.assess_catalog_mock(
        clip,
        service.dataset_clips.synthetic_sha256(clip),
        segment_start_s=0,
        segment_end_s=min(2, clip.duration_s or 2),
    )
    entered = threading.Event()
    release = threading.Event()

    def controlled_assessment(
        _clip_id,
        _profile="mixed",
        _segment_start_s=None,
        _segment_end_s=None,
        progress=None,
    ):
        progress(25, "detecting_chickens", "Located chickens in 1 of 4 frames")
        entered.set()
        assert release.wait(2)
        progress(80, "detecting_feces", "Checked feces candidates in 4 of 4 frames")
        return template

    monkeypatch.setattr(service, "assess_catalog_clip", controlled_assessment)
    response = client.post(
        f"/api/v1/clip-assessment-jobs/catalog/{clip.id}",
        params={"segment_start_s": 0, "segment_end_s": min(2, clip.duration_s or 2)},
    )
    assert response.status_code == 202
    created = response.json()
    assert created["progress_percent"] == 0
    assert entered.wait(2)
    running = client.get(f"/api/v1/clip-assessment-jobs/{created['id']}").json()
    assert running["status"] == "running"
    assert running["progress_percent"] == 25
    assert running["stage"] == "detecting_chickens"
    assert running["executor"] == "local"
    assert running["requested_executor"] == "local"
    assert running["effective_executor"] == "local"
    assert running["target"]["executor"] == "local"
    assert running["target"]["verified"] is True
    assert running["telemetry"]["source"] == "local"
    assert running["telemetry"]["process_cpu_percent"] is not None
    assert running["telemetry"]["ram_total_bytes"] is not None
    assert running["telemetry_history"]

    release.set()
    history = [created["progress_percent"], running["progress_percent"]]
    for _ in range(100):
        current = client.get(f"/api/v1/clip-assessment-jobs/{created['id']}").json()
        history.append(current["progress_percent"])
        if current["status"] == "completed":
            break
        time.sleep(0.01)
    assert current["status"] == "completed"
    assert current["progress_percent"] == 100
    assert current["assessment_id"] == template.id
    assert history == sorted(history)
    assert all(0 <= value <= 100 for value in history)
    assert client.get(f"/api/v1/clip-assessments/{template.id}").status_code == 200


def test_clip_assessment_job_exposes_sanitized_failure(
    client: TestClient, monkeypatch
) -> None:
    service = client.app.state.service
    clip = next(item for item in service.list_dataset_clips() if item.assessable)

    def failing_assessment(
        _clip_id,
        _profile="mixed",
        _segment_start_s=None,
        _segment_end_s=None,
        progress=None,
    ):
        progress(40, "decoding", "Decoded input")
        raise RuntimeError("model runtime unavailable")

    monkeypatch.setattr(service, "assess_catalog_clip", failing_assessment)
    response = client.post(f"/api/v1/clip-assessment-jobs/catalog/{clip.id}")
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        failed = client.get(f"/api/v1/clip-assessment-jobs/{job_id}").json()
        if failed["status"] == "failed":
            break
        time.sleep(0.01)
    assert failed["status"] == "failed"
    assert failed["stage"] == "failed"
    assert failed["message"] == "model runtime unavailable"
    assert "Traceback" not in failed["message"]
    assert client.get("/api/v1/clip-assessment-jobs/not-real").status_code == 404


class FakeClipQnxRunner:
    def __init__(self, outcome: QnxClipAssessmentOutcome | None = None, error=None) -> None:
        self.config = QnxRunnerConfig(mode="worker", ssh_alias="qnxpi")
        self.outcome = outcome
        self.error = error
        self.calls: list[dict] = []

    def assess_clip_on_target(self, **kwargs) -> QnxClipAssessmentOutcome:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        assert self.outcome is not None
        return self.outcome


def test_qnx_clip_job_never_falls_back_to_local_when_target_unreachable(
    tmp_path: Path, scenario_directory: Path, monkeypatch
) -> None:
    fake = FakeClipQnxRunner(error=QnxRunnerError("SSH to qnxpi failed: no route"))
    with TestClient(
        create_app(tmp_path / "qnx-jobs", scenario_directory, qnx_runner=fake)
    ) as qnx_api:
        service = qnx_api.app.state.service

        def forbidden_local(*_args, **_kwargs):
            raise AssertionError("local inference must not run for executor=qnx")

        monkeypatch.setattr(
            service.clip_assessments, "assess_stored_upload", forbidden_local
        )
        response = qnx_api.post(
            "/api/v1/clip-assessment-jobs/upload",
            data={"executor": "qnx", "profile": "mixed"},
            files={"file": ("clip.mp4", fake_mp4(), "video/mp4")},
        )
        assert response.status_code == 202
        created = response.json()
        assert created["requested_executor"] == "qnx"
        assert created["effective_executor"] is None
        assert created["target"]["verified"] is False
        for _ in range(100):
            job = qnx_api.get(
                "/api/v1/clip-assessment-jobs/%s" % created["id"]
            ).json()
            if job["status"] == "failed":
                break
            time.sleep(0.01)
        assert job["status"] == "failed"
        assert job["requested_executor"] == "qnx"
        assert job["effective_executor"] is None
        assert job["target"]["verified"] is False
        assert "no route" in job["message"]
        assert len(fake.calls) == 1


def test_qnx_clip_job_surfaces_verified_blocked_target_receipt(
    tmp_path: Path, scenario_directory: Path
) -> None:
    sample = {
        "captured_at": "2026-10-18T12:00:00+00:00",
        "source": "qnx",
        "cpu_percent": None,
        "ram_used_bytes": 1024,
        "ram_total_bytes": 8192,
        "process_cpu_percent": None,
        "process_ram_bytes": None,
        "detail": "child CPU unavailable",
    }
    fake = FakeClipQnxRunner(
        outcome=QnxClipAssessmentOutcome(
            status="blocked",
            message="installed QNX worker is missing",
            target={
                "executor": "qnx",
                "hostname": "qnx-pi",
                "system": "QNX",
                "release": "8.0.0",
                "machine": "aarch64le",
                "runtime": "Python 3.14.0",
                "verified": True,
            },
            telemetry_history=[sample],
            assessment=None,
            helper_output="",
            remote_run_dir="/data/home/qnxuser/simlab-runs/test",
        )
    )
    with TestClient(
        create_app(tmp_path / "qnx-jobs", scenario_directory, qnx_runner=fake)
    ) as qnx_api:
        response = qnx_api.post(
            "/api/v1/clip-assessment-jobs/upload",
            data={"executor": "qnx"},
            files={"file": ("clip.mp4", fake_mp4(), "video/mp4")},
        )
        job_id = response.json()["id"]
        for _ in range(100):
            job = qnx_api.get("/api/v1/clip-assessment-jobs/%s" % job_id).json()
            if job["status"] == "failed":
                break
            time.sleep(0.01)
        assert job["stage"] == "blocked"
        assert job["requested_executor"] == "qnx"
        assert job["effective_executor"] == "qnx"
        assert job["target"]["verified"] is True
        assert job["telemetry"]["ram_used_bytes"] == 1024
        assert job["telemetry"]["process_cpu_percent"] is None


def test_qnx_clip_job_does_not_set_effective_executor_before_identity_validation(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeClipQnxRunner(
        outcome=QnxClipAssessmentOutcome(
            status="blocked",
            message="unverified target",
            target={
                "executor": "qnx",
                "hostname": "unknown",
                "system": "QNX",
                "verified": False,
            },
            telemetry_history=[],
            assessment=None,
            helper_output="",
            remote_run_dir="/data/home/qnxuser/simlab-runs/test",
        )
    )
    with TestClient(
        create_app(tmp_path / "qnx-unverified", scenario_directory, qnx_runner=fake)
    ) as qnx_api:
        response = qnx_api.post(
            "/api/v1/clip-assessment-jobs/upload",
            data={"executor": "qnx"},
            files={"file": ("clip.mp4", fake_mp4(), "video/mp4")},
        )
        job_id = response.json()["id"]
        for _ in range(100):
            job = qnx_api.get("/api/v1/clip-assessment-jobs/%s" % job_id).json()
            if job["status"] == "failed":
                break
            time.sleep(0.01)

        assert job["status"] == "failed"
        assert job["requested_executor"] == "qnx"
        assert job["effective_executor"] is None
        assert job["target"]["verified"] is False
        assert "did not prove" in job["message"]


def test_synchronous_clip_api_accepts_executor_but_requires_jobs_for_qnx(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/clip-assessments/upload",
        data={"executor": "qnx"},
        files={"file": ("clip.mp4", fake_mp4(), "video/mp4")},
    )

    assert response.status_code == 422
    assert "asynchronous clip-assessment job endpoint" in response.json()["error"]["message"]


def test_upload_and_execute_mock_run(client: TestClient) -> None:
    upload = client.post(
        "/api/v1/models/upload",
        data={"name": "Uploaded model", "version": "7", "source": "teammate"},
        files={"file": ("model.onnx", b"onnx bytes", "application/octet-stream")},
    )
    assert upload.status_code == 201
    model = upload.json()
    assert model["format"] == "onnx"

    response = client.post(
        "/api/v1/runs",
        json={"scenario_id": "outbreak-100", "model_id": model["id"], "executor": "mock"},
    )
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "completed"
    assert run["metrics"]["alert_triggered"] is True
    assert len(client.get(f"/api/v1/runs/{run['id']}/timeline").json()) == 61
    snapshots = client.get(f"/api/v1/runs/{run['id']}/snapshots").json()
    assert len(snapshots) == 61
    assert len(snapshots[0]["birds"]) == 100
    result = client.app.state.service.catalog.get_result(run["id"])
    assert result is not None
    assert result.model.sha256 == model["sha256"]
    assert {artifact.kind for artifact in result.artifacts} == {"timeline", "snapshots"}
    assert result.evaluation_kind == "prediction"
    assert result.metrics is not None


def test_import_veri_endpoint(client: TestClient, tmp_path: Path) -> None:
    output = tmp_path / "veri"
    output.mkdir()
    model_bytes = b"tflite"
    (output / "model.tflite").write_bytes(model_bytes)
    (output / "model.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "veri-result",
                "version": "3",
                "model_file": "model.tflite",
                "sha256": hashlib.sha256(model_bytes).hexdigest(),
                "format": "tflite",
                "input": {
                    "width": 224,
                    "height": 224,
                    "channels": 3,
                    "dtype": "uint8",
                    "layout": "NHWC",
                    "color_space": "RGB",
                    "normalization": {"kind": "none"},
                },
                "output": {
                    "task": "anomaly_score",
                    "dtype": "float32",
                    "interpretation": "pen anomaly score",
                },
                "labels": ["expected", "anomalous"],
                "provenance": {"producer": "training-workstream", "training_run": "test-run"},
                "metrics": {},
                "compatibility": {"runtimes": [], "quantization": "none"},
                "created_at": "2026-10-17T12:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    response = client.post("/api/v1/models/import-veri", json={"path": str(output)})

    assert response.status_code == 201
    assert response.json()["source"] == "veri-local"


def test_api_errors_are_structured(client: TestClient) -> None:
    missing = client.get("/api/v1/runs/not-real")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    invalid = client.post("/api/v1/runs", json={"scenario_id": "healthy-100"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"

    qnx = client.post(
        "/api/v1/runs",
        json={"scenario_id": "healthy-100", "model_id": "mock-baseline", "executor": "qnx"},
    )
    assert qnx.status_code == 422
    assert qnx.json()["error"] == {
        "code": "adapter_error",
        "message": "executor not configured: qnx",
    }


def test_upload_rejects_missing_fields(client: TestClient) -> None:
    response = client.post(
        "/api/v1/models/upload",
        files={"file": ("model.tflite", b"bytes", "application/octet-stream")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# --- run result endpoint ------------------------------------------------------


def test_result_endpoint_for_mock_run(client: TestClient) -> None:
    run = client.post(
        "/api/v1/runs",
        json={"scenario_id": "outbreak-100", "model_id": "mock-baseline", "executor": "mock"},
    ).json()

    response = client.get(f"/api/v1/runs/{run['id']}/result")

    assert response.status_code == 200
    result = response.json()
    assert result["run_id"] == run["id"]
    assert result["evaluation_kind"] == "prediction"
    assert result["executor"]["name"] == "mock"
    assert result["metrics"] is not None
    assert {artifact["kind"] for artifact in result["artifacts"]} == {"timeline", "snapshots"}


def test_result_endpoint_missing_run_or_result(client: TestClient) -> None:
    missing_run = client.get("/api/v1/runs/not-real/result")
    assert missing_run.status_code == 404
    assert missing_run.json()["error"]["code"] == "not_found"


# --- QNX target validation ----------------------------------------------------


def test_qnx_probe_endpoint_returns_state_not_throw(tmp_path: Path, scenario_directory: Path) -> None:
    fake = FakeQnxClient()
    client = qnx_client(tmp_path, scenario_directory, fake)

    response = client.post("/api/v1/system/qnx/probe")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "qnx"
    assert body["kind"] == "executor"
    assert body["status"] == "probe_only"
    assert body["details"]["python_version"] == "3.14.0"
    assert body["details"]["inference_performed"] is False
    assert "ready" != body["status"]


def test_qnx_probe_endpoint_disabled_returns_not_configured(client: TestClient) -> None:
    response = client.post("/api/v1/system/qnx/probe")

    assert response.status_code == 200
    assert response.json()["status"] == "not_configured"


def test_qnx_target_probe_persists_run_and_result(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeQnxClient()
    client = qnx_client(tmp_path, scenario_directory, fake)
    model_bytes = b"real tflite artifact bytes for the Pi"
    upload = client.post(
        "/api/v1/models/upload",
        data={"name": "Pen anomaly model", "version": "4", "source": "teammate"},
        files={"file": ("pen.tflite", model_bytes, "application/octet-stream")},
    )
    assert upload.status_code == 201
    model = upload.json()

    response = client.post(
        "/api/v1/runs",
        json={"scenario_id": "pio-reference-100", "model_id": model["id"], "executor": "qnx"},
    )

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "completed"
    assert run["executor"] == "qnx"
    assert run["metrics"] is None

    result = client.get(f"/api/v1/runs/{run['id']}/result").json()
    assert result["evaluation_kind"] == "target_probe"
    assert result["executor"]["name"] == "qnx"
    assert result["executor"]["target"] == "QNX 8.0.0 (aarch64le)"
    assert result["executor"]["runtime"] == "Python 3.14.0"
    assert result["metrics"] is None
    assert {artifact["kind"] for artifact in result["artifacts"]} == {"report", "log"}
    assert result["model"]["sha256"] == hashlib.sha256(model_bytes).hexdigest()

    assert client.get(f"/api/v1/runs/{run['id']}/timeline").json() == []
    assert client.get(f"/api/v1/runs/{run['id']}/snapshots").json() == []

    assert len(fake.calls) == 1
    staged = fake.calls[0]
    assert Path(staged["model_path"]).read_bytes() == model_bytes
    assert Path(staged["scenario_path"]) == scenario_directory / "pio-reference-100.json"
    assert staged["scenario_name"] == "pio-reference-100"

    service = client.app.state.service
    run_dir = service.catalog.runs_dir / run["id"]
    receipt = json.loads((run_dir / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["run_id"] == run["id"]
    assert receipt["inference_performed"] is False
    assert "fake probe job" in (run_dir / "run.log").read_text(encoding="utf-8")


def test_qnx_result_uses_host_clock_when_target_clock_is_unsynchronized(
    tmp_path: Path, scenario_directory: Path
) -> None:
    epoch_start = "1970-01-01T01:13:20+00:00"
    epoch_finish = "1970-01-01T01:13:21+00:00"
    fake = FakeQnxClient(receipt_timestamps=(epoch_start, epoch_finish))
    client = qnx_client(tmp_path, scenario_directory, fake)
    model = client.post(
        "/api/v1/models/upload",
        data={"name": "Clock test", "version": "1", "source": "test"},
        files={"file": ("clock.tflite", b"model bytes", "application/octet-stream")},
    ).json()

    run_response = client.post(
        "/api/v1/runs",
        json={"scenario_id": "healthy-100", "model_id": model["id"], "executor": "qnx"},
    )
    assert run_response.status_code == 201
    run = run_response.json()
    result = client.get(f"/api/v1/runs/{run['id']}/result").json()

    assert result["started_at"] == run["created_at"]
    assert result["finished_at"] >= result["started_at"]
    assert result["started_at"] != epoch_start
    assert result["finished_at"] != epoch_finish

    receipt_path = client.app.state.service.catalog.runs_dir / run["id"] / "receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["started_at"] == epoch_start
    assert receipt["finished_at"] == epoch_finish


def test_qnx_rejects_builtin_zero_byte_mock_model(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeQnxClient()
    client = qnx_client(tmp_path, scenario_directory, fake)

    response = client.post(
        "/api/v1/runs",
        json={"scenario_id": "healthy-100", "model_id": "mock-baseline", "executor": "qnx"},
    )

    assert response.status_code == 422
    assert "zero-byte" in response.json()["error"]["message"]
    assert fake.calls == []
    assert client.get("/api/v1/runs").json() == []


def test_qnx_failed_validation_persists_failed_run(
    tmp_path: Path, scenario_directory: Path
) -> None:
    fake = FakeQnxClient(failure=QnxRunnerError("runner helper exited 2: worker failed"))
    client = qnx_client(tmp_path, scenario_directory, fake)
    upload = client.post(
        "/api/v1/models/upload",
        data={"name": "Pen anomaly model", "version": "5", "source": "teammate"},
        files={"file": ("pen.tflite", b"tflite bytes", "application/octet-stream")},
    )
    model = upload.json()

    response = client.post(
        "/api/v1/runs",
        json={"scenario_id": "healthy-100", "model_id": model["id"], "executor": "qnx"},
    )

    assert response.status_code == 422
    assert "runner helper exited 2" in response.json()["error"]["message"]
    runs = client.get("/api/v1/runs").json()
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["executor"] == "qnx"
    assert "worker failed" in runs[0]["error"]


# --- media --------------------------------------------------------------------


def test_media_listing_typed_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/media")

    assert response.status_code == 200
    assets = response.json()
    assert len(assets) == 2
    asset = next(item for item in assets if item["id"] == "pio-growth-stages")
    assert asset["id"] == "pio-growth-stages"
    assert asset["installed"] is False
    assert asset["verified"] is False
    assert asset["size_bytes"] == 0
    assert asset["content_url"] == "/api/v1/media/pio-growth-stages/content"
    assert "ncbi.nlm.nih.gov" in asset["source_url"]
    assert asset["doi"] == "10.1038/s41597-026-07114-5"
    assert asset["license"] == "CC-BY-4.0"
    assert asset["media_type"] == "image/jpeg"
    assert asset["expected_size_bytes"] == 121814
    assert asset["duration_s"] is None
    assert asset["attribution"]
    assert asset["creators"]
    for limitation in (
        "reference imagery only",
        "no disease labels",
        "not spatially aligned with simulated birds",
    ):
        assert limitation in asset["limitations"]

    video = next(item for item in assets if item["id"] == "spatiotemporal-whole-pen")
    assert video["media_type"] == "video/mp4"
    assert video["expected_size_bytes"] == 1322209
    assert video["duration_s"] == 19.4
    assert video["frame_rate_fps"] == 5.0
    assert video["frame_count"] == 97
    assert video["codec"] == "H.264"


def test_media_content_missing_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/media/pio-growth-stages/content")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_media_content_unknown_asset_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/media/does-not-exist/content")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_media_content_served_only_after_hash_verification(
    tmp_path: Path, scenario_directory: Path
) -> None:
    content = b"\xff\xd8\xff test reference image payload"
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    manifest = {
        "schema_version": 1,
        "id": "test-ref-image",
        "title": "Test reference image",
        "description": "Offline test manifest.",
        "source_url": "https://example.com/test-ref.jpg",
        "dataset_url": "https://doi.org/10.5281/zenodo.0000000",
        "doi": "10.1038/s41597-026-00000-0",
        "creators": ["Test Author"],
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Test attribution.",
        "sha256": hashlib.sha256(content).hexdigest(),
        "file_size_bytes": len(content),
        "media_type": "image/jpeg",
        "width": 640,
        "height": 480,
        "filename": "test-ref.jpg",
        "limitations": [
            "reference imagery only",
            "no disease labels",
            "not spatially aligned with simulated birds",
        ],
    }
    (manifests_dir / "test-ref-image.json").write_text(json.dumps(manifest), encoding="utf-8")
    home = tmp_path / "home"
    with TestClient(
        create_app(home, scenario_directory, demo_assets_directory=manifests_dir)
    ) as client:
        missing = client.get("/api/v1/media/test-ref-image/content")
        assert missing.status_code == 404

        content_path = home / "datasets" / "demo" / "test-ref-image" / "test-ref.jpg"
        content_path.parent.mkdir(parents=True)
        content_path.write_bytes(b"tampered bytes")
        tampered = client.get("/api/v1/media/test-ref-image/content")
        assert tampered.status_code == 404

        content_path.write_bytes(content)
        served = client.get("/api/v1/media/test-ref-image/content")
        assert served.status_code == 200
        assert served.content == content
        assert served.headers["content-type"].startswith("image/jpeg")

        listing = client.get("/api/v1/media").json()
        assert len(listing) == 1
        assert listing[0]["installed"] is True
        assert listing[0]["verified"] is True
        assert listing[0]["size_bytes"] == len(content)


# --- clip assessment profiles ------------------------------------------------


def fake_mp4(payload: bytes = b"whole pen video") -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + payload


def test_upload_profile_form_field_defaults_to_mixed(client: TestClient) -> None:
    content = fake_mp4(b"profile api")

    response = client.post(
        "/api/v1/clip-assessments/upload",
        files={"file": ("pen.mp4", content, "video/mp4")},
    )
    assert response.status_code == 201
    assert response.json()["profile"] == "mixed"

    response = client.post(
        "/api/v1/clip-assessments/upload",
        data={"profile": "concerning"},
        files={"file": ("pen.mp4", content, "video/mp4")},
    )
    assert response.status_code == 201
    assert response.json()["profile"] == "concerning"


def test_upload_profile_rejects_unknown_values(client: TestClient) -> None:
    response = client.post(
        "/api/v1/clip-assessments/upload",
        data={"profile": "infected"},
        files={"file": ("pen.mp4", fake_mp4(), "video/mp4")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_demo_endpoint_accepts_profile_query(
    tmp_path: Path, scenario_directory: Path
) -> None:
    content = fake_mp4(b"demo profile")
    digest = hashlib.sha256(content).hexdigest()
    manifests_dir = tmp_path / "demo-assets"
    manifests_dir.mkdir()
    (manifests_dir / "demo-video.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "demo-video",
                "title": "Test whole-pen clip",
                "description": "Test fixture",
                "source_url": "https://example.test/demo.mp4",
                "dataset_url": "https://example.test/dataset",
                "doi": "not-assigned",
                "creators": ["Test"],
                "license": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "Test fixture",
                "sha256": digest,
                "file_size_bytes": len(content),
                "media_type": "video/mp4",
                "width": 848,
                "height": 480,
                "duration_s": 19.4,
                "frame_rate_fps": 5,
                "frame_count": 97,
                "codec": "H.264",
                "filename": "demo.mp4",
                "limitations": [
                    "reference imagery only",
                    "no disease labels",
                    "not spatially aligned with simulated birds",
                ],
            }
        ),
        encoding="utf-8",
    )
    home = tmp_path / "simlab"
    installed = home / "datasets" / "demo" / "demo-video" / "demo.mp4"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(content)
    with TestClient(
        create_app(home, scenario_directory, demo_assets_directory=manifests_dir)
    ) as client:
        response = client.post(
            "/api/v1/clip-assessments/demo/demo-video?profile=healthy"
        )
        assert response.status_code == 201
        assert response.json()["profile"] == "healthy"
        assert all(
            candidate["proxy_crop"]["expected_demo_class"] == "healthy"
            for candidate in response.json()["summary"]["feces"]["candidates"]
        )
        assert response.json()["summary"]["pen_assessment"]["state"] in {
            "normal",
            "watch",
            "review",
        }


def test_catalog_endpoint_accepts_profile_query(client: TestClient) -> None:
    defaulted = client.post("/api/v1/clip-assessments/catalog/big-broiler-090")
    assert defaulted.status_code == 201
    assert defaulted.json()["profile"] == "mixed"
    assert all(
        candidate["provenance"]["location_source"] == "deterministic_overlay"
        for candidate in defaulted.json()["summary"]["feces"]["candidates"]
    )

    concerning = client.post(
        "/api/v1/clip-assessments/catalog/big-broiler-090?profile=concerning"
    )
    assert concerning.status_code == 201
    assert concerning.json()["profile"] == "concerning"

    invalid = client.post(
        "/api/v1/clip-assessments/catalog/big-broiler-090?profile=bogus"
    )
    assert invalid.status_code == 422


# --- proxy specimen content ---------------------------------------------------


def _proxy_app(tmp_path: Path, scenario_directory: Path, content: bytes) -> TestClient:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    digest = hashlib.sha256(content).hexdigest()
    for asset_id, demo_class, has_bytes in (
        ("healthy", "healthy", True),
        ("cocci", "cocci", False),
        ("ncd", "ncd", False),
        ("salmo", "salmo", False),
    ):
        (directory / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset_id": asset_id,
                    "filename": f"{asset_id}.jpg",
                    "media_type": "image/jpeg",
                    "sha256": digest if has_bytes else "TO_BE_FILLED_BY_ORCHESTRATOR",
                    "expected_demo_class": demo_class,
                    "description": "test fixture",
                    "source_dataset": "test dataset",
                    "source_url": "https://example.test/",
                    "license": "CC-BY-4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": "test fixture",
                    "substitution_reason": "test fixture",
                }
            ),
            encoding="utf-8",
        )
    (directory / "healthy.jpg").write_bytes(content)
    return TestClient(
        create_app(
            tmp_path / "simlab-proxy",
            scenario_directory,
            proxy_specimens_directory=directory,
        )
    )


def test_proxy_content_endpoint_rejects_unknown_and_path_like_ids(
    tmp_path: Path, scenario_directory: Path
) -> None:
    with _proxy_app(tmp_path, scenario_directory, b"\xff\xd8\xff fake jpeg") as client:
        for asset_id in ("does-not-exist", "../healthy", "healthy/../../etc", "HEALTHY"):
            response = client.get(f"/api/v1/proxy-specimens/{asset_id}/content")
            assert response.status_code == 404
            body = response.json()
            if "error" in body:
                assert body["error"]["code"] == "not_found"


def test_proxy_summary_is_metadata_only_and_tracks_cached_verification(
    tmp_path: Path, scenario_directory: Path
) -> None:
    content = b"\xff\xd8\xff real curated proxy photo bytes"
    with _proxy_app(tmp_path, scenario_directory, content) as client:
        initial = client.get("/api/v1/proxy-specimens")
        assert initial.status_code == 200
        assert initial.json() == {
            "total": 4,
            "selectable_total": 4,
            "bytes_present": 1,
            "verified_cached": 0,
            "by_expected_class": {
                "cocci": 1,
                "healthy": 1,
                "ncd": 1,
                "salmo": 1,
                "unknown_abnormal": 0,
            },
            "selectable_by_expected_class": {
                "cocci": 1,
                "healthy": 1,
                "ncd": 1,
                "salmo": 1,
                "unknown_abnormal": 0,
            },
            "by_dataset": [{"dataset": "test dataset", "count": 4}],
            "catalogs_supported": True,
        }

        assert client.get("/api/v1/proxy-specimens/healthy/content").status_code == 200
        after_content = client.get("/api/v1/proxy-specimens").json()
        assert after_content["verified_cached"] == 1
        assert after_content["bytes_present"] == 1


def test_proxy_content_serves_only_verified_bytes(
    tmp_path: Path, scenario_directory: Path
) -> None:
    content = b"\xff\xd8\xff real curated proxy photo bytes"
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    digest = hashlib.sha256(content).hexdigest()
    for asset_id, demo_class, sha in (
        ("healthy", "healthy", digest),
        ("cocci", "cocci", "TO_BE_FILLED_BY_ORCHESTRATOR"),
        ("ncd", "ncd", "TO_BE_FILLED_BY_ORCHESTRATOR"),
        ("salmo", "salmo", "TO_BE_FILLED_BY_ORCHESTRATOR"),
    ):
        (directory / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset_id": asset_id,
                    "filename": f"{asset_id}.jpg",
                    "media_type": "image/jpeg",
                    "sha256": sha,
                    "expected_demo_class": demo_class,
                    "description": "test fixture",
                    "source_dataset": "test dataset",
                    "source_url": "https://example.test/",
                    "license": "CC-BY-4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": "test fixture",
                    "substitution_reason": "test fixture",
                }
            ),
            encoding="utf-8",
        )
    photo = directory / "healthy.jpg"
    photo.write_bytes(b"tampered")
    with TestClient(
        create_app(
            tmp_path / "simlab-proxy-2",
            scenario_directory,
            proxy_specimens_directory=directory,
        )
    ) as client:
        tampered = client.get("/api/v1/proxy-specimens/healthy/content")
        assert tampered.status_code == 404

        placeholder = client.get("/api/v1/proxy-specimens/cocci/content")
        assert placeholder.status_code == 404

    photo.write_bytes(content)
    with TestClient(
        create_app(
            tmp_path / "simlab-proxy-2",
            scenario_directory,
            proxy_specimens_directory=directory,
        )
    ) as client:
        served = client.get("/api/v1/proxy-specimens/healthy/content")
        assert served.status_code == 200
        assert served.content == content
        assert served.headers["content-type"].startswith("image/jpeg")


def test_proxy_content_preserves_png_manifest_media_type(
    tmp_path: Path, scenario_directory: Path
) -> None:
    directory = tmp_path / "proxy-png"
    directory.mkdir()
    content = b"\x89PNG\r\n\x1a\n proxy fixture"
    digest = hashlib.sha256(content).hexdigest()
    (directory / "healthy.png").write_bytes(content)
    (directory / "healthy.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "asset_id": "healthy-png",
                "filename": "healthy.png",
                "media_type": "image/png",
                "sha256": digest,
                "expected_demo_class": "healthy",
                "description": "PNG proxy fixture",
                "source_dataset": "test dataset",
                "source_url": "https://example.test/png",
                "license": "test-only",
                "attribution": "test fixture",
                "substitution_reason": "test fixture",
            }
        ),
        encoding="utf-8",
    )
    with TestClient(
        create_app(
            tmp_path / "simlab-png",
            scenario_directory,
            proxy_specimens_directory=directory,
        )
    ) as client:
        served = client.get("/api/v1/proxy-specimens/healthy-png/content")
        assert served.status_code == 200
        assert served.content == content
        assert served.headers["content-type"].startswith("image/png")


# --- QNX evidence -------------------------------------------------------------


def test_qnx_evidence_endpoint_distinguishes_claim_statuses(client: TestClient) -> None:
    response = client.get("/api/v1/system/qnx/evidence")

    assert response.status_code == 200
    body = response.json()
    document = body["evidence"]
    assert document["evidence_id"] == "dropping4-laptop-final-320"
    assert "predictable capture deadlines" in document["thesis"]
    assert document["platform"]["system"] == "QNX"
    assert document["platform"]["release"] == "8.0.0"

    by_id = {claim["id"]: claim for claim in body["claims"]}
    assert set(by_id) == set(claim["id"] for claim in document["claims"])

    assert by_id["platform-boot"]["status"] == "verified"
    assert by_id["ncnn-native-execution"]["status"] == "verified"
    assert by_id["inference-timing"]["status"] == "verified"
    samples = by_id["inference-timing"]["detail"]["samples_ms"]
    assert len(samples) == 10
    assert round(sum(samples) / 10, 4) == 98.4287
    assert by_id["onnx-qnx-parity"]["detail"]["max_abs_error"] == 0.000732421875
    assert by_id["ncnn-artifact-hashes"]["detail"]["param_sha256"] == (
        "064220842481ac84c4736ab11012129ddb7191412b69bbfde8fee261b620b4c3"
    )

    assert by_id["fixed-priority-scheduling"]["status"] == "os_supported_only"
    assert by_id["sched-sporadic"]["status"] == "os_supported_only"

    for planned in (
        "ham",
        "hardware-watchdog",
        "kernel-tracing",
        "capture-jitter-metrics",
        "service-separation",
    ):
        assert by_id[planned]["status"] == "planned"

    assert by_id["aps-unsupported"]["status"] == "unsupported_guard"
    for claim in body["claims"]:
        assert "APS" not in claim["summary"].upper() or claim["id"] == "aps-unsupported"
        assert claim["status"] != "verified" or claim["id"] != "aps-unsupported"


def test_qnx_evidence_missing_file_is_structured_404(
    tmp_path: Path, scenario_directory: Path
) -> None:
    with TestClient(
        create_app(
            tmp_path / "simlab-no-evidence",
            scenario_directory,
            qnx_evidence_path=tmp_path / "missing.json",
        )
    ) as client:
        response = client.get("/api/v1/system/qnx/evidence")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
