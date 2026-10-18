# Camera-visible health signals

- Type: observable
- Summary: a fixed overhead RGB camera can see behavior, activity,
  distribution, and droppings; it cannot see disease.
- Why we care: everything the product promises must start from what the
  sensor can actually observe.

## What a top-down camera can potentially observe

Keep three evidence levels separate:

- **Supported in field/commercial-house research:** flock activity and spatial
  distribution or zone occupancy.
- **Supported in controlled studies:** some gait and movement features,
  including speed, steps, and lateral oscillation.
- **Plausible but unvalidated in our setting:** individual isolation,
  persistent inactivity, unresponsive-bird detection, crowding/piling, coarse
  feather condition, and deposition of new droppings.

Two field results anchor the achievable end. USDA ceiling-camera research
`[read]` ([https://www.ars.usda.gov/research/publications/publication/?seqNo115=379745](https://www.ars.usda.gov/research/publications/publication/?seqNo115=379745))
found floor distribution across feeding, drinking, and resting areas can act
as a welfare/health indicator. A study of monocular cameras in commercial
broiler houses `[read]`
([https://pureadmin.qub.ac.uk/ws/portalfiles/portal/553403602/A_computer_vision_approach.pdf](https://pureadmin.qub.ac.uk/ws/portalfiles/portal/553403602/A_computer_vision_approach.pdf))
supports flock/group activity monitoring. Group- and zone-level monitoring is
evidenced; per-bird diagnosis is not.

Top-view activity/distribution combined with age and weight predicted
pen-average gait score in small experimental pens in Yang et al.
`[abstract only]` ([https://pubmed.ncbi.nlm.nih.gov/36584623/](https://pubmed.ncbi.nlm.nih.gov/36584623/)).
Fodor et al. `[abstract only]` found top-view speed, steps, and lateral
oscillation useful for gait in a controlled corridor, but these features gave
little information about mild hock burn or footpad dermatitis
([https://pubmed.ncbi.nlm.nih.gov/39793240/](https://pubmed.ncbi.nlm.nih.gov/39793240/)).
Neither establishes unrestricted crowded-pen individual gait diagnosis.

Behavior also needs age- and time-specific baselines. A 2026 controlled
disease-challenge study `[abstract only]` found behavior was driven strongly
by age and time of day; Eimeria challenge sometimes increased rather than
decreased locomotion, while IBV+APEC produced modest activity changes
([https://pubmed.ncbi.nlm.nih.gov/42117450/](https://pubmed.ncbi.nlm.nih.gov/42117450/)).
“Less movement means sick” is not a safe universal rule.

## What it cannot reliably reveal

- subclinical disease (by definition it has no visible signs),
- internal lesions,
- pathogen identity,
- laboratory confirmation,
- precise individual intake (feed/water per bird),
- whether a given dropping is illness-related. In a 73-sample study, age
  significantly affected color, texture, pH, dry matter, and chemical
  composition, so appearance needs an age/flock baseline
  ([Mozuriene et al., 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11083088/),
  `[read]`). Samples were visually grouped and chemically characterized, not
  pathogen-confirmed disease cases.

## What the authorities say the visible signs are

USDA "how to spot sickness" `[read]`
[https://www.aphis.usda.gov/livestock-poultry-disease/avian/defend-the-flock/how-to-spot-sickness](https://www.aphis.usda.gov/livestock-poultry-disease/avian/defend-the-flock/how-to-spot-sickness)

- Visible indicators include changes in energy, appetite, movement, breathing,
  head/comb, production, and greenish watery diarrhea.
- USDA presents them as possible signs of avian influenza or other avian
  diseases. They are warning signs, not diagnoses.

WOAH Newcastle disease `[read]` [https://www.woah.org/en/disease/newcastle-disease/](https://www.woah.org/en/disease/newcastle-disease/)

- Signs vary widely and can include respiratory signs, depression, nervous
  signs, and diarrhea.
- It can resemble avian influenza; laboratory testing is needed to confirm.

USDA APHIS avian influenza `[read]`
[https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza](https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza)

- HPAI signs can include sudden death, reduced energy/appetite, egg changes,
  head/comb swelling or discoloration, respiratory signs, torticollis,
  stumbling, and diarrhea.
- LPAI may produce no signs at all.

MSD Veterinary Manual, coccidiosis `[read]`
[https://www.msdvetmanual.com/poultry/coccidiosis-in-poultry/coccidiosis-in-poultry?query=broiler](https://www.msdvetmanual.com/poultry/coccidiosis-in-poultry/coccidiosis-in-poultry?query=broiler)

- Coccidiosis can cause poor growth, reduced intake, weight loss, diarrhea,
  and mortality. Confirmation uses fecal examination/microscopy together
  with lesion and flock context; mixed infections are common, and relevant
  internal lesions are invisible to the camera.

None of these lists is specific to one disease; several signs overlap across
diseases. See [../evidence/clinical-limits-of-visual-diagnosis.md](../evidence/clinical-limits-of-visual-diagnosis.md).

## Droppings framing

Abnormal droppings segmentation study `[abstract only]`
[https://pmc.ncbi.nlm.nih.gov/articles/PMC11285374/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11285374/)

- 1,650 images; 60 broilers in five SPF cages.
- Normal, abnormal-shape, and abnormal-color segmentation; reported mDice
  79.43% after a random 8:2 image split.
- Supports semantic segmentation as a way to label overlapping droppings.
  It does not validate disease diagnosis, clinical outcomes, temporal new-
  dropping detection, or new-flock generalization.

Our inference: the defensible product claim is "abnormal-looking droppings
flagged for review", not "dropping labeled with a pathogen".

## Limits / open questions

- Coarse body/feather condition depends on resolution and mount height -
  unknown until the camera inventory is resolved (see [../../BIBLE.md](../../BIBLE.md)).
- Gait proxies from top view are plausible, but the reviewed evidence comes
  from small pens or controlled walkways; validate them in the mounted pen.
- Dropping color and texture are differential clues, not diagnoses.
  Veterinary diagnostic guidance distinguishes normal loose cecal droppings
  from diarrhea and associates some appearances with conditions to
  investigate, but directs confirmation through fecal parasitology or culture,
  PCR, histology, or postmortem examination as appropriate. The product may
  display measured appearance features and recommend review or sampling; it
  must not translate a color directly into a disease label
  ([University of Guelph Animal Health Laboratory](https://www.uoguelph.ca/ahl/content/diagnosing-enteric-disease-backyard-chickens),
  `[read]`).

## Connects to

- [../evidence/clinical-limits-of-visual-diagnosis.md](../evidence/clinical-limits-of-visual-diagnosis.md)
- [../datasets/machuve-fecal-datasets.md](../datasets/machuve-fecal-datasets.md)
- [../identity/README.md](../identity/README.md)
- [../PAPER.md](../PAPER.md)

## Sources

- USDA distribution research `[read]`: [https://www.ars.usda.gov/research/publications/publication/?seqNo115=379745](https://www.ars.usda.gov/research/publications/publication/?seqNo115=379745)
- Commercial-broiler-house activity paper `[read]`: [https://pureadmin.qub.ac.uk/ws/portalfiles/portal/553403602/A_computer_vision_approach.pdf](https://pureadmin.qub.ac.uk/ws/portalfiles/portal/553403602/A_computer_vision_approach.pdf)
- USDA spotting sickness `[read]`: [https://www.aphis.usda.gov/livestock-poultry-disease/avian/defend-the-flock/how-to-spot-sickness](https://www.aphis.usda.gov/livestock-poultry-disease/avian/defend-the-flock/how-to-spot-sickness)
- WOAH Newcastle disease `[read]`: [https://www.woah.org/en/disease/newcastle-disease/](https://www.woah.org/en/disease/newcastle-disease/)
- USDA APHIS avian influenza `[read]`: [https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza](https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza)
- MSD coccidiosis `[read]`: [https://www.msdvetmanual.com/poultry/coccidiosis-in-poultry/coccidiosis-in-poultry?query=broiler](https://www.msdvetmanual.com/poultry/coccidiosis-in-poultry/coccidiosis-in-poultry?query=broiler)
- Droppings segmentation `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/38587413/](https://pubmed.ncbi.nlm.nih.gov/38587413/)
- Yang et al. top-view gait proxies `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/36584623/](https://pubmed.ncbi.nlm.nih.gov/36584623/)
- Fodor et al. top-view gait features `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/39793240/](https://pubmed.ncbi.nlm.nih.gov/39793240/)
- Disease-challenge behavior `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/42117450/](https://pubmed.ncbi.nlm.nih.gov/42117450/)
- Dropping physical/chemical variation `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC11083088/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11083088/)
