# Vision Plan (data + model)

Written 2026-10-17. Scope: datasets, model training and running inference on the QNX Pi. Hardware and alerting are covered in game-plan.md.

## Tracks we are entering (LA Hacks AI Hackathon 2026)
Sources: live.lahacks.com/tracks (requires login, so this is taken from search snippets), veri.studio/lahacks, Devpost.

**QNX: "Best use of QNX"**: build an embedded system with QNX that uses AI.
- Hard requirement 1: the product runs on QNX OS.
- Hard requirement 2: the product includes one of the open-source AI modules from https://oss.qnx.com. Any of these counts: ONNX Runtime, TFLite (tensorflow port), ncnn, OpenCV dnn, pytorch.
- Prizes (Devpost snippet): $1,000 / $250 / $250.

**Veri (veri.studio)**: train or post-train an open-source model on the Veri platform.
- Veri confirmed to us that the model doesn't need to be one of theirs, only open source. Vision models count.
- Veri is built for LLMs, but its **custom script** mode runs any PyTorch training on a GPU it provisions (base image `veri/base`: CUDA 12.8, PyTorch 2.8, Python 3.10). Code is uploaded with the `veri run-script` CLI. Files written to `$VERI_OUTPUT_DIR` are saved to our account, and metrics logged with `veri_sdk.log_metrics` appear as charts in their UI.
- GPUs: mostly L4 (24 GB), which is plenty for a nano/small detector. Get credits from @daniung on the LA Hacks Discord and redeem them at veri.studio/settings/billing **before** the first run. Jobs on a $0 balance are killed.
- Prize: veri.studio/lahacks says $800 for the winning team; Devpost says $200 split between 3 winners. Not resolved.

How one project covers both tracks: **train an open-source detector on Veri → export it → run it on the QNX Pi 5 with a runtime from oss.qnx.com.**

## Blocker found: QNX version mismatch
TARGET.md says the Pi runs **QNX 8.0.0**. On oss.qnx.com:
- ONNX Runtime is only built for **8.0.5** (apk). There is no 8.0.0 build.
- For 8.0.0 there are only source ports (`cross`): tensorflow 2.16.1 (includes TFLite), opencv 4.9.0, pytorch 2.3.1, numpy, XNNPACK, ComputeLibrary, mosquitto.
- The camera packages (`qnx-sf-*`) on oss.qnx.com are built for 8.0.4/8.0.5. The camera stack already installed on the Pi is unknown.

**Decision rule:** train once and export **both ONNX and TFLite**, so the runtime decision doesn't hold up training.
1. On the Pi, check whether `apk` exists and whether the 8.0.5 onnxruntime package installs and loads. If it does, use ONNX Runtime (the earlier decision).
2. If it doesn't, use **TFLite** built from the qnx-ports tensorflow port for 8.0.0. QNX's own AI Camera App already does this on a Pi, and it still meets QNX hard requirement 2.
3. Upgrading the Pi to 8.0.5 is possible, but it would touch the Railway tunnel / onboot setup (see AGENTS.md). Do this only if Lance agrees.

## What we can use from oss.qnx.com
oss.qnx.com provides runtimes and libraries only. **It has no ready-made models; we train our own.**

**Prebuilt `apk` packages.** Built for QNX 8.0.3/8.0.4/8.0.5, so they're unproven on our 8.0.0 Pi. TARGET.md says the package tree is "not configured or verified".

| Use | Package |
|---|---|
| Inference | `onnxruntime`, `tflite-runtime`, `ncnn` (all with Python bindings) |
| Image handling | `opencv` 4.12, `python3-opencv`, `python3-numpy`, `python3-pillow` |
| Camera | `qnx-sf-camera-imx708` (Camera Module 3) plus the Pi 5 sensor-framework packages |

**`cross` source ports built for 8.0.0 (our version).** These must be compiled with the QNX SDP on a Linux host.

| Use | Port |
|---|---|
| Inference | `tensorflow` 2.16.1, which includes TFLite and is the path AICA uses |
| Image handling | `opencv` 4.9, `numpy` 1.25, `eigen` |
| Speed-ups | `XNNPACK`, `ComputeLibrary` |
| Messaging | `mosquitto` (MQTT) |
| Not useful | `pytorch` 2.3.1, too heavy for on-device inference |

Order to try on the Pi:
1. Prebuilt `tflite-runtime` or `onnxruntime` apk.
2. If neither works on 8.0.0, build TFLite from the `tensorflow` port following the AICA README.

## Data
**Primary dataset: Machuve et al., Zenodo, CC BY 4.0** (credit required). https://doi.org/10.5281/zenodo.4628934
- Full-resolution phone photos taken on farms in Tanzania: `cocci.zip` 2.7 GB, `healthy.zip` 2.4 GB, `salmo.zip` 3.1 GB, `ncd.zip` 0.35 GB.
- `imgObjDet_Yolo.zip` (2 MB) contains **official YOLO bounding boxes**. Inspected 2026-10-17:

| Class | Label files | Boxes | Images with more than one box |
|---|---|---|---|
| healthy | 2,057 | 3,311 | 699 |
| cocci | 2,103 | 3,075 | 616 |
| salmo | 2,276 | 2,320 | 42 |
| ncd | 376 | 384 | 6 |

  - The class comes from the folder name. Inside each file the class id is `0`, except for 356 boxes in cocci with id `1` (meaning unknown; check a few by eye).
