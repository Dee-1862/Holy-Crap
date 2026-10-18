# Vision Design v2: identity by place and time, not by bands

Written 2026-10-17. Builds on [vision-plan.md](vision-plan.md) (data, YOLO11n, runtime) and [prior-art-and-setups.md](prior-art-and-setups.md). Facts attributed to "pasted notes" come from a research summary the user pasted (abstract-level, not verified by us).

## 1. Why bands are the wrong tool
- Leg bands are visible only from the side at leg height. The cameras that see droppings (over a belt, or overhead on the floor) look down.
- Crowding hides legs; few colors separate reliably in dusty, dim barns; no public leg-band dataset exists.
- Even the best individual-ID attempts in open flocks are weak (pasted notes: printed markers on hens identified each bird only 37% of the time in a Wageningen study; a re-ID set reaches 95-100% only with several images per bird).
- Even a perfect bird ID would not say whose dropping it is: that needs a link between the bird and the dropping.

**Decision: drop bands from the core path. Identify by where and when, not by who.** Per-hen identity becomes an optional pilot.

## 2. Attribution ladder (use the cheapest level that works)
| Level | Housing | How | Evidence |
|---|---|---|---|
| L1 Cage | Caged layers | Camera over the manure belt; a second model tracks belt movement to map each dropping to the cage it fell from | Pasted notes: 2024 study, YOLOv5 flags abnormal manure, 91.6% correct cage tracing over 48 field tests [verify]. Closest solved case |
| L2 Zone | Cage-free / floor | Report by zone (camera view or pan-tilt sweep position); time-stamped events | Pasted notes: 2023 study sweeps the floor with a ~3.5 m pan-tilt camera every few minutes [verify] |
| L3 Soft attribution | Floor, optional | New dropping at (x,y,t) + bird tracklets (local track IDs, no identity) + defecation-posture cue -> ranked candidate birds with a probability; "unknown" is a normal answer | Not shown end-to-end by anyone found; research direction |
| L4 Persistent ID | Small pilot | Marker visible from above (e.g. ArUco/QR backpack or wing tag) instead of leg bands; welfare review first | Pasted notes: low reliability reported (37%) |

MVP = L2 (zone). L1 if the target is a caged house. L3/L4 are future work or a paper section.

## 3. Better vision model (stack for Pi 5 CPU, QNX)
Keep vision-plan.md's baseline (one-stage YOLO11n, TFLite, close-up camera) and add three cheap pieces that fix the real problems (dirty floor, tiny droppings, no disease names):

1. **New-dropping trigger (no ML).** Compare each frame against a slowly updating background of the same fixed view (grayscale/downscaled difference + blob filter). Fresh droppings appear as new blobs; old dirt does not. Solves "new droppings are hard to tell from an already dirty floor" (open-house slat-floor study). Also cuts compute: run the detector only on changed regions, and ignore moving birds by requiring the blob to persist several frames.
2. **Detector on candidates (YOLO11n, INT8 TFLite).** 1 class "dropping" or 4 classes (decide per vision-plan.md). Input 320-416 on the Pi; tile or crop candidate regions when the camera is higher.
3. **Coarse-to-fine classifier on full-resolution crops.** Detect at low resolution; when a candidate is confirmed, grab a full-resolution still (Camera Module 3 is 12 MP) and classify the crop with a small CNN (MobileNetV3 or EfficientNet-Lite0). Keeps FPS high while the classifier still sees the color/texture detail it needs.
4. **Output = normal / abnormal / uncertain.** Train 4-class internally (hint of type), expose "abnormal, consult a vet", never a disease name in the product (matches PR #1's safety stance). Calibrate confidence and send low-confidence cases to "uncertain" plus an evidence snapshot.
5. **Alerting on repeats per zone** (3+ abnormal in 10 min, tunable), as in game-plan.md.

Research options (not for the hackathon MVP):
- **Anomaly detection** (PatchCore-style or autoencoder trained on healthy droppings only): no disease labels, handles the tiny NCD class and domain shift better in theory. Hypothesis: color variation between normal diets may hurt it. Test against the 4-class model.
- **Bird detector + tracker** (small YOLO + ByteTrack) for L3 soft attribution; needs more compute and probably video off the Pi, which conflicts with the QNX-on-device goal. Run offline for the paper first.
- **Defecation-action cue:** the PR mentions a "Big Broiler defecation actions" resource as a possible event cue. Unread by us.

## 4. Is the current vision fine? (assessment)
**vision-plan.md (YOLO11n, Zenodo boxes, TFLite/ONNX, Pi inference): fine for the hackathon, with four caveats.**
1. Machuve photos are close-ups with mostly one box per image; mAP there will overstate barn performance. Say so, and test on our own mock-up images.
2. NCD has few boxes (384 in the label counts); report per-class recall, not just mAP.
3. Public output should be normal/abnormal; keep 4-class internal.
4. Keep inference on the Pi (the QNX track wants an oss.qnx.com AI package in the product).

**PR #1 direction (Lance's research base, as described in the pasted summary; I have not read the PR files):** the advisory/triage framing, evidence clips, no disease names, "unknown identity is normal", and cage-level attribution all match what the evidence supports and are good. Too heavy for a deadline measured in days: the 24-hour Wi-Fi load test, real-pen instrumentation and ArUco welfare review should be post-hackathon. A desktop-primary UI that receives video and runs inference there conflicts with keeping inference on the QNX Pi.

## 5. Impact on the three-person split ([team-architecture.md](team-architecture.md))
- C (vision): add a background-difference trigger, a 1-class dropping detector, full-res crop classifier, uncertain bucket; ship the YOLO11n baseline first.
- A (edge): need a still-capture path at full resolution in addition to the low-res stream (QSF).
- B (frontend): show zone status, "abnormal/uncertain" with a snapshot, never disease names; the event schema gains `label` in {normal, abnormal, uncertain} and an optional `type_hint`.
- Detection event contract: add `attribution` {level: "zone"|"cage"|"soft"|"id", candidates: [...]} so L1/L3 can be added later without a schema break.

## 6. Open questions
- Housing type decides L1 vs L2.
- Can the Pi do the background-difference + detector + full-res capture at usable speed? Benchmark stock models first.
- Which datasets cover new vs old droppings on dirty floors? (None found; need our own mock-up images.)

## 7. Update 2026-10-17: group-based design adopted
Decision: keep birds in separate groups and attribute to the group. This is attribution level L2 (zone) made physical: each group has its own region, so the L3/L4 bird-level work is dropped from scope and stays future research.
- Pipeline unchanged: background-difference trigger -> detector -> full-resolution crop -> normal/abnormal/uncertain. Add a **group assignment** step: each detection's box center is tested against per-group polygons (config file per camera/preset).
- Each camera needs a one-time calibration: draw group regions on a reference frame; store as `groups.json` (group_id, polygon, head_count). Re-check after any camera bump.
- Droppings on a boundary between groups: drop detections whose box overlaps a boundary margin, or tag them `ambiguous` and do not count them.
- Event schema (supersedes the optional `attribution` field in section 5): add `group_id`, `group_size`, and `region_conf` (how far inside the region the detection is). `attribution.level` is always `"group"`.
- Alert rule: abnormal events per group within a window, normalized by `group_size`, with a floor count so one dropping never alerts. The dashboard and StopWatch show groups, not birds.
- Evaluation additions: group-assignment accuracy (hand-label which region each test dropping is in), boundary-case rate, and false-alert rate per group-day.
- Data collection tip: a group with known health status (e.g. a vet-confirmed sick pen) gives group-level ground truth for the alert experiments without any bird IDs.
