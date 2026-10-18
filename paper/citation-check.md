# Citation check

Checked 2026-10-18 against publisher pages, Crossref, OpenAlex, Semantic Scholar, arXiv, the Zenodo API, and the projects' own citation files. BibTeX for every confirmed work is in [references.bib](references.bib).

Status key:
- **confirmed**: the facts in our docs match the source.
- **corrected**: the work exists, but something in our docs was wrong or incomplete. The right facts are given.
- **not found**: the work or the claim could not be confirmed. Do not cite it.

Number checks: "confirmed" means the number appears in the abstract or text. "not checked" means the full text was not reachable (most often a 403 from the publisher).

## 1. Prior poultry-dropping classification work

| Key | Cite for | Status | Facts and number checks | Source |
|---|---|---|---|---|
| machuve2022 | The original 4-class Tanzanian dataset and the CNN baselines. Also their untested claim that the model would not be affected by distribution shift | confirmed (one detail corrected) | Machuve D, Nwankwo E, Mduma N, Mbelwa J. Front. Artif. Intell. 5:733345, 2022 (Brief Research Report). Confirmed from the abstract: 83.06 / 85.85 / 94.79 / 87.46 / 88.27 % without fine-tuning, and 95.01 / 95.45 / **98.02 (MobileNetV2)** / 98.24 (Xception) % with fine-tuning and frozen BN. MobileNetV2 is the one they recommend. Test set is farm-labelled images only. PCR was run on "only 16%" of samples. The quote "We do not expect the model to be impacted by environment and distribution shift" is verbatim in the PDF. **Date discrepancy:** the paper says collection ran "February 2020 and February 2021", but both Zenodo records say September 2020 to February 2021. If we give dates, cite each source for its own dates | https://doi.org/10.3389/frai.2022.733345 ; local PDF paper/frai-05-733345.pdf |
| machuve2022corrigendum | Completeness only | confirmed | Front. Artif. Intell. 5:1016695, 2022, same authors. Its content (a funding statement fix) was not checked | https://doi.org/10.3389/frai.2022.1016695 |
| dhungana2025 | The closest pipeline to ours (YOLO11 detector, then a classifier) | confirmed, with a caveat | Dhungana A, Yang X, Paneru B, Dahal S, Lu G, Chai L. AgriEngineering 7(9):278, 2025. Abstract: YOLO11n mAP@0.5 = 0.881, EfficientNet-B0 99.12 % (B1 98.54 %), NCD precision 1.00 (B0) vs 0.88 (B1), total inference 25.8 ms. Our "~99%" is confirmed. The Streamlit app is not in the abstract (not checked; the abstract says "web-based"). **Caveat:** the abstract calls the 6,812 images "PCR-verified", but per Machuve et al. and Zenodo those are the farm-labelled set. The PCR set is 1,255 images. Worth pointing out | https://doi.org/10.3390/agriengineering7090278 |
| sakib2026 | ESP32-CAM edge capture with an EfficientNet-B0 classifier | confirmed; one claim not checked | Sakib SA, Misat MMH, Akanto TR, Islam J, Antara FA. J. Sensors 2026(1):1433795. Abstract: 99.19 % on a held-out public test set and **95.62 % on a separate local-farm dataset**. Our docs do not mention this second figure. Inference runs on a FastAPI cloud server, and the ESP32-CAM only captures. **"Only 2 NCD images" could not be checked** (Wiley returned 403) | https://doi.org/10.1155/js/1433795 |
| degu2023 | YOLOv3 + ResNet50 smartphone system | confirmed (details added) | Degu MZ, Simegn GL. Smart Agricultural Technology 4:100221, 2023 (PII S2772375523000515). Abstract: trained on 10,500 images "collected from Zenodo", YOLOv3 mAP 87.48 %, ResNet50 accuracy 98.7 % | https://doi.org/10.1016/j.atech.2023.100221 |
| reyad2024 | High in-dataset accuracies on the Kaggle copy | confirmed | Reyad A-M, Dey S, Bhuyian WU, Evan SI, Jahan N, Rahman R. Proc. 3rd Int. Conf. on Computing Advancements (ACM), pp. 145-153, 2024. Abstract: majority-vote ensemble **99.25 %** (confirmed). Uses the "publicly available poultry disease dataset from Kaggle". Individual models: EfficientNetB7 95, VGG19 96, MobileNetV3 91, ViT 99, Swin 99 % | https://doi.org/10.1145/3723178.3723198 |
| huda2024 | Same | confirmed | Huda MSA, Sarkar A, Tanvir K, Ali MA, Nandi D, Haq M. Same proceedings, pp. 830-837, 2024. Abstract: EfficientNetV2B0 + DenseNet121 hybrid, 97.78 % test accuracy. Our docs gave no number for it | https://doi.org/10.1145/3723178.3723288 |
| nakrosis2023 | Real-litter droppings in six appearance classes. Data only on request | confirmed | Nakrosis A, Paulauskaite-Taraseviciene A, Raudonis V, Narusis I, Gruzauskas V, Gruzauskas R, Lagzdinyte-Budnike I. Animals 13(19):3041, 2023. 91.78 % YOLOv5 classification accuracy, 92.41 % object detection, K-means Dice 0.8875 (0.88 in the abstract). 487 images (216 / 47 / 23 / 130 / 53 / 18), three Lithuanian farms. Data "available from the corresponding author upon request". All confirmed. The "94.5 % normal/abnormal" figure in docs/research.md was not checked | https://pmc.ncbi.nlm.nih.gov/articles/PMC10571708/ |
| wang2019 | Earlier dropping detection on a conveyor belt | confirmed; numbers partly checked | Wang J, Shen M, Liu L, Xu Y, Okinda C. J. Sensors 2019, Article 3823515. Abstract: Faster R-CNN 99.1 % recall and 93.3 % mAP, YOLOv3 88.7 % recall and 84.3 % mAP. Birds were 10,000 Ross broilers in multilayer cages. The "7,637 final images" figure is not in the abstract (not checked) | https://doi.org/10.1155/2019/3823515 |
| aworinde2023 | An independent (Nigerian) dataset for cross-dataset tests | confirmed | Aworinde HO, Adebayo S, Akinwunmi AO, et al. (10 authors). Data in Brief 50:109517, 2023. 19,155 raw images, 14,618 after cleaning, 100x100 JPEG (confirmed). Zenodo mirror 10.5281/zenodo.8122337 is CC BY 4.0 (confirmed). "94 physical instances" not checked | https://doi.org/10.1016/j.dib.2023.109517 ; https://zenodo.org/records/8122337 |
| li2025survey | Survey of open poultry computer-vision datasets | confirmed | Li G. Poultry Science 104(2):104784, 2025 (PII S0032579125000215). The survey covers 20 datasets, 6 of them for health status. Whether it reports the Machuve and Nigerian sets as described in our docs was not checked against the full text | https://doi.org/10.1016/j.psj.2025.104784 |

