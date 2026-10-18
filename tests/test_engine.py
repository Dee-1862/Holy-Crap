from __future__ import annotations

from pathlib import Path

from holy_crap_simlab.engine import simulate
from holy_crap_simlab.scenarios import ScenarioRepository


def test_simulation_is_deterministic(scenario_directory: Path) -> None:
    scenario = ScenarioRepository(scenario_directory).get("outbreak-100")
    assert scenario is not None

    first = simulate(scenario, "mock-baseline")
    second = simulate(scenario, "mock-baseline")

    assert first == second
    assert len(first.timeline) == 61
    assert len(first.snapshots) == 61
    assert all(len(snapshot.birds) == 100 for snapshot in first.snapshots)
    assert [bird.id for bird in first.snapshots[0].birds] == [bird.id for bird in first.snapshots[-1].birds]


def test_healthy_control_never_has_infected_truth(scenario_directory: Path) -> None:
    scenario = ScenarioRepository(scenario_directory).get("healthy-100")
    assert scenario is not None
    result = simulate(scenario, "mock-baseline")

    assert all(point.exposed == point.infectious == point.clinical == 0 for point in result.timeline)
    assert all(point.truth_score == 0 for point in result.timeline)
    assert result.metrics.detection_delay_s is None
    assert not result.metrics.alert_triggered


def test_outbreak_control_progresses_and_alerts(scenario_directory: Path) -> None:
    scenario = ScenarioRepository(scenario_directory).get("outbreak-100")
    assert scenario is not None
    result = simulate(scenario, "mock-baseline")

    assert result.timeline[0].susceptible == 100
    assert result.timeline[-1].susceptible < 100
    assert any(point.exposed > 0 for point in result.timeline)
    assert any(point.infectious > 0 for point in result.timeline)
    assert any(point.clinical > 0 for point in result.timeline)
    assert any(point.predicted_score != point.truth_score for point in result.timeline)
    assert result.metrics.alert_triggered
    assert result.metrics.detection_delay_s is not None
