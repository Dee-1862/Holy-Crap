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
    ClipValidationError,
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


def test_local_video_ingest_uses_content_addressed_hard_link(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    source = tmp_path / "installed.mp4"
    source.write_bytes(fake_mp4(b"large installed dataset fixture"))

    stored = service.store.ingest_file(
        source, filename=source.name, media_type="video/mp4"
    )

    assert stored.path.read_bytes() == source.read_bytes()
    assert stored.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    # pytest's temp directory and the assessment home share a filesystem here.
    assert stored.path.stat().st_ino == source.stat().st_ino


def test_pipeline_returns_one_aggregate_without_bird_ids_or_progression(tmp_path: Path) -> None:
    content = fake_mp4(b"aggregate contract")
    service = ClipAssessmentService(tmp_path / "simlab")
    store = service.store
    stored = store.ingest_stream(
        io.BytesIO(content), filename="five-minutes.mp4", media_type="video/mp4"
    )
    result = service.pipeline.assess(
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
    assert result.video_annotations == []
    assert result.profile.value == "mixed"
    assert result.video.duration_s == 300
    assert "SYNTHETIC MOCK OUTPUT" in result.non_diagnostic_notice
    assert "did NOT come from this video" in result.non_diagnostic_notice
    assert result.summary.overall.review_state == "synthetic-demo-only"
    assert set(result.summary.model_dump()) == {
        "activity",
        "appearance",
        "feces",
        "overall",
        "pen_assessment",
    }
    assert "bird_id" not in result.model_dump_json().lower()
    assert result.summary.feces.candidate_count == len(result.summary.feces.candidates)
    assert sum(result.summary.feces.class_distribution.values()) == len(
        result.summary.feces.candidates
    )
    assert all(0 <= candidate.timestamp_s <= 300 for candidate in result.summary.feces.candidates)
    assert all(candidate.classification.mode == "real" for candidate in result.summary.feces.candidates)
    assert all(
        candidate.classification.inference_performed is True
        for candidate in result.summary.feces.candidates
    )
    assert all(candidate.crop.materialized is False for candidate in result.summary.feces.candidates)
    assert all(
        candidate.provenance.location_source == "deterministic_overlay"
        for candidate in result.summary.feces.candidates
    )
    assert all(
        candidate.provenance.appearance_input == "curated_proxy"
        for candidate in result.summary.feces.candidates
    )
    assert all(
        candidate.crop.source_video_sha256 == result.video.sha256
        for candidate in result.summary.feces.candidates
    )
    assert all(candidate.proxy_crop is not None for candidate in result.summary.feces.candidates)
    assert all(candidate.proxy_crop.bytes_available for candidate in result.summary.feces.candidates)
    assert all(candidate.proxy_crop.content_url for candidate in result.summary.feces.candidates)
    classifier = next(
        module for module in result.modules if module.id == "feces-disease-classifier"
    )
    assert classifier.mode == "real"
    assert classifier.output_contract["execution_coverage"] == "full"
    assert classifier.output_contract["real_candidate_count"] == len(
        result.summary.feces.candidates
    )
    assert classifier.output_contract["fallback_candidate_count"] == 0
    pen = result.summary.pen_assessment
    assert pen is not None
    assert pen.policy_id == "demo-pen-v1"
    assert pen.evidence_mode == "hybrid_simulation"
    assert pen.non_diagnostic is True
    assert any("mock" in reason for reason in pen.reasons)
    assert any("proxy" in reason for reason in pen.reasons)
    assert pen.score == round(pen.feces_contribution + pen.activity_contribution, 3)


def test_classifier_module_exposes_configured_real_handoff(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    modules = {module.id: module for module in service.pipeline.modules()}
    classifier = modules["feces-disease-classifier"]

    assert classifier.mode == "real"
    assert classifier.input_contract == {
        "kind": "detected_feces_crop_or_curated_proxy",
        "color_space": "RGB",
        "width": 320,
        "height": 320,
        "upstream": "feces-candidate-detector",
    }
    assert classifier.output_contract == {
        "kind": "detection_with_appearance_classification",
        "labels": [
            "Coccidiosis",
            "Healthy",
            "New Castle Disease",
            "Salmonella",
        ],
        "bbox_coordinates": "normalized_xywh",
        "objectness": False,
        "execution_coverage": "configured",
        "real_candidate_count": 0,
        "fallback_candidate_count": 0,
        "fallback_reason_counts": {},
    }
    assert classifier.artifact.status == "configured"
    assert classifier.artifact.model_id == "dropping4-laptop"
    assert classifier.artifact.compatibility_verified is True
    assert "Live YOLO11n ONNX run" in classifier.notice
    assert "did not come from the assessed video" in classifier.notice
    assert "320" in classifier.version


def test_classifier_module_reports_partial_candidate_execution(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    result = service.assess_upload(
        io.BytesIO(fake_mp4(b"partial module")), "pen.mp4", "video/mp4"
    )
    candidates = list(result.summary.feces.candidates)
    first = candidates[0]
    candidates[0] = first.model_copy(
        update={
            "classification": first.classification.model_copy(
                update={
                    "mode": "mock",
                    "inference_performed": False,
                    "fallback_reason": "model_inference_failed",
                }
            )
        }
    )
    feces = result.summary.feces.model_copy(update={"candidates": candidates})

    classifier = next(
        module
        for module in service.pipeline.modules(feces)
        if module.id == "feces-disease-classifier"
    )

    assert classifier.mode == "partial"
    assert classifier.output_contract["execution_coverage"] == "partial"
    assert classifier.output_contract["real_candidate_count"] == len(candidates) - 1
    assert classifier.output_contract["fallback_candidate_count"] == 1
    assert classifier.output_contract["fallback_reason_counts"] == {
        "model_inference_failed": 1
    }
    assert "model_inference_failed=1" in classifier.notice


def test_real_video_crop_is_classified_without_proxy_substitution(tmp_path: Path) -> None:
    from PIL import Image

    from holy_crap_simlab.dropping_inference import DroppingInferenceResult
    from holy_crap_simlab.models import (
        ClipActivitySummary,
        FecesClassifierModel,
        FecesCropReference,
        NormalizedBoundingBox,
        VideoAnnotation,
    )
    from holy_crap_simlab.proxy_specimens import ProxySpecimenRepository
    from holy_crap_simlab.video_inference import ObservedCandidate, VideoInferenceResult

    bbox = NormalizedBoundingBox(x=0.1, y=0.2, width=0.03, height=0.04)
    crop = Image.new("RGB", (96, 96), (80, 60, 40))
    crop_sha = hashlib.sha256(crop.tobytes()).hexdigest()
    observed = ObservedCandidate(
        id="feces-001",
        timestamp_s=4.0,
        bbox=bbox,
        confidence=0.91,
        crop_reference=FecesCropReference(
            source_video_sha256=hashlib.sha256(fake_mp4(b"real crop")).hexdigest(),
            timestamp_s=4.0,
            bbox=bbox,
            materialized=True,
        ),
        crop_image=crop,
        crop_sha256=crop_sha,
    )

    class _VideoInference:
        def analyze(
            self, _path, _sha, _duration, *, segment_start_s=0.0, segment_end_s=None
        ):
            assert segment_start_s == 0.0
            assert segment_end_s is None
            return VideoInferenceResult(
                activity=ClipActivitySummary(
                    score=0.6,
                    category="typical",
                    motion_coverage=0.1,
                    zone_scores={},
                    sampled_frames=3,
                    bird_observations=8,
                    behavior_distribution={"moving": 0.5, "inactive": 0.5},
                ),
                candidates=[observed],
                frames_sampled=3,
                bird_observations=8,
                activity_mode="real",
                detector_mode="real",
                activity_notice="real behavior fixture",
                detector_notice="real detector fixture",
                annotations=[
                    VideoAnnotation(
                        id="feces-001-s00-00",
                        kind="dropping",
                        timestamp_s=4.0,
                        bbox=bbox,
                        detection_confidence=0.91,
                        candidate_id="feces-001",
                        sample_index=0,
                    )
                ],
                dropping_frames_sampled=3,
            )

    class _Classifier:
        MODEL_ID = "dropping4-laptop"
        MODEL_VERSION = "test-320"
        INPUT_SIZE = 320

        def available(self):
            return True

        def provenance(self):
            return FecesClassifierModel(
                id=self.MODEL_ID,
                version=self.MODEL_VERSION,
                sha256=None,
                format="onnx",
                input_size=[1, 3, 320, 320],
                runtime="test",
            )

        def infer(self, image, input_sha256):
            assert image is crop
            assert input_sha256 == crop_sha
            return DroppingInferenceResult(
                scores={"cocci": 0.8, "healthy": 0.1, "ncd": 0.05, "salmo": 0.05},
                class_name="cocci",
                score=0.8,
                product_label="abnormal",
                model_detection_bbox=bbox,
                raw_letterbox_bbox=(10, 10, 5, 5),
            )

    content = fake_mp4(b"real crop")
    proxy_dir = tmp_path / "kaggle-proxies"
    proxy_dir.mkdir()
    for asset_id, expected_class, color in (
        ("kaggle-healthy", "healthy", (90, 70, 45)),
        ("kaggle-cocci", "cocci", (110, 45, 30)),
    ):
        specimen_buffer = io.BytesIO()
        Image.new("RGB", (24, 24), color).save(specimen_buffer, format="JPEG")
        specimen_bytes = specimen_buffer.getvalue()
        (proxy_dir / f"{asset_id}.jpg").write_bytes(specimen_bytes)
        (proxy_dir / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset_id": asset_id,
                    "filename": f"{asset_id}.jpg",
                    "media_type": "image/jpeg",
                    "sha256": hashlib.sha256(specimen_bytes).hexdigest(),
                    "expected_demo_class": expected_class,
                    "description": "Verified Kaggle explainability fixture",
                    "source_dataset": "Chicken Disease 1 on Kaggle",
                    "source_url": "https://www.kaggle.com/datasets/allandclive/chicken-disease-1",
                    "license": "dataset terms",
                    "attribution": "Kaggle dataset fixture",
                    "substitution_reason": "Test reference",
                }
            ),
            encoding="utf-8",
        )
    service = ClipAssessmentService(
        tmp_path / "simlab",
        proxy_repository=ProxySpecimenRepository(proxy_dir),
        inference=_Classifier(),
        video_inference=_VideoInference(),
    )
    result = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4")

    candidate = result.summary.feces.candidates[0]
    assert candidate.crop.materialized is True
    assert candidate.proxy_crop is not None
    assert candidate.proxy_crop.bytes_available is True
    assert candidate.proxy_crop.content_url is not None
    assert "kaggle.com" in candidate.proxy_crop.source_url
    assert candidate.proxy_crop.expected_demo_class == "cocci"
    assert "Illustrative" in candidate.proxy_crop.substitution_reason
    assert candidate.provenance.appearance_input == "observed_crop"
    assert candidate.provenance.location_source == "observed_video"
    assert candidate.classification.inference_performed is True
    assert candidate.classification.input_sha256 == crop_sha
    assert candidate.classification.input_sha256 != candidate.proxy_crop.sha256
    assert len(result.video_annotations) == 1
    assert result.video_annotations[0].candidate_id == candidate.id
    persisted = service.store.get(result.id)
    assert persisted is not None
    assert persisted.video_annotations == result.video_annotations
    assert result.summary.overall.review_state == "non-diagnostic-review"
    assert "BOUNDED REAL MODEL EVIDENCE" in result.non_diagnostic_notice


def test_unavailable_proxy_has_no_content_url_and_reports_safe_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    monkeypatch.setattr(service.proxy_repository, "verified_path", lambda _manifest: None)

    result = service.assess_upload(
        io.BytesIO(fake_mp4(b"missing specimen")), "pen.mp4", "video/mp4"
    )

    for candidate in result.summary.feces.candidates:
        assert candidate.classification.mode == "mock"
        assert candidate.classification.fallback_reason == "specimen_unavailable"
        assert candidate.proxy_crop is not None
        assert candidate.proxy_crop.bytes_available is False
        assert candidate.proxy_crop.content_url is None
    classifier = next(
        module for module in result.modules if module.id == "feces-disease-classifier"
    )
    assert classifier.mode == "mock"
    assert classifier.output_contract["execution_coverage"] == "fallback"
    assert classifier.output_contract["fallback_reason_counts"] == {
        "specimen_unavailable": len(result.summary.feces.candidates)
    }
    assert "specimen_unavailable" in classifier.notice


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
    assert {module["mode"] for module in result["modules"]} == {"mock", "real"}
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
    assert result["video"]["segment_start_s"] == 0
    assert result["video"]["segment_end_s"] == 19.4
    assert result["video"]["sha256"] == hashlib.sha256(content).hexdigest()


def test_demo_segment_is_recorded_and_uses_absolute_source_timestamps(
    tmp_path: Path, scenario_directory: Path
) -> None:
    client, _content = _demo_client(tmp_path, scenario_directory)

    response = client.post(
        "/api/v1/clip-assessments/demo/demo-video"
        "?segment_start_s=5&segment_end_s=12"
    )

    assert response.status_code == 201
    result = response.json()
    assert result["video"]["duration_s"] == 19.4
    assert result["video"]["segment_start_s"] == 5
    assert result["video"]["segment_end_s"] == 12
    assert all(
        5 <= candidate["timestamp_s"] <= 12
        for candidate in result["summary"]["feces"]["candidates"]
    )


def test_demo_segment_rejects_invalid_or_out_of_bounds_ranges(
    tmp_path: Path, scenario_directory: Path
) -> None:
    client, _content = _demo_client(tmp_path, scenario_directory)

    reversed_range = client.post(
        "/api/v1/clip-assessments/demo/demo-video"
        "?segment_start_s=12&segment_end_s=5"
    )
    out_of_bounds = client.post(
        "/api/v1/clip-assessments/demo/demo-video"
        "?segment_start_s=5&segment_end_s=25"
    )

    assert reversed_range.status_code == 422
    assert out_of_bounds.status_code == 422
    assert out_of_bounds.json()["error"]["code"] == "clip_validation_error"


def test_missing_clip_assessment_is_structured_404(client: TestClient) -> None:
    response = client.get("/api/v1/clip-assessments/clip-00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


# --- profiles, pen policy, provenance, compatibility ---------------------------


def test_profiles_shape_proxy_selection(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    repository = service.proxy_repository
    video = "a" * 64

    healthy_picks = [
        repository.select_for_candidate(video, "healthy", index, "test").expected_demo_class
        for index in range(40)
    ]
    assert set(healthy_picks) == {"healthy"}

    mixed_picks = [
        repository.select_for_candidate(video, "mixed", index, "test").expected_demo_class
        for index in range(40)
    ]
    assert all(mixed_picks[index] == "healthy" for index in range(0, 40, 2))
    assert all(mixed_picks[index] != "healthy" for index in range(1, 40, 2))

    concerning_picks = [
        repository.select_for_candidate(video, "concerning", index, "test").expected_demo_class
        for index in range(100)
    ]
    abnormal = sum(1 for pick in concerning_picks if pick != "healthy")
    assert abnormal >= 70

    first = repository.select_for_candidate(video, "mixed", 3, "1.1.0")
    second = repository.select_for_candidate(video, "mixed", 3, "1.1.0")
    assert first == second


def test_upload_profile_is_recorded_and_defaults_to_mixed(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    content = fake_mp4(b"profile test")

    defaulted = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4")
    concerned = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4", "concerning")

    assert defaulted.profile.value == "mixed"
    assert concerned.profile.value == "concerning"
    assert (
        defaulted.summary.feces.candidate_count == concerned.summary.feces.candidate_count
    )

    with pytest.raises(ClipValidationError, match="unknown demo profile"):
        service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4", "not-a-profile")


def test_catalog_mock_uses_overlay_provenance(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    clip = SimpleNamespace(
        id="clip-one",
        assessable=True,
        media_kind="video",
        filename="catalog.mp4",
        title="Catalog clip",
        media_type="video/mp4",
        duration_s=60.0,
        width=1280,
        height=720,
        fps=5.0,
        demo_asset_id=None,
    )
    result = service.assess_catalog_mock(clip, "b" * 64)

    assert result.profile.value == "mixed"
    assert result.video.source == "catalog_mock"
    assert result.video_annotations == []
    assert result.video.bytes_available is False
    assert all(
        candidate.provenance.location_source == "deterministic_overlay"
        for candidate in result.summary.feces.candidates
    )


def _fake_feces_summary(product_labels: list[str]) -> object:
    candidates = [
        SimpleNamespace(
            classification=SimpleNamespace(product_label=label),
        )
        for label in product_labels
    ]
    return SimpleNamespace(candidates=candidates)


def test_pen_assessment_arithmetic_and_thresholds() -> None:
    from holy_crap_simlab.clip_assessment import DeterministicClipPipeline
    from holy_crap_simlab.models import ClipActivitySummary, SimulationProfile

    def pen(labels: list[str], activity_score: float) -> object:
        activity = ClipActivitySummary(
            score=activity_score, category="typical", motion_coverage=0.5, zone_scores={}
        )
        feces = _fake_feces_summary(labels)
        return DeterministicClipPipeline._pen_assessment(activity, feces, SimulationProfile.MIXED)

    empty = pen([], 0.9)
    assert empty.state == "normal"
    assert empty.score == round(0.0 * 0.65 + (1 - 0.9) * 0.35, 3)
    assert empty.activity_contribution == round(0.1 * 0.35, 3)
    assert empty.feces_contribution == 0.0

    half = pen(["abnormal", "normal"], 0.9)
    assert half.feces_contribution == round(0.5 * 0.65, 3)
    assert half.score == round(0.5 * 0.65 + 0.1 * 0.35, 3)
    assert half.state == "watch"

    review = pen(["abnormal", "abnormal"], 0.2)
    assert review.score == round(1.0 * 0.65 + 0.8 * 0.35, 3)
    assert review.state == "review"


def test_crop_hash_and_proxy_hash_stay_separate(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    content = fake_mp4(b"hash separation")
    result = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4")

    for candidate in result.summary.feces.candidates:
        assert candidate.crop.source_video_sha256 == result.video.sha256
        assert candidate.crop.source_video_sha256 == hashlib.sha256(content).hexdigest()
        assert candidate.proxy_crop is not None
        assert candidate.proxy_crop.sha256 != candidate.crop.source_video_sha256
        assert candidate.proxy_crop.sha256 != result.video.sha256


def test_live_model_output_is_never_rewritten_to_expected_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    import numpy as np
    from PIL import Image

    from holy_crap_simlab.dropping_inference import DroppingOnnxAdapter
    from holy_crap_simlab.proxy_specimens import ProxySpecimenRepository

    manifests_dir = tmp_path / "proxy-specimens"
    manifests_dir.mkdir()
    photo_path = manifests_dir / "cocci.jpg"
    Image.new("RGB", (64, 48), (10, 20, 30)).save(photo_path, "JPEG")
    photo_bytes = photo_path.read_bytes()
    digest = hashlib.sha256(photo_bytes).hexdigest()
    for asset_id, demo_class, filename, sha in (
        ("cocci", "cocci", "cocci.jpg", digest),
        ("healthy", "healthy", "healthy.jpg", "TO_BE_FILLED_BY_ORCHESTRATOR"),
        ("ncd", "ncd", "ncd.jpg", "TO_BE_FILLED_BY_ORCHESTRATOR"),
        ("salmo", "salmo", "salmo.jpg", "TO_BE_FILLED_BY_ORCHESTRATOR"),
    ):
        (manifests_dir / f"{asset_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset_id": asset_id,
                    "filename": filename,
                    "media_type": "image/jpeg",
                    "sha256": sha,
                    "expected_demo_class": demo_class,
                    "description": "test fixture",
                    "source_dataset": "test",
                    "source_url": "https://example.test/",
                    "license": "CC-BY-4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution": "test fixture",
                    "substitution_reason": "test fixture",
                }
            ),
            encoding="utf-8",
        )
    repository = ProxySpecimenRepository(manifests_dir)
    monkeypatch.setattr(
        repository,
        "select_for_candidate",
        lambda *args, **kwargs: repository.get("cocci"),
    )

    class FakeSession:
        def __init__(self) -> None:
            self.runs = 0

        def get_inputs(self):
            return [SimpleNamespace(name="images")]

        def run(self, names, feeds):
            self.runs += 1
            raw = np.zeros((1, 8, 4), dtype=np.float32)
            raw[0, 0:4, 0] = (32, 24, 24, 16)
            raw[0, 4:, :] = 0.05
            raw[0, 5, 0] = 0.87  # healthy column wins
            return [raw]

    fake = FakeSession()
    adapter = DroppingOnnxAdapter(
        model_path=tmp_path / "absent.onnx", session_factory=lambda: fake
    )
    monkeypatch.setattr(adapter, "available", lambda: True)
    service = ClipAssessmentService(
        tmp_path / "simlab", proxy_repository=repository, inference=adapter
    )
    content = fake_mp4(b"live model run")
    result = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4")

    # Every candidate reuses the same verified photo. Its content hash is the
    # inference cache key, so the real model executes exactly once.
    assert fake.runs == 1
    for candidate in result.summary.feces.candidates:
        assert candidate.classification.inference_performed is True
        assert candidate.classification.mode == "real"
        assert candidate.classification.input_sha256 == digest
        assert candidate.crop.source_video_sha256 != digest
        # The model said healthy even though the curated hint says cocci.
        assert candidate.proxy_crop.expected_demo_class == "cocci"
        assert candidate.classification.label == "Healthy"
        assert candidate.classification.product_label == "normal"
        assert candidate.classification.model_detection_bbox is not None


def test_historical_assessment_without_new_fields_still_loads(tmp_path: Path) -> None:
    service = ClipAssessmentService(tmp_path / "simlab")
    content = fake_mp4(b"compat")
    current = service.assess_upload(io.BytesIO(content), "pen.mp4", "video/mp4")
    payload = json.loads(
        service.store.assessments_dir.joinpath(f"{current.id}.json").read_text(encoding="utf-8")
    )
    payload.pop("profile")
    payload.pop("video_annotations")
    payload["summary"].pop("pen_assessment")
    for candidate in payload["summary"]["feces"]["candidates"]:
        candidate.pop("proxy_crop")
        candidate.pop("provenance")
        candidate.pop("lifecycle")
        candidate["crop"]["target_width"] = 224
        candidate["crop"]["target_height"] = 224
        classification = candidate["classification"]
        for key in (
            "product_label",
            "scores",
            "input_sha256",
            "model",
            "inference_performed",
            "model_detection_bbox",
            "fallback_reason",
        ):
            classification.pop(key)
    historical_id = "clip-11111111-2222-3333-4444-555555555555"
    payload["id"] = historical_id
    service.store.assessments_dir.joinpath(f"{historical_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    loaded = service.store.get(historical_id)
    assert loaded is not None
    assert loaded.profile.value == "mixed"
    assert loaded.video_annotations == []
    assert loaded.summary.pen_assessment is None
    assert loaded.summary.feces.candidates[0].crop.target_width == 224
    classification = loaded.summary.feces.candidates[0].classification
    assert classification.product_label == "uncertain"
    assert classification.inference_performed is False
    assert classification.input_sha256 is None
    assert classification.model_detection_bbox is None
    assert classification.fallback_reason is None
    listed = service.store.list()
    assert {assessment.id for assessment in listed} == {current.id, historical_id}
