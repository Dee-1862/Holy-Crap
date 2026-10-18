# Prior Art and Low-Disturbance Setups

Source: web searches on 2026-10-17 (abstracts/summaries only; full texts not read). Everything is `[verify]` until we read the originals.

## 1. Has anyone solved this?
Partly. Nobody found has the full thing (droppings classification running continuously in a real house with alerts).

| Work | What it did | Relevance |
|---|---|---|
| Machuve et al. 2022 (Tanzania) | 4-class fecal classification, MobileNetV2 etc. | Our dataset; close-up smartphone photos, not a mounted camera |
| YOLO11n + EfficientNet-B0, AgriEngineering 2025 | Detector + classifier, ~25.8 ms total inference reported; authors say field testing is still needed | Same pipeline as ours |
| Image-based droppings classification in open-house farms (ResearchGate 2025, Malaysia): https://www.researchgate.net/publication/392852662 | YOLOv5n, up to 94.9%; wood-slat floor makes fresh vs dirty floor hard | Shows the floor-background problem is real |
| Nakrosis et al. 2023 (Lithuania): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10571708/ | Six abnormality classes on droppings across litter types, three farms; segmentation model reported 137 FPS on Jetson Xavier NX | Closest to a real-farm setting |
| Indonesian modified YOLOv5 (2025) | 4 classes, 90.0% mAP | Detection-style baseline |
| Stacked-cage study with conveyor belt: https://mail.ijabe.org/index.php/ijabe/article/download/7732/pdf [verify this is the right paper] | Camera fixed 40 cm above the end of the manure belt to image droppings | **Best match for the low-disturbance setup below** |
| UGA robots (Chai/Lu labs) | Robot dog + YOLOv8 for dead birds and floor eggs: https://site.caes.uga.edu/precisionpoultry/2025/02/a-robotic-machine-vision-system-for-tracking-dead-chickens/ | Robot navigation in cage-free houses is feasible; not droppings |
| Dead-hen inspection robot in caged houses: https://www.sciencedirect.com/science/article/abs/pii/S0168169924009864 | Autonomous robot between cage rows | Shows mobile platforms in cage aisles |
| Grooved-floor feces weight estimation (ScienceDirect 2026): https://www.sciencedirect.com/science/article/pii/S277237552600701X | Vision/LiDAR to estimate feces; cage structures occlude views | Occlusion is a known problem |
| Patent "Robot assisted surveillance of livestock" (US 11019805): paired thermal + optical cameras classify droppings | Prior art to be aware of if we build something commercial | Patent landscape check needed |

Commercial products: none found in this search (search was limited; do a dedicated vendor search later).
Gap for us: real mounted-camera data, continuous alerting, and low-cost QNX edge deployment.

