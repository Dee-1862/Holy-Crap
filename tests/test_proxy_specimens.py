from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from holy_crap_simlab.proxy_specimens import ProxySpecimenRepository

PLACEHOLDER = "TO_BE_FILLED_BY_ORCHESTRATOR"


def _manifest(asset_id: str, filename: str, sha256: str, demo_class: str) -> dict:
    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "filename": filename,
        "media_type": "image/jpeg",
        "sha256": sha256,
        "expected_demo_class": demo_class,
        "description": "test fixture",
        "source_dataset": "test dataset",
        "source_url": "https://example.test/dataset",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "test fixture attribution",
        "substitution_reason": "curated proxy test fixture",
    }


def _catalog_entry(
    asset_id: str,
    filename: str,
    content: bytes,
    demo_class: str,
    **extra,
) -> dict:
    return {
        "asset_id": asset_id,
        "filename": filename,
        "sha256": hashlib.sha256(content).hexdigest(),
        "expected_demo_class": demo_class,
        "description": "generated catalog fixture",
        "substitution_reason": "curated proxy test fixture",
        **extra,
    }


def _repo(tmp_path: Path, *, healthy_bytes: bytes | None = None) -> tuple[ProxySpecimenRepository, Path]:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    healthy_digest = hashlib.sha256(healthy_bytes).hexdigest() if healthy_bytes else PLACEHOLDER
    for asset_id, demo_class in (
        ("healthy", "healthy"),
        ("cocci", "cocci"),
        ("ncd", "ncd"),
        ("salmo", "salmo"),
    ):
        digest = healthy_digest if asset_id == "healthy" else PLACEHOLDER
        (directory / f"{asset_id}.json").write_text(
            json.dumps(_manifest(asset_id, f"{asset_id}.jpg", digest, demo_class)),
            encoding="utf-8",
        )
    if healthy_bytes is not None:
        (directory / "healthy.jpg").write_bytes(healthy_bytes)
    return ProxySpecimenRepository(directory), directory


def test_manifests_load_with_placeholder_and_stay_unavailable(tmp_path: Path) -> None:
    repository, _ = _repo(tmp_path)

    healthy = repository.get("healthy")
    assert healthy is not None
    assert healthy.sha256 == PLACEHOLDER
    assert healthy.bytes_expected is False
    assert healthy.selection_eligible is True
    assert repository.verified_path(healthy) is None

    reference = repository.reference(healthy)
    assert reference.content_url is None
    assert reference.bytes_available is False
    assert reference.mapping_method == "sha256-seeded"
    assert reference.expected_demo_class == "healthy"
    assert "proxy" in reference.substitution_reason.lower()
    assert reference.source_url == "https://example.test/dataset"


def test_unknown_and_path_like_ids_are_rejected(tmp_path: Path) -> None:
    repository, _ = _repo(tmp_path)

    assert repository.get("does-not-exist") is None
    assert repository.get("../healthy") is None
    assert repository.get("healthy/../ncd") is None
    assert repository.get("") is None
    assert repository.get("HEALTHY") is None
    assert repository.get("healthy ") is None


def test_verified_bytes_only_when_digest_matches(tmp_path: Path) -> None:
    content = b"fake jpeg bytes for hashing"
    repository, directory = _repo(tmp_path, healthy_bytes=content)

    healthy = repository.get("healthy")
    assert healthy is not None
    path = repository.verified_path(healthy)
    assert path is not None
    assert path.read_bytes() == content

    path.write_bytes(b"tampered bytes")
    assert repository.verified_path(healthy) is None

    placeholder = repository.get("cocci")
    assert placeholder is not None
    assert repository.verified_path(placeholder) is None
    (directory / "cocci.jpg").write_bytes(content)
    assert repository.verified_path(placeholder) is None


def test_selection_profiles_are_stable_and_composed(tmp_path: Path) -> None:
    repository, _ = _repo(tmp_path)
    video = "a" * 64

    healthy_picks = [
        repository.select_for_candidate(video, "healthy", index, "pipeline-1").expected_demo_class
        for index in range(32)
    ]
    assert set(healthy_picks) == {"healthy"}

    mixed_picks = [
        repository.select_for_candidate(video, "mixed", index, "pipeline-1").expected_demo_class
        for index in range(32)
    ]
    assert all(pick == "healthy" for pick in mixed_picks[0::2])
    assert all(pick != "healthy" for pick in mixed_picks[1::2])

    concerning_picks = [
        repository.select_for_candidate(video, "concerning", index, "pipeline-1").expected_demo_class
        for index in range(100)
    ]
    assert sum(1 for pick in concerning_picks if pick != "healthy") >= 70

    assert repository.select_for_candidate(video, "mixed", 7, "pipeline-1") == (
        repository.select_for_candidate(video, "mixed", 7, "pipeline-1")
    )
    assert repository.select_for_candidate(video, "mixed", 7, "pipeline-1") != (
        repository.select_for_candidate(video, "mixed", 8, "pipeline-1")
    )


