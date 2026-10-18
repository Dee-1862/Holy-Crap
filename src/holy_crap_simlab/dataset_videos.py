"""Safe local index of reviewed dataset videos under ``<home>/datasets/videos``.

This module never downloads, copies, or modifies media bytes. It walks the
configured root and matches reviewed catalog entries by their exact safe file
name, returning only regular files located under the resolved root. Lookups
that are unsafe (traversal, escapes through symlinks) or ambiguous (duplicate
file names) are rejected instead of guessed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


class DatasetVideoLookupError(ValueError):
    """Raised when a local video lookup is unsafe or ambiguous."""


@dataclass(frozen=True)
class LocalDatasetVideo:
    """One resolved local file matching a reviewed clip's exact file name."""

    path: Path
    size_bytes: int


class LocalDatasetVideoStore:
    """Recursive exact-name index of regular video files under one root."""

    def __init__(self, root: Path | None = None, home: Path | None = None) -> None:
        configured = os.getenv("HOLY_CRAP_DATASET_VIDEOS_DIR")
        if configured:
            root = Path(configured)
        elif root is None:
            if home is None:
                raise ValueError("a dataset video root or home is required")
            root = Path(home) / "datasets" / "videos"
        self.root = Path(root).expanduser().resolve()

    def find(self, filename: str) -> LocalDatasetVideo | None:
        """Resolve one exact file name, or ``None`` when it is not installed.

        Raises :class:`DatasetVideoLookupError` for unsafe names, paths that
        resolve outside the configured root, non-regular files, and duplicate
        matches.
        """

        if not _SAFE_FILENAME.fullmatch(filename):
            raise DatasetVideoLookupError(f"unsafe dataset video file name: {filename!r}")
        if Path(filename).suffix.lower() not in _VIDEO_SUFFIXES:
            raise DatasetVideoLookupError(f"unsupported dataset video extension: {filename!r}")
        if not self.root.is_dir():
            return None
        matches: list[Path] = []
        for directory, subdirectories, files in os.walk(self.root):
            directory_path = Path(directory)
            subdirectories[:] = [
                name
                for name in subdirectories
                if not (directory_path / name).is_symlink()
            ]
            for name in files:
                if name != filename:
                    continue
                resolved = (directory_path / name).resolve()
                if not resolved.is_relative_to(self.root):
                    raise DatasetVideoLookupError(
                        f"dataset video escapes the configured root: {filename!r}"
                    )
                if not resolved.is_file():
                    raise DatasetVideoLookupError(
                        f"dataset video is not a regular file: {filename!r}"
                    )
                matches.append(resolved)
        if len(matches) > 1:
            raise DatasetVideoLookupError(
                f"ambiguous dataset video file name {filename!r}: "
                f"{len(matches)} matches under {self.root}"
            )
        if not matches:
            return None
        path = matches[0]
        return LocalDatasetVideo(path=path, size_bytes=path.stat().st_size)
