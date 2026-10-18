from __future__ import annotations

from pathlib import Path

from holy_crap_simlab.cli import load_local_env, parser


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
