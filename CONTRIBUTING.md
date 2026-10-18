# Working on Holy Crap

This repository is split so the three of us can work without sharing local
state or blocking on unfinished hardware and training work. Keep changes inside
the workstream you own, and treat `contracts/` as the point where we have to
coordinate.

## Start in a worktree

Do not pile concurrent work into the main checkout. Update `main`, then create a
task branch and worktree:

```sh
git fetch origin
git worktree add ~/worktrees/Holy-Crap/<task-id> -b <area>/<task-id> main
cd ~/worktrees/Holy-Crap/<task-id>
```

Use `edge/` for QNX and Pi work, `ml/` for training and evaluation, `web/` and
the simulation package for the lab, and `docs/` for shared decisions. A change
that crosses these boundaries should say why in the pull request.

## Local simulation setup

The scaffold expects Python 3.11 or newer, Node.js 20 or newer, and npm. Start
with:

```sh
make doctor
make bootstrap
make test
make build
```

`make doctor` reports optional tools such as Blender, ffmpeg, and the `qnxpi`
SSH alias. Missing optional tools should disable a capability, not break the
mock simulation.

Run the API and dashboard together with:

```sh
make dev
```

Local run data goes under `.simlab/` unless `HOLY_CRAP_HOME` points somewhere
else. Do not commit that directory.

## Contracts come first

The schemas in `contracts/` define model bundles, scenarios, and run results.
If you change a required field or its meaning:

1. update the schema version;
2. update Python validation and TypeScript types;
3. update fixtures and tests;
4. update the architecture document that explains the field;
5. ask a teammate from another workstream to review the pull request.

Do not add an unversioned field in one producer and wait for consumers to catch
up. Unknown data should be rejected or isolated in an explicitly open metadata
object.

## Adding a model bundle

The simulation lab receives completed artifacts. It does not own model
training, Veri compute, hosted job submission, or training credentials.

A bundle needs a schema-valid `model.json` and the referenced `.tflite` or
`.onnx` file. Calculate the artifact SHA-256 and put it in the manifest. The
importer recalculates it. Keep preprocessing and label order in the manifest so
the executor does not guess.

For a completed Veri run, copy or export its outputs to a local folder and pass
that folder to the importer. Do not commit tokens, signed URLs, job cookies, or
service configuration. The local folder is a handoff, not a hosted integration.

Never replace bytes under a registered model version. Give the new artifact a
new version and preserve both hashes long enough to compare runs.

## Large artifacts and datasets

Models, datasets, videos, render output, and generated run data stay out of Git.
Store them in the team's agreed artifact location or attach a deliberate release
artifact. Commit a small manifest containing:

- source and license;
- retrieval or creation date;
- SHA-256 digest;
- expected filename and size;
- preprocessing or generation recipe;
- any access restrictions.

Do not assume a public download is licensed for redistribution. Do not add farm
or operator identifiers to demo data without approval.

## Tests before review

Run the checks that match your change:

```sh
make test
make build
python3 -m json.tool contracts/model-bundle.schema.json >/dev/null
python3 -m json.tool contracts/scenario.schema.json >/dev/null
python3 -m json.tool contracts/run-result.schema.json >/dev/null
```

Scenario-engine changes need a determinism test with a fixed seed. Catalog
changes need tests for hash mismatch, path traversal, duplicate registration,
and interrupted writes. UI changes should cover loading, empty, error, and
unsupported-capability states. QNX claims need output from the physical target,
not only a workstation substitute.

## Pull requests

Keep a pull request small enough for one teammate to reproduce. Include:

- what works now and what is still a stub;
- commands you ran and their results;
- screenshots for visible dashboard changes;
- contract or artifact compatibility impact;
- measured target details for QNX changes;
- follow-up work that was intentionally left out.

Do not describe mock results as model accuracy or simulated hidden state as a
disease diagnosis. Use pen or group anomaly language in code, screenshots, and
docs.

The repository is public. Check staged files for credentials, local target
details, generated artifacts, and private data before pushing.
