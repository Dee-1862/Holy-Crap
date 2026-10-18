from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from holy_crap_simlab.adapters import AdapterError, VeriArtifactImporter
from holy_crap_simlab.catalog import Catalog


def manifest_for(model_bytes: bytes, model_file: str = "pen-model.tflite") -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "pen-anomaly",
        "version": "2026-10-17",
        "model_file": model_file,
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
        "provenance": {"producer": "training-workstream", "training_run": "local-test"},
        "metrics": {"validation_auc": 0.8},
        "compatibility": {"runtimes": [], "quantization": "none"},
        "created_at": "2026-10-17T12:00:00Z",
    }


def test_imports_completed_local_veri_directory(tmp_path: Path) -> None:
    output = tmp_path / "veri-output"
    output.mkdir()
    model_bytes = b"finished tflite artifact"
    (output / "pen-model.tflite").write_bytes(model_bytes)
    (output / "model.json").write_text(
        json.dumps(manifest_for(model_bytes)),
        encoding="utf-8",
    )

    model = VeriArtifactImporter(Catalog(tmp_path / "catalog")).import_directory(output)

    assert model.source == "veri-local"
    assert model.format == "tflite"
    assert model.sha256 == hashlib.sha256(model_bytes).hexdigest()


@pytest.mark.parametrize(
    "manifest, message",
    [
        (None, "must contain model.json"),
        (manifest_for(b"outside", "../outside.tflite"), "inside"),
    ],
)
def test_rejects_incomplete_or_escaping_veri_directory(
    tmp_path: Path, manifest: dict[str, str] | None, message: str
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (tmp_path / "outside.tflite").write_bytes(b"outside")
    if manifest:
        (output / "model.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AdapterError, match=message):
        VeriArtifactImporter(Catalog(tmp_path / "catalog")).import_directory(output)


def test_rejects_manifest_with_wrong_digest(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    model_bytes = b"actual bytes"
    (output / "pen-model.tflite").write_bytes(model_bytes)
    manifest = manifest_for(b"different bytes")
    (output / "model.json").write_text(json.dumps(manifest), encoding="utf-8")
    catalog = Catalog(tmp_path / "catalog")

    with pytest.raises(AdapterError, match="SHA-256"):
        VeriArtifactImporter(catalog).import_directory(output)

    assert catalog.list_models() == []
