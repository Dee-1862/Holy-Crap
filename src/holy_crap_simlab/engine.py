"""Deterministic control simulator for exercising the product pipeline."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .models import BirdSnapshot, PenSnapshot, RunMetrics, Scenario, ScenarioMode, TimelinePoint, TruthState


@dataclass(frozen=True)
class SimulationResult:
    timeline: list[TimelinePoint]
    snapshots: list[PenSnapshot]
    metrics: RunMetrics


def _population_at(scenario: Scenario, t_s: int) -> tuple[int, int, int, int]:
    if scenario.mode is ScenarioMode.HEALTHY:
        return scenario.bird_count, 0, 0, 0

    start = int(scenario.observation.onset_s or 8)
    elapsed = max(0, t_s - start)
    initial = round(scenario.bird_count * scenario.observation.initial_affected_fraction)
    affected = 0 if t_s < start else min(round(scenario.bird_count * 0.60), initial + elapsed * 2)
    infectious_total = min(round(scenario.bird_count * 0.30), max(0, elapsed - 12))
    clinical = min(round(scenario.bird_count * 0.15), max(0, (elapsed - 28) // 2 + 1))
    infectious = max(0, infectious_total - clinical)
    exposed = max(0, affected - infectious_total)
    susceptible = scenario.bird_count - exposed - infectious - clinical
    return susceptible, exposed, infectious, clinical


def simulate(scenario: Scenario, model_id: str) -> SimulationResult:
    """Return the same observations for the same scenario, model identifier, and seed."""
    model_salt = sum((index + 1) * ord(char) for index, char in enumerate(model_id))
    rng = random.Random(scenario.seed + model_salt)
    disease_order = list(range(scenario.bird_count))
    rng.shuffle(disease_order)
    base_positions = [
        (rng.uniform(0, scenario.pen_width_m), rng.uniform(0, scenario.pen_height_m), rng.uniform(0, 360))
        for _ in range(scenario.bird_count)
    ]
    timeline: list[TimelinePoint] = []
    snapshots: list[PenSnapshot] = []
    threshold = scenario.observation.alert_threshold

    for t_s in range(scenario.duration_s + 1):
        susceptible, exposed, infectious, clinical = _population_at(scenario, t_s)
        abnormal = min(scenario.bird_count, round(infectious * 0.35 + clinical * 0.85))
        truth_score = min(1.0, (infectious + clinical * 1.6 + abnormal * 0.8) / scenario.bird_count)
        measurement_noise = rng.uniform(-0.025, 0.025)
        predicted_score = min(1.0, max(0.0, truth_score * 0.82 + 0.018 + measurement_noise))
        alert = predicted_score >= threshold
        timeline.append(
            TimelinePoint(
                t_s=t_s,
                susceptible=susceptible,
                exposed=exposed,
                infectious=infectious,
                clinical=clinical,
                abnormal_droppings=abnormal,
                truth_score=round(truth_score, 5),
                predicted_score=round(predicted_score, 5),
                alert=alert,
            )
        )

        states = (
            [TruthState.CLINICAL] * clinical
            + [TruthState.INFECTIOUS] * infectious
            + [TruthState.EXPOSED] * exposed
        )
        state_by_bird = {disease_order[index]: state for index, state in enumerate(states)}
        birds: list[BirdSnapshot] = []
        for bird_index, (base_x, base_y, base_heading) in enumerate(base_positions):
            state = state_by_bird.get(bird_index, TruthState.SUSCEPTIBLE)
            phase = t_s * 0.13 + bird_index * 0.71
            x = min(scenario.pen_width_m, max(0.0, base_x + math.sin(phase) * 0.18))
            y = min(scenario.pen_height_m, max(0.0, base_y + math.cos(phase * 0.83) * 0.18))
            sensitivity = {
                TruthState.SUSCEPTIBLE: scenario.observation.false_positive_rate,
                TruthState.EXPOSED: 0.12,
                TruthState.INFECTIOUS: max(0.0, 0.72 - scenario.observation.miss_probability),
                TruthState.CLINICAL: max(0.0, 0.96 - scenario.observation.miss_probability),
            }[state]
            prediction_rng = random.Random(scenario.seed * 10_007 + model_salt + t_s * 997 + bird_index)
            birds.append(
                BirdSnapshot(
                    id=f"bird-{bird_index + 1:03d}",
                    x=round(x, 4),
                    y=round(y, 4),
                    heading=round((base_heading + t_s * 3.5 + math.sin(phase) * 20) % 360, 2),
                    truth_state=state,
                    predicted_abnormal=prediction_rng.random() < sensitivity,
                )
            )
        snapshots.append(PenSnapshot(t_s=t_s, birds=birds))

    first_clinical = next((point.t_s for point in timeline if point.clinical > 0), None)
    first_alert = next((point.t_s for point in timeline if point.alert), None)
    first_detection = next(
        (point.t_s for point in timeline if point.alert and first_clinical is not None and point.t_s >= first_clinical),
        None,
    )
    false_alerts = sum(1 for point in timeline if point.alert and (first_clinical is None or point.t_s < first_clinical))
    delay = None
    if first_clinical is not None and first_detection is not None:
        delay = float(first_detection - first_clinical)
    total_frames = round(scenario.duration_s * scenario.fps)
    dropped_frames = round(total_frames * 0.012)
    metrics = RunMetrics(
        detection_delay_s=delay,
        false_alerts=false_alerts,
        mean_fps=round(scenario.fps * 0.988, 3),
        p95_latency_ms=round(1000 / scenario.fps * 0.78, 3),
        dropped_frames=dropped_frames,
        alert_triggered=first_alert is not None,
    )
    return SimulationResult(timeline=timeline, snapshots=snapshots, metrics=metrics)