## 2. Datasets used

| Key | Cite for | Status | Facts | Source |
|---|---|---|---|---|
| machuve2021farm | Farm-labelled training images and YOLO boxes | **corrected** (license) | "Machine Learning Dataset for Poultry Diseases Diagnostics", Zenodo, version 2, 2021-02-03. Creators: Machuve, Nwankwo, Mduma, **Hope** Mbelwa, Maguo, Munisi (the paper lists "Jimmy Mbelwa"; use each source's own list). **License: CC BY 4.0.** docs/02-bibliography.md and docs/research/PAPER.md say "no explicit license displayed". That is wrong, and docs/research.md was right. Counts: 2,103 cocci, 2,057 healthy, 2,276 salmo, 376 NCD, 6,812 total (confirmed). Salmonella and NCD images were taken from **inoculated** birds, and coccidiosis and healthy images from farms. `imgObjDet_Yolo.zip` holds 6,812 label files and 9,094 non-empty lines. 9,090 of those lines are well-formed 5-field boxes, which matches the "9,090 boxes" in docs/research.md | https://zenodo.org/records/4628934 |
| machuve2021pcr | Separate PCR lab-confirmed test collection | **corrected** (license) | "... - PCR annotated", Zenodo, version 3, 2021-12-23. Creators: Machuve, Nwankwo, Lyimo, Maguo, Munisi. **License: CC BY 4.0.** 373 cocci, 347 healthy, 349 salmo, 186 NCD, 1,255 total (confirmed). PCR at NM-AIST | https://zenodo.org/records/5801834 |
| boniche2025piodata, boniche2026pio | PIO barn video, the background for the synthetic test clip | **corrected** (origin) | Zenodo record by Boniche K and Cruz E, 2025-08-01, CC BY 4.0. Data paper: Boniche, Cruz, Rangel, Hidalgo-Rodriguez, Gomez-Donoso, *Scientific Data* 13:801, 2026. **Recorded in Veraguas Province, Panama** (commercial farm plus prototype house). `app/live-feed/clips.py` credits it to "Universidade Federal da Grande Dourados", which is not supported by the record. Image count: 1,435 (Zenodo) vs 1,487 (paper abstract). Both report 327,289 instances | https://zenodo.org/records/16686320 ; https://doi.org/10.1038/s41597-026-07114-5 |
| nestler2025 | NESTLER pen videos | confirmed | "NESTLER Poultry Video Dataset", creator "NESTLER Horizon Project", Zenodo, 2025-03-21, CC BY 4.0, EU grant 101060762. A single file, `poultry_videos.zip` (about 82 MB) | https://zenodo.org/records/15063494 |
| cardoen2025bigbroiler | Big Broiler clips (behaviour models, held-out pens) | confirmed; counts differ | Cardoen T, Soster de Carvalho P, Lopes Carvalho C, Antonissen G, Tuyttens F, Leroux S, Simoens P. CV4Animals @ CVPR 2025, Nashville, 7 pp. No DOI (UGent handle). Repo license AGPL-3.0. **The paper and the repo give different counts:** the paper has 92 videos, 22 behaviours and 884,006 frames, while the repo README (v1 release) has 102 videos, 23 behaviours and 898,607 frames. Both report 3,560 tracks. Quote the repo figures for the release we used and say they come from the repo | https://biblio.ugent.be/publication/01K47TCM11DQFAY9ECSWKKV7C6 ; https://github.com/decide-ugent/big-broiler-dataset |
| (Kaggle allandclive/chicken-disease-1) | Do not cite as a source | n/a | A re-host of the Machuve data (counts match). Cite machuve2021farm and machuve2021pcr instead. Not re-checked here | https://www.kaggle.com/datasets/allandclive/chicken-disease-1 |

## 3. Software and platform

| Key | Cite for | Status | Facts | Source |
|---|---|---|---|---|
| jocher2024yolo11 | YOLO11n detector | confirmed | Jocher G, Qiu J. "Ultralytics YOLO11", v11.0.0, 2024, AGPL-3.0 (the docs page's own BibTeX). Docs table for YOLO11n: 640 px input, COCO mAP50-95 39.5, CPU ONNX 56.1 ± 0.8 ms, 2.6 M params, 6.5 B FLOPs. The repo's CITATION.cff now points to a YOLO26 arXiv paper, so use the YOLO11 docs entry. The "~200 ms per image on Pi 5 with ONNX" figure in paper-plan.md was **not checked** | https://docs.ultralytics.com/models/yolo11/ |
| onnxruntime | On-device runtime | confirmed | Author "ONNX Runtime developers", first release 2018-11-29, MIT license, per the repo's CITATION.cff. Add the exact version we ran | https://github.com/microsoft/onnxruntime/blob/main/CITATION.cff |
| hildebrand1992 | QNX microkernel architecture | confirmed; pages not confirmed | Hildebrand D (Quantum Software Systems). "An Architectural Overview of QNX". Proc. USENIX Workshop on Micro-Kernels and Other Kernel Architectures, Seattle, April 1992, ISBN 1-880446-42-1. Pages 113-126 come only from secondary bibliographies, so they are left out of the bib | https://ondoc.logand.com/d/8175/txt |
| qnx8sysarch | QNX OS 8.0 microkernel (the version on our Pi) | confirmed | QNX SDP 8.0 System Architecture guide, BlackBerry Limited: "The microkernel implements the core POSIX features used in embedded realtime systems." | https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.sys_arch/topic/about.html |

## 4. Evaluation methods and motivation

| Key | Cite for | Status | Facts | Source |
|---|---|---|---|---|
| guo2017 | Calibration, ECE, temperature scaling | confirmed | Guo C, Pleiss G, Sun Y, Weinberger KQ. ICML 2017, PMLR 70:1321-1330 | https://proceedings.mlr.press/v70/guo17a.html |
| wilson1927 | Wilson score interval (used in data-visualization/evaluation.py) | confirmed | Wilson EB. JASA 22(158):209-212, 1927 | https://doi.org/10.1080/01621459.1927.10502953 |
| kapoor2023 | Data leakage in ML-based science | confirmed | Kapoor S, Narayanan A. Patterns 4(9):100804, 2023. Abstract: leakage found in 17 fields and 294 papers, with a taxonomy of 8 leakage types | https://doi.org/10.1016/j.patter.2023.100804 |
| barz2020 | Near-duplicates between train and test | confirmed | Barz B, Denzler J. "Do We Train on Test Data? Purging CIFAR of Near-Duplicates". J. Imaging 6(6):41, 2020 | https://doi.org/10.3390/jimaging6060041 |
| geirhos2020 | Shortcut learning (e.g. collection context standing in for class) | confirmed | Geirhos R, Jacobsen J-H, Michaelis C, Zemel R, Brendel W, Bethge M, Wichmann FA. Nat. Mach. Intell. 2(11):665-673, 2020 | https://doi.org/10.1038/s42256-020-00257-z |
| geifman2017 | Selective prediction, risk-coverage trade-off ("ask a vet") | confirmed | Geifman Y, El-Yaniv R. "Selective Classification for Deep Neural Networks". NeurIPS 30, 2017. Abstract: on ImageNet, 2 % top-5 risk is guaranteed with probability 99.9 % at almost 60 % coverage | https://papers.nips.cc/paper_files/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html |
| ghiasi2021 | Copy-paste augmentation (droppings pasted onto pen frames) | confirmed | Ghiasi G, Cui Y, Srinivas A, Qian R, Lin T-Y, Cubuk ED, Le QV, Zoph B. CVPR 2021, pp. 2917-2927 | https://doi.org/10.1109/CVPR46437.2021.00294 |
| blake2020 | Economic burden of coccidiosis | confirmed | Blake DP, Knox J, Dehaeck B, et al. (14 authors). Vet. Res. 51:115, 2020. Abstract: UK cost £99.2 M in 2016 (range £73.0-125.5 M). Global cost **~£10.4 billion at 2016 prices** (£7.7-13.0 billion), £0.16 per chicken produced. Quote it in pounds sterling. Any dollar figure would be our own conversion | https://doi.org/10.1186/s13567-020-00837-2 |

## 5. Additional relevant works (not in the earlier docs)

| Key | Cite for | Status | Facts | Source |
|---|---|---|---|---|
| bodempudi2026 | **The closest prior cross-dataset test for fecal images.** Needed to frame our farm-vs-PCR and cross-source evaluation honestly | confirmed | Bodempudi VUC, Li G, Oladeinde A, Rothrock MJ, Aggrey SE, Liu T, Kota SAR, Yuan G, Nalla SSR. Comput. Electron. Agric. 252:112116, 2026. Binary Salmonella PCR positive/negative classification. Data: 720 US challenge-study images and 4,333 public African images. "Up to 85 %" accuracy across regions. Has a mobile/web app ("edge computing" in the title). We must not claim to be the first cross-dataset evaluation of fecal-image classifiers | https://doi.org/10.1016/j.compag.2026.112116 |
| zhang2026tinyml | Edge or microcontroller vision for livestock | confirmed | Zhang Q, Kanjo E. IEEE IoT Journal 13(1):666-677, 2026, doi:10.1109/JIOT.2025.3624811 (arXiv 2504.11467). Abstract: up to 270x smaller models and under 80 ms latency on commercial microcontrollers | https://arxiv.org/abs/2504.11467 |
| elmessery2023 | YOLO detection of broiler pathology in real houses (visual + thermal) | confirmed (metadata only) | Elmessery WM, et al. (10 authors). Agriculture 13(8):1527, 2023. A search snippet mentioned 10,000 images and mAP50 0.988, but the abstract was not read, so do not quote those numbers | https://doi.org/10.3390/agriculture13081527 |
| klein2009sel4 | Background on microkernels for safety-critical embedded systems | confirmed | Klein G, Elphinstone K, Heiser G, et al. (13 authors). "seL4: Formal Verification of an OS Kernel". SOSP 2009, pp. 207-220 | https://doi.org/10.1145/1629575.1629596 |

Search result: no peer-reviewed paper was found that runs a fecal-image or poultry-health model on QNX or any other microkernel RTOS. Only the vendor white paper above came up. Say "to our knowledge" and name the searches if the paper claims this gap.

## 6. NOT CONFIRMED: do not cite until checked

| Item (from our docs) | Problem |
|---|---|
| Sakib et al. 2026: "only 2 NCD images in its data" | Full text is behind Wiley (403). The paper itself is confirmed, but this claim is not |
| China multi-class set, "AEM journal", 10,548 samples, 5 categories | No title, DOI or authors in our docs. Not found |
| doi:10.11975/j.issn.1002-6819.202601168 (Chinese downstream reuse of the Machuve data) | Crossref returns 404 for this DOI. Not confirmed |
| Brazilian ONNX Runtime benchmark of tiny YOLOs on Pi 4 / Jetson Nano (sol.sbc.org.br wiarc 42894) | Not checked |
| "Ultralytics lists ~200 ms per image on Pi 5 with ONNX" | Not checked. The YOLO11 docs page gives only a CPU ONNX figure (56.1 ms, hardware not stated in what we read) |
| "YOLOv8n at 640 about 3 FPS on Pi 4 with ncnn" (Qengineering) | Not checked |
| OpenReview "Hybrid Optimization of Coccidiosis Chicken Disease ..." (id ZTXn9Yqt0s, Pi 4 + TFLite) | Page blocked by a verification screen. Title, authors and publication status unknown |
| Nakrosis "94.5 % normal/abnormal"; Wang 2019 "7,637 final images"; Aworinde "94 physical instances"; Elmessery numbers | The work is confirmed, but these numbers are not in the abstracts and the full text was not checked |
| Hildebrand 1992 pages 113-126 | Secondary sources only |
| Dhungana 2025 "Streamlit app" | Not in the abstract. Not checked |

## 7. Corrections to make elsewhere (not edited here)

1. **Machuve Zenodo licenses are CC BY 4.0** (both records, per the Zenodo API). docs/02-bibliography.md and docs/research/PAPER.md section 5 say "no explicit license displayed".
2. **PIO is from Panama** (Veraguas Province), by Boniche, Cruz et al. It is not from Universidade Federal da Grande Dourados as `app/live-feed/clips.py` says.
3. **Prior cross-region work exists** (bodempudi2026). The gap statement must be narrowed to the 4-class task, the farm-vs-PCR split and pen-scale video, not "first cross-dataset evaluation".
4. Collection dates differ: Feb 2020 to Feb 2021 in the paper vs Sep 2020 to Feb 2021 on Zenodo.
5. Dhungana 2025 calls the 6,812 farm-labelled images "PCR-verified". They are not.
6. Big Broiler counts differ between the paper (92 videos) and the repo (102 videos).
