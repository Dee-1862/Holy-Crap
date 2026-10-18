"""Small ffmpeg wrapper for repeatable whole-pen video variants.

The module deliberately keeps encoding benchmarks separate from model
benchmarks.  A smaller H.264 file reduces storage and transfer cost, but it
does not prove that a decoded tensor runs faster on the Pi.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal, Sequence


RunCommand = Callable[..., subprocess.CompletedProcess[str]]
ColorMode = Literal["color", "grayscale"]
Codec = Literal["h264", "h265", "mjpeg"]


class VideoToolError(RuntimeError):
    """Raised when ffmpeg/ffprobe cannot produce a valid result."""


@dataclass(frozen=True)
class TranscodeSpec:
    """One reproducible preprocessing variant."""

    width: int
    height: int
    fps: float
    color_mode: ColorMode = "color"
    codec: Codec = "h264"
    quality: int = 23
    preset: str = "medium"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.fps <= 0 or not math.isfinite(self.fps):
            raise ValueError("fps must be a positive finite number")
        if self.color_mode not in ("color", "grayscale"):
            raise ValueError("color_mode must be color or grayscale")
        if self.codec not in ("h264", "h265", "mjpeg"):
            raise ValueError("codec must be h264, h265, or mjpeg")
        if not 0 <= self.quality <= 51:
            raise ValueError("quality must be between 0 and 51")


PROFILES: dict[str, TranscodeSpec] = {
    # Recommended default for reviewing appearance while staying near the
    # measured Pi capture/inference ceiling.
    "pi-balanced": TranscodeSpec(960, 540, 11.0, "color", "h264", 23, "medium"),
    # Cheap luma-oriented stream for activity gating. Do not use it as the only
    # input for appearance, injury, or dropping-color review.
    "motion-gate": TranscodeSpec(320, 180, 5.5, "grayscale", "h264", 28, "fast"),
    # Workstation/reference output that preserves more small-object detail.
    "detail": TranscodeSpec(1920, 1080, 11.0, "color", "h264", 23, "slow"),
}


@dataclass(frozen=True)
class VideoMetadata:
    path: str
    size_bytes: int
    duration_seconds: float | None
    calculated_bitrate_bps: int | None
    width: int
    height: int
    fps: float | None
    frame_count: int | None
    codec: str | None
    pixel_format: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_tool(name: str) -> str:
    """Return a runnable binary or fail with an install-oriented error."""

    resolved = shutil.which(name)
    if resolved:
        return resolved
    raise VideoToolError(f"{name!r} was not found; install ffmpeg (which includes ffprobe)")


def _positive_float(value: object) -> float | None:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _frame_rate(value: object) -> float | None:
    text = str(value or "")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        top = _positive_float(numerator)
        bottom = _positive_float(denominator)
        return top / bottom if top is not None and bottom is not None else None
    return _positive_float(text)


def parse_probe_payload(path: Path, payload: dict[str, Any]) -> VideoMetadata:
    """Normalize the small ffprobe JSON subset used by the benchmark."""

    streams = payload.get("streams") or []
    if not streams:
        raise VideoToolError(f"no video stream found in {path}")
    stream = streams[0]
    container = payload.get("format") or {}
    try:
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VideoToolError(f"ffprobe did not report video dimensions for {path}") from exc

    size = path.stat().st_size
    duration = _positive_float(container.get("duration")) or _positive_float(stream.get("duration"))
    bitrate = round(size * 8 / duration) if duration else None
    fps = _frame_rate(stream.get("avg_frame_rate")) or _frame_rate(stream.get("r_frame_rate"))
    raw_frames = stream.get("nb_frames")
    try:
        frames = int(raw_frames) if raw_frames not in (None, "", "N/A") else None
    except (TypeError, ValueError):
        frames = None
    return VideoMetadata(
        path=str(path),
        size_bytes=size,
        duration_seconds=duration,
        calculated_bitrate_bps=bitrate,
        width=width,
        height=height,
        fps=fps,
        frame_count=frames,
        codec=stream.get("codec_name"),
        pixel_format=stream.get("pix_fmt"),
    )


def probe_video(
    path: Path,
    *,
    ffprobe_bin: str = "ffprobe",
    runner: RunCommand = subprocess.run,
) -> VideoMetadata:
    """Inspect the first video stream without decoding the full file."""

    path = Path(path)
    if not path.is_file():
        raise VideoToolError(f"input video does not exist: {path}")
    binary = resolve_tool(ffprobe_bin)
    command = [
        binary,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        (
            "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,"
            "codec_name,pix_fmt,duration:format=duration"
        ),
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = runner(command, check=True, capture_output=True, text=True)
        payload = json.loads(completed.stdout)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise VideoToolError(f"ffprobe failed for {path}: {detail or exc}") from exc
    except OSError as exc:
        raise VideoToolError(f"could not run ffprobe for {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise VideoToolError(f"ffprobe returned invalid JSON for {path}") from exc
    return parse_probe_payload(path, payload)


def _filter_graph(spec: TranscodeSpec) -> str:
    filters = [
        (
            f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,"
            f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2"
        ),
        f"fps={spec.fps:g}",
    ]
    if spec.color_mode == "grayscale":
        # Neutral chroma in yuv420p stays broadly playable. It is a motion-gate
        # representation, not evidence that color is irrelevant to diagnosis.
        filters.append("hue=s=0")
    return ",".join(filters)


def build_ffmpeg_command(
    source: Path,
    output: Path,
    spec: TranscodeSpec,
    *,
    ffmpeg_bin: str = "ffmpeg",
    overwrite: bool = False,
) -> list[str]:
    """Build a deterministic, video-only ffmpeg command."""

    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y" if overwrite else "-n",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        _filter_graph(spec),
    ]
    if spec.codec == "h264":
        command.extend(["-c:v", "libx264", "-crf", str(spec.quality), "-preset", spec.preset])
    elif spec.codec == "h265":
        command.extend(
            ["-c:v", "libx265", "-crf", str(spec.quality), "-preset", spec.preset, "-tag:v", "hvc1"]
        )
    else:
        # ffmpeg's MJPEG quality scale is 2 (best) through 31 (worst).
        mjpeg_quality = max(2, min(31, spec.quality))
        command.extend(["-c:v", "mjpeg", "-q:v", str(mjpeg_quality)])
    command.extend(["-pix_fmt", "yuv420p"])
    if output.suffix.lower() in {".mp4", ".mov", ".m4v"}:
        command.extend(["-movflags", "+faststart"])
    command.append(str(output))
    return command


def transcode_video(
    source: Path,
    output: Path,
    spec: TranscodeSpec,
    *,
    ffmpeg_bin: str = "ffmpeg",
    overwrite: bool = False,
    runner: RunCommand = subprocess.run,
) -> Sequence[str]:
    """Create one variant and return the exact command used."""

    source = Path(source)
    output = Path(output)
    if not source.is_file():
        raise VideoToolError(f"input video does not exist: {source}")
    if source.resolve() == output.resolve():
        raise VideoToolError("input and output paths must be different")
    if output.exists() and not overwrite:
        raise VideoToolError(f"output exists (pass --overwrite to replace it): {output}")
    binary = resolve_tool(ffmpeg_bin)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = build_ffmpeg_command(source, output, spec, ffmpeg_bin=binary, overwrite=overwrite)
    try:
        runner(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise VideoToolError(f"ffmpeg failed: {detail or exc}") from exc
    except OSError as exc:
        raise VideoToolError(f"could not run ffmpeg: {exc}") from exc
    if not output.is_file():
        raise VideoToolError(f"ffmpeg completed without creating {output}")
    return command


def override_spec(
    profile: str,
    *,
    size: tuple[int, int] | None = None,
    fps: float | None = None,
    color_mode: ColorMode | None = None,
    codec: Codec | None = None,
    quality: int | None = None,
    preset: str | None = None,
) -> TranscodeSpec:
    """Apply explicit CLI overrides to a named baseline profile."""

    try:
        base = PROFILES[profile]
    except KeyError as exc:
        raise ValueError(f"unknown profile: {profile}") from exc
    return replace(
        base,
        width=size[0] if size else base.width,
        height=size[1] if size else base.height,
        fps=fps if fps is not None else base.fps,
        color_mode=color_mode or base.color_mode,
        codec=codec or base.codec,
        quality=quality if quality is not None else base.quality,
        preset=preset or base.preset,
    )


def comparison_report(
    source: VideoMetadata,
    output: VideoMetadata,
    spec: TranscodeSpec,
    command: Sequence[str],
) -> dict[str, Any]:
    """Build a machine-readable report without claiming model performance."""

    size_ratio = output.size_bytes / source.size_bytes if source.size_bytes else None
    reduction = (1 - size_ratio) * 100 if size_ratio is not None else None
    decoded_channels = 1 if spec.color_mode == "grayscale" else 3
    return {
        "schema_version": 1,
        "evaluation_kind": "media_preprocessing",
        "source": source.to_dict(),
        "output": output.to_dict(),
        "transform": asdict(spec),
        "storage": {
            "size_ratio": size_ratio,
            "size_reduction_percent": reduction,
            "bitrate_reduction_percent": (
                (1 - output.calculated_bitrate_bps / source.calculated_bitrate_bps) * 100
                if source.calculated_bitrate_bps and output.calculated_bitrate_bps
                else None
            ),
        },
        "model_input_planning": {
            "pixels_per_frame": spec.width * spec.height,
            "intended_model_channels": decoded_channels,
            "nominal_model_samples_per_second": round(
                spec.width * spec.height * decoded_channels * spec.fps
            ),
            "note": (
                "A planning estimate only; grayscale assumes the inference pipeline extracts one luma "
                "channel from the compatible yuv420p video. This is not measured Pi inference time."
            ),
        },
        "command": list(command),
        "claims": {
            "storage_and_transfer_measured": True,
            "decode_latency_measured": False,
            "inference_latency_measured": False,
            "model_accuracy_measured": False,
        },
        "notes": [
            "Encoded file size and bitrate measure storage/transfer cost, not inference compute.",
            "Resolution, sampled FPS, channel count, preprocessing, model shape, and runtime affect inference cost.",
            "Keep a full-color path for appearance, injury, and dropping review; grayscale is intended for motion gating.",
        ],
    }
