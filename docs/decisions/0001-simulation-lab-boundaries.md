# ADR 0001: Simulation lab boundaries

- Status: Accepted
- Date: 2026-10-17

## Context

The repository had research and target notes but no shared way to register a
candidate model, run a repeatable pen scenario, or inspect the result. The team
needs a working vertical slice now, while the realistic video, rendering,
training, and QNX paths are still being developed by different people.

The physical target is a headless Raspberry Pi 5 running QNX 8. The target may
process around 11 FPS while image processing is active, but that needs measured
confirmation. It should execute inference tests, not carry the desktop UI or
render synthetic scenes.

Model training, including Veri compute and credentials, belongs to another
workstream. The simulation lab receives completed artifacts.

## Decision

We will build the first simulation-lab slice with:

- FastAPI and Pydantic for the local API and contract validation;
- React, TypeScript, and Vite for the dashboard;
- a local filesystem catalog with JSON metadata and content-addressed payloads;
- explicit renderer, model-import, and executor adapter boundaries;
- deterministic mock scenarios as the first working executor;
- JSON Schema 2020-12 contracts for model bundles, scenarios, and run results;
- local import of a completed training export folder, with no hosted Veri integration;
- a future QNX adapter based on deterministic file-camera or video playback.

Rendering is separate from execution. BlenderProc or another renderer can
produce frames and annotations on a workstation. The mock or QNX executor can
consume an observation set without also having to render it.

## Why this choice

FastAPI and React are ordinary tools the team can change quickly. They also
keep the browser UI independent from Python inference and scenario libraries.
JSON Schema gives the Python, TypeScript, training, and QNX workstreams a
language-neutral review point.

A filesystem catalog avoids a database migration project before the shape of a
run is stable. Content hashes make model and scenario references reproducible.
If concurrent writers or remote access become real requirements, the catalog
interface can move to SQLite or an object store without changing the public run
contract.

The mock-first slice tests the whole workflow without pretending to test model
accuracy. It makes missing QNX and rendering capabilities visible while letting
the team refine the UI, contracts, and experiment loop.

## Alternatives considered

### One Blender or Unity application for everything

This could make a polished 3D demo, but it couples rendering, experiment state,
inference, and UI. Unity Perception is no longer a good foundation for new work,
and a full game-engine application would slow down contract and target work.
BlenderProc remains useful later as an offline renderer.

### NVIDIA Omniverse or Isaac Sim

These tools have strong synthetic-data features but expect supported NVIDIA RTX
hardware and do not fit the current Apple Silicon workstation or QNX Pi target.
They also add more infrastructure than this hackathon needs.

### Start with a database and job queue

PostgreSQL, Redis, and a worker queue would help multiple remote users, but the
first use is one team running local experiments. A filesystem catalog is easier
to inspect and back up. The catalog API preserves a path to a different backend.

### Run the UI and orchestration on the Pi

This would consume limited target memory and CPU without improving the
measurement. The Pi remains an executor. The Mac hosts the lab and communicates
with it over Ethernet or SSH.

### Integrate the Veri API immediately

The training owner is already coordinating Veri compute. Binding the simulator
to an evolving hosted API would mix responsibilities and require credentials.
Version 1 accepts the completed local output instead.

## Consequences

### Benefits

- Teammates can run and inspect the same deterministic scenarios.
- Model and scenario hashes make comparisons traceable.
- UI work can proceed before the QNX adapter or realistic assets are ready.
- New renderers and executors have explicit integration points.
- Training-service credentials stay out of the simulator.

### Costs and limits

- The mock executor does not measure real model quality.
- The local catalog assumes one trusted machine and modest concurrency.
- A useful 3D or video demo still needs assets, licenses, and renderer work.
- The browser and Python layers require generated or hand-maintained shared
  types until contract code generation is added.
- QNX performance remains unknown until replay works on the physical target.

## Follow-up decisions

Separate ADRs are required before choosing a real-video format, a Blender asset
pipeline, catalog synchronization, remote authentication, or a hosted Veri
integration. None is implied by this decision.
