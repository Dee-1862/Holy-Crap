# Open questions

Each question states why it matters, how to answer it, and what decision the
answer unlocks. Synthesis: [research/PAPER.md](research/PAPER.md). Source of
truth: [BIBLE.md](BIBLE.md).

## P1: blocking bring-up

1. **Which Camera Module 3 units do we have?**
   Why: standard versus wide and IR-cut versus NoIR change coverage, color,
   lighting, and pixels per bird. Camera count and cable length affect the
   mount.
   Method: inventory the exact module variants and count; verify the required
   22-to-15-pin camera cables; record pen dimensions, camera height, lighting,
   cable route, dry enclosure/optical-window plan, and pixels per smallest
   bird/dropping target. Validate the calculated footprint with captured frames
   before choosing standard versus wide.
   Unlocks: mount geometry, coverage, floor resolution, and day/night strategy.

2. **What is installed and working on the physical QNX Pi 5?**
   Why: official documentation does not establish the state of this image.
   Method: after SSH reachability is confirmed, inventory the BSP/SDP, Screen,
   Sensor Framework, camera configuration, OpenCV, TensorFlow Lite, `io-sock`,
   physical interface state, and onboard Wi-Fi driver/firmware/association
   read-only. Do not reflash, rebuild the BSP, or modify startup files during
   discovery. The current `qnxpi`/Railway path does not prove WLAN support.
   Unlocks: the shortest safe bring-up path.

3. **Can Sensor Framework capture stable Camera Module 3 frames on Pi 5?**
   Why: AICA recommends Pi 4, even though QNX documentation lists Camera
   Module 3 on Pi 5.
   Method: enumerate via camapi, record camera index, frame formats,
   resolution/FPS, autofocus or focus-lock behavior, reboot recovery, and a
   long-run capture test.
   Unlocks: whether AICA is a viable foundation and the usable input budget.

4. **Can AICA be adapted safely to the headless non-root target?**
   Why: stock AICA requires QNX Screen/EGL/GLES and a touch/mouse path, and its
   README describes root deployment. QNX documents a mixed-user Screen/drm
   crash risk on Pi 5.
   Method: first inventory Screen/drm ownership. Test the stock sample only as
   a compatibility spike, then separate QSF capture/inference from Render and
   Screenlistener under a consistent non-root service user. Never enable root
   SSH merely to follow the sample.
   Unlocks: capture-service design and dependency list.

5. **What video transport and inference placement work best?**
   Why: reliable, high-bandwidth Wi-Fi and a desktop primary UI are working
   assumptions, but codec, latency, buffering, security, and compute placement
   are open. QSTI documents uncompressed recording/playback only on its stock
   camera path, not H.264/H.265.
   Method: benchmark representative capture resolutions, raw bandwidth,
   downscaling, and encoder cost with inference on the Pi, desktop, and a split
   pipeline. Measure bandwidth, latency, dropped frames, CPU/RAM, Pi
   temperature/throttling, and 24-hour stability. Require authentication,
   encryption, device-key provisioning and rotation, replay-resistant
   acknowledgements, bounded local buffering, and no credentials in the repo.
   Survey and load-test at the actual camera/AP/desktop positions during normal
   work and equipment use. Measure sustained and low-percentile throughput,
   packet loss, RTT/jitter, reconnects, and outage duration. Define preview
   drop/backfill and local-retention policy; prioritize alert/status traffic.
   If headroom is insufficient, use wired Ethernet or local inference and
   recording. Never silently present stale video.
   Unlocks: stream protocol/codec and the Pi-versus-desktop model boundary.

6. **What are the Machuve dataset reuse terms?**
   Why: the Zenodo records display no explicit license.
   Method: obtain written clarification or an explicit license from the
   authors/record. Until then, do not assume permission to redistribute,
   modify, or use the data in a product.
   Unlocks: research-only versus product use and redistribution.

## P2: product-defining experiments

7. **Can flock activity and zone metrics produce useful alerts?**
   Why: this is the earliest evidence-backed product layer.
   Method: establish age/time-specific baselines in one representative pen;
   evaluate false alerts per pen-day, missed events, alert persistence, and
   operator follow-through.
   Unlocks: the first deployable alert workflow.

