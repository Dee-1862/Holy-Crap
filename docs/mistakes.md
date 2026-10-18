# Mistakes & Dead Ends

Record anything that went wrong or was ruled out so we don't repeat it. Format: date, what happened, why, what to do instead.

- 2026-10-17: Veri custom scripts originally had a 64 MB /dev/shm: DataLoader workers and NCCL (multi-GPU) crashed with bus errors / "No space left on device". Fixed by Veri on 2026-10-17 (--shm-size 16g, verified with job 38f4d0ee9f3c). train.py still falls back to pipe-transport loading if shm < 1 GB.
- 2026-10-17: On Windows each DataLoader worker is a full process; with 15 GB RAM, 8 train workers (+16 val workers) crashed with "bad allocation". Use 4 workers locally.
- 2026-10-17: Leftover files (yolo11n.pt, runs/) in training/ made `veri run-script` uploads fail with a multipart parse error. Keep the upload dir to source files only.
- 2026-10-17: Initially treated bird-level dropping attribution as either guaranteed or impossible. Big Broiler labels defecation actions, but no reviewed work demonstrates end-to-end bird-to-resulting-dropping attribution in a crowded, free-moving floor pen. Test temporal/spatial attribution with ArUco identity, preserve `unattributed`, and keep zone-level output as the fallback.
- 2026-10-17: Considered ESP32 as a QNX/vision target. The M5Stack StopWatch does not run QNX and is not the compute target for this camera pipeline; use it only as an optional status/alert client.
- 2026-10-17: Research claims from the original write-up (UGA work, "AI4D" dataset name) are unverified. Don't cite them until checked.
- 2026-10-17: Reliable high-bandwidth barn Wi-Fi is an explicit working assumption, not a measured fact. The desktop and optional StopWatch must still show stream freshness/connectivity so silence is never mistaken for "all healthy."
- 2026-10-17: An earlier draft disease list included rabies. Rabies is a mammalian disease (WOAH), not a meaningful chicken-camera target; removed from all product framing. See docs/research/evidence/clinical-limits-of-visual-diagnosis.md.
- 2026-10-17: Chose ONNX Runtime before checking the Pi's QNX version. The oss.qnx.com ONNX Runtime build is for QNX 8.0.5; the Pi runs 8.0.0. Always filter oss.qnx.com packages by the target's exact QNX release. Export models to both ONNX and TFLite until the runtime is proven on the device.
- 2026-10-17: Went looking for third-party (Roboflow) bounding boxes before checking all the files in the original Zenodo record, which already has YOLO labels under CC BY 4.0. Check the primary source's full file list first.
- 2026-10-17: Veri custom-script job on Vast A100 (job ac6353c1331f) failed before our code ran: the Vast worker has no `docker` binary (FileNotFoundError: 'docker'). Run custom scripts on AWS (L4) until Veri fixes it; report to @daniung.
- 2026-10-17: Over-recommended multiple Pis too early. Start with one; add more only when one camera can't cover the area.
- 2026-10-17: The original write-up credited University of Georgia with droppings classification; search found UGA work on dead chickens/eggs instead. Don't repeat that attribution in the paper.
- 2026-10-17: Don't treat Kaggle copies of the Tanzania data as independent datasets, and don't use random splits; both inflate accuracy (papers report 98-99%).
- 2026-10-17: Could not open the Kaggle page (allandclive/chicken-disease-1); counts and classes are from secondary sources until the page is checked.
- 2026-10-17: Resolved earlier caveat: Kaggle page contents now verified (via user paste). Remaining unknowns: license (shown as Unknown) and the meaning of the `pcr*` filename prefix.
- 2026-10-17: Scripted PDF downloads (Frontiers, PMC, Europe PMC, MDPI) fail with 403/closed connections; don't retry. Ask the user to drop PDFs into paper/.
- 2026-10-17: pdftotext -layout scrambled the columns of Table 2 in the Machuve PDF. Cross-check table values against the prose or the rendered page before quoting.
- 2026-10-17: Repo's TARGET.md (commit by another collaborator) says the QNX target is a Raspberry Pi 5 running QNX 8.0.0, while our docs say Pi 4. Docs need reconciling.
- 2026-10-17: Earlier docs assumed Pi 4 and an ONNX Runtime path. Actual target is Pi 5 and QNX's sample uses TFLite; ONNX is not needed. Don't plan models that can't convert to TFLite.
- 2026-10-17: SSH alias qnxpi exists only on the other collaborator's Mac; it is not in this machine's ~/.ssh/config. Don't guess hostnames; get the alias/tunnel setup from them.
- 2026-10-17: Don't assume a floor-patrolling robot is the default. Robot studies show birds flee and need habituation; start with fixed cameras over manure belts/droppings points. Don't cite vendor claims (feather-picking, feed conversion) as evidence.
- 2026-10-17: Correction to my earlier correction: a UGA extension article does describe a machine-vision method for poultry disease detection from manure images (precisionpoultry 2025/09), so the original write-up's UGA claim is partly supported. The robot work I found at UGA was dead birds/eggs, but UGA is not absent from droppings research.
- 2026-10-17: Colored leg bands only work in a side view; top-down belt/floor cameras can't see them, and even good individual ID doesn't link a bird to a dropping. Don't build the core on bands (see vision-design-v2.md).
