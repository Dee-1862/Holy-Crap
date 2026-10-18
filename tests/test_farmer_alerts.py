from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from holy_crap_simlab.farmer_alerts import FarmerAlertNotifier
from holy_crap_simlab.service import SimulationService


def assessments(tmp_path: Path):
    service = SimulationService(tmp_path / "simlab")
    clip = next(item for item in service.list_dataset_clips() if item.assessable)
    digest = service.dataset_clips.synthetic_sha256(clip)
    healthy = service.clip_assessments.assess_catalog_mock(
        clip, digest, profile="healthy"
    )
    concerning = service.clip_assessments.assess_catalog_mock(
        clip, digest, profile="concerning"
    )
    return service, healthy, concerning


def test_notifier_skips_clean_and_watch_results_without_a_request(tmp_path, monkeypatch):
    service, healthy, _ = assessments(tmp_path)
    monkeypatch.setattr(
        "holy_crap_simlab.farmer_alerts.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not call")),
    )
    try:
        assert healthy.summary.pen_assessment.state != "review"
        assert FarmerAlertNotifier().notify(healthy) == "skipped"
    finally:
        service.close()


def test_notifier_maps_concerning_result_to_the_farmer_agent(tmp_path, monkeypatch):
    service, _, concerning = assessments(tmp_path)
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"status":"sent"}'

    def fake_open(request, timeout):
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("holy_crap_simlab.farmer_alerts.urlopen", fake_open)
    try:
        assert concerning.summary.pen_assessment.state == "review"
        assert FarmerAlertNotifier(pen_name="Pen 6", enabled=True).notify(concerning) == "sent"
        payload = captured["payload"]
        abnormal = [
            item for item in concerning.summary.feces.candidates
            if item.classification.product_label == "abnormal" and item.classification.label
        ]
        strongest = max(abnormal, key=lambda item: item.classification.confidence)
        assert payload["eventId"] == concerning.id
        assert payload["penName"] == "Pen 6"
        assert payload["observationCount"] == len(abnormal)
        assert payload["suspectedIllness"] == strongest.classification.label
        assert payload["confidence"] == strongest.classification.confidence
        assert payload["windowMinutes"] == 1
        assert payload["windowSeconds"] > 0
        assert captured["timeout"] == 30.0
    finally:
        service.close()


def test_notifier_saves_a_real_jpeg_frame_when_video_bytes_are_available(tmp_path, monkeypatch):
    service, _, concerning = assessments(tmp_path)
    captured = {}
    video = tmp_path / "source.mp4"
    video.write_bytes(b"video bytes are only read by the injected runner")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"status":"sent"}'

    def fake_open(request, timeout):
        captured["payload"] = json.loads(request.data)
        return Response()

    def fake_runner(command, **_kwargs):
        from PIL import Image

        Image.new("RGB", (100, 100), "white").save(command[-1], format="JPEG")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr("holy_crap_simlab.farmer_alerts.urlopen", fake_open)
    try:
        notifier = FarmerAlertNotifier(
            pen_name="Pen 6",
            enabled=True,
            evidence_dir=tmp_path / "evidence",
            runner=fake_runner,
        )
        assert notifier.notify(concerning, video_path=video) == "sent"
        evidence = captured["payload"]["evidence"]
        assert evidence["contentType"] == "image/jpeg"
        assert evidence["sizeBytes"] > 100
        assert Path(evidence["localPath"]).read_bytes().startswith(b"\xff\xd8\xff")
        assert evidence["sourceLabel"].startswith("Frame from Pen 6 at ")
    finally:
        service.close()


def test_assessment_job_reports_nonfatal_farmer_alert_failure(tmp_path):
    service, _, concerning = assessments(tmp_path)

    class FailedNotifier:
        def notify(self, assessment):
            assert assessment.id == concerning.id
            return "failed"

    service.farmer_alert_notifier = FailedNotifier()
    try:
        job = service._start_assessment_job(lambda _job_id, _progress: concerning)
        for _ in range(200):
            current = service.require_clip_assessment_job(job.id)
            if current.status == "completed":
                break
            time.sleep(0.01)
        assert current.status == "completed"
        assert current.assessment_id == concerning.id
        assert current.message == "Assessment complete; farmer text could not be sent"
    finally:
        service.close()
