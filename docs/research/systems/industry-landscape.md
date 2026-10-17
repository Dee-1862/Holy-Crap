# Industry landscape and prior art

- Type: system/landscape
- Summary: academic reviews show what computer vision can measure in barns
  and where it fails; commercial systems lead with weight, distribution, and
  anomalies: not pathogen labels from feces.
- Why we care: vendor positioning suggests product hypotheses, while the
  reviews set honest expectations for deployment. Adoption and willingness
  to pay still require customer evidence.

## Academic reviews

2026 narrative review of 82 YOLO poultry studies `[read]`
[https://pmc.ncbi.nlm.nih.gov/articles/PMC13091050/](https://pmc.ncbi.nlm.nih.gov/articles/PMC13091050/)

- Study areas include normal/comfort/problem behavior, leg conditions,
  disease/pathogen signals, injured/dead birds, counting, and tracking.
- Recurring deployment gaps: occlusion, lighting/infrastructure variation,
  limited dataset generalization, and scalability.
- Controlled-study metrics are not commercial proof.

2024 critical review `[skimmed]`
[https://www.sciencedirect.com/science/article/pii/S0168169924007300](https://www.sciencedirect.com/science/article/pii/S0168169924007300)

- Covers behavior, health, welfare, environmental variability, and annotation
  challenges.

Video-based poultry monitoring review `[skimmed]`
[https://www.past.or.kr/articles/article/j17n/](https://www.past.or.kr/articles/article/j17n/)

- Dense flocks, lighting, environment, and similar bird appearance are
  continuing problems.
- Calls for multi-farm/multi-view datasets and operator-interpretable
  indicators.

## Commercial systems

AGCO acquisition of Faromatics (ChickenBoy) `[read/company source]`
[https://investors.agcocorp.com/news-releases/news-release-details/agco-acquires-faromatics-precision-livestock-farming-company](https://investors.agcocorp.com/news-releases/news-release-details/agco-acquires-faromatics-precision-livestock-farming-company)

- Ceiling-suspended robot combines cameras/sensors for thermal sensation, air
  quality, light, sound, health/welfare, and equipment risks.
- This is evidence of industry investment, not independent proof of efficacy.

Calyx AI Eye `[read/vendor]` [https://www.calyxtechs.com/technology](https://www.calyxtechs.com/technology)

- Overhead still images for tag-free per-visible-bird weight estimates and
  flock weight distribution; this does not establish persistent identity.
- Designed for dusty/dim barn settings; edge filtering plus cloud.
- Market focus is weight and harvest planning, not disease diagnosis.

Animoni BroilerZoom `[read/vendor]` [https://animoni.dk/broilerzoom/](https://animoni.dk/broilerzoom/)

- 3D camera for real-time weight, daily growth, and uniformity.

Tylmen `[read/vendor]` [https://www.tylmen.com/](https://www.tylmen.com/)

- Ceiling cameras for weight, movement, distribution, behavior, and outlier
  flagging.
- The vendor's terms say density, lighting, dust, condensation, obstruction,
  and connectivity can affect analytics and do not guarantee detection of all
  birds or disease indicators
  ([terms](https://www.tylmen.com/terms-and-conditions)).

Poultron `[read/vendor]` [https://poultron.com/](https://poultron.com/)

- Vendor claims around weight, behavior, welfare, and audit trails.
- Do not repeat numeric claims without independent validation.
- Its “Disease Early Warning System” is listed as a roadmap item, not a
  validated live feature ([roadmap](https://www.poultron.com/products)).

Intelia `[read/vendor]` [https://intelia.com/anomaly-detection/](https://intelia.com/anomaly-detection/)

- Weight, environmental monitoring, and anomaly detection.

## The pattern

Across the reviewed vendor pages, positioning emphasizes weight and
uniformity, movement and distribution, environmental or operational anomaly
monitoring, auditability, and alerts. Some vendors also claim or plan feed,
water, mortality, and disease-warning features; those should be labeled
individually as vendor claims or roadmap items. No reviewed vendor leads with
pathogen labels from feces. The plausible wedge for this project is an
evidence-backed bird shortlist and health anomaly workflow. This pattern is
not independent proof of demand. See
[../practice/operator-needs-and-product-wedge.md](../practice/operator-needs-and-product-wedge.md).

## Connects to

- [../practice/operator-needs-and-product-wedge.md](../practice/operator-needs-and-product-wedge.md)
- [../PAPER.md](../PAPER.md)

## Sources

Each subsection above carries its source with a status label; the full
grouped list is in [../../02-bibliography.md](../../02-bibliography.md).
