# Holy-Crap Dropping Grades: datasheet

A 1 to 10 appearance grade, with six named sub-scores, for each of the 1,255 PCR annotated chicken dropping
photos of Machuve et al. Grades were assigned by three independent AI raters following a written rubric.
No veterinarian or human expert graded these photos. Read the limitations before using the grades.

## Motivation

The source photos carry a disease label from PCR (coccidiosis, Newcastle disease, Salmonella or none), but
nothing about how a dropping looks. Farmers and screening tools work from appearance. This set adds a
documented, reproducible appearance grade so models can be benchmarked on it next to the PCR labels.

## Composition

- 1,255 photos: 373 coccidiosis, 347 healthy, 186 Newcastle disease, the rest Salmonella (from the PCR zips).
- Per photo (`release/grades.csv`): the six sub-scores (`form`, `cap`, `color`, `blood`, `mucus`, `feed`,
  each 0, 1, 2 or empty), the grade, `coverage` (how many sub-scores could be judged), `grade_spread` (how far
  the three raters' grades were apart), photo `quality`, the PCR class, and the source zip, file name and md5 so
  every row can be traced back to the original photo.
- Every individual rating, with each rater's short note (`release/ratings_raw.csv`).
- Agreement numbers (`release/agreement.json`).
- The photos themselves are not redistributed. Get them from the source record and match by md5.

## How the grades were made

1. **Rubric.** `RUBRIC.md` defines six variables, each scored 0 to 2, from signs used in clinical flock checks
   of droppings. The grade is computed, `max(1, 10 - penalty)` with blood counting double, never chosen by a
   rater, so every lost point has a named reason.
2. **Blinding.** `prepare.py` gave every photo a random ID, re-encoded it at 768 pixels with no metadata, and
   kept the key (ID to file name and PCR class) outside the working folder until grading ended.
3. **Raters.** Three AI raters, each a separate Claude model run with no shared context:
   rater-a Claude Opus, rater-b Claude Sonnet, rater-c Claude Haiku. Each received the same instructions
   (`RATER_PROMPT.md`), saw only the photos, and graded them in its own random order.
4. **Repeats.** 126 photos (10 percent) appear twice under different IDs to measure each rater's agreement
   with itself.
5. **Consensus.** Each released sub-score is the median of the raters who could judge it, needing at least two.
   The grade is recomputed from the consensus sub-scores.
6. **Agreement.** Krippendorff's alpha (ordinal) across the three raters per variable and for the grade,
   quadratic weighted Cohen's kappa for each pair, and each rater's kappa with itself on the repeats.

## Results

From `release/agreement.json` and `release/grade_vs_models.json` (all 1,255 photos, 1,381 images per rater):

| Measure | Value |
|---|---|
| Krippendorff's alpha (ordinal), grade | 0.76 |
| Alpha per variable | form 0.70, cap 0.75, colour 0.56, blood 0.74, mucus 0.66, feed 0.57 |
| Pairwise weighted kappa, grade | Opus~Sonnet 0.84, Opus~Haiku 0.72, Sonnet~Haiku 0.71 |
| Self agreement on 126 repeats, weighted kappa | Opus 0.86, Sonnet 0.83, Haiku 0.71 |
| Self agreement, identical grade | Opus 47%, Sonnet 45%, Haiku 37% |
| Photo quality | 915 good, 331 partial, 9 unusable |
| Grades spread by 3 or more between raters | 234 photos |

| PCR class | n | Mean grade | Grade 9 or 10 |
|---|---|---|---|
| Healthy | 347 | 8.6 | 62% |
| Salmonella | 347 | 8.0 | 47% |
| Coccidiosis | 366 | 5.6 | 7% |
| Newcastle disease | 186 | 4.6 | 1% |

A single grade is precise to about one point: the raters agree with themselves closely but rarely give the exact
same number twice.

## Limitations

- **AI raters, not experts.** The grades say what three AI models saw when following the rubric. They are not
  validated against veterinarians. Agreement between the raters measures consistency, not correctness.
- **Related raters.** The three models come from one vendor and may share blind spots, which would make
  agreement look higher than independent humans would reach.
- **Appearance is not disease.** PCR detects a pathogen in the sample. A PCR positive bird can pass a normal
  looking dropping and the reverse. The grade by PCR class is reported as a sanity check, not as accuracy.
- **Photo conditions.** Phone photos from farms in Arusha and Kilimanjaro, Tanzania (layers, cross and
  indigenous breeds, September 2020 to February 2021), with varied light, focus and litter.
- **New scale.** The rubric is new. It is not a published, validated poultry scoring system.

## License and credit

Grades, ratings and rubric: CC BY 4.0. The photos and PCR labels are by Machuve, Nwankwo, Lyimo and
colleagues, CC BY 4.0, and must be credited when this set is used:

- Machuve D, Nwankwo E, Lyimo E, Maguo E, Munisi C. Machine Learning Dataset for Poultry Diseases
  Diagnostics, PCR annotated (version 3). Zenodo, 2021. doi:10.5281/zenodo.5801834
- Machuve D, Nwankwo E, Mduma N, Mbelwa J. Poultry diseases diagnostics models using deep learning.
  Frontiers in Artificial Intelligence 5:733345, 2022. doi:10.3389/frai.2022.733345

## SOURCES

- Clinical signs in droppings (formed with a white urate cap is normal, loose, capless, mucus, blood, red or
  yellow colour and feed particles are abnormal): Engormix, Intestinal integrity in broilers.
- Agreement statistics: Krippendorff's alpha for several raters and missing data, weighted kappa for ordinal
  scales, and self-inconsistency of AI judges (arXiv 2510.27106, arXiv 2506.13639).
