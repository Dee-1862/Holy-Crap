from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from holy_crap_simlab.dataset_library import DatasetClipRepository


def test_committed_catalog_loads_all_reviewed_entries() -> None:
    repository = DatasetClipRepository()
    clips = repository.list()

    assert len(clips) == 9
    assert {clip.id for clip in clips} == {
        "spatiotemporal-whole-pen",
        "big-broiler-090",
        "big-broiler-039",
        "pio-0002",
        "nestler-basic",
        "mvbrotrack-sample-6-camera-3",
        "nestler-annotated-behavior",
        "chickenverse-demo",
        "msu-poultry-piling-images",
    }
    assert repository.get("big-broiler-090").status == "cataloged"
    assert repository.get("nestler-basic").status == "reference_only"
    assert repository.get("nestler-basic").assessable is False
    assert repository.get("chickenverse-demo").status == "rejected"
    assert repository.get("msu-poultry-piling-images").media_kind == "images"
    assert repository.get("msu-poultry-piling-images").assessable is False


def test_committed_entries_match_public_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "contracts" / "dataset-clip.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    for clip in DatasetClipRepository().list():
        validator.validate(clip.model_dump(mode="json"))


def test_dataset_clip_list_and_get_expose_review_and_install_state(client: TestClient) -> None:
    response = client.get("/api/v1/dataset-clips")

    assert response.status_code == 200
    clips = response.json()
    assert len(clips) == 9
    spatiotemporal = next(item for item in clips if item["id"] == "spatiotemporal-whole-pen")
    assert spatiotemporal["status"] == "ready"
    assert spatiotemporal["assessable"] is True
    assert spatiotemporal["bytes_available"] is False
    assert spatiotemporal["content_url"] is None
    assert "complete pens" in spatiotemporal["review_verdict"]
    assert client.get("/api/v1/dataset-clips/big-broiler-090").json()["filename"].startswith(
        "090_"
    )


def test_unknown_dataset_clip_is_structured_404(client: TestClient) -> None:
    response = client.get("/api/v1/dataset-clips/not-a-real-clip")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_catalog_mock_is_deterministic_persisted_and_truthful(client: TestClient) -> None:
    first = client.post("/api/v1/clip-assessments/catalog/big-broiler-090")
    second = client.post("/api/v1/clip-assessments/catalog/big-broiler-090")

    assert first.status_code == second.status_code == 201
    one, two = first.json(), second.json()
    assert one["id"] != two["id"]
    assert one["summary"] == two["summary"]
    assert one["video"]["sha256"] == two["video"]["sha256"]
    assert one["video"]["source"] == "catalog_mock"
    assert one["video"]["catalog_clip_id"] == "big-broiler-090"
    assert one["video"]["bytes_available"] is False
    assert one["video"]["content_url"] is None
    assert one["video"]["size_bytes"] == 0
    assert one["video"]["metadata_source"] == "catalog"
    notice = one["non_diagnostic_notice"].lower()
    assert "no video bytes" in notice
    assert "no vision model ran" in notice
    assert all("no video bytes" in module["notice"].lower() for module in one["modules"])
    assert "bird_id" not in str(one).lower()
    assert "infection timeline" in " ".join(one["summary"]["overall"]["notes"]).lower()

    listed = client.get("/api/v1/clip-assessments").json()
    assert {item["id"] for item in listed} == {one["id"], two["id"]}
    assert client.get(f"/api/v1/clip-assessments/{one['id']}").json() == one
    content = client.get(f"/api/v1/clip-assessments/{one['id']}/content")
    assert content.status_code == 422
    assert content.json()["error"]["code"] == "clip_validation_error"


def test_reference_and_rejected_entries_cannot_be_assessed(client: TestClient) -> None:
    for clip_id in (
        "nestler-basic",
        "nestler-annotated-behavior",
        "chickenverse-demo",
        "msu-poultry-piling-images",
    ):
        response = client.post(f"/api/v1/clip-assessments/catalog/{clip_id}")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "clip_validation_error"
    assert client.get("/api/v1/clip-assessments").json() == []


def test_every_assessable_catalog_mock_conforms_to_clip_contract(client: TestClient) -> None:
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "contracts" / "clip-assessment.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assessable = [clip for clip in client.get("/api/v1/dataset-clips").json() if clip["assessable"]]

    assert assessable
    for clip in assessable:
        response = client.post(f"/api/v1/clip-assessments/catalog/{clip['id']}")
        assert response.status_code == 201, clip["id"]
        validator.validate(response.json())


def test_synthetic_catalog_identity_ignores_runtime_install_state() -> None:
    repository = DatasetClipRepository()
    clip = repository.get("pio-0002")
    assert clip is not None

    installed_view = clip.model_copy(
        update={"bytes_available": True, "content_url": "/api/v1/media/example/content"}
    )
    assert repository.synthetic_sha256(clip) == repository.synthetic_sha256(installed_view)
