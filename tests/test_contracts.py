from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from holy_crap_simlab.models import CreateRunRequest
from holy_crap_simlab.clip_assessment import ClipAssessmentService
from holy_crap_simlab.qnx_runner import QnxProbeReport, QnxRunnerConfig, QnxValidationOutcome
from holy_crap_simlab.service import SimulationService

ROOT = Path(__file__).resolve().parents[1]

RUN_ID_PATTERN = "8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c"


def validate(contract: str, instance: object) -> None:
    schema = json.loads((ROOT / "contracts" / contract).read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)


def valid_model_manifest(model_bytes: bytes) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "pen-anomaly",
        "version": "0.1.0",
        "model_file": "model.tflite",
        "sha256": hashlib.sha256(model_bytes).hexdigest(),
        "format": "tflite",
        "input": {
            "width": 320,
            "height": 320,
            "channels": 3,
            "dtype": "uint8",
            "layout": "NHWC",
            "color_space": "RGB",
            "normalization": {"kind": "none"},
        },
        "output": {
            "task": "anomaly_score",
            "dtype": "float32",
            "interpretation": "pen-level anomaly score",
            "threshold": 0.5,
        },
        "labels": ["expected", "anomalous"],
        "provenance": {"producer": "training-workstream", "training_run": "fixture-run"},
        "metrics": {"validation_auc": 0.8},
        "compatibility": {"runtimes": [], "quantization": "none"},
        "created_at": "2026-10-17T12:00:00Z",
    }


