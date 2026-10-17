# Machuve et al. fecal datasets (Tanzania)

- Type: dataset
- Summary: two public chicken-fecal image datasets from Tanzania: a large
  farm-labeled set (v2) and a smaller PCR-annotated set (v3): with
  acknowledged label-quality caveats and an unresolved license.
- Why we care: the closest public data to "classify chicken droppings from
  images", and a cautionary tale about labels.

## Evidence

### v2: farm-labeled (Zenodo)

`[read]` [https://zenodo.org/records/4628934](https://zenodo.org/records/4628934)

- 6,812 labeled fecal images: coccidiosis 2,103; healthy 2,057; salmonella
  2,276; Newcastle disease 376.
- Smartphone images collected in Arusha and Kilimanjaro, Tanzania, 2020-2021.
- Healthy/coccidiosis samples came from farm observations; Salmonella/Newcastle
  samples followed inoculation.
- Includes YOLO object-detection and JSON segmentation annotations.
- About 11.3 GB.
- The record exposes downloads but displays no explicit license. Do not assume
  permission to redistribute, modify, or use the data in a product; obtain
  written clarification or an explicit license first.
- Acquisition context is partly confounded with class: healthy/coccidiosis
  images came from farm observations while Salmonella/Newcastle images
  followed inoculation. A random image split may learn collection context,
  phone, background, or husbandry conditions rather than fecal pathology.

### v3: PCR-annotated (Zenodo)

`[read]` [https://zenodo.org/records/5801834](https://zenodo.org/records/5801834)

- 1,255 PCR-annotated images: coccidiosis 373; healthy 347; salmonella 349;
  Newcastle 186.
- About 4.4 GB.
- The record exposes downloads but displays no explicit license.
- PCR detection is stronger pathogen evidence, but it does not by itself
  prove that the detected organism caused the visible appearance or the
  bird's clinical condition. A sample negative for the assayed targets is not
  a comprehensive diagnosis of health, and co-infection remains possible.

### Primary paper

`[read]` [https://pmc.ncbi.nlm.nih.gov/articles/PMC9376463/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9376463/)

- Only 16% of samples formed the PCR-tested subset; the 6,812-image set used
  farm labels.
- The authors acknowledge likely label errors, especially Salmonella versus
  healthy, because white coloring overlaps and texture distinctions can be
  subjective.
- Never treat farm-labeled and PCR-labeled datasets as interchangeable.
- Some downstream papers collapse v2 and v3 into 8,067 images and describe the
  combined collection as PCR-positive. That conflicts with the primary record:
  6,812 images are farm-labelled and 1,255 are PCR-annotated. Do not count such
  downstream reuse as independent replication or laboratory confirmation
  ([2026 example](https://doi.org/10.11975/j.issn.1002-6819.202601168)).
- The reported training mixed label sources and used an 80/20 image split;
  the test set used farm labels. No held-out-farm, bird, or collection-session
  evaluation was reported. MobileNetV2/Xception results of 98.02–98.24%
  measure agreement with those labels, not laboratory-confirmed diagnostic
  accuracy or expected new-barn performance.

## Limits / open questions

- Reuse terms are unresolved. Download access alone does not establish
  permission for redistribution, modification, or product use.
- Farm labels carry acknowledged error risk; PCR labels are few (1,255 images).
- Collection context is smartphone photography, not overhead barn cameras.
  Domain shift to litter footage is untested (our inference).
- Preserve source and collection metadata; use held-out farms/sessions where
  metadata permit rather than a random image split.
- Disease-class proportions are imbalanced: Newcastle disease is a small
  minority in both sets (376 of 6,812; 186 of 1,255).

## Connects to

- [../observables/camera-visible-health-signals.md](../observables/camera-visible-health-signals.md)
- [../evidence/clinical-limits-of-visual-diagnosis.md](../evidence/clinical-limits-of-visual-diagnosis.md)
- [../PAPER.md](../PAPER.md)

## Sources

- v2 record `[read]`: [https://zenodo.org/records/4628934](https://zenodo.org/records/4628934)
- v3 record `[read]`: [https://zenodo.org/records/5801834](https://zenodo.org/records/5801834)
- Primary paper `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC9376463/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9376463/)
- 2025 poultry CV survey `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S0032579125000215](https://www.sciencedirect.com/science/article/pii/S0032579125000215)
