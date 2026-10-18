# ArUco marker backpacks

- Type: method
- Summary: lightweight laminated-paper ArUco markers worn like backpacks and
  read by top-down cameras produced the best-documented per-bird identity
  results we found.
- Why we care: identity is the gateway to per-bird history and to any
  evidence-backed dropping association.

## Evidence

Utrecht study `[read]` [https://doi.org/10.1016/j.atech.2024.100703](https://doi.org/10.1016/j.atech.2024.100703)

- University record: [https://research-portal.uu.nl/en/publications/tracking-laying-hens-with-aruco-marker-backpacks/](https://research-portal.uu.nl/en/publications/tracking-laying-hens-with-aruco-marker-backpacks/)
- Full text: [https://research-portal.uu.nl/ws/files/252705929/1-s2.0-S2772375524003071-main.pdf](https://research-portal.uu.nl/ws/files/252705929/1-s2.0-S2772375524003071-main.pdf)
- Code: [https://github.com/UtrechtUniversity/Laying_Hen_ArUco_Tracking](https://github.com/UtrechtUniversity/Laying_Hen_ArUco_Tracking)

- Lightweight laminated-paper ArUco backpack markers with top-down cameras.
- The best-fitting hybrid identified 94.0% of individuals and tracked them
  for 75.6% of the time they were manually visible.
- Feathers obscured markers, and physical fit mattered.
- Tested in 11 experimental pens with roughly 10 pullets per pen. The authors
  proposed possible research and semi-commercial use; they did not validate a
  semi-commercial deployment.

Tag 'n' Track `[skimmed]`
[https://www.sciencedirect.com/science/article/pii/S0168169924012031](https://www.sciencedirect.com/science/article/pii/S0168169924012031)

- Across 245 ten-minute videos of 21 hens, 3D ArUco markers produced 95.28%
  F1 for presence in defined resource regions and reduced annotation time by
  82.72%.
- This is resource-region presence, not continuous whole-barn identity
  through occlusion.

## Our recommendation

Run an ArUco/fiducial pilot over generic QR for phase one (see [../PAPER.md](../PAPER.md)).
Treat attachment, welfare, cleaning, marker loss, growth, pecking, and
handling as study variables, not afterthoughts.

## Limits / open questions

- Utrecht results are from laying hens in limited settings; transfer to other
  flocks and production barns is unproven.
- Welfare review of wearing any marker is mandatory before the pilot.
- Marker durability under litter, dust, moisture, and pecking is unknown for
  our deployment.

## Connects to

- [rfid-and-markerless-tracking.md](rfid-and-markerless-tracking.md)
- [../practice/operator-needs-and-product-wedge.md](../practice/operator-needs-and-product-wedge.md)
- [../PAPER.md](../PAPER.md)

## Sources

- Utrecht paper `[read]`: [https://doi.org/10.1016/j.atech.2024.100703](https://doi.org/10.1016/j.atech.2024.100703)
- Utrecht record `[read]`: [https://research-portal.uu.nl/en/publications/tracking-laying-hens-with-aruco-marker-backpacks/](https://research-portal.uu.nl/en/publications/tracking-laying-hens-with-aruco-marker-backpacks/)
- Utrecht full text `[read]`: [https://research-portal.uu.nl/ws/files/252705929/1-s2.0-S2772375524003071-main.pdf](https://research-portal.uu.nl/ws/files/252705929/1-s2.0-S2772375524003071-main.pdf)
- Utrecht code `[read]`: [https://github.com/UtrechtUniversity/Laying_Hen_ArUco_Tracking](https://github.com/UtrechtUniversity/Laying_Hen_ArUco_Tracking)
- Tag 'n' Track `[skimmed]`: [https://www.sciencedirect.com/science/article/pii/S0168169924012031](https://www.sciencedirect.com/science/article/pii/S0168169924012031)
