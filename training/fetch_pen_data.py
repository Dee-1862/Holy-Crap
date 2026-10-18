"""Download everything pen_scale.py needs onto a fresh machine and check it against Zenodo's md5.

    PEN_RAW=... PEN_VIDEOS=... python fetch_pen_data.py

Machuve farm photos and labels (Zenodo 4628934), PIO barn videos (Zenodo 16686320) and NESTLER clips
(Zenodo 15063494), all CC BY 4.0. Uses the parallel range downloader from prepare_data.py.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import prepare_data as P
from pen_scale import CLASSES, RAW, VIDEOS


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def listed(rec: str) -> dict[str, str]:
    with urllib.request.urlopen(f"https://zenodo.org/api/records/{rec}") as r:
        return {f["key"]: f["checksum"].split(":")[1] for f in json.load(r)["files"]}


def get(rec: str, name: str, dest: Path, sums: dict[str, str]) -> Path:
    if not (dest.exists() and md5(dest) == sums[name]):
        dest.unlink(missing_ok=True)
        P.download(rec, urllib.parse.quote(name), dest)
        if md5(dest) != sums[name]:
            raise SystemExit(f"md5 mismatch for {name}")
    print(f"{name}: md5 matches the value Zenodo lists", flush=True)
    return dest


def main():
    farm = listed(P.FARM_REC)
    for name in ["imgObjDet_Yolo.zip"] + [f"{c}.zip" for c in CLASSES]:
        get(P.FARM_REC, name, RAW / name, farm)

    pio = listed("16686320")
    (VIDEOS / "pio").mkdir(parents=True, exist_ok=True)
    get("16686320", "0002.mp4", VIDEOS / "pio" / "0002.mp4", pio)
    rar = get("16686320", "Videos 2023.rar", VIDEOS / "pio" / "videos2023.rar", pio)
    if not list((VIDEOS / "pio").rglob("0004.mp4")):
        tool = shutil.which("bsdtar") or shutil.which("unar") or shutil.which("7z")
        if not tool:
            raise SystemExit("no RAR extractor found, install libarchive-tools")
        args = [tool, "-xf", str(rar)] if "bsdtar" in tool else [tool, str(rar)] if "unar" in tool else [tool, "x", "-y", str(rar)]
        subprocess.run(args, cwd=VIDEOS / "pio", check=True)
    rar.unlink()                                                    # the extracted videos are enough, free 5 GB

    nest = listed("15063494")
    z = get("15063494", "poultry_videos.zip", RAW / "nestler_poultry_videos.zip", nest)
    out = VIDEOS / "nestler"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        for n in zf.namelist():
            if n.endswith(".mp4"):
                (out / Path(n).name).write_bytes(zf.read(n))
    print("videos:", sorted(p.name for p in VIDEOS.rglob("*.mp4")), flush=True)


if __name__ == "__main__":
    main()
