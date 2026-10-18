# Notes: Machuve et al. 2022, "Poultry diseases diagnostics models using deep learning"
Frontiers in AI 5:733345, doi:10.3389/frai.2022.733345. Read from the PDF in this folder (frai-05-733345.pdf) and an open-access full-text summary; key items below were re-checked against the PDF text.

## Dataset (their Table 1)
| Class | Lab (PCR) | Farm | Total |
|---|---|---|---|
| Healthy | 347 | 2,057 | 2,404 |
| Salmonella | 349 | 2,276 | 2,625 |
| Coccidiosis | 373 | 2,103 | 2,476 |
| Newcastle | 186 | 376 | 562 |
| Total | 1,255 | 6,812 | 8,067 |

- The totals equal the Kaggle class counts exactly, so the Kaggle set is this full dataset. The `pcr*` filename prefixes therefore almost certainly mark the 1,255 lab images (counts match; prefix meaning still to confirm on the files).
- PCR was done on only 16% of samples (NM-AIST lab). Farm labels came from vets/field officers.
- Collected on phones with ODK in Arusha and Kilimanjaro, layers/cross/indigenous breeds. Paper says Feb 2020-Feb 2021; Kaggle says Sep 2020-Feb 2021 (discrepancy, check).
- Zenodo: farm images https://zenodo.org/record/4628934 ; lab images https://zenodo.org/record/5801834. Dataset license not stated in the article (check Zenodo).

## Method
- Models: baseline CNN, VGG16, InceptionV3, MobileNetV2, Xception; frozen-base transfer, then fine-tuning, then fine-tuning with BatchNorm frozen (inference mode).
- Input sizes: 128 (baseline), 224 (VGG16, MobileNetV2), 299 (InceptionV3, Xception). Colab Pro, Tesla P100, TensorFlow/Keras.
- **Split: 80/20 train/test, 15% of train for validation. The paper does not say whether it was random or by farm/visit.** Training used farm + lab images; test used farm-labeled images only.
- Hyperparameters are in Supplementary Table 4 (not in the main text; get the supplement).

## Results (accuracy %: no FT / FT / FT+frozen BN)
Baseline 83.06 (only); VGG16 85.85 / 94.65 / 95.01; InceptionV3 94.79 / 94.94 / 95.45; MobileNetV2 87.46 / 97.14 / 98.02; Xception 88.27 / 97.36 / 98.24.
(The PDF text extraction scrambled this table's columns; the frozen-BN accuracies match the prose: 95.01, 95.45, 98.02, 98.24. Re-check against the rendered table before quoting the other columns.)
F1 {cocci, healthy, ncd, salmo} with frozen BN: baseline {0.92, 0.86, 0.14, 0.81}; VGG16 {0.98, 0.95, 0.77, 0.95}; InceptionV3 {0.98, 0.94, 0.77, 0.95}; MobileNetV2 {0.99, 0.97, 0.94, 0.99}; Xception {0.97, 0.98, 0.98, 0.99}.
Size: MobileNetV2 26 MB vs Xception 238 MB. Authors prefer MobileNetV2 for phones despite Xception's +0.22 pt accuracy.

## Things we can use / challenge
- **They state they "do not expect the model to be impacted by environment and distribution shift"; never tested.** This is exactly our contribution A (cross-source evaluation). Strong, citable motivation.
- Split method is unspecified, so the 98% could include same-farm/same-visit leakage. We split by source and by farm-vs-PCR.
- Newcastle is the weak class (baseline F1 0.14; InceptionV3 NCD recall 62.7%), and has the fewest images (562). Per-class NCD claims need caution.
- No on-device latency or TFLite accuracy was measured ("future work"). Our QNX Pi benchmark (contribution B) fills this.
- Authors list classification only; detection/segmentation as future work -> motivates the two-stage pipeline.
- Authors admit label noise risk (Salmonella vs healthy, white color) and no clinical history.
- Internal inconsistencies to avoid copying: abstract says F1 above 75% in all classes but baseline NCD F1 is 0.14; MobileNetV2 is called better-generalizing while Xception scores higher.
- Corrigendum (doi:10.3389/frai.2022.1016695) fixed only the funding statement per the search result.

## Open items
- [ ] Get the supplementary tables (hyperparameters, split details, full per-class precision/recall).
- [ ] Download Zenodo records; check license; confirm `pcr*` prefix = lab images.
- [ ] Confirm collection dates discrepancy.
