from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from holy_crap_simlab.api import create_app
from holy_crap_simlab.clip_assessment import (
    ClipAssessmentService,
    ClipAssessmentStore,
    ClipValidationError,
    DeterministicClipPipeline,
    VideoProbe,
    probe_video,
)


def fake_mp4(payload: bytes = b"whole pen video") -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + payload


def test_upload_is_immutable_content_addressed_and_deterministic(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    content = fake_mp4()

    first = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4")
    second = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4")

    assert first.id != second.id
    assert first.video.sha256 == hashlib.sha256(content).hexdigest()
    assert first.video.sha256 == second.video.sha256
    assert first.summary == second.summary
    assert first.modules == second.modules
    assert first.video.metadata_source in {"ffprobe", "unavailable"}
    blob = service.store.blob_path(first.video.sha256)
    assert blob.read_bytes() == content
    assert len(list((tmp_path / "simlab" / "clips" / "blobs").glob("*/*"))) == 1
    assert len(service.store.list()) == 2


def test_pipeline_returns_one_aggregate_without_bird_ids_or_progression(tmp_path: Path) -> None:
    content = fake_mp4(b"aggregate contract")
    store = ClipAssessmentStore(tmp_path / "simlab")
    stored = store.ingest_stream(
        io.BytesIO(content), filename="five-minutes.mp4", media_type="video/mp4"
    )
    result = DeterministicClipPipeline().assess(
        stored=stored,
        filename="five-minutes.mp4",
        media_type="video/mp4",
        source="upload",
        probe=VideoProbe(
            duration_s=300,
            width=1920,
            height=1080,
            fps=11,
            source="ffprobe",
        ),
    )

    assert result.status == "completed"
    assert result.video.duration_s == 300
    assert "SYNTHETIC MOCK OUTPUT" in result.non_diagnostic_notice
    assert result.summary.overall.review_state == "synthetic-demo-only"
    assert set(result.summary.model_dump()) == {"activity", "appearance", "feces", "overall"}
    assert "bird_id" not in result.model_dump_json().lower()
    assert result.summary.feces.candidate_count == len(result.summary.feces.candidates)
    assert sum(result.summary.feces.class_distribution.values()) == len(
        result.summary.feces.candidates
    )
    assert all(0 <= candidate.timestamp_s <= 300 for candidate in result.summary.feces.candidates)
    assert all(candidate.classification.mode == "mock" for candidate in result.summary.feces.candidates)
    assert all(candidate.crop.materialized is False for candidate in result.summary.feces.candidates)


def test_classifier_module_exposes_future_real_handoff() -> None:
    modules = {module.id: module for module in DeterministicClipPipeline().modules()}
    classifier = modules["feces-disease-classifier"]

    assert classifier.mode == "mock"
    assert classifier.input_contract == {
        "kind": "detected_feces_crop",
        "color_space": "RGB",
        "width": 224,
        "height": 224,
        "upstream": "feces-candidate-detector",
    }
    assert classifier.output_contract["labels"] == [
        "Coccidiosis",
        "Healthy",
        "New Castle Disease",
        "Salmonella",
    ]
    assert classifier.artifact.status == "not_configured"
    assert classifier.artifact.model_id is None
    assert classifier.artifact.compatibility_verified is False
    assert "no real inference ran" in classifier.notice


@pytest.mark.parametrize(
    ("filename", "media_type", "content", "message"),
    [
        ("../pen.mp4", "video/mp4", fake_mp4(), "plain filename"),
        ("pen.txt", "video/mp4", fake_mp4(), "unsupported video extension"),
        ("pen.mp4", "text/plain", fake_mp4(), "unsupported video content type"),
        ("pen.mov", "video/mp4", fake_mp4(), "does not match"),
        ("pen.mp4", "video/mp4", b"not a video", "file signature"),
        ("pen.mp4", "video/mp4", b"", "empty"),
    ],
)
def test_upload_validation(
    tmp_path: Path, filename: str, media_type: str, content: bytes, message: str
) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    with pytest.raises(ClipValidationError, match=message):
        service.assess_upload(io.BytesIO(content), filename, media_type)
    assert list((tmp_path / "simlab" / "clips" / "staging").iterdir()) == []


def test_upload_size_limit_cleans_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOLY_CRAP_MAX_VIDEO_BYTES", "24")
    service = ClipAssessmentService(tmp_path / "simlab")
    with pytest.raises(ClipValidationError, match="upload limit"):
        service.assess_upload(io.BytesIO(fake_mp4(b"too large")), "pen.mp4", "video/mp4")
    assert list((tmp_path / "simlab" / "clips" / "staging").iterdir()) == []


def test_ffprobe_metadata_and_safe_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "odd name;$(no).mp4"
    path.write_bytes(fake_mp4())
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "width": 1280,
                            "height": 720,
                            "avg_frame_rate": "11/1",
                            "duration": "300.25",
                        }
                    ],
                    "format": {"duration": "300.25"},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("holy_crap_simlab.clip_assessment.subprocess.run", fake_run)
    result = probe_video(path)

    assert result == VideoProbe(
        duration_s=300.25,
        width=1280,
        height=720,
        fps=11.0,
        source="ffprobe",
        warnings=(),
    )
    assert captured["command"][-1] == str(path)
    assert isinstance(captured["command"], list)
    assert "shell" not in captured["kwargs"]


