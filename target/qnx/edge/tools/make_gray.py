"""Turn a video into a raw grey frame file that the Pi can replay without any video decoder.

Runs on the laptop (needs OpenCV). The file is a one line text header, then frames of width*height bytes:

    HCGRAY <width> <height> <frames per second> <frame count>\\n

    python target/qnx/edge/tools/make_gray.py app/console/media/clips/pen-wide.mp4 pen-wide.gray --rate 2
"""
from __future__ import annotations

import argparse

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--rate", type=float, default=2.0, help="frames per second to keep")
    ap.add_argument("--seconds", type=float, default=0, help="stop after this much video, 0 for all")
    args = ap.parse_args()
    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, round(fps / args.rate))
    frames, i = [], 0
    while True:
        ok = cap.grab()
        if not ok or (args.seconds and i / fps > args.seconds):
            break
        if i % step == 0:
            ok, f = cap.retrieve()
            if ok:
                h = round(f.shape[0] * args.width / f.shape[1])
                frames.append(cv2.cvtColor(cv2.resize(f, (args.width, h), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).tobytes())
        i += 1
    with open(args.out, "wb") as out:
        out.write(f"HCGRAY {args.width} {h} {fps / step:g} {len(frames)}\n".encode())
        for b in frames:
            out.write(b)
    print(f"{args.out}: {len(frames)} frames of {args.width}x{h} at {fps / step:g} per second")


if __name__ == "__main__":
    main()
