from __future__ import annotations

import io
from pathlib import Path

import pytest

from holy_crap_simlab.catalog import Catalog, CatalogConflict
from holy_crap_simlab.models import SimulationRun


def test_catalog_persists_models_and_run_metadata(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    catalog = Catalog(root)
    model = catalog.register_stream(
        io.BytesIO(b"model bytes"),
        name="Pen model",
        version="v2",
        filename="../../unsafe.tflite",
        source="test",
    )
    run = SimulationRun(
        id="run-one",
        status="completed",
        scenario_id="healthy-100",
        model_id=model.id,
        executor="mock",
    )
    catalog.save_run(run, [], [])

    reopened = Catalog(root)
    assert reopened.get_model(model.id) == model
    assert reopened.artifact_path(model).read_bytes() == b"model bytes"
    assert reopened.get_run("run-one") == run
    assert reopened.get_timeline("run-one") == []
    assert reopened.get_snapshots("run-one") == []


def test_content_addressed_artifacts_are_deduplicated(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path)
    one = catalog.register_stream(
        io.BytesIO(b"same"), name="one", version="1", filename="one.onnx", source="test"
    )
    two = catalog.register_stream(
        io.BytesIO(b"same"), name="two", version="1", filename="two.onnx", source="test"
    )

    assert one.sha256 == two.sha256
    assert list(catalog.artifacts_dir.glob("*/*")) == [catalog.artifact_path(one)]


def test_identical_registration_returns_immutable_existing_record(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path)
    first = catalog.register_stream(
        io.BytesIO(b"same"), name="model", version="1", filename="model.onnx", source="test"
    )
    second = catalog.register_stream(
        io.BytesIO(b"same"), name="model", version="1", filename="model.onnx", source="test"
    )

    assert second == first
    assert second.created_at == first.created_at
    assert len(catalog.list_models()) == 1


def test_reusing_name_and_version_for_different_bytes_is_rejected(tmp_path: Path) -> None:
    catalog = Catalog(tmp_path)
    catalog.register_stream(
        io.BytesIO(b"one"), name="model", version="1", filename="model.onnx", source="test"
    )

    with pytest.raises(CatalogConflict, match="different bytes"):
        catalog.register_stream(
            io.BytesIO(b"two"), name="model", version="1", filename="model.onnx", source="test"
        )
