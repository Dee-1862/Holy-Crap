"""Find small things that appeared on the floor and then stayed still. Standard library only.

The Pi has Python but no numpy or OpenCV, so this works on bytes with plain loops at low resolution
(320 by 180 by default, about 58 thousand pixels a frame).

Method, two running backgrounds of the grey image:
- slow   follows the scene over minutes, so it still shows the floor as it was
- fast   follows it over a few seconds, so it already shows anything new that has stopped moving
A pixel is a candidate when fast differs from slow (something new is there) and the current frame
matches fast (it is not moving right now). Birds walk, so they rarely pass the second test for long.
The floor background starts as the median of the first `init` frames, so birds that were standing in
the first frame do not leave ghosts. Rows covered by camera overlay text (the clock) are ignored.
A candidate has to hold for `hold` frames in a row, then neighbouring pixels are grouped, and only
groups the size of a dropping (a few pixels at this scale) are reported. A hen that sits still is
too big and is dropped by the size limit. Two more checks on the ring of pixels just around a group:
the ring must still look like the old floor (so the group is isolated, not the edge of a bird), and the
group must stand out from that ring now (so it is not a ghost left where a resting bird got up). This finds new still spots, it does not know what they
are. The laptop or a person decides that from the crop.
"""
from __future__ import annotations

from array import array

SHIFT = 4                     # backgrounds are kept times 16 so integer updates stay smooth


class StillSpots:
    def __init__(self, width: int, height: int, slow: int = 9, fast: int = 2, new_diff: int = 22,
                 move_diff: int = 10, hold: int = 20, min_area: int = 3, max_area: int = 40, init: int = 15,
                 ignore_rows: tuple[float, float] = (0.07, 0.07), contrast: int = 14, ring_floor: float = 0.75):
        self.w, self.h = width, height
        self.slow_k, self.fast_k = slow, fast                # update rates are 1 / 2**k per frame
        self.new_diff, self.move_diff = new_diff << SHIFT, move_diff
        self.hold, self.min_area, self.max_area = hold, min_area, max_area
        self.init = init
        self.contrast, self.ring_floor = contrast, ring_floor
        self.start = int(height * ignore_rows[0]) * width               # first pixel looked at
        self.stop = (height - int(height * ignore_rows[1])) * width     # first pixel past the end
        self.first: list[bytes] = []
        n = width * height
        self.slow = array("i", bytes(4 * n))
        self.fast = array("i", bytes(4 * n))
        self.age = bytearray(n)                              # frames in a row a pixel has been a candidate
        self.frames = 0
        self.reported: list[tuple[int, int]] = []

    def update(self, gray: bytes) -> list[dict]:
        """Feed one grey frame (width*height bytes). Returns spots that just became reportable."""
        n = self.w * self.h
        if len(gray) != n:
            raise ValueError(f"frame has {len(gray)} bytes, expected {n}")
        slow, fast, age = self.slow, self.fast, self.age
        self.frames += 1
        if self.frames <= self.init:                         # collect frames for the starting floor
            self.first.append(bytes(gray))
            if self.frames == self.init:
                mid = len(self.first) // 2
                for i in range(n):
                    slow[i] = sorted(f[i] for f in self.first)[mid] << SHIFT
                    fast[i] = gray[i] << SHIFT
                self.first = []
            return []
        sk, fk, nd, md, hold = self.slow_k, self.fast_k, self.new_diff, self.move_diff, self.hold
        hot = []
        for i in range(self.start, self.stop):
            g = gray[i] << SHIFT
            f = fast[i] + ((g - fast[i]) >> fk)
            fast[i] = f
            s = slow[i]
            if abs(f - s) > nd and abs(g - f) >> SHIFT < md:
                a = age[i]
                if a < 255:
                    age[i] = a + 1
                if a + 1 >= hold:
                    hot.append(i)
                if a >= 250:                                 # long reported, let the floor take it in
                    slow[i] = s + ((g - s) >> sk)
            else:
                age[i] = 0
                slow[i] = s + ((g - s) >> sk)                # only learn the floor where nothing new sits
        return self._groups(hot, gray) if hot else []

    def _isolated(self, pix: list[int], gray: bytes) -> bool:
        """True when the ring around the group is unchanged floor and the group contrasts with it."""
        w, h, slow, md = self.w, self.h, self.slow, self.move_diff * 2
        xs = [p % w for p in pix]
        ys = [p // w for p in pix]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        ring, floor = [], 0
        for y in range(max(0, y0 - 4), min(h, y1 + 5)):
            for x in range(max(0, x0 - 4), min(w, x1 + 5)):
                if x0 - 2 <= x <= x1 + 2 and y0 - 2 <= y <= y1 + 2:
                    continue
                i = y * w + x
                ring.append(gray[i])
                if abs((gray[i] << SHIFT) - slow[i]) >> SHIFT < md:
                    floor += 1
        if not ring or floor < self.ring_floor * len(ring):
            return False
        inside = sum(gray[p] for p in pix) / len(pix)
        return abs(inside - sum(ring) / len(ring)) > self.contrast

    def _groups(self, hot: list[int], gray: bytes) -> list[dict]:
        w = self.w
        todo = set(hot)
        out = []
        while todo:
            seed = todo.pop()
            stack, pix = [seed], [seed]
            while stack:
                p = stack.pop()
                x = p % w
                for q in (p - 1 if x else -1, p + 1 if x < w - 1 else -1, p - w, p + w):
                    if q in todo:
                        todo.remove(q)
                        stack.append(q)
                        pix.append(q)
            if not self.min_area <= len(pix) <= self.max_area or not self._isolated(pix, gray):
                continue
            xs = [p % w for p in pix]
            ys = [p // w for p in pix]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            if any(abs(cx - rx) < 4 and abs(cy - ry) < 4 for rx, ry in self.reported):
                continue
            self.reported.append((cx, cy))
            out.append({"x": min(xs), "y": min(ys), "w": max(xs) - min(xs) + 1, "h": max(ys) - min(ys) + 1,
                        "area": len(pix), "cx": round(cx / w, 4), "cy": round(cy / self.h, 4)})
        return out

    def crop(self, gray: bytes, spot: dict, side: int = 24) -> bytes:
        """A side by side grey patch around a spot, for the dashboard to show."""
        x0 = max(0, min(self.w - side, spot["x"] + spot["w"] // 2 - side // 2))
        y0 = max(0, min(self.h - side, spot["y"] + spot["h"] // 2 - side // 2))
        return b"".join(gray[(y0 + r) * self.w + x0:(y0 + r) * self.w + x0 + side] for r in range(side))
