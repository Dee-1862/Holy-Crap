# Operator needs and product wedge

- Type: practice note
- Summary: farmers need a review workflow with evidence, not a classifier
  verdict. Commercial systems converge on measurement and anomaly workflows;
  our wedge follows that pattern.
- Why we care: the MVP and its interface must be built around operator
  workflow, or alerts get ignored.

## Evidence-backed baseline

A Tennessee survey `[read]` of 77 broiler producers found mature adoption of
temperature monitoring (98.1%), automated feed (88.7%), and water meters
(85.2%), but only 25.0% reported video and 24.6% data-management systems. Most
respondents were contract growers. Only 46% said they were the primary
technology decision-maker; 41% consulted the integrator or had technology
addressed by contract. Interest rose when technology increased farm income,
could be seen working on another farm, or came with cost sharing. This is
stated interest from one low-response regional survey, not a dollar
willingness-to-pay estimate.

European farm visits `[read]` found that operators wanted integrated, readable
data and still relied on direct observation. Complaints included high price,
slow maintenance, broken equipment, unrealistic values, systems they could not
repair or adjust, and data retained by the vendor. Longitudinal and
commercial-house studies `[read]` add missing or duplicate data, stale values,
clock/location inconsistencies, dust and insect fouling, connectivity loss,
domain shift, and large annotation burdens.

That evidence supports these baseline requirements:

- Place alerts in the existing flock/house record alongside feed, water,
  weight, environment, mortality, health observations, and manual checks.
- Keep humans in control. The system supports daily inspection; it never
  replaces it.
- Show evidence clips, reason, persistence, bird/zone, data freshness, and
  sensor health for every alert.
- Record acknowledgement, inspection, notes, action, and exportable audit
  history. “No alert” must never hide missing or stale data.
- Give operators access to raw and derived data, with a defined export and
  retention path.
- Publish maintenance needs, operator time, trusted-data uptime, and payback,
  not only model accuracy.
- Rank and suppress alerts. Literature confirms false alarms erode trust, but
  it does not establish one universal poultry alert budget.

## Buyer and user map

- **Grower:** operates the house, inspects birds, and responds to alerts.
- **Integrator/live-production manager:** may approve technology, control
  production data, and capture part of the economic benefit.
- **Veterinarian or animal-health authority:** owns diagnostic escalation.
- **Auditor or certifier:** may consume traceability and biosecurity records.
- **Maintenance provider:** services hardware under farm biosecurity rules.

Local discovery must ask who approves, pays, owns the data, services the
hardware, receives alerts, and benefits financially. No credible
poultry-specific transaction or dollar willingness-to-pay evidence was found
in this pass.

## Pilot-specific questions

- Which clip format and alert priority levels lead to action?
- What false-alert load is tolerable for this house and role?
- Who receives escalation, and on which device?
- What information belongs on the desktop versus the optional wall display?
- How much review and maintenance time does the workflow add per flock?

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

- Tennessee producer survey `[read]`: [thesis](https://trace.tennessee.edu/server/api/core/bitstreams/0888a2ff-4de7-4004-8018-13803c302a66/content), [peer-reviewed paper](https://doi.org/10.1016/j.japr.2025.100548)
- European PLF farm visits `[read]`: [https://doi.org/10.2527/af.2017.0107](https://doi.org/10.2527/af.2017.0107)
- Aviagen broiler handbook `[read/industry primary]`: [https://eseu.aviagen.com/assets/Tech_Center/AA_Broiler/Aviagen-AA-Broiler-Handbook-EN.pdf](https://eseu.aviagen.com/assets/Tech_Center/AA_Broiler/Aviagen-AA-Broiler-Handbook-EN.pdf)
- WOAH broiler welfare standard `[read/official]`: [https://www.woah.org/fileadmin/Home/eng/Health_standards/tahc/2024/en_chapitre_aw_broiler_chicken.htm](https://www.woah.org/fileadmin/Home/eng/Health_standards/tahc/2024/en_chapitre_aw_broiler_chicken.htm)
- Livestock alarm review `[read]`: [https://www.sciencedirect.com/science/article/abs/pii/S0168169916311620](https://www.sciencedirect.com/science/article/abs/pii/S0168169916311620)
- Longitudinal deployment `[read]`: [https://www.mdpi.com/2071-1050/15/21/15527](https://www.mdpi.com/2071-1050/15/21/15527)
- Commercial-house CV `[read]`: [https://www.frontiersin.org/journals/animal-science/articles/10.3389/fanim.2022.945534/full](https://www.frontiersin.org/journals/animal-science/articles/10.3389/fanim.2022.945534/full)
- Pi-camera field prototype `[read]`: [https://doi.org/10.5187/jast.2400235](https://doi.org/10.5187/jast.2400235)
- Vendor pages and reviews: see [../systems/industry-landscape.md](../systems/industry-landscape.md)
