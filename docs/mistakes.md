# Mistakes & Dead Ends

Record anything that went wrong or was ruled out so we don't repeat it. Format: date, what happened, why, what to do instead.

- 2026-10-17: Initially treated bird-level dropping attribution as either guaranteed or impossible. Big Broiler labels defecation actions, but no reviewed work demonstrates end-to-end bird-to-resulting-dropping attribution in a crowded, free-moving floor pen. Test temporal/spatial attribution with ArUco identity, preserve `unattributed`, and keep zone-level output as the fallback.
- 2026-10-17: Considered ESP32 as a QNX/vision target. The M5Stack StopWatch does not run QNX and is not the compute target for this camera pipeline; use it only as an optional status/alert client.
- 2026-10-17: Research claims from the original write-up (UGA work, "AI4D" dataset name) are unverified. Don't cite them until checked.
- 2026-10-17: Reliable high-bandwidth barn Wi-Fi is an explicit working assumption, not a measured fact. The desktop and optional StopWatch must still show stream freshness/connectivity so silence is never mistaken for "all healthy."
- 2026-10-17: An earlier draft disease list included rabies. Rabies is a mammalian disease (WOAH), not a meaningful chicken-camera target; removed from all product framing. See docs/research/evidence/clinical-limits-of-visual-diagnosis.md.
- 2026-10-17: Chose ONNX Runtime before checking the Pi's QNX version. The oss.qnx.com ONNX Runtime build is for QNX 8.0.5; the Pi runs 8.0.0. Always filter oss.qnx.com packages by the target's exact QNX release. Export models to both ONNX and TFLite until the runtime is proven on the device.
- 2026-10-17: Went looking for third-party (Roboflow) bounding boxes before checking all the files in the original Zenodo record, which already has YOLO labels under CC BY 4.0. Check the primary source's full file list first.
- 2026-10-17: Over-recommended multiple Pis too early. Start with one; add more only when one camera can't cover the area.
