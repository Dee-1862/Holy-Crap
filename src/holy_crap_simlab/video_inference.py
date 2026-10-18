"""Bounded, CPU-only inference over a selected whole-pen video segment.

Short, low-frame-rate segments are decoded frame-for-frame so annotations track
what is actually on screen. Longer or high-frame-rate segments are sampled on a
uniform, documented budget instead of allowing model work to grow without bound.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageChops

from .dropping_inference import letterbox_rgb
from .models import (
    ClipActivitySummary,
    FecesCandidateLifecycle,
    FecesCropReference,
    NormalizedBoundingBox,
    VideoAnnotation,
)

BEHAVIOURS = ("drinking", "eating", "inactive", "moving", "other", "panting", "preening")
_ENERGY = {"drinking": 0.55, "eating": 0.65, "inactive": 0.05, "moving": 1.0,
           "other": 0.4, "panting": 0.3, "preening": 0.45}


class VideoInferenceUnavailable(RuntimeError):
    """Raised when real frame/model inference cannot safely be completed."""


@dataclass(frozen=True)
class DecodedFrame:
    timestamp_s: float
    image: Image.Image


@dataclass(frozen=True)
class ObservedCandidate:
    id: str
    timestamp_s: float
    bbox: NormalizedBoundingBox
    confidence: float
    crop_reference: FecesCropReference
    crop_image: Image.Image
    crop_sha256: str
    lifecycle: FecesCandidateLifecycle | None = None


@dataclass(frozen=True)
class VideoInferenceResult:
    activity: ClipActivitySummary
    candidates: list[ObservedCandidate]
    frames_sampled: int
    bird_observations: int
    activity_mode: str
    detector_mode: str
    activity_notice: str
    detector_notice: str
    annotations: list[VideoAnnotation] = field(default_factory=list)
    dropping_frames_sampled: int = 0
    source_duration_s: float | None = None
    segment_start_s: float = 0.0
    segment_end_s: float | None = None
    frame_sampling_mode: str = "uniform_bounded_sample"
    source_frames_estimated: int | None = None


@dataclass(frozen=True)
class FramePlan:
    timestamps_s: list[float]
    mode: str
    source_frames_estimated: int
    source_duration_s: float
    segment_start_s: float
    segment_end_s: float


def frame_plan(
    *,
    source_duration_s: float,
    fps: float,
    segment_start_s: float = 0.0,
    segment_end_s: float | None = None,
    max_frames: int = 120,
) -> FramePlan:
    """Choose every source frame when bounded, otherwise a uniform fixed budget."""

    if not math.isfinite(source_duration_s) or source_duration_s <= 0:
        raise VideoInferenceUnavailable("video duration is unavailable")
    if not math.isfinite(fps) or fps <= 0:
        raise VideoInferenceUnavailable("video frame rate is unavailable")
    if not math.isfinite(segment_start_s) or segment_start_s < 0:
        raise VideoInferenceUnavailable("segment start must be a non-negative number")
    end = source_duration_s if segment_end_s is None else segment_end_s
    if not math.isfinite(end) or end <= segment_start_s:
        raise VideoInferenceUnavailable("segment end must be after segment start")
    if segment_start_s >= source_duration_s or end > source_duration_s + 0.05:
        raise VideoInferenceUnavailable("selected segment is outside the source video")
    end = min(end, source_duration_s)
    if max_frames < 2:
        raise ValueError("max_frames must be at least two")

    duration = end - segment_start_s
    estimated = max(1, int(math.ceil(duration * fps - 1e-9)))
    if estimated <= max_frames:
        timestamps = [
            min(end - 1e-6, segment_start_s + index / fps)
            for index in range(estimated)
        ]
        mode = "every_source_frame"
    else:
        # Midpoints avoid over-representing either end of a long segment.
        timestamps = [
            segment_start_s + duration * (index + 0.5) / max_frames
            for index in range(max_frames)
        ]
        mode = "uniform_bounded_sample"
    return FramePlan(
        timestamps_s=timestamps,
        mode=mode,
        source_frames_estimated=estimated,
        source_duration_s=source_duration_s,
        segment_start_s=segment_start_s,
        segment_end_s=end,
    )


class SparseFfmpegDecoder:
    """Decode a dense short segment or a uniform bounded sample with ffmpeg."""

    DEFAULT_MAX_FRAMES = 120

    def __init__(self, runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run):
        self.runner = runner

    def decode(
        self,
        path: Path,
        duration_s: float | None,
        max_frames: int = DEFAULT_MAX_FRAMES,
        *,
        segment_start_s: float = 0.0,
        segment_end_s: float | None = None,
    ) -> list[DecodedFrame]:
        source_duration, fps = self._probe(path, duration_s)
        plan = frame_plan(
            source_duration_s=source_duration,
            fps=fps,
            segment_start_s=segment_start_s,
            segment_end_s=segment_end_s,
            max_frames=max_frames,
        )
        self.last_plan = plan
        frames: list[DecodedFrame] = []
        segment_duration = plan.segment_end_s - plan.segment_start_s
        with tempfile.TemporaryDirectory(prefix="holy-crap-frames-") as temporary:
            output_pattern = str(Path(temporary) / "frame-%06d.png")
            filters = ["scale=1280:-2"]
            if plan.mode == "uniform_bounded_sample":
                filters.append(f"fps={len(plan.timestamps_s) / segment_duration:.12f}")
            command = [
                "ffmpeg", "-v", "error", "-ss", f"{plan.segment_start_s:.6f}",
                "-i", str(path), "-t", f"{segment_duration:.6f}",
                "-vf", ",".join(filters), "-vsync", "0", "-frames:v",
                str(len(plan.timestamps_s)), output_pattern,
            ]
            try:
                completed = self.runner(command, check=False, capture_output=True, timeout=120)
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise VideoInferenceUnavailable("ffmpeg frame decoding is unavailable") from exc
            if completed.returncode != 0:
                raise VideoInferenceUnavailable("ffmpeg could not decode the selected video segment")
            decoded_paths = sorted(Path(temporary).glob("frame-*.png"))
            for index, decoded_path in enumerate(decoded_paths[:len(plan.timestamps_s)]):
                try:
                    with Image.open(decoded_path) as decoded:
                        frames.append(DecodedFrame(plan.timestamps_s[index], decoded.convert("RGB").copy()))
                except (OSError, ValueError):
                    continue
        if len(frames) < 2:
            raise VideoInferenceUnavailable("fewer than two video frames could be decoded")
        return frames

    def _probe(self, path: Path, duration_hint_s: float | None) -> tuple[float, float]:
        command = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate,duration:format=duration",
            "-of", "default=noprint_wrappers=1", str(path),
        ]
        try:
            completed = self.runner(command, check=False, capture_output=True, timeout=15)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise VideoInferenceUnavailable("ffprobe video inspection is unavailable") from exc
        values: dict[str, str] = {}
        for line in completed.stdout.decode("utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values.setdefault(key, value)
        duration = duration_hint_s if duration_hint_s and duration_hint_s > 0 else None
        if duration is None:
            try:
                duration = float(values.get("duration", ""))
            except ValueError:
                duration = None
        rate = values.get("avg_frame_rate", "")
        try:
            numerator, denominator = rate.split("/", 1)
            fps = float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        if duration is None or duration <= 0 or fps <= 0:
            raise VideoInferenceUnavailable("ffprobe did not report a usable duration and frame rate")
        return duration, fps


class OnnxModel:
    def __init__(self, path: Path, *, threads: int = 4, session_factory: Callable[[Path], object] | None = None):
        self.path = path
        self.threads = threads
        self.session_factory = session_factory
        self._session: object | None = None

    def expected_sha256(self) -> str | None:
        sums = self.path.parent / "SHA256SUMS"
        if not sums.is_file():
            return None
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[-1] == self.path.name and re.fullmatch(r"[a-f0-9]{64}", parts[0]):
                return parts[0]
        return None

    def verified(self) -> bool:
        if not self.path.is_file():
            return False
        expected = self.expected_sha256()
        if expected is None:
            return True
        digest = hashlib.sha256()
        with self.path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest() == expected

    def session(self) -> object:
        if self._session is not None:
            return self._session
        if not self.verified():
            raise VideoInferenceUnavailable(f"model artifact is missing or failed checksum: {self.path.name}")
        if self.session_factory:
            self._session = self.session_factory(self.path)
            return self._session
        try:
            import onnxruntime as ort  # noqa: PLC0415
            options = ort.SessionOptions()
            options.intra_op_num_threads = self.threads
            options.inter_op_num_threads = 1
            self._session = ort.InferenceSession(
                str(self.path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise VideoInferenceUnavailable("ONNX Runtime could not load a video model") from exc
        return self._session

    def run(self, tensor: np.ndarray) -> np.ndarray:
        session = self.session()
        try:
            name = session.get_inputs()[0].name  # type: ignore[attr-defined]
            return np.asarray(session.run(None, {name: tensor})[0])  # type: ignore[attr-defined]
        except Exception as exc:
            raise VideoInferenceUnavailable(f"model inference failed: {self.path.name}") from exc


def _tensor(image: Image.Image, size: int) -> tuple[np.ndarray, float, float, int, int]:
    boxed, sx, sy, px, py = letterbox_rgb(image, size, (114, 114, 114))
    array = np.asarray(boxed, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    return array, sx, sy, px, py


def _nms(rows: list[tuple[float, float, float, float, float]], iou_threshold: float = 0.5) -> list[int]:
    if not rows:
        return []
    order = sorted(range(len(rows)), key=lambda index: rows[index][4], reverse=True)
    kept: list[int] = []
    while order:
        current = order.pop(0)
        kept.append(current)
        ax1, ay1, ax2, ay2, _ = rows[current]
        survivors = []
        for index in order:
            bx1, by1, bx2, by2, _ = rows[index]
            intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
            union = max(1e-9, (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - intersection)
            if intersection / union <= iou_threshold:
                survivors.append(index)
        order = survivors
    return kept


def _detector_boxes(model: OnnxModel, image: Image.Image, size: int, score_offset: int,
                    threshold: float) -> list[tuple[float, float, float, float, float]]:
    tensor, sx, sy, px, py = _tensor(image, size)
    raw = model.run(tensor)
    if raw.ndim != 3 or raw.shape[0] != 1 or raw.shape[1] <= score_offset:
        raise VideoInferenceUnavailable(f"unexpected detector output shape: {raw.shape}")
    values = raw[0].T
    scores = values[:, score_offset:].max(axis=1)
    rows: list[tuple[float, float, float, float, float]] = []
    width, height = image.size
    for row, score in zip(values[scores >= threshold], scores[scores >= threshold], strict=False):
        cx, cy, bw, bh = (float(value) for value in row[:4])
        x1 = max(0.0, min(float(width), (cx - bw / 2 - px) / sx))
        y1 = max(0.0, min(float(height), (cy - bh / 2 - py) / sy))
        x2 = max(0.0, min(float(width), (cx + bw / 2 - px) / sx))
        y2 = max(0.0, min(float(height), (cy + bh / 2 - py) / sy))
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            rows.append((x1, y1, x2, y2, float(score)))
    return [rows[index] for index in _nms(rows)]


def _crop_with_margin(image: Image.Image, box: tuple[float, float, float, float, float],
                      *, factor: float, minimum: int) -> Image.Image:
    x1, y1, x2, y2, _ = box
    side = max(minimum, (x2 - x1) * factor, (y2 - y1) * factor)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    left, top = max(0, int(cx - side / 2)), max(0, int(cy - side / 2))
    right, bottom = min(image.width, int(cx + side / 2)), min(image.height, int(cy + side / 2))
    return image.crop((left, top, max(left + 1, right), max(top + 1, bottom))).convert("RGB")


def coverage_starts(length: int, tile: int = 640) -> list[int]:
    """Return a bounded, edge-appended grid that leaves no source pixels uncovered."""

    if length <= tile:
        return [0]
    starts = list(range(0, length - tile + 1, tile))
    edge = length - tile
    if starts[-1] != edge:
        starts.append(edge)
    return starts


def overlapping_starts(length: int, tile: int, overlap: float = 0.25) -> list[int]:
    """Return a full-coverage grid with deterministic overlap at tile seams."""

    if length <= tile:
        return [0]
    stride = max(1, round(tile * (1 - overlap)))
    starts = list(range(0, length - tile + 1, stride))
    edge = length - tile
    if starts[-1] != edge:
        starts.append(edge)
    return starts


def _individual_bird_box(
    box: tuple[float, float, float, float, float], image: Image.Image
) -> bool:
    """Reject regions too large or oddly shaped to truthfully call one bird."""

    width, height = box[2] - box[0], box[3] - box[1]
    if width < 8 or height < 8 or box[4] < 0.25:
        return False
    area_share = width * height / (image.width * image.height)
    aspect = width / height
    return (
        width / image.width <= 0.08
        and height / image.height <= 0.14
        and area_share <= 0.006
        and 0.25 <= aspect <= 3.5
    )


def _whole_frame_bird_box(
    box: tuple[float, float, float, float, float], image: Image.Image
) -> bool:
    """Accept high-confidence full-body boxes in the detector's trained domain."""

    width, height = box[2] - box[0], box[3] - box[1]
    if width < 12 or height < 12 or box[4] < 0.5:
        return False
    area_share = width * height / (image.width * image.height)
    aspect = width / height
    return (
        width / image.width <= 0.2
        and height / image.height <= 0.35
        and area_share <= 0.04
        and 0.25 <= aspect <= 3.5
    )


