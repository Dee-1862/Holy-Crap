"""Copy a small set of camera clips and their analysis into the console's public folder, for a deployed console.

    python app/live-feed/export_demo_media.py

The full media folder (about 1.5 GB) is never committed. A deployed console (Vercel) has no disk to read it from,
so the API falls back to these files: the A1 test clip (re-encoded smaller) and the two Big Broiler pens, about
20 MB, with their analysis. Licenses travel with them in the manifest (CC BY 4.0 and AGPL-3.0).
"""
from __future__ import annotations

import json
import shutil
import subprocess

from clips import MEDIA, REPO
from fetch_clips import ffmpeg

IDS = ["test-a1", "bb-093", "bb-101"]
OUT = REPO / "app" / "console" / "public" / "demo-media"


def main():
    (OUT / "clips").mkdir(parents=True, exist_ok=True)
    (OUT / "analysis").mkdir(parents=True, exist_ok=True)
    manifest = [c for c in json.loads((MEDIA / "clips.json").read_text()) if c["id"] in IDS]
    for c in manifest:
        src, dst = MEDIA / "clips" / f"{c['id']}.mp4", OUT / "clips" / f"{c['id']}.mp4"
        if c["id"] == "test-a1":                      # 3 minutes at 1280, re-encoded so it stays small enough for git
            subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(src), "-an", "-c:v", "libx264", "-preset", "slow",
                            "-crf", "31", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], check=True)
        else:
            shutil.copyfile(src, dst)
        c["bytes"] = dst.stat().st_size
        shutil.copyfile(MEDIA / "analysis" / f"{c['id']}.json", OUT / "analysis" / f"{c['id']}.json")
        print(f"{c['id']}: {c['bytes'] / 1e6:.1f} MB", flush=True)
    (REPO / "app" / "console" / "src" / "lib" / "demo-clips.json").write_text(json.dumps(manifest, indent=2))
    print("wrote", len(manifest), "clips")


if __name__ == "__main__":
    main()
