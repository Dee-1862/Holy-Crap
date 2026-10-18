#!/usr/bin/env python3
"""Build a runtime-local proxy-specimen catalog from the Kaggle feces dataset.

The Kaggle mirror does not declare a reusable license. This tool therefore
downloads through the user's authenticated Kaggle CLI (when explicitly asked)
or ingests a user-supplied archive/directory for local evaluation. It never
stores credentials and never labels the mirror CC BY based on an assumed
upstream relationship.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DATASET_SLUG = "allandclive/chicken-disease-1"
CATALOG_ID = "kaggle-chicken-disease-1-v1"
CATALOG_FILENAME = f"{CATALOG_ID}.catalog.json"
SOURCE_URL = "https://www.kaggle.com/datasets/allandclive/chicken-disease-1/data"
SOURCE_DATASET = "Chicken Disease Image Classification (Kaggle mirror)"
UNKNOWN_LICENSE = "Unknown / local-use only"
DEFAULT_MAX_MEMBER_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024
DEFAULT_MAX_COMPRESSION_RATIO = 200.0

DESCRIPTION = (
    "Proxy feces photo for deterministic simulation; the source label is an "
    "appearance-classification reference, not a clinical diagnosis."
)
SUBSTITUTION_REASON = (
    "The whole-pen feces locator is simulated, so this external photo is used "
    "as the classifier input and did not come from the assessed video."
)

CLASS_PREFIXES = {
    "cocci": "cocci",
    "healthy": "healthy",
    "ncd": "ncd",
    "salmo": "salmo",
    "coccidiosis": "cocci",
    "newcastledisease": "ncd",
    "salmonella": "salmo",
}


class DatasetError(RuntimeError):
    """A user-actionable ingestion error."""


@dataclass(frozen=True)
class SourceImage:
    logical_path: str
    data: bytes


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_logical_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DatasetError(f"unsafe archive path: {value!r}")
    return path.as_posix()


def _image_type(data: bytes) -> tuple[str, str] | None:
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return ".jpg", "image/jpeg"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png", "image/png"
    return None


def _class_and_evidence(logical_path: str) -> tuple[str, str] | None:
    stem = PurePosixPath(logical_path).stem.lower()
    compact = "".join(character for character in stem if character.isalnum())
    evidence = "pcr" if compact.startswith("pcr") else "farm"
    if evidence == "pcr":
        compact = compact[3:]
    for prefix, label in sorted(CLASS_PREFIXES.items(), key=lambda pair: -len(pair[0])):
        if compact.startswith(prefix):
            return label, evidence
    return None


def _zip_images(
    path: Path,
    *,
    max_member_bytes: int,
    max_total_bytes: int,
    max_compression_ratio: float,
) -> Iterator[SourceImage]:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise DatasetError(f"cannot read ZIP archive {path}: {exc}") from exc
    with archive:
        members = sorted(archive.infolist(), key=lambda item: item.filename)
        total_uncompressed = 0
        for member in members:
            _safe_logical_path(member.filename)
            if member.is_dir():
                continue
            if member.file_size > max_member_bytes:
                raise DatasetError(
                    f"ZIP member exceeds {max_member_bytes} uncompressed bytes: "
                    f"{member.filename!r} ({member.file_size} bytes)"
                )
            total_uncompressed += member.file_size
            if total_uncompressed > max_total_bytes:
                raise DatasetError(
                    f"ZIP exceeds {max_total_bytes} total uncompressed bytes "
                    f"while indexing {member.filename!r}"
                )
            if member.file_size:
                if member.compress_size == 0:
                    raise DatasetError(
                        f"ZIP member has nonzero content but zero compressed size: {member.filename!r}"
                    )
                ratio = member.file_size / member.compress_size
                if ratio > max_compression_ratio:
                    raise DatasetError(
                        f"ZIP member compression ratio {ratio:.1f} exceeds "
                        f"limit {max_compression_ratio:.1f}: {member.filename!r}"
                    )
        for member in members:
            if member.is_dir():
                continue
            logical_path = _safe_logical_path(member.filename)
            with archive.open(member, "r") as handle:
                chunks: list[bytes] = []
                bytes_read = 0
                while chunk := handle.read(min(1024 * 1024, max_member_bytes + 1 - bytes_read)):
                    bytes_read += len(chunk)
                    if bytes_read > max_member_bytes:
                        raise DatasetError(
                            f"ZIP member expanded beyond {max_member_bytes} bytes while reading: "
                            f"{member.filename!r}"
                        )
                    chunks.append(chunk)
                data = b"".join(chunks)
            if len(data) != member.file_size:
                raise DatasetError(
                    f"ZIP member size changed while reading {member.filename!r}: "
                    f"expected {member.file_size}, got {len(data)}"
                )
            yield SourceImage(logical_path=logical_path, data=data)


def _directory_images(path: Path) -> Iterator[SourceImage]:
    root = path.resolve()
    for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise DatasetError(f"source path escapes input directory: {candidate}") from exc
        logical_path = _safe_logical_path(candidate.relative_to(path).as_posix())
        yield SourceImage(logical_path=logical_path, data=candidate.read_bytes())


def iter_source_images(
    path: Path,
    *,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> Iterator[SourceImage]:
    if max_member_bytes < 1 or max_total_bytes < 1 or max_compression_ratio < 1:
        raise DatasetError("ZIP safety limits must all be positive (compression ratio at least 1)")
    if not path.exists():
        raise DatasetError(f"input does not exist: {path}")
    if path.is_dir():
        yield from _directory_images(path)
    elif zipfile.is_zipfile(path):
        yield from _zip_images(
            path,
            max_member_bytes=max_member_bytes,
            max_total_bytes=max_total_bytes,
            max_compression_ratio=max_compression_ratio,
        )
    else:
        raise DatasetError("input must be an extracted directory or ZIP archive")


def _asset_id(logical_path: str, demo_class: str, evidence: str, digest: str) -> str:
    path_hash = hashlib.sha256(logical_path.encode("utf-8")).hexdigest()[:12]
    return f"kaggle-{demo_class}-{evidence}-{path_hash}-{digest[:12]}"


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".part", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _write_image(path: Path, data: bytes, digest: str) -> None:
    if path.is_file() and sha256_file(path) == digest:
        return
    _atomic_write_bytes(path, data)


def _catalog_bytes(catalog: dict[str, object]) -> bytes:
    return (json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def build_catalog(
    input_path: Path,
    output: Path,
    acquisition_method: str,
    *,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_compression_ratio: float = DEFAULT_MAX_COMPRESSION_RATIO,
) -> dict[str, object]:
    output = output.resolve()
    images_directory = output / "images"
    specimens: list[dict[str, object]] = []
    ignored_non_images = 0
    ignored_unclassified = 0
    seen_ids: dict[str, str] = {}

    for source in iter_source_images(
        input_path,
        max_member_bytes=max_member_bytes,
        max_total_bytes=max_total_bytes,
        max_compression_ratio=max_compression_ratio,
    ):
        image_type = _image_type(source.data)
        if image_type is None:
            ignored_non_images += 1
            continue
        classification = _class_and_evidence(source.logical_path)
        if classification is None:
            ignored_unclassified += 1
            continue
        demo_class, evidence = classification
        extension, media_type = image_type
        digest = _sha256_bytes(source.data)
        asset_id = _asset_id(source.logical_path, demo_class, evidence, digest)
        prior = seen_ids.get(asset_id)
        if prior is not None and prior != digest:
            raise DatasetError(f"asset-id collision for {source.logical_path}")
        seen_ids[asset_id] = digest
        relative_filename = f"images/{asset_id}{extension}"
        _write_image(images_directory / f"{asset_id}{extension}", source.data, digest)
        specimens.append(
            {
                "asset_id": asset_id,
                "attribution": (
                    "Dataset supplied by Kaggle user allandclive; apparent Machuve et al. "
                    "source relationship is retained as research context but not a license grant."
                ),
                "description": DESCRIPTION,
                "expected_demo_class": demo_class,
                "filename": relative_filename,
                "label_evidence": evidence,
                "license": UNKNOWN_LICENSE,
                "license_url": None,
                "media_type": media_type,
                "original_filename": source.logical_path,
                "schema_version": 1,
                "sha256": digest,
                "source_dataset": SOURCE_DATASET,
                "source_sha256": digest,
                "source_url": SOURCE_URL,
                "substitution_reason": SUBSTITUTION_REASON,
            }
        )

    specimens.sort(key=lambda item: str(item["asset_id"]))
    if not specimens:
        raise DatasetError("no classifiable JPEG or PNG specimens found")
    if len({item["asset_id"] for item in specimens}) != len(specimens):
        raise DatasetError("duplicate asset IDs in source")

    by_digest: dict[str, list[dict[str, object]]] = {}
    for specimen in specimens:
        by_digest.setdefault(str(specimen["sha256"]), []).append(specimen)
    duplicate_groups = [group for group in by_digest.values() if len(group) > 1]
    conflicting_groups = [
        group
        for group in duplicate_groups
        if len({str(item["expected_demo_class"]) for item in group}) > 1
    ]
    same_label_duplicate_excluded = 0
    for group in by_digest.values():
        ordered_group = sorted(group, key=lambda item: str(item["asset_id"]))
        canonical_asset_id = str(ordered_group[0]["asset_id"])
        conflicting = len({str(item["expected_demo_class"]) for item in group}) > 1
        for index, specimen in enumerate(ordered_group):
            specimen["canonical_asset_id"] = canonical_asset_id
            if conflicting:
                specimen["selection_eligible"] = False
                specimen["selection_exclusion_reason"] = "conflicting-labels"
            elif index == 0:
                specimen["selection_eligible"] = True
                specimen["selection_exclusion_reason"] = None
            else:
                specimen["selection_eligible"] = False
                specimen["selection_exclusion_reason"] = "exact-byte-duplicate"
                same_label_duplicate_excluded += 1

    integrity = {
        "conflicting_digest_group_count": len(conflicting_groups),
        "conflicting_row_count": sum(len(group) for group in conflicting_groups),
        "duplicate_digest_group_count": len(duplicate_groups),
        "duplicate_row_count": len(specimens) - len(by_digest),
        "same_label_duplicate_excluded_row_count": same_label_duplicate_excluded,
        "selection_eligible_row_count": len(by_digest) - len(conflicting_groups),
        "total_specimen_rows": len(specimens),
        "unique_sha256_count": len(by_digest),
    }

    source_digest = sha256_file(input_path) if input_path.is_file() else None
    catalog: dict[str, object] = {
        "catalog_id": CATALOG_ID,
        "dataset": {
            "acquisition_method": acquisition_method,
            "attribution": (
                "Dataset supplied by Kaggle user allandclive; use is restricted to local "
                "evaluation until reuse terms are verified."
            ),
            "license": UNKNOWN_LICENSE,
            "license_url": None,
            "redistribution_status": "Do not redistribute raw images until rights are verified.",
            "source_dataset": SOURCE_DATASET,
            "source_digest": source_digest,
            "source_url": SOURCE_URL,
        },
        "integrity": integrity,
        "schema_version": 1,
        "specimens": specimens,
    }
    output.mkdir(parents=True, exist_ok=True)
    _atomic_write_bytes(output / CATALOG_FILENAME, _catalog_bytes(catalog))
    return {
        "catalog": str(output / CATALOG_FILENAME),
        "ignored_non_images": ignored_non_images,
        "ignored_unclassified_images": ignored_unclassified,
        "specimens": len(specimens),
        **integrity,
    }


def fetch_kaggle(output: Path) -> Path:
    executable = shutil.which("kaggle")
    if executable is None:
        raise DatasetError(
            "Kaggle CLI is unavailable. Download the dataset in your browser, then run: "
            "python scripts/proxy_specimen_dataset.py ingest --input /path/to/archive.zip"
        )
    output.mkdir(parents=True, exist_ok=True)
    command = [executable, "datasets", "download", "-d", DATASET_SLUG, "-p", str(output)]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise DatasetError(
            "Kaggle download failed. Confirm your Kaggle API credentials and that you accepted "
            "the dataset terms, or download manually and pass the archive to `ingest`."
        ) from exc
    archives = sorted(output.glob("*.zip"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
    if not archives:
        raise DatasetError(f"Kaggle CLI completed but no ZIP archive was found in {output}")
    return archives[0]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="ingest a local Kaggle ZIP or directory")
    ingest.add_argument("--input", type=Path, required=True)
    ingest.add_argument("--output", type=Path, default=Path("datasets/proxy-specimens/kaggle"))
    ingest.add_argument(
        "--acquisition-method",
        choices=("manual-local", "kaggle-cli"),
        default="manual-local",
    )
    ingest.add_argument(
        "--max-member-bytes",
        type=int,
        default=DEFAULT_MAX_MEMBER_BYTES,
        help=f"maximum uncompressed bytes per ZIP member (default: {DEFAULT_MAX_MEMBER_BYTES})",
    )
    ingest.add_argument(
        "--max-total-bytes",
        type=int,
        default=DEFAULT_MAX_TOTAL_BYTES,
        help=f"maximum total uncompressed ZIP bytes (default: {DEFAULT_MAX_TOTAL_BYTES})",
    )
    ingest.add_argument(
        "--max-compression-ratio",
        type=float,
        default=DEFAULT_MAX_COMPRESSION_RATIO,
        help=(
            "maximum uncompressed/compressed ratio for one ZIP member "
            f"(default: {DEFAULT_MAX_COMPRESSION_RATIO:g})"
        ),
    )

    fetch = commands.add_parser("fetch-kaggle", help="download through the authenticated Kaggle CLI")
    fetch.add_argument("--output", type=Path, default=Path("datasets/downloads/kaggle"))
    fetch.add_argument("--ingest-output", type=Path)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "ingest":
            result = build_catalog(
                args.input,
                args.output,
                args.acquisition_method,
                max_member_bytes=args.max_member_bytes,
                max_total_bytes=args.max_total_bytes,
                max_compression_ratio=args.max_compression_ratio,
            )
        else:
            archive = fetch_kaggle(args.output)
            result = {"archive": str(archive)}
            if args.ingest_output is not None:
                result.update(build_catalog(archive, args.ingest_output, "kaggle-cli"))
    except DatasetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