def _center_inside(
    box: tuple[float, float, float, float, float],
    container: tuple[float, float, float, float, float],
) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return container[0] <= cx <= container[2] and container[1] <= cy <= container[3]


def _remove_group_regions(
    boxes: list[tuple[float, float, float, float, float]],
) -> list[tuple[float, float, float, float, float]]:
    """Drop a large region when two distinct smaller detections explain it."""

    retained: list[tuple[float, float, float, float, float]] = []
    for candidate in boxes:
        area = (candidate[2] - candidate[0]) * (candidate[3] - candidate[1])
        contained: list[tuple[float, float, float, float, float]] = []
        for other in boxes:
            other_area = (other[2] - other[0]) * (other[3] - other[1])
            if other is candidate or other_area >= area * 0.55:
                continue
            cx, cy = (other[0] + other[2]) / 2, (other[1] + other[3]) / 2
            if candidate[0] <= cx <= candidate[2] and candidate[1] <= cy <= candidate[3]:
                contained.append(other)
        distinct = [contained[index] for index in _nms(contained, iou_threshold=0.35)]
        if len(distinct) < 2:
            retained.append(candidate)
    return retained


def _bounded_sample_indices(count: int, budget: int) -> set[int]:
    if count <= budget:
        return set(range(count))
    return {
        min(count - 1, int((index + 0.5) * count / budget))
        for index in range(budget)
    }


