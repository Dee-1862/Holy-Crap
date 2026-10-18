# System Architecture: Pi -> Backend -> Watch and Mobile

Written 2026-10-17. Combines [vision-design-v2.md](vision-design-v2.md) (what the vision does), [team-architecture.md](team-architecture.md) (who builds what) and the group decision in [game-plan.md](game-plan.md). Sizes, timings and battery claims are estimates until measured.

## 1. Big picture
```
 PI 5 / QNX 8.0.0 (edge, per camera)                  BACKEND (laptop / small server / cloud)           CLIENTS
 +--------------------------------------+            +-------------------------------------+
 | Camera Module 3 (QSF)                |            | Mosquitto broker                    |    +--------------------+
 |  low-res stream + full-res still     |            |   topics: detections, status, alerts|--->| M5Stack StopWatch  |
 |        |                             |   Wi-Fi    | Backend service                     |    |  alerts, 2 buttons |
 |  [1] change trigger (bg difference)  |  MQTT/HTTP |   validate -> store (SQLite)        |    +--------------------+
 |  [2] detector (TFLite, YOLO11n)      |----------->|   alert engine (per group, per N)   |
 |  [3] crop classifier (full-res crop) |            |   ack/escalate handling             |    +--------------------+
 |  [4] group mapper (groups.json)      |            |   REST + WebSocket API              |--->| Mobile dashboard   |
 |  [5] evidence snapshot (JPEG)        |            |   notifications (push / SMS / call) |    | (PWA in browser)   |
 |  [6] spool queue (store-and-forward) |            |   feedback labels -> ml/ retraining |    +--------------------+
 |  [7] publisher + heartbeat           |            +-------------------------------------+
 +--------------------------------------+                         ^
                                                                  |  optional: ESP32 sensor nodes (temp/humidity/ammonia) publish to the same broker
```

## 2. What runs on the Raspberry Pi 5 (QNX)
| # | Component | Notes |
|---|---|---|
| 1 | **Camera capture** | C++ via QNX Sensor Framework (no Python API for QSF). Low-res frames continuously (e.g. 1-2 FPS), full-res still only when a candidate is confirmed. Based on QNX AI Camera App's capture code, headless (no Screen window, non-root) |
| 2 | **Change trigger** | Cheap background difference on downscaled grayscale; finds *new* droppings, ignores old dirt and brief bird movement |
| 3 | **Detector** | TFLite YOLO11n (INT8 if accuracy holds) on changed regions; runtime from the QNX tensorflow port (or ONNX Runtime if it installs on 8.0.0) |
| 4 | **Crop classifier** | Small CNN on the full-res crop; outputs normal / abnormal / uncertain (+ internal 4-class scores) |
| 5 | **Group mapper** | Point-in-polygon with `groups.json` (group_id, polygon, head count). Boundary hits tagged `ambiguous` |
| 6 | **Evidence snapshot** | One JPEG per abnormal/uncertain event (plus optionally the last few seconds of thumbnails); kept in a small ring buffer on the Pi |
| 7 | **Spool queue** | Each event written as a JSON file in a spool directory before sending. If Wi-Fi drops, events wait and are sent later in order. Prevents lost alerts and decouples inference from networking |
| 8 | **Publisher** | Separate small process: reads the spool, sends over MQTT (mosquitto port) or HTTP POST fallback, deletes on ack. Python at `/system/bin/python3` is already present if easier than C++ |
| 9 | **Heartbeat + health** | Every 30 s: uptime, CPU temp, camera ok, model version, queue depth, clock offset |
| 10 | **Config** | Reads `groups.json`, thresholds, model path; updated from backend on request, with version numbers |

Not on the Pi: dashboards, alert rules, long-term storage, model training.
Process model: one C++ process for capture -> inference -> spool write (no frames passed between processes); one publisher process.

## 3. What is pushed (and what is not)
| Message | When | Size (rough) | Path |
|---|---|---|---|
| Detection event JSON | each confirmed new dropping | under 1 KB | MQTT `.../detection`, QoS 1 |
| Heartbeat | every 30 s | under 1 KB | MQTT `.../status`, retained, last-will "offline" |
| Evidence snapshot | only abnormal/uncertain events | tens to a couple hundred KB | HTTP POST to backend; event carries `snapshot_id` |
| Full video | never by default | - | (keeps inference on the QNX device, avoids a Wi-Fi load problem) |

Event fields: schema, device_id, group_id, group_size, ts (UTC), label (normal/abnormal/uncertain), confidence, type_hint (optional, internal), model_version, region_conf, bbox, snapshot_id, latency_ms. Only abnormal/uncertain events are sent in full; normal detections can be aggregated into per-group counts every few minutes to save bandwidth.

Time: NTP on the Pi (verify it exists on the image), timestamps UTC.

## 4. Backend
- **Broker:** Mosquitto (plain on the LAN first; add TLS and passwords before any real deployment).
- **Backend service:** subscribes to detections/status, validates schema, stores in SQLite, runs the alert engine, serves REST + WebSocket for the web app, receives snapshot uploads, handles acks.
- **Alert engine:** per group, count abnormal events in a window, normalized by `group_size` with a minimum count (default idea: at least 3 abnormal in 10 min; tune on data). Also raises "device offline" if heartbeats stop, and "uncertain burst" separately from "abnormal".
- **Notification fan-out:** alert -> MQTT `alerts` topic (watch), WebSocket (dashboard), optional web push / SMS / phone call through a messaging provider (account needed, costs; stretch goal).
- **Feedback store:** every human response (confirmed / false alarm) with the snapshot becomes a labeled example exported to `ml/` for retraining.

