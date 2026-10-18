"""Small colour JPEG of the newest camera frame, for the site's live camera view.

Reads the frame ring hccam (cam/hccam.c) or the replay camera keeps in shared memory, scales it down with numpy
and encodes it with libturbojpeg through ctypes (the library is on the image, its headers are not).
    python3 livejpeg.py out.jpg
"""
from __future__ import annotations

import ctypes
import sys

import numpy as np

from shm import HEAD, Frames

_tj = None


def _lib():
    global _tj
    if _tj is None:
        tj = ctypes.CDLL("libturbojpeg.so.0")
        tj.tjInitCompress.restype = ctypes.c_void_p
        tj.tjCompress2.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)), ctypes.POINTER(ctypes.c_ulong),
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int]
        tj.tjFree.argtypes = [ctypes.c_void_p]
        _tj = (tj, tj.tjInitCompress())
    return _tj


def encode(rgb: np.ndarray, quality: int = 70) -> bytes:
    tj, handle = _lib()
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    h, w, _ = rgb.shape
    out, size = ctypes.POINTER(ctypes.c_ubyte)(), ctypes.c_ulong(0)
    # pixel format 0 is RGB, subsampling 2 is 4:2:0
    if tj.tjCompress2(handle, rgb.ctypes.data, w, w * 3, h, 0, ctypes.byref(out), ctypes.byref(size), 2, quality, 0):
        raise RuntimeError("jpeg encode failed")
    data = ctypes.string_at(out, size.value)
    tj.tjFree(out)
    return data


def frame_rgb(frames: Frames, step: int = 4) -> tuple[np.ndarray, dict] | None:
    """The newest frame scaled down by step (even), as RGB. None if the camera reused the slot while reading."""
    slot = frames.newest()
    hd = frames.head(slot)
    w, h = hd["w"], hd["h"]
    if not w or not h:
        return None
    base = HEAD + slot * frames.frame_bytes
    if hd["type"] == 1:                                   # NV12: luma plane, then half height U V rows
        y = np.frombuffer(frames.m, np.uint8, w * h, base).reshape(h, w)[::step, ::step].astype(np.float32)
        uv = np.frombuffer(frames.m, np.uint8, w * h // 2, base + w * h).reshape(h // 2, w // 2, 2)
        uv = uv[::step // 2, ::step // 2].astype(np.float32) - 128
        y, uv = y[:uv.shape[0], :uv.shape[1]], uv[:y.shape[0], :y.shape[1]]
        c = 1.164 * (y - 16)
        rgb = np.stack([c + 1.596 * uv[..., 1], c - 0.392 * uv[..., 0] - 0.813 * uv[..., 1], c + 2.017 * uv[..., 0]], -1)
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    elif hd["type"] == 31:                                # B G R A
        rgb = np.frombuffer(frames.m, np.uint8, w * h * 4, base).reshape(h, w, 4)[::step, ::step, 2::-1].copy()
    else:
        return None
    if frames.head(slot)["seq"] != hd["seq"]:
        return None
    return rgb, hd


def snapshot(frames: Frames, step: int = 4, quality: int = 70) -> tuple[bytes, dict] | None:
    for _ in range(3):
        got = frame_rgb(frames, step)
        if got:
            return encode(got[0], quality), got[1]
    return None


if __name__ == "__main__":
    jpg, hd = snapshot(Frames())
    open(sys.argv[1], "wb").write(jpg)
    print("wrote", len(jpg), "bytes from", hd)
