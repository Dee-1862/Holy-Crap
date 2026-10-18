"""The clips the live feed replays. All are public datasets that allow reuse with credit (CC BY 4.0).

Clips are never committed to git. fetch_clips.py downloads them, checks the publisher's checksum, and
copies the playable files into app/console/media/. The reviewed catalog is docs/research/datasets/whole-pen-video-catalog.md.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEDIA = REPO / "app" / "console" / "media"
RAW = MEDIA / "raw"

NESTLER = {
    "name": "NESTLER Poultry Video Dataset",
    "url": "https://zenodo.org/records/15063494",
    "download": "https://zenodo.org/api/records/15063494/files/poultry_videos.zip/content",
    "zip": "nestler_poultry_videos.zip",
    "md5": "edde39ceed6c6eb07afc27e17d50b79f",
    "license": "CC BY 4.0",
}
PIO = {
    "name": "PIO poultry dataset, Universidade Federal da Grande Dourados",
    "url": "https://zenodo.org/records/16686320",
    "download": "https://zenodo.org/api/records/16686320/files/0002.mp4/content",
    "file": "pio/0002.mp4",
    "md5": "8ca0273b36d0fd3e349eb07f735f0d73",
    "license": "CC BY 4.0",
}

# Three cameras, one per camera pen. id, the pen it stands in for, title, what the camera sees, source, file inside the source
CLIPS = [
    {"id": "pio-0002", "pen": "A1", "title": "Broiler house, 78 minutes", "view": "Overhead camera in a commercial broiler house, a dense flock of white broilers, 1920 by 1080 shown at 1280",
     "source": PIO, "member": None},
    {"id": "pen-wide", "pen": "A2", "title": "Pen, wide view", "view": "Fixed camera over a litter floor pen, young and adult birds, 1280 by 720",
     "source": NESTLER, "member": "20250319_20250319150714_20250319150744_150715.mp4"},
    {"id": "pen-dense", "pen": "B1", "title": "Pen, dense flock", "view": "Fixed camera at a corner of a pen with perches, adult birds, 1280 by 720",
     "source": NESTLER, "member": "20250320_20250320125521_20250320125601_125521.mp4"},
]
