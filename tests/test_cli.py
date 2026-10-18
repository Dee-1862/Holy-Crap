from __future__ import annotations

from pathlib import Path

import pytest

from holy_crap_simlab.cli import _validate_report_path, load_local_env, parser
from holy_crap_simlab.preprocessing import VideoToolError


def test_local_env_supplies_serve_defaults_without_overriding_process_env(
    tmp_path: Path, monkeypatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HOLY_CRAP_API_HOST=127.0.0.2\nHOLY_CRAP_API_PORT=8123\nHOLY_CRAP_HOME=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("HOLY_CRAP_API_HOST", raising=False)
    monkeypatch.delenv("HOLY_CRAP_API_PORT", raising=False)
    monkeypatch.setenv("HOLY_CRAP_HOME", "from-process")

    load_local_env(env_file)
    args = parser().parse_args(["serve"])

    assert args.host == "127.0.0.2"
    assert args.port == 8123
    assert __import__("os").environ["HOLY_CRAP_HOME"] == "from-process"


def test_video_preprocess_defaults_to_balanced_profile() -> None:
    args = parser().parse_args(["preprocess-video", "input.mp4", "output.mp4"])

    assert args.profile == "pi-balanced"
    assert args.size is None
    assert args.output == Path("output.mp4")


def test_video_size_is_validated_by_parser() -> None:
    with pytest.raises(SystemExit):
        parser().parse_args(["preprocess-video", "input.mp4", "output.mp4", "--size", "wide"])


def test_report_cannot_replace_a_video() -> None:
    with pytest.raises(VideoToolError, match="must differ"):
        _validate_report_path(Path("output.mp4"), Path("input.mp4"), Path("output.mp4"))
