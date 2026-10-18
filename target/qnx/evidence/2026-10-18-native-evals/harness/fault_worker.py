#!/system/bin/python3
"""Disposable worker used only by the isolated QNX recovery evaluation."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def write_atomic(path: Path, payload: dict[str, int | str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: fault_worker.py READY_PATH RESULT_PATH GENERATION", file=sys.stderr)
        return 64
    ready_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    generation = int(sys.argv[3])
    write_atomic(
        ready_path,
        {"event": "ready", "generation": generation, "pid": os.getpid(), "monotonic_ns": time.monotonic_ns()},
    )
    sequence = 0
    while True:
        sequence += 1
        write_atomic(
            result_path,
            {
                "event": "result",
                "generation": generation,
                "pid": os.getpid(),
                "sequence": sequence,
                "monotonic_ns": time.monotonic_ns(),
            },
        )
        time.sleep(0.02)


if __name__ == "__main__":
    raise SystemExit(main())

