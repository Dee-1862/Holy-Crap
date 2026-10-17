# Bibliography

Every source used in the 2026-10-17 research pass, grouped by type, with
status labels per [research/README.md](research/README.md):

- `[read]`: read in full
- `[skimmed]`: read partially
- `[found]`: located, assessed relevant, not fully reviewed
- `[abstract only]`: abstract only
- `[inaccessible]`: could not be read

Synthesis: [research/PAPER.md](research/PAPER.md). Open items: [03-open-questions.md](03-open-questions.md).

## Peer-reviewed and repository evidence

### Datasets and papers

- Machuve et al. primary paper `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC9376463/](https://pmc.ncbi.nlm.nih.gov/articles/PMC9376463/): label provenance: only 16% PCR-tested; authors acknowledge likely label errors.
- Machuve et al. farm-labeled dataset v2 `[read]`: [https://zenodo.org/records/4628934](https://zenodo.org/records/4628934): 6,812 fecal images with YOLO + JSON segmentation annotations; no explicit license displayed.
- Machuve et al. PCR-annotated dataset v3 `[read]`: [https://zenodo.org/records/5801834](https://zenodo.org/records/5801834): 1,255 PCR-annotated images; no explicit license displayed.
- Machuve downstream provenance example `[read]`: [https://doi.org/10.11975/j.issn.1002-6819.202601168](https://doi.org/10.11975/j.issn.1002-6819.202601168): collapses v2/v3 into 8,067 images and describes them as PCR-positive; do not treat downstream reuse as independent replication or override the primary records.
- 2025 poultry CV dataset survey `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S0032579125000215](https://www.sciencedirect.com/science/article/pii/S0032579125000215): reports Machuve datasets and a Nigerian binary dataset (14,618 images, 100x100 px).
- Aworinde/Adebayo Nigeria collection `[read]`: [paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10477973/), [Mendeley dataset](https://data.mendeley.com/datasets/8pnbzpt2k9/1), [Zenodo mirror](https://zenodo.org/records/8122337): 14,618 CC BY 4.0 100×100 smartphone images, visual labels, 94 reported physical instances; grouped-split leakage risk and no pathogen ground truth.
- Abnormal droppings segmentation `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/38587413/](https://pubmed.ncbi.nlm.nih.gov/38587413/): 1,650 images, 60 broilers, five SPF cages; three appearance labels; mDice 79.43%; random image split.
- Wang et al. abnormality detection `[read]`: [https://onlinelibrary.wiley.com/doi/10.1155/2019/3823515](https://onlinelibrary.wiley.com/doi/10.1155/2019/3823515): 7,637 final images, veterinarian visual labels, controlled conveyor; data by request; split independence unclear after augmentation.
- Nakrosis et al. `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC10571708/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10571708/): 487 real-litter images from three farms; six appearance-based classes; veterinarian labels; data by request; no pathogen ground truth.
- Mozuriene et al. droppings variation `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC11083088/](https://pmc.ncbi.nlm.nih.gov/articles/PMC11083088/): age affected color, texture, pH, dry matter, and composition in 73 visually grouped, chemically characterized samples; not pathogen-confirmed disease cases.
- Zhou et al. growth-cycle manure-belt collection `[read]`: [paper](https://www.ijabe.org/index.php/ijabe/article/download/7732/pdf), [DOI](https://doi.org/10.25165/j.ijabe.20231601.7732): one 43-day cycle, visual labels, augmentation/split leakage risk; not an in-pen deposition or diagnostic dataset.
- Big Broiler `[read]`: [repository](https://github.com/decide-ugent/big-broiler-dataset), [paper](https://biblio.ugent.be/publication/01K47TCM11DQFAY9ECSWKKV7C6/file/01K47TEMS4W9984XERQWHDHJHF.pdf), [dataset page](https://decide.ugent.be/datasets/big-broiler/): tracked `Defecating` action labels, but no resulting-deposit label or persistent identity across clips; closest event-cue precursor, not end-to-end attribution.
- Essien et al. longitudinal overhead collection `[read]`: [paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC13199025/), [restricted record](https://doi.org/10.5281/zenodo.18735885): 150 layers, five barns, 22 weeks; useful long-run multimodal data but no manual behavior, health, welfare, fecal, or pathogen labels; Data Access Agreement required.
- Feces weight / robotic floor paper `[found]`: [https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7067666](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7067666): feces monitoring, not bird-specific disease attribution.
- Qin et al. manure tracing `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S0168169924003909](https://www.sciencedirect.com/science/article/pii/S0168169924003909): 91.6% correct tracing to a cage across 48 tests in a stacked-cage/manure-belt system; not individual floor-pen attribution.

### Identity and tracking

- ArUco marker backpacks `[read]`: [https://doi.org/10.1016/j.atech.2024.100703](https://doi.org/10.1016/j.atech.2024.100703): 94.0% identified, 75.6% tracked while manually visible; fit and feather occlusion matter.
- Utrecht record `[read]`: [https://research-portal.uu.nl/en/publications/tracking-laying-hens-with-aruco-marker-backpacks/](https://research-portal.uu.nl/en/publications/tracking-laying-hens-with-aruco-marker-backpacks/)
- Utrecht full text `[read]`: [https://research-portal.uu.nl/ws/files/252705929/1-s2.0-S2772375524003071-main.pdf](https://research-portal.uu.nl/ws/files/252705929/1-s2.0-S2772375524003071-main.pdf)
- Utrecht code `[read]`: [https://github.com/UtrechtUniversity/Laying_Hen_ArUco_Tracking](https://github.com/UtrechtUniversity/Laying_Hen_ArUco_Tracking)
- Tag 'n' Track `[skimmed]`: [https://research-portal.uu.nl/en/publications/tag-n-track-tackling-the-validation-challenge-in-animal-behaviour/](https://research-portal.uu.nl/en/publications/tag-n-track-tackling-the-validation-challenge-in-animal-behaviour/): 3D ArUco; 95.28% F1 for resource-region presence; 82.72% less annotation time.
- 2025 RFID validation `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC12355069/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12355069/): 21 hens; dense interaction zones challenge RFID; posture blocks tags.
- Broiler RFID validation `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC7374484/](https://pmc.ncbi.nlm.nih.gov/articles/PMC7374484/): 40 tagged broilers; video-location metrics came from four birds in four short videos; environmental sensitivity.
- Head-based re-identification `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S2772375525001789](https://www.sciencedirect.com/science/article/pii/S2772375525001789): 18,819 images, 3,644 sequences; Top-1 only above 40% at 100 birds; markerless fallback.
- BroilerTrack `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S277237552500543X](https://www.sciencedirect.com/science/article/pii/S277237552500543X): multi-camera/unified-plane tracking.
- Top-down BoT-SORT `[skimmed]`: [https://www.mdpi.com/2624-7402/5/4/104](https://www.mdpi.com/2624-7402/5/4/104): 98.5% was detector mAP, not identity accuracy; one 15-minute/20-hen tracking video; IDs reset/fragmented.
- MVBroTrack `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S0168169925005411](https://www.sciencedirect.com/science/article/pii/S0168169925005411): calibrated multi-camera fallback; experimental pens. [Open repository](https://github.com/decide-ugent/multi-view-broiler-tracking).
- UGA locomotion/tracking `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC10967591/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10967591/): dye markings for identity under overhead cameras.
- UGA floor detection/counting overview `[read]`: [https://site.caes.uga.edu/precisionpoultry/2022/09/a-precision-method-for-tracking-cage-free-hens-on-the-floor/](https://site.caes.uga.edu/precisionpoultry/2022/09/a-precision-method-for-tracking-cage-free-hens-on-the-floor/): 800-hen research facility; detection/counting across locations, not persistent individual identity; piling, uneven light, and equipment occlusion caused errors.

### Reviews and field studies

- 2026 narrative review, 82 YOLO poultry studies `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC13091050/](https://pmc.ncbi.nlm.nih.gov/articles/PMC13091050/): deployment gaps: occlusion, lighting, generalization, scalability.
- 2024 critical review `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S0168169924007300](https://www.sciencedirect.com/science/article/pii/S0168169924007300): behavior, health, welfare, environmental variability, annotation challenges.
- Video-based poultry monitoring review `[skimmed]`: [https://www.past.or.kr/articles/article/j17n/](https://www.past.or.kr/articles/article/j17n/): dense flocks, lighting, similar appearance; calls for operator-interpretable indicators.
- Commercial-broiler-house activity paper `[read]`: [https://pureadmin.qub.ac.uk/ws/portalfiles/portal/553403602/A_computer_vision_approach.pdf](https://pureadmin.qub.ac.uk/ws/portalfiles/portal/553403602/A_computer_vision_approach.pdf): monocular cameras support group activity monitoring.
- USDA ceiling-camera distribution research `[read]`: [https://www.ars.usda.gov/research/publications/publication/?seqNo115=379745](https://www.ars.usda.gov/research/publications/publication/?seqNo115=379745): floor distribution across feeding/drinking/resting as a welfare indicator.
- Yang et al. top-view gait proxies `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/36584623/](https://pubmed.ncbi.nlm.nih.gov/36584623/): activity/distribution with age and weight predicted pen-average gait score in small pens.
- Fodor et al. top-view gait features `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/39793240/](https://pubmed.ncbi.nlm.nih.gov/39793240/): walking features related to gait in a controlled corridor but revealed little about mild hock burn/footpad dermatitis.
- Disease-challenge behavior study `[abstract only]`: [https://pubmed.ncbi.nlm.nih.gov/42117450/](https://pubmed.ncbi.nlm.nih.gov/42117450/): age/time effects dominated; challenged birds did not follow a universal low-movement pattern.
- Tennessee broiler-producer survey `[read]`: [full thesis](https://trace.tennessee.edu/server/api/core/bitstreams/0888a2ff-4de7-4004-8018-13803c302a66/content), [peer-reviewed paper](https://doi.org/10.1016/j.japr.2025.100548): 77/531 respondents; regional, low-response evidence on installed technology, adoption conditions, barriers, and grower/integrator decision roles; not dollar willingness to pay.
- European PLF farm visits `[read]`: [https://doi.org/10.2527/af.2017.0107](https://doi.org/10.2527/af.2017.0107): 21 farms, including five broiler farms; operators wanted integrated readable data and direct observation, and reported price, maintenance, reliability, repairability, and vendor-held-data problems.
- Livestock early-warning alarm review `[read]`: [https://www.sciencedirect.com/science/article/abs/pii/S0168169916311620](https://www.sciencedirect.com/science/article/abs/pii/S0168169916311620): false alarms repeatedly eroded trust and consumed time; livestock-wide, not a poultry-specific alert threshold.
- Layer alarm-threshold study `[read]`: [https://www.nature.com/articles/s41598-018-26954-9](https://www.nature.com/articles/s41598-018-26954-9): adjacent evidence that persistence reduces alert volume but delays detection; not broiler CV or operator-tolerance evidence.
- Longitudinal broiler deployment `[read]`: [https://www.mdpi.com/2071-1050/15/21/15527](https://www.mdpi.com/2071-1050/15/21/15527): 31 months in an 8,100-bird house; substantial discarded/lost records, stalls, inconsistency, maintenance, and connectivity problems.
- Commercial-house CV `[read]`: [https://www.frontiersin.org/journals/animal-science/articles/10.3389/fanim.2022.945534/full](https://www.frontiersin.org/journals/animal-science/articles/10.3389/fanim.2022.945534/full): roughly 28,000-bird house; commercial-scene performance lagged research results; zone presence did not prove drinking; annotation and cleaning were limiting.
- Pi-camera field prototype `[read]`: [https://doi.org/10.5187/jast.2400235](https://doi.org/10.5187/jast.2400235): different multi-tier installation; bird contact, ammonia damage, lens dust, acquisition gaps, and feeder false detections.
- Biosecurity video study `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC12389693/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12389693/): entry-zone cameras on seven previously HPAI-affected farms; adjacent use case only, with separate privacy and governance needs.
- 120-day commercial-house connectivity study `[read]`: [https://doi.org/10.3390/electronics15112406](https://doi.org/10.3390/electronics15112406): different mobile/caged-broiler setting, used only as risk evidence for weak uplink, loss, latency, reconnects, buffering, and acknowledgements.

## Veterinary authorities

- WOAH Newcastle disease `[read]`: [https://www.woah.org/en/disease/newcastle-disease/](https://www.woah.org/en/disease/newcastle-disease/): signs vary widely and can resemble avian influenza; virulent disease is WOAH-listed; lab testing confirms diagnosis.
- USDA APHIS avian influenza `[read]`: [https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza](https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza): HPAI signs list; LPAI may show none; owners observing suspicious illness are directed to contact veterinary/animal-health authorities promptly.
- USDA spotting sickness `[read]`: [https://www.aphis.usda.gov/livestock-poultry-disease/avian/defend-the-flock/how-to-spot-sickness](https://www.aphis.usda.gov/livestock-poultry-disease/avian/defend-the-flock/how-to-spot-sickness): presents visible signs as possible indicators of avian influenza or other avian diseases.
- MSD Veterinary Manual, coccidiosis `[read]`: [https://www.msdvetmanual.com/poultry/coccidiosis-in-poultry/coccidiosis-in-poultry?query=broiler](https://www.msdvetmanual.com/poultry/coccidiosis-in-poultry/coccidiosis-in-poultry?query=broiler): coccidiosis signs; none uniquely diagnostic.
- MSD Veterinary Manual, common infectious diseases `[read]`: [https://www.msdvetmanual.com/exotic-and-laboratory-animals/backyard-poultry/common-infectious-diseases-in-backyard-poultry](https://www.msdvetmanual.com/exotic-and-laboratory-animals/backyard-poultry/common-infectious-diseases-in-backyard-poultry): paratyphoid Salmonella often subclinical.
- WOAH rabies `[read]`: [https://www.woah.org/en/disease/rabies/](https://www.woah.org/en/disease/rabies/): mammalian disease; not a poultry-camera target (correction recorded).
- University of Guelph enteric-disease guidance `[read]`: [https://www.uoguelph.ca/ahl/content/diagnosing-enteric-disease-backyard-chickens](https://www.uoguelph.ca/ahl/content/diagnosing-enteric-disease-backyard-chickens): color and texture are differential clues; laboratory, histology, or postmortem methods confirm causes as appropriate.
- WOAH broiler welfare standard `[read/official]`: [https://www.woah.org/fileadmin/Home/eng/Health_standards/tahc/2024/en_chapitre_aw_broiler_chicken.htm](https://www.woah.org/fileadmin/Home/eng/Health_standards/tahc/2024/en_chapitre_aw_broiler_chicken.htm): daily physical inspection remains required; feed, water, behavior, feathers, feces, and physical signs inform escalation.
- WOAH poultry biosecurity `[read/official]`: [https://www.woah.org/fileadmin/Home/eng/Health_standards/tahc/2021/en_chapitre_biosecu_poul_production.htm](https://www.woah.org/fileadmin/Home/eng/Health_standards/tahc/2021/en_chapitre_biosecu_poul_production.htm): health, production, medication, mortality, surveillance, cleaning, visitor, and equipment records; service work must respect cleaning and sanitation procedures.
- Aviagen broiler handbook `[read/industry primary]`: [https://eseu.aviagen.com/assets/Tech_Center/AA_Broiler/Aviagen-AA-Broiler-Handbook-EN.pdf](https://eseu.aviagen.com/assets/Tech_Center/AA_Broiler/Aviagen-AA-Broiler-Handbook-EN.pdf): routine mortality, feed, water, weight, environment, health, cull, house-check, and visitor records; automatic systems are manually cross-checked.
- U.S. HPAI indemnity biosecurity rule `[read/current regulation]`: [9 CFR §53.11](https://www.ecfr.gov/current/title-9/chapter-I/subchapter-B/part-53/section-53.11), [USDA audit tool](https://www.aphis.usda.gov/sites/default/files/biosecurityaudit.pdf): approved plans and documented audits matter in specified indemnity/restocking contexts; do not generalize to every farm.

## Vendor and company sources

All claims from these pages are vendor claims, not independent evidence.
See [research/systems/industry-landscape.md](research/systems/industry-landscape.md).

- AGCO acquires Faromatics (ChickenBoy) `[read/company source]`: [https://investors.agcocorp.com/news-releases/news-release-details/agco-acquires-faromatics-precision-livestock-farming-company](https://investors.agcocorp.com/news-releases/news-release-details/agco-acquires-faromatics-precision-livestock-farming-company): ceiling robot, multi-sensor; evidence of industry investment only.
- Calyx AI Eye `[read/vendor]`: [https://www.calyxtechs.com/technology](https://www.calyxtechs.com/technology): overhead still images for per-visible-bird weight estimates and flock distribution; no persistent identity claim.
- Animoni BroilerZoom `[read/vendor]`: [https://animoni.dk/broilerzoom/](https://animoni.dk/broilerzoom/): 3D-camera weight, daily growth, and uniformity.
- Tylmen `[read/vendor]`: [https://www.tylmen.com/](https://www.tylmen.com/): ceiling cameras for weight, movement, distribution, behavior, outlier flagging.
- Tylmen terms `[read/vendor]`: [https://www.tylmen.com/terms-and-conditions](https://www.tylmen.com/terms-and-conditions): vendor-disclosed sensitivity to density, lighting, dust, condensation, obstruction, and connectivity.
- Poultron `[read/vendor]`: [https://poultron.com/](https://poultron.com/): claims weight, behavior, welfare, audit trails; numbers not repeated without validation.
- Poultron roadmap `[read/vendor]`: [https://www.poultron.com/products](https://www.poultron.com/products): disease early warning is listed as a roadmap item.
- Intelia `[read/vendor]`: [https://intelia.com/anomaly-detection/](https://intelia.com/anomaly-detection/): weight, environmental monitoring, anomaly detection.

## Hardware and software primary sources

- QNX AI Camera App `[read]`: [https://gitlab.com/qnx/projects/ai-camera-app](https://gitlab.com/qnx/projects/ai-camera-app): Apache-2.0 QSF/camapi, OpenCV, TensorFlow Lite, and Screen sample; recommends Pi 4 and lists Camera Module 3 as tested.
- QNX camera frame types `[read]`: [https://qnx.com/developers/docs/7.0.0/com.qnx.doc.camera/topic/camera_frametype_t.html](https://qnx.com/developers/docs/7.0.0/com.qnx.doc.camera/topic/camera_frametype_t.html): frame bit depth used for raw-payload planning; negotiated target format and stride still require measurement.
- QNX Pi 5 BSP release notes `[read]`: [https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_sdp80.bsp.broadcom.rpi5.bcm2712.html](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_sdp80.bsp.broadcom.rpi5.bcm2712.html): official 64-bit Pi 5 BSP, currently experimental.
- QNX Pi 5 driver commands `[read]`: [https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp_raspberrypi.bcm2712.rpi5_8.0/topic/driver_commands.html](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp_raspberrypi.bcm2712.rpi5_8.0/topic/driver_commands.html): onboard Wi-Fi may require driver, firmware, network services, and BSP-image work; installed target state is unknown.
- QNX QSTI camera guide `[read]`: [https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/next-steps.html](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/next-steps.html): Camera Module 3 IDs on Pi 5.
- QNX Pi 5 Screen release notes `[read]`: [https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_gfx.sdp80.PUA2025-010.bsp.broadcom.rpi5.bcm2712.html](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_gfx.sdp80.PUA2025-010.bsp.broadcom.rpi5.bcm2712.html): mixed-user Screen/drm risk.
- Raspberry Pi Camera Module 3 product brief `[read]`: [https://datasheets.raspberrypi.com/camera/camera-module-3-product-brief.pdf](https://datasheets.raspberrypi.com/camera/camera-module-3-product-brief.pdf): sensor, optics, modes, environmental envelope.
- M5Stack StopWatch C152 `[read]`: [https://docs.m5stack.com/en/core/StopWatch](https://docs.m5stack.com/en/core/StopWatch): hardware specifications and v1.0/v1.0.1 power-pin warning.
- Detailed notes: [research.md](research.md) and [BIBLE.md](BIBLE.md).
