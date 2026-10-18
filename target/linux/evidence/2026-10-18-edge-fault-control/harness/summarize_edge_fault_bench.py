"""Summarize raw Linux control benchmark artifacts without overstating QNX."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import statistics


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def quantile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * share
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def phase_summary(samples: list[dict]) -> dict:
    statuses = [sample["status"] for sample in samples if sample.get("status")]
    rss = [sample["aggregateRssBytes"] for sample in samples]
    stage_bytes = [sample["stageFileBytes"] for sample in samples]
    combined_bytes = [sample["combinedRssAndStageFileBytes"] for sample in samples]
    temperatures = [sample["temperatureC"] for sample in samples if sample.get("temperatureC") is not None]
    queue_lines = [sample["cloudQueueLines"] for sample in samples]
    process_cpu: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        status = sample.get("status") or {}
        by_pid = {
            str(details.get("pid")): name
            for name, details in (status.get("procs") or {}).items()
            if details.get("pid")
        }
        for pid, value in sample.get("perPidCpuPercent", {}).items():
            process_cpu[by_pid.get(pid, f"pid:{pid}")].append(value)
    first, last = (statuses[0], statuses[-1]) if statuses else ({}, {})
    capture = last.get("captureTiming") or {}
    model = last.get("modelStats") or {}
    return {
        "samples": len(samples),
        "durationMonotonicMs": round((samples[-1]["monotonicNs"] - samples[0]["monotonicNs"]) / 1e6, 3)
        if len(samples) >= 2
        else None,
        "framesDelta": (last.get("frames") - first.get("frames"))
        if isinstance(last.get("frames"), int) and isinstance(first.get("frames"), int)
        else None,
        "dropsDelta": (last.get("dropped") - first.get("dropped"))
        if isinstance(last.get("dropped"), int) and isinstance(first.get("dropped"), int)
        else None,
        "endingFps": last.get("fps"),
        "endingCaptureWindow": capture,
        "endingModelStats": model,
        "aggregateRssBytes": {
            "mean": round(statistics.fmean(rss), 3) if rss else None,
            "p95": round(quantile(rss, 0.95), 3) if rss else None,
            "max": max(rss) if rss else None,
        },
        "stageFileBytes": {
            "mean": round(statistics.fmean(stage_bytes), 3) if stage_bytes else None,
            "max": max(stage_bytes) if stage_bytes else None,
        },
        "combinedRssAndStageFileBytes": {
            "mean": round(statistics.fmean(combined_bytes), 3) if combined_bytes else None,
            "p95": round(quantile(combined_bytes, 0.95), 3) if combined_bytes else None,
            "max": max(combined_bytes) if combined_bytes else None,
        },
        "temperatureC": {
            "min": min(temperatures) if temperatures else None,
            "mean": round(statistics.fmean(temperatures), 3) if temperatures else None,
            "max": max(temperatures) if temperatures else None,
        },
        "cloudQueueLinesMax": max(queue_lines) if queue_lines else None,
        "perProcessCpuPercent": {
            name: {
                "mean": round(statistics.fmean(values), 3),
                "p95": round(quantile(values, 0.95), 3),
                "max": max(values),
            }
            for name, values in sorted(process_cpu.items())
            if values
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    samples = read_jsonl(args.results / "samples.jsonl")
    faults = read_jsonl(args.results / "fault-tests.jsonl")
    by_phase: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        by_phase[sample.get("phase", "unknown")].append(sample)
    summary = {
        "claimBoundary": "Linux TCP fallback and application supervisor; not QNX evidence",
        "phases": {phase: phase_summary(rows) for phase, rows in sorted(by_phase.items())},
        "faultTests": [
            {
                "regime": fault.get("regime"),
                "process": fault.get("process"),
                "oldPid": fault.get("oldPid"),
                "newPid": fault.get("newPid"),
                "rawFaultEvent": fault.get("rawFaultEvent"),
                "externalMonotonic": fault.get("externalMonotonic"),
                "unrelatedPidChanges": fault.get("unrelatedPidChanges"),
                "applicationReadyAt": fault.get("applicationReadyAt"),
                "applicationFirstResultAt": fault.get("applicationFirstResultAt"),
                "applicationRecoveryMs": fault.get("applicationRecoveryMs"),
            }
            for fault in faults
        ],
        "guard": {
            "aggregateThresholdWasExceeded": any(
                event.get("kind") == "aggregate-memory-abort"
                for event in read_jsonl(args.results / "events.jsonl")
            )
        },
    }
    output = args.results / "summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
