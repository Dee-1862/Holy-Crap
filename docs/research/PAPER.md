# Poultry health research: what the evidence supports

_Status: initial evidence-backed research pass, 2026-10-17. This is a
synthesis of the sources in [../02-bibliography.md](../02-bibliography.md), not an exhaustive
literature search. Source status labels follow the conventions in
[README.md](README.md)._

## 1. Product conclusion

Build an explainable early-warning/triage system, not a visual disease
diagnosis and not an automatic-cull system.

Veterinary guidance, dataset quality, and commercial product positioning all
set the same boundary. Veterinary authorities treat visible signs as
nonspecific warnings, and some important diseases are subclinical
([evidence/clinical-limits-of-visual-diagnosis.md](evidence/clinical-limits-of-visual-diagnosis.md)). The main public fecal
collection reviewed here is explicitly caveated by its authors over label errors
and label provenance ([datasets/machuve-fecal-datasets.md](datasets/machuve-fecal-datasets.md)). Commercial
systems, which operate under real customer pressure, lead with weight,
distribution, activity, and anomaly workflows rather than pathogen labels
from feces ([systems/industry-landscape.md](systems/industry-landscape.md)).

A camera system can therefore pursue four layers, with different evidence
strength:

1. Evidence-supported flock monitoring: activity and spatial/zone
   distribution.
2. Controlled-study or project-validation targets: gait/movement proxies,
   persistent inactivity, crowding/piling, and individual anomaly shortlisting.
3. Experimental new-dropping detection and appearance triage.
4. A veterinary-escalation workflow for persistent, nonspecific warning
   signs, without disease-name findings.

Camera alerts never authorize treatment or culling. Suspected
high-consequence or legally reportable disease must be escalated promptly
under the applicable veterinary protocol. Isolation and biosecurity measures
may precede test results when an authority directs them; laboratory testing,
not the camera, confirms the diagnosis. The product never claims to diagnose
disease or makes automatic culling decisions. The safety boundary is recorded
in [../BIBLE.md](../BIBLE.md).

## 2. What the camera can and cannot observe

A fixed overhead RGB camera has direct evidence for flock activity and spatial
distribution/zone occupancy. Controlled studies also support some gait and
movement proxies. Individual isolation, piling, coarse feather condition, and
new-dropping deposition are plausible targets that this project must still
validate in its own geometry
([observables/camera-visible-health-signals.md](observables/camera-visible-health-signals.md)).

It cannot reliably reveal subclinical disease, internal lesions, pathogen
identity, laboratory confirmation, precise individual intake, or determine
whether dropping appearance changed because of disease, age, feed, or another
flock-level factor.

The authority sources are explicit about why. USDA's guidance on spotting
sickness `[read]` lists energy, appetite, movement, breathing, head/comb, and
production changes plus greenish watery diarrhea as possible signs of avian
influenza or other avian diseases. They are warning signs, not diagnoses.
WOAH `[read]` notes Newcastle disease
signs vary widely and can resemble avian influenza, with laboratory testing
needed to confirm. APHIS `[read]` notes LPAI may produce no signs at all. The
camera sees behavior and appearances; it does not see disease.

Two field results anchor what is achievable. USDA ceiling-camera research
`[read]` found floor distribution across feeding, drinking, and resting areas
can act as a welfare/health indicator. A Queen's University Belfast study
`[read]` demonstrated monocular cameras monitoring group activity in
commercial broiler houses. Group- and zone-level monitoring is evidenced;
per-bird diagnosis is not.

The observable list maps directly onto the product layers. Flock-level
metrics (activity and zone occupancy) need no identity and are the most
evidenced layer. Posture/gait cues have controlled-study support. Crowding,
persistent inactivity, and unresponsive-bird detection are experimental in
our setting and need tracking, though not always permanent identity. Coarse
body/feather condition and individual
histories need real identity, which is why identity work is staged, not
front-loaded. New-dropping detection is a proposed temporal-change plus
segmentation task. It does not require a disease label, but its feasibility
on occupied litter remains unvalidated.

