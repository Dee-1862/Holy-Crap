# Live feed replay

Replays public whole-pen barn clips in the console at `/live`.

- `python app/live-feed/fetch_clips.py` downloads the clips, checks the NESTLER zip md5 and re-encodes them for browsers into `app/console/media/clips`
- `python app/live-feed/analyze_clips.py` measures flock motion and runs the droppings detector, writing `app/console/media/analysis`
- `media/` is git-ignored. Needs `onnxruntime`, `opencv-python` and `imageio-ffmpeg`

## Finding

The detector does not transfer to whole-pen footage. It was trained on close-up photos. On these clips the boxes sit on birds and equipment, and no droppings labels exist, so no accuracy can be reported. The boxes are experimental, off by default and never used for alerts. A pen camera needs a different approach such as a background difference trigger, close-up crops or our own barn images.

Sources and licenses are in `docs/research/datasets/whole-pen-video-catalog.md`.
