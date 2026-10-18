"""Small JPEG of the newest camera frame, for the site's live camera view (colour, or grey with grey=True).

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


def encode(img: np.ndarray, quality: int = 70) -> bytes:
    """RGB (h, w, 3) or grey (h, w) to JPEG."""
    tj, handle = _lib()
    img = np.ascontiguousarray(img, dtype=np.uint8)
    h, w = img.shape[:2]
    grey = img.ndim == 2
    out, size = ctypes.POINTER(ctypes.c_ubyte)(), ctypes.c_ulong(0)
    # pixel format 0 is RGB with subsampling 2 (4:2:0); pixel format 6 is GRAY with subsampling 3 (grey)
    pf, pitch, sub = (6, w, 3) if grey else (0, w * 3, 2)
    if tj.tjCompress2(handle, img.ctypes.data, w, pitch, h, pf, ctypes.byref(out), ctypes.byref(size), sub, quality, 0):
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


def frame_grey(frames: Frames, step: int = 4) -> tuple[np.ndarray, dict] | None:
    """The newest frame scaled down by step, grey only. For the live view: no colour conversion, and NV12's luma
    plane is already the grey picture. The models never use this; they cut colour patches with shm.crop_rgb."""
    slot = frames.newest()
    hd = frames.head(slot)
    w, h = hd["w"], hd["h"]
    if not w or not h:
        return None
    base = HEAD + slot * frames.frame_bytes
    if hd["type"] == 1:                                   # NV12: the luma plane is the grey picture
        grey = np.frombuffer(frames.m, np.uint8, w * h, base).reshape(h, w)[::step, ::step].copy()
    elif hd["type"] == 31:                                # B G R A: integer luma, same weights as hccam.c
        bgra = np.frombuffer(frames.m, np.uint8, w * h * 4, base).reshape(h, w, 4)[::step, ::step].astype(np.uint16)
        grey = ((29 * bgra[..., 0] + 150 * bgra[..., 1] + 77 * bgra[..., 2]) >> 8).astype(np.uint8)
    else:
        return None
    if frames.head(slot)["seq"] != hd["seq"]:
        return None
    return grey, hd


def enhance(img: np.ndarray, sharpen: float = 0.6) -> np.ndarray:
    """For people looking at the live view only, never for model input (the models were trained on plain frames).
    Auto levels per channel (1st to 99th percentile, which also evens out a colour cast from barn lighting), then a
    light unsharp mask. Plain numpy, a few ms at 384 by 216 on the Pi."""
    f = img.astype(np.float32)
    chans = f[..., None] if f.ndim == 2 else f
    sample = chans[::4, ::4]                              # percentiles from every 4th pixel: same levels, much faster
    lo = np.percentile(sample, 1, axis=(0, 1))
    hi = np.percentile(sample, 99, axis=(0, 1))
    chans = (chans - lo) * (255.0 / np.maximum(hi - lo, 1.0))
    if sharpen:
        # 3x3 box blur by shifted sums, then add back the detail it removed
        p = np.pad(chans, ((1, 1), (1, 1), (0, 0)), mode="edge")
        h, w = chans.shape[:2]
        blur = sum(p[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3)) / 9.0
        chans = chans + sharpen * (chans - blur)
    out = np.clip(chans, 0, 255).astype(np.uint8)
    return out[..., 0] if f.ndim == 2 else out


def snapshot(frames: Frames, step: int = 4, quality: int = 70, grey: bool = False,
             enhanced: bool = False) -> tuple[bytes, dict] | None:
    take = frame_grey if grey else frame_rgb
    for _ in range(3):
        got = take(frames, step)
        if got:
            return encode(enhance(got[0]) if enhanced else got[0], quality), got[1]
    return None


if __name__ == "__main__":
    jpg, hd = snapshot(Frames(), grey="--grey" in sys.argv)
    open(sys.argv[1], "wb").write(jpg)
    print("wrote", len(jpg), "bytes from", hd)
