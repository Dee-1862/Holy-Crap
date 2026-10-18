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
- **Not confirmed**: whether QNX's camera stack is libcamera and whether it works on the Pi 5; whether ONNX Runtime/TFLite/OpenCV are available (oss.qnx.com ports list should be checked next).
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
