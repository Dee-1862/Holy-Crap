#!/usr/bin/env python3
"""Extract the CC BY 4.0 poultry-health Parquet distribution for local use.

The generated directory is directly consumable by ``ProxySpecimenRepository``:
it contains JPEGs plus one provenance-rich ``*.catalog.json`` file. Re-running
the command is safe; matching files are retained and only missing or corrupted
outputs are written again. Install the reader with ``pip install -e '.[datasets]'``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping

try:
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover - exercised by CLI environments
    raise SystemExit(
        "pyarrow is required; install it with: pip install -e '.[datasets]'"
    ) from exc


MENDELEY_URL = "https://data.mendeley.com/datasets/8pnbzpt2k9/1"
HUGGING_FACE_URL = "https://huggingface.co/datasets/Dianyo/poultry-health"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DATASET_NAME = "Poultry Birds Poo Imagery Dataset for Health Status Prediction"
ATTRIBUTION = (
    "Adebayo, Segun; Aworinde, Halleluyah; Akinwunmi, Akinwale; "
    "Alabi, Olufemi; Ayandiji, Adebamiji; Sakpere, Aderonke (2023); "
    "Hugging Face packaging by Tien-Yu Chi (2026)"
)
LABELS = {0: "healthy", 1: "unknown_abnormal"}
RELEASE_COUNTS = {"healthy": 7_991, "unknown_abnormal": 6_627}


@dataclass(frozen=True)
class IngestResult:
    catalog_path: Path
    total: int
    class_counts: dict[str, int]
    written: int
    retained: int


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _parquet_files(source_dir: Path) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for split in ("train", "test"):
        split_files = sorted(source_dir.glob(f"{split}-*.parquet"))
        if not split_files:
            raise ValueError(f"no {split} Parquet file found in {source_dir}")
        files.extend((split, path) for path in split_files)
    return files


def _rows(path: Path) -> Iterator[tuple[dict, int]]:
    parquet = pq.ParquetFile(path)
    names = set(parquet.schema_arrow.names)
    if not {"image", "label"}.issubset(names):
        raise ValueError(f"{path} must contain image and label columns")
    for batch in parquet.iter_batches(batch_size=256, columns=["image", "label"]):
        images = batch.column("image").to_pylist()
        labels = batch.column("label").to_pylist()
        yield from zip(images, labels, strict=True)


def _entry(
    *, split: str, index: int, source_file: Path, image: dict, label: int
) -> tuple[dict, bytes]:
    if label not in LABELS:
        raise ValueError(f"unsupported poultry-health label {label!r} in {source_file}")
    if not isinstance(image, dict) or not isinstance(image.get("bytes"), bytes):
        raise ValueError(f"missing embedded image bytes in {source_file} row {index}")
    content = image["bytes"]
    if not (content.startswith(b"\xff\xd8") and content.endswith(b"\xff\xd9")):
        raise ValueError(f"row {index} in {source_file} is not an embedded JPEG")

    demo_class = LABELS[label]
    asset_id = f"poultry-health-{split}-{index:05d}"
    filename = f"images/{demo_class}/{asset_id}.jpg"
    digest = _sha256_bytes(content)
    original_filename = image.get("path")
    return (
        {
            "asset_id": asset_id,
            "filename": filename,
            "media_type": "image/jpeg",
            "sha256": digest,
            "expected_demo_class": demo_class,
            "description": (
                "Healthy poultry feces photo"
                if label == 0
                else "Poultry feces photo labelled unhealthy; disease class unspecified"
            ),
            "substitution_reason": (
                "Licensed proxy specimen used after a video feces candidate is localized"
            ),
            "original_filename": original_filename,
            "source_filename": source_file.name,
            "label_evidence": {
                "kind": "dataset_label",
                "numeric_label": label,
                "source_class": "healthy" if label == 0 else "unhealthy",
                "mapped_demo_class": demo_class,
                "split": split,
                "row_index": index,
            },
            "source_sha256": digest,
        },
        content,
    )


def ingest_dataset(
    source_dir: Path,
    output_dir: Path,
    *,
    expected_counts: Mapping[str, int] | None = RELEASE_COUNTS,
) -> IngestResult:
    """Extract every image and create a deterministic repository catalog."""

    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    parquet_files = _parquet_files(source_dir)
    entries: list[dict] = []
    counts: Counter[str] = Counter()
    written = 0
    retained = 0
    source_files: list[dict] = []
    split_indices: Counter[str] = Counter()

    for split, source_file in parquet_files:
        source_files.append(
            {
                "filename": source_file.name,
                "sha256": _sha256_file(source_file),
                "rows": pq.ParquetFile(source_file).metadata.num_rows,
            }
        )
        for image, label in _rows(source_file):
            split_index = split_indices[split]
            entry, content = _entry(
                split=split,
                index=split_index,
                source_file=source_file,
                image=image,
                label=label,
            )
            destination = output_dir / entry["filename"]
            if destination.is_file() and _sha256_file(destination) == entry["sha256"]:
                retained += 1
            else:
                _atomic_write(destination, content)
                written += 1
            entries.append(entry)
            counts[entry["expected_demo_class"]] += 1
            split_indices[split] += 1

    actual_counts = dict(sorted(counts.items()))
    if expected_counts is not None and actual_counts != dict(sorted(expected_counts.items())):
        raise ValueError(
            f"unexpected class counts: expected {dict(expected_counts)}, got {actual_counts}"
        )

    catalog = {
        "schema_version": 1,
        "catalog_id": "poultry-health-hf-v1",
        "dataset": {
            "source_dataset": DATASET_NAME,
            "source_url": MENDELEY_URL,
            "license": "CC BY 4.0",
            "license_url": LICENSE_URL,
            "attribution": ATTRIBUTION,
            "acquisition_method": (
                f"Embedded JPEGs extracted from the Parquet distribution at {HUGGING_FACE_URL}"
            ),
            "redistribution_status": "CC BY 4.0 with attribution",
            "distribution_url": HUGGING_FACE_URL,
            "doi": "10.17632/8pnbzpt2k9.1",
        },
        "distribution_files": source_files,
        "class_counts": actual_counts,
        "specimens": entries,
    }
    catalog_path = output_dir / "poultry-health.catalog.json"
    rendered = (json.dumps(catalog, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if not catalog_path.is_file() or catalog_path.read_bytes() != rendered:
        _atomic_write(catalog_path, rendered)

    return IngestResult(
        catalog_path=catalog_path,
        total=len(entries),
        class_counts=actual_counts,
        written=written,
        retained=retained,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path(".simlab/datasets/feces/poultry-health-hf"),
        help="directory containing train-*.parquet and test-*.parquet",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".simlab/datasets/feces/optional-pools/nigeria"),
        help="optional research-only specimen repository directory to create",
    )
    parser.add_argument(
        "--allow-unexpected-counts",
        action="store_true",
        help="skip the official 7,991 healthy / 6,627 unhealthy release check",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = ingest_dataset(
        args.source_dir,
        args.output_dir,
        expected_counts=None if args.allow_unexpected_counts else RELEASE_COUNTS,
    )
    print(
        json.dumps(
            {
                "catalog": str(result.catalog_path),
                "total": result.total,
                "class_counts": result.class_counts,
                "written": result.written,
                "retained": result.retained,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
