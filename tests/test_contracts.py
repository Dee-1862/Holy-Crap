from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from holy_crap_simlab.models import CreateRunRequest
from holy_crap_simlab.service import SimulationService


ROOT = Path(__file__).resolve().parents[1]


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


def test_committed_scenarios_conform_to_contract() -> None:
    paths = sorted((ROOT / "scenarios").glob("*.json"))
    assert {path.stem for path in paths} == {"healthy-100", "outbreak-100"}
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

    validate("run-result.schema.json", json.loads(result_path.read_text(encoding="utf-8")))
