# Team Architecture: 3 Workstreams

Goal: three people work in parallel without blocking each other. They only meet at **two written contracts** (below). Anything not in a contract is private to its owner.

| Role | Owns | Folder |
|---|---|---|
| **A. Edge/Hardware** | Raspberry Pi 5 on QNX: camera, TFLite runtime, inference loop, publishing detections, on-device benchmarks | `edge/` |
| **B. Frontend/System** | MQTT broker + backend (alert rules, storage), website dashboard, M5Stack StopWatch firmware (and optional ESP32 sensor nodes) | `app/` (`backend/`, `web/`, `watch/`) |
| **C. Vision/ML** | Datasets, training, evaluation, TFLite export, model versions, paper experiments | `ml/` |

## Data flow
```
          model contract                         event contract                     alert contract
[C: ml/] ----------------> [A: edge/ on Pi 5] ----------------> [B: broker+backend] ------------> [web dashboard]
 train/eval/export          camera -> TFLite -> detections       alert rules + storage    \-----> [StopWatch]
 .tflite + labels.json      MQTT over Wi-Fi                                                  (ESP32-S3)
```

## Contract 1: Model (C -> A)
A model release is a folder `ml/releases/vX.Y.Z/` containing:
- `model.tflite` (INT8 if accuracy holds, otherwise float32)
- `labels.json`: `["coccidiosis","healthy","ncd","salmonella"]` (order = output index; never reorder without a major version bump)
- `model.json`: input size (e.g. 224x224), channel order (RGB), normalization (e.g. `x/255` or `[-1,1]`), output type (softmax probabilities), stage (`classifier` or `detector`), training dataset + split used, test metrics, model size, git commit
- `CHANGELOG` line in `docs/changes.md`

Rules: A reads `model.json` and does not hard-code preprocessing. C must only ship models that convert to TFLite and are checked with the same TFLite version A builds on QNX (record it in `model.json`). Until C ships a real model, C hands A a **stub** (e.g. the untrained or off-the-shelf MobileNet) so A can finish the pipeline.

## Contract 2: Detection event (A -> B), JSON over MQTT
Topic: `holycrap/v1/{site_id}/{zone_id}/detection` (QoS 1)
```json
{
  "schema": 1,
  "device_id": "pi5-01",
  "zone_id": "aisle4-b",
  "ts": "2026-10-17T14:03:22Z",
  "model_version": "v0.1.0",
  "label": "coccidiosis",
  "confidence": 0.91,
  "scores": {"coccidiosis": 0.91, "healthy": 0.05, "ncd": 0.01, "salmonella": 0.03},
  "bbox": [x, y, w, h],
  "latency_ms": 420
}
```
Other topics from A: `.../status` (heartbeat every 30 s, retained, with last-will "offline": temperature, CPU %, camera ok, model_version, uptime). No images over MQTT by default; thumbnails only on explicit request (later, via HTTP).

Time: the Pi must have NTP; timestamps are UTC ISO-8601.
Fallback if no MQTT client builds on QNX: A POSTs the same JSON to `POST /api/v1/detections` on B's backend. B supports both.

