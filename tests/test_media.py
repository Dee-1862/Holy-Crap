from __future__ import annotations

import hashlib
import importlib.util
import ssl
import types
from pathlib import Path

import pytest
from pydantic import ValidationError

from holy_crap_simlab.media import (
    DemoAssetManifest,
    DemoAssetRepository,
    DemoAssetStore,
    InstalledAsset,
    UnsafeContentPath,
    resolve_content_path,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = "87bfcad1a0abb179a61e834ee00a80906780ddab6c7b2b2dd82d374517d1af25"
VIDEO_SHA256 = "ad70155b0e7491316bd6439c96dcc8712cba2517a2960ca5d5c6132fd15977d6"
REQUIRED_LIMITATIONS = (
    "reference imagery only",
    "no disease labels",
    "not spatially aligned with simulated birds",
)


def manifest_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": "pio-growth-stages",
        "title": "PIO growth-stages overhead broiler-house montage (Figure 3)",
        "description": "Reference imagery.",
        "source_url": "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/206d/13223325/b30ebfd52771/41597_2026_7114_Fig3_HTML.jpg",
        "dataset_url": "https://doi.org/10.5281/zenodo.16686320",
        "doi": "10.1038/s41597-026-07114-5",
        "creators": ["Keyla Boniche", "Edmanuel Cruz"],
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "Figure 3 from the Scientific Data article at DOI 10.1038/s41597-026-07114-5, CC BY 4.0.",
        "sha256": EXPECTED_SHA256,
        "file_size_bytes": 121814,
        "media_type": "image/jpeg",
        "width": 675,
        "height": 375,
        "filename": "pio-growth-stages.jpg",
        "limitations": list(REQUIRED_LIMITATIONS),
    }


