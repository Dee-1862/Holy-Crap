from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from holy_crap_simlab.api import create_app
from holy_crap_simlab.clip_assessment import VideoProbe
from holy_crap_simlab.dataset_videos import DatasetVideoLookupError, LocalDatasetVideoStore
from holy_crap_simlab.media import InstalledAsset


@pytest.fixture
def videos_root(tmp_path: Path) -> Path:
    root = tmp_path / "videos"
    root.mkdir()
    return root


@pytest.fixture
def client_with_videos(
    tmp_path: Path, scenario_directory: Path, videos_root: Path
) -> TestClient:
    with TestClient(
        create_app(
            tmp_path / "simlab",
            scenario_directory,
            dataset_videos_directory=videos_root,
        )
    ) as test_client:
        yield test_client


def test_recursive_exact_match_exposes_playable_content(
    client_with_videos: TestClient, videos_root: Path
) -> None:
    nested = videos_root / "big-broiler" / "nested"
    nested.mkdir(parents=True)
    payload = b"\x00\x01\x02\x03local-bytes"
    (nested / "090_3_32_1920_010_0_10.mp4").write_bytes(payload)

    clip = client_with_videos.get("/api/v1/dataset-clips/big-broiler-090").json()
    assert clip["bytes_available"] is True
    assert clip["content_url"] == "/api/v1/dataset-clips/big-broiler-090/content"
    assert clip["installed_size_bytes"] == len(payload)
    assert clip["assessable"] is True

    listed = client_with_videos.get("/api/v1/dataset-clips").json()
    installed = next(item for item in listed if item["id"] == "big-broiler-090")
    assert installed["bytes_available"] is True
    assert installed["installed_size_bytes"] == len(payload)

    content = client_with_videos.get("/api/v1/dataset-clips/big-broiler-090/content")
    assert content.status_code == 200
    assert content.content == payload
    assert content.headers["content-type"].startswith("video/mp4")


def test_content_endpoint_supports_byte_ranges(
    client_with_videos: TestClient, videos_root: Path
) -> None:
    payload = b"0123456789"
    (videos_root / "mvbrotrack").mkdir()
    (videos_root / "mvbrotrack" / "3_12_2023-03-25_15_05_00_15_05_30.mp4").write_bytes(
        payload
    )

    ranged = client_with_videos.get(
        "/api/v1/dataset-clips/mvbrotrack-sample-6-camera-3/content",
        headers={"Range": "bytes=2-5"},
    )
    assert ranged.status_code == 206
    assert ranged.content == payload[2:6]
    assert ranged.headers["content-range"] == f"bytes 2-5/{len(payload)}"


def test_missing_local_file_stays_unavailable(
    client_with_videos: TestClient, client: TestClient
) -> None:
    clip = client_with_videos.get("/api/v1/dataset-clips/pio-0002").json()
    assert clip["bytes_available"] is False
    assert clip["content_url"] is None
    assert clip["installed_size_bytes"] is None

    missing = client_with_videos.get("/api/v1/dataset-clips/pio-0002/content")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    empty_home = client.get("/api/v1/dataset-clips/big-broiler-090/content")
    assert empty_home.status_code == 404
    assert empty_home.json()["error"]["code"] == "not_found"

    assert client.get("/api/v1/dataset-clips/not-a-real-clip/content").status_code == 404


def test_duplicate_filenames_are_rejected_not_guessed(
    client_with_videos: TestClient, videos_root: Path
) -> None:
    (videos_root / "a").mkdir()
    (videos_root / "b").mkdir()
    (videos_root / "a" / "090_3_32_1920_010_0_10.mp4").write_bytes(b"one")
    (videos_root / "b" / "090_3_32_1920_010_0_10.mp4").write_bytes(b"two")

    clip = client_with_videos.get("/api/v1/dataset-clips/big-broiler-090").json()
    assert clip["bytes_available"] is False
    assert clip["content_url"] is None

    ambiguous = client_with_videos.get("/api/v1/dataset-clips/big-broiler-090/content")
    assert ambiguous.status_code == 404
    assert ambiguous.json()["error"]["code"] == "not_found"


def test_unsafe_lookup_names_are_rejected(videos_root: Path) -> None:
    store = LocalDatasetVideoStore(root=videos_root)

    for unsafe in ("../escape.mp4", "sub/dir.mp4", "..", ".", "", "~backup.mp4"):
        with pytest.raises(DatasetVideoLookupError):
            store.find(unsafe)


def test_non_video_extensions_are_never_indexed(videos_root: Path) -> None:
    store = LocalDatasetVideoStore(root=videos_root)
    (videos_root / "dataset.zip").write_bytes(b"not video")

    with pytest.raises(DatasetVideoLookupError, match="unsupported dataset video extension"):
        store.find("dataset.zip")


def test_symlink_escapes_are_rejected(tmp_path: Path, videos_root: Path) -> None:
    store = LocalDatasetVideoStore(root=videos_root)

    outside_file = tmp_path / "outside-secret.mp4"
    outside_file.write_bytes(b"secret")
    links = videos_root / "links"
    links.mkdir()
    (links / "linked.mp4").symlink_to(outside_file)
    with pytest.raises(DatasetVideoLookupError):
        store.find("linked.mp4")

    outside_dir = tmp_path / "outer-dir"
    outside_dir.mkdir()
    (outside_dir / "090_3_32_1920_010_0_10.mp4").write_bytes(b"x")
    (videos_root / "escape-dir").symlink_to(outside_dir, target_is_directory=True)
    assert store.find("090_3_32_1920_010_0_10.mp4") is None


