# Research Notes

Honest status: **no research papers have been read yet.** Everything marked *(unverified)* came from the idea write-up or memory and must be checked before it's cited anywhere.

## Source of the idea (user's pasted write-up)
Claims, all *(unverified)*:
- Automated fecal scoring is a validated computer-vision application; University of Georgia researchers work on machine vision for abnormal droppings.
- An "AI4D Poultry Dataset" with thousands of annotated fecal images exists. *(Likely the 4-class Tanzania dataset, Machuve et al., 2022, ~14k images: cocci / healthy / NCD / salmonella. From memory; find the actual paper and license.)*
- Two-stage pipeline: YOLOv8 localisation, then MobileNetV2/ViT classification.
- Edge deployment on a robot or trolley (Jetson or QNX ARM board).

### Disease/appearance table (from the write-up, *unverified*)
| Class | Appearance |
|---|---|
| Healthy | firm, brown, white urate cap |
| Coccidiosis | blood-streaked, mucousy, dark brown or watery |
| Salmonella | yellowish, foamy, diarrhea |
| Newcastle (NCD) | bright green, watery |

Caveat: green/yellow/dark droppings also occur from diet, bile, and normal cecal droppings. Needs veterinary-literature backing.

## Prior work: attributing droppings to individual birds (web search 2026-10-17; abstracts and snippets only, papers not read)
- **No end-to-end system found for floor-raised flocks** that links a dropping to a specific hen.
- **Caged layers, solved at cage level:** YOLOv5 flags abnormal manure on the manure belt, and SuperPoint-SuperGlue estimates belt motion to trace it back to the cage. Reported 91.6% correct cage tracing over 48 field tests, about 95% detector precision/recall. https://www.sciencedirect.com/science/article/abs/pii/S0168169924003909
- Per-cage fecal volume on the manure belt as a mortality signal (3D camera, only 2–3 birds per trial): https://www.sciencedirect.com/science/article/pii/S277237552600701X
- **Individual tracking in floor flocks is still early research:**
  - UGA/Cobb tracked broilers in 48 pens with YOLO11x plus re-ID. Problems: occlusion, look-alike birds, feeders and drinker lines blocking the view. https://www.cobbgenetics.com/assets/Uploads/Li-et-al-v2.-Enhancing-Consistency-and-Efficiency-of-Tracking-Multiple-Individual-Broiler-Chickens-in-Group-Settings_RFS.pdf
  - Wageningen used ArUco markers on hens and detected each individual only 37% of the observation time; identity switches cause misassignment. https://www.wur.nl/en/news/pixels-breeding-values-can-cameras-help-breed-better-hens
  - Chicken re-ID dataset: 95–100% accuracy when multiple images per bird are available. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11718998/
  - RFID leg bands track visits to feeders and nests, not droppings: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12355069/ and smart nest box https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5877303/
- **Zone/flock-level dropping monitoring (what we are building) has precedent:**
  - Pan-tilt-zoom camera about 3.5 m up, scanning the litter in a zigzag every few minutes to detect abnormal droppings early: https://doi.org/10.3390/ani13193041
  - UGA precision-poultry machine-vision method for disease from manure images. This partly confirms the original write-up's UGA claim. https://site.caes.uga.edu/precisionpoultry/2025/09/a-machine-vision-method-for-poultry-disease-detection-based-on-manure-images/
  - Open-house farms with slatted floors: new droppings are hard to tell apart from a dirty floor. https://www.researchgate.net/publication/392852662
  - Commercial lead (vendor claim, unverified): Carus Lab "Chicken Boy", a rail robot that rates dropping colour, claiming disease prediction 2–3 days earlier. https://www.caruslab.com/blog-details/early-poultry-disease-detection-precision-farming-tech
  - Patent: robot surveillance that detects chickens, equipment and droppings. https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11019805

## TODO reading list
- [ ] Machuve et al. poultry disease fecal dataset paper + dataset license
- [ ] UGA machine-vision poultry papers (find actual titles)
- [ ] YOLO small-object detection on cluttered floors
- [ ] Domain shift / augmentation for barn imagery
- [ ] Veterinary reference on fecal color vs disease

## QNX findings (web search, 2026-10-17)
- **Verified target (2026-10-17)**: the actual device is a Raspberry Pi 5 running QNX 8.0.0 (`aarch64le`). See TARGET.md for the recorded target facts and connection procedure.
- **Pi 4 background research only** (kept for reference, not evidence of Pi 5 support):
  - Pi 4 (BCM2711) BSP for QNX SDP 8.0 exists; release notes dated Jan 2026 (build 484).
    https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_sdp80.bsp.broadcom.rpi4.bcm2711.html
  - Quick Start Target Image (QSTI) for Raspberry Pi includes a camera demo; recommended if you need camera functionality.
    https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/intro.html
  - Refreshed QSTI adds Raspberry Pi Camera Module 3 support and multi-camera configuration.
    https://qnx.software/en/blog/2026/refreshed-qnx-quick-start
  - Custom image build repo for Pi 4 on QNX 8.0: https://devblog.qnx.com/refreshed-quick-start-custom-image-builds-and-more-samples
- Resources hub: https://oss.qnx.com/
- **Not confirmed**: whether the camera works on the Pi 5 under QNX. Runtime availability: see the package survey below.

## oss.qnx.com package survey (2026-10-17)
Pulled the full build list (13,675 builds) from the dashboard's backing API (`/packages`, paginated). All builds below are aarch64 and passed. "apk" = installable via APK package manager; "cross" = source port in github.com/qnx-ports built with QNX makefiles. Platforms listed: QEMU, Raspberry Pi 4, Raspberry Pi 5.

| Need | Package (version, QNX release, type) |
|---|---|
| Inference | onnxruntime + python3-onnxruntime 1.24.4 (8.0.5, apk) |
| Inference | tflite-runtime + python3-tflite-runtime 2.21.0 (8.0.3, apk); XNNPACK, ruy also ported |
| Inference | ncnn + python3-ncnn 20260526 (8.0.5, apk) |
| Inference (heavy) | pytorch 2.3.1, tensorflow 2.16.1 (8.0.0, cross only) |
| Image/CV | opencv 4.12.0 incl. dnn, python3-opencv (8.0.3, apk); ARM ComputeLibrary 52.8 (8.0.5) |
| Python | python3 3.14 (8.0.3/8.0.5), python3-numpy 2.4.1, python3-pillow, python3-scipy |
| Camera | qnx-sf-camera-imx708 (Camera Module 3 sensor), qnx-rpi-camera-ipa, qnx-sf-camera-usb, qnx-sf-camera-ipc-server (8.0.5, apk). License: QDL **Non-Commercial**. |
| Video | gstreamer 1.26.8, ffmpeg 8.0 |
| MQTT | mosquitto 2.0.15 (8.0.0, cross; C lib + broker); qt6-mqtt. No Python paho client found. |

Caveats:
- Packages are split across releases: OpenCV/TFLite are built for 8.0.3, while ONNX Runtime/ncnn/camera are built for 8.0.5. Check whether 8.0.3 packages install on an 8.0.5 image before relying on mixing.
- The QNX camera is exposed through "QNX Sensor Framework" (`qnx-sf-*`), not obviously libcamera/V4L2. Whether OpenCV `VideoCapture` can read it is unknown; frames may need to come via the sensor-framework API and then be handed to OpenCV/numpy.
- "Built" ≠ "tested"; most entries show no test run. Performance on Pi 4 CPU unmeasured.

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
