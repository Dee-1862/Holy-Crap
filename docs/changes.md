# Changes Log

Newest first. One line per change: date, what, why.

- 2026-10-17: vision-plan.md: added which oss.qnx.com packages are usable on 8.0.0 (prebuilt apks vs source ports), the 4-class vs 2-class option, and training feasibility. Added prior work on per-hen dropping attribution to research.md (none found for floor flocks; cage-level tracing exists).
- 2026-10-17: Pulled ecb50fb (Pi is QNX 8.0.0) and merged it with local doc edits. Added docs/vision-plan.md: LA Hacks QNX + Veri tracks, data (Zenodo CC BY 4.0 with official YOLO boxes, so Roboflow is no longer needed), recommended single-stage 4-class YOLO11n trained on Veri GPUs, and a check for ONNX Runtime vs TFLite caused by the 8.0.0 vs 8.0.5 package mismatch.
- 2026-10-17: Decisions: all-C++ on device; hackathon timeline (days); detector boxes from Roboflow set; camera view undecided, prototype close-up. Added "Hackathon scope" to game-plan.md.
- 2026-10-17: Decisions: runtime = ONNX Runtime; hardware in hand = Raspberry Pi 5 + Camera Module 3 (plan previously assumed Pi 4). Language: C++ for camera capture (QSF API is C only); see game-plan.md. Recorded dataset candidates in research.md.
- 2026-10-17: Surveyed oss.qnx.com: ONNX Runtime, TFLite, ncnn, OpenCV, Python 3 + numpy, and a Camera Module 3 driver are all ported for aarch64 QNX 8.0. Added table to research.md. Focus is now the vision pipeline.
- 2026-10-17: Corrected the target hardware to the verified Raspberry Pi 5 running QNX 8.0.0. Removed the Pi 4-specific camera claim and made CPU-only inference the working assumption until acceleration is verified. Added TARGET.md and AGENTS.md with target facts, connection steps, and operating rules.
- 2026-10-17: Created docs/ with game-plan.md, research.md, changes.md, mistakes.md. Initial plan from user's idea (two-stage fecal classification on QNX Raspberry Pi). Hardware recommendation: one Pi 4 per camera zone; ESP32 only for sensors/alert display.
- 2026-10-17: Decided to assume barn-wide Wi-Fi + MQTT. Added multi-node scaling layout and StopWatch screen design (status/alerts only; full dashboard on a separate web page) to game-plan.md.
- 2026-10-17: Reframed hardware: single Pi 4 + one camera is the baseline; extra Pis are optional and only for coverage. Updated game-plan.md hardware decision, scaling section, and open questions.
- 2026-10-17: Literature/dataset/model research pass. Added paper-plan.md (gap analysis, contributions, datasets, model matrix, experiments, risks, outline). Appended findings and a correction (UGA claim) to research.md.
- 2026-10-17: Verified Kaggle dataset from user's pasted page; updated paper-plan.md dataset row, risks (unknown license, 224px), and added farm-vs-PCR split idea.
- 2026-10-17: Created paper/ folder (README index + notes-machuve2022.md). Read Machuve et al. PDF added by user. Direct downloads from Frontiers/PMC/Europe PMC/MDPI were blocked, so only user-supplied PDFs are stored.
- 2026-10-17: Target confirmed Raspberry Pi 5 + Camera Module 3. Read QNX ai-camera-app (TFLite + OpenCV on QNX). Switched runtime plan to TensorFlow Lite; updated game-plan.md, paper-plan.md, research.md.
- 2026-10-17: User confirmed the board is a Raspberry Pi 5. Removed remaining Pi 4 assumptions from paper-plan.md and research.md (Pi 4 kept only as labeled background/benchmark context).
- 2026-10-17: Added team-architecture.md (3 workstreams: edge/hardware, frontend+watch, vision/ML; model/event/alert contracts; milestones). Tried the qnxpi SSH test from this Windows machine: alias not configured here (host unresolved), so the Pi was not reached.
- 2026-10-17: Researched prior art and low-disturbance setups; added prior-art-and-setups.md (belt/tray camera recommended first, robot only for open litter).
- 2026-10-17: Searched for colored-leg-band / hen re-ID data; added section 7 to prior-art-and-setups.md (no leg-band dataset found; Chicks4FreeID and Roboflow 'chickens' as partial starts; top-down cameras can't see leg bands).
