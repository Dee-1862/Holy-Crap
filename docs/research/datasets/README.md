# Datasets

- [machuve-fecal-datasets.md](machuve-fecal-datasets.md): the Machuve et al. Tanzanian fecal datasets
  (v2 farm-labeled, v3 PCR-annotated) and their caveats.
- [abnormal-droppings-datasets.md](abnormal-droppings-datasets.md): appearance-based normal/abnormal
  datasets from conveyor, litter-floor, and controlled-cage studies.

## Not yet a node

- A Nigerian binary healthy/unhealthy fecal dataset (14,618 images at
  100x100 px) is reported in the 2025 poultry CV survey `[skimmed]`
  ([https://www.sciencedirect.com/science/article/pii/S0032579125000215](https://www.sciencedirect.com/science/article/pii/S0032579125000215)).
  We have not located or reviewed the dataset itself; do not add details
  beyond what the survey states.

## General caveats

- License: the Machuve records expose downloads but display no explicit
  license. Do not assume permission to redistribute, modify, or use the data
  in a product; obtain written clarification or an explicit license. See
  [machuve-fecal-datasets.md](machuve-fecal-datasets.md).
- Label quality: farm-labeled and PCR-labeled images carry different evidence
  strength and must not be mixed without care. See
  [machuve-fecal-datasets.md](machuve-fecal-datasets.md).
- Field gap: public fecal datasets are smartphone/lab photography, not
  footage from a barn camera on litter. Expect a domain gap (see [../PAPER.md](../PAPER.md)).