@pytest.fixture(scope="module")
def fetcher() -> types.ModuleType:
    path = ROOT / "scripts" / "fetch_demo_assets.py"
    spec = importlib.util.spec_from_file_location("fetch_demo_assets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repository() -> DemoAssetRepository:
    return DemoAssetRepository(ROOT / "demo-assets")


def test_committed_pio_manifest_parses(repository: DemoAssetRepository) -> None:
    manifest = repository.get("pio-growth-stages")
    assert manifest is not None
    assert manifest.id == "pio-growth-stages"
    assert manifest.schema_version == 1
    assert manifest.sha256 == EXPECTED_SHA256
    assert manifest.file_size_bytes == 121814
    assert manifest.license == "CC-BY-4.0"
    assert str(manifest.license_url).rstrip("/") == "https://creativecommons.org/licenses/by/4.0"
    assert manifest.doi == "10.1038/s41597-026-07114-5"
    assert str(manifest.dataset_url) == "https://doi.org/10.5281/zenodo.16686320"
    assert str(manifest.source_url) == "https://cdn.ncbi.nlm.nih.gov/pmc/blobs/206d/13223325/b30ebfd52771/41597_2026_7114_Fig3_HTML.jpg"
    assert manifest.media_type == "image/jpeg"
    assert (manifest.width, manifest.height) == (675, 375)
    assert manifest.filename == "pio-growth-stages.jpg"
    assert "Keyla Boniche" in manifest.creators
    assert len(manifest.creators) == 5
    assert manifest.attribution
    for limitation in REQUIRED_LIMITATIONS:
        assert limitation in manifest.limitations


def test_committed_whole_pen_video_manifest_parses(repository: DemoAssetRepository) -> None:
    manifest = repository.get("spatiotemporal-whole-pen")
    assert manifest is not None
    assert manifest.sha256 == VIDEO_SHA256
    assert manifest.file_size_bytes == 1322209
    assert manifest.license == "CC-BY-4.0"
    assert str(manifest.source_url) == (
        "https://raw.githubusercontent.com/steven068zzy/spatiotemporal-annotator/"
        "3d2f2eb43888122229b0da992f9893a66a530e2a/examples/videos/"
        "cam1__20250930_095000.mp4"
    )
    assert str(manifest.dataset_url).endswith("/3d2f2eb43888122229b0da992f9893a66a530e2a/examples")
    assert manifest.doi == "not-assigned"
    assert manifest.media_type == "video/mp4"
    assert (manifest.width, manifest.height) == (848, 480)
    assert manifest.duration_s == 19.4
    assert manifest.frame_rate_fps == 5.0
    assert manifest.frame_count == 97
    assert manifest.codec == "H.264"
    assert manifest.filename == "cam1__20250930_095000.mp4"
    assert "Ziyuan Zhao" in manifest.creators
    assert "IACUC 2024-0108" in manifest.attribution
    for limitation in REQUIRED_LIMITATIONS:
        assert limitation in manifest.limitations


def test_repository_returns_none_for_unknown_id(repository: DemoAssetRepository) -> None:
    assert repository.get("does-not-exist") is None


def test_manifest_rejects_invalid_sha256() -> None:
    with pytest.raises(ValidationError):
        DemoAssetManifest.model_validate({**manifest_dict(), "sha256": "not-a-digest"})


def test_manifest_rejects_traversal_filename() -> None:
    with pytest.raises(ValidationError):
        DemoAssetManifest.model_validate({**manifest_dict(), "filename": "../escape.jpg"})


def test_manifest_requires_mandatory_limitations() -> None:
    with pytest.raises(ValidationError):
        DemoAssetManifest.model_validate({**manifest_dict(), "limitations": ["reference imagery only"]})


def test_video_manifest_requires_timing_and_codec_metadata() -> None:
    with pytest.raises(ValidationError, match="video manifests must include"):
        DemoAssetManifest.model_validate({**manifest_dict(), "media_type": "video/mp4"})


def test_store_reports_missing_asset(tmp_path: Path, repository: DemoAssetRepository) -> None:
    manifest = repository.get("pio-growth-stages")
    store = DemoAssetStore(tmp_path / "simlab")
    state = store.state(manifest)

    assert isinstance(state, InstalledAsset)
    assert not state.installed
    assert not state.sha256_ok
    assert not state.valid
    assert state.size_bytes == 0
    assert state.path == tmp_path / "simlab" / "datasets" / "demo" / "pio-growth-stages" / "pio-growth-stages.jpg"


def test_store_reports_installed_and_verified_asset(tmp_path: Path) -> None:
    content = b"\xff\xd8\xff tiny camera reference"
    manifest = DemoAssetManifest.model_validate(
        {**manifest_dict(), "sha256": hashlib.sha256(content).hexdigest()}
    )
    store = DemoAssetStore(tmp_path / "simlab")
    path = store.content_path(manifest)
    path.parent.mkdir(parents=True)
    path.write_bytes(content)

    state = store.state(manifest)
    assert state.installed
    assert state.sha256_ok
    assert state.valid
    assert state.size_bytes == len(content)
    assert sha256_file(path) == manifest.sha256


def test_store_flags_corrupt_asset(tmp_path: Path) -> None:
    manifest = DemoAssetManifest.model_validate(manifest_dict())
    store = DemoAssetStore(tmp_path / "simlab")
    path = store.content_path(manifest)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"tampered bytes")

    state = store.state(manifest)
    assert state.installed
    assert not state.sha256_ok
    assert not state.valid
    assert state.size_bytes == len(b"tampered bytes")


def test_content_path_resolves_plain_file(tmp_path: Path) -> None:
    directory = tmp_path / "assets"
    assert resolve_content_path(directory, "a-1_b.jpg") == (directory / "a-1_b.jpg").resolve()


def test_content_path_rejects_traversal(tmp_path: Path) -> None:
    for filename in ("../outside.jpg", "..", ".", "sub/dir.jpg", "/etc/passwd", "..%2Fescape.jpg"):
        with pytest.raises(UnsafeContentPath):
            resolve_content_path(tmp_path / "assets", filename)


