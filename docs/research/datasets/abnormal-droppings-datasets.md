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
