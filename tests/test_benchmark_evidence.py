from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from holy_crap_simlab.api import create_app
from holy_crap_simlab.models import BenchmarkEvidenceResponse

QNX_SCHEMA_MARKER = "holy-crap-qnx-native-eval-summary-v1"
LINUX_SUITE_MARKER = "linux_scheduler_wakeup_jitter_control"


def qnx_summary() -> dict:
    return {
        "schema": QNX_SCHEMA_MARKER,
        "source_commit": "7778ee028347acb8793b7fd81d3d92f63ff57d37",
        "target": {
            "os": "QNX 8.0.0",
            "board": "RaspberryPi5",
            "architecture": "aarch64le",
            "cpu": "4x Cortex-A76 at 1500 MHz",
        },
        "jitter": {
            "deadline_us": 100,
            "scenarios": {
                "same-core-load-control": {"p50_us": 2564530.037},
                "same-core-load-fifo40": {
                    "p50_us": 335.658,
                    "deadline_miss_rate": 0.99996,
                },
            },
        },
        "ipc": {
            "mechanism": "native QNX MsgSend/MsgReceive/MsgReply",
            "payload_bytes": 57600,
            "p50_us": 89.695,
        },
        "ncnn_feces_320_fp32": {
            "idle": {"calls_per_second": 9.756},
            "observed_data_memory_mb": 48,
        },
        "fault_isolation": {
            "fault": "SIGKILL sent only to a disposable supervised Python worker",
            "detect_mean_ms": 11.518,
            "first_result_mean_ms": 4398.116,
        },
    }


def linux_summary() -> dict:
    return {
        "suite": LINUX_SUITE_MARKER,
        "deadline_lateness_threshold_us": 100,
        "scenarios": {
            "idle-fifo40": {
                "pooled_lateness_us": {"p50": 2.91},
                "deadline_misses": 0,
                "total_wakes": 25000,
            },
            "cross-core-load-fifo40": {
                "pooled_lateness_us": {"p50": 1.785},
                "deadline_misses": 0,
                "total_wakes": 25000,
            },
            "same-core-load-fifo40": {
                "pooled_lateness_us": {"p50": 2.134},
                "deadline_misses": 0,
                "total_wakes": 25000,
            },
        },
    }


def write_summary(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (path.parent / "SHA256SUMS").write_text(
        f"{digest}  ./summary.json\n", encoding="utf-8"
    )
    return path


@pytest.fixture
def scenario_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "scenarios"


@pytest.fixture
def client_factory(
    tmp_path: Path, scenario_directory: Path
) -> Callable[[Path, Path], TestClient]:
    def build(qnx_path: Path, linux_path: Path) -> TestClient:
        return TestClient(
            create_app(
                tmp_path / "simlab",
                scenario_directory,
                qnx_benchmark_evidence_path=qnx_path,
                linux_benchmark_evidence_path=linux_path,
            )
        )

    return build


def test_valid_fixtures_return_exact_source_numbers_and_null_ratio(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_payload = qnx_summary()
    qnx_payload["unexpected_top_level_key"] = {"ignored": True}
    qnx_payload["jitter"]["unexpected_jitter_key"] = [1, 2, 3]
    qnx_payload["jitter"]["scenarios"]["same-core-load-control"]["extra_us"] = 999.0
    linux_payload = linux_summary()
    linux_payload["unexpected_top_level_key"] = "ignored"
    linux_payload["scenarios"]["idle-fifo40"]["extra_metric"] = 42
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_payload)
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_payload)

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    qnx = payload["qnx"]
    assert qnx["status"] == "available"
    assert qnx["source_identity"] == {
        "source_commit": "7778ee028347acb8793b7fd81d3d92f63ff57d37",
        "os": "QNX 8.0.0",
        "board": "RaspberryPi5",
        "architecture": "aarch64le",
        "cpu": "4x Cortex-A76 at 1500 MHz",
    }
    assert qnx["jitter"] == {
        "same_core_control_p50_us": 2564530.037,
        "fifo40_p50_us": 335.658,
        "fifo40_deadline_miss_rate": 0.99996,
        "deadline_threshold_us": 100.0,
        "same_core_control_to_fifo_p50_ratio": None,
    }
    assert qnx["ipc"] == {
        "mechanism": "native QNX MsgSend/MsgReceive/MsgReply",
        "payload_bytes": 57600,
        "p50_us": 89.695,
    }
    assert qnx["ncnn"] == {
        "idle_calls_per_second": 9.756,
        "observed_data_memory_mb": 48,
    }
    assert qnx["fault_isolation"] == {
        "subject": "SIGKILL sent only to a disposable supervised Python worker",
        "detect_mean_ms": 11.518,
        "first_result_mean_ms": 4398.116,
    }
    linux = payload["linux"]
    assert linux["status"] == "available"
    assert linux["deadline_threshold_us"] == 100.0
    assert linux["idle"] == {
        "p50_lateness_us": 2.91,
        "deadline_misses": 0,
        "total_wakes": 25000,
    }
    assert linux["cross_core_load"] == {
        "p50_lateness_us": 1.785,
        "deadline_misses": 0,
        "total_wakes": 25000,
    }
    assert linux["same_core_load"] == {
        "p50_lateness_us": 2.134,
        "deadline_misses": 0,
        "total_wakes": 25000,
    }
    assert payload["test_context"]["qnx"]
    assert payload["test_context"]["linux"]
    assert payload["full_qnx_pipeline_status"] == "not_run"
    assert payload["full_qnx_pipeline_models_completed"] == 0


