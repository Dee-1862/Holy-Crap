# RFID and markerless tracking

- Type: methods
- Summary: RFID can provide coarse presence but varies sharply by resource
  and struggles in dense interaction zones; markerless visual re-identification is promising
  but underdeveloped in field settings.
- Why we care: these are the alternatives if ArUco backpacks fail welfare
  review or prove impractical.

## RFID

2025 RFID validation `[read]` [https://pmc.ncbi.nlm.nih.gov/articles/PMC12355069/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12355069/)

- 21 hens; RFID leg bands plus a 3D ArUco reference, run for five days.
- Feeder/drinker visits were challenging: rapid movement, crowding, and
  interference.
- Perching posture could block tags.
- Markerless identity remained underdeveloped in field settings.
- Reported F1 varied by resource: wintergarden 0.84, perch exit 0.86, perch
  access 0.79, nest box 0.78, and feeder/drinker 0.64 each.

Broiler RFID validation `[read]` [https://pmc.ncbi.nlm.nih.gov/articles/PMC7374484/](https://pmc.ncbi.nlm.nih.gov/articles/PMC7374484/)

- Forty broilers were tagged with sub-1g HF RFID tags over a full-pen antenna
  grid. The location validation used four visually marked birds across four
  approximately seven-minute videos.
- Exact-location match in that validation was 62.5%; within one antenna,
  99.2%.
- Separate approximately one-hour distance comparisons reported Spearman
  correlations of 0.82 for video-RFID and 0.70 for UWB-RFID.
- Moisture, tag orientation, birds lying down, calibration, and cleaning
  affected the system.

Our inference: RFID answers "which bird was near this zone", not
centimeter-level attribution of a dropping footprint. Antenna grids are heavy
infrastructure for a one-camera product.

## Markerless visual re-identification

Head-based re-identification `[skimmed]`
[https://www.sciencedirect.com/science/article/pii/S2772375525001789](https://www.sciencedirect.com/science/article/pii/S2772375525001789)

- 18,819 images and 3,644 sequences in an uncontrolled farm setting.
- Top-1 accuracy exceeded 80% for small groups but remained only above 40%
  at 100 birds. The model uses head features such as combs and wattles, which
  may not be consistently visible from overhead. Data are available by request.
- Useful as a future markerless fallback, not the MVP.

## Tracking without identity

BroilerTrack `[skimmed]`
[https://www.sciencedirect.com/science/article/pii/S277237552500543X](https://www.sciencedirect.com/science/article/pii/S277237552500543X)

- Multi-camera/unified-plane tracking meant to reduce homogeneous-appearance
  ambiguity.

Top-down BoT-SORT `[skimmed]` [https://www.mdpi.com/2624-7402/5/4/104](https://www.mdpi.com/2624-7402/5/4/104)

- The reported 98.5% is detector mAP, not persistent-identity accuracy.
- Tracking evaluation used one 15-minute video of 20 hens. A bird returning
  after leaving received a new ID, and wing flapping sometimes split one bird
  into multiple IDs.

MVBroTrack `[skimmed]`
[https://www.sciencedirect.com/science/article/pii/S0168169925005411](https://www.sciencedirect.com/science/article/pii/S0168169925005411)

- Multiple calibrated cameras across experimental pens reported average MODA
  85.8% and recall 93%; tracklet fusion improved IDF1 by three points and
  mostly-tracked birds by five points.
- This is a fallback architecture if one overhead view fails, not evidence
  that a single camera solves identity.
- Code/data: [https://github.com/decide-ugent/multi-view-broiler-tracking](https://github.com/decide-ugent/multi-view-broiler-tracking)

## Research-only identity aids

UGA locomotion/tracking study `[read]`
[https://pmc.ncbi.nlm.nih.gov/articles/PMC10967591/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10967591/)

- Used dye markings to identify individual birds under overhead cameras.

UGA floor detection/counting overview `[read]`
[https://site.caes.uga.edu/precisionpoultry/2022/09/a-precision-method-for-tracking-cage-free-hens-on-the-floor/](https://site.caes.uga.edu/precisionpoultry/2022/09/a-precision-method-for-tracking-cage-free-hens-on-the-floor/)

- Ceiling/side cameras in a research facility with 800 hens demonstrated hen
  detection and counting across locations, not persistent individual identity.
- Piling, uneven light, and equipment occlusion caused errors.

## Connects to

- [aruco-marker-backpacks.md](aruco-marker-backpacks.md)
- [../PAPER.md](../PAPER.md)

## Sources

- 2025 RFID validation `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC12355069/](https://pmc.ncbi.nlm.nih.gov/articles/PMC12355069/)
- Broiler RFID validation `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC7374484/](https://pmc.ncbi.nlm.nih.gov/articles/PMC7374484/)
- Head-based re-ID `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S2772375525001789](https://www.sciencedirect.com/science/article/pii/S2772375525001789)
- BroilerTrack `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S277237552500543X](https://www.sciencedirect.com/science/article/pii/S277237552500543X)
- BoT-SORT top-down `[skimmed]`: [https://www.mdpi.com/2624-7402/5/4/104](https://www.mdpi.com/2624-7402/5/4/104)
- MVBroTrack `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S0168169925005411](https://www.sciencedirect.com/science/article/pii/S0168169925005411)
- MVBroTrack code/data `[read]`: [https://github.com/decide-ugent/multi-view-broiler-tracking](https://github.com/decide-ugent/multi-view-broiler-tracking)
- UGA locomotion `[read]`: [https://pmc.ncbi.nlm.nih.gov/articles/PMC10967591/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10967591/)
- UGA floor detection/counting `[read]`: [https://site.caes.uga.edu/precisionpoultry/2022/09/a-precision-method-for-tracking-cage-free-hens-on-the-floor/](https://site.caes.uga.edu/precisionpoultry/2022/09/a-precision-method-for-tracking-cage-free-hens-on-the-floor/)