def test_reference_and_rejected_clips_preview_without_assessability(
    client_with_videos: TestClient, videos_root: Path
) -> None:
    (videos_root / "nestler-behavior").mkdir()
    (videos_root / "nestler-behavior" / "annotated_000009.mp4").write_bytes(b"annotated")
    (videos_root / "chickenverse").mkdir()
    (videos_root / "chickenverse" / "ChickenAct.mp4").write_bytes(b"chicken")

    listed = client_with_videos.get("/api/v1/dataset-clips").json()
    reference = next(item for item in listed if item["id"] == "nestler-annotated-behavior")
    assert reference["bytes_available"] is True
    assert (
        reference["content_url"]
        == "/api/v1/dataset-clips/nestler-annotated-behavior/content"
    )
    assert reference["assessable"] is False

    rejected = next(item for item in listed if item["id"] == "chickenverse-demo")
    assert rejected["bytes_available"] is True
    assert rejected["assessable"] is False

    content = client_with_videos.get("/api/v1/dataset-clips/chickenverse-demo/content")
    assert content.status_code == 200
    assert content.content == b"chicken"

    for clip_id in ("nestler-annotated-behavior", "chickenverse-demo"):
        attempt = client_with_videos.post(f"/api/v1/clip-assessments/catalog/{clip_id}")
        assert attempt.status_code == 422
        assert attempt.json()["error"]["code"] == "clip_validation_error"


def test_installed_assessable_catalog_clip_uses_local_video_bytes(
    client_with_videos: TestClient, videos_root: Path
) -> None:
    (videos_root / "big-broiler").mkdir()
    payload = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2bytes"
    (videos_root / "big-broiler" / "090_3_32_1920_010_0_10.mp4").write_bytes(payload)

    response = client_with_videos.post("/api/v1/clip-assessments/catalog/big-broiler-090")
    assert response.status_code == 201
    assessment = response.json()

    assert assessment["video"]["source"] == "dataset"
    assert assessment["video"]["catalog_clip_id"] == "big-broiler-090"
    assert assessment["video"]["bytes_available"] is True
    assert assessment["video"]["content_url"].endswith("/content")
    assert assessment["video"]["size_bytes"] == len(payload)
    assert "fell back" in " ".join(assessment["video"]["metadata_warnings"]).lower()


def test_installed_catalog_clip_probes_missing_metadata_and_accepts_segment(
    client_with_videos: TestClient,
    videos_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = videos_root / "big-broiler"
    directory.mkdir()
    path = directory / "090_3_32_1920_010_0_10.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2local-video")
    calls: list[Path] = []

    def fake_probe(probed_path: Path) -> VideoProbe:
        calls.append(probed_path)
        return VideoProbe(
            duration_s=301.4,
            width=1920,
            height=1080,
            fps=11.0,
            source="ffprobe",
        )

    monkeypatch.setattr("holy_crap_simlab.service.probe_video", fake_probe)

    clip = client_with_videos.get("/api/v1/dataset-clips/big-broiler-090")
    assert clip.status_code == 200
    payload = clip.json()
    assert payload["duration_s"] == 301.4
    assert payload["width"] == 1920
    assert payload["height"] == 1080
    assert payload["fps"] == 11.0

    assessment = client_with_videos.post(
        "/api/v1/clip-assessments/catalog/big-broiler-090"
        "?segment_start_s=120&segment_end_s=140"
    )
    assert assessment.status_code == 201
    assessed_video = assessment.json()["video"]
    assert assessed_video["duration_s"] == 301.4
    assert assessed_video["segment_start_s"] == 120
    assert assessed_video["segment_end_s"] == 140
    assert calls == [path.resolve()]


class _FakeMediaStore:
    def __init__(self, manifest, path: Path, size_bytes: int) -> None:
        self._manifest = manifest
        self._path = path
        self._size_bytes = size_bytes

    def state(self, manifest) -> InstalledAsset:
        return InstalledAsset(
            manifest=manifest,
            path=self._path,
            installed=True,
            size_bytes=self._size_bytes,
            sha256_ok=True,
        )


def test_verified_demo_asset_is_preferred_for_ready_clip(
    tmp_path: Path, scenario_directory: Path, videos_root: Path
) -> None:
    dataset_file = videos_root / "spatiotemporal-annotator" / "cam1__20250930_095000.mp4"
    dataset_file.parent.mkdir(parents=True)
    dataset_file.write_bytes(b"dataset-store-bytes")

    demo_file = tmp_path / "verified-demo.mp4"
    demo_file.write_bytes(b"verified-demo-bytes")

    application = create_app(
        tmp_path / "simlab",
        scenario_directory,
        dataset_videos_directory=videos_root,
    )
    service = application.state.service
    manifest = service.media_manifest("spatiotemporal-whole-pen")
    assert manifest is not None
    service.media_store = _FakeMediaStore(
        manifest, demo_file, size_bytes=len(b"verified-demo-bytes")
    )

    with TestClient(application) as client:
        clip = client.get("/api/v1/dataset-clips/spatiotemporal-whole-pen").json()
        assert clip["bytes_available"] is True
        assert clip["content_url"] == "/api/v1/media/spatiotemporal-whole-pen/content"
        assert clip["installed_size_bytes"] == len(b"verified-demo-bytes")

        content = client.get("/api/v1/dataset-clips/spatiotemporal-whole-pen/content")
        assert content.status_code == 200
        assert content.content == b"verified-demo-bytes"
