"""Command-line entry points for serving the API and importing local artifacts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

import uvicorn

from .adapters import VeriArtifactImporter
from .catalog import Catalog


def load_local_env(path: Path | None = None) -> None:
    """Load simple KEY=VALUE settings without overriding the process environment."""
    candidates = [path] if path else [Path.cwd() / ".env", Path(__file__).resolve().parents[2] / ".env"]
    env_path = next((candidate for candidate in candidates if candidate and candidate.is_file()), None)
    if env_path is None:
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        os.environ.setdefault(key, value.strip().strip("'\""))


def _api_port() -> int:
    value = os.getenv("HOLY_CRAP_API_PORT", "8000")
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError("HOLY_CRAP_API_PORT must be an integer") from exc


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="holy-crap-simlab")
    commands = root.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the local API")
    serve.add_argument("--host", default=os.getenv("HOLY_CRAP_API_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=_api_port())
    importer = commands.add_parser("import-veri", help="import a completed local Veri output directory")
    importer.add_argument("path", type=Path)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    load_local_env()
    args = parser().parse_args(argv)
    if args.command == "serve":
        from .api import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, reload=False)
        return 0
    home = Path(os.getenv("HOLY_CRAP_HOME", ".simlab"))
    model = VeriArtifactImporter(Catalog(home)).import_directory(args.path)
    print(json.dumps(model.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
