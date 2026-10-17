# Operator needs and product wedge

- Type: practice note
- Summary: farmers need a review workflow with evidence, not a classifier
  verdict. Commercial systems converge on measurement and anomaly workflows;
  our wedge follows that pattern.
- Why we care: the MVP and its interface must be built around operator
  workflow, or alerts get ignored.

## Provisional operator requirements

These are design hypotheses synthesized from vendor positioning and research
gaps. Farmer interviews and pilot use must confirm them
([../systems/industry-landscape.md](../systems/industry-landscape.md)):

- Evidence clips/images for every alert.
- Reason, confidence, and persistence (how long the condition has held).
- Bird ID or zone, whichever the evidence supports.
- Acknowledgement and an audit trail.
- Explicit connection and stream-freshness state. Reliable high-bandwidth
  Wi-Fi is a working assumption, but silence must not look like “all healthy.”
- Low false-alarm burden: a busy farmer abandons noisy systems.
- Fit with barn workflows: quick glance first, deeper review when convenient.

## The wedge

Our inference: lead with an evidence-backed bird shortlist and health anomaly
workflow: persistent, explainable alerts with clips: not pathogen labels
from feces. See [../systems/industry-landscape.md](../systems/industry-landscape.md) and [../PAPER.md](../PAPER.md).

## MVP sequence

Recommended order (details in [../PAPER.md](../PAPER.md) and [../../BIBLE.md](../../BIBLE.md)):

1. Prove Camera Module 3 capture on the QNX Pi and stream it to the primary
   desktop UI over the assumed reliable Wi-Fi link.
2. Instrument one representative pen with controlled overhead RGB video and
   stable lighting.
3. Deliver flock activity/zone metrics and persistent anomaly alerts with
   evidence clips in the desktop UI.
4. Pilot welfare-reviewed ArUco backpacks on a small flock; measure
   visible-time identity rate, marker loss/occlusion, and handling burden.
5. Add new-dropping detection and normal-versus-abnormal triage; keep
   unattributed as a valid outcome.
6. Add the optional M5Stack StopWatch wall client after the authoritative
   desktop/event path works.

Disease-specific association work is future offline research, not part of
this MVP.

Prioritize data collection and label governance over model shopping. Model
families to consider, at a high level only: object detection/segmentation,
multi-object tracking, pose/activity estimation, temporal anomaly detection,
embedding-based re-identification. No YOLO version is prescribed.

## Connects to

- [../systems/industry-landscape.md](../systems/industry-landscape.md)
- [../PAPER.md](../PAPER.md)

## Sources

- Vendor pages and reviews: see [../systems/industry-landscape.md](../systems/industry-landscape.md)
