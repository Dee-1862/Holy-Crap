# Kaggle `chicken-disease-1` integration audit

- Dataset: [Chicken Disease Image Classification](https://www.kaggle.com/datasets/allandclive/chicken-disease-1/data)
- Kaggle owner: `allandclive`
- Kaggle version: 1, published April 3, 2022
- Audit date: October 17, 2026
- Recommendation: useful for the feces-classification stage, but not for finding
  droppings in an overhead pen video and not as direct evidence that a pen is
  infected.

## What is actually in the download

The Kaggle API reports 294,125,618 bytes (280.5 MiB) across 8,068 files:
8,067 RGB JPEGs and one 219,521-byte CSV. The images are resized to 224x224.
There is no provided validation or test split.

```text
Train/
  cocci.<n>.jpg       2,103 farm-labelled images
  healthy.<n>.jpg     2,057 farm-labelled images
  ncd.<n>.jpg           376 farm-labelled images
  salmo.<n>.jpg       2,276 farm-labelled images
  pcrcocci.<n>.jpg      373 PCR-annotated images
  pcrhealthy.<n>.jpg    347 PCR-annotated images
  pcrncd.<n>.jpg        186 PCR-annotated images
  pcrsalmo.<n>.jpg      349 PCR-annotated images
train_data.csv        images,label
```

The CSV has one unique filename per row and combines the two label sources into
four classes:

| CSV label | Farm-labelled | PCR-annotated | Total | JPEG bytes |
| --- | ---: | ---: | ---: | ---: |
| `Coccidiosis` | 2,103 | 373 | 2,476 | 83,950,898 |
| `Healthy` | 2,057 | 347 | 2,404 | 82,348,553 |
| `New Castle Disease` | 376 | 186 | 562 | 26,497,409 |
| `Salmonella` | 2,276 | 349 | 2,625 | 101,109,237 |

Newcastle disease is only 6.97% of the images, so overall accuracy can hide
poor performance on that class. Keep per-class recall, precision, F1, and the
confusion matrix alongside the headline accuracy.

The files are feces-oriented smartphone photos, not whole-pen images or video.
Eight representative images were inspected without downloading the archive.
They show close-range deposits with soil, litter, trays, or other background;
they are not clean cut-outs of feces. They contain no chicken identity,
movement, pen-level timeline, or bounding-box coordinates. One inspected file
also retained GPS-related EXIF metadata, so raw files should be metadata-scrubbed
before any redistribution.

## Origin and label quality

The counts and filename prefixes match two datasets by Machuve and colleagues:

- [Farm-labelled dataset, DOI 10.5281/zenodo.4628934](https://doi.org/10.5281/zenodo.4628934):
  6,812 images labelled with help from animal-health professionals. Its source
  record also includes YOLO object-detection and JSON segmentation annotations,
  which are not included in this Kaggle mirror.
- [PCR-annotated dataset, DOI 10.5281/zenodo.5801834](https://doi.org/10.5281/zenodo.5801834):
  1,255 images linked to tested fecal samples.
- [Primary paper](https://doi.org/10.3389/frai.2022.733345): describes the
  collection, labels, model experiments, and known confusion between visually
  similar healthy and Salmonella samples.

The `pcr*` prefixes carry stronger evidence than the farm labels. Do not erase
that distinction during training or evaluation. PCR detection still means a
target was detected in the linked sample; it does not prove that the visible
appearance was caused by that organism or that a negative sample was healthy
in every clinical sense.

The Kaggle record says its license is `Unknown`. The Zenodo API metadata for
both apparent source records identifies `CC BY 4.0`. For reproducible training,
prefer the two Zenodo records, retain attribution and DOI provenance, and
confirm that each Kaggle file maps to those sources before redistributing the
Kaggle mirror itself.

## Leakage and evaluation risks

The Kaggle archive puts every image in `Train/`; `train_data.csv` contains only
`images` and `label`. It provides no farm, bird, date, session, burst, or sample
identifier for a grouped split. The primary paper reports an 80/20 image split
with 15% of training used for validation, but does not report holding out farms,
birds, or collection sessions. A random split can therefore reward repeated
background, phone, farm, or capture-session cues.

A 2026 preprint, [FecalFed](https://arxiv.org/abs/2604.00559), found extensive
cross-repository contamination while combining the original Zenodo collection
with two Roboflow derivatives: 7,743 of 16,513 images were removed as duplicate
or near-duplicate, and 19 duplicate groups had conflicting labels. That study
does **not** report an internal duplicate rate for this Kaggle archive, so its
46.89% figure must not be assigned to Kaggle. It does show why copies from
Kaggle, Zenodo, and Roboflow must be deduplicated together before splitting.

Before trusting a model result:

1. Recover source provenance and grouping metadata where possible.
2. Detect exact and near duplicates before creating splits. Hashes should catch
   resized and recompressed copies, not only byte-identical files.
3. Split by farm and collection session, then keep all related crops and frames
   in the same partition.
4. Report results separately for farm-labelled and PCR-annotated images.
5. Reserve a final test set made from the actual overhead camera and litter
   conditions. The smartphone result is not the expected overhead-video result.

## Integration contract for the five-minute video pipeline

This classifier belongs after a separate feces detector or segmenter:

```text
five-minute pen video
  -> sample frames / find candidate deposition events
  -> detect or segment visible droppings
  -> associate repeated sightings of the same deposit
  -> choose one or a few useful RGB crops per unique deposit
  -> run the four-class feces classifier
  -> aggregate crop evidence into one video-level feces summary
```

Do not run the classifier on the whole pen frame. A 224x224 training photo may
contain far more feces pixels than an overhead frame. If the detected deposit
is too small, blurred, occluded, or compressed to support the classifier,
return `not_evaluable` instead of upscaling it into a confident prediction.
Preserve color in candidate crops because the source annotation process
explicitly used color and shape cues.

Each classifier artifact should ship with a manifest containing:

```json
{
  "task": "feces_crop_classification",
  "artifact_id": "team-model-name-and-version",
  "artifact_sha256": "...",
  "runtime": "tflite-or-onnx",
  "input": {
    "width": 224,
    "height": 224,
    "channels": "RGB",
    "dtype": "uint8-or-float32",
    "normalization": "exact-training-transform"
  },
  "class_order": [
    "coccidiosis",
    "healthy",
    "newcastle_disease",
    "salmonella"
  ],
  "source_label_map": {
    "Coccidiosis": "coccidiosis",
    "Healthy": "healthy",
    "New Castle Disease": "newcastle_disease",
    "Salmonella": "salmonella"
  },
  "calibration": {
    "unknown_threshold": null,
    "method": "documented-by-model-owner"
  },
  "evaluation": {
    "reported_accuracy": 0.83,
    "split_unit": "must-be-documented",
    "per_class_metrics": "required",
    "overhead_camera_validation": "required-before-field-claims"
  }
}
```

The crop request should include `video_id`, `frame_id`, `timestamp_ms`, a stable
`deposit_id`, bounding box or mask, detector confidence, crop padding, and all
preprocessing applied. The classifier response should return the four raw or
calibrated scores, predicted class, confidence, model version/hash, latency,
and an `evaluable` flag with a reason when false.

Aggregate by unique `deposit_id`, not by frame, or a single dropping visible for
several minutes will dominate the result. The five-minute summary should show:

- detector coverage and number of unique candidate deposits;
- evaluable versus rejected crops;
- class proportions and confidence distribution across unique deposits;
- representative crops for review; and
- a clearly marked deterministic placeholder when the real detector or
  classifier is not active.

Call these outputs **feces appearance signals** or **model classifications**,
not confirmed infections. The team's reported 83% is artifact-level evaluation
metadata until its split method and per-class performance are documented, and
it does not transfer automatically to overhead video.

## Audit method and sources

This audit used the public Kaggle metadata and paginated file-list APIs, the
219 KB label CSV, and eight representative JPEGs. The full 280.5 MiB archive
was not downloaded.

- [Kaggle dataset](https://www.kaggle.com/datasets/allandclive/chicken-disease-1/data)
- [Kaggle API metadata](https://www.kaggle.com/api/v1/datasets/view/allandclive/chicken-disease-1)
- [Farm-labelled Zenodo source](https://zenodo.org/records/4628934)
- [PCR-annotated Zenodo source](https://zenodo.org/records/5801834)
- [Primary paper](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2022.733345/full)
- [FecalFed deduplication preprint](https://arxiv.org/abs/2604.00559)