class RecordingFakeClient:
    """Builds a valid target-probe receipt from the staged bytes; no network."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.config = QnxRunnerConfig(mode="probe")
        self.failure = failure
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
            "started_at": "2026-10-17T20:00:00+00:00",
            "finished_at": "2026-10-17T20:00:01+00:00",
            "inference_performed": False,
            "inference_reason": "No QNX inference runtime is installed or configured.",
        }
        return QnxValidationOutcome(
            receipt=receipt,
            helper_output="fake helper output",
            remote_run_dir="/data/home/qnxuser/simlab-runs/run-%s" % run_id,
        )


def probe_report() -> QnxProbeReport:
    return QnxProbeReport(
        reachable=True,
        python_version="3.14.0",
        runner_output="runner: running (pid 1)",
        runtime_presence={},
        detail="probe detail",
    )


def qnx_service(tmp_path: Path, fake: RecordingFakeClient) -> SimulationService:
    return SimulationService(
        tmp_path / "simlab",
        ROOT / "scenarios",
        qnx_runner=fake,
        qnx_prober=probe_report,
    )


def test_committed_scenarios_conform_to_contract() -> None:
    paths = sorted((ROOT / "scenarios").glob("*.json"))
    assert {path.stem for path in paths} == {
        "healthy-100",
        "outbreak-100",
        "pio-reference-100",
    }
    for path in paths:
        validate("scenario.schema.json", json.loads(path.read_text(encoding="utf-8")))


def test_representative_model_manifest_conforms_to_contract() -> None:
    validate("model-bundle.schema.json", valid_model_manifest(b"model bytes"))


def test_persisted_mock_result_conforms_to_contract(tmp_path: Path) -> None:
    service = SimulationService(tmp_path / "simlab", ROOT / "scenarios")
    run = service.run(
        CreateRunRequest(scenario_id="outbreak-100", model_id="mock-baseline", executor="mock")
    )
    result_path = service.catalog.runs_dir / run.id / "result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    validate("run-result.schema.json", payload)
    assert payload["evaluation_kind"] == "prediction"
    assert payload["executor"]["name"] == "mock"
    assert payload["metrics"] is not None


def test_historical_mock_result_without_evaluation_kind_still_conforms(
    tmp_path: Path,
) -> None:
    service = SimulationService(tmp_path / "simlab", ROOT / "scenarios")
    run = service.run(
        CreateRunRequest(scenario_id="outbreak-100", model_id="mock-baseline", executor="mock")
    )
    result_path = service.catalog.runs_dir / run.id / "result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    payload.pop("evaluation_kind")

    validate("run-result.schema.json", payload)


def test_persisted_qnx_target_probe_result_conforms_to_contract(tmp_path: Path) -> None:
    fake = RecordingFakeClient()
    service = qnx_service(tmp_path, fake)
    model_bytes = b"real tflite artifact bytes"
    model = service.catalog.register_stream(
        io.BytesIO(model_bytes),
        name="Pen anomaly model",
        version="1",
        filename="pen.tflite",
        source="teammate",
    )
    run = service.run(
        CreateRunRequest(scenario_id="healthy-100", model_id=model.id, executor="qnx")
    )
    result_path = service.catalog.runs_dir / run.id / "result.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    validate("run-result.schema.json", payload)
    assert payload["evaluation_kind"] == "target_probe"
    assert payload["executor"]["name"] == "qnx"
    assert payload["metrics"] is None
    assert {artifact["kind"] for artifact in payload["artifacts"]} == {"report", "log"}
    for artifact in payload["artifacts"]:
        artifact_path = service.catalog.runs_dir / run.id / artifact["path"]
        assert artifact_path.is_file()


def test_persisted_clip_assessment_conforms_to_contract(tmp_path: Path) -> None:
    content = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2whole pen"
    service = ClipAssessmentService(tmp_path / "simlab")
    result = service.assess_upload(
        io.BytesIO(content), "whole-pen.mp4", "video/mp4"
    )
    result_path = service.store.assessments_dir / f"{result.id}.json"
    payload = json.loads(result_path.read_text(encoding="utf-8"))

    validate("clip-assessment.schema.json", payload)
    assert payload["summary"]["overall"]["review_state"] == "synthetic-demo-only"
    assert {module["mode"] for module in payload["modules"]} == {"mock", "real"}
    assert payload["profile"] == "mixed"
    pen = payload["summary"]["pen_assessment"]
    assert pen["policy_id"] == "demo-pen-v1"
    assert pen["evidence_mode"] == "hybrid_simulation"
    assert pen["non_diagnostic"] is True
    candidate = payload["summary"]["feces"]["candidates"][0]
    assert candidate["crop"]["target_width"] == 320
    assert candidate["crop"]["target_height"] == 320
    assert candidate["provenance"]["location_source"] == "observed_video"
    assert candidate["provenance"]["appearance_input"] == "curated_proxy"
    assert candidate["provenance"]["classification_source"] == "live_model_run"
    assert candidate["classification"]["product_label"] in {"normal", "abnormal", "uncertain"}
    assert candidate["classification"]["inference_performed"] is True
    assert candidate["classification"]["fallback_reason"] is None
    assert candidate["proxy_crop"]["mapping_method"] == "sha256-seeded"
    assert candidate["proxy_crop"]["bytes_available"] is True
    assert candidate["proxy_crop"]["content_url"].startswith(
        "/api/v1/proxy-specimens/"
    )

    candidate["proxy_crop"]["expected_demo_class"] = "unknown_abnormal"
    validate("clip-assessment.schema.json", payload)


def test_clip_contract_declares_320_yolo_detection_not_224_single_label() -> None:
    schema = json.loads(
        (ROOT / "contracts" / "clip-assessment.schema.json").read_text(encoding="utf-8")
    )
    crop = schema["$defs"]["fecesCandidate"]["properties"]["crop"]["properties"]
    assert crop["target_width"]["const"] == 320
    assert crop["target_height"]["const"] == 320

    classifier = schema["$defs"]["fecesCandidate"]["properties"]["classification"]["properties"]
    assert classifier["label"]["enum"] == [
        "Coccidiosis",
        "Healthy",
        "New Castle Disease",
        "Salmonella",
        None,
    ]
    assert classifier["product_label"]["enum"] == ["normal", "abnormal", "uncertain"]
    assert schema["properties"]["modules"]["items"]["properties"]["mode"]["enum"] == [
        "mock",
        "partial",
        "real",
    ]
    assert classifier["fallback_reason"]["enum"] == [
        "specimen_unavailable",
        "runtime_unavailable",
        "image_decode_failed",
        "model_inference_failed",
        None,
    ]
    proxy = schema["$defs"]["proxySpecimen"]
    assert proxy["properties"]["expected_demo_class"]["enum"] == [
        "cocci",
        "healthy",
        "ncd",
        "salmo",
        "unknown_abnormal",
    ]
