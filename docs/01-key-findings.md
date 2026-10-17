# Key findings

Numbered, actionable findings from the 2026-10-17 research pass. Each has a
confidence note and points at evidence. Sources carry status labels per
[research/README.md](research/README.md); the full list is [02-bibliography.md](02-bibliography.md).

1. **Build triage, not diagnosis.** The product is an explainable
   early-warning/triage system: monitor the flock, shortlist birds/zones,
   flag abnormal droppings, and hand evidence to a human. It is not a visual
   disease diagnosis and never makes automatic culling decisions.
   Confidence: high. Veterinary authorities, dataset label evidence, and
   the commercial pattern all point the same way. See
   [research/PAPER.md](research/PAPER.md) §1, [BIBLE.md](BIBLE.md) §2-3.

2. **The camera sees behavior, not disease.** Field research supports flock
   activity and zone occupancy; controlled studies support some gait and
   movement proxies. Isolation, piling, feather condition, and new-dropping
   deposition remain project hypotheses. The camera cannot reliably see
   subclinical disease, lesions, pathogen identity, lab confirmation,
   precise intake, or tell whether dropping appearance changed because of
   disease, age, feed, or another flock-level factor. Confidence: high, based
   on USDA `[read]`, WOAH `[read]`, APHIS `[read]`,
   MSD `[read]`; zone monitoring evidenced by USDA distribution research
   `[read]` and a commercial-broiler-house study `[read]`. See
   [research/observables/camera-visible-health-signals.md](research/observables/camera-visible-health-signals.md).

3. **No disease names in the MVP output.** Visible signs are not
   disease-specific, and some key infections are subclinical; output
   vocabulary is new/normal-looking/abnormal-looking/unattributed droppings
   plus behavior anomalies. Confidence: high for the boundary; triage
   feasibility is medium and must be measured. See
   [research/evidence/clinical-limits-of-visual-diagnosis.md](research/evidence/clinical-limits-of-visual-diagnosis.md).

4. **Bird-level dropping attribution has not been demonstrated for our setting.**
   We found no peer-reviewed result for a crowded, free-moving floor pen; the
   nearest work traced manure to a cage, not a bird. Working
   hypothesis: detect a new dropping by temporal change/segmentation, look
   back over a short identity-track window, and assign only when one tagged
   bird occupies the footprint and a visible posture/event cue supports it;
   otherwise mark unattributed. Confidence: untested hypothesis; zone-level
   output is the fallback. See [research/PAPER.md](research/PAPER.md) §4, [BIBLE.md](BIBLE.md) §4.

5. **Machuve is the best-characterized downloadable fecal collection reviewed
   in this pass, with real caveats.**
   v2: 6,812 farm-labeled images; v3: 1,255 PCR-annotated images. Only 16%
   of samples were PCR-tested; authors acknowledge likely label errors
   (Salmonella vs healthy). No explicit license is displayed, so reuse rights
   must be clarified. Its
   80/20 image split did not hold out farms or sessions, and reported ~98%
   results measure agreement with dataset labels rather than diagnostic
   accuracy. Never mix farm-labeled and PCR-labeled subsets. Confidence: high;
   the caveats come from the authors themselves `[read]`. See
   [research/datasets/machuve-fecal-datasets.md](research/datasets/machuve-fecal-datasets.md).

6. **ArUco backpacks are the phase-one identity approach.** Utrecht `[read]`:
   the best-fitting hybrid identified 94.0% of individuals and was tracked for
   75.6% of manually visible time. The study used small experimental groups of
   roughly ten pullets; its authors proposed possible research and
   semi-commercial use but did not validate a semi-commercial deployment. Tag
   'n' Track `[skimmed]` reported 95.28% F1 for presence in defined resource
   regions, not continuous identity, and 82.72% less annotation time.
   Treat attachment, welfare, cleaning, marker loss, growth, pecking, and
   handling as study variables. Confidence: medium. This is encouraging but not
   evidence of production-scale performance. See [research/identity/aruco-marker-backpacks.md](research/identity/aruco-marker-backpacks.md).

