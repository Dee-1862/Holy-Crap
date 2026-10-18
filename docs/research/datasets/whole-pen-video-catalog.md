# Whole-pen poultry video catalog

This is the short list of real-camera sources reviewed for the simulation lab. Lance is the final
judge of camera suitability. Each new video dataset should be reviewed with exactly one
representative clip open in QuickTime at a time.

The current requirement is a whole-pen feed. Cropped, single-bird, or behavior-montage footage is
not useful as simulator input, even when the underlying labels are good. “Approved” below means the
camera view is useful for simulation and UI work. It does not mean the dataset contains disease
ground truth.

## Watch or download the reviewed footage

These are the source files used for review. Nothing here depends on a local browser session.

- [Download the approved 20-second Spatiotemporal Annotator clip](https://raw.githubusercontent.com/steven068zzy/spatiotemporal-annotator/3d2f2eb43888122229b0da992f9893a66a530e2a/examples/videos/cam1__20250930_095000.mp4)
- [Download the reviewed PIO source video](https://zenodo.org/api/records/16686320/files/0002.mp4/content)
- [Download all 21 NESTLER activity clips](https://zenodo.org/api/records/15063494/files/poultry_videos.zip/content)
- [Download MVBroTrack](https://datasets.ilabt.imec.be/broilertracking/MVBroTrack_v2.zip). The reviewed member was `MVBroTrack/Multi-View-Tracking/sample_6/videos/3_12_2023-03-25_15_05_00_15_05_30.mp4`.
- [Download the NESTLER behavior/keypoint archive](https://zenodo.org/api/records/20924893/files/poultry_behaviour_dataset.zip/content). The rejected pre-annotated review file was `poultry_behaviour_dataset/chickens/job_000009/annotated_000009.mp4`.
- [Download the rejected ChickenVerse demo MP4](https://raw.githubusercontent.com/amirivojdan/ChickenVerse/main/ChickenAct.mp4) if you need to verify why single-bird montages are out of scope.

Big Broiler is published as one 32.5 GB ZIP, but the two reviewed MP4 members are stored without ZIP
compression. These HTTP range requests fetch the MP4 payloads directly instead of downloading the
entire release:

```bash
# Approved complete-pen overhead Setup 3 clip (about 183 MB)
curl -fL --range 32437897338-32621387686 \
  https://datasets.ilabt.imec.be/broilertracking/big-broiler_v1.zip \
  -o 090_3_32_1920_010_0_10.mp4

# Dense clip with two Defecating events (about 164 MB)
curl -fL --range 11869289525-12033018531 \
  https://datasets.ilabt.imec.be/broilertracking/big-broiler_v1.zip \
  -o 039_1_17_1920_176_0_01.mp4
```

Expected sizes are `183490349` bytes for clip 090 and `163729007` bytes for clip 039. A size
mismatch means the archive changed; do not treat the result as a valid MP4.

## Reviewed video sources

| Source | What it contains | Human review | Best use | Important limits | License |
|---|---|---|---|---|---|
| [Big Broiler](https://github.com/decide-ugent/big-broiler-dataset) | 102 real videos, tracks, boxes, posture labels, and 23 behavior labels | **Approved.** Setup 3 clip `090_3_32_1920_010_0_10.mp4` was the best complete-pen overhead view reviewed. Clip `039_1_17_1920_176_0_01.mp4` was also useful and contains two labeled `Defecating` events. | Primary camera-geometry reference; identity tracking; behavior-event review | Setup 3 clip 090 has no released `Defecating` event. A `Defecating` row labels the bird’s action, not the deposited feces or its pixels. | AGPL-3.0 |
| [Spatiotemporal Annotator example data](https://github.com/steven068zzy/spatiotemporal-annotator/tree/main/examples) | A real 20-second overhead video of two complete pens with about 40 week-one broilers; 848×480 at 5 FPS | **Approved.** The complete pens and flock motion were easy to read despite the low frame rate. | Low-rate activity replay; full-pen tracking and scrubber tests | Low resolution, grooved floor, young birds, and poor feces visibility. Labels are `resting` and `active`, not health outcomes. | CC BY 4.0 |
| [PIO](https://zenodo.org/records/16686320) | Dense real overhead poultry-house video plus extracted bird-box annotations | **Useful with limits.** The commercial-house view and density were good, but the camera did not cover the complete pen. | Dense-flock detection and commercial-house appearance | Birds can leave the frame, so track interruption must not be interpreted as inactivity. No behavior, feces, or disease labels. | CC BY 4.0 |
| [NESTLER Poultry Video Dataset](https://zenodo.org/records/15063494) | 21 short real videos from fixed cameras mounted over poultry | **Useful with limits.** Litter and feces were easier to see, but the reviewed clip did not show the full pen. | Activity and optical-flow experiments; floor-detail reference | Partial-pen framing, no boxes or persistent IDs, and no feces or disease labels. | CC BY 4.0 |
| [MVBroTrack](https://github.com/decide-ugent/multi-view-broiler-tracking) | Four synchronized cameras, single-view boxes, multi-view ground-plane detections, and tracks | **Useful with limits.** The reviewed view covered the pen, but it was oblique from a high corner; distant birds were hard to resolve. | Track coverage, trajectories, occlusion, and multi-camera continuity | Not a strict top-down view. No behavior, feces, or disease labels. | AGPL-3.0 |
| [NESTLER Poultry Behaviour Analytics Detection Dataset](https://zenodo.org/records/20924893) | Walking, pecking, standing, and lying boxes plus four body keypoints | **Not approved as raw input.** The reviewed file was already annotated, used a tiered enclosure, and did not show a simple full-floor pen. | Overlay and keypoint UI reference only | Rendered boxes/keypoints contaminate model input. Use the unmodified source if this dataset is revisited for inference. | CC BY 4.0 |
| [ChickenVerse](https://github.com/amirivojdan/ChickenVerse) | Overhead detection/segmentation images and a behavior-video montage | **Rejected for video replay.** The reviewed MP4 was a series of close-ups of individual chickens. | Its still-image annotations may be useful elsewhere | The demo video is not a whole-pen feed. License is non-commercial share-alike. | CC BY-NC-SA 4.0 |

## Exact review clips and labels

### Big Broiler

The official release is a large ZIP:
[`big-broiler_v1.zip`](https://datasets.ilabt.imec.be/broilertracking/big-broiler_v1.zip).

- Primary whole-pen view: `090_3_32_1920_010_0_10.mp4` from documented overhead Setup 3.
- Defecation review: `039_1_17_1920_176_0_01.mp4`.
- Track 2152 is labeled `Defecating` at frames 2052–2073, or 82.08–82.92 seconds at 25 FPS.
- Track 2122 is labeled `Defecating` at frames 2349–2397, or 93.96–95.88 seconds at 25 FPS.
- Filter the annotation CSV by the exact `actions_ground == "Defecating"` value. Do not
  describe these rows as feces bounding boxes or deposited-dropping masks.

### Spatiotemporal Annotator

The reviewed clip is directly downloadable:
[`cam1__20250930_095000.mp4`](https://raw.githubusercontent.com/steven068zzy/spatiotemporal-annotator/3d2f2eb43888122229b0da992f9893a66a530e2a/examples/videos/cam1__20250930_095000.mp4).
The example-data documentation describes a camera about 2.5 m above the floor.

### PIO

The reviewed source was
[`0002.mp4`](https://zenodo.org/api/records/16686320/files/0002.mp4/content). It is roughly
1 GB and more than 78 minutes long, so local review should use a short derived clip rather than
copying the full file into Git.

### NESTLER and MVBroTrack

- [NESTLER 21-video archive](https://zenodo.org/api/records/15063494/files/poultry_videos.zip/content), about 82 MB.
- [MVBroTrack archive](https://datasets.ilabt.imec.be/broilertracking/MVBroTrack_v2.zip), about 1.59 GB.
- [NESTLER behavior archive](https://zenodo.org/api/records/20924893/files/poultry_behaviour_dataset.zip/content), about 1.18 GB.

## Images and feces-specific material

These do not meet the whole-pen video requirement, but they can support separate appearance panels
or crop-level tests:

- [MSU Poultry Piling Dataset](https://data.mendeley.com/datasets/pgp8mj6ms4/2): 11,263 real
  overhead JPGs labeled positive/negative for piling; CC BY 4.0. It is sampled imagery, not a
  continuous tracking feed.
- [Machuve fecal datasets](https://zenodo.org/records/4628934): disease-linked fecal close-ups,
  useful for appearance research but not camera geometry or whole-pen replay.

## Dashboard implications

- Keep individual-track and pen/zone aggregate outputs separate. Exact bird identity will not be
  reliable in every camera view.
- Report frame exits, occlusion, track coverage, and missingness. A bird leaving the camera view is
  not evidence of inactivity.
- Preserve dataset provenance and distinguish raw footage from annotated or derived video.
- Treat movement, posture, appearance, and feces as observable evidence. The simulation dashboard
  evaluates model outputs; it does not decide which signal diagnoses disease.
- Keep the media and result contracts profile-based so other livestock can reuse the same workflow
  later without hard-coding poultry disease logic into the platform.