## 2. What disturbs the birds (robot studies)
- Broiler robot study (Poultry Science 2024): https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11017054/ - robot entry makes birds leave the zone within seconds, more strongly and slower to return in younger birds; authors suggest long-term robot presence might act as enrichment.
- Escape-distance study: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11011048/ - slow robot: shorter escape distance but more collisions; fast robot: longer escape distance, fewer collisions.
- A thesis (Mississippi State, https://scholarsjunction.msstate.edu/td/5260/) reports birds habituate to a ground robot, and aerial drones caused stronger avoidance than a rail-mounted sensor package.
- Vendor claims (feather-picking, feed conversion) are unreplicated. Do not cite as evidence.

Conclusion: moving things near birds always cause some disturbance. The least disturbing design is one that doesn't move near them.

## 3. Recommended setups (least to most disturbing)
1. **Fixed camera over a manure belt / droppings tray (caged or perch-board houses).** No contact, birds unaware, clean uniform background, fixed lighting, easiest data. Mount about 40 cm above the belt end or above a clear section [distance from the belt study; adapt]. Needs no robot. **Recommended first.**
2. **Fixed camera at a droppings collection point under roosts or drinkers (cage-free houses).** Passive, one camera per point; limited coverage but cheap.
3. **Ceiling or rail-mounted slow camera.** Moves overhead on a track, no floor contact. Rail packages were reportedly less alarming than drones [verify].
4. **Ground robot at low speed.** Needed only for open litter. Habituation helps; run at a consistent schedule; accept more occlusion and the hardest data.
Avoid: drones, bright flashes, sudden noise, flickering lights.

## 4. Camera and lighting guidance (to validate on a bench)
- Top-down view, fixed height, Camera Module 3 (autofocus, 12 MP): small dropping should span roughly 100+ px; measure on the bench.
- Constant, diffuse, flicker-free lighting (prefer DC or high-frequency LED drivers; poultry see flicker that humans don't, check house lighting guidance). Avoid glare on wet droppings; a polarizer or off-axis light can help. Color is the main signal, so fix white balance and add a gray/color reference card in view to calibrate.
- Dust and ammonia: enclose the camera in a sealed housing with a clean window; plan cleaning.
- Capture on a schedule or when the belt advances, not continuous video, to save compute and bandwidth.

## 5. Plan impact
- Housing type decides the setup. First target: **belt or board in a caged/aviary house**. Open litter robot work is a later phase.
- Collect our own mounted-camera images early, even from a benchtop mock-up (belt or tray, fake droppings made with colored paste) to test the pipeline before any barn access.
- Paper: add "mounted-camera domain gap" and "setup comparison" as future work or an experiment if we get real images. Cite the belt study for the setup choice.
- Check patents (US 11019805 and others) before any commercial use.

## 6. Open questions
- Which housing type does the target farm use? (decides setup 1-4)
- Can we get access to a real house or a belt-equipped barn for image collection?
- Does anyone have a veterinary contact to label our own images?

## 7. Individual identification and data (searched 2026-10-17; abstracts only)
- **No public chicken leg-band dataset found.** Searches (general web, Roboflow, Kaggle) returned nothing for colored-band chickens. A one-pass search can miss things; re-check Roboflow Universe and Hugging Face before concluding.
- Closest public data:
  - Chicks4FreeID (Kern et al., Animals 2025, doi:10.3390/ani15010001; https://huggingface.co/datasets/dariakern/Chicks4FreeID): first public chicken re-ID set, 677 images / 1,270 cut-out crops, 50-54 named birds, identified by plumage, not bands; reported 95.1-100% accuracy with multiple images per bird. Paper: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11718998/. License not confirmed.
  - Roboflow Universe "chickens" project (https://universe.roboflow.com/augus/chickens-3tf9n/dataset/): classes "chicken" and "chicken legs", CC BY 4.0 per search snippet; size and quality unchecked. Could bootstrap a leg detector.
  - CHIRP / color-ring work on wild birds (https://arxiv.org/pdf/2603.25524): method reference for detecting color rings (segmentation); not chickens.
  - GalliformeSpectra (https://arxiv.org/pdf/2310.19830): ten hen breeds, breed classification only.
- **Plan:** we collect our own. Task = detect legs, then classify band color(s). Small effort: a few hundred to a few thousand labeled images with the actual band colors, camera angle and lighting we use. Pretrain/bootstrap the leg detector on the Roboflow set.
- **Geometry problem:** a top-down camera over a belt or tray cannot see leg bands. Band ID needs a side view at leg height (e.g. a perch or feeder station with a side camera), or marks visible from above (back/wing tag). So per-hen ID and droppings-tray imaging would be two cameras at one station, linked by time.
- **Color limits:** only a handful of colors are reliably separable under barn lighting and dirt (guess 5-6 until tested); use two bands (one per leg, or two per leg) to make combinations; avoid similar hues (e.g. orange/red/yellow). Numbered bands are sold commercially, but reading numbers needs high resolution.
- Treat per-hen ID as optional research scope; the core product stays zone-level.
