"""Committed reference-media manifests, install state, and safe content paths.

This module never makes network calls. It reads the committed manifests under
``demo-assets/`` and verifies bytes already present under the runtime home
(``HOLY_CRAP_HOME``, default ``.simlab``). Downloading is delegated to
``scripts/fetch_demo_assets.py``; nothing here auto-downloads at import time.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, computed_field, model_validator

from .catalog import safe_part
from .models import StrictModel

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_REQUIRED_LIMITATIONS = (
    "reference imagery only",
    "no disease labels",
    "not spatially aligned with simulated birds",
)


class DemoAssetManifest(StrictModel):
    """Committed description of a downloadable reference-media asset."""

    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str
    description: str
    source_url: HttpUrl
    dataset_url: HttpUrl
    doi: str
    creators: list[str] = Field(min_length=1)
    license: Literal["CC-BY-4.0"]
    license_url: HttpUrl
    attribution: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    filename: str
    limitations: list[str]

    @model_validator(mode="after")
    def _check_filename_and_limitations(self) -> DemoAssetManifest:
        if not _SAFE_FILENAME.fullmatch(self.filename):
            raise ValueError(f"filename must be a plain safe file name: {self.filename!r}")
        missing = [item for item in _REQUIRED_LIMITATIONS if item not in self.limitations]
        if missing:
            raise ValueError("limitations must include: " + ", ".join(missing))
        return self


class InstalledAsset(StrictModel):
    """Install-state snapshot for one asset under the runtime home."""

    manifest: DemoAssetManifest
    path: Path
    installed: bool
    size_bytes: int = Field(ge=0)
    sha256_ok: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def valid(self) -> bool:
        """True when the file exists and its bytes match the manifest digest."""
        return self.installed and self.sha256_ok


class DemoAssetRepository:
    """Loads and validates the committed demo-asset manifests."""

    def __init__(self, directory: Path | None = None) -> None:
        configured = os.getenv("HOLY_CRAP_DEMO_ASSETS_DIR")
        self.directory = Path(configured) if configured else directory or self.default_directory()
        self._assets = self._load()

    @staticmethod
    def default_directory() -> Path:
        return Path(__file__).resolve().parents[2] / "demo-assets"

    def _load(self) -> dict[str, DemoAssetManifest]:
        assets: dict[str, DemoAssetManifest] = {}
        for path in sorted(self.directory.glob("*.json")):
            manifest = DemoAssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
            if manifest.id in assets:
                raise ValueError(f"duplicate demo asset id: {manifest.id}")
            assets[manifest.id] = manifest
        if not assets:
            raise ValueError(f"no demo asset manifests found in {self.directory}")
        return assets

    def list(self) -> list[DemoAssetManifest]:
        return sorted(self._assets.values(), key=lambda item: item.id)

    def get(self, asset_id: str) -> DemoAssetManifest | None:
        return self._assets.get(asset_id)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class UnsafeContentPath(ValueError):
    """Raised when a content path is not a plain file directly under its root."""


def resolve_content_path(directory: Path, filename: str) -> Path:
    """Resolve ``filename`` inside ``directory``, rejecting traversal or nesting."""
    root = directory.resolve()
    if not _SAFE_FILENAME.fullmatch(filename):
        raise UnsafeContentPath(f"unsafe content file name: {filename!r}")
    candidate = (root / filename).resolve()
    if candidate.parent != root:
        raise UnsafeContentPath(f"content path escapes its directory: {filename!r}")
    return candidate


class DemoAssetStore:
    """Install-state and hash verification for assets under the runtime home.

    Assets live at ``<home>/datasets/demo/<asset_id>/<filename>``. Verification
    is content-based: the file is re-hashed on demand and compared against the
    manifest digest.
    """

    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.datasets_dir = self.home / "datasets" / "demo"

    def asset_dir(self, manifest: DemoAssetManifest) -> Path:
        return self.datasets_dir / safe_part(manifest.id)

    def content_path(self, manifest: DemoAssetManifest) -> Path:
        return resolve_content_path(self.asset_dir(manifest), manifest.filename)

    def state(self, manifest: DemoAssetManifest) -> InstalledAsset:
        path = self.content_path(manifest)
        installed = path.is_file()
        size_bytes = path.stat().st_size if installed else 0
        sha256_ok = installed and sha256_file(path) == manifest.sha256
        return InstalledAsset(
            manifest=manifest,
            path=path,
            installed=installed,
            size_bytes=size_bytes,
            sha256_ok=sha256_ok,
        )
