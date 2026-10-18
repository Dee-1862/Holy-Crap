# Research wiki

Conventions for every note under `docs/research/`. The synthesis lives in
[PAPER.md](PAPER.md); this tree holds the evidence and subject nodes it links to.

## Source status labels

Every source gets exactly one label:

- `[read]`: the source itself was read in full.
- `[skimmed]`: read partially (abstract, methods, tables); treat details cautiously.
- `[found]`: located and assessed relevant, but not fully reviewed.
- `[abstract only]`: only the abstract was read.
- `[inaccessible]`: could not be read; noted for follow-up.

Vendor/company pages get an extra marker: `[vendor]` or `[company source]`,
because they are marketing, not independent evidence.

## Rules

1. Every factual claim needs a source in the same paragraph or table row.
2. Contradictions stay visible: record both sides with their statuses; never
   silently pick a winner.
3. Source claims vs our inferences: label our conclusions clearly (e.g.
   "Our inference: ...").
4. Links are normal relative Markdown links.
5. Numbers belong next to their citation.
6. Keep nodes small; link, don't duplicate.

## Node template

- Title
- Type (dataset / observable / method / system / evidence / practice note)
- One-line summary
- Why we care
- Evidence
- Limits / open questions
- Connects to
- Sources (with status labels)

Not every node needs every section; drop the boilerplate when a shorter
layout is clearer.

## Index

- `datasets/`: data we could train or evaluate on
- `observables/`: what a camera can and cannot see
- `identity/`: tracking and individual identity
- `systems/`: prior art, reviews, commercial landscape
- `evidence/`: clinical and veterinary limits
- `practice/`: operator needs and product decisions
