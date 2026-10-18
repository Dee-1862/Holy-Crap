# Paper Plan

Status: planning. All numbers below come from web-search summaries and have NOT been checked against the original papers. Verify before citing (marked `[verify]`).

## 1. Where the gap is (what NOT to claim)
Already published, so "we classify chicken feces with a CNN" is **not novel**:
- Machuve et al. 2022, Frontiers in AI, doi:10.3389/frai.2022.733345. Baseline CNN, VGG16, InceptionV3, MobileNetV2, Xception; MobileNetV2 recommended for deployment (~98%) [verify].
- YOLO11 + EfficientNet-B0 two-stage pipeline, AgriEngineering 2025, doi:10.3390/agriengineering7090278 (~99% classifier accuracy, Streamlit app) [verify]. **Closest to our pipeline; read first.**
- ESP32-CAM + EfficientNet-B0 IoT system, Journal of Sensors 2026 (Wiley); notes only 2 NCD images in its data [verify]. Directly relevant to our ESP32 question.
- YOLOv3 + ResNet50 smartphone system (ScienceDirect 2023, S2772375523000515) [verify].
- Ensembles/fusion on the Kaggle data: ACM 10.1145/3723178.3723198 (~99.25%), 10.1145/3723178.3723288 [verify].
- Nakrosis et al. 2023, Animals 13(19):3041 (Lithuania, six abnormality classes, three farms) [verify].

Reported accuracies of 98-99% on one dataset are likely inflated by random splits (see Risks). A paper that just reports 99% again will not stand out.

## 2. Candidate contributions (pick 1-2; ordered by how defensible they are)
A. **Honest generalization evaluation.** The filename prefixes give a built-in farm-vs-PCR-lab split to test (train farm, test lab, and the reverse), in addition to cross-dataset tests. Split by source (farm/collection batch/breed), not randomly; deduplicate; test cross-dataset (Tanzania -> Nigeria -> Lithuania/China sets). Show how much accuracy drops. High value, cheap, needs no hardware.
B. **Deployment-focused benchmark on a QNX Raspberry Pi 5 (Camera Module 3, TFLite).** Latency, memory, power, thermal throttling for a model matrix (below), real-time on QNX. Few if any papers report QNX (not checked exhaustively); this is the unique angle tied to your hardware. Runtime path now identified: TensorFlow Lite + OpenCV QNX ports, with QNX's open-source AI Camera App as a base (Apache-2.0). Remaining risk: building/running it on Pi 5.
C. **Alerting policy, not single-image classification.** Temporal aggregation per zone (e.g. N abnormal in T minutes) vs per-frame, evaluated on simulated sequences, with false-alarm rate. Moves the work toward a system paper.
D. **Floor-scene detection+classification with real clutter** (bedding, feed, feathers). Needs your own labeled barn images; strongest but most work, and requires farm access/ethics.

Suggested framing: **A + B** ("Is fecal-image disease screening ready for real-time edge deployment? A cross-source evaluation and QNX benchmark"). Add C if time allows. Only claim D if you collect your own data.

