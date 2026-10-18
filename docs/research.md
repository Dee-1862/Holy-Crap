# Research Notes

## Research log / front door

The knowledge base lives under [docs/research/](research/README.md), with the central
synthesis in [research/PAPER.md](research/PAPER.md). Start there.

- [research/PAPER.md](research/PAPER.md): product conclusion, MVP sequence, risks, gaps.
- [research/](research/README.md): evidence/subject nodes (datasets, observables, identity,
  systems, evidence, practice).
- [00-landscape-review.md](00-landscape-review.md): narrative + comparison table.
- [01-key-findings.md](01-key-findings.md): numbered findings with confidence notes.
- [02-bibliography.md](02-bibliography.md): sources with `[read]`/`[skimmed]`/`[found]` status.
- [03-open-questions.md](03-open-questions.md): prioritized questions + answered/settled list.
- [BIBLE.md](BIBLE.md): single source of truth for scope, hardware, decisions, unknowns.

Status of the original claims from the idea write-up: the Machuve dataset is real and now
documented with its label-quality caveats (see
[research/datasets/machuve-fecal-datasets.md](research/datasets/machuve-fecal-datasets.md));
UGA machine-vision work exists in the sources, but only as tracking/dye-marking studies -
the specific "UGA works on machine vision for abnormal droppings" claim remains unverified
(see
[research/identity/rfid-and-markerless-tracking.md](research/identity/rfid-and-markerless-tracking.md)
and [02-bibliography.md](02-bibliography.md)); the disease-appearance table below remains
*(unverified)* and is now annotated against veterinary literature in
[research/evidence/clinical-limits-of-visual-diagnosis.md](research/evidence/clinical-limits-of-visual-diagnosis.md).
The rabies row was removed from the target list: rabies is a disease of mammals
([WOAH](https://www.woah.org/en/disease/rabies/), `[read]`), not a chicken-camera target.

## Source of the idea (user's pasted write-up)

Claims, all *(unverified)* until checked against the bibliography:

- Automated fecal scoring is a validated computer-vision application; University of Georgia
  researchers work on machine vision for abnormal droppings.
- An "AI4D Poultry Dataset" with thousands of annotated fecal images exists. *(Still unverified
  as stated; the closest documented dataset is the 4-class Tanzania collection, Machuve et al.: see
  [research/datasets/machuve-fecal-datasets.md](research/datasets/machuve-fecal-datasets.md).)*
- Two-stage pipeline: YOLOv8 localisation, then MobileNetV2/ViT classification. *(Model
  prescriptivism dropped; families named at a high level only: see
  [01-key-findings.md](01-key-findings.md) #12.)*
- Edge deployment on a robot or trolley (Jetson or QNX ARM board). *(Target is now fixed:
  headless Raspberry Pi 5 on QNX 8.0.0: see [TARGET.md](../TARGET.md) and [BIBLE.md](BIBLE.md).)*

### Historical disease/appearance table removed

The original idea associated dropping colors and textures with named diseases.
That mapping is not sufficiently supported for product use and has been
removed to avoid implying visual diagnosis. The reviewed evidence supports
appearance-based labels such as normal-looking, abnormal color, abnormal
shape, and abnormal water content. See
[research/evidence/clinical-limits-of-visual-diagnosis.md](research/evidence/clinical-limits-of-visual-diagnosis.md).

The earlier implementation survey and hackathon-oriented data/model/runtime
recommendations are preserved in [vision-plan.md](vision-plan.md). The
evidence-backed conclusions on attribution, datasets, and commercial systems
have been reconciled into the linked research notes above rather than repeated
here.

## QNX, camera, and application findings (2026-10-17)

- **Verified physical target:** Raspberry Pi 5, `aarch64le`, running QNX
  8.0.0. Connection and non-root runner details are in [../TARGET.md](../TARGET.md).
- **Official platform context:** QNX publishes a 64-bit QNX 8 BSP for Pi 5 /
  BCM2712, currently classified as experimental software. That is suitable for
  this prototype, not a production-support guarantee
  ([release notes](https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_sdp80.bsp.broadcom.rpi5.bcm2712.html)).
- **Selected camera:** Raspberry Pi Camera Module 3. QNX's QSTI documentation
  lists it on Pi 5 as camera ID 3 (camera 1) and ID 4 (camera 2)
  ([camera guide](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/next-steps.html)).
- **Selected application foundation:** QNX
  [AI Camera App](https://gitlab.com/qnx/projects/ai-camera-app), an Apache-2.0
  sample using Sensor Framework/camapi, OpenCV, TensorFlow Lite, and QNX
  Screen. It lists Camera Module 3 as tested but recommends Pi 4; Pi 5 + Camera
  Module 3 + AICA remains a bring-up test, not an established fact.
- **Headless gap:** stock AICA creates a Screen/EGL/GLES window and listens for
  mouse/touch input. The production path needs a no-window capture/inference
  service. Do not enable root SSH just to follow the sample's deployment steps.
- **Documented, not verified on this target:** AICA references Linux-host SDP
  cross-build recipes for OpenCV and TensorFlow Lite. Use those recipes for
  the isolated AICA compatibility test. Native APK packaging is a separate
  Pi-side `abuild` workflow and is not configured yet. The availability of
  matching OpenCV, TensorFlow, or TensorFlow Lite APKs in the configured
  repositories has not been checked. ONNX Runtime and hardware acceleration
  remain unknown.
- QNX's Pi 5 QSTI guide uses `/etc/config/sensor/sensor_rpi5.conf`, with
  related files under `/etc/config/sensor/rpi5`. Camera Module 3 uses
  `SENSOR_UNIT_3` for camera 1 and `SENSOR_UNIT_4` for camera 2, followed by a
  Sensor Framework restart with the Pi 5 configuration. The installed target
  state is still unknown
  ([camera guide](https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/next-steps.html)).

## M5Stack StopWatch C152

- **Role:** optional barn-wall status and alert client. The desktop application
  is primary; the StopWatch is not a vision node or source of truth.
- **Official specifications:** ESP32-S3R8 at 240 MHz, 16 MB flash, 8 MB PSRAM,
  2.4 GHz Wi-Fi, 1.75-inch 466×466 round AMOLED touch display, buttons,
  vibration, audio, IMU, RTC, 450 mAh battery, USB-C 5 V, and rear magnetic
  attachment
  ([M5Stack documentation](https://docs.m5stack.com/en/core/StopWatch)).
- **Wall deployment:** propose protected continuous USB-C power. Treat the
  battery as a short buffer until measured; test auto-restart, reconnect,
  screen visibility/image retention, enclosure, dust, and moisture.
- **Revision warning:** on some v1.0 units a pin labeled `BAT` is actually
  5 V input. Never connect a lithium battery to that pin. On v1.0.1 the
  `*BAT` pin is an actual battery connection. Inventory every unit first.
