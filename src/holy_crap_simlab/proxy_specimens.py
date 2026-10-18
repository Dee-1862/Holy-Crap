"""Indexed, verified proxy photos used in place of video-derived feces crops.

The repository accepts both the original one-JSON-per-photo manifests and
generated catalogs containing thousands of entries. Only metadata is indexed
at startup. Image bytes are never decoded here, and SHA-256 verification is
streamed and cached by file stat signature.

Honesty rules:

* placeholder or missing bytes are never served as verified input;
* generated catalog entries retain their source, license, and attribution;
* deterministic profiles choose verified photos when any are available, but
  may return an unavailable manifest so callers can truthfully use mock output;
* ``expected_demo_class`` steers demo selection only and never overwrites a
  model result; and
* this module never downloads data or makes a network request.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .media import sha256_file
from .models import (
    PROXY_SHA256_PLACEHOLDER,
    ProxySpecimenDatasetCount,
    ProxySpecimenPoolSummary,
    ProxySpecimenReference,
    StrictModel,
)

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SAFE_PATH_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

DemoClass = Literal["cocci", "healthy", "ncd", "salmo", "unknown_abnormal"]
Profile = Literal["healthy", "mixed", "concerning"]


def _validate_relative_filename(filename: str) -> str:
    """Return a normalized POSIX-relative asset path or reject it."""

    if not filename or "\\" in filename:
        raise ValueError(f"filename must be a safe file name or relative path: {filename!r}")
    path = Path(filename)
    if path.is_absolute() or any(
        part in {"", ".", ".."} or not _SAFE_PATH_PART.fullmatch(part)
        for part in path.parts
    ):
        raise ValueError(f"filename must be a safe file name or relative path: {filename!r}")
    return path.as_posix()


class ProxySpecimenManifest(StrictModel):
    """Description of one proxy image, from a legacy manifest or catalog."""

    schema_version: Literal[1] = 1
    asset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    filename: str
    media_type: Literal["image/jpeg", "image/png"] = "image/jpeg"
    sha256: str
    expected_demo_class: DemoClass
    selection_eligible: bool = True
    description: str
    source_dataset: str = Field(min_length=1)
    source_url: HttpUrl
    license: str = Field(min_length=1)
    license_url: HttpUrl | None = None
    attribution: str = Field(min_length=1)
    substitution_reason: str
    # Catalog-only traceability fields. They are retained in the repository,
    # while the stable API reference continues to expose its existing shape.
    original_filename: str | None = None
    source_filename: str | None = None
    label_evidence: str | dict[str, Any] | list[Any] | None = None
    source_sha256: str | None = None

    @model_validator(mode="after")
    def _safe_and_truthful(self) -> ProxySpecimenManifest:
        self.filename = _validate_relative_filename(self.filename)
        if self.sha256 != PROXY_SHA256_PLACEHOLDER and not _SHA256.fullmatch(self.sha256):
            raise ValueError(
                "sha256 must be a 64-character hex digest or the placeholder "
                f"{PROXY_SHA256_PLACEHOLDER!r}"
            )
        if self.source_sha256 is not None and not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be a 64-character lowercase hex digest")
        return self

    @property
    def bytes_expected(self) -> bool:
        return self.sha256 != PROXY_SHA256_PLACEHOLDER


class ProxySpecimenDataset(BaseModel):
    """Provenance defaults shared by all entries in a generated catalog."""

    model_config = ConfigDict(extra="ignore")

    source_dataset: str = Field(min_length=1)
    source_url: HttpUrl
    license: str = Field(min_length=1)
    license_url: HttpUrl | None = None
    attribution: str = Field(min_length=1)
    acquisition_method: str | None = None
    redistribution_status: str | None = None


class ProxySpecimenCatalogEntry(BaseModel):
    """Catalog row before dataset-level provenance defaults are applied."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[1] = 1
    asset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    filename: str
    media_type: Literal["image/jpeg", "image/png"] = "image/jpeg"
    sha256: str
    expected_demo_class: DemoClass
    selection_eligible: bool = True
    description: str
    substitution_reason: str
    source_dataset: str | None = None
    source_url: HttpUrl | None = None
    license: str | None = None
    license_url: HttpUrl | None = None
    attribution: str | None = None
    original_filename: str | None = None
    source_filename: str | None = None
    label_evidence: str | dict[str, Any] | list[Any] | None = None
    source_sha256: str | None = None

    @model_validator(mode="after")
    def _safe_fields(self) -> ProxySpecimenCatalogEntry:
        self.filename = _validate_relative_filename(self.filename)
        if self.sha256 != PROXY_SHA256_PLACEHOLDER and not _SHA256.fullmatch(self.sha256):
            raise ValueError("catalog specimen sha256 must be lowercase hexadecimal")
        if self.source_sha256 is not None and not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be lowercase hexadecimal")
        return self

    def materialize(self, dataset: ProxySpecimenDataset | None) -> ProxySpecimenManifest:
        values = self.model_dump(mode="python")
        if dataset is not None:
            defaults = dataset.model_dump(
                mode="python",
                include={"source_dataset", "source_url", "license", "license_url", "attribution"},
            )
            for key, value in defaults.items():
                if values.get(key) is None:
                    values[key] = value
        missing = [
            key
            for key in ("source_dataset", "source_url", "license", "attribution")
            if values.get(key) is None
        ]
        if missing:
            raise ValueError(
                f"catalog specimen {self.asset_id!r} lacks provenance fields: "
                + ", ".join(missing)
            )
        return ProxySpecimenManifest.model_validate(values)


