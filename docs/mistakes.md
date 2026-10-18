# Mistakes & Dead Ends

Record anything that went wrong or was ruled out so we don't repeat it. Format: date, what happened, why, what to do instead.

- 2026-10-17: Assumed "multiple hens at once" meant per-hen monitoring. Droppings can't be attributed to individual hens from a floor camera. Plan is per-zone monitoring instead.
- 2026-10-17: Considered ESP32 as a QNX target. No evidence QNX supports ESP32; treat ESP32 as sensor/display nodes only (and it can't run the vision models).
- 2026-10-17: Research claims from the original write-up (UGA work, "AI4D" dataset name) are unverified. Don't cite them until checked.
- 2026-10-17: Wi-Fi coverage in a barn is an assumption, not verified. If alerts go missing in the field, check dead spots first, and make the StopWatch show an explicit "offline" state so silence is never mistaken for "all healthy".
- 2026-10-17: Chose ONNX Runtime before checking the Pi's QNX version. The oss.qnx.com ONNX Runtime build is for QNX 8.0.5; the Pi runs 8.0.0. Always filter oss.qnx.com packages by the target's exact QNX release. Export models to both ONNX and TFLite until the runtime is proven on the device.
- 2026-10-17: Went looking for third-party (Roboflow) bounding boxes before checking all the files in the original Zenodo record, which already has YOLO labels under CC BY 4.0. Check the primary source's full file list first.
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
