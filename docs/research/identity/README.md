# Identity and tracking

Options ranked by current evidence:

1. ArUco marker backpacks: best-documented for our use; recommended pilot.
   See [aruco-marker-backpacks.md](aruco-marker-backpacks.md).
2. RFID (leg bands, antenna grids): strong at coarse presence, weak in dense
   interaction zones; heavy infrastructure. See [rfid-and-markerless-tracking.md](rfid-and-markerless-tracking.md).
3. Markerless re-identification: promising but underdeveloped in field
   settings; fallback, not MVP. See [rfid-and-markerless-tracking.md](rfid-and-markerless-tracking.md).
4. Dye markings: research-only identity aid. See
   [rfid-and-markerless-tracking.md](rfid-and-markerless-tracking.md).

Key risks are identity coverage while markers are obscured and reliable
markerless reassociation after long gaps. A readable fiducial or RFID tag can
re-establish identity after a gap, but neither guarantees continuous location
coverage. See [../PAPER.md](../PAPER.md) and
[../../03-open-questions.md](../../03-open-questions.md).