class ProxySpecimenCatalog(BaseModel):
    """Generated, compact index for a large specimen collection."""

    model_config = ConfigDict(extra="ignore")

    schema_version: Literal[1] = 1
    catalog_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    dataset: ProxySpecimenDataset | None = None
    specimens: list[ProxySpecimenCatalogEntry] = Field(min_length=1)


class ProxySpecimenRepository:
    """Index manifests and lazily verify image bytes before selection/serving."""

    def __init__(self, directory: Path | None = None) -> None:
        configured = os.getenv("HOLY_CRAP_PROXY_SPECIMENS_DIR")
        self.directory = (
            Path(configured) if configured else directory or self.default_directory()
        ).resolve()
        self._base_dirs: dict[str, Path] = {}
        self._verification_cache: dict[
            str, tuple[tuple[int, int, int] | None, Path | None]
        ] = {}
        self._specimens = self._load()
        self._class_index: dict[DemoClass, tuple[ProxySpecimenManifest, ...]] = {
            demo_class: tuple(
                sorted(
                    (
                        item
                        for item in self._specimens.values()
                        if item.expected_demo_class == demo_class
                    ),
                    key=lambda item: item.asset_id,
                )
            )
            for demo_class in ("cocci", "healthy", "ncd", "salmo", "unknown_abnormal")
        }
        self._selection_index: dict[DemoClass, tuple[ProxySpecimenManifest, ...]] = {
            demo_class: tuple(
                item
                for item in self._class_index[demo_class]
                if item.selection_eligible
            )
            for demo_class in ("cocci", "healthy", "ncd", "salmo", "unknown_abnormal")
        }

    @staticmethod
    def default_directory() -> Path:
        return Path(__file__).resolve().parents[2] / "proxy-specimens"

    def _add(
        self,
        specimens: dict[str, ProxySpecimenManifest],
        manifest: ProxySpecimenManifest,
        base_dir: Path,
    ) -> None:
        if manifest.asset_id in specimens:
            raise ValueError(f"duplicate proxy specimen id: {manifest.asset_id}")
        specimens[manifest.asset_id] = manifest
        self._base_dirs[manifest.asset_id] = base_dir.resolve()

    def _load(self) -> dict[str, ProxySpecimenManifest]:
        specimens: dict[str, ProxySpecimenManifest] = {}
        for path in sorted(self.directory.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid proxy specimen JSON: {path}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"proxy specimen JSON must be an object: {path}")
            if "specimens" in payload:
                catalog = ProxySpecimenCatalog.model_validate(payload)
                for entry in catalog.specimens:
                    self._add(specimens, entry.materialize(catalog.dataset), path.parent)
            else:
                self._add(
                    specimens,
                    ProxySpecimenManifest.model_validate(payload),
                    path.parent,
                )
        if not specimens:
            raise ValueError(f"no proxy specimen manifests found in {self.directory}")
        return specimens

    def list(self) -> list[ProxySpecimenManifest]:
        return sorted(self._specimens.values(), key=lambda item: item.asset_id)

    def get(self, asset_id: str) -> ProxySpecimenManifest | None:
        if not _SAFE_ID.fullmatch(asset_id):
            return None
        return self._specimens.get(asset_id)

    def _content_path(self, manifest: ProxySpecimenManifest) -> Path:
        base = self._base_dirs[manifest.asset_id]
        candidate = (base / manifest.filename).resolve()
        if candidate != base and base not in candidate.parents:
            raise ValueError(f"content path escapes its catalog directory: {manifest.filename!r}")
        return candidate

    @staticmethod
    def _stat_signature(path: Path) -> tuple[int, int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_size, stat.st_mtime_ns, stat.st_ino)

    def verified_path(self, manifest: ProxySpecimenManifest) -> Path | None:
        """Return verified bytes, streaming SHA-256 only when file state changes."""

        if not manifest.bytes_expected:
            return None
        path = self._content_path(manifest)
        signature = self._stat_signature(path)
        cached = self._verification_cache.get(manifest.asset_id)
        if cached is not None and cached[0] == signature:
            return cached[1]
        verified: Path | None = None
        if signature is not None and path.is_file():
            try:
                digest = sha256_file(path)
            except OSError:
                digest = ""
            # Re-stat after hashing so an in-flight mutation is never accepted.
            if digest == manifest.sha256 and self._stat_signature(path) == signature:
                verified = path
        self._verification_cache[manifest.asset_id] = (signature, verified)
        return verified

    def reference(self, manifest: ProxySpecimenManifest) -> ProxySpecimenReference:
        bytes_available = self.verified_path(manifest) is not None
        return ProxySpecimenReference(
            asset_id=manifest.asset_id,
            sha256=manifest.sha256,
            content_url=(
                f"/api/v1/proxy-specimens/{manifest.asset_id}/content"
                if bytes_available
                else None
            ),
            bytes_available=bytes_available,
            source_dataset=manifest.source_dataset,
            source_url=str(manifest.source_url),
            license=manifest.license,
            attribution=manifest.attribution,
            expected_demo_class=manifest.expected_demo_class,
            mapping_method="sha256-seeded",
            substitution_reason=manifest.substitution_reason,
        )

    def summary(self) -> ProxySpecimenPoolSummary:
        """Return pool counts using metadata/stat only, never image contents."""

        expected_classes = ("cocci", "healthy", "ncd", "salmo", "unknown_abnormal")
        by_expected_class = {
            demo_class: len(self._class_index[demo_class]) for demo_class in expected_classes
        }
        selectable_by_expected_class = {
            demo_class: len(self._selection_index[demo_class])
            for demo_class in expected_classes
        }
        dataset_counts: dict[str, int] = {}
        bytes_present = 0
        verified_cached = 0
        for manifest in self._specimens.values():
            dataset_counts[manifest.source_dataset] = (
                dataset_counts.get(manifest.source_dataset, 0) + 1
            )
            path = self._content_path(manifest)
            signature = self._stat_signature(path)
            if signature is not None and path.is_file():
                bytes_present += 1
            cached = self._verification_cache.get(manifest.asset_id)
            if (
                cached is not None
                and cached[1] is not None
                and cached[0] == signature
            ):
                verified_cached += 1
        return ProxySpecimenPoolSummary(
            total=len(self._specimens),
            selectable_total=sum(selectable_by_expected_class.values()),
            bytes_present=bytes_present,
            verified_cached=verified_cached,
            by_expected_class=by_expected_class,
            selectable_by_expected_class=selectable_by_expected_class,
            by_dataset=[
                ProxySpecimenDatasetCount(dataset=dataset, count=count)
                for dataset, count in sorted(dataset_counts.items())
            ],
            catalogs_supported=True,
        )

    def _declared_pool(
        self, group: Literal["healthy", "abnormal"]
    ) -> tuple[ProxySpecimenManifest, ...]:
        if group == "healthy":
            return self._selection_index["healthy"]
        return tuple(
            sorted(
                (
                    *self._selection_index["cocci"],
                    *self._selection_index["ncd"],
                    *self._selection_index["salmo"],
                    *self._selection_index["unknown_abnormal"],
                ),
                key=lambda item: item.asset_id,
            )
        )

    def _pool(
        self, group: Literal["healthy", "abnormal"]
    ) -> tuple[ProxySpecimenManifest, ...]:
        """Return the metadata-only class index without hashing image bytes."""

        return self._declared_pool(group)

    def _select_verified_or_declared(
        self,
        pool: tuple[ProxySpecimenManifest, ...],
        start: int,
    ) -> ProxySpecimenManifest:
        """Probe deterministically from ``start`` and hash only until one verifies."""

        for offset in range(len(pool)):
            manifest = pool[(start + offset) % len(pool)]
            if self.verified_path(manifest) is not None:
                return manifest
        # Catalog metadata may be installed before its images. Returning the
        # selected declaration lets the caller expose provenance while falling
        # back with inference_performed=false instead of inventing a model run.
        return pool[start]

    def select_for_candidate(
        self,
        video_sha256: str,
        profile: Profile,
        candidate_index: int,
        pipeline_version: str,
    ) -> ProxySpecimenManifest:
        """Choose a photo deterministically from all verified eligible entries."""

        healthy_pool = self._pool("healthy")
        abnormal_pool = self._pool("abnormal")
        if not healthy_pool or not abnormal_pool:
            raise ValueError(
                "proxy specimen selection needs at least one healthy and one abnormal specimen"
            )
        key = hashlib.sha256(
            f"{video_sha256}:{profile}:{candidate_index}:{pipeline_version}".encode("utf-8")
        ).digest()
        group_unit = int.from_bytes(key[:8], "big") / ((1 << 64) - 1)
        selection_unit = int.from_bytes(key[8:16], "big") / ((1 << 64) - 1)
        if profile == "healthy":
            pool = healthy_pool
        elif profile == "concerning":
            pool = abnormal_pool if group_unit >= 0.2 else healthy_pool
        else:
            pool = healthy_pool if candidate_index % 2 == 0 else abnormal_pool
        start = int(selection_unit * len(pool)) % len(pool)
        return self._select_verified_or_declared(pool, start)
