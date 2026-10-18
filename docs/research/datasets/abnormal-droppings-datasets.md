# Appearance-based abnormal-droppings datasets

- Type: dataset evidence
- Summary: these studies label visible abnormality, not pathogens. They are
  more relevant to the MVP than disease-name classification, but their
  controlled settings and split methods limit transfer to an occupied pen.
- Why we care: they suggest useful annotation categories and expose the gap
  between published image metrics and our temporal, litter-floor task.

## Wang et al. (2019)

`[read]` [https://onlinelibrary.wiley.com/doi/10.1155/2019/3823515](https://onlinelibrary.wiley.com/doi/10.1155/2019/3823515)

- 7,637 final images covering normal droppings and abnormal shape, color,
  water content, and combined shape/water appearance.
- Labels were visual veterinary judgments, not pathogen or laboratory labels.
- Images came from a controlled conveyor-belt setup with the camera 0.3 m
  above the belt.
- Faster R-CNN reported 99.1% recall and 93.3% mAP; YOLOv3 reported 88.7%
  recall and 84.3% mAP. These are study results, not expected barn performance.
- Data are available only by author request.
- Augmentation occurred before the reported final train/test accounting, so
  independence of derived images across splits is not established.

## Nakrosis et al. (2023)

`[read]` [https://pmc.ncbi.nlm.nih.gov/articles/PMC10571708/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10571708/)

- 487 litter-floor images from three Lithuanian farms, using six visual
  abnormality classes defined with veterinary input.
- Reported best results were 91.78% classification accuracy, 92.41% object-
  detection accuracy, and a 0.8875 Dice coefficient for K-means segmentation.
- The dataset is small and imbalanced, and is available only from the authors
  on request.
- The authors treat links from visual classes to disease causes as assumptions
  that require diagnostic verification.

## He et al. (2024)

`[abstract only]` [https://pubmed.ncbi.nlm.nih.gov/38587413/](https://pubmed.ncbi.nlm.nih.gov/38587413/)

- 1,650 RGB images from 60 broilers in five SPF cages.
- Normal, abnormal-shape, and abnormal-color segmentation; reported mDice
  79.43% after a random 8:2 image split.
- The work supports semantic segmentation for overlapping droppings. It does
  not validate pathogen detection, clinical outcomes, temporal detection of a
  newly deposited dropping, or generalization to another flock or farm.

## Aworinde/Adebayo Nigeria collection (2023)

`[read]` [paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10477973/),
[dataset](https://data.mendeley.com/datasets/8pnbzpt2k9/1)

- 14,618 CC BY 4.0 smartphone images at 100×100 pixels: 7,991 labelled
  healthy and 6,627 non-healthy.
- Animal scientists and farmers verified the visual labels; there was no
  laboratory or pathogen testing. Treat it only as binary visual-abnormality
  data, not disease or health ground truth.
- Burst capture and only 94 reported physical instances create serious
  near-duplicate and grouped-split leakage risk. Separate evaluation by
  physical instance, farm, and acquisition period where identifiers permit.
- Morning, afternoon, and night folders do not identify individual birds or
  repeated samples, so this is not a longitudinal dataset. The paper contains
  a conflicting raw-image count; cite only the consistent 14,618 final total.

## Zhou et al. manure-belt growth-cycle collection (2023)

`[read]` [paper](https://www.ijabe.org/index.php/ijabe/article/download/7732/pdf),
[DOI](https://doi.org/10.25165/j.ijabe.20231601.7732)

- Video frames were collected at the end of a manure belt through one 43-day
  broiler growth cycle: 2,098 raw images, augmented to 5,314, with 1,000
  selected for train/validation/test (569 normal, 431 abnormal).
- This is the closest reviewed longitudinal droppings collection, but it is a
  belt-end appearance dataset, not an in-pen deposition-event dataset.
- Labels were visual and veterinary-advised, not laboratory/pathogen
  confirmed. The reported 98.8% should not be read as independent clinical
  accuracy: augmentation preceded final selection, and the paper does not
  describe grouped splits by source frame, session, or day.
- It cannot support bird attribution, new-deposit detection, or disease
  diagnosis.

## Big Broiler defecation-action precursor (2025)

`[read]` [repository](https://github.com/decide-ugent/big-broiler-dataset),
[paper](https://biblio.ugent.be/publication/01K47TCM11DQFAY9ECSWKKV7C6/file/01K47TEMS4W9984XERQWHDHJHF.pdf),
[dataset page](https://decide.ugent.be/datasets/big-broiler/)

- Human-labelled `Defecating` actions are attached to tracked broilers,
  including a 140-bird angled-view pen and a small overhead setup.
- The released tracklets average about 73 seconds, and the paper notes
  relatively low stocking density.
- It does not label the resulting fecal deposit, its location or appearance,
  or persistent identity across clips. It is a behavioral event-cue precursor,
  not proof of bird-to-dropping attribution.

## Essien et al. long-running overhead collection (2026)

`[read]` [paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC13199025/),
[restricted record](https://doi.org/10.5281/zenodo.18735885)

- 150 floor-housed layers across five barns were recorded continuously for 22
  weeks with overhead RGB video, audio, periodic thermal imaging, and
  environmental sensors.
- It may help with self-supervised pretraining, capture-system testing,
  long-run reliability, and age/time baselines.
- It has no manual behavior, health, welfare, fecal, or pathogen labels, and
  raw access requires a Data Access Agreement. It is not supervised disease or
  droppings ground truth.

## Project implication

Reuse the annotation idea (normal appearance, abnormal shape, abnormal color,
and abnormal water content) only as a starting ontology. Collect video from
the actual overhead camera, annotate deposition events separately from static
appearance, preserve flock/date/session boundaries, and evaluate on held-out
acquisition units. Disease names do not belong in this MVP label set.

## Connects to

- [machuve-fecal-datasets.md](machuve-fecal-datasets.md)
- [../observables/camera-visible-health-signals.md](../observables/camera-visible-health-signals.md)
- [../evidence/clinical-limits-of-visual-diagnosis.md](../evidence/clinical-limits-of-visual-diagnosis.md)
- [../PAPER.md](../PAPER.md)
