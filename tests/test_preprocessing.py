from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from holy_crap_simlab.preprocessing import (
    PROFILES,
    TranscodeSpec,
    VideoToolError,
    build_ffmpeg_command,
    comparison_report,
    parse_probe_payload,
    transcode_video,
)


def _payload(*, width: int = 1920, height: int = 1080, duration: str = "2.0") -> dict:
    return {
        "streams": [
            {
                "width": width,
                "height": height,
                "avg_frame_rate": "11/1",
                "r_frame_rate": "11/1",
                "nb_frames": "22",
                "codec_name": "h264",
                "pix_fmt": "yuv420p",
            }
        ],
        "format": {"duration": duration},
    }


def test_probe_payload_reports_metadata_and_calculated_bitrate(tmp_path: Path) -> None:
    video = tmp_path / "whole-pen.mp4"
    video.write_bytes(b"x" * 1_000)

    metadata = parse_probe_payload(video, _payload())

    assert metadata.width == 1920
    assert metadata.height == 1080
    assert metadata.fps == 11
    assert metadata.frame_count == 22
    assert metadata.calculated_bitrate_bps == 4_000


def test_balanced_command_preserves_color_and_aspect_ratio() -> None:
    command = build_ffmpeg_command(
        Path("pen.mp4"), Path("balanced.mp4"), PROFILES["pi-balanced"], ffmpeg_bin="ffmpeg"
    )

    filters = command[command.index("-vf") + 1]
    assert "scale=960:540:force_original_aspect_ratio=decrease" in filters
    assert "pad=960:540" in filters
    assert "fps=11" in filters
    assert "hue=s=0" not in filters
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[-1] == "balanced.mp4"


def test_motion_gate_is_explicitly_grayscale() -> None:
    command = build_ffmpeg_command(
        Path("pen.mp4"), Path("motion.mp4"), PROFILES["motion-gate"], ffmpeg_bin="ffmpeg"
    )
    filters = command[command.index("-vf") + 1]

    assert "scale=320:180" in filters
    assert "fps=5.5" in filters
    assert "hue=s=0" in filters


def test_transcode_refuses_existing_output_before_running(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"
    source.write_bytes(b"source")
    output.write_bytes(b"existing")

    with pytest.raises(VideoToolError, match="output exists"):
        transcode_video(source, output, PROFILES["pi-balanced"], ffmpeg_bin="/bin/true")


def test_transcode_invokes_tool_and_requires_created_output(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "nested" / "output.mp4"
    source.write_bytes(b"source")
    calls: list[list[str]] = []

    def fake_runner(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"encoded")
        return subprocess.CompletedProcess(command, 0, "", "")

    command = transcode_video(
        source,
        output,
        PROFILES["pi-balanced"],
        ffmpeg_bin=sys.executable,
        runner=fake_runner,
    )

    assert calls == [command]
    assert output.read_bytes() == b"encoded"


def test_report_separates_storage_from_inference_claims(tmp_path: Path) -> None:
    source_path = tmp_path / "source.mp4"
    output_path = tmp_path / "output.mp4"
    source_path.write_bytes(b"x" * 2_000)
    output_path.write_bytes(b"x" * 500)
    source = parse_probe_payload(source_path, _payload())
    output = parse_probe_payload(output_path, _payload(width=960, height=540))

    report = comparison_report(source, output, PROFILES["pi-balanced"], ["ffmpeg"])

    assert report["storage"]["size_reduction_percent"] == 75
    assert report["claims"] == {
        "storage_and_transfer_measured": True,
        "decode_latency_measured": False,
        "inference_latency_measured": False,
        "model_accuracy_measured": False,
    }
    assert report["model_input_planning"]["nominal_model_samples_per_second"] == 960 * 540 * 3 * 11


@pytest.mark.parametrize(
    ("width", "height", "fps"),
    [
        (0, 540, 11),
        (960, 540, 0),
    ],
)
def test_invalid_specs_are_rejected(width: int, height: int, fps: float) -> None:
    with pytest.raises(ValueError):
        TranscodeSpec(width, height, fps)
