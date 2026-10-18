# Game plan

This plan implements the current decisions in [BIBLE.md](BIBLE.md). The bible
controls if the two files ever diverge.

## Goal

Build a fixed, overhead poultry-monitoring system that turns camera footage
into explainable flock, group, zone, and dropping anomalies for human review.
It does not diagnose disease, prescribe treatment, or make culling decisions.

## Working architecture

```text
Raspberry Pi Camera Module 3
  -> Raspberry Pi 5 running QNX 8
  -> QNX Sensor Framework capture based on ai-camera-app
  -> reliable high-bandwidth Wi-Fi (working assumption)
  -> desktop application (primary UI and authoritative review workflow)
       -> live/recorded video and evidence clips
       -> flock/group/zone metrics and group history
       -> alert acknowledgement and audit trail
  -> optional M5Stack StopWatch wall display (summary/status only)
```

Inference may run on the Pi, the desktop, or both. Benchmarking decides; it is
not an architectural article of faith. MQTT, WebSocket, HTTP, and video codec
choices remain open.

## Unit of tracking: the group

The core product does not identify individual birds. A group is a physically
separated pen, section, or cage with a known head count. Each fixed camera view
or region of interest maps detections to one `group_id`; alerts are normalized
by group size and require persistence or a minimum event count. Small groups
improve attribution, while large groups produce faster signals but weaker
localization. Use farm-defined groups and welfare rules; never reshuffle birds
for the monitoring system. See [vision-design-v2.md](vision-design-v2.md) for
the group-first event design. Individual identity remains optional research,
not an MVP dependency.

## Vision prototype note

The time-boxed data, model, and runtime assessment is in
[vision-plan.md](vision-plan.md). It recommends a small four-class detector as
the first training experiment, but no QNX inference runtime is final until it
is proven on this exact QNX 8.0.0 target. The broader product sequence below
remains authoritative.

## Delivery sequence

1. **Read-only target inventory.** Record the installed Pi 5 BSP, Screen,
   Sensor Framework, camera configuration, OpenCV, TensorFlow Lite, physical
   interface, `io-sock`, and onboard Wi-Fi driver/firmware/association state.
   Do not reflash, rebuild the BSP, or change startup files during discovery.
2. **Camera proof.** Inventory the Camera Module 3 variant and cable, enumerate
   it through Sensor Framework/camapi, capture frames, and measure format,
   stride, resolution, FPS, autofocus behavior, reboot recovery, and 24-hour
   stability. Record the mount height and pen dimensions; calculate and then
   verify the footprint and pixels per smallest bird/dropping target before
   choosing standard versus wide.
3. **AICA compatibility spike.** Cross-build the unmodified QNX AI Camera App
   on x86-64 Ubuntu 22.04 with the QNX SDP baseline and QNX package versions
   matched to the target. Ubuntu 22.04 is the overlap between AICA's tested
   hosts and the [current SDP 8.0.5 host list](https://www.qnx.com/developers/docs/relnotes8.0/com.qnx.doc.release_notes/topic/8.0.5_prod_release_notes/8.0.5_rn.html);
   AICA also reports Ubuntu 20.04,
   but the current SDP no longer supports it. Pin AICA and the referenced
   `qnx-ports/build-files`, OpenCV, TensorFlow, numpy, and muslflt revisions.
   Keep the cross-built libraries in an isolated application directory. Run
   the bundled face/style demo only to prove compatibility, then replace it
   with poultry logic. Do not enable root SSH to follow the sample.
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
   acknowledgement, and audit records. Run the load test at the actual
   camera/AP/desktop positions during normal barn work and equipment use;
   measure throughput, loss, RTT/jitter, reconnects, and outages. Prioritize
   alert/status traffic over preview, define drop/backfill and local-retention
   policies, and fall back to wired Ethernet or local inference/recording if
   the Wi-Fi path has insufficient headroom.
6. **Flock baseline.** Mount one camera over one representative group with
   controlled lighting. Build activity and zone-distribution baselines before
   disease-related work.
7. **Group mapping.** Define fixed regions of interest for each pen, section,
   or cage. Measure group-assignment coverage, boundary ambiguity, occupancy,
   and the effect of occlusion and equipment on region confidence.
8. **Dropping events.** Detect new deposits, then classify visible appearance
   as normal/abnormal for review. Attribute each event to a group only when the
   region mapping is reliable; `unattributed` is a valid result.
9. **Optional wall display.** Add the M5Stack StopWatch after the authoritative
   desktop/event path works. It shows state, alert count, affected group/zone,
   age, confidence/persistence, acknowledgement, and connectivity. It receives
   low-rate versioned summaries, never video; offline acknowledgement stays
   pending until the desktop accepts it.

Native APK packaging is a separate decision, not part of the AICA compatibility
spike. If the production service later uses native-a packages, configure an
aports checkout, packager identity, signing key, and local package repository
under writable `/data`, then build the dependency chain on the Pi with
`abuild`. Do not combine cross-built AICA libraries with APK-owned copies of
the same dependencies.

Disease-specific associations are future offline research requiring
veterinary sampling, laboratory reference labels, independent prospective
validation, and a separately defined intended use. They are not an MVP output.

## Evaluation gates

- Split data by the strongest independent acquisition unit available (bird,
  flock, farm, date, or session), and keep near-duplicate video frames together.
- Measure capture uptime, stream latency/freshness, group-assignment coverage,
  unknown-group rate, new-dropping event recall/precision, attribution
  coverage, false alerts per group-day, missed incidents, and operator
  follow-through.
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
