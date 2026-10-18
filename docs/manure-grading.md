# Manure Grading (proposal)

Written 2026-10-17. The product vision is that the same camera **(1) flags disease from droppings** and **(2) rates the droppings as manure**, sorting each batch into a manure grade. This doc covers (2). Sources are listed in research.md under "Dropping quality grading" and "Manure grading".

## What a camera can and can't tell us
| Property | From an RGB camera? | Notes |
|---|---|---|
| Wetness / consistency | **Yes, estimated** | Watery droppings spread out, look shiny, have no firm shape (Nakrosis 2023 "high moisture" class) |
| Contamination | **Yes** | Feathers, bedding/litter, spilled feed, foreign objects |
| Freshness | **Yes** | The new-dropping trigger in vision-design-v2 timestamps each dropping |
| Source group and its health | **Yes** | Group assignment + the disease/abnormal detector |
| Nitrogen / phosphorus / potassium (fertilizer value) | **No** | Needs a lab test or an NIR spectrometer. FT-NIR measured total N (R² 0.82) and moisture (R² 0.93) on farm (Tamburini 2015). Future add-on sensor, not the camera |
| Pathogens present | **No (only a risk signal)** | A lab test confirms. The camera only raises the risk tier |

## Grades
Manure is handled in **batches** (a manure-belt run, a tray, a pen clean-out), not one dropping at a time. So the grade is computed **per group per collection period**, from all droppings detected in it.

| Grade | Rule (all droppings in the batch) | What the farmer does with it |
|---|---|---|
| **A: Premium** | Group healthy (no abnormal alerts), mostly firm droppings, low contamination | Best for composting or pelleting as fertilizer |
| **B: Standard** | Group healthy, but many wet droppings or mixed with bedding/feathers | Usable, but needs extra drying or longer composting |
| **C: Restricted** | Abnormal droppings detected in this group during the period | Keep separate, and compost with a validated heat process before any use. FSMA example: static compost at ≥131 °F for 3 days, or turned compost for 15 days (secondary summary; verify against 21 CFR 112.54/56). Never apply raw |
| **Hold** | Suspected high-consequence or reportable disease (e.g. Newcastle-like) | Don't move off-farm; follow the vet / animal-health authority |

Consistency terms come from manure handling guides. Solid is >20% solids (stackable), semi-solid/slurry is 5–20%, and liquid is <5%. Poultry manure is normally solid, so we use firm / moist / wet as visual proxies, not measured percentages.

## How it plugs into the pipeline
No new model is needed for the first version. Grading is a rule layer on top of what the vision stack already produces:
```
dropping detections (box, class/abnormal score, group_id, time)
  + per-dropping attributes: wetness (watery/foamy), contamination flags
  -> batch summary per group per period: % firm/moist/wet, % contaminated, # abnormal
  -> grade A/B/C/Hold + reasons ("62% wet droppings", "2 abnormal in group 3")
```
- Wetness: start with the Machuve disease labels and simple measurements (spread vs size, shine, urate cap). Later, train attribute labels (watery, foamy, undigested feed, blood) on a few hundred hand-labelled crops.
- Contamination: needs our own images (feathers, bedding). No public dataset found.
- Event schema addition: `manure: {wetness, contamination, grade, reasons[]}` on the batch summary.

## Pitch line
"The camera that warns you about sick birds also tells you which manure is safe and valuable: premium batches go to fertilizer, and batches from suspect groups are flagged for heat treatment before anyone spreads them."

## Open questions
- Disease naming: this doc assumes disease detection is part of the vision. The repo's current decision (BIBLE.md, vision-design-v2.md) is "no disease names in the product". Agree on wording, e.g. "suspected coccidiosis-like, confirm with vet".
- Batch unit: belt run, tray, or pen clean-out? Depends on housing (cages vs floor groups).
- Should Grade C/Hold also trigger the farmer alert, or only the manure report?
- Is an NIR sensor worth adding later for real nutrient values?