def test_selection_needs_both_pools(tmp_path: Path) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    (directory / "healthy.json").write_text(
        json.dumps(_manifest("healthy", "healthy.jpg", PLACEHOLDER, "healthy")),
        encoding="utf-8",
    )
    repository = ProxySpecimenRepository(directory)

    with pytest.raises(ValueError, match="healthy and one abnormal"):
        repository.select_for_candidate("a" * 64, "healthy", 0, "pipeline-1")


def test_legacy_manifest_can_be_indexed_but_excluded_from_selection(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    disabled = _manifest("healthy-disabled", "disabled.jpg", PLACEHOLDER, "healthy")
    disabled["selection_eligible"] = False
    enabled = _manifest("healthy-enabled", "enabled.jpg", PLACEHOLDER, "healthy")
    abnormal = _manifest("cocci-enabled", "cocci.jpg", PLACEHOLDER, "cocci")
    for payload in (disabled, enabled, abnormal):
        (directory / f"{payload['asset_id']}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    repository = ProxySpecimenRepository(directory)

    assert repository.get("healthy-disabled") is not None
    assert repository.summary().total == 3
    selected = {
        repository.select_for_candidate("a" * 64, "healthy", index, "v1").asset_id
        for index in range(20)
    }
    assert selected == {"healthy-enabled"}


def test_unsafe_manifests_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    (directory / "healthy.json").write_text(
        json.dumps(_manifest("healthy", "healthy.jpg", PLACEHOLDER, "healthy")),
        encoding="utf-8",
    )
    (directory / "bad.json").write_text(
        json.dumps(_manifest("bad", "../escape.jpg", PLACEHOLDER, "healthy")),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="safe file name"):
        ProxySpecimenRepository(directory)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    (directory / "one.json").write_text(
        json.dumps(_manifest("healthy", "healthy.jpg", PLACEHOLDER, "healthy")),
        encoding="utf-8",
    )
    (directory / "two.json").write_text(
        json.dumps(_manifest("healthy", "other.jpg", PLACEHOLDER, "healthy")),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate proxy specimen id"):
        ProxySpecimenRepository(directory)


def test_generated_catalog_inherits_provenance_and_resolves_nested_images(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "proxy-specimens"
    image_dir = directory / "generated" / "images" / "healthy"
    image_dir.mkdir(parents=True)
    healthy_bytes = b"catalog healthy image"
    abnormal_bytes = b"catalog binary-abnormal image"
    (image_dir / "one.jpg").write_bytes(healthy_bytes)
    abnormal_path = directory / "generated" / "images" / "abnormal" / "one.jpg"
    abnormal_path.parent.mkdir(parents=True)
    abnormal_path.write_bytes(abnormal_bytes)
    catalog = {
        "schema_version": 1,
        "catalog_id": "generated-one",
        "dataset": {
            "source_dataset": "Licensed binary dropping set",
            "source_url": "https://example.test/dataset",
            "license": "Research-only; redistribution status documented",
            "attribution": "Example dataset authors",
            "acquisition_method": "downloaded through provider API",
            "redistribution_status": "local-only",
        },
        "specimens": [
            _catalog_entry(
                "generated-healthy-1",
                "images/healthy/one.jpg",
                healthy_bytes,
                "healthy",
                original_filename="DSC 001.JPG",
                label_evidence={"kind": "dataset_folder", "value": "healthy"},
            ),
            _catalog_entry(
                "generated-abnormal-1",
                "images/abnormal/one.jpg",
                abnormal_bytes,
                "unknown_abnormal",
                source_filename="unhealthy/one.jpg",
                source_sha256=hashlib.sha256(abnormal_bytes).hexdigest(),
            ),
        ],
        "class_counts": {"healthy": 1, "unknown_abnormal": 1},
    }
    (directory / "generated" / "catalog.json").write_text(
        json.dumps(catalog), encoding="utf-8"
    )

    repository = ProxySpecimenRepository(directory)

    healthy = repository.get("generated-healthy-1")
    abnormal = repository.get("generated-abnormal-1")
    assert healthy is not None and abnormal is not None
    assert healthy.original_filename == "DSC 001.JPG"
    assert healthy.label_evidence == {"kind": "dataset_folder", "value": "healthy"}
    assert abnormal.expected_demo_class == "unknown_abnormal"
    assert abnormal.source_filename == "unhealthy/one.jpg"
    assert abnormal.license == "Research-only; redistribution status documented"
    assert repository.verified_path(healthy) == image_dir / "one.jpg"
    assert repository.verified_path(abnormal) == abnormal_path
    reference = repository.reference(abnormal)
    assert reference.expected_demo_class == "unknown_abnormal"
    assert reference.license == "Research-only; redistribution status documented"


def test_selection_uses_all_verified_entries_and_skips_unavailable_catalog_rows(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    contents = {
        "healthy-1": b"healthy one",
        "healthy-2": b"healthy two",
        "abnormal-1": b"abnormal one",
    }
    for asset_id, content in contents.items():
        (directory / f"{asset_id}.jpg").write_bytes(content)
    missing = b"not installed"
    entries = [
        _catalog_entry("healthy-1", "healthy-1.jpg", contents["healthy-1"], "healthy"),
        _catalog_entry("healthy-2", "healthy-2.jpg", contents["healthy-2"], "healthy"),
        _catalog_entry("healthy-missing", "healthy-missing.jpg", missing, "healthy"),
        _catalog_entry(
            "abnormal-1", "abnormal-1.jpg", contents["abnormal-1"], "unknown_abnormal"
        ),
    ]
    for entry in entries:
        entry.update(
            source_dataset="test",
            source_url="https://example.test/dataset",
            license="unknown/local-only",
            attribution="test",
        )
    (directory / "catalog.json").write_text(
        json.dumps({"schema_version": 1, "specimens": entries}), encoding="utf-8"
    )
    repository = ProxySpecimenRepository(directory)

    selected = {
        repository.select_for_candidate("a" * 64, "healthy", index, "v1").asset_id
        for index in range(256)
    }
    assert selected == {"healthy-1", "healthy-2"}
    assert "healthy-missing" not in selected
    concerning = [
        repository.select_for_candidate("a" * 64, "concerning", index, "v1")
        for index in range(64)
    ]
    abnormal = [item for item in concerning if item.expected_demo_class != "healthy"]
    assert abnormal
    assert {item.asset_id for item in abnormal} == {"abnormal-1"}
    assert {item.expected_demo_class for item in abnormal} == {"unknown_abnormal"}


def test_cross_label_duplicates_remain_indexed_and_served_but_are_never_selected(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    duplicate = b"same photo with conflicting source labels"
    healthy = b"eligible healthy"
    abnormal = b"eligible abnormal"
    files = {
        "duplicate-healthy.jpg": duplicate,
        "duplicate-cocci.jpg": duplicate,
        "healthy.jpg": healthy,
        "cocci.jpg": abnormal,
    }
    for filename, content in files.items():
        (directory / filename).write_bytes(content)
    entries = [
        _catalog_entry(
            "duplicate-healthy",
            "duplicate-healthy.jpg",
            duplicate,
            "healthy",
            selection_eligible=False,
        ),
        _catalog_entry(
            "duplicate-cocci",
            "duplicate-cocci.jpg",
            duplicate,
            "cocci",
            selection_eligible=False,
        ),
        _catalog_entry("eligible-healthy", "healthy.jpg", healthy, "healthy"),
        _catalog_entry("eligible-cocci", "cocci.jpg", abnormal, "cocci"),
    ]
    for entry in entries:
        entry.update(
            source_dataset="conflict fixture",
            source_url="https://example.test/conflicts",
            license="test",
            attribution="test",
        )
    (directory / "catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "integrity": {
                    "conflicting_digest_group_count": 1,
                    "conflicting_row_count": 2,
                },
                "specimens": entries,
            }
        ),
        encoding="utf-8",
    )
    repository = ProxySpecimenRepository(directory)

    assert len(repository.list()) == 4
    summary = repository.summary()
    assert summary.total == 4
    assert summary.selectable_total == 2
    assert summary.by_expected_class["healthy"] == 2
    assert summary.by_expected_class["cocci"] == 2
    assert summary.selectable_by_expected_class["healthy"] == 1
    assert summary.selectable_by_expected_class["cocci"] == 1
    for asset_id in ("duplicate-healthy", "duplicate-cocci"):
        manifest = repository.get(asset_id)
        assert manifest is not None
        assert manifest.selection_eligible is False
        assert repository.verified_path(manifest) is not None

    selected = {
        repository.select_for_candidate("a" * 64, "mixed", index, "v1").asset_id
        for index in range(100)
    }
    assert selected == {"eligible-healthy", "eligible-cocci"}


def test_verification_hash_is_cached_until_file_state_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    content = b"same bytes"
    repository, directory = _repo(tmp_path, healthy_bytes=content)
    healthy = repository.get("healthy")
    assert healthy is not None
    calls = 0

    def counted(path: Path) -> str:
        nonlocal calls
        calls += 1
        return hashlib.sha256(path.read_bytes()).hexdigest()

    monkeypatch.setattr("holy_crap_simlab.proxy_specimens.sha256_file", counted)
    assert repository.verified_path(healthy) is not None
    assert repository.verified_path(healthy) is not None
    assert calls == 1

    (directory / "healthy.jpg").write_bytes(b"tampered bytes")
    assert repository.verified_path(healthy) is None
    assert calls == 2


def test_selection_hashes_only_the_chosen_candidate_in_a_large_installed_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    entries = []
    for index in range(200):
        demo_class = "healthy" if index < 100 else "unknown_abnormal"
        content = f"image-{index}".encode()
        filename = f"images/{demo_class}/{index}.jpg"
        path = directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        entry = _catalog_entry(f"lazy-{index:03d}", filename, content, demo_class)
        entry.update(
            source_dataset="test",
            source_url="https://example.test/dataset",
            license="test",
            attribution="test",
        )
        entries.append(entry)
    (directory / "catalog.json").write_text(
        json.dumps({"schema_version": 1, "specimens": entries}), encoding="utf-8"
    )
    calls = 0

    def counted(path: Path) -> str:
        nonlocal calls
        calls += 1
        return hashlib.sha256(path.read_bytes()).hexdigest()

    monkeypatch.setattr("holy_crap_simlab.proxy_specimens.sha256_file", counted)
    repository = ProxySpecimenRepository(directory)

    selected = repository.select_for_candidate("a" * 64, "healthy", 0, "v1")

    assert selected.expected_demo_class == "healthy"
    assert calls == 1


def test_catalog_indexes_thousands_of_rows_without_opening_image_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "proxy-specimens"
    directory.mkdir()
    entries = []
    for index in range(2_000):
        demo_class = "healthy" if index % 2 == 0 else "unknown_abnormal"
        entries.append(
            {
                "asset_id": f"large-{index:04d}",
                "filename": f"images/{demo_class}/{index:04d}.jpg",
                "sha256": PLACEHOLDER,
                "expected_demo_class": demo_class,
                "description": "large generated catalog fixture",
                "substitution_reason": "curated proxy test fixture",
            }
        )
    (directory / "large.catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "catalog_id": "large-fixture",
                "dataset": {
                    "source_dataset": "large test dataset",
                    "source_url": "https://example.test/large",
                    "license": "metadata-only fixture",
                    "attribution": "test",
                },
                "specimens": entries,
            }
        ),
        encoding="utf-8",
    )

    def unexpected_hash(_path: Path) -> str:
        raise AssertionError("placeholder catalog entries must not read image bytes")

    monkeypatch.setattr("holy_crap_simlab.proxy_specimens.sha256_file", unexpected_hash)
    repository = ProxySpecimenRepository(directory)

    assert len(repository.list()) == 2_000
    assert repository.get("large-1999") is not None
    summary = repository.summary()
    assert summary.total == 2_000
    assert summary.selectable_total == 2_000
    assert summary.bytes_present == 0
    assert summary.verified_cached == 0
    assert summary.by_expected_class["healthy"] == 1_000
    assert summary.by_expected_class["unknown_abnormal"] == 1_000
    assert repository.select_for_candidate(
        "a" * 64, "mixed", 0, "v1"
    ).expected_demo_class == "healthy"
    assert repository.select_for_candidate(
        "a" * 64, "mixed", 1, "v1"
    ).expected_demo_class == "unknown_abnormal"


def test_committed_manifests_have_verified_attributed_bytes() -> None:
    repository = ProxySpecimenRepository()
    manifests = {item.asset_id: item for item in repository.list()}
    assert {"cocci", "healthy", "ncd", "salmo"} <= set(manifests)
    for asset_id in ("cocci", "healthy", "ncd", "salmo"):
        manifest = manifests[asset_id]
        assert manifest.filename == f"{asset_id}.jpg"
        assert manifest.sha256 != PLACEHOLDER
        assert len(manifest.sha256) == 64
        assert manifest.bytes_expected is True
        assert manifest.media_type == "image/jpeg"
        assert manifest.license == "CC-BY-4.0"
        assert "Machuve" in manifest.attribution
        assert "10.5281/zenodo.4628934" in str(manifest.source_url)
        assert "10.5281/zenodo.4628934" in manifest.attribution
        assert repository.verified_path(manifest) is not None
