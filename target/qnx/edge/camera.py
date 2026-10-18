"""Camera section, replay version: plays recorded footage the same way the live capture (cam/hccam.c) works.

    python3 camera.py --mov /data/share/sensor/simulator_camera.barn.mov --rate 2    full resolution
    python3 camera.py --replay ../hc-replay/pen-wide.gray --rate 2                   small grey only

With --mov (raw ARGB QuickTime, as tools/make_gray.py or ffmpeg -c:v rawvideo -pix_fmt argb writes it)
each full frame goes into the shared memory ring that hccam uses, and only a small grey copy is sent on
to the spot finder. Later sections cut full resolution patches out of shared memory themselves, so no
big frame is copied between processes and nothing queues up.

If the spot finder is down the frame is counted as dropped and the camera keeps its pace.
"""
from __future__ import annotations

import argparse
import json
import struct
import time

import qnxipc

SMALL_W = 320


def mov_frames(path: str):
    """Frames of a raw ARGB .mov: find the media data atom and the frame size, then step through."""
    with open(path, "rb") as f:
        data_at = size = None
        w = h = 0
        pos = 0
        while True:
            f.seek(pos)
            head = f.read(16)
            if len(head) < 8:
                break
            n, kind = struct.unpack(">I4s", head[:8])
            if n == 1:
                n = struct.unpack(">Q", head[8:16])[0]
            if kind == b"mdat":
                hdr = 16 if head[:4] == b"\0\0\0\1" else 8
                data_at, size = pos + hdr, n - hdr
            elif kind == b"moov":
                f.seek(pos + 8)
                body = f.read(n - 8)
                k = body.find(b"stsd")                              # the video sample entry holds width and height
                w, h = struct.unpack(">HH", body[k + 44:k + 48])
            if n == 0:
                break
            pos += n
        frame = w * h * 4
        count = size // frame if data_at and frame else 0
        while True:
            for i in range(count):
                f.seek(data_at + i * frame)
                argb = f.read(frame)
                if len(argb) < frame:
                    break
                bgra = bytearray(frame)                           # A R G B -> B G R A, the live camera's order
                bgra[0::4], bgra[1::4], bgra[2::4], bgra[3::4] = argb[3::4], argb[2::4], argb[1::4], argb[0::4]
                yield w, h, bytes(bgra)


def gray_frames(path: str):
    with open(path, "rb") as f:
        _, w, h, fps, n = f.readline().split()
        start = f.tell()
        w, h, n = int(w), int(h), int(n)
        while True:
            f.seek(start)
            for _ in range(n):
                yield w, h, f.read(w * h)


def small_gray(bgra: bytes, w: int, h: int) -> tuple[bytes, int, int]:
    step = w // SMALL_W
    sh = h // step
    out = bytearray(SMALL_W * sh)
    for y in range(sh):
        row = bgra[y * step * w * 4:(y * step * w + w) * 4]
        b, g, r = row[0::4 * step], row[1::4 * step], row[2::4 * step]
        o = y * SMALL_W
        for x in range(SMALL_W):
            out[o + x] = (29 * b[x] + 150 * g[x] + 77 * r[x]) >> 8
    return bytes(out), SMALL_W, sh


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--mov")
    src.add_argument("--replay")
    ap.add_argument("--rate", type=float, default=2.0)
    args = ap.parse_args()
    ring = None
    if args.mov:
        from shm import Ring
        ring = Ring()
    spotter = None
    sent = dropped = 0
    period, next_t = 1 / args.rate, time.monotonic()
    frames = mov_frames(args.mov) if args.mov else gray_frames(args.replay)
    for k, (w, h, frame) in enumerate(frames):
        now = time.time()
        head = {"k": k, "t": now, "dropped": dropped, "source": "replay"}
        if ring:
            slot, seq = ring.write(frame, w, h, now)
            small, sw, sh = small_gray(frame, w, h)
            head.update(w=sw, h=sh, slot=slot, seq=seq, fullW=w, fullH=h, shm="/dev/shmem/hc-frames")
        else:
            small = frame
            head.update(w=w, h=h)
        data = json.dumps(head).encode()
        try:
            if spotter is None:
                spotter = qnxipc.Client("hc/spotter", wait=0)
            spotter.send(len(data).to_bytes(2, "little") + data + small)
            sent += 1
        except OSError:
            dropped += 1
            spotter = None
        next_t += period
        time.sleep(max(0.0, next_t - time.monotonic()))


if __name__ == "__main__":
    main()
