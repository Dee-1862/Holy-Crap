# Whole-pen video preprocessing

The preprocessing utility creates repeatable, reviewable variants of real
whole-pen footage before a model bundle reaches the QNX Raspberry Pi. It wraps
local `ffmpeg`/`ffprobe`; it does not contain a video decoder, train a model, or
claim to benchmark inference.

## Quick start

Install ffmpeg on the Mac, activate the project environment, and inspect a
source without modifying it:

```sh
holy-crap-simlab preprocess-video path/to/whole-pen.mp4
```

Create the recommended color-preserving baseline and save its JSON report:

```sh
holy-crap-simlab preprocess-video \
  path/to/whole-pen.mp4 \
  .simlab/preprocessed/whole-pen-540p-11fps.mp4 \
  --profile pi-balanced \
  --report .simlab/preprocessed/whole-pen-540p-11fps.json
```

The original is never overwritten unless `--overwrite` is supplied, and input
and output cannot be the same path. Audio is dropped because the current
camera/model contract is visual only. Outputs and reports under `.simlab/` stay
out of Git.

## Included profiles

| Profile | Output | Intended use | Important limitation |
|---|---:|---|---|
| `pi-balanced` | 960x540, 11 FPS, color H.264 CRF 23 | Default appearance and activity experiments | Must still be timed on the actual Pi/model runtime |
| `motion-gate` | 320x180, 5.5 FPS, grayscale H.264 CRF 28 | Cheap pen/zone motion gating | Not the only input for appearance, injury, or dropping review |
| `detail` | 1920x1080, 11 FPS, color H.264 CRF 23 | Workstation review and small-object reference | Larger transfer/decode load |

Use explicit overrides to isolate one variable at a time:

```sh
holy-crap-simlab preprocess-video source.mp4 output.mp4 \
  --profile pi-balanced --size 640x360 --fps 5.5 \
  --color-mode color --codec h264 --quality 26
```

Keeping a full-color option matters. Plumage, skin, wounds, litter, and
droppings may carry useful color information. The grayscale profile is a
candidate first-stage motion stream, not a conclusion that color is irrelevant.

## Reading the report

The JSON report includes:

- source and output resolution, sampled FPS, duration, frame count, codec,
  pixel format, size, and calculated container bitrate;
- the exact transform and ffmpeg command;
- measured size and bitrate reductions;
- a nominal model-input sample planning estimate; and
- explicit booleans showing what was and was not measured.

File compression and inference compute are different measurements:

1. Codec and quality primarily change bytes stored or transferred.
2. Resolution, sampled FPS, decoded channels, preprocessing, and model input
   shape affect the amount of input work.
3. The model architecture, quantization, delegate, decoder, memory copies, and
   QNX runtime determine actual latency.

Therefore, a 75% smaller file is not evidence of a 4x faster model. Final
profiles must be benchmarked with the actual exported model on the Pi. For the
current two-stage design, use the motion stream to identify candidate times or
zones, then retain full-color crops/frames for appearance review.

## Whole-pen experiment discipline

- Start with footage that shows the complete pen; reject close-up montages for
  pen-level replay.
- Preserve the untouched source and record dataset/video identifiers alongside
  each report.
- Change one factor at a time when comparing resolution, FPS, color, or quality.
- Inspect small birds and droppings visually before accepting a lower resolution.
- Compare activity at pen/zone level when stable individual identity is not
  possible, while retaining individual tracks when the view supports them.
- Never treat preprocessing output as evidence of disease or model accuracy.
