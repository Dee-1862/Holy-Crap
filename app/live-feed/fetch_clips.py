"""Download the live feed clips, verify them, and copy the playable files to app/console/media/clips.

    python app/live-feed/fetch_clips.py

Needs network once. Safe to rerun: files that already match are skipped.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from clips import CLIPS, MEDIA, RAW


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ffmpeg() -> str:
    """imageio-ffmpeg ships a build with H.264, otherwise fall back to ffmpeg on PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def to_web_mp4(src: Path, dest: Path, fps: int | None = None) -> None:
    """The NESTLER files are named .mp4 but are camera program streams that browsers cannot play.
    Re-encode to ordinary H.264 in an MP4, at most 1280 wide, with the index at the front so it can stream."""
    cmd = [ffmpeg(), "-y", "-loglevel", "error", "-i", str(src), "-an", "-vf", "scale='min(1280,iw)':-2" + (f",fps={fps}" if fps else ""),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dest)]
    subprocess.run(cmd, check=True)


def fetch(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {dest.name}", flush=True)
    urllib.request.urlretrieve(url, dest)


def main() -> None:
    out = MEDIA / "clips"
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for clip in CLIPS:
        src = clip["source"]
        target = out / f"{clip['id']}.mp4"
        if not target.exists():
            if src.get("file"):                                         # a single checked file, re-encoded
                raw = RAW / src["file"]
                if not raw.exists() or md5(raw) != src["md5"]:
                    fetch(src["download"], raw)
                    if md5(raw) != src["md5"]:
                        raise SystemExit(f"md5 mismatch for {src['file']}, not using it")
                print(f"  converting {clip['id']} to a playable MP4", flush=True)
                to_web_mp4(raw, target, fps=15)
            else:                                                       # a member of a checked zip
                z = RAW / src["zip"]
                if not z.exists() or md5(z) != src["md5"]:
                    fetch(src["download"], z)
                    if md5(z) != src["md5"]:
                        z.unlink(missing_ok=True)
                        raise SystemExit(f"md5 mismatch for {src['zip']}, not using it")
                    print(f"  {src['zip']}: md5 matches the value Zenodo lists", flush=True)
                raw = RAW / "members" / clip["member"]
                raw.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(z) as zf:
                    names = {Path(n).name: n for n in zf.namelist()}
                    raw.write_bytes(zf.read(names[clip["member"]]))
                print(f"  converting {clip['id']} to a playable MP4", flush=True)
                to_web_mp4(raw, target)
        manifest.append({
            "id": clip["id"], "pen": clip["pen"], "title": clip["title"], "view": clip["view"],
            "source": src["name"], "sourceUrl": src["url"], "license": src["license"],
            "bytes": target.stat().st_size,
        })
        print(f"ready: {target.name} ({target.stat().st_size / 1e6:.1f} MB)", flush=True)
    (MEDIA / "clips.json").write_text(json.dumps(manifest, indent=2))
    print("wrote", MEDIA / "clips.json")


if __name__ == "__main__":
    main()
