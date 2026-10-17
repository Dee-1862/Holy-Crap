# BIBLE: Holy-Crap poultry health research

Last updated: 2026-10-17

This is the single source of truth for the project. Where older notes,
including [research.md](research.md), conflict with this file, this file
controls; links to the evidence are given throughout. Status labels:
**Verified**, **Working assumption**, **Proposed**, **Unknown**.

## 1. Purpose and non-goals

**Purpose.** Build a fixed overhead RGB camera system for one chicken pen
that:

- monitors the flock continuously,
- tracks individuals when feasible,
- detects newly deposited droppings and associates them with a bird only
  when the evidence supports it,
- surfaces health/welfare anomalies for a farmer to review.

**Non-goals.** [Verified decisions]

- Disease diagnosis: the system does not diagnose disease.
- Automatic culling, and no automated treatment/isolation action of any kind.
- Pathogen identification from images.
- Replacing veterinary or laboratory testing.
- Guaranteed identity for every bird, or guaranteed per-bird dropping
  attribution.

## 2. Current product thesis

Status: **Proposed**.

Build an explainable early-warning/triage system, not a visual disease
diagnosis and not an automatic-cull system. The camera observes behavior,
activity, and droppings; the system shortlists birds and zones and hands the
farmer persistent, explainable anomalies with evidence clips. Full argument:
[research/PAPER.md](research/PAPER.md) §1.

## 3. Safety and decision boundary

- The system is advisory. Every output is a flagged anomaly for human
  review, never a diagnosis and never an instruction. [Verified decision]
- Camera alerts never authorize treatment or culling. Suspected
  high-consequence or legally reportable disease must be escalated promptly
  to a veterinarian or animal-health authority. Isolation and biosecurity
  measures follow their guidance while testing is pending; laboratory
  testing, not the camera, confirms a diagnosis. Exact duties depend on
  pathogen/pathotype and jurisdiction. [Verified decision]
- Product wording must avoid diagnostic language: no “detects disease,” no
  “diagnoses,” and no disease names as MVP output classes. Any future disease-
  association study requires a separate intended use and validation path (§9).
- This document deliberately describes no path to automatically killing
  animals; there is none in this system.

## 4. System concept

Status: **Proposed**.

The primary operating path is:

```text
Raspberry Pi Camera Module 3
  -> Raspberry Pi 5 / QNX Sensor Framework / AICA-derived capture
  -> reliable barn Wi-Fi
  -> desktop processing and primary UI
       - live and recorded video
       - flock, zone, and bird histories
       - evidence clips and alert review
       - acknowledgement and audit trail
  -> optional M5Stack StopWatch wall display
       - current state, alert count, connectivity, acknowledgement
```

Reliable, high-bandwidth Wi-Fi is a **Working assumption** for the current
design. It lets the desktop application be the primary interface and allows
camera data to leave the Pi. The exact stream format, buffering policy, and
recovery behavior are still **Unknown**. Full disconnected operation is out of
current scope; explicit stale/offline signalling and bounded local buffering
are mandatory.

The stock QSTI camera path documents uncompressed recording and playback only;
H.264 and H.265 are not supported there. This does not prove that a custom
encoder is impossible, but compressed transport must be demonstrated before
the desktop stream is considered viable.

