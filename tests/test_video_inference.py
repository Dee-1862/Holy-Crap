from __future__ import annotations

import hashlib
from pathlib import Path
from types import MethodType

import numpy as np
from PIL import Image

from holy_crap_simlab.video_inference import (
    BEHAVIOURS,
    DecodedFrame,
    WholePenVideoInference,
    _remove_group_regions,
    coverage_starts,
    frame_plan,
    overlapping_starts,
)


class _Input:
    name = "images"


class _Session:
    def __init__(self, output: np.ndarray) -> None:
        self.output = output

    def get_inputs(self):
        return [_Input()]

    def run(self, _outputs, _inputs):
        return [self.output]


class _Decoder:
    def decode(
        self,
        _path: Path,
        _duration: float | None,
        max_frames: int = 120,
        *,
        segment_start_s: float = 0.0,
        segment_end_s: float | None = None,
    ):
        assert max_frames == 120
        assert segment_start_s == 0.0
        assert segment_end_s is None
        images = []
        for index in range(3):
            image = Image.new("RGB", (1280, 720), (45 + index * 8, 38, 28))
            images.append(DecodedFrame(float(index + 1), image))
        return images


def test_coverage_grid_does_not_skip_center_of_wide_frame() -> None:
    assert coverage_starts(1920) == [0, 640, 1280]
    assert coverage_starts(1280) == [0, 640]
    assert coverage_starts(1000) == [0, 360]
    assert coverage_starts(500) == [0]


def test_short_low_fps_segment_processes_every_source_frame() -> None:
    plan = frame_plan(source_duration_s=19.4, fps=5.0, max_frames=120)

    assert plan.mode == "every_source_frame"
    assert plan.source_frames_estimated == 97
    assert len(plan.timestamps_s) == 97
    assert plan.timestamps_s[:3] == [0.0, 0.2, 0.4]
    assert plan.timestamps_s[-1] == 19.2


def test_long_segment_uses_bounded_uniform_frame_budget() -> None:
    plan = frame_plan(
        source_duration_s=600.0,
        fps=25.0,
        segment_start_s=100.0,
        segment_end_s=400.0,
        max_frames=120,
    )

    assert plan.mode == "uniform_bounded_sample"
    assert plan.source_frames_estimated == 7500
    assert len(plan.timestamps_s) == 120
    assert plan.timestamps_s[0] == 101.25
    assert plan.timestamps_s[-1] == 398.75


def test_overlapping_grid_covers_tile_seams() -> None:
    assert overlapping_starts(1280, 640) == [0, 480, 640]
    assert overlapping_starts(724, 448) == [0, 276]


def test_group_region_is_removed_when_distinct_individuals_explain_it() -> None:
    group = (10.0, 10.0, 210.0, 110.0, 0.9)
    first = (25.0, 25.0, 75.0, 80.0, 0.8)
    second = (125.0, 25.0, 175.0, 80.0, 0.75)

    assert _remove_group_regions([group, first, second]) == [first, second]


