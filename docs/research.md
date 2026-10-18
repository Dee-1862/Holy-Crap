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

## Additional implementation survey

### Camera access on QNX (2026-10-17)
- Frames come from the **QNX Sensor Framework (QSF) camera C API** (`sf.camapi`). There is no Python binding for it on oss.qnx.com, so capture code must be C/C++.
- Reference app: QNX "AI Camera App", C++, QSF camera intake → TFLite face detection, uses OpenCV. Recommended platform is Pi 4 + Quick Start Image; tested with Camera Module 3. Camera must be enabled in `/system/etc/post_startup.sh`. https://gitlab.com/qnx/projects/ai-camera-app
- Simpler camera samples: https://gitlab.com/qnx/sample-apps/camera_example1_callback (also example2_events, example3_viewfinder).
- **Pi 5**: oss.qnx.com has Pi 5 sensor-framework packages (`qnx-sf-hw-rpi5`, `qnx-sf-platform-broadcom-rpi5`, `qnx-sensor-framework-example-config-rpi5`, 8.0.4/8.0.5), and a QNX 8.0 BSP for Pi 5 exists (https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_sdp80.bsp.broadcom.rpi5.bcm2712.html). Camera Module 3 on Pi 5 with QNX is **not yet confirmed working**; the QSTI wiki camera page returned 404. Pi 5 needs the 22-pin camera cable (included with standard CM3, not with the wide-angle version).

## Datasets (2026-10-17)
- **Kaggle "Chicken Disease Image Classification"** (allandclive/chicken-disease-1): re-upload of the Tanzania dataset (Arusha/Kilimanjaro, Sept 2020–Feb 2021, phone photos via ODK). Classes: Coccidiosis, Healthy, New Castle Disease, Salmonella. Resized to 224×224. **Classification labels only, no boxes.** Kaggle license: "Unknown". ~294 MB. https://www.kaggle.com/datasets/allandclive/chicken-disease-1
- Original source (Machuve et al.): Zenodo https://doi.org/10.5281/zenodo.4628934 (2021) and PCR-annotated version https://doi.org/10.5281/zenodo.5801834. ~6,812 field photos + 1,255 lab (PCR) labelled. Paper: https://frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2022.733345 . License still to be checked on the Zenodo page.
- **Roboflow "chicken-droppings-analysis"**: object detection, ~15.6k images, reportedly CC BY 4.0, classes healthy/cocci/NCD/salmonella-like. Candidate source of **bounding boxes** for the detector. Unverified: provenance (likely the same Tanzania images re-labelled), label quality. https://universe.roboflow.com/thesis-pr4oh/chicken-droppings-analysis
- Roboflow "dropping-classification": ~12.5k images, healthy/avian_influenza/coccidiosis (different class set). https://universe.roboflow.com/yolo-poultry-dropping/dropping-classification
- Domain gap: all of these are close-up phone photos of single droppings, not a wide barn-floor view.

- **No evidence** QNX runs on ESP32. Other RTOSes (Zephyr, NuttX, FreeRTOS via ESP-IDF) do. https://www.espressif.com/en/media_overview/news/support-new-operating-systems-esp32-series-socs

## M5Stack StopWatch (C152 dev kit), per CNX Software / Mouser
- ESP32-S3R8, dual-core 240 MHz, 8MB PSRAM, 16MB flash, Wi-Fi 4, BLE 5
- 1.75" round AMOLED touch, 466x466; 2 buttons; vibration motor; 1W speaker; MEMS mic; IMU; RTC; Grove + GPIO; 450 mAh battery, USB-C
- No camera listed. Role here: alert display / farmer wearable.
- https://www.cnx-software.com/2026/05/22/m5stack-stopwatch-esp32-s3-devkit-offers-1-75-inch-touch-amoled-microphone-speaker-and-gpio-expansion/
- Sources are secondary (not the M5Stack page itself).

## Update 2026-10-17: literature and datasets (web search; verify against originals)
**Correction:** the original write-up's claim that University of Georgia builds droppings classifiers was not supported. UGA (Chai / Lu labs) work found is a YOLOv8 robot-dog system for dead chickens and floor eggs (YOLOv8m ~91% precision). A UGA group is reported to have used the Tanzanian data for a screening tool (unconfirmed). Droppings work found elsewhere: Tanzania (Machuve), Lithuania (Nakrosis), Nigeria, China.

Papers (details in paper-plan.md section 1):
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9376463/ (Machuve 2022)
- https://doi.org/10.3390/agriengineering7090278 (YOLO11 + EfficientNet-B0)
- https://onlinelibrary.wiley.com/doi/10.1155/js/1433795 (ESP32-CAM IoT, 2026)
- https://www.sciencedirect.com/science/article/pii/S2772375523000515 (smartphone, YOLOv3 + ResNet50)
- https://dl.acm.org/doi/10.1145/3723178.3723198 and https://dl.acm.org/doi/10.1145/3723178.3723288 (Kaggle-data ensembles)
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10571708/ (Nakrosis 2023, Lithuania, six classes)
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC10477973/ (Nigeria dataset)
- https://arxiv.org/html/2507.10056v1 (chicken disease paper surfaced by search; not yet read)

Datasets: Kaggle allandclive/chicken-disease-1 (page not opened; counts vary 6.8k-8k by source); Tanzania set; Nigeria set (14.6k cleaned); China set (10.5k). Kaggle copies are likely not independent of the Tanzania data.

