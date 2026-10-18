"""Small filesystem catalog for local experiments and content-addressed artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import BinaryIO, Iterable

from .models import ModelArtifact, PenSnapshot, RunResult, SimulationRun, TimelinePoint


_SAFE_PART = re.compile(r"[^a-zA-Z0-9._-]+")


class CatalogConflict(ValueError):
    """Raised when registration would mutate an existing artifact identity."""


def safe_part(value: str, fallback: str = "item") -> str:
    cleaned = _SAFE_PART.sub("-", value.strip()).strip(".-_")
    return cleaned[:80] or fallback


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, default=str).encode("utf-8") + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class Catalog:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.models_dir = self.root / "catalog" / "models"
        self.artifacts_dir = self.root / "artifacts"
        self.runs_dir = self.root / "runs"
        for directory in (self.models_dir, self.artifacts_dir, self.runs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def seed_mock_model(self) -> ModelArtifact:
        existing = self.get_model("mock-baseline")
        if existing:
            return existing
        model = ModelArtifact(
            id="mock-baseline",
            name="Mock baseline",
            version="1",
            format="mock",
            source="built-in",
            sha256=hashlib.sha256(b"mock-baseline").hexdigest(),
            size_bytes=0,
        )
        self.save_model(model)
        return model

    def save_model(self, model: ModelArtifact) -> None:
        path = self.models_dir / f"{safe_part(model.id)}.json"
        if path.exists():
            existing = ModelArtifact.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != model:
                raise CatalogConflict(f"model id already exists with different metadata: {model.id}")
            return
        atomic_json(path, model.model_dump(mode="json"))

    def list_models(self) -> list[ModelArtifact]:
        models = [ModelArtifact.model_validate_json(path.read_text(encoding="utf-8")) for path in self.models_dir.glob("*.json")]
        return sorted(models, key=lambda item: (item.created_at, item.id), reverse=True)

    def get_model(self, model_id: str) -> ModelArtifact | None:
        path = self.models_dir / f"{safe_part(model_id)}.json"
        if not path.is_file():
            return None
        model = ModelArtifact.model_validate_json(path.read_text(encoding="utf-8"))
        return model if model.id == model_id else None

    def register_stream(
        self,
        stream: BinaryIO,
        *,
        name: str,
        version: str,
        filename: str,
        source: str,
    ) -> ModelArtifact:
        suffix = Path(filename).suffix.lower().lstrip(".") or "bin"
        with tempfile.NamedTemporaryFile(prefix="upload-", dir=self.root, delete=False) as handle:
            temporary = Path(handle.name)
            digest = hashlib.sha256()
            size = 0
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                handle.write(chunk)
                size += len(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            sha256 = digest.hexdigest()
            model_id = "-".join(
                (
                    safe_part(name).lower()[:36],
                    safe_part(version).lower()[:16],
                    sha256[:12],
                )
            )
            normalized = {
                "name": name.strip(),
                "version": version.strip(),
                "format": suffix,
                "source": source.strip() or "upload",
                "sha256": sha256,
                "size_bytes": size,
            }
            existing = self.get_model(model_id)
            if existing is not None:
                actual = existing.model_dump(exclude={"schema_version", "id", "created_at"})
                if actual != normalized:
                    raise CatalogConflict(f"model id already exists with different metadata: {model_id}")
                blob = self._blob_path(sha256)
                if blob.exists() and self._hash_file(blob) != (sha256, size):
                    raise CatalogConflict(f"content-addressed artifact is corrupt: {sha256}")
                if blob.exists():
                    temporary.unlink()
                else:
                    blob.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(temporary, blob)
                return existing
            for registered in self.list_models():
                if (
                    registered.name == normalized["name"]
                    and registered.version == normalized["version"]
                    and registered.sha256 != sha256
                ):
                    raise CatalogConflict(
                        f"model {normalized['name']} version {normalized['version']} is already registered with different bytes"
                    )
            blob = self._blob_path(sha256)
            blob.parent.mkdir(parents=True, exist_ok=True)
            if blob.exists():
                temporary.unlink()
            else:
                os.replace(temporary, blob)
            model = ModelArtifact(
                id=model_id,
                **normalized,
            )
            self.save_model(model)
            return model
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def register_file(self, path: Path, **metadata: str) -> ModelArtifact:
        with path.open("rb") as stream:
            return self.register_stream(stream, filename=path.name, **metadata)

    def _blob_path(self, sha256: str) -> Path:
        return self.artifacts_dir / sha256[:2] / sha256

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def artifact_path(self, model: ModelArtifact) -> Path | None:
        return self._blob_path(model.sha256) if model.sha256 else None

    def save_run(
        self,
        run: SimulationRun,
        timeline: Iterable[TimelinePoint] | None = None,
        snapshots: Iterable[PenSnapshot] | None = None,
    ) -> None:
        directory = self.runs_dir / safe_part(run.id)
        atomic_json(directory / "metadata.json", run.model_dump(mode="json"))
        if timeline is not None:
            atomic_json(directory / "timeline.json", [item.model_dump(mode="json") for item in timeline])
        if snapshots is not None:
            atomic_json(directory / "snapshots.json", [item.model_dump(mode="json") for item in snapshots])

    def save_result(self, result: RunResult) -> None:
        directory = self.runs_dir / safe_part(result.run_id)
        atomic_json(directory / "result.json", result.model_dump(mode="json"))

    def get_result(self, run_id: str) -> RunResult | None:
        path = self.runs_dir / safe_part(run_id) / "result.json"
        if not path.is_file():
            return None
        result = RunResult.model_validate_json(path.read_text(encoding="utf-8"))
        return result if result.run_id == run_id else None

    def result_artifact(self, run_id: str, filename: str) -> tuple[str, int]:
        path = self.runs_dir / safe_part(run_id) / filename
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size

    def list_runs(self) -> list[SimulationRun]:
        runs = []
        for path in self.runs_dir.glob("*/metadata.json"):
            runs.append(SimulationRun.model_validate_json(path.read_text(encoding="utf-8")))
        return sorted(runs, key=lambda item: (item.created_at, item.id), reverse=True)

    def get_run(self, run_id: str) -> SimulationRun | None:
        path = self.runs_dir / safe_part(run_id) / "metadata.json"
        if not path.is_file():
            return None
        run = SimulationRun.model_validate_json(path.read_text(encoding="utf-8"))
        return run if run.id == run_id else None

    def get_timeline(self, run_id: str) -> list[TimelinePoint] | None:
        path = self.runs_dir / safe_part(run_id) / "timeline.json"
        if not path.is_file():
            return None
        return [TimelinePoint.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]

    def get_snapshots(self, run_id: str) -> list[PenSnapshot] | None:
        path = self.runs_dir / safe_part(run_id) / "snapshots.json"
        if not path.is_file():
            return None
        return [PenSnapshot.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
