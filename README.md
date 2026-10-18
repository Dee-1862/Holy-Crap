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

The first working scaffold is a local experiment loop: choose a deterministic
100-bird scenario, select or upload a model artifact, run the mock executor,
and inspect pen state, alerts, timing, and saved results in the dashboard. The
mock makes the workflow testable; it does not measure the uploaded model's
accuracy. Real-video replay and optional 3D rendering are visible but
intentionally not claimed as working yet.

The QNX Pi is wired as an honest target-validation path, not an inference
executor: it has no TensorFlow Lite, ONNX, OpenCV, or NumPy runtime, so a QNX
run stages one exact catalog model and one canonical scenario JSON onto the
physical Pi and returns a verified receipt (`evaluation_kind: target_probe`,
`inference_performed: false`). QNX capability is at best `probe_only`; it
never reports `ready` until actual inference exists. See
`POST /api/v1/system/qnx/probe` and the `QNX_*` settings in `.env.example`.

Committed reference media (one PIO-paper overhead broiler-house image) is
served through `GET /api/v1/media` and `GET /api/v1/media/{id}/content` only
after the file is present and its SHA-256 matches the committed manifest.
Fetch it with `make demo-assets`. This imagery is a visual reference only:
the scenario's bird positions and outbreak timing are simulated, so the
combined result is not outbreak footage and is never labeled as one.

```sh
make doctor
make bootstrap
make demo-assets   # optional: fetch the committed PIO reference image
make dev
```

Then open `http://127.0.0.1:5173`. Local artifacts are stored under `.simlab/`
and are ignored by Git.

- [Simulation architecture](docs/architecture/simulation-lab.md): component
  boundaries, run flow, runtime split, and current capability status.
- [Model handoff](docs/architecture/model-lifecycle.md): importing a completed
  local bundle without coupling the simulator to training infrastructure.
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
