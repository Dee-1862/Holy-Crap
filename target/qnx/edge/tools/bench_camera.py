"""Benchmark the camera path on the Pi: live view colour vs grey, and how many full frames hccam copies.

Run while the pipeline (or just cam/hccam) is running:
    python3 tools/bench_camera.py            # 40 pictures each way + 10 s of frame counting

Prints, for the live view JPEG (step 6, quality 70, like sitelink.py):
    colour: ms per picture, bytes per picture
    grey:   ms per picture, bytes per picture
and how many full frames a second hccam copied into shared memory (30 before the -c change, about 8 after).
Compare the hccam CPU share before and after with `hogs -i 5` or `top`.
"""
from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import livejpeg  # noqa: E402
from shm import Frames  # noqa: E402

N = 40


def bench(frames: Frames, grey: bool, enhanced: bool = False) -> tuple[float, float]:
    ms, sizes = [], []
    for _ in range(N):
        t = time.perf_counter()
        got = livejpeg.snapshot(frames, step=6, quality=70, grey=grey, enhanced=enhanced)
        if got:
            ms.append((time.perf_counter() - t) * 1000)
            sizes.append(len(got[0]))
        time.sleep(0.05)
    return statistics.median(ms), statistics.median(sizes)


def main() -> None:
    frames = Frames()
    for grey in (False, True):
        for enhanced in (False, True):
            ms, size = bench(frames, grey, enhanced)
            name = ("grey" if grey else "colour") + (" + enhance" if enhanced else "")
            print(f"{name:17s} live view: {ms:6.1f} ms per picture, {size / 1024:6.1f} KB per picture")
    copied0, _ = frames.counts()
    time.sleep(10)
    copied1, _ = frames.counts()
    print(f"hccam full frames copied into shared memory: {(copied1 - copied0) / 10:.1f} a second")


if __name__ == "__main__":
    main()
