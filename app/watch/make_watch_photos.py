"""Shrink the specimen photos to the watch's photo box, so the watch can fetch the real photo over Wi-Fi.

    python app/watch/make_watch_photos.py

Reads app/console/public/specimens/E-*.jpg (made by app/live-feed/make_specimen_photos.py) and writes
180 by 135 baseline JPEGs to app/console/public/watch/. Baseline, not progressive, because the watch's
JPEG decoder only reads baseline. Each one is a few kilobytes, small enough for one https request.
"""
from pathlib import Path

from PIL import Image

CONSOLE = Path(__file__).resolve().parents[1] / "console" / "public"
SRC, OUT = CONSOLE / "specimens", CONSOLE / "watch"
W, H = 180, 135

OUT.mkdir(exist_ok=True)
for f in sorted(SRC.glob("E-*.jpg")):
    im = Image.open(f).convert("RGB")
    scale = max(W / im.width, H / im.height)                  # fill the box, then crop the middle
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    x, y = (im.width - W) // 2, (im.height - H) // 2
    im.crop((x, y, x + W, y + H)).save(OUT / f.name, quality=82, progressive=False, optimize=True)
    print(f.name, (OUT / f.name).stat().st_size, "bytes")