## 3. Datasets
Update 2026-10-17 (reported by another session, not rechecked): the Zenodo releases (doi:10.5281/zenodo.4628934 farm, 5801834 PCR) are CC BY 4.0, full resolution, with official YOLO boxes. Prefer Zenodo over the Kaggle copy (224 px, license unknown) for the paper.
| Dataset | Notes |
|---|---|
| Kaggle `allandclive/chicken-disease-1` (user's link; page contents verified by user 2026-10-17) | 8,067 images, 4 classes (Salmonella ~33%, Coccidiosis ~31%, Healthy, New Castle Disease), `train_data.csv` with image name + label, v1, 294 MB. Collected in Arusha and Kilimanjaro, Tanzania, Sep 2020 - Feb 2021 with the ODK app on phones. **Pre-resized to 224x224.** **License: Unknown.** Class counts from secondary source: cocci 2,476 / healthy 2,404 / NCD 562 / salmonella 2,625 (sum = 8,067, matches; salmonella and cocci percentages match the page). Filename prefixes `cocci. healthy. ncd. salmo.` and `pcrcocci. pcrhealthy. pcrncd. pcrsalmo.` (the `pcr*` ones are very likely the PCR-confirmed lab images; inferred, verify). 8,067 = 6,812 farm + 1,255 lab images in Machuve et al., so this is that paper's full dataset, re-hosted. |
| Tanzania farm + PCR-verified lab set (Machuve et al. 2022; Zenodo per a citing paper, unconfirmed) | Cocci ~2.1k, healthy ~2.1k, NCD ~0.4k, salmonella ~2.3k, YOLO-format boxes in one version [verify]. |
| Nigeria smartphone set, Data in Brief 2023 (PMC10477973) | 19,155 raw, 14,618 after cleaning, 100x100 px JPEG [verify]. Independent source -> good for cross-dataset testing. |
| China multi-class set (AEM journal) | 10,548 samples, 5 categories, Guangdong broiler farms + vet institute [verify]. Availability unknown. |
| Lithuania set (Nakrosis 2023) | Six abnormality classes, three farms. Availability unknown. |
| Own barn images | Needed for any claim about real floors. |

Rule: Kaggle copies of the Tanzania data are NOT independent datasets. Don't count them as separate sources.

## 4. Model matrix (keep it small and justified)
Classifier (stage 2), all pretrained on ImageNet then fine-tuned:
- MobileNetV2 (baseline from Machuve et al.)
- MobileNetV3-Small/Large
- EfficientNet-B0 / EfficientNet-Lite0 (literature favorite; Lite variant is friendlier to int8 export)
- ResNet18/50 as a heavier reference
- Optional: a small ViT/DeiT-tiny or Swin-tiny for an accuracy-vs-cost contrast

Detector (stage 1), only if using floor images with boxes:
- YOLOv8n or YOLO11n (one of them), YOLOv5n (reported to balance latency and accuracy on a Pi 4 in a Brazilian benchmark [verify]; Pi 5 not tested there)
- SSDLite-MobileNetV3 as a non-YOLO reference

Ablation: single-stage YOLO with 4 classes vs the two-stage pipeline (is stage 2 worth its cost?).
Export: must reach **TFLite** (Keras -> TFLite directly, or PyTorch -> ONNX -> TFLite via a converter, or train in TensorFlow); compare FP32 vs INT8 accuracy and latency. Prefer ops TFLite supports (MobileNet/EfficientNet-Lite are safe; check ViT/Swin and YOLO exports before committing).

Pi 4 speed anchors from the literature (Pi 5 is faster; rough, different runtimes, unverified): YOLOv8n at 640 about 3 FPS with ncnn; Ultralytics lists ~200 ms per image on Pi 5 with ONNX [verify]. Expect low single-digit FPS detection on the Pi 5 until measured: fine for a slow robot, not for 30 FPS video.

## 5. Experiments
1. Within-dataset baseline: stratified, deduplicated split. Report accuracy, macro-F1, per-class recall (NCD matters most), confusion matrix.
2. Source-held-out: train on A, test on B (and leave-one-source-out). Report the drop.
3. Class imbalance: weighted loss vs oversampling vs augmentation; augment AFTER splitting.
4. Robustness: blur, low light, JPEG compression, color shift, bedding backgrounds (synthetic pasting). Color is the main signal, so test white-balance and color-jitter sensitivity.
5. Calibration: confidence reliability (ECE); selective prediction ("uncertain, ask a vet").
6. Explainability: Grad-CAM to check models look at the dropping, not background/camera artifacts.
7. Edge benchmark on QNX Pi 5: latency (median/p95), RAM, CPU temperature/throttling, power, FP32 vs INT8, input size sweep.
8. Optional: alert-policy simulation.

## 6. Risks to the paper
- **Data leakage / non-independence:** near-duplicates, multiple photos of the same dropping, and the same source across Kaggle copies inflate results. Deduplicate (perceptual hash) and split by source.
- **Tiny NCD class:** per-class claims about NCD are weak with a few hundred images or fewer. Say so.
- **Label noise / not a diagnosis:** labels are often farm-annotated; only part is PCR-confirmed. Frame as screening, not diagnosis.
- **Visual confounders:** diet, bile and cecal droppings change color. State as a limitation.
- **QNX ML runtime (reduced risk):** TFLite and OpenCV ports exist for QNX 8.0 and QNX's ai-camera-app uses them, but its README targets Pi 4 B. First task: build and run it on our Pi 5. If it fails, benchmark on Pi OS instead, say so clearly, and reframe contribution B.
- **Hardware is Pi 5** (TARGET.md). Pi 4 numbers from other papers are not directly comparable; benchmark ourselves.
- **License unknown** on the Kaggle copy: before publishing, cite Machuve et al. as the original source, find the original (Zenodo) release and its license, or contact the authors.
- **224x224 pre-resized images:** fine for classification, but limits any detector/crop experiments and means real-camera resolution is not represented.
- Several paper numbers still unverified.

## 7. Paper outline
1. Abstract
2. Introduction: economic burden of coccidiosis/NCD/salmonella; screening via droppings; the gap (generalization + edge reality)
3. Related work: table of the papers in section 1
4. Datasets and preprocessing: sources, dedup, splits
5. Methods: models, training, quantization, edge setup, alert policy
6. Experiments and results: sections 5.1-5.8
7. Discussion: failure cases, Grad-CAM, limitations (not a diagnostic tool)
8. Conclusion and future work (floor-scene data, robot, on-farm trial)
Appendix: hyperparameters, hardware, reproducibility (seeds, split files, code link)

## 8. Venue ideas (check scope and deadlines yourself)
Computers and Electronics in Agriculture; Smart Agricultural Technology; Sensors; AgriEngineering; Animals; or workshops on TinyML / edge AI / AI for agriculture. For a student or competition paper, a workshop is more realistic than a journal.

## 9. Next steps
1. Kaggle page checked (see Datasets). Still to do: download, hash files, confirm `pcr*` prefix = lab-confirmed, find original release + license.
2. Read the closest papers fully (YOLO11+EfficientNet; Machuve; ESP32-CAM IoT) and fix the gap statement.
3. Download the Tanzania and Nigeria sets; build dedup and source-aware split scripts.
4. Train baselines on a laptop; produce the first results table.
5. In parallel: build the TFLite + OpenCV QNX ports and run ai-camera-app on the Pi 5 via `qnxpi`.
6. Decide whether to collect own barn images (needs farm permission).
