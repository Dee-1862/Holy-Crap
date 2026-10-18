#!/usr/bin/env python3
"""Fetch committed demo reference assets into the local runtime home.

Python-stdlib-only CLI: ``urllib`` transport, ``hashlib`` verification, and
``os.replace`` atomic install. Nothing downloads at import time or on
startup; running this script is the only trigger.

Usage:
    python3 scripts/fetch_demo_assets.py [asset_id] [--home PATH]

The default asset is ``pio-growth-stages``, the committed PIO paper Figure 3
reference manifest under ``demo-assets/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFESTS_DIR = REPO_ROOT / "demo-assets"
DEFAULT_ASSET_ID = "pio-growth-stages"
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_MAX_BYTES = 10 * 1024 * 1024

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_HEX64 = re.compile(r"^[a-f0-9]{64}$")

_REQUIRED_FIELDS = (
    "id",
    "title",
    "source_url",
    "dataset_url",
    "doi",
    "license",
    "license_url",
    "attribution",
    "sha256",
    "media_type",
    "width",
    "height",
    "filename",
    "limitations",
)


class FetchError(RuntimeError):
    """Raised when an asset cannot be located, downloaded, or verified."""


def load_manifest(asset_id: str) -> dict:
    """Load and minimally validate a committed manifest without network access."""
    path = MANIFESTS_DIR / f"{asset_id}.json"
    if not path.is_file():
        raise FetchError(f"no committed manifest for asset id {asset_id!r} at {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise FetchError(f"manifest {path} is not valid JSON: {exc}") from exc
    missing = [key for key in _REQUIRED_FIELDS if key not in manifest]
    if missing:
        raise FetchError(f"manifest {path} is missing fields: {', '.join(missing)}")
    if manifest["id"] != asset_id:
        raise FetchError(f"manifest id mismatch: {manifest['id']!r} != {asset_id!r}")
    if not _SAFE_ID.fullmatch(str(manifest["id"])):
        raise FetchError(f"manifest {path} has an unsafe asset id: {manifest['id']!r}")
    if not _HEX64.fullmatch(str(manifest["sha256"])):
        raise FetchError(f"manifest {path} has an invalid sha256 digest")
    if not _SAFE_FILENAME.fullmatch(str(manifest["filename"])):
        raise FetchError(f"manifest {path} has an unsafe filename: {manifest['filename']!r}")
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_asset(
    manifest: dict,
    destination: Path,
    *,
    source_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT_S,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict:
    """Download to a sibling temp file, verify sha256, then atomic replace.

    ``source_url`` overrides ``manifest["source_url"]`` (used by tests to stay
    offline). Returns the installed path, byte size, and verified digest.
    """
    url = source_url or str(manifest["source_url"])
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = str(manifest["sha256"]).lower()
    digest = hashlib.sha256()
    size = 0
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(fd)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            with open(temporary, "wb") as out:
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise FetchError(f"download exceeds size limit of {max_bytes} bytes")
                    digest.update(chunk)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
        actual = digest.hexdigest()
        if actual != expected:
            raise FetchError(f"sha256 mismatch for {url}: expected {expected}, got {actual}")
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return {"path": str(destination), "size_bytes": size, "sha256": actual}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fetch-demo-assets",
        description="Download and verify committed demo reference assets into the runtime home.",
    )
    parser.add_argument(
        "asset_id",
        nargs="?",
        default=DEFAULT_ASSET_ID,
        help=f"committed demo asset id (default: {DEFAULT_ASSET_ID})",
    )
    parser.add_argument(
        "--home",
        default=os.getenv("HOLY_CRAP_HOME", ".simlab"),
        help="runtime home to install into (default: HOLY_CRAP_HOME or .simlab)",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="download timeout in seconds")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="download size ceiling in bytes")
    return parser


def _print_summary(manifest: dict, destination: Path) -> None:
    print("asset:", manifest["id"])
    print("  title:", manifest["title"])
    print("  source:", manifest["source_url"])
    print("  dataset:", manifest["dataset_url"])
    print("  doi:", manifest["doi"])
    print("  license:", f"{manifest['license']} ({manifest['license_url']})")
    print("  attribution:", manifest["attribution"])
    print("  path:", destination)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.asset_id)
        destination = Path(args.home) / "datasets" / "demo" / str(manifest["id"]) / str(manifest["filename"])
        if destination.is_file() and sha256_file(destination) == str(manifest["sha256"]).lower():
            print(f"{manifest['id']} is already installed and verified")
            _print_summary(manifest, destination)
            return 0
        result = fetch_asset(manifest, destination, timeout=args.timeout, max_bytes=args.max_bytes)
        print(f"downloaded {result['size_bytes']} bytes, sha256 verified: {result['sha256']}")
        _print_summary(manifest, destination)
        return 0
    except (FetchError, urllib.error.URLError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
