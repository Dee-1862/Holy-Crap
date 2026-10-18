from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "proxy_specimen_dataset.py"
SPEC = importlib.util.spec_from_file_location("proxy_specimen_dataset", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

JPEG = b"\xff\xd8\xff\xe0" + b"fixture-jpeg"
PNG = b"\x89PNG\r\n\x1a\n" + b"fixture-png"


def _write_zip(
    path: Path,
    files: dict[str, bytes],
    compression: int = zipfile.ZIP_STORED,
) -> None:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def test_zip_ingestion_maps_classes_evidence_and_hashes(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    _write_zip(
        archive,
        {
            "Train/cocci.1.jpg": JPEG + b"1",
            "Train/pcrhealthy.2.jpg": JPEG + b"2",
            "Train/ncd.3.png": PNG + b"3",
            "Train/salmo.4.jpg": JPEG + b"4",
            "train_data.csv": b"images,label\n",
            "Train/unknown.jpg": JPEG + b"?",
        },
    )
    output = tmp_path / "pool"

    summary = module.build_catalog(archive, output, "manual-local")
    catalog_path = output / module.CATALOG_FILENAME
    catalog = json.loads(catalog_path.read_text())

    assert summary["specimens"] == 4
    assert summary["ignored_non_images"] == 1
    assert summary["ignored_unclassified_images"] == 1
    assert catalog["catalog_id"] == "kaggle-chicken-disease-1-v1"
    assert catalog["dataset"]["license"] == "Unknown / local-use only"
    specimens = catalog["specimens"]
    assert [item["expected_demo_class"] for item in specimens] == sorted(
        ["cocci", "healthy", "ncd", "salmo"]
    )
    healthy = next(item for item in specimens if item["expected_demo_class"] == "healthy")
    assert healthy["label_evidence"] == "pcr"
    for item in specimens:
        content = (output / item["filename"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == item["sha256"] == item["source_sha256"]
        assert item["selection_eligible"] is True


def test_duplicate_statistics_and_cross_label_conflicts_are_ineligible(tmp_path: Path) -> None:
    archive = tmp_path / "duplicates.zip"
    same_label = JPEG + b"same-label"
    conflicting = JPEG + b"conflicting"
    _write_zip(
        archive,
        {
            "Train/healthy.1.jpg": same_label,
            "Train/healthy.2.jpg": same_label,
            "Train/pcrhealthy.3.jpg": conflicting,
            "Train/pcrsalmo.4.jpg": conflicting,
            "Train/cocci.5.jpg": JPEG + b"unique",
        },
    )

    summary = module.build_catalog(archive, tmp_path / "pool", "manual-local")
    catalog = json.loads((tmp_path / "pool" / module.CATALOG_FILENAME).read_text())

    expected_integrity = {
        "conflicting_digest_group_count": 1,
        "conflicting_row_count": 2,
        "duplicate_digest_group_count": 2,
        "duplicate_row_count": 2,
        "same_label_duplicate_excluded_row_count": 1,
        "selection_eligible_row_count": 2,
        "total_specimen_rows": 5,
        "unique_sha256_count": 3,
    }
    assert catalog["integrity"] == expected_integrity
    assert all(summary[key] == value for key, value in expected_integrity.items())

    same_label_rows = [
        item for item in catalog["specimens"] if item["sha256"] == hashlib.sha256(same_label).hexdigest()
    ]
    assert len(same_label_rows) == 2
    canonical = min(same_label_rows, key=lambda item: item["asset_id"])
    duplicate = max(same_label_rows, key=lambda item: item["asset_id"])
    assert canonical["selection_eligible"] is True
    assert canonical["canonical_asset_id"] == canonical["asset_id"]
    assert canonical["selection_exclusion_reason"] is None
    assert duplicate["selection_eligible"] is False
    assert duplicate["canonical_asset_id"] == canonical["asset_id"]
    assert duplicate["selection_exclusion_reason"] == "exact-byte-duplicate"

    conflicting_rows = [
        item
        for item in catalog["specimens"]
        if item["sha256"] == hashlib.sha256(conflicting).hexdigest()
    ]
    assert {item["expected_demo_class"] for item in conflicting_rows} == {"healthy", "salmo"}
    assert all(item["selection_eligible"] is False for item in conflicting_rows)
    assert all(item["selection_exclusion_reason"] == "conflicting-labels" for item in conflicting_rows)
    assert {item["canonical_asset_id"] for item in conflicting_rows} == {
        min(item["asset_id"] for item in conflicting_rows)
    }


def test_directory_and_zip_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "Train").mkdir(parents=True)
    (source / "Train" / "healthy.2.jpg").write_bytes(JPEG + b"2")
    (source / "Train" / "pcrncd.1.jpg").write_bytes(JPEG + b"1")
    output = tmp_path / "pool"
    module.build_catalog(source, output, "manual-local")
    first = (output / module.CATALOG_FILENAME).read_bytes()
    module.build_catalog(source, output, "manual-local")
    assert (output / module.CATALOG_FILENAME).read_bytes() == first

    catalog = json.loads(first)
    assert [item["asset_id"] for item in catalog["specimens"]] == sorted(
        item["asset_id"] for item in catalog["specimens"]
    )


def test_unsafe_zip_member_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    _write_zip(archive, {"../escape.jpg": JPEG, "Train/healthy.1.jpg": JPEG})
    with pytest.raises(module.DatasetError, match="unsafe archive path"):
        module.build_catalog(archive, tmp_path / "pool", "manual-local")
    assert not (tmp_path / "escape.jpg").exists()


def test_oversized_zip_member_is_rejected_before_read(tmp_path: Path) -> None:
    archive = tmp_path / "oversized.zip"
    _write_zip(archive, {"Train/healthy.1.jpg": JPEG + (b"x" * 100)})
    with pytest.raises(module.DatasetError, match="ZIP member exceeds 50"):
        list(module.iter_source_images(archive, max_member_bytes=50))


def test_extreme_zip_compression_ratio_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "high-ratio.zip"
    _write_zip(
        archive,
        {"Train/healthy.1.jpg": JPEG + (b"A" * 100_000)},
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(module.DatasetError, match="compression ratio"):
        list(module.iter_source_images(archive, max_compression_ratio=10))


def test_excessive_total_uncompressed_zip_size_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "too-large-total.zip"
    _write_zip(
        archive,
        {
            "Train/healthy.1.jpg": JPEG + (b"1" * 40),
            "Train/cocci.2.jpg": JPEG + (b"2" * 40),
        },
    )
    with pytest.raises(module.DatasetError, match="total uncompressed bytes"):
        list(
            module.iter_source_images(
                archive,
                max_member_bytes=100,
                max_total_bytes=80,
            )
        )


def test_extension_does_not_make_non_image_valid(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "healthy.jpg").write_bytes(b"not an image")
    with pytest.raises(module.DatasetError, match="no classifiable"):
        module.build_catalog(source, tmp_path / "pool", "manual-local")


def test_fetch_kaggle_without_cli_has_manual_guidance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)
    with pytest.raises(module.DatasetError, match="Download the dataset in your browser"):
        module.fetch_kaggle(tmp_path)


def test_cli_reports_actionable_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    result = module.main(["ingest", "--input", str(tmp_path / "missing.zip")])
    assert result == 2
    assert "input does not exist" in capsys.readouterr().err
