#!/usr/bin/env python3
"""Run the checked-in ctypes bridge against one preprocessed real specimen."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--ortlite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.ortlite))
    from ortlite import Session

    tensor = np.fromfile(args.input, dtype=np.float32).reshape(1, 3, 320, 320)
    load_started = time.perf_counter_ns()
    session = Session(str(args.model), threads=4)
    load_ms = (time.perf_counter_ns() - load_started) / 1_000_000
    session.run(tensor)
    elapsed_ms: list[float] = []
    output = None
    for _ in range(5):
        started = time.perf_counter_ns()
        output = session.run(tensor)
        elapsed_ms.append((time.perf_counter_ns() - started) / 1_000_000)
    assert output is not None
    np.ascontiguousarray(output, np.float32).tofile(args.output)
    result = {
        "runtime": "QNX libonnxruntime through checked-in libhcort/ortlite",
        "model_sha256": sha256(args.model),
        "input_shape": list(tensor.shape),
        "input_sha256": sha256(args.input),
        "output_shape": list(output.shape),
        "output_sha256": sha256(args.output),
        "output_elements": int(output.size),
        "output_min": float(output.min()),
        "output_max": float(output.max()),
        "load_ms": load_ms,
        "timings_ms": elapsed_ms,
        "timing_mean_ms": statistics.fmean(elapsed_ms),
    }
    args.result.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
