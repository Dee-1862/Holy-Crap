"""Time ONNX models on the Pi with the same harness, for the paper's edge benchmark.

    python3 tools/bench_models.py model.onnx [model.onnx ...] --threads 1 4 --runs 50 --out bench.json

Each model gets 5 warm-up runs, then RUNS timed runs on a fixed random input of its own input size (read from the
file name: _224, _320 or _640). Reports median and 95th percentile wall time per run, inference only (no image
decoding or post-processing). Run it with the pipeline stopped, or the numbers include its load.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ortlite"))
from ortlite import Session  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--threads", type=int, nargs="+", default=[1, 4])
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--out", default="bench.json")
    a = ap.parse_args()
    rows = []
    for path in a.models:
        side = int(re.search(r"_(\d{3})\.onnx$", path).group(1))
        x = np.random.default_rng(0).random((1, 3, side, side), dtype=np.float32)
        for th in a.threads:
            s = Session(path, th)
            for _ in range(5):
                s.run(x)
            t = []
            for _ in range(a.runs):
                t0 = time.perf_counter()
                s.run(x)
                t.append((time.perf_counter() - t0) * 1000)
            del s
            r = {"model": os.path.basename(path), "input": side, "threads": th, "runs": a.runs,
                 "median_ms": round(float(np.median(t)), 1), "p95_ms": round(float(np.percentile(t, 95)), 1)}
            rows.append(r)
            print(r, flush=True)
    with open(a.out, "w") as f:
        json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
