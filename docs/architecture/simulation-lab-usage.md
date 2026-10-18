# Simulation lab: usage notes

Moved from the top-level README on 2026-10-18. See also [simulation-lab.md](simulation-lab.md).

## Run the simulation lab

The main operator workflow is a whole-pen clip assessment. Upload one video,
typically around five minutes, and get one aggregate summary of flock activity,
flock appearance, and feces candidates. It does not invent an infection
progression or require stable bird identities. Activity, appearance, and feces
locations are deterministic mocks. The feces appearance stage runs the
committed ONNX model on attributed proxy photos and marks that substitution in
the result. Re-uploading the same bytes produces the same evidence mix.

```sh
curl -F 'file=@whole-pen.mp4;type=video/mp4' \
  http://127.0.0.1:8000/api/v1/clip-assessments/upload
```

The uploaded video is stored once by SHA-256 under `.simlab/clips/`. You can
also assess an installed, hash-verified demo clip with
`POST /api/v1/clip-assessments/demo/{asset_id}`. List saved assessments with
`GET /api/v1/clip-assessments`, fetch one with
`GET /api/v1/clip-assessments/{id}`, and stream its original bytes from the
assessment's `video.content_url`.

The dashboard's dataset picker comes from the committed reviewed catalog at
`GET /api/v1/dataset-clips`. When a reviewed entry's exact file name exists in
the local dataset-video store (`<HOLY_CRAP_HOME>/datasets/videos/**`, overridable
with `HOLY_CRAP_DATASET_VIDEOS_DIR`), the API reports `bytes_available`, the
installed byte size, and a playable `content_url`
(`GET /api/v1/dataset-clips/{id}/content`). That preview never changes an
entry's review status or assessability. When an assessable entry has local
video bytes, `POST /api/v1/clip-assessments/catalog/{clip_id}` analyzes those
bytes and records `source: dataset`. An assessable entry without installed
bytes can still produce deterministic interface sample data through the same
endpoint. That fallback response is labeled
`catalog_mock`, has no playable content URL, and says plainly that no video was
decoded and no model ran. Rejected footage, annotated reference clips, and
image-only datasets cannot be assessed through that endpoint.

The video path now runs bounded real inference over six sparse ffmpeg frames.
The behavior pipeline detects chickens and aggregates seven behavior classes
without requiring stable bird IDs. The pen-dropping model proposes persistent
locations across sampled frames, then the close-up model evaluates the observed
RGB crops. If real video inference is unavailable, the response marks the
affected stage as partial or mock and uses deterministic locations or the
installed attributed proxy-photo pool as an explicit fallback. The dashboard
keeps the observed location, classifier input, and model output separate. The
close-up classifier was trained from the linked
[Chicken Disease dataset](https://www.kaggle.com/datasets/allandclive/chicken-disease-1/data);
the bundled proxy photos come from the CC BY 4.0 Machuve et al. Zenodo dataset
and carry their own manifests and attribution.

The older scenario runner is still available for deterministic infrastructure
testing: choose a 100-bird scenario, select or upload a model artifact, run the
mock executor, and inspect its saved result. That mock does not measure an
uploaded model's accuracy and should not be confused with the clip assessment.

The dashboard's QNX executor is an honest target-validation path: a QNX run
stages one exact catalog model and one canonical scenario JSON onto the
physical Pi and returns a verified receipt (`evaluation_kind: target_probe`,
`inference_performed: false`). Separately, the final 320x320 model has now run
natively through NCNN on the Pi; ten model-only runs averaged 98.4287 ms, and a
real feces frame matched the ONNX reference closely. That experimental path is
not yet the production dashboard executor. See
`POST /api/v1/system/qnx/probe` and the `QNX_*` settings in `.env.example`.
When `qnxpi.local` is unavailable on a direct Ethernet link, keep
`QNX_SSH_ALIAS=qnxpi` so the existing identity and host-key policy still
apply, and set `QNX_SSH_HOSTNAME` to the Pi's current link-local address. The
checked-in runner helper carries that override through the full validation
job, including upload, polling, and receipt download.

Committed reference media includes a PIO-paper overhead broiler-house image
and the team-reviewed Spatiotemporal Annotator whole-pen clip (two complete
pens, 40 week-one birds, 848 x 480 at 5 fps). It is
served through `GET /api/v1/media` and `GET /api/v1/media/{id}/content` only
after the file is present and its SHA-256 matches the committed manifest.
Fetch all committed assets with `make demo-assets`, or pass one manifest id to
`python3 scripts/fetch_demo_assets.py`. Downloads also have to match the exact
manifest byte size. This imagery is a visual reference only:
the scenario's bird positions and outbreak timing are simulated, so the
combined result is not outbreak footage and is never labeled as one.

```sh
make doctor
make bootstrap
make demo-assets   # optional: fetch every committed reference image/video
make dev
```

Then open `http://127.0.0.1:5173`. Local artifacts are stored under `.simlab/`
and are ignored by Git.

- [Simulation architecture](../architecture/simulation-lab.md): component
  boundaries, run flow, runtime split, and current capability status.
- [Model handoff](../architecture/model-lifecycle.md): importing a completed
  local bundle without coupling the simulator to training infrastructure.
- [Video preprocessing](../architecture/video-preprocessing.md): create and
  measure color, grayscale, resolution, FPS, and codec variants without
  confusing storage compression with model inference speed.
- [Simulation roadmap](../roadmap/simulation-lab.md): real footage,
  epidemiological state, optional 3D, and deterministic QNX playback gates.
- [Contributing](../../CONTRIBUTING.md): worktrees, contracts, tests, and pull-request
  expectations for the team.