## Contract 3: Alert (B -> watch/web)
Topic: `holycrap/v1/{site_id}/alerts` (QoS 1), published by the backend after applying the rule (default: >=3 abnormal detections in one zone within 10 minutes; thresholds are config, tuned by B with C's false-positive numbers):
```json
{"schema":1,"alert_id":"...","zone_id":"aisle4-b","label":"coccidiosis","count":3,"window_min":10,"severity":"amber","first_ts":"...","last_ts":"..."}
```
The watch subscribes to alerts only (not raw detections). Acknowledgement goes back on `.../alerts/{alert_id}/ack`.

## Workstream plans

### A. Edge/Hardware (Pi 5, QNX 8.0.0, Camera Module 3)
1. Reach the Pi (SSH alias `qnxpi`, see TARGET.md); note it is configured only on the Mac that set it up.
2. Camera: QSF sensor config for Camera Module 3 (`post_startup.sh`).
3. Build TFLite + OpenCV ports; build and run QNX's `ai-camera-app` unchanged (face detection) as the proof of pipeline.
4. Replace the model with C's stub; strip the UI to a headless loop (camera -> preprocess -> TFLite -> JSON).
5. Publish detections/heartbeat (MQTT client or HTTP fallback); make it start on boot and survive Wi-Fi drops (local queue).
6. Benchmarks for the paper: latency median/p95, RAM, CPU temp/throttling, power, FP32 vs INT8, input-size sweep, written to `edge/bench/*.csv`.
Done when: Pi runs headless on boot, sends valid detection events from live camera frames at >=1 FPS.

### B. Frontend/System (backend, web, watch)
1. Pick and run the broker (e.g. Mosquitto on a laptop/small server/cloud); define auth later, plain LAN first.
2. Backend: subscribe to detections, validate against the schema, store (SQLite is enough), apply alert rule, publish alerts, expose a REST API for the web app.
3. Simulator: a script that publishes fake detections (healthy-only, a cocci outbreak in one zone, a device going offline). **This lets B and the watch work with no Pi at all.**
4. Web dashboard: zone overview (green/amber/red), per-zone history, device health (last heartbeat), alert log, thumbnails later. Mobile-friendly.
5. StopWatch (ESP32-S3, 466x466 round AMOLED): home screen (barn color + alert count), swipeable zone pages, alert popup with vibration + beep, touch to acknowledge, explicit "offline" state when Wi-Fi/MQTT drops. Keep content inside the center circle.
6. Optional ESP32 sensor nodes (temp/humidity/ammonia) on `holycrap/v1/{site}/{zone}/env`.
Done when: with the simulator running, web and watch show the right colors/alerts and the offline state, and the same works with the real Pi.

### C. Vision/ML
1. Data: download Zenodo/Kaggle data, hash files, dedupe (perceptual hash), confirm `pcr*` = lab images, write the source-aware split files (committed, so everyone evaluates the same way).
2. Baselines (MobileNetV2/V3, EfficientNet-B0/Lite, ResNet): macro-F1, per-class recall, confusion matrix.
3. Cross-source and farm-vs-PCR evaluation (paper contribution A); extra datasets (Nigeria etc.).
4. TFLite export (FP32 + INT8), accuracy check after conversion, hand-off as a model release to A. First release should be quick and imperfect so A is unblocked.
5. Robustness (blur, light, color shift, bedding backgrounds), calibration, Grad-CAM.
6. Detector stage experiments only if/when floor images with boxes exist.
Done when: a released model.tflite with documented metrics runs on the Pi and its on-device accuracy matches the laptop within a stated tolerance.

## Integration milestones
| # | Milestone | Needs |
|---|---|---|
| M0 | Contracts agreed (this file), repo folders created, simulator + stub model exist | all |
| M1 | A: ai-camera-app runs on Pi 5. B: simulator -> backend -> web/watch works. C: baseline model + first TFLite release | parallel, no dependencies |
| M2 | Pi publishes real detections from the stub/first model; B displays them | A + B + C v0.1 |
| M3 | Real fecal model on Pi; on-device vs laptop accuracy check; first benchmark table | A + C |
| M4 | Alert rule tuned on replayed test sequences; watch field test over barn Wi-Fi | B + C |
| M5 | Paper experiments frozen, figures generated, writing | all |

## Working agreements
- `main` is protected by convention: work on branches (`edge/...`, `app/...`, `ml/...`), merge via pull request, one other person reviews anything that touches a contract.
- Contract changes: edit this file in a PR, bump the `schema`/`model` version, tell the other two before merging.
- Everyone appends to `docs/changes.md` (one line per meaningful change) and `docs/mistakes.md` (what went wrong, so it isn't repeated).
- Large files (datasets, `.tflite`, PDFs) stay out of git unless small; use releases or shared storage and commit a manifest with hashes.
- No secrets in the repo (SSH, Wi-Fi, broker passwords): each person keeps theirs locally, as TARGET.md already does for SSH.
- Short sync twice a week: what shipped, what is blocked, any contract change.

## Paper ownership (maps to docs/paper-plan.md)
- C: datasets, models, cross-source generalization, robustness, calibration (sections 4-6).
- A: QNX edge benchmark, deployment, quantization measurements.
- B: alert policy simulation, system architecture, user-facing results; also related work table if time allows.
- Everyone reviews everyone's section; one person owns final assembly.

## Open questions
- Who runs the broker/backend, and where (laptop, VPS, cloud)? Needed before M2.
- Is the Pi 5 reachable by all three, or only through one person's tunnel (the SSH alias lives on one Mac)? A needs a shared way to run jobs on it.
- Is there access to a real barn or only bench tests? Decides whether M4 happens on real hens.
- Deadline/submission venue (drives how much of C's optional work is in scope).
