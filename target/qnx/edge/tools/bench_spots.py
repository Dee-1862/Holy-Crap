"""Time stillspot on a replay file and count what it flags.   python3 tools/bench_spots.py FILE.gray"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from stillspot import StillSpots  # noqa: E402

with open(sys.argv[1], "rb") as f:
    _, w, h, fps, n = f.readline().split()
    w, h, n = int(w), int(h), int(n)
    d, spots, t0 = StillSpots(w, h), 0, time.perf_counter()
    for _ in range(n):
        spots += len(d.update(f.read(w * h)))
dt = (time.perf_counter() - t0) / n
print(f"{os.path.basename(sys.argv[1])}: {n} frames {w}x{h}, {dt * 1000:.1f} ms a frame, {spots} spots")
