# Paper draft

LaTeX source of the Holy-Crap paper. Build it on Overleaf (upload this folder as a zip) or locally with
`latexmk -pdf main.tex`. Every red `[TODO: ...]` marker must be filled in or removed before submission.

| File | What it is |
|---|---|
| `main.tex` | title, abstract, statements, and the sections in order |
| `sections/*.tex` | introduction, related work, methods, results, discussion and conclusion |
| `references.bib` | only references that were checked against the source |
| `citation-check.md` | how each reference was checked, corrections, and claims that must not be cited yet |
| `figures/` | copies of the PDF figures from `data-visualization/figures`, made by `data-visualization/evaluation.py` |

To refresh the figures after new results: `cd data-visualization && python evaluation.py`, then copy
`figures/05_*.pdf` to `figures/13_*.pdf` into `paper/figures/`.

Writing rules for this draft: no em dashes and no semicolons, plain words over AI-sounding ones, every number traced
to a file in the repository, and every limitation stated where the claim is made.
