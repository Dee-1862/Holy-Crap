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
    "name": "PIO poultry dataset, Boniche, Cruz et al. 2025 (Veraguas, Panama)",
    "url": "https://zenodo.org/records/16686320",
    "download": "https://zenodo.org/api/records/16686320/files/0002.mp4/content",
    "file": "pio/0002.mp4",
    "md5": "8ca0273b36d0fd3e349eb07f735f0d73",
    "license": "CC BY 4.0",
}

BIGBROILER = {
    "name": "Big Broiler, Cardoen et al. 2025",
    "url": "https://github.com/decide-ugent/big-broiler-dataset",
    "remote_zip": "https://datasets.ilabt.imec.be/broilertracking/big-broiler_v1.zip",
    "license": "AGPL-3.0",
}

# The floor of the Big Broiler pen, drawn once for its fixed camera as shares of the frame, the way an installer
# marks the floor when mounting a camera. Spots outside it (walls, the door panel, the feeder bar's wall side) are ignored.
BB_FLOOR = [(0.448, 0.231), (0.583, 0.105), (0.865, 0.075), (0.87, 0.24), (0.833, 0.611), (0.776, 1.0),
            (0.062, 1.0), (0.0, 0.87), (0.0, 0.815), (0.344, 0.352)]

# Three cameras, one per camera pen. The Big Broiler clips are from Rishit's held out behaviour test set (092 to 101),
# and no Big Broiler video was used for the droppings model, so no live camera shows footage any model trained on. id, the pen it stands in for, title, what the camera sees, source, file inside the source
CLIPS = [
    {"id": "pio-0002", "pen": "A1", "title": "Broiler house, 78 minutes", "view": "Overhead camera in a commercial broiler house, a dense flock of white broilers, 1920 by 1080 shown at 1280",
     "source": PIO, "member": None},
    {"id": "bb-093", "pen": "A2", "title": "Research pen, day 22", "view": "Fixed camera over a small pen of dye marked broilers, 22 days old, 2688 by 1520 shown at 1280",
     "source": BIGBROILER, "member": "093_2_22_2688_011_1_01.mp4", "floor": BB_FLOOR},
    {"id": "bb-101", "pen": "B1", "title": "Research pen, day 40", "view": "Fixed camera over a small pen of dye marked broilers, 40 days old, 2688 by 1520 shown at 1280",
     "source": BIGBROILER, "member": "101_2_40_2688_011_1_01.mp4", "floor": BB_FLOOR},
]
