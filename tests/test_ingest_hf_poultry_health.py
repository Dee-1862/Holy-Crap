from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from holy_crap_simlab.proxy_specimens import ProxySpecimenRepository
from scripts.ingest_hf_poultry_health import (
    HUGGING_FACE_URL,
    MENDELEY_URL,
    _parser,
    ingest_dataset,
)


def _jpeg(marker: bytes) -> bytes:
    return b"\xff\xd8" + marker + b"\xff\xd9"


def _write_split(path: Path, rows: list[tuple[str, bytes, int]]) -> None:
    table = pa.table(
        {
            "image": pa.array(
                [{"path": name, "bytes": content} for name, content, _ in rows],
                type=pa.struct([("bytes", pa.binary()), ("path", pa.string())]),
            ),
            "label": pa.array([label for _, _, label in rows], type=pa.int64()),
        }
    )
    pq.write_table(table, path)


def _fixture(source: Path) -> dict[str, bytes]:
    source.mkdir()
    content = {
        "train-healthy": _jpeg(b"train healthy"),
        "train-unhealthy": _jpeg(b"train unhealthy"),
        "test-healthy": _jpeg(b"test healthy"),
    }
    _write_split(
        source / "train-00000-of-00001.parquet",
        [
            ("Farm 1.JPG", content["train-healthy"], 0),
            ("Farm 2.JPG", content["train-unhealthy"], 1),
        ],
    )
    _write_split(
        source / "test-00000-of-00001.parquet",
        [("Farm 3.JPG", content["test-healthy"], 0)],
    )
    return content


def test_default_output_stays_in_the_optional_research_pool() -> None:
    args = _parser().parse_args([])
    assert args.output_dir == Path(".simlab/datasets/feces/optional-pools/nigeria")


def test_ingest_extracts_all_images_and_repository_loads_catalog(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "specimens"
    content = _fixture(source)

    result = ingest_dataset(
        source,
        output,
        expected_counts={"healthy": 2, "unknown_abnormal": 1},
    )

    assert result.total == 3
    assert result.class_counts == {"healthy": 2, "unknown_abnormal": 1}
    assert result.written == 3
    assert result.retained == 0
    catalog = json.loads(result.catalog_path.read_text(encoding="utf-8"))
    assert catalog["dataset"]["source_url"] == MENDELEY_URL
    assert catalog["dataset"]["distribution_url"] == HUGGING_FACE_URL
    assert catalog["dataset"]["license"] == "CC BY 4.0"
    assert catalog["class_counts"] == {"healthy": 2, "unknown_abnormal": 1}
    assert [row["asset_id"] for row in catalog["specimens"]] == [
        "poultry-health-train-00000",
        "poultry-health-train-00001",
        "poultry-health-test-00000",
    ]
    abnormal = catalog["specimens"][1]
    assert abnormal["expected_demo_class"] == "unknown_abnormal"
    assert abnormal["label_evidence"]["source_class"] == "unhealthy"
    assert abnormal["original_filename"] == "Farm 2.JPG"
    assert abnormal["sha256"] == hashlib.sha256(content["train-unhealthy"]).hexdigest()

    repository = ProxySpecimenRepository(output)
    summary = repository.summary()
    assert summary.total == 3
    assert summary.bytes_present == 3
    assert summary.by_expected_class["healthy"] == 2
    assert summary.by_expected_class["unknown_abnormal"] == 1
    specimen = repository.get("poultry-health-train-00001")
    assert specimen is not None
    assert repository.verified_path(specimen) is not None


def test_ingest_is_idempotent_and_repairs_corrupted_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    output = tmp_path / "specimens"
    content = _fixture(source)
    expected = {"healthy": 2, "unknown_abnormal": 1}

    first = ingest_dataset(source, output, expected_counts=expected)
    catalog_before = first.catalog_path.read_bytes()
    second = ingest_dataset(source, output, expected_counts=expected)
    assert second.written == 0
    assert second.retained == 3
    assert second.catalog_path.read_bytes() == catalog_before

    damaged = output / "images/healthy/poultry-health-train-00000.jpg"
    damaged.write_bytes(b"damaged")
    repaired = ingest_dataset(source, output, expected_counts=expected)
    assert repaired.written == 1
    assert repaired.retained == 2
    assert damaged.read_bytes() == content["train-healthy"]


def test_ingest_rejects_unknown_labels(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_split(
        source / "train-00000-of-00001.parquet",
        [("bad.jpg", _jpeg(b"bad label"), 2)],
    )
    _write_split(
        source / "test-00000-of-00001.parquet",
        [("okay.jpg", _jpeg(b"healthy"), 0)],
    )

    with pytest.raises(ValueError, match="unsupported poultry-health label"):
        ingest_dataset(source, tmp_path / "output", expected_counts=None)


def test_ingest_uses_unique_stable_indices_across_multiple_shards(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write_split(
        source / "train-00000-of-00002.parquet",
        [("one.jpg", _jpeg(b"one"), 0)],
    )
    _write_split(
        source / "train-00001-of-00002.parquet",
        [("two.jpg", _jpeg(b"two"), 1)],
    )
    _write_split(
        source / "test-00000-of-00001.parquet",
        [("three.jpg", _jpeg(b"three"), 0)],
    )

    result = ingest_dataset(
        source,
        tmp_path / "output",
        expected_counts={"healthy": 2, "unknown_abnormal": 1},
    )
    catalog = json.loads(result.catalog_path.read_text(encoding="utf-8"))

    assert [entry["asset_id"] for entry in catalog["specimens"]] == [
        "poultry-health-train-00000",
        "poultry-health-train-00001",
        "poultry-health-test-00000",
    ]
