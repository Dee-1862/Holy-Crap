#!/usr/bin/env python3
"""Build pooled scheduler-control statistics from the preserved raw trials."""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def scenario_from_name(name: str) -> str:
    return name.removeprefix("jitter-").split("-trial", 1)[0]


def main() -> None:
    documents: dict[str, list[dict[str, object]]] = {}
    for path in sorted(RAW.glob("*.json")):
        if path.name.endswith(".original.json"):
            continue
        scenario = scenario_from_name(path.stem)
        documents.setdefault(scenario, []).append(json.loads(path.read_text(encoding="utf-8")))

    output: dict[str, object] = {
        "suite": "linux_scheduler_wakeup_jitter_control",
        "benchmark_cpu": 3,
        "iterations_per_trial": 5000,
        "period_us": 1000,
        "deadline_lateness_threshold_us": 100,
        "trials_per_scenario": 5,
        "address_space_limit_bytes": 8 * 1024 * 1024 * 1024,
        "scenarios": {},
    }
    rows: list[dict[str, object]] = []
    scenarios = output["scenarios"]
    assert isinstance(scenarios, dict)
    for scenario, trials in sorted(documents.items()):
        pooled: list[float] = []
        misses = 0
        trial_p99: list[float] = []
        trial_max: list[float] = []
        for trial in trials:
            misses += int(trial["deadline_misses"])
            lateness = trial["lateness_us"]
            assert isinstance(lateness, dict)
            trial_p99.append(float(lateness["p99"]))
            trial_max.append(float(lateness["max"]))
        for path in sorted(RAW.glob(f"jitter-{scenario}-trial*.csv")):
            with path.open(newline="", encoding="utf-8") as handle:
                pooled.extend(float(row["lateness_us"]) for row in csv.DictReader(handle))
        policies = sorted({str(trial["scheduler_policy"]) for trial in trials})
        priorities = sorted({int(trial["priority"]) for trial in trials})
        record = {
            "trials": len(trials),
            "total_wakes": len(pooled),
            "scheduler_policies_observed": policies,
            "priorities_observed": priorities,
            "pooled_lateness_us": {
                "mean": round(statistics.fmean(pooled), 3),
                "p50": round(percentile(pooled, 0.50), 3),
                "p95": round(percentile(pooled, 0.95), 3),
                "p99": round(percentile(pooled, 0.99), 3),
                "max": round(max(pooled), 3),
            },
            "deadline_misses": misses,
            "deadline_miss_rate": round(misses / len(pooled), 9),
            "between_trial_p99_us": {
                "min": round(min(trial_p99), 3),
                "median": round(statistics.median(trial_p99), 3),
                "max": round(max(trial_p99), 3),
            },
            "between_trial_max_us": {
                "min": round(min(trial_max), 3),
                "median": round(statistics.median(trial_max), 3),
                "max": round(max(trial_max), 3),
            },
        }
        scenarios[scenario] = record
        pooled_stats = record["pooled_lateness_us"]
        assert isinstance(pooled_stats, dict)
        rows.append(
            {
                "scenario": scenario,
                "policy": "+".join(policies),
                "priority": "+".join(str(value) for value in priorities),
                "wakes": len(pooled),
                "mean_us": pooled_stats["mean"],
                "p50_us": pooled_stats["p50"],
                "p95_us": pooled_stats["p95"],
                "p99_us": pooled_stats["p99"],
                "max_us": pooled_stats["max"],
                "deadline_misses": misses,
                "deadline_miss_rate": record["deadline_miss_rate"],
            }
        )

    (ROOT / "summary.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (ROOT / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
