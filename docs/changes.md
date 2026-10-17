# Changes Log

Newest first. One line per change: date, what, why.

- 2026-10-17: Established the research knowledge base under docs/ (BIBLE.md, research/PAPER.md, subject nodes, landscape, findings, bibliography, and open questions). Reframed the product as explainable early warning/triage rather than camera diagnosis. Selected Raspberry Pi Camera Module 3 and QNX AI Camera App, made the desktop the primary UI over a reliable-Wi-Fi working assumption, and made the M5Stack StopWatch an optional wall client. Rewrote game-plan.md to match.
- 2026-10-17: Corrected the target hardware to the verified Raspberry Pi 5 running QNX 8.0.0. Removed the Pi 4-specific camera claim and made CPU-only inference the working assumption until acceleration is verified. Added TARGET.md and AGENTS.md with target facts, connection steps, and operating rules.
- 2026-10-17: Created docs/ with game-plan.md, research.md, changes.md, mistakes.md. Initial plan from user's idea (two-stage fecal classification on QNX Raspberry Pi). Hardware recommendation: one Pi 4 per camera zone; ESP32 only for sensors/alert display.
- 2026-10-17: Decided to assume barn-wide Wi-Fi + MQTT. Added multi-node scaling layout and StopWatch screen design (status/alerts only; full dashboard on a separate web page) to game-plan.md.
- 2026-10-17: Reframed hardware: single Pi 4 + one camera is the baseline; extra Pis are optional and only for coverage. Updated game-plan.md hardware decision, scaling section, and open questions.
