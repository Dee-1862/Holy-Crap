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
from .models import (
    ClipActivitySummary,
    ClipAppearanceSummary,
    ClipAssessment,
    ClipFecesSummary,
    ClipModule,
    ClipModuleArtifactSlot,
    ClipOverallSummary,
    ClipSummary,
    ClipVideo,
    DatasetClip,
    FecesCandidate,
    FecesClassification,
    FecesCropReference,
    NormalizedBoundingBox,
    utc_now,
)

DEFAULT_MAX_VIDEO_BYTES = 1024 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
NON_DIAGNOSTIC_NOTICE = (
    "SYNTHETIC MOCK OUTPUT — no real vision model ran. This aggregate is for interface "
    "testing only, is not a veterinary diagnosis, and must not drive treatment or culling."
)
DISEASE_LABELS = ("Coccidiosis", "Healthy", "New Castle Disease", "Salmonella")
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


class DeterministicFecesClassifierAdapter:
    """Mock classifier that explicitly consumes detector crop references."""

    def classify(
        self, video_sha256: str, candidates: list[DetectedFecesCandidate]
    ) -> ClipFecesSummary:
        distribution = {label: 0 for label in DISEASE_LABELS}
        classified: list[FecesCandidate] = []
        for index, candidate in enumerate(candidates):
            # Accessing crop is intentional: it is the contract a real adapter replaces.
            if candidate.crop.source_video_sha256 != video_sha256:
                raise ClipValidationError("feces crop refers to a different source video")
            label = DISEASE_LABELS[
                int(_unit(video_sha256, f"feces:{index}:label") * 4) % 4
            ]
            distribution[label] += 1
            classified.append(
                FecesCandidate(
                    id=candidate.id,
                    timestamp_s=candidate.timestamp_s,
                    bbox=candidate.bbox,
                    detection_confidence=candidate.detection_confidence,
                    crop=candidate.crop,
                    classification=FecesClassification(
                        label=label,
                        confidence=_rounded(
                            0.5
                            + 0.44
                            * _unit(video_sha256, f"feces:{index}:classification")
                        ),
                        mode="mock",
                    ),
                )
            )
        return ClipFecesSummary(
            candidate_count=len(classified),
            class_distribution=distribution,
            candidates=classified,
        )


class DeterministicClipPipeline:
    id = "deterministic-aggregate-mock"
    version = "1.0.0"

    def __init__(self) -> None:
        self.activity = DeterministicActivityAdapter()
        self.appearance = DeterministicAppearanceAdapter()
        self.feces_detector = DeterministicFecesDetectorAdapter()
        self.feces_classifier = DeterministicFecesClassifierAdapter()

    def modules(self) -> list[ClipModule]:
        mock_notice = "Synthetic deterministic adapter; no model artifact was executed."
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
                label="Feces disease classification",
                mode="mock",
                version="mock-1",
                status="completed",
                adapter="DeterministicFecesClassifierAdapter",
                input_contract={
                    "kind": "detected_feces_crop",
                    "color_space": "RGB",
                    "width": 224,
                    "height": 224,
                    "upstream": "feces-candidate-detector",
                },
                output_contract={
                    "kind": "single_label_classification",
                    "labels": list(DISEASE_LABELS),
                },
                artifact=ClipModuleArtifactSlot(
                    required_for_real_mode=True,
                    status="not_configured",
                    expected_formats=["tflite", "onnx"],
                    compatibility_verified=False,
                ),
                notice=(
                    "Synthetic predictions only. The future Kaggle-derived classifier slot expects "
                    "an RGB 224x224 detected-feces crop; no artifact is configured, compatibility "
                    "has not been verified, and no real inference ran."
                ),
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
    ) -> ClipAssessment:
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
        summary = self._summary(stored.sha256, metadata.duration_s)
        return ClipAssessment(
            id=assessment_id,
            status="completed",
            created_at=created_at or utc_now(),
            video=video,
            modules=self.modules(),
            summary=summary,
            non_diagnostic_notice=NON_DIAGNOSTIC_NOTICE,
        )

    def assess_catalog_mock(
        self,
        *,
        clip: DatasetClip,
        synthetic_sha256: str,
        created_at: datetime | None = None,
    ) -> ClipAssessment:
        """Create UI-only mock output without claiming catalog video bytes were analyzed."""

        if not clip.assessable or clip.media_kind != "video":
            raise ClipValidationError(f"catalog entry is not assessable: {clip.id}")
        assessment_id = f"clip-{uuid.uuid4()}"
        unavailable_notice = (
            "SYNTHETIC MOCK OUTPUT — CATALOG MOCK ONLY. No video bytes were available, decoded, "
            "or analyzed, and no "
            "vision model ran. Values are deterministic UI sample data derived from catalog "
            "identity metadata, not from footage, and are not a veterinary diagnosis."
        )
        modules = [
            module.model_copy(update={"notice": unavailable_notice}) for module in self.modules()
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
                    "No model ran; all scores and candidates are deterministic UI sample data.",
                ],
            ),
            modules=modules,
            summary=self._summary(synthetic_sha256, clip.duration_s),
            non_diagnostic_notice=unavailable_notice,
        )

    def _summary(self, sha256: str, duration_s: float | None) -> ClipSummary:
        activity = self.activity.assess(sha256)
        appearance = self.appearance.assess(sha256)
        detected = self.feces_detector.detect(sha256, duration_s)
        feces = self.feces_classifier.classify(sha256, detected)
        overall = ClipOverallSummary(
            review_state="synthetic-demo-only",
            notes=[
                "One aggregate result summarizes the entire clip; there is no infection timeline.",
                "No bird identities or per-bird health claims are produced.",
                "All activity, appearance, detection, and classification values are deterministic mock data.",
            ],
        )
        return ClipSummary(activity=activity, appearance=appearance, feces=feces, overall=overall)


class ClipAssessmentService:
    def __init__(self, home: Path) -> None:
        self.store = ClipAssessmentStore(home)
        self.pipeline = DeterministicClipPipeline()

    def assess_upload(self, stream: BinaryIO, filename: str, media_type: str) -> ClipAssessment:
        normalized_type = _validate_name_and_type(filename, media_type)
        stored = self.store.ingest_stream(
            stream, filename=filename, media_type=normalized_type
        )
        result = self.pipeline.assess(
            stored=stored,
            filename=filename,
            media_type=normalized_type,
            source="upload",
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
        self, clip: DatasetClip, synthetic_sha256: str
    ) -> ClipAssessment:
        result = self.pipeline.assess_catalog_mock(
            clip=clip,
            synthetic_sha256=synthetic_sha256,
        )
        self.store.save(result)
        return result