7. **RFID answers coarse presence, not footprint attribution.** In a broiler
   study `[read]`, location validation on four visually marked birds in four
   approximately seven-minute videos found 62.5% exact matches and 99.2%
   within one antenna. Separate approximately one-hour distance comparisons
   reported Spearman correlations of 0.82 for video-RFID and 0.70 for
   UWB-RFID. A 2025 validation `[read]` found feeder/drinker zones challenging
   and tags blockable by posture. Antenna grids are heavy infrastructure for
   a one-camera product. Confidence: medium-high.
   See [research/identity/rfid-and-markerless-tracking.md](research/identity/rfid-and-markerless-tracking.md).

8. **Markerless re-ID is a later fallback.** Head-based re-ID `[skimmed]`
   exists (18,819 images, 3,644 sequences, uncontrolled farm), but Top-1
   performance fell from above 80% for small groups to only above 40% at 100
   birds. Markerless identity is underdeveloped in field settings. Confidence: medium.
   See [research/identity/rfid-and-markerless-tracking.md](research/identity/rfid-and-markerless-tracking.md).

9. **Follow the commercial pattern.** Across the reviewed vendor pages,
   positioning emphasizes weight and uniformity, movement and distribution,
   environmental or operational anomaly monitoring, auditability, and alerts.
   Some vendors also claim or plan feed, water, mortality, and disease-warning
   features; these are vendor claims or roadmap items, not independent
   evidence. The wedge is an evidence-backed bird shortlist and health anomaly
   workflow. This is a product hypothesis, not proof of adoption or willingness
   to pay. Confidence: medium, based on vendor/company sources `[vendor]`. See
   [research/systems/industry-landscape.md](research/systems/industry-landscape.md),
   [research/practice/operator-needs-and-product-wedge.md](research/practice/operator-needs-and-product-wedge.md).

10. **Expect the documented deployment gaps.** The 2026 review of 82 YOLO
    poultry studies `[read]` names occlusion, lighting/infrastructure
    variation, limited dataset generalization, and scalability; controlled
    metrics are not commercial proof. Confidence: high as a literature
    consensus; treat as our risk list. See [research/systems/industry-landscape.md](research/systems/industry-landscape.md).

11. **Evaluate like an operator, split to avoid leakage.** As project method,
    split by the strongest available independent unit (bird, flock, farm,
    date, or session), and keep near-duplicate video frames together. Measure
    event-level alert value, identity
    coverage, false alarms per pen-day, latency, missed incidents, and
    operator follow-through. Confidence: high as method.
    See [research/PAPER.md](research/PAPER.md) §9, [BIBLE.md](BIBLE.md) §9.

12. **Label governance before model shopping.** Data collection and label
    quality decide the outcome more than model choice; consider model
    families at a high level only and prescribe no YOLO version.
    Confidence: high; this is the core lesson across the reviews in this pass.
    See [research/PAPER.md](research/PAPER.md) §8.

13. **Hardware reality is narrow and specific.** The compute target is one
    headless Raspberry Pi 5 (`aarch64le`) running QNX 8.0.0, with Raspberry Pi
    Camera Module 3 and QNX AICA selected. AICA documents Sensor Framework,
    OpenCV, and TensorFlow Lite on QNX but recommends Pi 4; the combined Pi 5
    setup and installed runtimes remain unverified. Confidence: verified/
    selected/unknown mix.
    See [BIBLE.md](BIBLE.md) §5-6, [03-open-questions.md](03-open-questions.md).

14. **Rabies is off the table.** An earlier draft disease list included
    rabies; WOAH `[read]` states rabies is a mammalian disease. It is not a
    chicken-camera target and has been removed. Confidence: high.
    See [research/evidence/clinical-limits-of-visual-diagnosis.md](research/evidence/clinical-limits-of-visual-diagnosis.md).

15. **The desktop is primary; the StopWatch is optional.** Assume reliable,
    high-bandwidth barn Wi-Fi and stream camera data to a desktop application
    for live view, history, evidence, and alert review. The M5Stack StopWatch
    is a replaceable wall-status client, not a hard constraint or source of
    truth. Pi-versus-desktop inference placement is decided by benchmarks.
    Confidence: project decision. See [BIBLE.md](BIBLE.md) §4-7.
