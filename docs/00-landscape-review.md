# Landscape review (compact)

Status labels follow [research/README.md](research/README.md). Full synthesis: [research/PAPER.md](research/PAPER.md).
All sources: [02-bibliography.md](02-bibliography.md).

## Narrative

Four layers of evidence stack into one conclusion.

**Veterinary layer.** Visible signs of poultry disease overlap heavily
across diseases (USDA spotting-sickness guidance `[read]`), some diseases
are subclinical (paratyphoid Salmonella per MSD `[read]`). Suspected high-
consequence disease warrants prompt veterinary/authority escalation, while
laboratory testing confirms diagnosis; exact reporting duties vary by
jurisdiction and pathotype. A camera cannot diagnose; it can only observe.
Rabies, once floated as a target, is a mammalian disease and irrelevant
(WOAH `[read]`). See [research/evidence/clinical-limits-of-visual-diagnosis.md](research/evidence/clinical-limits-of-visual-diagnosis.md).

**Observable layer.** Field research supports flock activity and spatial
distribution/zone occupancy; controlled studies support some gait and
movement proxies. Individual isolation, piling, feather condition, and new-
dropping deposition still need validation in this project's camera geometry.
The camera cannot reveal subclinical disease, lesions, pathogens, lab
confirmation, precise intake, or why dropping appearance changed. See
[research/observables/camera-visible-health-signals.md](research/observables/camera-visible-health-signals.md).

**Academic layer.** Reviews document the capability ceiling and the
deployment gaps. The 2026 narrative review of 82 YOLO poultry studies
`[read]` lists occlusion, lighting/infrastructure variation, limited dataset
generalization, and scalability as recurring gaps. The 2024 critical review
`[skimmed]` and the video-monitoring review `[skimmed]` add annotation
challenges and the need for operator-interpretable indicators. Detection and
short-window tracking are demonstrated, while dependable continuous identity
at commercial density remains unproven. See
[research/systems/industry-landscape.md](research/systems/industry-landscape.md).

**Commercial layer.** Across the reviewed vendor pages, positioning emphasizes
weight and uniformity, movement and distribution, environmental or operational
anomaly monitoring, auditability, and alerts. Some vendors also claim or plan
feed, water, mortality, and disease-warning features; those are individual
vendor claims or roadmap items. See the table below and
[research/practice/operator-needs-and-product-wedge.md](research/practice/operator-needs-and-product-wedge.md).

## Comparison: academic evidence

| Source (status) | Setting | Result worth quoting | Caveat |
|---|---|---|---|
| Utrecht ArUco backpacks `[read]` | 11 experimental pens, roughly 10 pullets each, top-down cameras | 94.0% identified; tracked 75.6% of manually visible time | Feathers obscure markers; fit matters; not semi-commercial deployment proof |
| Tag 'n' Track `[skimmed]` | 3D ArUco validation, 21 hens, defined resource regions | 95.28% F1; 82.72% less annotation time | Region presence, not continuous identity through occlusion |
| 2025 RFID validation `[read]` | 21 hens, RFID leg bands + 3D ArUco, 5 days | Feeder/drinker visits hard; perching blocks tags | Markerless identity underdeveloped in field settings |
| Broiler RFID `[read]` | 40 tagged broilers, full-pen antenna grid; location validation on four birds in four approximately seven-minute videos | 62.5% exact-location match; 99.2% within one antenna | Separate approximately one-hour distance comparisons reported Spearman 0.82 video-RFID and 0.70 UWB-RFID; moisture, orientation, lying down, calibration, and cleaning degrade it |
| Machuve v2/v3 datasets `[read]` | Smartphone fecal images, Tanzania | 6,812 farm-labeled; 1,255 PCR-annotated | Authors flag label errors; license unclear; 16% PCR-tested |
| Droppings segmentation `[abstract only]` | 1,650 images, 60 broilers, 5 SPF cages | Reported mDice 79.43% for appearance labels | Random image split; not temporal deposition or pathogen evidence |
| Nakrosis et al. `[read]` | 487 real-litter images from three farms; six visual classes | 91.78% classification; 92.41% detection; Dice 0.8875 | Small, imbalanced, visual labels; data by request |
| Big Broiler `[read]` | Tracked broiler clips, including a 140-bird angled view and a small overhead setup | Human-labelled `Defecating` actions | No resulting-deposit label, persistent identity across clips, or end-to-end attribution proof |
| UGA floor detection `[read]` | 800-hen research facility, ceiling/side cameras | Demonstrated hen detection/counting across locations | Not individual identity tracking; piling, uneven light, and equipment occlusion caused errors |

## Comparison: commercial systems

All commercial rows are vendor/company sources; treat as claims, not
evidence.

| System (status) | Modality | Market focus | Notes |
|---|---|---|---|
| AGCO/Faromatics ChickenBoy `[read/company source]` | Ceiling-suspended robot, cameras + sensors | Thermal, air quality, light, sound, health/welfare, equipment risks | Evidence of industry investment, not efficacy |
| Calyx AI Eye `[read/vendor]` | Overhead still imagery, edge + cloud | Per-visible-bird weight estimates and flock distribution; harvest planning | Does not establish persistent identity or diagnosis |
| Animoni BroilerZoom `[read/vendor]` | 3D camera | Weight, daily growth, and uniformity | Vendor positioning, not independent validation |
| Tylmen `[read/vendor]` | Ceiling cameras | Weight, movement, distribution, behavior, outlier flagging | Vendor claim; terms warn that density, lighting, dust, condensation, obstruction, and connectivity affect analytics and do not guarantee all birds or disease indicators |
| Poultron `[read/vendor]` | Vendor product | Weight, behavior, welfare, audit trails | Numeric claims not repeated without validation |
| Intelia `[read/vendor]` | Vendor product | Weight, environmental monitoring, anomaly detection | Vendor positioning; no independent effectiveness metrics cited here |

## Bottom line

Across the reviewed vendors, positioning emphasizes measurement, anomalies,
and audit. That suggests a product hypothesis rather than proving demand. The
most mature deployment evidence is at flock and zone level. Tagged systems
demonstrate individual identity in limited research settings, but dependable
continuous identity at commercial density remains unproven. The defensible
concept is an evidence-backed early-warning and triage workflow: shortlist
birds/zones with clips, never label pathogens.

A Tennessee producer survey `[read]` found that growers often are not the sole
technology decision-maker, and no credible dollar willingness-to-pay estimate
was found. Farm visits and longitudinal deployments make maintenance, data
freshness, export, ownership, and integration with existing house records part
of the product, not backend details. See
[research/practice/operator-needs-and-product-wedge.md](research/practice/operator-needs-and-product-wedge.md).
Next steps in [research/PAPER.md](research/PAPER.md) §8 and [03-open-questions.md](03-open-questions.md).
