"""Camera process: sends grey frames to the spot finder at a steady rate.

    python3 camera.py --replay ../hc-replay/pen-wide.gray --rate 2

Only replay is wired up so far. Frames come from a file made by tools/make_gray.py, looped. Live capture
from the Camera Module 3 goes through the QNX Sensor Framework (/dev/sensor/camera1), which has a C API
and no Python binding, so it will be a small C program that sends frames the same way.

If the spot finder is down, the frame is counted as dropped and the camera keeps its pace. It does not
block or crash, which is the point of keeping them in separate processes.
"""
from __future__ import annotations

import argparse
import json
import time

import qnxipc


def frames(path: str):
    with open(path, "rb") as f:
        _, w, h, fps, n = f.readline().split()
        start = f.tell()
        w, h, n = int(w), int(h), int(n)
        while True:
            f.seek(start)
            for _ in range(n):
                yield w, h, f.read(w * h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--rate", type=float, default=2.0)
    args = ap.parse_args()
    spotter = None
    sent = dropped = 0
    period, next_t = 1 / args.rate, time.monotonic()
    for k, (w, h, frame) in enumerate(frames(args.replay)):
        head = json.dumps({"k": k, "w": w, "h": h, "t": time.time(), "dropped": dropped}).encode()
        try:
            if spotter is None:
                spotter = qnxipc.Client("hc/spotter", wait=0)
            spotter.send(len(head).to_bytes(2, "little") + head + frame)
            sent += 1
        except OSError:
            dropped += 1
            spotter = None
        next_t += period
        time.sleep(max(0.0, next_t - time.monotonic()))


if __name__ == "__main__":
    main()
