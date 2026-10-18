"""Turn the camera analyses into the droppings every screen shows, so the website and the watch read one source.

    python app/live-feed/export_camera_droppings.py

Reads the deployed camera set (app/console/public/demo-media/analysis/*.json and lib/demo-clips.json). Each spot a
camera flagged becomes one dropping, numbered in the order the camera view shows its thumbnails, with:
    the camera crop and the detector's box on it
    the reading: the close-up model's scores on the original photo of the dropping when the clip has one (the A1
        clip, where known droppings were added at known times), the pen model's scores otherwise
    a score out of 10, the close-up model's healthy share times ten (no written grades)
    plain notes from what was measured: size, how much darker and how differently coloured than the floor, frames seen
Also writes each camera's bird counts over the clip (from the behaviour models) and a 180 by 135 photo per dropping
for the watch (app/console/public/watch/<id>.jpg).
Writes app/console/src/lib/camera-droppings.json.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[2]
CONSOLE = REPO / "app" / "console"
ANALYSIS = CONSOLE / "public" / "demo-media" / "analysis"
WATCH = CONSOLE / "public" / "watch"
OUT = CONSOLE / "src" / "lib" / "camera-droppings.json"
TYPE = {"healthy": "healthy", "cocci": "coccidiosis", "salmo": "salmonella", "ncd": "ncd"}


def probs_of(scores: dict) -> dict:
    """Detector scores per class, scaled to add up to one. All zero reads as healthy."""
    p = {TYPE[k]: max(0.0, v) for k, v in scores.items() if k in TYPE}
    total = sum(p.values())
    if total <= 0:
        return {"healthy": 1.0, "coccidiosis": 0.0, "salmonella": 0.0, "ncd": 0.0}
    return {k: round(v / total, 3) for k, v in p.items()}


def notes(s: dict, closeup: bool) -> list[str]:
    out = [f"{s['sizePx']} px across on the camera, dropping sized for this view"]
    out.append(f"Darker than the floor around it by {s['darker']:.0f} levels" if s["darker"] >= 3 else "About as dark as the floor around it")
    out.append(f"Colour differs from the litter by {s['colourShift']:.0f}" if s["colourShift"] >= 3 else "Close to the litter colour")
    out.append(f"Still for {s['seen']} checks in a row, so not a moving bird")
    if closeup:
        out.append("Reading from the close-up model on the original photo of this dropping")
    return out


def watch_photo(crop_url: str, path: Path) -> None:
    im = Image.open(io.BytesIO(base64.b64decode(crop_url.split(",", 1)[1]))).convert("RGB")
    w, h = im.size
    ch = int(w * 3 / 4)                                   # 4:3 from the square crop, centred on the spot
    im = im.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch)).resize((180, 135), Image.LANCZOS)
    im.save(path, "JPEG", quality=82)


def main():
    clips = json.loads((CONSOLE / "src" / "lib" / "demo-clips.json").read_text())
    WATCH.mkdir(parents=True, exist_ok=True)
    for old in WATCH.glob("*.jpg"):
        old.unlink()
    out = {"clips": [], "droppings": []}
    for clip in clips:
        f = ANALYSIS / f"{clip['id']}.json"
        if not f.exists():
            continue
        d = json.loads(f.read_text())
        beh = d.get("behaviour") or {}
        out["clips"].append({"id": clip["id"], "pen": clip["pen"], "duration": d["duration"], "added": bool(clip.get("test")),
                             "times": beh.get("times", []), "birds": beh.get("birds", [])})
        for n, s in enumerate(d.get("spots") or [], 1):
            close = (s.get("truth") or {}).get("closeup")
            probs = probs_of(close["scores"] if close and close.get("scores") else s["scores"])
            kind = max(probs, key=probs.get)
            sid = f"{clip['pen']}-{n}"
            watch_photo(s["crop"], WATCH / f"{sid}.jpg")
            out["droppings"].append({
                "id": sid, "n": n, "group": clip["pen"], "clip": clip["id"], "at": round(s["t"], 1),
                "type": kind, "probs": probs, "grade": max(1, round(10 * probs["healthy"])),
                "crop": s["crop"], "box": s.get("cropBox"),
                "closeup": close["img"] if close else None, "closeupBox": close.get("box") if close else None,
                "why": notes(s, bool(close)),
            })
    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {len(out['droppings'])} droppings from {len(out['clips'])} cameras to {OUT.relative_to(REPO)}")
    for x in out["droppings"]:
        print(f"  {x['id']}  {x['type']:12s} score {x['grade']:2d}  at {x['at']:6.1f} s")


if __name__ == "__main__":
    main()
