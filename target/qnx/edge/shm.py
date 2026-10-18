"""Read full resolution camera frames that hccam (cam/hccam.c) keeps in shared memory.

Each section cuts out only the part it needs, straight from the shared frame, so no full frame is
copied between processes and nothing queues up. Layout must match struct ring in hccam.c.
"""
from __future__ import annotations

import mmap
import os
import struct

PATH = "/dev/shmem/hc-frames"
HEAD = 4096
SLOT_HEAD_AT = 72                       # struct ring: 4 x u32, 2 x u64, 40 pad bytes, then the slot heads
SLOT_HEAD = 64                          # u64 seq, 4 x u32, i64 time, 32 pad bytes


class Frames:
    def __init__(self, path: str = PATH):
        fd = os.open(path, os.O_RDONLY)
        self.m = mmap.mmap(fd, os.fstat(fd).st_size, mmap.MAP_SHARED, mmap.PROT_READ)   # QNX needs the length
        os.close(fd)
        magic, self.slots, self.frame_bytes, _ = struct.unpack_from("<4I", self.m, 0)
        if magic != 0x31464348:
            raise ValueError("not an hccam frame ring")

    def head(self, slot: int) -> dict:
        seq, w, h, stride, ftype, t = struct.unpack_from("<Q4Iq", self.m, SLOT_HEAD_AT + slot * SLOT_HEAD)
        return {"seq": seq, "w": w, "h": h, "stride": stride, "type": ftype, "t": t / 1e9}

    def newest(self) -> int:
        return struct.unpack_from("<I", self.m, 12)[0]

    def counts(self) -> tuple[int, int]:
        return struct.unpack_from("<2Q", self.m, 16)

    def crop_rgb(self, slot: int, cx: float, cy: float, side: int) -> tuple[bytes, int] | None:
        """A side x side RGB patch centred on (cx, cy), given as shares of the frame. None if the slot changed."""
        hd = self.head(slot)
        w, h, stride = hd["w"], hd["h"], hd["stride"]
        side = min(side, w, h) & ~1
        x0 = max(0, min(w - side, int(cx * w) - side // 2)) & ~1     # even, so each pixel pair shares its chroma
        y0 = max(0, min(h - side, int(cy * h) - side // 2))
        base = HEAD + slot * self.frame_bytes
        if hd["type"] == 1:
            return self._crop_nv12(slot, hd, base, x0, y0, side)
        bpp = stride // w
        yo = self.y_offset(slot) if bpp == 2 else 0
        # copy the raw rows first, which is quick, then check the camera did not reuse the slot meanwhile
        rows = [self.m[base + y * stride + x0 * bpp: base + y * stride + (x0 + side) * bpp] for y in range(y0, y0 + side)]
        if self.head(slot)["seq"] != hd["seq"]:
            return None
        if hd["type"] == 31:                         # Camera Module 3: B G R A, just reorder
            out = bytearray(side * side * 3)
            for k, row in enumerate(rows):
                o = k * side * 3
                out[o:o + side * 3:3], out[o + 1:o + side * 3:3], out[o + 2:o + side * 3:3] = row[2::4], row[1::4], row[0::4]
            return bytes(out), side
        out = bytearray(side * side * 3)
        k = 0
        for row in rows:
            for x in range(0, side * 2, 4):          # 4 bytes hold 2 pixels: Y0 U Y1 V (or U Y0 V Y1)
                if yo == 0:
                    y0_, u, y1_, v = row[x], row[x + 1], row[x + 2], row[x + 3]
                else:
                    u, y0_, v, y1_ = row[x], row[x + 1], row[x + 2], row[x + 3]
                d, e = u - 128, v - 128
                for yy in (y0_, y1_):
                    c = 298 * (yy - 16) + 128
                    out[k] = max(0, min(255, (c + 409 * e) >> 8))
                    out[k + 1] = max(0, min(255, (c - 100 * d - 208 * e) >> 8))
                    out[k + 2] = max(0, min(255, (c + 516 * d) >> 8))
                    k += 3
        return bytes(out), side

    def _crop_nv12(self, slot: int, hd: dict, base: int, x0: int, y0: int, side: int) -> tuple[bytes, int] | None:
        """NV12, as the Camera Module 3 sends it: luma rows, then half height rows of interleaved U V."""
        w, h = hd["w"], hd["h"]
        y0 &= ~1                                      # even, so each pair of rows shares its chroma row
        ys = [self.m[base + y * w + x0: base + y * w + x0 + side] for y in range(y0, y0 + side)]
        uvs = [self.m[base + (h + y) * w + x0: base + (h + y) * w + x0 + side] for y in range(y0 // 2, (y0 + side) // 2)]
        if self.head(slot)["seq"] != hd["seq"]:
            return None
        out = bytearray(side * side * 3)
        k = 0
        for r, row in enumerate(ys):
            uv = uvs[r // 2]
            for x in range(side):
                d, e = uv[x & ~1] - 128, uv[x | 1] - 128
                c = 298 * (row[x] - 16) + 128
                out[k] = max(0, min(255, (c + 409 * e) >> 8))
                out[k + 1] = max(0, min(255, (c - 100 * d - 208 * e) >> 8))
                out[k + 2] = max(0, min(255, (c + 516 * d) >> 8))
                k += 3
        return bytes(out), side

    def y_offset(self, slot: int) -> int:
        """0 when luma comes first (YUYV), 1 when chroma does (UYVY). Luma varies far more."""
        if not hasattr(self, "_yo"):
            base = HEAD + slot * self.frame_bytes
            hd = self.head(slot)
            row = self.m[base + (hd["h"] // 2) * hd["stride"]: base + (hd["h"] // 2) * hd["stride"] + hd["stride"]]
            even = sum((b - 128) ** 2 for b in row[0::2])
            odd = sum((b - 128) ** 2 for b in row[1::2])
            self._yo = 1 if odd > even else 0
        return self._yo


class Ring:
    """Writer side, the same layout hccam.c creates, for the replay camera. Frames are stored as B G R A."""

    SLOTS = 4
    FRAME_BYTES = 2304 * 1296 * 4

    def __init__(self, path: str = PATH):
        size = HEAD + self.SLOTS * self.FRAME_BYTES
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        os.ftruncate(fd, size)
        self.m = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        os.close(fd)
        self.m[:HEAD] = bytes(HEAD)
        struct.pack_into("<4I2Q", self.m, 0, 0x31464348, self.SLOTS, self.FRAME_BYTES, 0, 0, 0)
        self.newest = 0
        self.frames = 0

    def write(self, bgra: bytes, w: int, h: int, t: float) -> tuple[int, int]:
        """Store one frame in the next slot. Returns (slot, sequence number)."""
        i = (self.newest + 1) % self.SLOTS
        at = SLOT_HEAD_AT + i * SLOT_HEAD
        seq = struct.unpack_from("<Q", self.m, at)[0]
        struct.pack_into("<Q", self.m, at, seq + 1)                  # odd while writing
        base = HEAD + i * self.FRAME_BYTES
        self.m[base:base + len(bgra)] = bgra
        struct.pack_into("<Q4Iq", self.m, at, seq + 2, w, h, w * 4, 31, int(t * 1e9))
        self.newest = i
        self.frames += 1
        struct.pack_into("<IQ", self.m, 12, i, self.frames)
        return i, seq + 2