The practical consequence: product claims must be written around observable
signals ("bird in this zone has been down and unresponsive for N minutes
with video attached"), never around disease names.

## 3. Identity and tracking

Individual identity is the gateway to per-bird history and to any
evidence-backed dropping association: and it is the weakest part of the
stack in field conditions.

The best-documented approach for our setting is ArUco marker backpacks
([identity/aruco-marker-backpacks.md](identity/aruco-marker-backpacks.md)). In the Utrecht study `[read]`,
lightweight laminated-paper ArUco markers worn on hens and read by top-down
cameras: the best-fitting hybrid identified 94.0% of individuals and tracked
them for 75.6% of the time they were manually visible. Feathers obscured
markers, and physical fit mattered. The study used small experimental groups
of roughly ten pullets; its authors proposed possible research and
semi-commercial use. That is encouraging, not production proof. A companion
validation, Tag 'n' Track `[skimmed]`, reported 95.28% F1 for detecting
individual presence in defined resource regions across 245 ten-minute videos
of 21 hens and reduced annotation time by 82.72%. It does not establish
continuous whole-barn identity through occlusion.

RFID is the main alternative ([identity/rfid-and-markerless-tracking.md](identity/rfid-and-markerless-tracking.md)). A
2025 validation `[read]` with 21 hens wearing RFID leg bands plus a 3D ArUco
reference found feeder/drinker visits challenging because of rapid movement,
crowding, and interference, and perching posture could block tags. A broiler
study `[read]` tagged 40 birds with sub-1g HF tags and used a full-pen antenna
grid. Its location validation used four visually marked birds in four
approximately seven-minute videos and found 62.5% exact matches and 99.2%
within one antenna. Separate approximately one-hour distance comparisons
reported Spearman correlations of 0.82 for video-RFID and 0.70 for UWB-RFID.
Moisture, tag orientation, birds lying down, calibration, and cleaning all
degraded the system. RFID answers coarse presence questions, not footprint-level
attribution, and its antenna infrastructure is heavy for a one-camera
product.

Markerless re-identification exists: a head-based study `[skimmed]` used
18,819 images and 3,644 sequences in an uncontrolled farm setting. Top-1
accuracy exceeded 80% for small groups but remained only above 40% at 100
birds; its head features may not be consistently visible from overhead. It
is a later fallback, not the MVP. Multi-camera systems are another fallback.
In the reviewed BoT-SORT study, 98.5% was detector mAP, not persistent-
identity accuracy; tracking used one 15-minute video of 20 hens, reset IDs
after exits/re-entry, and sometimes split one bird during wing flapping.
Research groups fall back on dye
markings under overhead cameras (UGA `[read]`), which is fine for studies
and not for production. A UGA floor-detection overview `[read]` describes
ceiling/side cameras in an 800-hen research facility. It demonstrated hen
detection and counting across locations, not persistent individual identity;
piling, uneven light, and equipment occlusion caused errors.

Recommendation: pilot ArUco/fiducial markers over generic QR in phase one,
and treat attachment, welfare, cleaning, marker loss, growth, pecking, and
handling as study variables.

## 4. Droppings: detection, attribution, classification

Droppings are also the easiest feature to overclaim. The tempting version,
“classify droppings by pathogen,” is not supported by the evidence.

Attribution first. We found no end-to-end demonstration of reliable
bird-to-resulting-dropping attribution in a crowded, free-moving floor pen.
Big Broiler `[read]` is the closest precursor: it attaches a human-labelled
`Defecating` action to broiler tracklets, including a 140-bird angled-view pen
and a small overhead setup. It does not label the resulting fecal deposit, its
location or appearance, or persistent identity across clips; released
tracklets average about 73 seconds, and the paper notes relatively low stocking
density ([repository](https://github.com/decide-ugent/big-broiler-dataset),
[paper](https://biblio.ugent.be/publication/01K47TCM11DQFAY9ECSWKKV7C6/file/01K47TEMS4W9984XERQWHDHJHF.pdf)).
Qin et al. separately traced abnormal manure to a cage in a stacked-cage,
manure-belt system with 91.6% correct tracing across 48 field tests; it did not
identify an individual bird
([Qin et al., 2024](https://www.sciencedirect.com/science/article/pii/S0168169924003909)).
We therefore propose a testable hypothesis: detect a new dropping by temporal
change/segmentation; look back over a short window in identity tracks; assign
only when one tagged bird occupies the deposition footprint and a visible
event cue supports it; otherwise mark it unattributed. Unattributed must be a
valid, first-class outcome, not an error state. Zone-level output ("zone X has
abnormal droppings") remains useful on its own and is the fallback.

Classification second. The framing that survives the evidence is
normal/abnormal triage, not pathogen diagnosis. A segmentation study
`[abstract only]` of 1,650 images across 60 broilers in five SPF cages used
normal, abnormal-shape, and abnormal-color pixel labels and reported mDice
79.43% after a random 8:2 image split. It supports semantic segmentation as
a way to label overlapping droppings. It does not validate disease diagnosis,
clinical triage outcomes, temporal detection of newly deposited droppings,
or new-flock generalization. The Machuve authors
themselves acknowledge likely label errors, especially Salmonella versus
healthy, because white coloring overlaps and texture distinctions can be
subjective, and only 16% of samples were PCR-tested
([datasets/machuve-fecal-datasets.md](datasets/machuve-fecal-datasets.md)). A "Salmonella class" from images is
further undermined by veterinary evidence that common paratyphoid Salmonella
infections in poultry are often subclinical
([evidence/clinical-limits-of-visual-diagnosis.md](evidence/clinical-limits-of-visual-diagnosis.md)).

Disease-specific associations are future research, not an MVP stage. They
may be evaluated offline using veterinary and laboratory reference labels;
deployment would require prospective independent validation and a separately
defined intended use. The honest MVP vocabulary is "new dropping",
"normal-looking", "abnormal-looking", and "unattributed".

## 5. Data

The best-characterized downloadable fecal collection reviewed in this pass is
the Machuve et al. Tanzanian collection
([datasets/machuve-fecal-datasets.md](datasets/machuve-fecal-datasets.md)):

- v2 farm-labeled `[read]`: 6,812 images (coccidiosis 2,103; healthy 2,057;
  salmonella 2,276; Newcastle disease 376), smartphone images from Arusha and
  Kilimanjaro, 2020-2021, with YOLO object-detection and JSON segmentation
  annotations; about 11.3 GB.
- v3 PCR-annotated `[read]`: 1,255 images (coccidiosis 373; healthy 347;
  salmonella 349; Newcastle 186); about 4.4 GB.
- The Zenodo records expose downloads but display no explicit license. Do not
  assume permission to redistribute, modify, or use the data in a product;
  obtain written clarification or an explicit license first.

Four rules follow. Never treat farm-labeled and PCR-labeled subsets as
interchangeable (only 16% of samples were PCR-tested per the primary paper
`[read]`). Acquisition context is partly confounded with class: farm
observations supplied healthy/coccidiosis images while Salmonella/Newcastle
images followed inoculation, so a random split may reward collection context
rather than pathology. PCR detection strengthens pathogen evidence but does
not by itself prove that organism caused the visible appearance, and a sample
negative for three targets is not a comprehensive health diagnosis. Finally,
expect a domain gap from smartphone photography to overhead barn footage.
The paper's 80/20 image split did not hold out a farm, bird, or collection
session; its reported 98.02–98.24% results measure agreement with the dataset
labels, not lab-confirmed diagnostic accuracy or expected barn performance.

The Aworinde/Adebayo Nigeria collection `[read]` contains 14,618 CC BY 4.0
smartphone images at 100×100 pixels: 7,991 labelled healthy and 6,627
non-healthy. Animal scientists and farmers verified the visual labels, not
laboratory or pathogen testing. Burst capture and only 94 reported physical
instances create serious near-duplicate and grouped-split leakage risk. The
morning/afternoon/night folders do not identify birds or repeated samples, so
this is not longitudinal data. Treat it only as binary visual-abnormality data
([paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10477973/),
[dataset](https://data.mendeley.com/datasets/8pnbzpt2k9/1)).

Nakrosis et al. `[read]` collected 487 real-litter images from three Lithuanian
farms and used six veterinarian-defined appearance classes. Reported best
results were 91.78% classification accuracy, 92.41% object-detection accuracy,
and a 0.8875 K-means Dice score; the data are small, imbalanced, and available
only by request, and the labels are visual rather than pathogen-confirmed.
Zhou et al. `[read]` followed one 43-day broiler cycle at a manure-belt end,
making it the closest reviewed longitudinal dropping-appearance collection,
not an in-pen deposition dataset. Its visual, veterinary-advised labels and
ungrouped augmentation/split reporting do not support clinical accuracy,
bird attribution, or new-deposit detection. Essien et al. `[read]` supplies 22
weeks of overhead multimodal data across five layer barns, but has no behavior,
health, welfare, fecal, or pathogen labels and requires a Data Access Agreement.
See [datasets/abnormal-droppings-datasets.md](datasets/abnormal-droppings-datasets.md).

A 2026 SSRN paper `[found]` on feces weight and robotic floors is relevant to
feces monitoring generally but does not support bird-specific disease
attribution.

## 6. Prior academic and commercial work

A 2026 narrative review `[read]` of 82 YOLO poultry studies covers
normal/comfort/problem behavior, leg conditions, disease/pathogen signals,
injured/dead birds, counting, and tracking, and lists recurring deployment
gaps: occlusion, lighting/infrastructure variation, limited dataset
generalization, and scalability. Controlled-study metrics are not commercial
proof. A 2024 critical review `[skimmed]` covers behavior, health, welfare,
environmental variability, and annotation challenges. A Korean
video-monitoring review `[skimmed]` emphasizes dense flocks, lighting,
environment, and similar bird appearance as continuing problems, and calls
for multi-farm/multi-view datasets and operator-interpretable indicators.
These gaps are our deployment risk list, and they are well documented
([systems/industry-landscape.md](systems/industry-landscape.md)).

The vendor pages show a consistent positioning pattern. AGCO acquired
Faromatics (ChickenBoy) `[read/company source]`, a ceiling-suspended robot
combining cameras/sensors for thermal sensation, air quality, light, sound,
health/welfare, and equipment risks: evidence of industry investment, not
efficacy. Calyx AI Eye `[read/vendor]` uses overhead still images for
tag-free per-visible-bird weight estimates and flock weight distribution in
dusty/dim barns with edge filtering plus cloud,
aimed at weight and harvest planning, not disease diagnosis. Animoni's
BroilerZoom `[read/vendor]` uses a 3D camera for weight, daily growth, and
uniformity. Tylmen `[read/vendor]` sells ceiling
cameras for weight, movement, distribution, behavior, and outlier flagging.
Poultron `[read/vendor]` claims weight, behavior, welfare, and audit trails
- vendor claims we do not repeat without independent validation. Intelia
`[read/vendor]` offers weight, environmental monitoring, and anomaly
detection.

No commercial system we reviewed leads with pathogen labels from feces.
Across the reviewed vendor pages, positioning emphasizes weight and
uniformity, movement and distribution, environmental or operational anomaly
monitoring, auditability, and alerts. Some vendors also claim or plan feed,
water, mortality, and disease-warning features; those remain individual
vendor claims or roadmap items. This informs a product hypothesis; it does not
independently establish adoption or willingness to pay.

## 7. Market and operator needs

The market evidence supports an operational workflow, not a willingness-to-pay
claim. A Tennessee broiler-producer survey `[read]` found widespread use of
temperature, feed, and water automation but much lower reported use of video
and data-management systems. Of this contract-grower-heavy sample, only 46%
said they were the primary technology decision-maker; 41% consulted the
integrator or had technology addressed by contract. Producers expressed more
interest when a technology increased income, could be seen working on a farm,
or came with cost sharing. The survey was regional and low-response, so it does
not establish a price or paid demand.

Farm visits and field deployments `[read]` make the adoption requirements more
concrete: integrate readable data with existing records; keep direct human
inspection; expose missing, stale, duplicate, and unrealistic data; let the
operator access and export raw and derived records; state maintenance and
cleaning needs; and show economic and time burden. Local interviews remain
necessary for transfer validation. They must include growers and
integrator/live-production managers, not only the person standing in the barn.
See [practice/operator-needs-and-product-wedge.md](practice/operator-needs-and-product-wedge.md).

The resulting product hypothesis is an evidence-backed bird
shortlist and health anomaly workflow. The camera produces continuous
activity/zone metrics; anomalies become persistent, explainable alerts with
clips; the farmer acknowledges and acts with a vet. This is a triage
product, and its honest boundaries (no diagnosis, no automated action) are
also its credibility.

## 8. Recommended MVP

Sequence, each stage gated in [../BIBLE.md](../BIBLE.md):

1. Instrument one representative pen with controlled overhead RGB video and
   stable lighting.
2. Pilot welfare-reviewed ArUco backpacks on a small flock; measure
   visible-time identity rate, marker loss/occlusion, and handling burden.
3. Deliver flock activity/zone metrics and persistent anomaly alerts with
   evidence clips.
4. Add new-dropping detection and normal-versus-abnormal triage; keep
   unattributed as a valid outcome.

Disease-specific associations are future research, not an MVP stage. They
may be evaluated offline using veterinary and laboratory reference labels;
deployment would require prospective independent validation and a separately
defined intended use.

Prioritize data collection and label governance over model shopping.
Consider model families at a high level only: object
detection/segmentation, multi-object tracking, pose/activity estimation,
temporal anomaly detection, embedding-based re-identification: without
pinning a YOLO version or a specific backbone.

Stage 1 exists because every downstream stage
consumes stable footage; no footage, no labels, no evaluation. Stage 2 is
the identity experiment, deliberately small so a failed marker concept costs
little. Stage 3 is the first shippable value: it needs no disease model and
no droppings model, only activity/zone features and an alert workflow, and
it is where the operator workflow (acknowledgement, audit trail, false-alarm
budget) gets real-world testing. Stage 4 adds droppings on top of the same
workflow. Disease-association research sits outside this MVP.

Deployment note: the selected camera is Raspberry Pi Camera Module 3 and the
verified compute target is one headless Raspberry Pi 5 running QNX 8.0.0.
QNX AICA is the selected Sensor Framework/OpenCV/TensorFlow Lite reference,
but Pi 5 + Camera Module 3 + AICA has not been demonstrated on this target.
Reliable high-bandwidth Wi-Fi is a working assumption. The desktop is the
primary UI and receives camera data; the optional M5Stack StopWatch is a
secondary status display. Inference placement remains benchmark-driven. See
[../BIBLE.md](../BIBLE.md).

## 9. Validation

As project methodology, evaluation must split by the strongest available
independent acquisition unit (bird, flock, farm, date, or session), and never
place near-duplicate frames from one recording across train and test. It must
measure operator-relevant quantities: trusted-data uptime; missing, duplicate,
and stale-frame rates; clock integrity; maintenance interventions per flock;
identity coverage; false alarms per house-day; alert acknowledgement and
inspection rate; action yield; latency; missed incidents; delay created by
persistence rules; operator follow-through; and performance against the
existing manual-record baseline. Controlled-study accuracy numbers from the
literature are not deployment performance; our own barn data decides.

Leakage deserves emphasis because the public datasets are small and
class-imbalanced. If frames from one flock appear in both train and test
splits, the model may learn pen-specific appearance rather than condition;
splitting by an independent acquisition unit helps expose that failure. For the
droppings stages, evaluation should be on annotated footage from the
instrumented pen, with the annotation process itself treated as an
experiment (inter-annotator agreement on "abnormal" is an early signal of
whether the boundary is even learnable).

A persistent, acknowledged alert workflow answers two practical questions:
did the farmer act on the alert, and was that action useful?

## 10. Risks

- Attribution risk: dropping-to-bird association may simply fail in dense
  pens; zone-level unattributed output must remain acceptable.
- Identity risk: marker welfare and durability; feather occlusion; growth;
  pecking; handling burden ([identity/aruco-marker-backpacks.md](identity/aruco-marker-backpacks.md)).
- Data risk: public fecal data is smartphone/lab photography with
  acknowledged label error and an unclear license.
- Deployment risk: QNX documents the Sensor Framework/AICA path, but Camera
  Module 3 + Pi 5 + AICA and the ML runtimes have not been proved on this
  physical target; inference placement depends on benchmarks.
- Field reliability risk: ammonia, dust, insects, bird contact, connectivity
  loss, timestamp inconsistency, missing/duplicate/stale data, and slow
  maintenance can make a technically accurate model operationally useless.
- Commercial-domain risk: research-facility accuracy may not survive age,
  density, occlusion, lighting, equipment, and full-grow-out conditions. Zone
  occupancy must not be relabeled as a specific behavior such as drinking
  without separate evidence.
- Adoption risk: the grower may not control purchasing or data, and the party
  paying may not capture the benefit. Buyer, approver, operator, data owner,
  maintenance owner, and economic beneficiary must be mapped.
- False-alarm risk: age and other flock context can change dropping color,
  texture, pH, dry matter, and composition; alert rules need flock baselines
  and persistence, not isolated frames.
- Boundary risk: overpromising diagnosis invites misuse; wording and
  interface must keep the product advisory.

## 11. Research gaps

- Explicit reuse terms for the Machuve datasets; downloads alone do not grant
  permission to redistribute, modify, or use the data in a product.
- QNX camera capture and ML runtime verification on the Pi 5.
- New-dropping detection on real litter (no public dataset reviewed for
  this).
- The normal-vs-abnormal dropping boundary under diet changes (no public
  data reviewed for this).
- Marker pilot data under production-like density and handling.
- Markerless identity in field settings (underdeveloped in the literature).
- Operator workflow and buyer interviews: what growers and integrators need,
  who approves and pays, who owns the data, who services the system, who
  receives alerts, and who captures the benefit.

The prioritized list with methods and the decisions each one unlocks is in
[../03-open-questions.md](../03-open-questions.md); the condensed landscape with comparison tables is
in [../00-landscape-review.md](../00-landscape-review.md); the numbered findings are in
[../01-key-findings.md](../01-key-findings.md).
