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
- Pi 4 (BCM2711) BSP for QNX SDP 8.0 exists; release notes dated Jan 2026 (build 484).
  https://www.qnx.com/developers/docs/BSP8.0/com.qnx.doc.bsp.releasenotes/topic/rel_sdp80.bsp.broadcom.rpi4.bcm2711.html
- Quick Start Target Image (QSTI) for Raspberry Pi includes a camera demo; recommended if you need camera functionality.
  https://www.qnx.com/developers/docs/qnxeverywhere/com.qnx.doc.target_images/topic/qsti/intro.html
- Refreshed QSTI adds Raspberry Pi Camera Module 3 support and multi-camera configuration.
  https://qnx.software/en/blog/2026/refreshed-qnx-quick-start
- Custom image build repo for Pi 4 on QNX 8.0: https://devblog.qnx.com/refreshed-quick-start-custom-image-builds-and-more-samples
- Resources hub: https://oss.qnx.com/
- **Not confirmed**: whether QNX's camera stack is libcamera; whether ONNX Runtime/TFLite/OpenCV are available (oss.qnx.com ports list should be checked next). Whether Pi 5 is supported was not checked.
- **No evidence** QNX runs on ESP32. Other RTOSes (Zephyr, NuttX, FreeRTOS via ESP-IDF) do. https://www.espressif.com/en/media_overview/news/support-new-operating-systems-esp32-series-socs

## M5Stack StopWatch (C152 dev kit), per CNX Software / Mouser
- ESP32-S3R8, dual-core 240 MHz, 8MB PSRAM, 16MB flash, Wi-Fi 4, BLE 5
- 1.75" round AMOLED touch, 466x466; 2 buttons; vibration motor; 1W speaker; MEMS mic; IMU; RTC; Grove + GPIO; 450 mAh battery, USB-C
- No camera listed. Role here: alert display / farmer wearable.
- https://www.cnx-software.com/2026/05/22/m5stack-stopwatch-esp32-s3-devkit-offers-1-75-inch-touch-amoled-microphone-speaker-and-gpio-expansion/
- Sources are secondary (not the M5Stack page itself).
