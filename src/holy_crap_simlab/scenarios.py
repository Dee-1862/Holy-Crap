"""Scenario loading with validation and duplicate detection."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Scenario


class ScenarioRepository:
    def __init__(self, directory: Path | None = None) -> None:
        configured = os.getenv("HOLY_CRAP_SCENARIOS_DIR")
        self.directory = Path(configured) if configured else directory or self.default_directory()
        self._scenarios = self._load()

    @staticmethod
    def default_directory() -> Path:
        return Path(__file__).resolve().parents[2] / "scenarios"

    def _load(self) -> dict[str, Scenario]:
        scenarios: dict[str, Scenario] = {}
        for path in sorted(self.directory.glob("*.json")):
            scenario = Scenario.model_validate(json.loads(path.read_text(encoding="utf-8")))
            if scenario.id in scenarios:
                raise ValueError(f"duplicate scenario id: {scenario.id}")
            scenarios[scenario.id] = scenario
        if not scenarios:
            raise ValueError(f"no scenario JSON files found in {self.directory}")
        return scenarios

    def list(self) -> list[Scenario]:
        return sorted(self._scenarios.values(), key=lambda item: item.id)

    def get(self, scenario_id: str) -> Scenario | None:
        return self._scenarios.get(scenario_id)