8. **Will ArUco backpacks pass welfare review and maintain useful identity?**
   Why: per-bird history and any bird-dropping association depend on identity.
   Method: small-flock welfare-reviewed pilot; measure visible-time identity,
   unknown-ID rate, fit, feather/manure occlusion, loss, cleaning, growth,
   pecking, and handling burden.
   Unlocks: markers versus RFID, multi-camera, or markerless fallback.

9. **Can newly deposited droppings be detected on occupied litter?**
   Why: static droppings segmentation does not prove temporal event detection.
   Method: annotate deposition events in mounted-camera video and test temporal
   change plus segmentation across separate sessions.
   Unlocks: whether the droppings layer ships at all.

10. **Can a detected dropping be attributed to a bird with useful precision?**
    Why: Big Broiler labels defecation actions on short tracklets but not the
    resulting deposit or persistent bird identity. No result found in this pass
    demonstrates end-to-end attribution in a crowded, free-moving floor pen.
    Method: look backward through confident ArUco tracks at each deposition;
    require spatial footprint plus a visible event cue; measure correct,
    incorrect, and unattributed outcomes separately.
    Unlocks: bird-level versus zone-only claims.

11. **Can humans agree on normal versus abnormal appearance?**
    Why: age, feed, environment, and collection context affect appearance, and
    inconsistent labels cap the model's value.
    Method: define a veterinary-reviewed appearance ontology; measure inter-
    annotator agreement before model training; preserve flock context.
    Unlocks: label set, thresholds, and whether appearance triage is viable.

## P3: interfaces and field operation

12. **Who buys, operates, owns, and benefits from the system?**
    Why: producer evidence shows that a contract grower is often not the sole
    technology decision-maker. Literature does not supply a universal poultry
    false-alert budget or credible dollar willingness-to-pay estimate.
    Method: interview growers and integrator/live-production managers. Ask who
    approves, pays, owns raw and derived data, services hardware under
    biosecurity rules, receives alerts, and benefits financially. Test evidence
    clips, priority tiers, acknowledgement, history, export, and alert load with
    real events; set the false-alert budget with pilot operators, not literature.
    Unlocks: buyer map, data rights, dashboard information architecture,
    maintenance model, ROI measurement, and false-alert budget.

13. **What exact escalation language is required?**
    Why: duties for suspected Newcastle disease or avian influenza vary by
    jurisdiction and pathogen/pathotype.
    Method: review the pilot jurisdiction with a veterinarian or authority;
    encode prompt escalation without camera-issued diagnoses.
    Unlocks: safe alert copy and incident workflow.

14. **Is the optional StopWatch practical as a wall client?**
    Why: its role is useful but non-blocking, and the official page publishes
    no IP rating or operating-temperature range.
    Method: inventory v1.0/v1.0.1 revision; use protected USB-C power; test
    2.4 GHz Wi-Fi reconnect, auto-restart, stream/event staleness, AMOLED image
    retention, visibility, acknowledgement, enclosure, and update strategy.
    Unlocks: whether and where it is deployed.

15. **What are the project deadline and pilot-site constraints?**
    Why: pen size, camera height, lighting, barn workflow, and schedule decide
    which stages fit.
    Method: site survey and project-timeline decision.
    Unlocks: concrete milestone plan.

## Answered / settled

- Compute: one headless Raspberry Pi 5 running QNX 8.0.0.
- Camera model: Raspberry Pi Camera Module 3; exact variant/count remain open.
- Camera software foundation: QNX AI Camera App, used as a reference/fork base
  rather than a ready headless service.
- Mount concept: fixed overhead, not a moving trolley.
- Connectivity: reliable, high-bandwidth Wi-Fi is a working assumption, not a
  settled fact. The physical WLAN path and a viable compressed/downsampled
  transport remain to be demonstrated; the desktop remains the intended
  primary UI.
- Inference location: benchmark-driven; Pi, desktop, or split remain viable.
- M5Stack StopWatch: optional wall status/alert client, not a hard constraint.
- Diagnosis: no camera-issued disease diagnosis or automatic culling.
- Attribution: never guaranteed; `unattributed` is a first-class result.
- Rabies: not a poultry-camera target; it is a mammalian disease.
