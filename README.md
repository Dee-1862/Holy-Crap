# Holy-Crap: poultry health research

A Raspberry Pi Camera Module 3 mounted overhead watches chickens in a pen.
The headless QNX Raspberry Pi 5 streams camera data over the project's
reliable-Wi-Fi working assumption to a desktop primary UI. The system monitors
the flock, tracks individuals when feasible, detects and associates newly
deposited droppings when the evidence supports it, and surfaces
health/welfare anomalies for a farmer to review. It does not diagnose
disease and it never makes culling decisions.

## Start here

- [docs/BIBLE.md](docs/BIBLE.md): the authoritative handbook: scope, safety boundary,
  hardware, QNX Pi operations, build plan, decisions, unknowns. Controls
  where older docs conflict.
- [docs/research/PAPER.md](docs/research/PAPER.md): the central synthesis: what the camera can and
  cannot observe, identity and tracking, droppings, data, prior work,
  recommended MVP.

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