def test_explicit_ratio_field_is_passed_through_without_recalculation(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_payload = qnx_summary()
    qnx_payload["jitter"]["comparisons"] = {
        "same_core_control_to_fifo_p50_ratio": 7640.307,
        "same_core_control_to_fifo_p50_ratio_formula": "not used by the API",
    }
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_payload)
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    jitter = response.json()["qnx"]["jitter"]
    assert jitter["same_core_control_to_fifo_p50_ratio"] == 7640.307
    assert jitter["same_core_control_p50_us"] == 2564530.037
    assert jitter["fifo40_p50_us"] == 335.658


def test_invalid_explicit_ratio_reports_invalid_instead_of_raising(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_payload = qnx_summary()
    qnx_payload["jitter"]["comparisons"] = {
        "same_core_control_to_fifo_p50_ratio": "not-a-number"
    }
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_payload)
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    assert response.json()["qnx"]["status"] == "invalid"
    assert response.json()["qnx"]["jitter"] is None


def test_missing_qnx_file_reports_unavailable_with_null_metrics(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    missing_qnx = tmp_path / "does-not-exist" / "summary.json"
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(missing_qnx, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    qnx = response.json()["qnx"]
    assert qnx["status"] == "unavailable"
    assert qnx["source_identity"] is None
    assert qnx["jitter"] is None
    assert qnx["ipc"] is None
    assert qnx["ncnn"] is None
    assert qnx["fault_isolation"] is None
    assert response.json()["linux"]["status"] == "available"


def test_missing_linux_file_reports_unavailable_with_null_metrics(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_summary())
    missing_linux = tmp_path / "does-not-exist" / "summary.json"

    with client_factory(qnx_path, missing_linux) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    linux = response.json()["linux"]
    assert linux["status"] == "unavailable"
    assert linux["deadline_threshold_us"] is None
    assert linux["idle"] is None
    assert linux["cross_core_load"] is None
    assert linux["same_core_load"] is None
    assert response.json()["qnx"]["status"] == "available"


def test_missing_both_files_reports_unavailable_without_500(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    missing_qnx = tmp_path / "no-qnx" / "summary.json"
    missing_linux = tmp_path / "no-linux" / "summary.json"

    with client_factory(missing_qnx, missing_linux) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["qnx"]["status"] == "unavailable"
    assert payload["linux"]["status"] == "unavailable"
    assert payload["full_qnx_pipeline_status"] == "not_run"


def test_existing_summary_without_manifest_is_invalid(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_path = tmp_path / "qnx" / "summary.json"
    qnx_path.parent.mkdir(parents=True)
    qnx_path.write_text(json.dumps(qnx_summary()), encoding="utf-8")
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    assert response.json()["qnx"]["status"] == "invalid"


def test_summary_digest_mismatch_is_invalid(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_summary())
    qnx_path.write_text(json.dumps({**qnx_summary(), "tampered": True}), encoding="utf-8")
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    assert response.json()["qnx"]["status"] == "invalid"


def test_manifest_without_summary_entry_is_invalid(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_summary())
    other = qnx_path.parent / "other.txt"
    other.write_text("evidence\n", encoding="utf-8")
    digest = hashlib.sha256(other.read_bytes()).hexdigest()
    (qnx_path.parent / "SHA256SUMS").write_text(
        f"{digest}  ./other.txt\n", encoding="utf-8"
    )
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    assert response.json()["qnx"]["status"] == "invalid"


def test_mismatch_in_another_manifest_artifact_is_invalid(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_summary())
    other = qnx_path.parent / "other.txt"
    other.write_text("tampered\n", encoding="utf-8")
    summary_digest = hashlib.sha256(qnx_path.read_bytes()).hexdigest()
    (qnx_path.parent / "SHA256SUMS").write_text(
        f"{summary_digest}  ./summary.json\n"
        f"{'0' * 64}  ./other.txt\n",
        encoding="utf-8",
    )
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    assert response.json()["qnx"]["status"] == "invalid"


def test_malformed_json_reports_invalid_with_no_stale_metrics(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    broken_qnx = tmp_path / "qnx" / "summary.json"
    broken_qnx.parent.mkdir(parents=True)
    broken_qnx.write_text("{ this is not valid json", encoding="utf-8")
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(broken_qnx, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    qnx = response.json()["qnx"]
    assert qnx["status"] == "invalid"
    assert qnx["source_identity"] is None
    assert qnx["jitter"] is None
    assert qnx["ipc"] is None
    assert qnx["ncnn"] is None
    assert qnx["fault_isolation"] is None
    assert response.json()["linux"]["status"] == "available"


def test_malformed_linux_json_reports_invalid_with_no_stale_metrics(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_summary())
    broken_linux = tmp_path / "linux" / "summary.json"
    broken_linux.parent.mkdir(parents=True)
    broken_linux.write_text("{ this is not valid json", encoding="utf-8")

    with client_factory(qnx_path, broken_linux) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    linux = response.json()["linux"]
    assert linux["status"] == "invalid"
    assert linux["deadline_threshold_us"] is None
    assert linux["idle"] is None
    assert linux["cross_core_load"] is None
    assert linux["same_core_load"] is None
    assert response.json()["qnx"]["status"] == "available"


def test_unknown_schema_marker_reports_invalid(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_payload = qnx_summary()
    qnx_payload["schema"] = "some-future-schema"
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_payload)
    linux_payload = linux_summary()
    linux_payload["suite"] = "a-different-suite"
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_payload)

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    assert response.json()["qnx"]["status"] == "invalid"
    assert response.json()["linux"]["status"] == "invalid"


def test_missing_required_metric_reports_invalid_without_partial_numbers(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_payload = qnx_summary()
    del qnx_payload["jitter"]["scenarios"]["same-core-load-control"]["p50_us"]
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_payload)
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        response = client.get("/api/v1/system/benchmark-evidence")

    assert response.status_code == 200
    assert response.json()["qnx"]["status"] == "invalid"
    assert response.json()["qnx"]["jitter"] is None


def test_response_model_is_strict_about_unknown_keys(
    client_factory: Callable[[Path, Path], TestClient], tmp_path: Path
) -> None:
    qnx_path = write_summary(tmp_path / "qnx" / "summary.json", qnx_summary())
    linux_path = write_summary(tmp_path / "linux" / "summary.json", linux_summary())

    with client_factory(qnx_path, linux_path) as client:
        payload = client.get("/api/v1/system/benchmark-evidence").json()

    payload["unexpected_key"] = "rejected"
    with pytest.raises(ValidationError):
        BenchmarkEvidenceResponse.model_validate(payload)
