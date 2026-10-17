# Game plan

This plan implements the current decisions in [BIBLE.md](BIBLE.md). The bible
controls if the two files ever diverge.

## Goal

Build a fixed, overhead poultry-monitoring system that turns camera footage
into explainable flock, zone, bird, and dropping anomalies for human review.
It does not diagnose disease, prescribe treatment, or make culling decisions.

## Working architecture

```text
Raspberry Pi Camera Module 3
  -> Raspberry Pi 5 running QNX 8
  -> QNX Sensor Framework capture based on ai-camera-app
  -> reliable high-bandwidth Wi-Fi (working assumption)
  -> desktop application (primary UI and authoritative review workflow)
       -> live/recorded video and evidence clips
       -> flock/zone metrics and individual history when identity is reliable
       -> alert acknowledgement and audit trail
  -> optional M5Stack StopWatch wall display (summary/status only)
```

Inference may run on the Pi, the desktop, or both. Benchmarking decides; it is
not an architectural article of faith. MQTT, WebSocket, HTTP, and video codec
choices remain open.

## Delivery sequence

1. **Read-only target inventory.** Record the installed Pi 5 BSP, Screen,
   Sensor Framework, camera configuration, OpenCV, and TensorFlow Lite state.
   Do not reflash or change startup files as part of ordinary bring-up.
2. **Camera proof.** Inventory the Camera Module 3 variant and cable, enumerate
   it through Sensor Framework/camapi, capture frames, and measure format,
   resolution, FPS, autofocus behavior, reboot recovery, and 24-hour stability.
3. **AICA compatibility spike.** Cross-build the unmodified QNX AI Camera App
   with QNX SDP 8.0 on a supported host; upstream says its instructions were
   tested on Ubuntu 20.04/22.04, so do not assume this Mac or the QNX target is
   a supported build host. Run the bundled face/style demo only to prove
   compatibility, then replace it with poultry logic. Do not enable root SSH
   to follow the sample.
4. **Headless capture service.** Reuse/fork AICA's QSF and TensorFlow Lite
   integration while removing its Screen/render/touch dependency from the
   production path. Run under a consistent non-root service model.
5. **Desktop stream and UI.** Benchmark raw bandwidth, downscaling, and encoder
   cost before choosing a timestamped camera transport. QSTI documents only
   uncompressed recording/playback on its stock camera path, not H.264/H.265,
   so demonstrate any required compressed path. Authenticate and encrypt the
   link, provision and rotate device keys outside the repository, and make
   acknowledgements replay-resistant. Show live/recorded feeds, explicit
   stream freshness, bounded local buffering, evidence clips, alerts, history,
   acknowledgement, and audit records.
6. **Flock baseline.** Mount one camera over one representative pen with
   controlled lighting. Build activity and zone-distribution baselines before
   individual identity or disease-related work.
7. **Identity pilot.** Test welfare-reviewed ArUco backpacks on a small flock.
   Measure visible-time identity coverage, unknown-ID time, marker retention,
   occlusion, cleaning, growth/fit, pecking, and handling burden.
8. **Dropping events.** Detect new deposits, then classify visible appearance
   as normal/abnormal for review. Attribute to a bird only with strong temporal
   and spatial evidence; `unattributed` is a valid result.
9. **Optional wall display.** Add the M5Stack StopWatch after the authoritative
   desktop/event path works. It shows state, alert count, affected bird/zone,
   age, confidence/persistence, acknowledgement, and connectivity.

Disease-specific associations are future offline research requiring
veterinary sampling, laboratory reference labels, independent prospective
validation, and a separately defined intended use. They are not an MVP output.

## Evaluation gates

- Split data by the strongest independent acquisition unit available (bird,
  flock, farm, date, or session), and keep near-duplicate video frames together.
- Measure capture uptime, stream latency/freshness, identity coverage,
  unknown-ID rate, new-dropping event recall/precision, attribution coverage,
  false alerts per pen-day, missed incidents, and operator follow-through.
- Treat literature accuracy as study context, never as expected field
  performance.
- Preserve an evidence clip and reason for every alert.

## Hardware boundaries

- Compute: one headless Raspberry Pi 5 running QNX 8.0.0.
- Camera: Raspberry Pi Camera Module 3; exact standard/wide and IR-cut/NoIR
  variant, count, mount geometry, lighting, and enclosure remain to inventory.
- Primary UI: desktop application over reliable high-bandwidth Wi-Fi.
- Optional UI: M5Stack StopWatch C152 wall client, powered continuously over
  protected USB-C; it does not run QNX or this camera pipeline.
- MVP uses one Pi. Add cameras or compute nodes only if measured coverage or
  performance requires them.

## Safety and operating boundaries

- The camera reports observable anomalies, not diagnoses.
- Suspected high-consequence or reportable disease is escalated promptly to a
  veterinarian or animal-health authority. Their guidance controls isolation,
  biosecurity, testing, treatment, and reporting.
- Never enable root SSH merely to follow AICA's sample instructions.
- Do not modify `/boot/onboot` or the Railway reverse tunnel unless explicitly
  asked to perform connectivity maintenance.
- Exact target facts and connection commands are in [../TARGET.md](../TARGET.md).