Raw HD video over barn Wi-Fi is not the baseline. At 1920×1080 and 30 FPS,
uncompressed payload is roughly 1.0 Gb/s at 16 bits per pixel and 2.0 Gb/s at
32 bits per pixel, before stride, metadata, and protocol overhead. The exact
format and stride must be measured on the target. Stage 1 must demonstrate a
compressed or downsampled preview, or choose local inference plus event clips,
sampled keyframes, or wired Ethernet. AICA supplies capture/inference
scaffolding, not network transport. Sources: [QNX camera frame types](https://qnx.com/developers/docs/7.0.0/com.qnx.doc.camera/topic/camera_frametype_t.html)
and [AICA README](https://gitlab.com/qnx/projects/ai-camera-app/-/raw/main/README.md).

A 120-day study of a different mobile system in a commercial broiler house
reported weak locations, packet loss, latency, and repeated reconnects. Those
figures are not forecasts for this fixed installation, but they justify an
actual-position site survey, buffering, acknowledgements, and a degraded-mode
test. Source: [commercial-house connectivity study](https://doi.org/10.3390/electronics15112406).

Inference placement is **Proposed, not decided**. Capture must run on the QNX
Pi. Models may run on the Pi, on the desktop, or be split between them. We will
choose after measuring stream quality, latency, Pi throughput, thermals, and
desktop workload. The M5Stack display is optional and cannot be the source of
truth.

Layers, in order of maturity:

1. Evidence-supported flock monitoring: activity and spatial/zone
   distribution.
2. Controlled-study or project-validation targets: gait/movement proxies,
   persistent inactivity, crowding/piling, and individual anomaly shortlisting.
3. Experimental new-dropping detection and appearance triage.
4. Veterinary-escalation workflow for persistent, nonspecific warning signs,
   without disease-name findings.

Field evidence supports flock activity and spatial/zone distribution.
Controlled work supports some gait/movement proxies. Isolation, persistent
inactivity, unresponsive-bird detection, crowding/piling, coarse feather
condition, and new-dropping deposition still require project validation. The
camera cannot reliably reveal subclinical disease, internal
lesions, pathogen identity, laboratory confirmation, precise individual
intake, or determine whether a visible dropping change comes from disease,
age, feed, or another flock-level factor. Sources:
[research/observables/camera-visible-health-signals.md](research/observables/camera-visible-health-signals.md).

**Dropping attribution.** This review found no end-to-end demonstration of
bird-to-resulting-dropping attribution in a crowded, free-moving floor pen.
Big Broiler supplies human-labelled `Defecating` actions on short broiler
tracklets, but not the resulting deposit, its location or appearance, or
persistent identity across clips. Qin et al. traced manure to a cage, not a
bird. Working hypothesis (testable): detect a new dropping by temporal
change/segmentation; look back over a short window in identity tracks; assign
only when one tagged bird occupies the deposition footprint and a visible
event cue supports it; otherwise mark it unattributed. Status: **Working
assumption** until the stage-5 experiment measures it. Sources:
[Big Broiler](https://github.com/decide-ugent/big-broiler-dataset) and
[Qin et al.](https://www.sciencedirect.com/science/article/pii/S0168169924003909).

## 5. Hardware inventory

### Verified compute target

| Item | Status | Facts |
|---|---|---|
| Compute | Verified | One Raspberry Pi 5, `aarch64le`, running QNX 8.0.0 |
| I/O | Verified | Headless: no keyboard, mouse, or local interactive display in normal operation |
| SSH | Verified | Alias `qnxpi`; user `qnxuser`; home `/data/home/qnxuser` |
| Python | Verified | `/system/bin/python3` |
| Runner | Verified | App `/data/home/qnxuser/qnx-runner-app`; spool `/data/home/qnxuser/qnx-runner` |

### Camera

| Item | Status | Facts |
|---|---|---|
| Selected camera | Verified decision | Raspberry Pi Camera Module 3 |
| Sensor/interface | Verified from manufacturer | Sony IMX708, 11.9 MP, 4608×2592, CSI-2, phase-detection autofocus |
| Published video modes | Verified from manufacturer | 1080p50, 720p100, 480p120 among the common modes |
| QNX target-image support | Verified in documentation | QNX lists Camera Module 3 on Raspberry Pi 5 as camera ID 3 (camera 1) and ID 4 (camera 2) |
| Exact units | Unknown | Count, standard vs wide lens, IR-cut vs NoIR, and hardware revision still need inventory |
| Deployment geometry | Unknown | Mount height, pen footprint, pixels per bird/dropping, focus strategy, lighting, cable length, and enclosure |
| Live target state | Unknown | Sensor Framework configuration, negotiated formats/resolutions/FPS, autofocus behavior, and long-run stability have not been tested on this Pi |

The standard module has a 66°×41° horizontal-by-vertical field of view (75°
diagonal); the wide version is 102°×67° (120° diagonal). For a level,
straight-down camera over a flat floor, the ideal footprint is
`2 × height × tan(FOV / 2)`. At 3 m, that is about 3.90×2.24 m for standard and
7.41×3.97 m for wide. At 1080p, the idealized resolution is about 493×481
pixels/m versus 259×272 pixels/m. Mode crop, distortion, tilt, obstructions,
and usable overlap will change those figures, so validate them from captured
frames before choosing wide. More coverage means fewer pixels per bird, so the
variant cannot be chosen from field of view alone. Color is important for dropping review;
standard IR-cut is the safer starting assumption unless we deliberately
design an IR/night mode. The module is specified for dry 0–50°C operation and
must be protected from moisture and condensation. Record mount height and pen
dimensions, calculate pixels per smallest bird/dropping target, then confirm
with representative frames under normal dust, humidity, temperature, and
lighting. Use a protected optical window, strain relief, and a documented
cleaning/fouling cadence. The supplied ribbon is only 200 mm, so keep the Pi
near the camera or validate an extension. Raspberry Pi 5 uses a
22-way mini camera connector while the module uses a 15-way connector, so the
correct standard-to-mini camera cable is required.
Shut down the Pi and disconnect external power before connecting or removing
the camera ribbon. Do not fold, crease, or strain the ribbon cable.

Sources: [Raspberry Pi Camera Module 3 product brief](https://datasheets.raspberrypi.com/camera/camera-module-3-product-brief.pdf),
[Raspberry Pi camera cables](https://www.raspberrypi.com/products/camera-cable/), and
[QNX QSTI camera documentation](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/next-steps.html).

### M5Stack StopWatch wall display

Status: **Selected, optional secondary display**. It is useful, but it is not
a launch constraint and never owns authoritative state or camera inference.

The selected M5Stack StopWatch (SKU C152) has an ESP32-S3R8 at 240 MHz,
16 MB flash, 8 MB PSRAM, 2.4 GHz Wi-Fi, a 1.75-inch 466×466 round AMOLED touch
display, buttons, vibration, microphone, 1 W speaker, RTC, 450 mAh battery,
USB-C 5 V input, and rear magnetic attachment. Its proposed wall screen shows
overall flock state, active alerts, affected bird or zone, alert age,
confidence/persistence, acknowledgement, and stream/device connectivity.
Video, history, configuration, and detailed review remain in the desktop UI.

The StopWatch receives low-rate, versioned event/status summaries only, never
video. Survey its 2.4 GHz-only link independently at the wall position. Show
the last successful update and an explicit stale/offline state. An
acknowledgement remains pending until accepted by the authoritative desktop;
an offline tap is never shown as confirmed.

For wall deployment, use protected continuous USB-C power and treat the
battery as a short continuity buffer until measured. Enclosure, dust/moisture
protection, screen visibility, AMOLED image retention, Wi-Fi reconnect,
auto-restart, and fleet updating are open tests. Use mechanical retention and
cable strain relief; the rear magnet alone is not accepted for a barn wall.
The published page gives no barn IP or operating-temperature rating, so the
enclosure and environment need acceptance tests. Prove cold boot and reconnect
after an outage; the 450 mAh battery is not an assumed UPS. Inventory the hardware
revision before touching the rear pins: on some v1.0 units a pin labeled
`BAT` is actually 5 V input, while v1.0.1 changes that pin to an actual battery
connection. Never connect a lithium battery to a v1.0 pin labeled `BAT`; on
affected units it is actually 5 V input. Source:
[M5Stack StopWatch documentation](https://docs.m5stack.com/en/core/StopWatch).

### Compute power and cooling

The Raspberry Pi 5 vendor recommendation is a 5 V/5 A (27 W) supply, and
active cooling is recommended for sustained heavy workloads. Use protected
barn power and prove cold-start/autostart recovery. Treat the fan, filter, and
enclosure as maintenance items: define a cleaning cadence and measure power,
temperature, throttling, and image quality under representative dust and heat,
not only on a clean bench. QNX documents watchdog capability, but enabling it
or changing startup is a later operations decision, not part of read-only
discovery. Sources: [Raspberry Pi 5 product page](https://www.raspberrypi.com/products/raspberry-pi-5/)
and [Raspberry Pi documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).

## 6. Headless QNX Pi: connection and operating procedures

Recorded target configuration (2026-10-17); re-verify reachability before
target work. Details also in [TARGET.md](../TARGET.md).

- Connection test:
  `ssh -o BatchMode=yes -o ConnectTimeout=20 qnxpi 'uname -a; id'`
- Authentication and Railway proxy details live in the user's SSH
  configuration and must not be recorded in this repository. Never place
  private keys, tokens, Wi-Fi credentials, or authentication state in the
  repository.
- Use direct SSH for short commands.
- Use the persistent runner for builds, tests, or jobs that must survive a
  dropped SSH session. The runner executes argv directly without a shell and
  does not run as root.
- Runner status:
  `ssh qnxpi /data/home/qnxuser/qnx-runner-app/status-runner.sh`
- The aports tree is not configured or verified.
- The active physical interface and onboard Wi-Fi driver, firmware, and
  association state are unverified. The working SSH/Railway path does not prove
  the planned WLAN path. Inventory `io-sock`, interfaces, driver/firmware
  presence, and association read-only before selecting transport; QNX documents
  that enabling onboard Wi-Fi can require image/BSP components
  ([Pi 5 driver commands](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp_raspberrypi.bcm2712.rpi5_8.0/topic/driver_commands.html)).
- Do not change the Railway reverse tunnel or `/boot/onboot` unless
  connectivity maintenance is explicitly requested.

## 7. Software

### Verified installed

| Software | Status |
|---|---|
| QNX 8.0.0 on Raspberry Pi 5 | Verified |
| Python 3 at `/system/bin/python3` | Verified |
| `qnx-runner-app` (persistent job runner) | Verified |

### Selected camera application foundation

QNX's [AI Camera App (AICA)](https://gitlab.com/qnx/projects/ai-camera-app)
is the selected starting point, not a finished barn application. Status:
**Verified selection; target compatibility not yet demonstrated**.

AICA is an Apache-2.0 sample that demonstrates frame capture through QNX
Sensor Framework camera APIs, OpenCV processing, QNX Screen rendering, and
TensorFlow Lite inference. Its documented QNX dependencies are Sensor
Framework camera/base, multimedia AOI/MMF core, and Screen image codecs. It
lists Camera Module 3 as tested and requires QNX SDP 8.0, but its recommended
platform is Raspberry Pi 4 B. It does not document the combined Pi 5 + Camera
Module 3 + AICA configuration.

The official AICA build path is a cross-build with QNX SDP 8.0 on a supported
host; its README says the instructions were tested on Ubuntu 20.04 and 22.04.
Do not assume a native-QNX or macOS build until one is proved. The bundled
face/style demo pipeline is only a compatibility test and will be replaced;
it is not poultry logic.

Stock AICA is GUI-first: it creates QNX Screen/EGL/GLES windows and listens
for mouse/touch input. Its README also describes root-SSH deployment. Neither
assumption matches this headless, non-root target. We will reuse or fork its
QSF capture and TensorFlow Lite integration, preserve its Apache license and
notices, and separate capture/inference from rendering and input. We will not
enable root SSH merely to follow the sample. QNX also documents a Pi 5 Screen
failure risk when root-owned and non-root graphics processes are mixed, so
the service/user model must be tested deliberately.

Primary sources: [AICA README](https://gitlab.com/qnx/projects/ai-camera-app/-/raw/main/README.md),
[build file](https://gitlab.com/qnx/projects/ai-camera-app/-/raw/main/common.mk),
[license](https://gitlab.com/qnx/projects/ai-camera-app/-/raw/main/LICENSE.txt),
and [QNX Pi 5 Screen release notes](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_gfx.sdp80.PUA2025-010.bsp.broadcom.rpi5.bcm2712.html).

The official QNX 8 Raspberry Pi 5 BSP exists but is currently classified as
experimental software. That is acceptable for this prototype, not a
production-support guarantee. Source: [QNX Raspberry Pi 5 BSP release notes](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_sdp80.bsp.broadcom.rpi5.bcm2712.html).

Everything beyond the verified target and the selected foundation is
proposed or unverified on the physical Pi.

### Proposed components

| Component | Purpose | Status |
|---|---|---|
| QSF capture service | Pull Camera Module 3 frames on the headless QNX Pi, based on AICA | Selected approach; not yet run on target |
| Video transport | Send live/recorded camera data over Wi-Fi | Proposed; codec/protocol/buffering TBD |
| Desktop application | Primary live view, history, alert review, configuration, and audit trail | Proposed; required |
| Identity/detection | Detect birds; assign identities where markers allow | Proposed |
| Tracking | Multi-object tracking across frames | Proposed |
| Activity/zone features | Flock activity, zone occupancy, crowding, inactivity | Proposed |
| New-dropping detection | Temporal-change/segmentation detection of fresh droppings | Proposed |
| Normal/abnormal triage | Flag abnormal-looking droppings for review | Proposed |
| Event store | Persistent, time-stamped events with evidence clips | Proposed |
| Inference placement | Pi, desktop, or split | Unknown until benchmarked |
| StopWatch client | Optional glanceable status/alert display | Proposed; non-blocking |
| Event transport | Summaries to UI/display; MQTT, WebSocket, or HTTP | Proposed; protocol undecided |

The video and event transport gate includes authentication, encryption,
device-key provisioning and rotation, replay resistance for acknowledgements,
and a strict rule that no credentials enter the repository. The protocol is
still undecided.

AICA documents OpenCV and TensorFlow Lite build paths for QNX; their presence
and operation on this target are still unverified. ONNX Runtime and hardware
acceleration are also unverified. QNX background notes: [research.md](research.md);
bring-up plan: [03-open-questions.md](03-open-questions.md).

## 8. Data and research summary

- The best-characterized downloadable fecal collection reviewed in this pass
  has serious caveats: Machuve et
  al. farm-labeled v2 (6,812 images) and PCR-annotated v3 (1,255 images).
  Farm labels and PCR labels must never be treated as interchangeable; the
  authors flag likely label errors (Salmonella vs healthy). The records
  display no explicit license, so do not assume permission to redistribute,
  modify, or use the data in a product
  ([research/datasets/machuve-fecal-datasets.md](research/datasets/machuve-fecal-datasets.md)).
- The Nigerian collection provides 14,618 CC BY 4.0 images, but its labels are
  visual, its 94 reported physical instances create grouped-split leakage risk,
  and it is neither longitudinal nor pathogen ground truth. Zhou et al. is the
  closest reviewed growth-cycle dropping-appearance collection, but it is a
  manure-belt dataset and cannot support deposition or bird attribution.
- Big Broiler labels tracked defecation actions but not the resulting deposit;
  Essien et al. provides 22 weeks of overhead multimodal data with no manual
  health, behavior, fecal, or pathogen labels and restricted raw access
  ([research/datasets/abnormal-droppings-datasets.md](research/datasets/abnormal-droppings-datasets.md)).
- Veterinary authorities support using visible signs as nonspecific warning
  signals; suspected high-consequence disease should be escalated promptly,
  and laboratory testing confirms the diagnosis
  ([research/evidence/clinical-limits-of-visual-diagnosis.md](research/evidence/clinical-limits-of-visual-diagnosis.md)).
- Identity research supports an ArUco/fiducial pilot as the phase-one
  approach; markerless identity is underdeveloped in field settings
  ([research/identity/aruco-marker-backpacks.md](research/identity/aruco-marker-backpacks.md),
  [research/identity/rfid-and-markerless-tracking.md](research/identity/rfid-and-markerless-tracking.md)).
- Across the reviewed vendor pages, positioning emphasizes weight and
  uniformity, movement and distribution, environmental or operational anomaly
  monitoring, auditability, and alerts. Feed, water, mortality, and
  disease-warning features are individual vendor claims or roadmap items, not
  independent evidence
  ([research/systems/industry-landscape.md](research/systems/industry-landscape.md)).
- Producer evidence suggests the grower may not be the sole buyer. In one
  regional, low-response Tennessee survey, only 46% of a contract-grower-heavy
  sample said they were the primary technology decision-maker. There is no
  credible poultry-specific dollar willingness-to-pay estimate in this review.
  Customer discovery must include growers and integrator/live-production
  managers and map payment, approval, data rights, service, and economic benefit
  ([research/practice/operator-needs-and-product-wedge.md](research/practice/operator-needs-and-product-wedge.md)).
- Full synthesis: [research/PAPER.md](research/PAPER.md). Numbered findings:
  [01-key-findings.md](01-key-findings.md). Sources: [02-bibliography.md](02-bibliography.md). Gaps:
  [03-open-questions.md](03-open-questions.md).

## 9. Staged build plan and evaluation gates

Status: **Proposed**. Each stage has a gate; do not start the next stage
without passing it.

| Stage | Work | Evaluation gate |
|---|---|---|
| 0. Capture + site survey | Inventory Camera Module 3 variant/cable, mount height, pen dimensions, lighting, enclosure, and physical/Wi-Fi interface state; prove Sensor Framework capture on Pi 5 | Stable representative frames; negotiated format, stride, FPS, reboot recovery, focus, footprint, and pixels per smallest target recorded; discovery makes no BSP or startup changes |
| 1. Desktop stream | Benchmark raw bandwidth, downscaling, encoder cost, and representative camera transport over the proposed Wi-Fi link | Authenticated and encrypted live view with bounded latency, local retention, timestamps, replay-resistant acknowledgements, and explicit stale/offline state; site survey plus 24-hour load test records throughput, loss, RTT/jitter, reconnects, and outages at actual positions; compressed transport demonstrated if required, with wired or local-inference fallback |
| 2. Instrument one pen | Mount overhead with controlled lighting; record baseline footage | Measured coverage and pixels per bird/dropping remain sufficient during normal barn work, dust, humidity, and lighting |
| 3. Flock metrics + UI | Activity/zone metrics; primary desktop alert workflow with evidence clips | False alarms per pen-day and operator follow-through measured |
| 4. ArUco pilot | Welfare-reviewed markers on a small flock | Visible-time identity rate, unknown-ID rate, marker loss/occlusion, handling burden |
| 5. Droppings | Detect new droppings and triage normal/abnormal appearance | Event detection and unattributed rates measured; no disease classes claimed |
| 6. Optional StopWatch | Show a versioned summary from the authoritative event state | Reconnect, stale-state, acknowledgement, power, and visibility tests pass |
| 7. Future disease-association research | Offline study using veterinary sampling, lab labels, and a prospective protocol; not part of the MVP | Separate intended use and independent validation are approved; otherwise do not deploy disease-name output |

Evaluation principles: split by the strongest available independent
acquisition unit (bird, flock, farm, date, or session), and keep near-duplicate
frames from one recording together;
measure event-level alert value, identity coverage, false alarms per
house-day, trusted-data uptime, missing/duplicate/stale frames, clock integrity,
maintenance interventions per flock, acknowledgement and inspection rate,
action yield, persistence delay, latency, missed incidents, operator
follow-through, and performance against the manual-record baseline. Prioritize
data collection and label governance over model shopping. Model families at
a high level only: object detection/segmentation, multi-object tracking,
pose/activity estimation, temporal anomaly detection, embedding-based
re-identification. No YOLO version is prescribed.

## 10. Decisions made

- 2026-10-17 (this pass): product conclusion is an explainable
  early-warning/triage system, not visual disease diagnosis or automatic
  culling. Supersedes the historical four-class disease classifier framing;
  evidence in [research/PAPER.md](research/PAPER.md).
- 2026-10-17 (this pass): the product may raise a nonspecific veterinary-
  escalation alert but does not present a disease name as a finding.
- 2026-10-17 (this pass): unattributed droppings are a valid first-class
  outcome, not an error state.
- 2026-10-17 (earlier): baseline is one Pi 5 + one camera; add nodes only if
  measured coverage or performance requires them ([game-plan.md](game-plan.md)).
- 2026-10-17 (earlier): droppings are reported per zone unless attribution
  evidence supports a bird ID (evolved from [game-plan.md](game-plan.md)).
- 2026-10-17 (earlier): ESP32 nodes are display/sensor clients, not this
  project's QNX camera-compute target ([game-plan.md](game-plan.md), [mistakes.md](mistakes.md)).
- 2026-10-17: Raspberry Pi Camera Module 3 is the selected camera and QNX
  AICA is the selected application foundation.
- 2026-10-17: reliable, high-bandwidth Wi-Fi is a working assumption; the
  desktop app is the primary UI and receives camera data.
- 2026-10-17: inference location is benchmark-driven; it may run on the Pi,
  desktop, or both.
- 2026-10-17: M5Stack StopWatch is an optional wall-mounted status client,
  not a hard constraint or source of truth.

## 11. Unresolved decisions

- Which Camera Module 3 variant and how many units are available: Unknown (§5).
- Whether Camera Module 3 + Pi 5 + AICA works reliably on the physical target: Unknown (§7).
- Video transport, buffering, desktop technology, and inference placement: Unknown (§7).
- StopWatch revision, enclosure, power behavior, and final protocol: Unknown (§5).
- Machuve dataset reuse rights: Unknown (§8).
- Pen dimensions, camera height, lighting, cable route, and coverage: open
  ([03-open-questions.md](03-open-questions.md)).
- Project deadline and pilot-site constraints: open
  ([03-open-questions.md](03-open-questions.md)).

## 12. Links

- [research/PAPER.md](research/PAPER.md): central synthesis
- [00-landscape-review.md](00-landscape-review.md), [01-key-findings.md](01-key-findings.md), [02-bibliography.md](02-bibliography.md),
  [03-open-questions.md](03-open-questions.md)
- [research/datasets/machuve-fecal-datasets.md](research/datasets/machuve-fecal-datasets.md)
- [research/datasets/abnormal-droppings-datasets.md](research/datasets/abnormal-droppings-datasets.md)
- [research/observables/camera-visible-health-signals.md](research/observables/camera-visible-health-signals.md)
- [research/identity/aruco-marker-backpacks.md](research/identity/aruco-marker-backpacks.md),
  [research/identity/rfid-and-markerless-tracking.md](research/identity/rfid-and-markerless-tracking.md)
- [research/systems/industry-landscape.md](research/systems/industry-landscape.md)
- [research/evidence/clinical-limits-of-visual-diagnosis.md](research/evidence/clinical-limits-of-visual-diagnosis.md)
- [research/practice/operator-needs-and-product-wedge.md](research/practice/operator-needs-and-product-wedge.md)
- [game-plan.md](game-plan.md) (current implementation sequence derived from this bible)
- [research.md](research.md) (older notes: QNX/M5Stack details)
- [TARGET.md](../TARGET.md) (target facts), [changes.md](changes.md), [mistakes.md](mistakes.md)
