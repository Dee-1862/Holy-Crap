from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from holy_crap_simlab.api import create_app
from holy_crap_simlab.qnx_runner import (
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