def test_ffprobe_missing_falls_back_without_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("holy_crap_simlab.clip_assessment.subprocess.run", missing)
    result = probe_video(tmp_path / "video.mp4")

    assert result.source == "unavailable"
    assert result.duration_s is None
    assert result.warnings == ("ffprobe is not installed; technical metadata unavailable",)


def _demo_client(tmp_path: Path, scenario_directory: Path) -> tuple[TestClient, bytes]:
    content = fake_mp4(b"installed demo")
    digest = hashlib.sha256(content).hexdigest()
    manifests = tmp_path / "demo-assets"
    manifests.mkdir()
    (manifests / "demo-video.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "demo-video",
                "title": "Test whole-pen clip",
                "description": "Test fixture",
                "source_url": "https://example.test/demo.mp4",
                "dataset_url": "https://example.test/dataset",
                "doi": "not-assigned",
                "creators": ["Test"],
                "license": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution": "Test fixture",
                "sha256": digest,
                "file_size_bytes": len(content),
                "media_type": "video/mp4",
                "width": 848,
                "height": 480,
                "duration_s": 19.4,
                "frame_rate_fps": 5,
                "frame_count": 97,
                "codec": "H.264",
                "filename": "demo.mp4",
                "limitations": [
                    "reference imagery only",
                    "no disease labels",
                    "not spatially aligned with simulated birds",
                ],
            }
        ),
        encoding="utf-8",
    )
    home = tmp_path / "simlab"
    installed = home / "datasets" / "demo" / "demo-video" / "demo.mp4"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(content)
    return TestClient(create_app(home, scenario_directory, manifests)), content


def test_clip_assessment_api_upload_list_get_and_content(client: TestClient) -> None:
    content = fake_mp4(b"api clip")
    response = client.post(
        "/api/v1/clip-assessments/upload",
        files={"file": ("whole-pen.mp4", content, "video/mp4")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["video"]["source"] == "upload"
    assert result["summary"]["overall"]["review_state"] == "synthetic-demo-only"
    assert {module["mode"] for module in result["modules"]} == {"mock"}
    assessment_id = result["id"]
    assert client.get(f"/api/v1/clip-assessments/{assessment_id}").json() == result
    assert client.get("/api/v1/clip-assessments").json() == [result]
    content_response = client.get(f"/api/v1/clip-assessments/{assessment_id}/content")
    assert content_response.status_code == 200
    assert content_response.content == content


def test_clip_assessment_api_rejects_bad_upload(client: TestClient) -> None:
    response = client.post(
        "/api/v1/clip-assessments/upload",
        files={"file": ("not-video.mp4", b"plain text", "video/mp4")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "clip_validation_error"


def test_demo_media_endpoint_uses_verified_manifest(
    tmp_path: Path, scenario_directory: Path
) -> None:
    client, content = _demo_client(tmp_path, scenario_directory)
    response = client.post("/api/v1/clip-assessments/demo/demo-video")

    assert response.status_code == 201
    result = response.json()
    assert result["video"]["source"] == "demo"
    assert result["video"]["demo_asset_id"] == "demo-video"
    assert result["video"]["metadata_source"] == "demo_manifest"
    assert result["video"]["duration_s"] == 19.4
    assert result["video"]["sha256"] == hashlib.sha256(content).hexdigest()


def test_missing_clip_assessment_is_structured_404(client: TestClient) -> None:
    response = client.get("/api/v1/clip-assessments/clip-00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