def _bird_domain_compatible(
    boxes_by_frame: list[list[tuple[float, float, float, float, float]]],
) -> bool:
    """Require repeatable individual detections before exposing bird boxes."""

    if not boxes_by_frame:
        return False
    frames_with_individuals = sum(len(boxes) >= 3 for boxes in boxes_by_frame)
    return frames_with_individuals / len(boxes_by_frame) >= 0.5


def _center_on_bird(
    box: tuple[float, float, float, float, float],
    birds: list[tuple[float, float, float, float, float]],
) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    for x1, y1, x2, y2, _ in birds:
        inset_x, inset_y = (x2 - x1) * 0.15, (y2 - y1) * 0.15
        if x1 + inset_x <= cx <= x2 - inset_x and y1 + inset_y <= cy <= y2 - inset_y:
            return True
    return False


class WholePenVideoInference:
    ACTIVITY_MODEL_ID = "behaviour-v1/chicken-yolo11n-640+behaviour7-yolo11n-cls-224"
    DROPPING_MODEL_ID = "dropping4-pen/dropping4pen-yolo11n-640"
    MAX_VIDEO_FRAMES = 120
    MAX_BEHAVIOUR_FRAMES = 24
    MAX_BIRDS_PER_FRAME = 128
    MAX_CLASSIFIED_BIRDS_PER_FRAME = 12

    def __init__(self, decoder: SparseFfmpegDecoder | None = None, *, model_root: Path | None = None,
                 session_factory: Callable[[Path], object] | None = None) -> None:
        root = model_root or Path(__file__).resolve().parents[2] / "models"
        behaviour = root / "behaviour-v1"
        dropping = root / "dropping4-pen"
        self.decoder = decoder or SparseFfmpegDecoder()
        self.chickens = OnnxModel(behaviour / "chicken_yolo11n_640.onnx", session_factory=session_factory)
        self.behaviour = OnnxModel(behaviour / "behaviour7_yolo11n-cls_224.onnx", session_factory=session_factory)
        self.droppings = OnnxModel(dropping / "dropping4pen_yolo11n_640.onnx", session_factory=session_factory)

    def analyze(
        self,
        path: Path,
        video_sha256: str,
        duration_s: float | None,
        *,
        segment_start_s: float = 0.0,
        segment_end_s: float | None = None,
        progress: Callable[[int, str, str], None] | None = None,
    ) -> VideoInferenceResult:
        if progress:
            progress(12, "decoding", "Decoding the selected video segment")
        frames = self.decoder.decode(
            path,
            duration_s,
            max_frames=self.MAX_VIDEO_FRAMES,
            segment_start_s=segment_start_s,
            segment_end_s=segment_end_s,
        )
        if progress:
            progress(18, "detecting_chickens", f"Decoded {len(frames)} frames; locating chickens")
        bird_localizations = []
        for frame_index, frame in enumerate(frames):
            bird_localizations.append(self._chicken_localizations(frame.image))
            if progress:
                progress(
                    18 + round(32 * (frame_index + 1) / len(frames)),
                    "detecting_chickens",
                    f"Located chickens in {frame_index + 1} of {len(frames)} frames",
                )
        detected_bird_boxes = [localization[0] for localization in bird_localizations]
        bird_exclusion_masks = [localization[1] for localization in bird_localizations]
        bird_domain_compatible = _bird_domain_compatible(detected_bird_boxes)
        bird_boxes_by_frame = (
            detected_bird_boxes
            if bird_domain_compatible
            else [[] for _ in detected_bird_boxes]
        )
        activity_kwargs = {"bird_boxes_by_frame": bird_boxes_by_frame}
        if progress is not None:
            activity_kwargs["progress"] = progress
        activity, observations, chicken_annotations = self._activity(
            frames, **activity_kwargs
        )
        plan = getattr(self.decoder, "last_plan", None)
        sampling_mode = plan.mode if isinstance(plan, FramePlan) else "decoder_provided_frames"
        source_duration = plan.source_duration_s if isinstance(plan, FramePlan) else duration_s
        actual_start = plan.segment_start_s if isinstance(plan, FramePlan) else segment_start_s
        actual_end = (
            plan.segment_end_s if isinstance(plan, FramePlan)
            else segment_end_s if segment_end_s is not None
            else duration_s
        )
        estimated_frames = plan.source_frames_estimated if isinstance(plan, FramePlan) else None
        dropping_frames = frames
        dropping_kwargs = {
            "active_until_s": actual_end,
            "bird_boxes_by_frame": bird_exclusion_masks,
        }
        if progress is not None:
            dropping_kwargs["progress"] = progress
        candidates, dropping_annotations = self._dropping_candidates(
            dropping_frames,
            video_sha256,
            **dropping_kwargs,
        )
        classified = sum(annotation.label is not None for annotation in chicken_annotations)
        coverage_notice = (
            " The detector did not show repeatable individual-bird coverage in this camera domain, so questionable regions were suppressed and no bird crops were sent to the behavior model. Pen-level motion remains available."
            if not bird_domain_compatible
            else " Low individual-bird coverage means the behavior mix is weak evidence."
            if observations / len(frames) < 5
            else ""
        )
        sampling_notice = (
            "every source frame"
            if sampling_mode == "every_source_frame"
            else f"a uniform cap of {len(frames)} frames"
        )
        return VideoInferenceResult(
            activity=activity,
            candidates=candidates,
            frames_sampled=len(frames),
            bird_observations=observations,
            activity_mode="real" if observations else "partial",
            detector_mode="real",
            activity_notice=(
                f"Decoded {sampling_notice} and localized {observations} individual-sized bird observations; "
                f"classified {classified} bounded crops with {self.ACTIVITY_MODEL_ID}. "
                "Overlapping multi-scale tiles improve small-bird recall. Group-sized regions are rejected before behavior inference. "
                "The score combines frame-to-frame pixel motion with aggregate single-frame behavior evidence; it is not individual tracking."
                + coverage_notice
            ),
            detector_notice=(
                f"Ran {self.DROPPING_MODEL_ID} on {len(frames)} real decoded frames and retained "
                f"{len(candidates)} candidate crop(s). Field accuracy is not established."
            ),
            annotations=[*chicken_annotations, *dropping_annotations],
            dropping_frames_sampled=len(dropping_frames),
            source_duration_s=source_duration,
            segment_start_s=actual_start,
            segment_end_s=actual_end,
            frame_sampling_mode=sampling_mode,
            source_frames_estimated=estimated_frames,
        )

    def _activity(
        self,
        frames: list[DecodedFrame],
        *,
        bird_boxes_by_frame: list[list[tuple[float, float, float, float, float]]] | None = None,
        progress: Callable[[int, str, str], None] | None = None,
    ) -> tuple[ClipActivitySummary, int, list[VideoAnnotation]]:
        counts: Counter[str] = Counter()
        annotations: list[VideoAnnotation] = []
        zone_motion = {key: [] for key in ("northwest", "northeast", "southwest", "southeast")}
        motion_values: list[float] = []
        previous: Image.Image | None = None
        behavior_frame_indices = _bounded_sample_indices(
            len(frames), self.MAX_BEHAVIOUR_FRAMES
        )
        for frame_index, frame in enumerate(frames):
            gray = frame.image.convert("L").resize((320, 180))
            if previous is not None:
                diff = np.asarray(ImageChops.difference(previous, gray), dtype=np.uint8)
                motion_values.append(float(np.mean(diff > 18)))
                for name, area in zip(zone_motion, (diff[:90, :160], diff[:90, 160:], diff[90:, :160], diff[90:, 160:]), strict=True):
                    zone_motion[name].append(float(np.mean(area > 18)))
            previous = gray
            birds = (
                bird_boxes_by_frame[frame_index]
                if bird_boxes_by_frame is not None
                else self._chicken_boxes(frame.image)
            )[:self.MAX_BIRDS_PER_FRAME]
            for bird_index, bird in enumerate(birds):
                label: str | None = None
                label_confidence: float | None = None
                scores: dict[str, float] = {}
                should_classify = (
                    frame_index in behavior_frame_indices
                    and bird_index < self.MAX_CLASSIFIED_BIRDS_PER_FRAME
                )
                if should_classify:
                    crop = _crop_with_margin(frame.image, bird, factor=1.15, minimum=32).resize((224, 224), Image.Resampling.BILINEAR)
                    tensor = np.asarray(crop, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
                    raw = self.behaviour.run(tensor).reshape(-1)
                else:
                    raw = np.asarray([], dtype=np.float32)
                if len(raw) == len(BEHAVIOURS) and np.isfinite(raw).all():
                    probabilities = _probabilities(raw)
                    label_index = int(np.argmax(probabilities))
                    label = BEHAVIOURS[label_index]
                    counts[label] += 1
                    label_confidence = round(float(probabilities[label_index]), 6)
                    scores = {
                        behavior: round(float(probabilities[index]), 6)
                        for index, behavior in enumerate(BEHAVIOURS)
                    }
                _, _, _, _, confidence = bird
                annotations.append(
                    VideoAnnotation(
                        id=f"chicken-s{frame_index:04d}-{bird_index:03d}",
                        kind="chicken",
                        timestamp_s=round(frame.timestamp_s, 3),
                        bbox=_normalized_box(bird, frame.image),
                        detection_confidence=round(min(1.0, confidence), 6),
                        label=label,
                        label_confidence=label_confidence,
                        scores=scores,
                        sample_index=frame_index,
                    )
                )
            if progress:
                progress(
                    50 + round(18 * (frame_index + 1) / len(frames)),
                    "classifying_activity",
                    f"Measured activity in {frame_index + 1} of {len(frames)} frames",
                )
        observations = len(annotations)
        classified_observations = sum(counts.values())
        motion_coverage = float(np.mean(motion_values)) if motion_values else 0.0
        motion_score = min(1.0, motion_coverage / 0.18)
        behaviour_score = (
            sum(counts[key] * _ENERGY[key] for key in BEHAVIOURS)
            / classified_observations
            if classified_observations
            else motion_score
        )
        score = round(0.45 * motion_score + 0.55 * behaviour_score, 3)
        category = "low" if score < 0.4 else "high" if score > 0.72 else "typical"
        distribution = {
            key: round(counts[key] / classified_observations, 3)
            if classified_observations else 0.0
            for key in BEHAVIOURS
        }
        zones = {key: round(min(1.0, (float(np.mean(values)) if values else 0.0) / 0.18), 3) for key, values in zone_motion.items()}
        return ClipActivitySummary(
            score=score,
            category=category,
            motion_coverage=round(min(1.0, motion_coverage), 3),
            zone_scores=zones,
            sampled_frames=len(frames),
            bird_observations=observations,
            behavior_distribution=distribution,
        ), observations, annotations

    def _chicken_boxes(
        self, image: Image.Image
    ) -> list[tuple[float, float, float, float, float]]:
        """Localize individual-sized birds with overlapping multi-scale tiles."""

        return self._chicken_localizations(image)[0]

    def _chicken_localizations(
        self, image: Image.Image
    ) -> tuple[
        list[tuple[float, float, float, float, float]],
        list[tuple[float, float, float, float, float]],
    ]:
        """Return truthful individual boxes plus conservative bird exclusion masks."""

        whole_frame_boxes = _detector_boxes(self.chickens, image, 640, 4, 0.05)
        trusted_whole = [
            box for box in whole_frame_boxes if _whole_frame_bird_box(box, image)
        ]
        tiled_boxes: list[tuple[float, float, float, float, float]] = []
        tile_size = 448
        for y in overlapping_starts(image.height, tile_size):
            for x in overlapping_starts(image.width, tile_size):
                tile = image.crop((x, y, x + tile_size, y + tile_size))
                for x1, y1, x2, y2, confidence in _detector_boxes(
                    self.chickens, tile, 640, 4, 0.05
                ):
                    tiled_boxes.append((x1 + x, y1 + y, x2 + x, y2 + y, confidence))
        raw_tiled_boxes = tiled_boxes
        tiled_boxes = [
            box for box in raw_tiled_boxes
            if _individual_bird_box(box, image)
            and not any(_center_inside(box, whole) for whole in trusted_whole)
        ]
        boxes = _remove_group_regions([*trusted_whole, *tiled_boxes])
        individuals = [boxes[index] for index in _nms(boxes, iou_threshold=0.45)]

        # These masks are deliberately broader than the user-visible boxes.
        # A domain-shifted detector may only recognize a chick cluster, but that
        # region is still useful negative evidence for the much smaller dropping
        # detector. Never classify these masks as individual chickens.
        exclusion_candidates = [
            box for box in [*whole_frame_boxes, *raw_tiled_boxes]
            if box[4] >= 0.1
            and (box[2] - box[0]) / image.width <= 0.3
            and (box[3] - box[1]) / image.height <= 0.45
        ]
        exclusion_masks = [
            exclusion_candidates[index]
            for index in _nms(exclusion_candidates, iou_threshold=0.45)
        ]
        return individuals, exclusion_masks

    def _dropping_candidates(
        self,
        frames: list[DecodedFrame],
        video_sha256: str,
        *,
        active_until_s: float | None = None,
        bird_boxes_by_frame: list[
            list[tuple[float, float, float, float, float]]
        ] | None = None,
        progress: Callable[[int, str, str], None] | None = None,
    ) -> tuple[list[ObservedCandidate], list[VideoAnnotation]]:
        per_frame: list[list[tuple[tuple[float, float, float, float, float], DecodedFrame]]] = []
        for frame_index, frame in enumerate(frames):
            image = frame.image
            boxes: list[tuple[float, float, float, float, float]] = []
            xs = coverage_starts(image.width)
            ys = coverage_starts(image.height)
            for y in ys:
                for x in xs:
                    tile = image.crop((x, y, min(image.width, x + 640), min(image.height, y + 640)))
                    for x1, y1, x2, y2, confidence in _detector_boxes(self.droppings, tile, 640, 4, 0.25):
                        boxes.append((x1 + x, y1 + y, x2 + x, y2 + y, confidence))
            # Model input is normalized to 1280-wide camera scale. The trained
            # target is roughly 8–30 px; 4–48 tolerates imperfect footage while
            # rejecting obvious birds, feeders, and tile-edge artifacts.
            minimum_side = 4.0
            maximum_side = 48.0
            boxes = [
                box for box in boxes
                if minimum_side <= max(box[2] - box[0], box[3] - box[1]) <= maximum_side
            ]
            birds = (
                bird_boxes_by_frame[frame_index]
                if bird_boxes_by_frame is not None
                and frame_index < len(bird_boxes_by_frame)
                else self._chicken_boxes(image)
            )
            boxes = [box for box in boxes if not _center_on_bird(box, birds)]
            boxes = [boxes[index] for index in _nms(boxes)]
            per_frame.append([(box, frame) for box in boxes])
            if progress:
                progress(
                    68 + round(22 * (frame_index + 1) / len(frames)),
                    "detecting_feces",
                    f"Checked feces candidates in {frame_index + 1} of {len(frames)} frames",
                )

        # Droppings are stationary. Associate detections against each cluster's
        # median center, not only its first observation, so small localization
        # jitter does not split one candidate into several identities.
        clusters: list[list[tuple[int, tuple[float, float, float, float, float], DecodedFrame]]] = []
        for frame_index, detections in enumerate(per_frame):
            for box, frame in detections:
                cx = (box[0] + box[2]) / (2 * frame.image.width)
                cy = (box[1] + box[3]) / (2 * frame.image.height)
                eligible: list[tuple[float, list[tuple[int, tuple[float, float, float, float, float], DecodedFrame]]]] = []
                for cluster in clusters:
                    if any(item[0] == frame_index for item in cluster):
                        continue
                    centers = [
                        (
                            (item[1][0] + item[1][2]) / (2 * item[2].image.width),
                            (item[1][1] + item[1][3]) / (2 * item[2].image.height),
                        )
                        for item in cluster
                    ]
                    median_x = float(np.median([center[0] for center in centers]))
                    median_y = float(np.median([center[1] for center in centers]))
                    distance = math.hypot(cx - median_x, cy - median_y)
                    if distance < 0.02:
                        eligible.append((distance, cluster))
                target = min(eligible, key=lambda item: item[0])[1] if eligible else None
                if target is None:
                    clusters.append([(frame_index, box, frame)])
                else:
                    target.append((frame_index, box, frame))

        # A location becomes persistent only after independent recurrence. A
        # one-frame detection remains unconfirmed and never receives a carried
        # overlay.
        persistent = [cluster for cluster in clusters if len(cluster) >= 2]
        persistent.sort(key=lambda cluster: max(item[1][4] for item in cluster), reverse=True)
        found: list[ObservedCandidate] = []
        annotations: list[VideoAnnotation] = []
        for candidate_index, cluster in enumerate(persistent[:12]):
            cluster.sort(key=lambda item: item[2].timestamp_s)
            candidate_id = f"feces-{candidate_index + 1:03d}"
            normalized_observations = [
                _normalized_box(observed_box, observed_frame.image)
                for _, observed_box, observed_frame in cluster
            ]
            canonical_x = float(np.median([box.x for box in normalized_observations]))
            canonical_y = float(np.median([box.y for box in normalized_observations]))
            canonical = NormalizedBoundingBox(
                x=round(canonical_x, 6),
                y=round(canonical_y, 6),
                width=min(
                    round(float(np.median([box.width for box in normalized_observations])), 6),
                    round(1 - canonical_x, 6),
                ),
                height=min(
                    round(float(np.median([box.height for box in normalized_observations])), 6),
                    round(1 - canonical_y, 6),
                ),
            )
            first_observed_s = round(cluster[0][2].timestamp_s, 3)
            confirmed_s = round(cluster[1][2].timestamp_s, 3)
            last_observed_s = round(cluster[-1][2].timestamp_s, 3)
            carry_until_s = round(
                max(last_observed_s, active_until_s if active_until_s is not None else last_observed_s),
                3,
            )
            lifecycle = FecesCandidateLifecycle(
                first_observed_s=first_observed_s,
                confirmed_s=confirmed_s,
                last_observed_s=last_observed_s,
                active_until_s=carry_until_s,
                canonical_bbox=canonical,
                observation_count=len(cluster),
            )
            for observation_index, (sample_index, observed_box, observed_frame) in enumerate(cluster):
                annotations.append(
                    VideoAnnotation(
                        id=(
                            f"{candidate_id}-s{sample_index:02d}-"
                            f"{observation_index:02d}"
                        ),
                        kind="dropping",
                        timestamp_s=round(observed_frame.timestamp_s, 3),
                        bbox=_normalized_box(observed_box, observed_frame.image),
                        detection_confidence=round(
                            min(1.0, observed_box[4]), 6
                        ),
                        candidate_id=candidate_id,
                        sample_index=sample_index,
                    )
                )
            confirmation_sample_index = cluster[1][0]
            annotations.append(
                VideoAnnotation(
                    id=f"{candidate_id}-carried",
                    kind="dropping",
                    timestamp_s=confirmed_s,
                    bbox=canonical,
                    detection_confidence=round(
                        min(1.0, float(np.mean([item[1][4] for item in cluster]))), 6
                    ),
                    candidate_id=candidate_id,
                    sample_index=confirmation_sample_index,
                    observation_state="carried_forward",
                    active_from_s=confirmed_s,
                    active_until_s=carry_until_s,
                )
            )
            _, box, frame = max(cluster, key=lambda item: item[1][4])
            image = frame.image
            x1, y1, x2, y2, confidence = box
            observed_bbox = _normalized_box(box, image)
            crop = _crop_with_margin(image, box, factor=4.0, minimum=96)
            buffer = io.BytesIO()
            crop.save(buffer, format="PNG")
            crop_sha = hashlib.sha256(buffer.getvalue()).hexdigest()
            found.append(ObservedCandidate(
                id=candidate_id, timestamp_s=round(frame.timestamp_s, 3),
                bbox=canonical, confidence=round(min(1.0, confidence), 3),
                crop_reference=FecesCropReference(
                    source_video_sha256=video_sha256, timestamp_s=round(frame.timestamp_s, 3),
                    bbox=observed_bbox, materialized=True,
                ), crop_image=crop, crop_sha256=crop_sha, lifecycle=lifecycle,
            ))
        return found, annotations


def _probabilities(raw: np.ndarray) -> np.ndarray:
    """Normalize classifier output while accepting either logits or probabilities."""

    values = np.asarray(raw, dtype=np.float64)
    total = float(values.sum())
    if np.all(values >= 0) and np.all(values <= 1) and total > 0:
        probabilities = values / total
    else:
        shifted = values - float(values.max())
        exponentials = np.exp(shifted)
        probabilities = exponentials / float(exponentials.sum())
    return probabilities


def _normalized_box(
    box: tuple[float, float, float, float, float], image: Image.Image
) -> NormalizedBoundingBox:
    x1, y1, x2, y2, _ = box
    x = round(x1 / image.width, 6)
    y = round(y1 / image.height, 6)
    return NormalizedBoundingBox(
        x=x,
        y=y,
        width=min(round((x2 - x1) / image.width, 6), round(1 - x, 6)),
        height=min(round((y2 - y1) / image.height, 6), round(1 - y, 6)),
    )