## 5. StopWatch (ESP32-S3, 1.75" round AMOLED, 2 buttons, touch, vibration, speaker)
Subscribes to the `alerts` topic over Wi-Fi (MQTT client) and shows a short summary. It never sees raw detections.

Screens: home (barn color + number of groups in alert; offline banner if broker unreachable), group list (swipe), alert popup (group name, "abnormal x3 in 10 min", time, vibration + beep until acknowledged).

**Buttons (proposal; the device has two programmable buttons):**
| Input | Action | Sent to backend |
|---|---|---|
| Button 1, short press | **Acknowledge** ("I'll go look") | `ack` |
| Button 1, long press | **False alarm** ("No, looks normal") | `feedback: false_alarm` -> becomes a training label |
| Button 2, long press (hold ~2 s, with vibration confirm) | **Escalate**: notify vet/owner contact list | `escalate` -> backend sends the message |
| Touch | Swipe between groups; tap to open details; "Looks abnormal - confirmed" | `feedback: confirmed` |

Use a long press for escalation so a pocket press never contacts anyone. Yes/no on the decision maps to **Confirmed / False alarm** feedback, which doubles as free data labeling.

**On "kill":** I have not put a cull/kill button on the watch. Reasons: alerts are advisory and will have false positives; the decision is irreversible; a farm cull decision belongs to a person on site with a vet, and the research base for this project (PR #1) explicitly sets a no-cull-path rule. The watch's strongest action is "escalate to a person" (contact vet/owner). If you want a cull workflow it should be a separate, deliberate human process, not a device button.

The watch can't place calls itself: "contact someone" means the backend sends an SMS/push/call through a provider, or opens a Telegram/WhatsApp-style message (needs an account, a contact list and cost; stretch goal).

Offline behavior: if Wi-Fi or the broker drops, show "OFFLINE" in red so silence is never read as "all healthy"; queue acks locally and send when reconnected. Battery life with Wi-Fi on a 450 mAh battery is unmeasured; test it.

## 6. Mobile dashboard
Simplest path: the same responsive web app (PWA) the backend serves, installable to the phone home screen.
- Live updates via WebSocket/SSE; group tiles (green/amber/red), per-group history, device health, alert log with snapshots, acknowledge / false alarm / escalate buttons that mirror the watch.
- Push notifications: Web Push needs HTTPS and a service worker; quick alternative = a Telegram bot for alerts while the web app is built.
- Access: login required (alerts and images are farm data). On a LAN-only demo, serve it from the backend machine.
- Not required for the hackathon demo: multi-user roles, offline mode.

## 7. Failure handling
| Failure | Behavior |
|---|---|
| Wi-Fi down | Pi spools events; watch shows OFFLINE; backend raises device-offline after missed heartbeats; spool drains on reconnect |
| Broker/backend down | Same as above; Pi keeps inferring and spooling (spool has a size cap; drop oldest normal events first, never abnormal) |
| Camera lost | Heartbeat reports camera not ok; backend alert "device unhealthy" |
| Pi reboot | Services start on boot; spool persists on disk |
| Clock wrong | Heartbeat reports offset; backend flags events with untrusted time |
| Model update | Versioned model + config; Pi keeps the previous model until the new one self-tests |

## 8. Can we train on the Raspberry Pi?
**No, not for this model; train off-device and run the exported model on the Pi.**
- The Pi 5 is CPU-only here (no verified GPU/accelerator path on QNX), so even a nano detector would take many hours to days to train (estimate), while an L4 GPU on Veri or a laptop GPU takes about 1-2 hours (rough guess, unmeasured).
- QNX has no easy training stack: the oss.qnx.com PyTorch port exists but is heavy and not meant for this. TFLite on-device training exists in principle but is limited and would not be a sensible first path.
- Training needs the 8.5 GB dataset and lots of RAM; the Pi should run inference only.

What the Pi *can* do cheaply (no neural-network training):
- Learn the **background model** for the change trigger.
- **Tune thresholds** (confidence, min event count) from feedback.
- **Collect data:** save snapshots and the watch/phone feedback labels for later retraining off-device.
- Optional later: a tiny on-device calibration of the classifier's last layer using feedback; treat as research, not MVP.

Loop: Pi collects snapshots + human labels -> backend stores -> `ml/` retrains on a GPU -> new versioned `.tflite` is pushed to the Pi.

## 9. Build order (maps to the three roles)
1. B: broker + backend + simulator + web app + watch against fake events (no Pi needed).
2. A: camera frames on Pi 5, run stock model, spool + publisher, heartbeat.
3. C: first YOLO11n model, TFLite export, hand to A.
4. Join: real detections -> alerts -> watch + phone; add feedback buttons.
5. Evaluate (latency, false alarms per group-day, group-assignment accuracy) for the paper.

## 10. Open questions
- Where does the backend run, and is the Pi able to reach it on the barn Wi-Fi?
- Does the Pi image have NTP and a working MQTT/HTTP client? (mosquitto port or Python on the Pi)
- Who receives escalations (vet/owner contact list), and through what channel and account?
- Do we need accounts/logins for the dashboard in the demo?
- StopWatch SDK/firmware route (Arduino vs ESP-IDF vs M5 libraries) and actual battery life.
