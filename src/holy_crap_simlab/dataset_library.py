"""Committed, human-reviewed dataset and clip catalog."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .models import DatasetClip, StrictModel


class DatasetClipCatalog(StrictModel):
    schema_version: Literal[1] = 1
    clips: list[DatasetClip] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_and_consistent(self) -> DatasetClipCatalog:
        ids = [clip.id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset clip ids must be unique")
        for clip in self.clips:
            expected_assessable = clip.status in {"ready", "cataloged"} and clip.media_kind == "video"
            if clip.assessable != expected_assessable:
                raise ValueError(
                    f"dataset clip {clip.id!r} has inconsistent status/media_kind/assessable"
                )
            if clip.byte_range_start is not None or clip.byte_range_end is not None:
                if clip.byte_range_start is None or clip.byte_range_end is None:
                    raise ValueError(f"dataset clip {clip.id!r} has an incomplete byte range")
                if clip.byte_range_end < clip.byte_range_start:
                    raise ValueError(f"dataset clip {clip.id!r} has an invalid byte range")
                expected = clip.byte_range_end - clip.byte_range_start + 1
                if clip.expected_size_bytes != expected:
                    raise ValueError(f"dataset clip {clip.id!r} byte range size does not match")
        return self


class DatasetClipRepository:
    """Loads reviewed entries and provides a stable identity for catalog-only mocks."""

    def __init__(self, directory: Path | None = None) -> None:
        configured = os.getenv("HOLY_CRAP_DATASET_CLIPS_DIR")
        self.directory = Path(configured) if configured else directory or self.default_directory()
        path = self.directory / "reviewed.json"
        if not path.is_file():
            raise ValueError(f"dataset clip catalog not found: {path}")
        catalog = DatasetClipCatalog.model_validate_json(path.read_text(encoding="utf-8"))
        self._clips = {clip.id: clip for clip in catalog.clips}

    @staticmethod
    def default_directory() -> Path:
        return Path(__file__).resolve().parents[2] / "dataset-clips"

    def list(self) -> list[DatasetClip]:
        return list(self._clips.values())

    def get(self, clip_id: str) -> DatasetClip | None:
        return self._clips.get(clip_id)

    @staticmethod
    def synthetic_sha256(clip: DatasetClip) -> str:
        """Hash reviewed identity/metadata, never pretending to hash unavailable bytes."""

        payload = clip.model_dump(
            mode="json",
            exclude={"bytes_available", "content_url"},
        )
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"catalog-mock-v1:{canonical}".encode("utf-8")).hexdigest()
