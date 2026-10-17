# Game Plan: Holy-Crap (Poultry Fecal Health Monitor)

## Goal
Detect abnormal chicken droppings on a barn floor with an edge vision device and alert the farmer before birds start dying. Classes: Healthy, Coccidiosis, Salmonella, Newcastle Disease (NCD).

## Important scoping note
The system classifies **droppings on the floor, not individual hens**. With many hens, a dropping cannot be tied to one bird. The output is "zone X has abnormal droppings", which is what a farmer can act on anyway. Per-hen attribution would need a separate tracking problem and is out of scope.

## Architecture
```
[CSI camera] -> [Pi 4 on QNX]
                  Stage 1: dropping detector (YOLO-family, small)
                  Stage 2: crop classifier (MobileNetV2, 4 classes + confidence)
                  Log (zone/time/class/conf) -> local store
                  -> Wi-Fi/MQTT -> dashboard + alert
                                      -> [ESP32 display node] (farmer-side alert)
[ESP32 sensor nodes] (optional: temp/humidity/ammonia) -> MQTT
```

## Hardware decision (see research.md for sources)
- **Baseline: ONE QNX Raspberry Pi 4 + one camera.** Enough to prove the whole idea. Do NOT cluster several Pis to share one workload; there's no benefit.
- A Pi 4 has one CSI camera port. If one camera can't cover the area, try in this order: (1) move the camera (trolley/robot), (2) add a USB camera to the same Pi (CPU is the limit), (3) only then add more independent Pis, each owning a zone and reporting to one broker.
- Extra Pis add **coverage only**, not accuracy or speed.
- **ESP32 cannot run QNX** (no QNX port found). Use ESP32 only for what it is good at: sensors and a small alert display. It cannot run the vision models.
- M5Stack StopWatch (ESP32-S3, 1.75" AMOLED, Wi-Fi, speaker, vibration) = good farmer-side alert/status device, not a vision node.

## Phases
1. **Data**: get the public 4-class dataset (verify name/license, see research.md). Collect own barn images later; public data will not match real lighting/bedding.
2. **Prototype on laptop**: train classifier first (the easier stage); then detector. Measure accuracy per class, watch the confusion between Cocci and Healthy-dark-brown.
3. **Bring-up on QNX Pi 4**: flash QNX SDP 8.0 Quick Start Target Image, confirm camera capture works (Camera Module 3 is listed as supported), run a still-image inference.
4. **Port inference**: ONNX Runtime / TFLite on QNX (check availability and CPU latency; Pi 4 has no GPU compute path to rely on). Target: 1-2 FPS is enough for a slow-moving platform.
5. **Alerting**: MQTT -> dashboard; ESP32 StopWatch shows alert + vibrates.
6. **Field test**: static mount first, mobile robot/trolley later.

## Risks
- Dataset domain gap (lab/photo images vs. dusty barn camera).
- Pi 4 CPU-only inference speed; may need a smaller model or lower resolution.
- Unverified: QNX ML runtime support, camera stack details. Resolve in phase 3 before committing.
- Fecal color overlaps (diet, bile, cecal droppings are normal but look abnormal). Expect false positives; alert on repeated detections per zone, not single frames.
- Not a veterinary diagnostic; frame output as "suspected, send sample to vet/lab".

## Open questions for the user
- Static camera, or moving robot/trolley? (Changes mounting, motion blur, power.)
- Barn size / number of zones?
- How much floor area must one camera cover? (Decides whether a second Pi is ever needed.)
- Is this a school/competition project (QNX challenge?) with a deadline?

## Assumptions (decided 2026-10-17)
- **Wi-Fi is available throughout the barn** and is the only network link for now. Revisit if coverage proves unreliable (risk: dead spots, dust, metal structures).
- Transport: MQTT over Wi-Fi (fallback: HTTP POST if MQTT isn't available on QNX; unverified).

## Scaling layout (optional, only if one Pi can't cover the area)
- Each added QNX Pi 4 + CSI camera owns one coverage zone; each runs the full pipeline and publishes only small results (zone ID, time, class, confidence).
- One MQTT broker (on a Pi, small server, or cloud) collects everything. Needs NTP time sync on every node.
- Alert rule: repeated abnormal detections per zone in a time window (e.g. 3+ in 10 min), not single frames.
- ESP32 nodes: sensors (temp/humidity/ammonia) and alert displays only. They never run the vision models.
- Start with 1 Pi (the default). Add a 2nd only if coverage demands it, and use it to validate zone IDs and the shared broker before buying more.

## M5Stack StopWatch role: glanceable status + alerts (not a full dashboard)
Screen is 1.75" round, 466x466, so keep content inside the center circle.
1. Home: overall barn color (green/amber/red) + number of zones in alert.
2. Zone pages (swipe): zone name, last detection time, suspected class, confidence.
3. Alert popup: "Coccidiosis suspected, Aisle 4"; vibrate + beep; touch to acknowledge.
4. Optional: temp/humidity/ammonia value from sensor nodes.
- Subscribes to the MQTT broker over Wi-Fi; runs standard ESP32 firmware (Arduino/ESP-IDF + M5 libs), not QNX.
- Images, history and configuration live on a separate web dashboard (phone/laptop).
- To test: battery life with Wi-Fi on, behavior when Wi-Fi drops (show "offline" state).