QNX ML runtimes (superseded by the AI Camera App section below): TFLite and OpenCV QNX ports exist; no ONNX Runtime port confirmed. Target board is Pi 5 (confirmed by user).

Edge speed anchors (not comparable to each other): YOLOv8n about 3 FPS on Pi 4 with ncnn (Qengineering); Brazilian ONNX Runtime CPU comparison of tiny YOLOs and SSDLite on Jetson Nano vs Pi 4B (https://sol.sbc.org.br/index.php/wiarc/article/view/42894).

Reading status: none of the papers above has been read in full yet.

## Kaggle dataset verified by user (page pasted 2026-10-17)
allandclive/chicken-disease-1: 8,067 images, 4 classes, 224x224, Arusha/Kilimanjaro Tanzania, Sep 2020 - Feb 2021, ODK phone app, license Unknown, v1 294 MB, ~9k downloads. Counts and the 6,812 farm + 1,255 lab composition match Machuve et al. 2022, so it is that dataset re-hosted (not independent). Filenames carry source hints (`pcr*` prefix = likely lab-confirmed).

## QNX AI Camera App (read 2026-10-17; cloned and read README + source layout)
https://gitlab.com/qnx/projects/ai-camera-app (Apache-2.0; created Apr 2025, last commit Oct 2025 "Fixed link in readme").
- Sample showing video frames from QSF (QNX Sensor Framework) camera APIs processed with TensorFlow Lite and displayed (OpenGL shaders). Default mode: face detection (ModelExecutor / TFLiteExecutor / QSFCameraIntake classes); also style-transfer models fetched from Kaggle.
- Requires QNX SDP 8.0 with packages sf.camapi, sf.base, mm.aoi, mm.mmf.core, screen.img_codecs; builds on Ubuntu 20.04/22.04 with `make` after `source ~/qnx800/qnxsdp-env.sh`.
- Needs TFLite and OpenCV built from QNX ports: https://github.com/qnx-ports/build-files (ports/tensorflow, ports/opencv). Libraries and binary are copied to the target with scp.
- README: recommended platform Raspberry Pi 4 B with Quick Start Image; **tested cameras include Raspberry Pi Camera Module 3**; accepted frame types YUYV, BGR8888, CBYCRY. Camera needs sensor config in /system/etc/post_startup.sh (see QSI wiki Next steps > Camera).
- Interpreter calls: AllocateTensors, SetNumThreads(-1), Invoke (no explicit delegate seen; XNNPACK library is copied, so TFLite may use it by default; unverified).
- Not stated: Pi 5 support, latency numbers. Our target is a Pi 5 on QNX 8.0.0, so the sample must be verified there.
- Implication: ML runtime on QNX is no longer an open risk; the plan uses TFLite (supersedes the earlier "no confirmed port" note).

## Prior work on attribution and zone monitoring (from user-pasted summary, 2026-10-17; abstract-level, unverified by us)
- **Caged hens (solved at cage level):** a 2024 study puts a camera over the manure belt under stacked cages; YOLOv5 flags abnormal manure and a second model tracks belt movement to map manure to its cage; 91.6% correct cage tracing over 48 field tests. Another study measures manure quantity per cage as a death indicator but used only 2-3 birds.
- **Open floors, individual birds:** UGA/Cobb broiler study (YOLO11x) found overlap, look-alike birds and feeders as the main failures. Wageningen printed ID markers on hens and identified each bird only 37% of the time. Chicken re-ID dataset reaches 95-100% only with several images per bird. RFID leg bands/smart nest boxes log feeder/nest visits, not droppings. Nobody found has tied individual birds to droppings.
- **Zone monitoring:** a 2023 study uses a pan-tilt camera about 3.5 m up that sweeps the floor every few minutes. UGA has a machine-vision method for disease from manure images (https://site.caes.uga.edu/precisionpoultry/2025/09/a-machine-vision-method-for-poultry-disease-detection-based-on-manure-images/). Carus Lab "Chicken Boy" is a rail-mounted robot rating dropping color; the vendor claims 2-3 days earlier prediction (unverified). Open-house slat-floor study: new droppings are hard to tell from a dirty floor.

## Other-session findings now merged (2026-10-17; reported, not rechecked by us)
- Zenodo Machuve records (https://doi.org/10.5281/zenodo.4628934 farm, https://doi.org/10.5281/zenodo.5801834 PCR) reported as **CC BY 4.0**, full-resolution photos plus official YOLO boxes (`imgObjDet_Yolo.zip`; 9,090 boxes). This resolves the earlier "license unknown" and "224 px only" concerns for the Zenodo copy (the Kaggle copy is still 224 px with unknown license). Credit required.
- oss.qnx.com: prebuilt packages target QNX 8.0.3-8.0.5; source ports (tensorflow 2.16.1, opencv 4.9, mosquitto, XNNPACK, ComputeLibrary) target 8.0.0. Details in vision-plan.md.
- Hackathon context: LA Hacks QNX track (needs an oss.qnx.com AI module) and Veri track (train an open-source model on Veri); see vision-plan.md.
- The research branch adds the knowledge base (`BIBLE.md` and linked notes),
  advisory-only product framing, no disease-name outputs, a desktop primary
  UI, and staged validation gates.
