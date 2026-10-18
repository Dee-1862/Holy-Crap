"""Immutable clip storage and deterministic aggregate assessment adapters.

The adapters in this module are scaffolding. They make the complete handoff
between stages visible without pretending that any model inference occurred.
Every generated value is deterministic from the input video's SHA-256 digest.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO, Literal

from .catalog import atomic_json
from .dropping_inference import (
    CLASS_BY_LABEL,
    LABEL_BY_CLASS,
    DroppingInferenceResult,
    DroppingOnnxAdapter,
)
from .models import (
    ClipActivitySummary,
    ClipAppearanceSummary,
    ClipAssessment,
    ClipFecesSummary,
    ClipModule,
    ClipModuleArtifactSlot,
    ClipOverallSummary,
    ClipPenAssessment,
    ClipSummary,
    ClipVideo,
    DatasetClip,
    FecesCandidate,
    FecesClassification,
    FecesCropReference,
    FecesProvenance,
    NormalizedBoundingBox,
    SimulationProfile,
    utc_now,
)
from .proxy_specimens import ProxySpecimenRepository

DEFAULT_MAX_VIDEO_BYTES = 1024 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
NON_DIAGNOSTIC_NOTICE = (
    "SYNTHETIC MOCK OUTPUT — HYBRID SIMULATION DEMO. Activity, appearance, and whole-pen "
    "candidate detection are deterministic mock data; feces appearance evidence uses curated "
    "proxy specimen photos that did NOT come from this video. This aggregate is for interface "
    "testing only, is not a veterinary diagnosis, and must not drive treatment or culling."
)
DISEASE_LABELS = ("Coccidiosis", "Healthy", "New Castle Disease", "Salmonella")
_PIPELINE_VERSION = "1.1.0"
_PROFILES = {"healthy", "mixed", "concerning"}
_ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
_ALLOWED_MEDIA_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo",
}
_MEDIA_TYPES_BY_SUFFIX = {
    ".mp4": {"video/mp4"},
    ".m4v": {"video/mp4"},
    ".mov": {"video/quicktime"},
    ".webm": {"video/webm"},
    ".mkv": {"video/x-matroska"},
    ".avi": {"video/x-msvideo"},
}
_ASSESSMENT_ID = re.compile(r"^clip-[a-f0-9-]{36}$")


class ClipValidationError(ValueError):
    """Raised when video input is unsafe or outside the clip contract."""


@dataclass(frozen=True)
class VideoProbe:
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    source: Literal["ffprobe", "unavailable"] = "unavailable"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StoredVideo:
    path: Path
    sha256: str
    size_bytes: int


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _frame_rate(value: object) -> float | None:
    if value in (None, "", "0/0"):
        return None
    try:
        parsed = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def probe_video(path: Path, timeout_s: float = 15) -> VideoProbe:
    """Read container metadata through ffprobe without invoking a shell."""

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,r_frame_rate,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        return VideoProbe(warnings=("ffprobe is not installed; technical metadata unavailable",))
    except subprocess.TimeoutExpired:
        return VideoProbe(warnings=("ffprobe timed out; technical metadata unavailable",))
    if completed.returncode != 0:
        return VideoProbe(warnings=("ffprobe could not read this video; technical metadata unavailable",))
    try:
        payload = json.loads(completed.stdout)
        stream = payload.get("streams", [])[0]
        container = payload.get("format", {})
    except (json.JSONDecodeError, IndexError, TypeError, AttributeError):
        return VideoProbe(warnings=("ffprobe returned incomplete metadata",))
    duration = _positive_float(stream.get("duration")) or _positive_float(container.get("duration"))
    fps = _frame_rate(stream.get("avg_frame_rate")) or _frame_rate(stream.get("r_frame_rate"))
    return VideoProbe(
        duration_s=duration,
        width=_positive_int(stream.get("width")),
        height=_positive_int(stream.get("height")),
        fps=fps,
        source="ffprobe",
        warnings=() if duration is not None else ("video duration was not reported by ffprobe",),
    )


def _validate_name_and_type(filename: str, media_type: str) -> str:
    if not filename or len(filename) > 200 or filename != Path(filename).name:
        raise ClipValidationError("video filename must be a plain filename of at most 200 characters")
    if "/" in filename or "\\" in filename or any(ord(character) < 32 for character in filename):
        raise ClipValidationError("video filename contains an unsafe path or control character")
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise ClipValidationError(
            "unsupported video extension; expected mp4, mov, m4v, webm, mkv, or avi"
        )
    normalized_type = media_type.lower().split(";", 1)[0].strip()
    if normalized_type not in _ALLOWED_MEDIA_TYPES:
        raise ClipValidationError("unsupported video content type")
    if normalized_type not in _MEDIA_TYPES_BY_SUFFIX[suffix]:
        raise ClipValidationError("video content type does not match its filename extension")
    return normalized_type


def _header_matches_video(header: bytes, suffix: str) -> bool:
    if suffix in {".mp4", ".mov", ".m4v"}:
        return len(header) >= 12 and header[4:8] == b"ftyp"
    if suffix in {".webm", ".mkv"}:
        return header.startswith(b"\x1aE\xdf\xa3")
    if suffix == ".avi":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    return False


def _max_video_bytes() -> int:
    raw = os.getenv("HOLY_CRAP_MAX_VIDEO_BYTES")
    if raw is None:
        return DEFAULT_MAX_VIDEO_BYTES
    try:
        value = int(raw)
    except ValueError as exc:
        raise ClipValidationError("HOLY_CRAP_MAX_VIDEO_BYTES must be an integer") from exc
    if value <= 0:
        raise ClipValidationError("HOLY_CRAP_MAX_VIDEO_BYTES must be positive")
    return value


class ClipAssessmentStore:
    """Content-addressed video bytes plus append-only assessment envelopes."""

    def __init__(self, home: Path) -> None:
        self.root = Path(home).resolve() / "clips"
        self.blobs_dir = self.root / "blobs"
        self.assessments_dir = self.root / "assessments"
        self.staging_dir = self.root / "staging"
        for directory in (self.blobs_dir, self.assessments_dir, self.staging_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def ingest_stream(
        self,
        stream: BinaryIO,
        *,
        filename: str,
        media_type: str,
        max_bytes: int | None = None,
    ) -> StoredVideo:
        _validate_name_and_type(filename, media_type)
        limit = max_bytes if max_bytes is not None else _max_video_bytes()
        fd, temporary_name = tempfile.mkstemp(prefix="clip-upload-", dir=self.staging_dir)
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        size = 0
        header = b""
        try:
            with os.fdopen(fd, "wb") as handle:
                while chunk := stream.read(READ_CHUNK_BYTES):
                    size += len(chunk)
                    if size > limit:
                        raise ClipValidationError(f"video exceeds the {limit}-byte upload limit")
                    if len(header) < 32:
                        header = (header + chunk)[:32]
                    digest.update(chunk)
                    handle.write(chunk)
                if size == 0:
                    raise ClipValidationError("video upload is empty")
                handle.flush()
                os.fsync(handle.fileno())
            suffix = Path(filename).suffix.lower()
            if not _header_matches_video(header, suffix):
                raise ClipValidationError("file signature does not match a supported video container")
            sha256 = digest.hexdigest()
            destination = self.blob_path(sha256)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                existing_sha, existing_size = self._hash_file(destination)
                if (existing_sha, existing_size) != (sha256, size):
                    raise ClipValidationError("content-addressed video blob is corrupt")
                temporary.unlink()
            else:
                os.replace(temporary, destination)
            return StoredVideo(path=destination, sha256=sha256, size_bytes=size)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def ingest_file(self, path: Path, *, filename: str, media_type: str) -> StoredVideo:
        with path.open("rb") as stream:
            return self.ingest_stream(
                stream,
                filename=filename,
                media_type=media_type,
                max_bytes=max(_max_video_bytes(), path.stat().st_size),
            )

    def blob_path(self, sha256: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise ClipValidationError("invalid video digest")
        return self.blobs_dir / sha256[:2] / sha256

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while chunk := handle.read(READ_CHUNK_BYTES):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def save(self, assessment: ClipAssessment) -> None:
        path = self.assessments_dir / f"{assessment.id}.json"
        if path.exists():
            raise ClipValidationError(f"clip assessment already exists: {assessment.id}")
        atomic_json(path, assessment.model_dump(mode="json"))

    def get(self, assessment_id: str) -> ClipAssessment | None:
        if not _ASSESSMENT_ID.fullmatch(assessment_id):
            return None
        path = self.assessments_dir / f"{assessment_id}.json"
        if not path.is_file():
            return None
        result = ClipAssessment.model_validate_json(path.read_text(encoding="utf-8"))
        return result if result.id == assessment_id else None

    def list(self) -> list[ClipAssessment]:
        results = [
            ClipAssessment.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.assessments_dir.glob("clip-*.json")
        ]
        return sorted(results, key=lambda item: (item.created_at, item.id), reverse=True)

    def content_path(self, assessment: ClipAssessment) -> Path:
        if not assessment.video.bytes_available or assessment.video.content_url is None:
            raise ClipValidationError("this catalog mock has no video bytes or playable content")
        path = self.blob_path(assessment.video.sha256)
        if not path.is_file():
            raise ClipValidationError("stored video bytes are missing")
        actual = self._hash_file(path)
        expected = (assessment.video.sha256, assessment.video.size_bytes)
        if actual != expected:
            raise ClipValidationError("stored video bytes failed integrity verification")
        return path


def _unit(sha256: str, namespace: str) -> float:
    digest = hashlib.sha256(f"{sha256}:{namespace}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)


def _rounded(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 3)


def _validated_profile(profile: str) -> SimulationProfile:
    if profile not in _PROFILES:
        raise ClipValidationError(f"unknown demo profile: {profile!r}; expected healthy, mixed, or concerning")
    return SimulationProfile(profile)


class DeterministicActivityAdapter:
    """Mock clip-average movement adapter; never tracks individual birds."""

    def assess(self, video_sha256: str) -> ClipActivitySummary:
        score = _rounded(0.2 + 0.72 * _unit(video_sha256, "activity"))
        if score < 0.4:
            category = "low"
        elif score > 0.72:
            category = "high"
        else:
            category = "typical"
        return ClipActivitySummary(
            score=score,
            category=category,
            motion_coverage=_rounded(0.5 + 0.48 * _unit(video_sha256, "coverage")),
            zone_scores={
                zone: _rounded(0.15 + 0.8 * _unit(video_sha256, f"zone:{zone}"))
                for zone in ("northwest", "northeast", "southwest", "southeast")
            },
        )


class DeterministicAppearanceAdapter:
    """Mock clip-average visible-appearance adapter."""

    def assess(self, video_sha256: str) -> ClipAppearanceSummary:
        score = _rounded(0.25 + 0.7 * _unit(video_sha256, "appearance"))
        if score < 0.42:
            category = "review"
        elif score < 0.7:
            category = "mixed"
        else:
            category = "typical-looking"
        return ClipAppearanceSummary(
            score=score,
            category=category,
            notes=[
                "Synthetic clip-average appearance score; it is not based on individual birds.",
                "A future adapter may aggregate posture, gait, plumage, and visible-injury evidence.",
            ],
        )


@dataclass(frozen=True)
class DetectedFecesCandidate:
    id: str
    timestamp_s: float
    bbox: NormalizedBoundingBox
    detection_confidence: float
    crop: FecesCropReference


class DeterministicFecesDetectorAdapter:
    """Mock detector that emits the real detector-to-classifier handoff shape."""

    def detect(
        self, video_sha256: str, duration_s: float | None
    ) -> list[DetectedFecesCandidate]:
        candidate_count = 3 + int(_unit(video_sha256, "feces-count") * 8)
        # Mock timestamps need an analysis window even when ffprobe is missing.
        # Five minutes is the product's target clip length, not claimed metadata.
        analysis_window_s = duration_s or 300.0
        candidates: list[DetectedFecesCandidate] = []
        for index in range(candidate_count):
            timestamp = round(analysis_window_s * (index + 1) / (candidate_count + 1), 3)
            width = round(0.025 + 0.055 * _unit(video_sha256, f"feces:{index}:w"), 6)
            height = round(0.025 + 0.055 * _unit(video_sha256, f"feces:{index}:h"), 6)
            bbox = NormalizedBoundingBox(
                x=round((1 - width) * _unit(video_sha256, f"feces:{index}:x"), 6),
                y=round((1 - height) * _unit(video_sha256, f"feces:{index}:y"), 6),
                width=width,
                height=height,
            )
            crop = FecesCropReference(
                source_video_sha256=video_sha256,
                timestamp_s=timestamp,
                bbox=bbox,
            )
            candidates.append(
                DetectedFecesCandidate(
                    id=f"feces-{index + 1:03d}",
                    timestamp_s=timestamp,
                    bbox=bbox,
                    detection_confidence=_rounded(
                        0.55 + 0.4 * _unit(video_sha256, f"feces:{index}:detection")
                    ),
                    crop=crop,
                )
            )
        return candidates


_ABNORMAL_LABELS = ("Coccidiosis", "New Castle Disease", "Salmonella")
def _mock_label(video_sha256: str, profile: str, index: int) -> str:
    unit = _unit(video_sha256, f"feces:{profile}:{index}:label")
    second = _unit(video_sha256, f"feces:{profile}:{index}:label-2")
    abnormal = _ABNORMAL_LABELS[int(second * 3) % 3]
    if profile == "healthy":
        return "Healthy" if unit < 0.75 else abnormal
    if profile == "concerning":
        return "Healthy" if unit < 0.2 else abnormal
    return DISEASE_LABELS[int(unit * 4) % 4]


def _mock_scores(video_sha256: str, profile: str, index: int, label: str) -> dict[str, float]:
    scores = {
        key: _rounded(0.1 + 0.8 * _unit(video_sha256, f"feces:{profile}:{index}:score:{key}"))
        for key in CLASS_BY_LABEL
    }
    label_key = CLASS_BY_LABEL[label]
    boost = _rounded(0.15 + 0.3 * _unit(video_sha256, f"feces:{profile}:{index}:boost"))
    scores[label_key] = _rounded(max(scores.values()) + boost)
    return scores


class DeterministicFecesClassifierAdapter:
    """Classifies proxy specimen photos; live ONNX when available, mock otherwise."""

    def __init__(
        self,
        proxy_repository: ProxySpecimenRepository,
        inference: DroppingOnnxAdapter,
    ) -> None:
        self.proxy_repository = proxy_repository
        self.inference = inference

    def classify(
        self,
        video_sha256: str,
        candidates: list[DetectedFecesCandidate],
        *,
        profile: str,
        location_source: str,
    ) -> ClipFecesSummary:
        distribution = {label: 0 for label in DISEASE_LABELS}
        classified: list[FecesCandidate] = []
        for index, candidate in enumerate(candidates):
            # Accessing crop is intentional: it is the contract a real adapter replaces.
            if candidate.crop.source_video_sha256 != video_sha256:
                raise ClipValidationError("feces crop refers to a different source video")
            manifest = self.proxy_repository.select_for_candidate(
                video_sha256, profile, index, _PIPELINE_VERSION
            )
            reference = self.proxy_repository.reference(manifest)
            classification, classification_source = self._classify_one(
                video_sha256=video_sha256,
                manifest=manifest,
                index=index,
                profile=profile,
            )
            if classification.label is not None:
                distribution[classification.label] += 1
            classified.append(
                FecesCandidate(
                    id=candidate.id,
                    timestamp_s=candidate.timestamp_s,
                    bbox=candidate.bbox,
                    detection_confidence=candidate.detection_confidence,
                    crop=candidate.crop,
                    classification=classification,
                    proxy_crop=reference,
                    provenance=FecesProvenance(
                        location_source=location_source,
                        appearance_input="curated_proxy",
                        classification_source=classification_source,
                    ),
                )
            )
        return ClipFecesSummary(
            candidate_count=len(classified),
            class_distribution=distribution,
            candidates=classified,
        )

    def _classify_one(
        self,
        *,
        video_sha256: str,
        manifest,
        index: int,
        profile: str,
    ) -> tuple[FecesClassification, str]:
        path = self.proxy_repository.verified_path(manifest)
        if path is None:
            return (
                self._mock_classification(
                    video_sha256,
                    profile,
                    index,
                    manifest.sha256,
                    fallback_reason="specimen_unavailable",
                ),
                "deterministic_mock",
            )
        if not self.inference.available():
            return (
                self._mock_classification(
                    video_sha256,
                    profile,
                    index,
                    manifest.sha256,
                    fallback_reason="runtime_unavailable",
                ),
                "deterministic_mock",
            )
        try:
            from PIL import Image  # noqa: PLC0415

            image = Image.open(path)
            image.load()
        except (OSError, ValueError):
            return (
                self._mock_classification(
                    video_sha256,
                    profile,
                    index,
                    manifest.sha256,
                    fallback_reason="image_decode_failed",
                ),
                "deterministic_mock",
            )
        try:
            with image:
                result = self.inference.infer(image, manifest.sha256)
            return (
                self._classification_from_result(manifest, result),
                "live_model_run",
            )
        except Exception:
            # Report a safe category, not exception text that may expose local details.
            return (
                self._mock_classification(
                    video_sha256,
                    profile,
                    index,
                    manifest.sha256,
                    fallback_reason="model_inference_failed",
                ),
                "deterministic_mock",
            )

    def _classification_from_result(
        self, manifest, result: DroppingInferenceResult
    ) -> FecesClassification:
        return FecesClassification(
            label=LABEL_BY_CLASS.get(result.class_name) if result.class_name else None,
            confidence=_rounded(result.score),
            mode="real",
            product_label=result.product_label,
            scores={key: _rounded(value) for key, value in result.scores.items()},
            input_sha256=manifest.sha256,
            model=self.inference.provenance(),
            inference_performed=True,
            model_detection_bbox=result.model_detection_bbox,
        )

    def _mock_classification(
        self,
        video_sha256: str,
        profile: str,
        index: int,
        proxy_sha256: str,
        fallback_reason: Literal[
            "specimen_unavailable",
            "runtime_unavailable",
            "image_decode_failed",
            "model_inference_failed",
        ],
    ) -> FecesClassification:
        label = _mock_label(video_sha256, profile, index)
        input_sha256 = (
            proxy_sha256
            if re.fullmatch(r"[a-f0-9]{64}", proxy_sha256)
            else None
        )
        return FecesClassification(
            label=label,
            confidence=_rounded(0.5 + 0.44 * _unit(video_sha256, f"feces:{profile}:{index}:classification")),
            mode="mock",
            product_label="normal" if label == "Healthy" else "abnormal",
            scores=_mock_scores(video_sha256, profile, index, label),
            input_sha256=input_sha256,
            model=self.inference.provenance(),
            inference_performed=False,
            model_detection_bbox=None,
            fallback_reason=fallback_reason,
        )


class DeterministicClipPipeline:
    id = "deterministic-aggregate-mock"
    version = _PIPELINE_VERSION

    def __init__(
        self,
        proxy_repository: ProxySpecimenRepository,
        inference: DroppingOnnxAdapter,
    ) -> None:
        self.activity = DeterministicActivityAdapter()
        self.appearance = DeterministicAppearanceAdapter()
        self.feces_detector = DeterministicFecesDetectorAdapter()
        self.feces_classifier = DeterministicFecesClassifierAdapter(proxy_repository, inference)
        self.inference = inference

    def modules(self, feces: ClipFecesSummary | None = None) -> list[ClipModule]:
        mock_notice = "Synthetic deterministic adapter; no model artifact was executed."
        classifier_configured = self.inference.available() and any(
            self.feces_classifier.proxy_repository.verified_path(manifest) is not None
            for manifest in self.feces_classifier.proxy_repository.list()
        )
        real_count = 0
        fallback_count = 0
        fallback_reasons: dict[str, int] = {}
        if feces is None:
            classifier_mode = "real" if classifier_configured else "mock"
            execution_coverage = "configured" if classifier_configured else "unavailable"
        else:
            real_count = sum(
                1
                for candidate in feces.candidates
                if candidate.classification.inference_performed
            )
            fallback_count = len(feces.candidates) - real_count
            for candidate in feces.candidates:
                reason = candidate.classification.fallback_reason
                if reason:
                    fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1
            if real_count and fallback_count:
                classifier_mode = "partial"
                execution_coverage = "partial"
            elif real_count:
                classifier_mode = "real"
                execution_coverage = "full"
            else:
                classifier_mode = "mock"
                execution_coverage = "fallback"
        if classifier_mode == "real":
            classifier_notice = (
                "Live YOLO11n ONNX run on curated proxy specimen photos. The proxy photos did "
                "not come from the assessed video."
            )
        elif classifier_mode == "partial":
            categories = ", ".join(
                f"{reason}={count}" for reason, count in sorted(fallback_reasons.items())
            )
            classifier_notice = (
                f"Partial execution: {real_count} candidates completed live ONNX inference and "
                f"{fallback_count} used deterministic fallback ({categories}). Proxy photos did "
                "not come from the assessed video."
            )
        elif classifier_configured:
            categories = ", ".join(
                f"{reason}={count}" for reason, count in sorted(fallback_reasons.items())
            )
            classifier_notice = (
                "The ONNX model and proxy photos are configured, but no candidate completed "
                "real inference; candidate outputs fell back to the deterministic mock"
                + (f" ({categories})." if categories else ".")
            )
        else:
            categories = ", ".join(
                f"{reason}={count}" for reason, count in sorted(fallback_reasons.items())
            )
            classifier_notice = (
                "Synthetic predictions only. The feces appearance module expects an RGB "
                "320x320 image for a YOLO11n detection + appearance-classification model "
                "(no objectness head); no runtime or artifact is currently available, so no "
                "real inference ran"
                + (f" ({categories})." if categories else ".")
            )
        return [
            ClipModule(
                id="pen-activity",
                label="Pen activity / energy",
                mode="mock",
                version="mock-1",
                status="completed",
                adapter="DeterministicActivityAdapter",
                input_contract={"kind": "whole_pen_video", "unit": "one_complete_clip"},
                output_contract={
                    "kind": "clip_activity_aggregate",
                    "fields": ["score", "category", "motion_coverage", "zone_scores"],
                    "individual_tracking": False,
                },
                artifact=ClipModuleArtifactSlot(
                    required_for_real_mode=True,
                    status="not_configured",
                    expected_formats=["tflite", "onnx"],
                ),
                notice=mock_notice,
            ),
            ClipModule(
                id="flock-appearance",
                label="Flock appearance",
                mode="mock",
                version="mock-1",
                status="completed",
                adapter="DeterministicAppearanceAdapter",
                input_contract={"kind": "whole_pen_video", "unit": "sampled_clip_frames"},
                output_contract={
                    "kind": "clip_appearance_aggregate",
                    "individual_tracking": False,
                },
                artifact=ClipModuleArtifactSlot(
                    required_for_real_mode=True,
                    status="not_configured",
                    expected_formats=["tflite", "onnx"],
                ),
                notice=mock_notice,
            ),
            ClipModule(
                id="feces-candidate-detector",
                label="Feces candidate detection",
                mode="mock",
                version="mock-1",
                status="completed",
                adapter="DeterministicFecesDetectorAdapter",
                input_contract={"kind": "whole_pen_video", "unit": "sampled_clip_frames"},
                output_contract={
                    "kind": "feces_candidate_list",
                    "bbox_coordinates": "normalized_xywh",
                    "crop_handoff": "lazy RGB crop reference",
                },
                artifact=ClipModuleArtifactSlot(
                    required_for_real_mode=True,
                    status="not_configured",
                    expected_formats=["tflite", "onnx"],
                ),
                notice=mock_notice,
            ),
            ClipModule(
                id="feces-disease-classifier",
                label="Feces appearance classification",
                mode=classifier_mode,
                version=(
                    self.inference.MODEL_VERSION if classifier_configured else "mock-1"
                ),
                status="completed",
                adapter="DroppingOnnxAdapter",
                input_contract={
                    "kind": "detected_feces_crop_or_curated_proxy",
                    "color_space": "RGB",
                    "width": self.inference.INPUT_SIZE,
                    "height": self.inference.INPUT_SIZE,
                    "upstream": "feces-candidate-detector",
                },
                output_contract={
                    "kind": "detection_with_appearance_classification",
                    "labels": list(DISEASE_LABELS),
                    "bbox_coordinates": "normalized_xywh",
                    "objectness": False,
                    "execution_coverage": execution_coverage,
                    "real_candidate_count": real_count,
                    "fallback_candidate_count": fallback_count,
                    "fallback_reason_counts": fallback_reasons,
                },
                artifact=ClipModuleArtifactSlot(
                    required_for_real_mode=True,
                    status="configured" if classifier_configured else "not_configured",
                    model_id=self.inference.MODEL_ID if classifier_configured else None,
                    expected_formats=["onnx"],
                    compatibility_verified=classifier_configured,
                ),
                notice=classifier_notice,
            ),
        ]

    def assess(
        self,
        *,
        stored: StoredVideo,
        filename: str,
        media_type: str,
        source: Literal["upload", "demo"],
        demo_asset_id: str | None = None,
        probe: VideoProbe | None = None,
        created_at: datetime | None = None,
        profile: str = "mixed",
    ) -> ClipAssessment:
        requested_profile = _validated_profile(profile)
        metadata = probe or probe_video(stored.path)
        assessment_id = f"clip-{uuid.uuid4()}"
        video = ClipVideo(
            name=filename,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            media_type=media_type,
            duration_s=metadata.duration_s,
            width=metadata.width,
            height=metadata.height,
            fps=metadata.fps,
            source=source,
            demo_asset_id=demo_asset_id,
            bytes_available=True,
            content_url=f"/api/v1/clip-assessments/{assessment_id}/content",
            metadata_source=metadata.source,
            metadata_warnings=list(metadata.warnings),
        )
        summary = self._summary(
            stored.sha256,
            metadata.duration_s,
            profile=requested_profile,
            location_source="observed_video",
        )
        return ClipAssessment(
            id=assessment_id,
            status="completed",
            created_at=created_at or utc_now(),
            video=video,
            modules=self.modules(summary.feces),
            summary=summary,
            non_diagnostic_notice=NON_DIAGNOSTIC_NOTICE,
            profile=requested_profile,
        )

    def assess_catalog_mock(
        self,
        *,
        clip: DatasetClip,
        synthetic_sha256: str,
        created_at: datetime | None = None,
        profile: str = "mixed",
    ) -> ClipAssessment:
        """Create UI-only mock output without claiming catalog video bytes were analyzed."""

        requested_profile = _validated_profile(profile)
        if not clip.assessable or clip.media_kind != "video":
            raise ClipValidationError(f"catalog entry is not assessable: {clip.id}")
        assessment_id = f"clip-{uuid.uuid4()}"
        unavailable_notice = (
            "SYNTHETIC MOCK OUTPUT — CATALOG MOCK ONLY. No video bytes were available from the catalog, "
            "decoded, or analyzed, and no vision model ran on catalog video. Activity, appearance, "
            "and candidate locations are deterministic "
            "UI sample data derived from catalog identity metadata. Any live feces appearance "
            "inference runs only on curated proxy photos that did NOT come from the catalog video. "
            "This is not a veterinary diagnosis."
        )
        summary = self._summary(
            synthetic_sha256,
            clip.duration_s,
            profile=requested_profile,
            location_source="deterministic_overlay",
        )
        modules = [
            module.model_copy(
                update={
                    "notice": (
                        f"{module.notice} Candidate locations are deterministic catalog overlays; "
                        "no video bytes from the catalog were analyzed."
                        if module.id == "feces-disease-classifier"
                        else unavailable_notice
                    )
                }
            )
            for module in self.modules(summary.feces)
        ]
        return ClipAssessment(
            id=assessment_id,
            status="completed",
            created_at=created_at or utc_now(),
            video=ClipVideo(
                name=clip.filename or clip.title,
                sha256=synthetic_sha256,
                size_bytes=0,
                media_type=clip.media_type or "video/unknown",
                duration_s=clip.duration_s,
                width=clip.width,
                height=clip.height,
                fps=clip.fps,
                source="catalog_mock",
                demo_asset_id=clip.demo_asset_id,
                catalog_clip_id=clip.id,
                bytes_available=False,
                content_url=None,
                metadata_source="catalog",
                metadata_warnings=[
                    "No video bytes were installed, decoded, or analyzed for this catalog mock.",
                    "Technical fields come from reviewed catalog metadata and may be incomplete.",
                    "Activity, appearance, and candidate locations are deterministic UI sample data; "
                    "feces appearance inference, when available, uses only curated proxy photos.",
                ],
            ),
            modules=modules,
            summary=summary,
            non_diagnostic_notice=unavailable_notice,
            profile=requested_profile,
        )

    def _summary(
        self,
        sha256: str,
        duration_s: float | None,
        *,
        profile: SimulationProfile,
        location_source: str,
    ) -> ClipSummary:
        activity = self.activity.assess(sha256)
        appearance = self.appearance.assess(sha256)
        detected = self.feces_detector.detect(sha256, duration_s)
        feces = self.feces_classifier.classify(
            sha256,
            detected,
            profile=profile.value,
            location_source=location_source,
        )
        live_proxy_runs = sum(
            1 for candidate in feces.candidates if candidate.classification.inference_performed
        )
        classification_note = (
            f"The live feces appearance model ran on {live_proxy_runs} curated proxy photo(s); "
            "those photos did not come from the assessed video."
            if live_proxy_runs
            else (
                "Feces classifications are deterministic mock outputs because verified proxy "
                "bytes or the ONNX runtime were unavailable."
            )
        )
        overall = ClipOverallSummary(
            review_state="synthetic-demo-only",
            notes=[
                "One aggregate result summarizes the entire clip; there is no infection timeline.",
                "No bird identities or per-bird health claims are produced.",
                "Activity, flock appearance, and whole-pen candidate locations are deterministic mock data.",
                classification_note,
            ],
        )
        return ClipSummary(
            activity=activity,
            appearance=appearance,
            feces=feces,
            overall=overall,
            pen_assessment=self._pen_assessment(activity, feces, profile),
        )

    @staticmethod
    def _pen_assessment(
        activity: ClipActivitySummary,
        feces: ClipFecesSummary,
        profile: SimulationProfile,
    ) -> ClipPenAssessment:
        total = len(feces.candidates)
        abnormal = sum(
            1
            for candidate in feces.candidates
            if candidate.classification.product_label == "abnormal"
        )
        abnormal_fraction = abnormal / total if total else 0.0
        feces_contribution = _rounded(abnormal_fraction * 0.65)
        activity_contribution = _rounded((1 - activity.score) * 0.35)
        score = _rounded(abnormal_fraction * 0.65 + (1 - activity.score) * 0.35)
        if score < 0.25:
            state = "normal"
        elif score < 0.55:
            state = "watch"
        else:
            state = "review"
        return ClipPenAssessment(
            state=state,
            score=score,
            policy_id="demo-pen-v1",
            reasons=[
                "Pen activity input is mock: a deterministic synthetic activity score stands in "
                "for measured bird movement and feeds the pen score.",
                "Feces evidence is proxy-assisted: appearance inputs are curated proxy specimen "
                "photos, not crops cut from the assessed video, and the whole-pen detector is "
                "still a mock.",
                f"Requested demo profile {profile.value} deterministically shaped the evidence mix.",
            ],
            activity_contribution=activity_contribution,
            feces_contribution=feces_contribution,
            evidence_mode="hybrid_simulation",
            non_diagnostic=True,
        )


class ClipAssessmentService:
    def __init__(
        self,
        home: Path,
        proxy_repository: ProxySpecimenRepository | None = None,
        inference: DroppingOnnxAdapter | None = None,
    ) -> None:
        self.store = ClipAssessmentStore(home)
        self.proxy_repository = proxy_repository or ProxySpecimenRepository()
        self.inference = inference or DroppingOnnxAdapter()
        self.pipeline = DeterministicClipPipeline(self.proxy_repository, self.inference)

    def assess_upload(
        self,
        stream: BinaryIO,
        filename: str,
        media_type: str,
        profile: str = "mixed",
    ) -> ClipAssessment:
        normalized_type = _validate_name_and_type(filename, media_type)
        stored = self.store.ingest_stream(
            stream, filename=filename, media_type=normalized_type
        )
        result = self.pipeline.assess(
            stored=stored,
            filename=filename,
            media_type=normalized_type,
            source="upload",
            profile=profile,
        )
        self.store.save(result)
        return result

    def assess_demo(
        self,
        *,
        path: Path,
        filename: str,
        media_type: str,
        asset_id: str,
        duration_s: float,
        width: int,
        height: int,
        fps: float,
        profile: str = "mixed",
    ) -> ClipAssessment:
        normalized_type = _validate_name_and_type(filename, media_type)
        stored = self.store.ingest_file(path, filename=filename, media_type=normalized_type)
        result = self.pipeline.assess(
            stored=stored,
            filename=filename,
            media_type=normalized_type,
            source="demo",
            demo_asset_id=asset_id,
            probe=VideoProbe(
                duration_s=duration_s,
                width=width,
                height=height,
                fps=fps,
                source="ffprobe",
            ),
            profile=profile,
        )
        # Demo manifests are already hash-verified and contain reviewed metadata.
        result = result.model_copy(
            update={
                "video": result.video.model_copy(update={"metadata_source": "demo_manifest"})
            }
        )
        self.store.save(result)
        return result

    def assess_catalog_mock(
        self, clip: DatasetClip, synthetic_sha256: str, profile: str = "mixed"
    ) -> ClipAssessment:
        result = self.pipeline.assess_catalog_mock(
            clip=clip,
            synthetic_sha256=synthetic_sha256,
            profile=profile,
        )
        self.store.save(result)
        return result
