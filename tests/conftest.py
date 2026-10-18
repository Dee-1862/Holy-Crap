from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from holy_crap_simlab.api import create_app


@pytest.fixture
def scenario_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "scenarios"


@pytest.fixture
def client(tmp_path: Path, scenario_directory: Path) -> TestClient:
    with TestClient(create_app(tmp_path / "simlab", scenario_directory)) as test_client:
        yield test_client