def test_load_manifest_rejects_unknown_id(fetcher: types.ModuleType) -> None:
    with pytest.raises(fetcher.FetchError, match="no committed manifest"):
        fetcher.load_manifest("does-not-exist")


def test_fetch_downloads_and_verifies_without_network(tmp_path: Path, fetcher: types.ModuleType) -> None:
    content = b"\xff\xd8\xff fake jpeg payload"
    source = tmp_path / "source.jpg"
    source.write_bytes(content)
    manifest = {
        **manifest_dict(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "file_size_bytes": len(content),
    }
    destination = tmp_path / "home" / "datasets" / "demo" / "pio-growth-stages" / "pio-growth-stages.jpg"

    result = fetcher.fetch_asset(manifest, destination, source_url=source.as_uri(), timeout=5, max_bytes=1024)

    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["size_bytes"] == len(content)
    assert destination.read_bytes() == content
    assert list(destination.parent.glob(".pio-growth-stages.jpg.*")) == []


def test_fetch_rejects_hash_mismatch_without_installing(tmp_path: Path, fetcher: types.ModuleType) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"wrong bytes")
    manifest = {
        **manifest_dict(),
        "sha256": hashlib.sha256(b"expected bytes").hexdigest(),
        "file_size_bytes": len(b"wrong bytes"),
    }
    destination = tmp_path / "asset.bin"

    with pytest.raises(fetcher.FetchError, match="sha256 mismatch"):
        fetcher.fetch_asset(manifest, destination, source_url=source.as_uri(), timeout=5, max_bytes=1024)

    assert not destination.exists()
    assert list(tmp_path.glob(".asset.bin.*")) == []


def test_fetch_enforces_size_limit(tmp_path: Path, fetcher: types.ModuleType) -> None:
    content = b"x" * 256
    source = tmp_path / "source.bin"
    source.write_bytes(content)
    manifest = {
        **manifest_dict(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "file_size_bytes": len(content),
    }
    destination = tmp_path / "asset.bin"

    with pytest.raises(fetcher.FetchError, match="size limit"):
        fetcher.fetch_asset(manifest, destination, source_url=source.as_uri(), timeout=5, max_bytes=64)

    assert not destination.exists()


def test_fetch_rejects_size_mismatch_without_installing(tmp_path: Path, fetcher: types.ModuleType) -> None:
    content = b"correct digest but unexpected length"
    source = tmp_path / "source.bin"
    source.write_bytes(content)
    manifest = {
        **manifest_dict(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "file_size_bytes": len(content) + 1,
    }
    destination = tmp_path / "asset.bin"

    with pytest.raises(fetcher.FetchError, match="size mismatch"):
        fetcher.fetch_asset(manifest, destination, source_url=source.as_uri(), timeout=5, max_bytes=1024)

    assert not destination.exists()


def test_load_manifests_defaults_to_every_committed_asset(fetcher: types.ModuleType) -> None:
    manifests = fetcher.load_manifests()
    assert [manifest["id"] for manifest in manifests] == [
        "pio-growth-stages",
        "spatiotemporal-whole-pen",
    ]


def test_build_ssl_context_rejects_missing_explicit_bundle(
    tmp_path: Path, fetcher: types.ModuleType
) -> None:
    with pytest.raises(fetcher.FetchError, match="configured CA bundle does not exist"):
        fetcher.build_ssl_context(tmp_path / "missing.pem")


def test_build_ssl_context_uses_explicit_ca_bundle(fetcher: types.ModuleType) -> None:
    cafile = ssl.get_default_verify_paths().cafile or "/etc/ssl/cert.pem"
    if not Path(cafile).is_file():
        pytest.skip("no trusted system CA bundle available")
    context = fetcher.build_ssl_context(cafile)
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
