from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient


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
