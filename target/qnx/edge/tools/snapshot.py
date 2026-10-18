"""Save the newest camera frame from shared memory as a PPM (full colour) and a small crop.   python3 tools/snapshot.py out.ppm"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from shm import Frames  # noqa: E402

f = Frames()
i = f.newest()
hd = f.head(i)
print("frames", f.counts(), "slot", i, hd)
side = min(hd["w"], hd["h"])
rgb, side = f.crop_rgb(i, 0.5, 0.5, side)
with open(sys.argv[1], "wb") as out:
    out.write(f"P6 {side} {side} 255\n".encode() + rgb)
print("wrote", side, "square from the centre")
