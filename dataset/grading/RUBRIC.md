# Holy-Crap dropping grade, rubric v1

A 1 to 10 grade for how normal a single chicken dropping looks in a photo, built from six named visual
variables. 10 is a textbook normal dropping. The grade describes appearance only. It is not a diagnosis.
Disease status for every photo comes separately from the source dataset's PCR results.

The variables follow the signs used in clinical flock checks of droppings: a well formed dropping with a
white urate cap is normal, while loose or watery droppings, a missing cap, mucus, blood, red or yellow
discolouration and visible feed particles point to poor intestinal health (see SOURCES in DATASHEET.md).

## The six variables

Score each one 0, 1 or 2. Score `null` when the photo does not let you judge it (blurred, cropped, the
dropping is mixed into litter, glare). Never guess a value you cannot see.

| Key | Variable | 0 normal | 1 mild | 2 marked |
|---|---|---|---|---|
| `form` | Consistency and form | Formed, holds its shape, firm or slightly soft | Pasty or soft, shape partly lost, smeared | Loose, watery or liquid, no shape, spreads out |
| `cap` | White urate cap | Distinct white cap present | Thin, small, smeared or partly mixed in | Absent, or urates yellow or green instead of white |
| `color` | Colour of the faecal part | Brown, grey brown or green brown | Unusual tint: pale, yellowish, very dark, orange cast | Strongly abnormal: red, bright green, black and tarry, or chalky white throughout |
| `blood` | Blood | None visible | Small streaks or specks of red | Obvious blood, red or red brown dominates |
| `mucus` | Mucus or foam | None visible | Some mucus strands, sheen or a few bubbles | Frothy or foamy, or heavy mucus |
| `feed` | Undigested feed | None visible | A few visible feed particles | Many feed particles, feed clearly passed through |

## The grade

    penalty = form + cap + color + 2 * blood + mucus + feed        (blood counts double)
    grade   = max(1, 10 - penalty)                                 (variables scored null count as 0)

The grade is computed from the variables, never chosen directly, so anyone can recompute it and every
point lost has a named reason. `coverage` is the number of variables that were not null (0 to 6). A grade
with coverage under 4 is reported but flagged as low confidence.

| Grade | Label | Meaning |
|---|---|---|
| 10 | Gem | Nothing abnormal seen on any variable |
| 9 | Mint | One mild finding |
| 8 | Near mint | Two mild findings, or one marked |
| 6 to 7 | Fair | Several findings |
| 4 to 5 | Poor | Clearly abnormal |
| 1 to 3 | Severe | Many marked findings, usually including blood |

## Photo quality

Each photo also gets `quality`: `good` (dropping clearly visible), `partial` (visible but blurred, small or
partly covered) or `unusable` (no dropping can be judged). Unusable photos get all variables null.

## Rules for raters

1. Judge only what is visible in the photo. Do not infer a disease, and do not let a guess about the disease
   change a score.
2. Score each variable on its own. A watery dropping does not automatically lose its cap.
3. If there are several droppings, score the most central, best visible one and describe it in `note`.
4. `note` is one short sentence in plain words about what you saw, at most 120 characters.
