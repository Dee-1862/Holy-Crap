"""Low-priority, affinity-bounded CPU load for the disposable benchmark."""
from __future__ import annotations

import argparse
import os
import signal


running = True


def stop(_signum: int, _frame: object) -> None:
    global running
    running = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", type=int, required=True)
    args = parser.parse_args()
    os.nice(19)
    os.sched_setaffinity(0, {args.cpu})
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    value = 0x12345678
    while running:
        for _ in range(250_000):
            value = ((value << 5) - value + 0x9E3779B9) & 0xFFFFFFFF
    print(value, flush=True)


if __name__ == "__main__":
    main()
