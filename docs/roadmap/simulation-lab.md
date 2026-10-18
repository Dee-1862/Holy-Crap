# Simulation lab roadmap

Each phase has an acceptance gate. A phase is not complete because a screen
exists; its saved artifacts and measurements must be inspectable by another
teammate.

## Phase 0: Working scaffold

Build the local FastAPI catalog, deterministic mock executor, two 100-bird
scenarios, React dashboard, JSON contracts, and basic CI.

Acceptance gate:

- a clean checkout can run tests and build the dashboard using documented
  commands;
- `healthy-100` and `outbreak-100` run at a requested 11 FPS contract;
- repeating a mock run with the same seed produces the same timeline values;
- the dashboard shows truth, predictions, alert timing, timing metrics, and
  current adapter capabilities;
- model upload and local completed-output import reject an invalid bundle;
- no target, Veri, or farm credentials are required.

## Phase 1: Real-video replay on the workstation

Add an observation-set manifest for a fixed overhead clip, frame timestamps,
annotations, and source/license metadata. Implement a workstation executor that
runs a real TFLite or ONNX model over decoded frames.

The committed PIO reference image already exercises the media-manifest path:
`demo-assets/` carries the manifest, `make demo-assets` fetches and verifies
the bytes, and the media API serves them only after hash validation. The image
is a non-aligned visual reference with simulated bird state, so it must not be
treated as outbreak footage; a real replay clip needs its own pinned
observation manifest and license review before it is used for measurement.

Start with project-owned footage or a dataset whose license permits the intended
use. ChickenVerse and Big Broiler are candidates for behavior and occupancy
work. Machuve data may inform dropping-focused tests. Each source still needs a
license and task-fit review before download or redistribution.

Acceptance gate:

- one pinned clip can be replayed twice with the same frame order;
- frame preprocessing is read from the model bundle, not hard-coded;
- prediction artifacts point back to frame timestamps;
- measured FPS, p50/p95 latency, skipped frames, and alert output are saved;
- source, license, and file digests are recorded.

## Phase 2: Pen-state and progression scenarios

Use EMULSION for population and state transitions, with the DECIDE broiler
model as a reference rather than an unquestioned truth source. Map latent state
to observable behavior parameters such as movement, clustering, and event rate.
Keep that mapping explicit and versioned.

Acceptance gate:

- scenario state transitions are deterministic for a fixed seed;
- a scenario can vary onset time, prevalence, pen size, and observation noise;
- latent states are clearly separated from camera-visible observations;
- no generated label is presented as a veterinary diagnosis;
- parameters and their evidence or working-assumption status are documented.

## Phase 3: Optional 3D demonstration

Add a Blender/BlenderProc renderer on the workstation. Use overhead camera
calibration, varied lighting and bedding, bird appearance variation, occlusion,
and annotation passes. The first target is a useful visual demo and stress test,
not photorealistic scientific validation.

Acceptance gate:

- one committed scene recipe renders from the command line without opening the
  Blender UI;
- RGB frames and ground-truth masks/positions share timestamps and frame IDs;
- camera height, field of view, pen geometry, lighting, assets, and random seed
  are recorded;
- every external asset has a recorded source and usable license;
- the output can be opened as the same observation set used by real-video
  replay.

## Phase 4: QNX target validation and deterministic playback

The honest transport path now exists: QNX runs stage one exact catalog model
and one canonical scenario JSON onto the physical Pi and store a verified
receipt (`evaluation_kind: target_probe`, `inference_performed: false`) plus
the helper log under the run directory. This is target validation, not
inference: the Pi has no TensorFlow Lite, ONNX, OpenCV, or NumPy runtime, so
the probe worker only proves the files reached the target and were processed
there.

Remaining: measured inference. When a real runtime exists on the Pi, connect
QNX Sensor Framework file-camera or another proven deterministic playback path
so the Pi receives a known frame sequence and returns predictions. Transfer
jobs and artifacts over Ethernet/SSH. Long runs use the existing persistent
runner.

Acceptance gate:

- the capability check reports exact target/runtime versions and can actively
  probe with short timeouts (done for target validation);
- a submitted run refers to immutable model, scenario, and observation hashes;
- the Pi returns per-frame predictions plus median/p95 latency, achieved FPS,
  memory, temperature, throttling, and dropped frames where available;
- a connection loss does not corrupt a completed artifact or duplicate a run;
- the same frames can be compared between workstation and Pi outputs;
- no change to `/boot/onboot` or the Railway tunnel is required.

## Phase 5: Evaluation and reports

Add comparison views and machine-readable reports across model versions,
executors, and scenario suites. Define alert thresholds from validation results,
not from a demo screenshot.

Acceptance gate:

- the team can compare two model hashes on the same scenario set;
- reports include detection delay, false alerts per group-time, missed events,
  achieved FPS, latency, and dropped frames;
- failures and unsupported runs remain visible in the comparison;
- every alert can be traced to timeline evidence;
- a report records the contract versions and repository revision.

## Phase 6: Optional Veri automation

Only after the local artifact handoff is stable, consider an adapter that reads
completed exports or submits evaluation feedback through supported Veri tools.
The training teammate owns this integration and its credentials.

Acceptance gate:

- the team has a documented reason local import is insufficient;
- the official API or CLI contract is pinned and tested;
- credentials use local secret storage and never enter model bundles or run
  results;
- a hosted failure cannot delete or rewrite local registered artifacts;
- manual local import remains available.

This phase is optional for the hackathon. Compute allocation and model training
are already handled outside the simulation workstream.