- PCR-confirmed subset (lab-verified labels): https://doi.org/10.5281/zenodo.5801834. Use it as the **trusted test set**, since its labels are stronger than visual labelling.
- The Kaggle set (`allandclive/chicken-disease-1`) is the same images resized to 224 px, with no boxes and the license listed as "Unknown". Use it only for quick classifier experiments, and cite Zenodo.
- Roboflow is no longer needed, because Zenodo has official boxes under a clear license. It's a backup if the Zenodo boxes turn out bad.

**Data risks**
- **NCD is badly under-represented** (384 boxes vs about 3k for other classes). Use class weights or oversampling, and report recall per class, not just overall mAP.
- Images from the same farm on the same day leak between train and test under a random split. Split by group if the filenames or metadata allow it. Otherwise use a random stratified split and say so in the results.
- Domain gap: these are close-up phone photos. Our camera has to sit close to the floor (30–60 cm) to resemble them.

## Model
**Recommended: one-stage, 4-class detector.** It finds droppings and labels the class in a single pass. This means one model on the Pi and no crop/second-model code in C++.
- Model: YOLO11n (Ultralytics, AGPL-3.0, open source). Its exporter writes both ONNX and TFLite directly.
- Input size: train at 640, then test 320/416 on the Pi for speed. Target is 1–2 FPS on CPU.
- If Ultralytics' AGPL license is a problem, alternatives under Apache-2.0 are YOLOX-nano and RT-DETR (larger).

**Class scheme (open decision).** Both come from the same Zenodo labels, only the mapping differs:
- **4-class** (healthy / cocci / salmo / ncd). This is the original plan. NCD has only 384 boxes.
- **2-class** (normal / abnormal = healthy vs the other three). This fits PR #1's "no disease names in the product output" stance and avoids the NCD imbalance.
- Proposal: train both (cheap, same pipeline) and decide on the output wording later. Even with 4 classes, the UI can say "abnormal, consult a vet".

**Training feasibility.** Data, model and GPU are all available (Zenodo CC BY 4.0 + YOLO11n + Veri L4). Rough guess, not measured: about 1–2 h per full run on an L4, plus downloading about 8.5 GB. Training happens off the Pi; the Pi only runs the exported model.

**Two-stage (from the game plan) is a stretch goal:** a 1-class "dropping" detector plus a classifier on each crop (MobileNetV3-Small or EfficientNet-B0, torchvision, BSD). Only worth it if the 4-class detector confuses cocci and healthy.

**Evaluation (on the PCR test set where possible)**
- Detection: mAP@0.5 and mAP@0.5:0.95.
- Per-class precision and recall, plus a confusion matrix. Watch cocci ↔ healthy and NCD recall.
- Speed: ms per frame on the Pi 5 CPU at each input size.
- Published work reports about 90% mAP with YOLOv5 variants on this data (unverified search snippet, not yet read).

## Training on Veri
Project layout (to create): `training/`
```
training/
  prepare_data.py   # downloads the Zenodo zips, matches each image to its label, remaps class ids by folder, writes a YOLO dataset + data.yaml
  train.py          # Ultralytics train, logs to veri_sdk, exports best.pt -> .onnx and .tflite into $VERI_OUTPUT_DIR
  requirements.txt  # ultralytics, veri-sdk
```
Run with:
`veri run-script ./training --entrypoint 'python prepare_data.py && python train.py' --base-image veri/base --gpu-type L4-24GB --gpu-count 1 --requirements ./training/requirements.txt`
- Download the data inside the job (about 8.5 GB from Zenodo; fast from a datacenter) instead of uploading it from a laptop. Alternatively, put it on a Veri volume once and reuse it.
- Run a smoke test first: 1 epoch on a few hundred images, to confirm credits, export and output capture all work.

## On the Pi
1. Run the TFLite and ONNX Runtime checks above (Lance has SSH access). Benchmark a **stock** yolo11n `.tflite`/`.onnx` immediately, before our model is trained, to learn the FPS budget.
2. Camera: check whether the Sensor Framework camera API exists on this 8.0.0 image, and get one frame with `camera_example1_callback`.
3. C++ app: camera capture → resize → inference → non-max suppression → results logged and published over MQTT. Reuse `QSFCameraIntake` from the QNX AI Camera App and replace `TFLiteExecutor` only if we use ONNX Runtime.
4. Fallback demo: if the camera doesn't work, run the same binary on still photos from the PCR test set.

## Order of work (hackathon, run in parallel)
| Rishit (data/model) | Lance (Pi) |
|---|---|
| Get Veri credits; write prepare_data.py; smoke-test on Veri | Check apk, onnxruntime and TFLite on QNX 8.0.0 |
| Full training run; export ONNX and TFLite | Benchmark stock yolo11n; get the camera working |
| Evaluate on the PCR set; tune input size against Pi speed | Build the C++ inference app around the stock model |
| Hand over the final model | Swap in our model; add MQTT |

## Open questions
- Pi: does `apk` exist on the 8.0.0 image? Does the camera work?
- 4-class vs 2-class output. Reconcile with PR #1 (Lance's research knowledge base), which drops disease-name outputs and leaves the inference location open (Pi vs desktop). Keep inference on the Pi to stay eligible for the QNX track.
- Pi 5 CPU speed for YOLO11n at 320/416/640: benchmark a stock model before ours is trained.
- Veri prize amount and judging criteria. Do they want the training run shared publicly (they have a "Sharing runs" feature)?
- Is AGPL (Ultralytics) acceptable to the team?
- What do the 356 class-id-1 boxes in cocci mean?
