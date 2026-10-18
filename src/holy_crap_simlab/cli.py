"""Command-line entry points for serving the API and importing local artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

import uvicorn

from .adapters import VeriArtifactImporter
from .catalog import Catalog
from .preprocessing import (
    PROFILES,
    VideoToolError,
    comparison_report,
    override_spec,
    probe_video,
    transcode_video,
)


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
    preprocess = commands.add_parser(
        "preprocess-video",
        help="inspect a video or create and measure a Pi-oriented variant",
    )
    preprocess.add_argument("input", type=Path)
    preprocess.add_argument("output", type=Path, nargs="?", help="omit to inspect the source only")
    preprocess.add_argument("--profile", choices=sorted(PROFILES), default="pi-balanced")
    preprocess.add_argument("--size", type=_video_size, metavar="WIDTHxHEIGHT")
    preprocess.add_argument("--fps", type=float)
    preprocess.add_argument("--color-mode", choices=("color", "grayscale"))
    preprocess.add_argument("--codec", choices=("h264", "h265", "mjpeg"))
    preprocess.add_argument("--quality", type=int, help="CRF for H.26x; qscale (2-31) for MJPEG")
    preprocess.add_argument("--preset", help="ffmpeg encoder preset")
    preprocess.add_argument("--overwrite", action="store_true")
    preprocess.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable")
    preprocess.add_argument("--ffprobe", default="ffprobe", help="ffprobe executable")
    preprocess.add_argument("--report", type=Path, help="also write the JSON report to this path")
    return root


def _video_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("size must look like WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("width and height must be positive")
    return width, height


def _emit_report(report: dict[str, object], path: Path | None) -> None:
    rendered = json.dumps(report, indent=2)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


def _validate_report_path(report: Path | None, *media_paths: Path) -> None:
    if report is None:
        return
    report_path = report.resolve()
    if any(report_path == path.resolve() for path in media_paths):
        raise VideoToolError("the JSON report path must differ from input and output video paths")


def main(argv: Sequence[str] | None = None) -> int:
    load_local_env()
    args = parser().parse_args(argv)
    if args.command == "serve":
        from .api import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, reload=False)
        return 0
    if args.command == "preprocess-video":
        try:
            _validate_report_path(args.report, args.input, *([args.output] if args.output else []))
            source = probe_video(args.input, ffprobe_bin=args.ffprobe)
            if args.output is None:
                _emit_report(
                    {
                        "schema_version": 1,
                        "evaluation_kind": "media_inspection",
                        "source": source.to_dict(),
                        "note": "Container bitrate measures storage/transfer cost, not model inference speed.",
                    },
                    args.report,
                )
                return 0
            spec = override_spec(
                args.profile,
                size=args.size,
                fps=args.fps,
                color_mode=args.color_mode,
                codec=args.codec,
                quality=args.quality,
                preset=args.preset,
            )
            command = transcode_video(
                args.input,
                args.output,
                spec,
                ffmpeg_bin=args.ffmpeg,
                overwrite=args.overwrite,
            )
            output = probe_video(args.output, ffprobe_bin=args.ffprobe)
            _emit_report(comparison_report(source, output, spec, command), args.report)
            return 0
        except (ValueError, VideoToolError) as exc:
            print(f"video preprocessing failed: {exc}", file=sys.stderr)
            return 2
    home = Path(os.getenv("HOLY_CRAP_HOME", ".simlab"))
    model = VeriArtifactImporter(Catalog(home)).import_directory(args.path)
    print(json.dumps(model.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
