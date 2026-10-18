# Holy-Crap: poultry health research

A Raspberry Pi Camera Module 3 mounted overhead watches chickens in a pen.
The headless QNX Raspberry Pi 5 is intended to send a compressed/downsampled
preview, clips, or events to a desktop primary UI over a Wi-Fi path that still
needs field validation. The system monitors the flock, tracks individuals when
feasible, detects and associates newly deposited droppings when the evidence
supports it, and surfaces
health/welfare anomalies for a farmer to review. It does not diagnose
disease and it never makes culling decisions.

## Start here

- [docs/BIBLE.md](docs/BIBLE.md): the authoritative handbook: scope, safety boundary,
  hardware, QNX Pi operations, build plan, decisions, unknowns. Controls
  where older docs conflict.
- [docs/research/PAPER.md](docs/research/PAPER.md): the central synthesis: what the camera can and
  cannot observe, identity and tracking, droppings, data, prior work,
  recommended MVP.

## Run the simulation lab

The main operator workflow is a whole-pen clip assessment. Upload one video,
typically around five minutes, and get one aggregate summary of flock activity,
flock appearance, and feces candidates. It does not invent an infection
progression or require stable bird identities. The current four adapters are
deterministic mocks, so every score and classification is marked synthetic and
non-diagnostic. Re-uploading the same bytes produces the same mock result.

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
`GET /api/v1/dataset-clips`. An assessable entry without installed bytes can
still produce deterministic interface sample data through
`POST /api/v1/clip-assessments/catalog/{clip_id}`. That response is labeled
`catalog_mock`, has no playable content URL, and says plainly that no video was
decoded and no model ran. Rejected footage, annotated reference clips, and
image-only datasets cannot be assessed through that endpoint.

The feces path already has a clean model boundary. Detection produces a
timestamp, a normalized bounding box, and a lazy RGB crop reference. The next
adapter consumes that crop as RGB 224 x 224 and returns one of Coccidiosis,
Healthy, New Castle Disease, or Salmonella. That classifier slot is intended
for a future model trained from the linked
[Chicken Disease dataset](https://www.kaggle.com/datasets/allandclive/chicken-disease-1/data),
but no artifact is configured or executed yet. The dataset page does not state
a license in the metadata we reviewed, so this repository does not download or
redistribute its images.

The older scenario runner is still available for deterministic infrastructure
testing: choose a 100-bird scenario, select or upload a model artifact, run the
mock executor, and inspect its saved result. That mock does not measure an
uploaded model's accuracy and should not be confused with the clip assessment.

The QNX Pi is wired as an honest target-validation path, not an inference
executor: it has no TensorFlow Lite, ONNX, OpenCV, or NumPy runtime, so a QNX
run stages one exact catalog model and one canonical scenario JSON onto the
physical Pi and returns a verified receipt (`evaluation_kind: target_probe`,
`inference_performed: false`). QNX capability is at best `probe_only`; it
never reports `ready` until actual inference exists. See
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

- [Simulation architecture](docs/architecture/simulation-lab.md): component
  boundaries, run flow, runtime split, and current capability status.
- [Model handoff](docs/architecture/model-lifecycle.md): importing a completed
  local bundle without coupling the simulator to training infrastructure.
- [Video preprocessing](docs/architecture/video-preprocessing.md): create and
  measure color, grayscale, resolution, FPS, and codec variants without
  confusing storage compression with model inference speed.
- [Simulation roadmap](docs/roadmap/simulation-lab.md): real footage,
  epidemiological state, optional 3D, and deterministic QNX playback gates.
- [Contributing](CONTRIBUTING.md): worktrees, contracts, tests, and pull-request
  expectations for the team.

## Research base

- [docs/01-key-findings.md](docs/01-key-findings.md): numbered, actionable findings with confidence notes.
- [docs/00-landscape-review.md](docs/00-landscape-review.md): compact narrative review and comparison tables.
- [docs/02-bibliography.md](docs/02-bibliography.md): every source, grouped, with status labels.
- [docs/03-open-questions.md](docs/03-open-questions.md): prioritized open questions and settled answers.
- `docs/research/`: evidence and subject nodes (datasets, observables,
  identity, systems, evidence, practice).

## Existing plans and target

- [docs/game-plan.md](docs/game-plan.md): implementation sequence derived from
  [docs/BIBLE.md](docs/BIBLE.md).
- [TARGET.md](TARGET.md): the headless QNX Raspberry Pi 5 target and connection procedure.
- [docs/research.md](docs/research.md): research log plus QNX, Camera Module 3, AICA, and StopWatch notes.
- [docs/changes.md](docs/changes.md), [docs/mistakes.md](docs/mistakes.md): log of decisions and corrections.
