from __future__ import annotations

from pathlib import Path

from scripts.dev import _configure_farmer_alerts, _configure_proxy_specimen_pool


def test_dev_supervisor_enables_local_farmer_alerts() -> None:
    environ: dict[str, str] = {}

    _configure_farmer_alerts(environ)

    assert environ["HOLY_CRAP_FARMER_ALERTS_ENABLED"] == "1"
    assert environ["HOLY_CRAP_FARMER_AGENT_URL"] == (
        "http://127.0.0.1:4317/simulation-alerts"
    )


def test_generated_catalog_root_is_configured_without_reading_catalog(
    tmp_path: Path,
) -> None:
    catalog = (
        tmp_path
        / ".simlab"
        / "datasets"
        / "feces"
        / "proxy-pools"
        / "kaggle"
        / "pool.catalog.json"
    )
    catalog.parent.mkdir(parents=True)
    catalog.write_text("not parsed by the supervisor", encoding="utf-8")
    environ: dict[str, str] = {}

    result = _configure_proxy_specimen_pool(environ, tmp_path)

    assert result == catalog.parent
    assert environ["HOLY_CRAP_PROXY_SPECIMENS_DIR"] == str(catalog.parent)


def test_explicit_proxy_directory_is_never_overridden(tmp_path: Path) -> None:
    explicit = tmp_path / "my-pool"
    environ = {"HOLY_CRAP_PROXY_SPECIMENS_DIR": str(explicit)}

    result = _configure_proxy_specimen_pool(environ, tmp_path)

    assert result == explicit
    assert environ == {"HOLY_CRAP_PROXY_SPECIMENS_DIR": str(explicit)}


def test_committed_fallback_remains_when_generated_catalog_is_absent(
    tmp_path: Path,
) -> None:
    combined = tmp_path / ".simlab" / "datasets" / "feces" / "proxy-pools"
    combined.mkdir(parents=True)
    (combined / "README.md").write_text("no catalog", encoding="utf-8")
    environ: dict[str, str] = {}

    assert _configure_proxy_specimen_pool(environ, tmp_path) is None
    assert "HOLY_CRAP_PROXY_SPECIMENS_DIR" not in environ


def test_optional_nigeria_pool_is_not_auto_discovered(tmp_path: Path) -> None:
    optional_catalog = (
        tmp_path
        / ".simlab"
        / "datasets"
        / "feces"
        / "optional-pools"
        / "nigeria"
        / "poultry-health.catalog.json"
    )
    optional_catalog.parent.mkdir(parents=True)
    optional_catalog.write_text("not loaded automatically", encoding="utf-8")
    environ: dict[str, str] = {}

    assert _configure_proxy_specimen_pool(environ, tmp_path) is None
    assert "HOLY_CRAP_PROXY_SPECIMENS_DIR" not in environ