def test_activity_keeps_one_hundred_localized_birds_but_bounds_classification() -> None:
    class _BehaviorModel:
        calls = 0

        def run(self, _tensor):
            self.calls += 1
            output = np.zeros((1, len(BEHAVIOURS)), dtype=np.float32)
            output[0, 3] = 1.0
            return output

    pipeline = object.__new__(WholePenVideoInference)
    pipeline.behaviour = _BehaviorModel()
    frames = [
        DecodedFrame(float(index), Image.new("RGB", (1280, 720), (40, 40, 40)))
        for index in range(2)
    ]
    boxes = [
        (float((index % 20) * 60), float((index // 20) * 60),
         float((index % 20) * 60 + 40), float((index // 20) * 60 + 40), 0.8)
        for index in range(100)
    ]

    _, observations, annotations = pipeline._activity(
        frames, bird_boxes_by_frame=[boxes, boxes]
    )

    assert observations == 200
    assert len(annotations) == 200
    assert pipeline.behaviour.calls == 24
    assert sum(annotation.label is not None for annotation in annotations) == 24


def test_incompatible_bird_boxes_are_hidden_but_remain_pooping_exclusion_masks() -> None:
    pipeline = object.__new__(WholePenVideoInference)
    pipeline.decoder = _Decoder()
    questionable = (100.0, 100.0, 220.0, 210.0, 0.3)
    exclusion = (90.0, 90.0, 230.0, 220.0, 0.3)
    received_masks: list[list[tuple[float, float, float, float, float]]] = []

    def localizations(_self, _image):
        # One questionable region per frame fails the repeatability/coverage
        # gate for truthful individual chicken observations.
        return [questionable], [exclusion]

    def dropping(_self, _frames, _sha, *, active_until_s, bird_boxes_by_frame):
        assert active_until_s == 30.0
        received_masks.extend(bird_boxes_by_frame)
        return [], []

    pipeline._chicken_localizations = MethodType(localizations, pipeline)
    pipeline._dropping_candidates = MethodType(dropping, pipeline)

    result = pipeline.analyze(Path("video.mp4"), "a" * 64, 30.0)

    assert result.bird_observations == 0
    assert not [annotation for annotation in result.annotations if annotation.kind == "chicken"]
    assert received_masks == [[exclusion], [exclusion], [exclusion]]
    assert "questionable regions were suppressed" in result.activity_notice


def test_sparse_pipeline_returns_real_behavior_and_persistent_crop(tmp_path: Path) -> None:
    model_root = tmp_path / "models"
    behavior_dir = model_root / "behaviour-v1"
    dropping_dir = model_root / "dropping4-pen"
    behavior_dir.mkdir(parents=True)
    dropping_dir.mkdir(parents=True)
    for path in (
        behavior_dir / "chicken_yolo11n_640.onnx",
        behavior_dir / "behaviour7_yolo11n-cls_224.onnx",
        dropping_dir / "dropping4pen_yolo11n_640.onnx",
    ):
        path.write_bytes(b"fixture")

    chicken = np.zeros((1, 5, 1), dtype=np.float32)
    chicken[0, :, 0] = [500, 300, 100, 100, 0.9]
    behavior = np.zeros((1, len(BEHAVIOURS)), dtype=np.float32)
    behavior[0, 3] = 1.0
    dropping = np.zeros((1, 8, 1), dtype=np.float32)
    dropping[0, :, 0] = [100, 100, 16, 12, 0.8, 0.1, 0.05, 0.05]

    def factory(path: Path):
        if path.name.startswith("chicken"):
            return _Session(chicken)
        if "behaviour7" in path.name:
            return _Session(behavior)
        return _Session(dropping)

    pipeline = WholePenVideoInference(
        decoder=_Decoder(), model_root=model_root, session_factory=factory
    )
    digest = hashlib.sha256(b"video").hexdigest()
    result = pipeline.analyze(tmp_path / "video.mp4", digest, 30.0)

    assert result.activity_mode == "real"
    assert result.frames_sampled == 3
    assert 3 <= result.bird_observations <= 3 * pipeline.MAX_BIRDS_PER_FRAME
    assert result.activity.behavior_distribution["moving"] == 1.0
    assert result.activity.sampled_frames == 3
    chicken_annotations = [
        annotation for annotation in result.annotations if annotation.kind == "chicken"
    ]
    assert len(chicken_annotations) == result.bird_observations
    first_bird = chicken_annotations[0]
    assert first_bird.id == "chicken-s0000-000"
    assert first_bird.sample_index == 0
    assert first_bird.timestamp_s == 1.0
    assert 0 <= first_bird.bbox.x < 1
    assert 0 <= first_bird.bbox.y < 1
    assert first_bird.bbox.x + first_bird.bbox.width <= 1
    assert first_bird.bbox.y + first_bird.bbox.height <= 1
    assert first_bird.detection_confidence == 0.9
    assert first_bird.label == "moving"
    assert first_bird.label_confidence == 1.0
    assert first_bird.scores == {
        "drinking": 0.0,
        "eating": 0.0,
        "inactive": 0.0,
        "moving": 1.0,
        "other": 0.0,
        "panting": 0.0,
        "preening": 0.0,
    }
    assert result.candidates
    assert len(result.candidates) <= 12
    candidate = result.candidates[0]
    assert candidate.crop_reference.materialized is True
    assert candidate.crop_reference.source_video_sha256 == digest
    assert candidate.crop_image.width >= 1
    assert len(candidate.crop_sha256) == 64
    dropping_annotations = [
        annotation for annotation in result.annotations if annotation.kind == "dropping"
    ]
    assert dropping_annotations
    retained_ids = {candidate.id for candidate in result.candidates}
    assert {annotation.candidate_id for annotation in dropping_annotations} == retained_ids
    for candidate_id in retained_ids:
        observations = [
            annotation
            for annotation in dropping_annotations
            if annotation.candidate_id == candidate_id
            and annotation.observation_state == "observed"
        ]
        assert len(observations) >= 2
        assert len({annotation.sample_index for annotation in observations}) >= 2
        carried = [
            annotation
            for annotation in dropping_annotations
            if annotation.candidate_id == candidate_id
            and annotation.observation_state == "carried_forward"
        ]
        assert len(carried) == 1
        lifecycle = next(item for item in result.candidates if item.id == candidate_id).lifecycle
        assert lifecycle is not None
        assert lifecycle.first_observed_s == 1.0
        assert lifecycle.confirmed_s == 2.0
        assert lifecycle.last_observed_s == 3.0
        assert lifecycle.active_until_s == 30.0
        assert lifecycle.observation_count == len(observations)
        assert carried[0].timestamp_s == lifecycle.confirmed_s
        assert carried[0].active_from_s == lifecycle.confirmed_s
        assert carried[0].active_until_s == lifecycle.active_until_s
        assert not any(
            annotation.observation_state == "carried_forward"
            and (annotation.active_from_s or 0) < lifecycle.confirmed_s
            for annotation in dropping_annotations
            if annotation.candidate_id == candidate_id
        )
    assert result.dropping_frames_sampled == 3
