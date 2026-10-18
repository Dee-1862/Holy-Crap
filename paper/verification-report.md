# Paper Verification Report

**Paper:** Held-out Accuracy Is Not New-Collection Accuracy: A Cross-Collection Benchmark of Poultry Dropping Classifiers and a Fault-Isolated Pen-Camera Detector on a QNX Raspberry Pi 5 (`paper/holy-crap-paper.tex`, compiled `holy-crap-paper.pdf`)
**Date:** 2026-10-18
**Method:** paper-verifier (storyline, claim-level fact check, internal consistency, methodology, citation spot-check)

---

## Executive Summary

The core story holds up. Almost every number in the abstract, the contributions, the results text, Table 1, the figure captions and the conclusion matches the released CSV and JSON files. I recomputed the main figures from the per-photograph predictions, including accuracy, Wilson intervals, the duplicate audit, coverage, ECE, grade-vs-model accuracy and the live-clip answer key, and they reproduce. The writing rules pass: the .tex has no em or en dashes, no `---` and no semicolons. The PDF has no `??` or TODO markers.

The problems are in the framing, not the arithmetic. Three are critical. (1) The novelty claim that nobody has tested the four-class task on a second collection is contradicted by Sakib et al. 2026, which the paper itself cites with a 95.62% result on a separate local-farm set. (2) The external "PCR-confirmed" test set holds 35 byte-identical image pairs (same MD5), and 19 of those pairs carry two different PCR classes. The paper does not disclose this, even though it audits duplicates in the farm set. (3) Per its Zenodo record, the farm collection's salmonella and Newcastle photographs come from experimentally inoculated birds. The paper says instead that the farm labels describe "the farm a sample came from" and that the photos were "taken on farms". That leaves out a major confound that bears directly on the paper's main finding (the salmonella lean and the shortcut discussion).

The important issues are mostly overclaims. The QNX part of the paper is described as "fault isolated", yet it measured only supervisor respawn after SIGKILL. A contribution says "every model timed on the device", but the paper later says the baselines were not timed. The drop is called "the same for all" models, but a paired test shows MobileNetV2 and EfficientNet-B0 differ significantly on the lab set. The abstract and conclusion imply the pen model is part of the Pi pipeline, which it is not. The paper also treats overlapping CIs as evidence of no difference.

**Limitations of this audit.** The MDPI (Dhungana) and Wiley (Sakib) full texts returned 403, so for those I checked abstracts only (via OpenAlex). The Bodempudi check is abstract-only too. I did not log in to the Pi, so the Pi timings are checked against the repo documentation (`docs/qnx-microkernel.md`, `target/qnx/edge/ortlite/README.md`), not re-measured. I could not re-run model training or inference because the images are not in the repo. The Scholar Gateway and Consensus connectors were not authorized, so they were not used.

### Severity Summary
- Critical (must fix before submission): 3
- Important (should fix): 11
- Minor (nice to fix): 17
- Suggestions: 8

---

## Critical Issues

### C1. "First such test for the four-class task" is contradicted by a paper the authors cite
- **Where:** Introduction, para 2 and Contribution 1. Also Related work, "Classifying poultry droppings".
- **Sentences:** "This has not been tested for the four-class task." and "To our knowledge this is the first such test for the four-class task."
- **Problem:** Related work states: "Sakib et al. ... reporting 99.19% on a public test set and 95.62% on a separate local-farm set~\cite{sakib2026}". I confirmed that number from the Sakib et al. abstract via OpenAlex: four classes (coccidiosis, Newcastle, salmonella, healthy), EfficientNet-B0, "95.62% on a separate real-world dataset from local commercial farms". That is a four-class test on a second collection. A reviewer will spot the contradiction inside the paper itself. Sakib's much smaller drop (about 3.6 points) also cuts against the paper's general reading that published accuracies are only within-collection accuracies, and the paper never discusses it.
- **Fix:** Narrow the claim, for example: "To our knowledge this is the first test of the four-class task on photographs whose labels were confirmed by PCR, with the training split, the models and the per-photograph predictions released." Replace "This has not been tested for the four-class task" with "Only one study has tested the four-class task on a second collection, a local-farm set with an unreported labelling protocol~\cite{sakib2026}, and none on laboratory-confirmed labels." In the Discussion, add a sentence on why Sakib et al. saw a smaller drop (different label source, local set built by the same team, and so on), or say that it cannot be explained from their abstract.

### C2. The PCR test set has 35 byte-identical image pairs, 19 of them with conflicting PCR labels (undisclosed)
- **Where:** Methods, Data ("Lab-confirmed photographs"). Results 4.1 and 4.5. Abstract.
- **Sentence:** "a second, separate collection of 1,255 photographs whose labels were confirmed by polymerase chain reaction (PCR)".
- **Evidence (recomputed):** In `data-visualization/results/pcr_predictions.csv`, 70 rows share a 256-bit dHash with another row, forming 35 pairs. In `dataset/grading/release/grades.csv`, the same 70 rows share `source_md5`, so the files are byte-identical. The detector gives the two files of each pair identical scores. In 19 of the 35 pairs the two files sit in different PCR classes: 16 coccidiosis/healthy pairs (e.g. `pcrcocci.118.jpg` = `pcrhealthy.108.jpg`) and 3 healthy/salmonella pairs (e.g. `pcrhealthy.306.jpg` = `pcrsalmo.202.jpg`).
- **Problem:** The same photograph cannot be both PCR-positive for coccidiosis and PCR-negative, so at least 19 labels are wrong or the files were misfiled. The paper's case rests on "lab-confirmed" labels as the reference standard, and it audits duplicates in the farm set but not here. The numeric effect is small. Without the 38 conflicting files, accuracy rises by about 1 point (detector top-1 76.3 to 77.3%, MobileNetV2 74.6 to 75.6%, EfficientNet-B0 78.2 to 79.5%), so the headline drop survives. But the label-quality claim and the effective sample size (1,220 unique images, not 1,255) do not. The grade analysis is affected too, since duplicated photos were graded twice. The paired grades differ by up to 2 points, which also says something about rater consistency.
- **Fix:** Add a sentence in Data and a row or footnote in Results, for example: "The PCR release contains 35 pairs of byte-identical files, 19 of them filed under two different classes (16 coccidiosis and healthy, 3 healthy and salmonella). Removing the 38 conflicting files changes every model's accuracy by at most 1.3 points." Report the de-duplicated accuracies in the appendix or a table note. Soften "labels were confirmed by PCR" to "labelled from PCR results by the dataset authors", and list the conflicting pairs in the release.

### C3. The farm collection's disease photos come from inoculated birds, but the paper describes them as farm-labelled photos
- **Where:** Methods, Data ("Farm photographs"). Limitations. Discussion ("What the farm test measures").
- **Sentences:** "It contains 6,812 full-resolution smartphone photographs taken on farms in Arusha and Kilimanjaro" and "because the farm labels describe the appearance of the dropping and the farm a sample came from, not a laboratory diagnosis of each dropping." Limitations: "The farm labels describe appearance and farm".
- **Problem:** The Zenodo record 4628934 description, fetched from the Zenodo API, says the chickens "were inoculated for Salmonella disease", with fecal images taken "after one week", and inoculated for Newcastle disease, with images "within three days". Only the healthy and coccidiosis images are described as coming from "poultry farms". So two of the four farm-set classes come from an experimental inoculation setting. That is the kind of class-specific collection context the paper's own shortcut argument (Discussion, citing Geirhos) is about. It could explain the salmonella lean in Section 4.5 ("MobileNetV2 also calls 72 of the 215 normal looking healthy photographs salmonella") and the collapse of Newcastle recall. Leaving it out misdescribes the data and weakens the Discussion's list of candidate causes.
- **Fix:** Rewrite as follows. "The healthy and coccidiosis photographs were taken on farms, and the salmonella and Newcastle photographs from experimentally inoculated birds, in Arusha and Kilimanjaro (Zenodo record description)." In the Discussion, add this as a candidate cause: "In the farm collection the salmonella and Newcastle photographs come from inoculated birds, so the setting itself may stand in for the class." The Limitations sentence needs the same correction.

---

## Important Issues

### I1. Contradiction: "every model timed on the device" against "We did not time the baseline classifiers on the Pi"
- **Where:** Contribution 4 against Section 4.7.
- **Sentences:** "A complete pipeline running on a Raspberry Pi 5 under the QNX microkernel, with every model timed on the device." and "We did not time the baseline classifiers on the Pi."
- **Evidence:** `target/qnx/edge/ortlite/README.md` times only the three detector ONNX files: `dropping4_yolo11n_320` (168 ms), `dropping4_yolo11n_640` (618 ms) and `dropping4pen_yolo11n_640` (608 ms). The 416 export and the Veri model were not timed either.
- **Fix:** "with our detector and pen model timed on the device". Better still, time the MobileNetV2 and EfficientNet-B0 ONNX exports, which `benchmark_classifiers.py export` already produces "for timing on the Pi".

### I2. "Fault-Isolated" in the title, and the QNX claims, go beyond what was measured
- **Where:** Title. Abstract ("Each stage is an isolated process, and any stage we killed was restarted in 20 to 33 ms while the others kept running"). Contribution 4. Discussion "Why a microkernel". Conclusion ("any failed stage restarts in tens of milliseconds").
- **Problem:** The only fault experiment is SIGKILL on user-level pipeline processes, followed by a respawn by the project's own supervisor (`docs/qnx-microkernel.md`: "SIGKILL on any section: restarted in 20 to 33 ms"). Process isolation and supervisor respawn are features of the pipeline design, not of the microkernel itself. Nothing that is specific to a microkernel was exercised: no driver, camera service, `io-sock` or file-system process was killed, and no fault was injected into the ONNX runtime. The number of kill trials per section and how restart time was measured are not reported. The conclusion's "any failed stage" turns "killed with SIGKILL" into "failed".
- **Fix:** Retitle along the lines of "... and a Process-Isolated Pen-Camera Pipeline on a QNX Raspberry Pi 5", or keep "fault-isolated" only after you have killed and restarted a QNX driver-level process (e.g. the camera service) and measured it. In the abstract and conclusion write "killed with SIGKILL" and report n per section (e.g. "restarted in 20 to 33 ms over N kills of each of the seven sections"). Say how the time was measured (the supervisor's timestamp from exit to the new process being ready?).

### I3. The abstract and conclusion imply the pen model runs in the Pi pipeline, and the deployed pipeline's accuracy is never measured
- **Where:** Abstract ("On unseen cameras, recall rises ... The full pipeline runs on a Raspberry Pi 5 under the QNX microkernel"). Conclusion ("our YOLO11n detector finds 80% of pen-sized droppings ... The full pipeline runs on a Raspberry Pi 5").
- **Problem:** Section 4.7 says "On the Pi, the deployed pipeline proposes candidates with a still-spot finder and judges a full-resolution patch of each with the close-up detector." The pen model was only timed on the Pi, and the live clip "was made on a laptop". The deployed pipeline (spot finder, close-up detector on patches, explanation step) has no accuracy result at all. The repo docs also note a failure mode the paper does not mention: "At pen scale it [the close-up detector] scores white birds as salmonella at up to 0.83", which the explain-step heuristics suppress (`docs/qnx-microkernel.md`, "Limits, stated plainly").
- **Fix:** In the abstract write "A pipeline built around the close-up detector runs on a Raspberry Pi 5 ...". In 4.7 add "We have not measured the detection accuracy of the deployed pipeline on the Pi." In the Methods (deployment), mention the explain-step filters and why they exist.

### I4. "the drop is the same for all of them", and overlapping CIs used as evidence of no difference
- **Where:** Contribution 1 ("the drop is the same for all of them"). Section 4.1 ("On the lab-confirmed photographs the intervals of all three models overlap").
- **Evidence (recomputed, paired McNemar exact test on the 1,255 PCR photos, top-1 calls):** MobileNetV2 vs EfficientNet-B0: 81 against 127 discordant photos, p = 0.0017. MobileNetV2 vs detector: p = 0.20. EfficientNet-B0 vs detector: p = 0.16. The drops are 25.0 points (MobileNetV2), 20.8 (EfficientNet-B0) and 22.2 (detector, always answers).
- **Problem:** The drops are similar, not the same, and two of the baselines do differ significantly on the lab set. Overlapping 95% CIs are not a test of equality, and with paired data they are especially conservative. The main message (the gap between test sets is far larger than the gaps between models) still holds.
- **Fix:** "the drop is 21 to 25 points for every model". In 4.1: "A paired McNemar test finds no difference between the detector and either classifier (p = 0.16 and 0.20), while EfficientNet-B0 is ahead of MobileNetV2 (p = 0.002). All of these differences are small next to the drop."

### I5. "98 to 99%" understates the range the paper reports
- **Where:** Abstract ("Every model scores 98 to 99% on the farm test"). Discussion ("reaches 98 to 99% on the random farm test"). Conclusion.
- **Problem:** Table 1 gives MobileNetV2 at 99.6%, and Contribution 1 says "98.5 to 99.6%". The range "98 to 99" leaves out the top score, and the abstract and contribution then disagree.
- **Fix:** Use "98.5 to 99.6%" (or "about 99%") everywhere. Keep the "98 to 99%" wording only where it describes published numbers.

### I6. The 8-to-30-pixel premise is an assumption, stated as a measurement
- **Where:** Abstract ("Since a fixed pen camera sees each dropping at 8 to 30 pixels"). Introduction. Section 3.4 ("In a pen camera at 1280x720 a dropping covers 8 to 30 pixels").
- **Evidence:** In `training/pen_scale.py`, `SIZE_PX = (8, 30)` is a design constant ("longest side of a pasted dropping in a 1280 wide pen frame"). The paper reports no measurement of real droppings in pen footage, and Limitations says "We have no labelled droppings from a real pen camera." The deployed camera also captures at 2304x1296 (`docs/qnx-microkernel.md`), not 1280x720.
- **Fix:** Give the basis for the number, for example "assuming a dropping 1 to 4 cm across seen by a 1280-pixel-wide camera covering about N m of floor", or "we estimate". Say that pen frames are resized to 1280 wide.

### I7. Citation used for a claim it does not make: Barz and Kapoor cited for a fact about this collection
- **Where:** Introduction, para 2.
- **Sentence:** "A random split by photograph places pictures from the same farm visit, and sometimes the same picture, on both sides of the split~\cite{barz2020,kapoor2023}."
- **Problem:** Barz and Denzler document near-duplicates in CIFAR, and Kapoor and Narayanan survey leakage across fields. Neither says anything about this collection, about farm visits, or about the general claim. The "same picture" part is supported by the paper's own audit, Section 4.3. The "same farm visit" part is not shown anywhere: the paper says the release "carries no farm or visit information".
- **Fix:** "A random split by photograph can place near-identical pictures on both sides of the split, as documented for standard benchmarks~\cite{barz2020}, and such leakage has inflated results in many fields~\cite{kapoor2023}. Section 4.3 shows it happens here." Drop "the same farm visit" or mark it as possible.

### I8. "Bodempudi et al. also found a drop across regions" goes beyond their abstract
- **Where:** Discussion, "What the farm test measures".
- **Sentence:** "Bodempudi et al. also found a drop across regions for a binary Salmonella task~\cite{bodempudi2026}."
- **Problem:** The abstract (OpenAlex) reports "up to 85% classification accuracy when validated across geographical regions". It does not report a within-region figure in the part I could read, so a "drop" cannot be confirmed. Could not verify against the full text (ScienceDirect).
- **Fix:** Check the full text for a within-region number. If there is none, write "Bodempudi et al. reached at most 85% across regions for a binary Salmonella task".

### I9. Huda et al. is cited for "98 to 99%" on the Tanzanian collection, but reports 97.78% and does not name the dataset in its abstract
- **Where:** Introduction, para 1 ("convolutional classifiers reach 98 to 99% accuracy~\cite{machuve2022,dhungana2025,degu2023,reyad2024,huda2024}"). Related work ("Later work on the same photographs or their 224-pixel Kaggle copy reports similar or higher numbers.").
- **Problem:** Huda et al.'s abstract (Semantic Scholar) gives 97.78% and names no dataset. Reyad et al. say only "a publicly available poultry disease dataset from Kaggle". I could not verify that it is the Machuve 224-pixel copy. Machuve 2022 itself reports 98.02%, which fits.
- **Fix:** Write "97.8 to 99.3%", or drop huda2024 from that bracket. Confirm in the full texts that Reyad and Huda used the Machuve data, or write "on what appear to be the same photographs".

### I10. "Run-to-run variation ... is small next to a drop of more than 20 points" asserts something not measured
- **Where:** Limitations.
- **Sentence:** "Run-to-run variation is therefore not measured, although it is small next to a drop of more than 20 points."
- **Problem:** The sentence says variation is not measured, then states its size. `benchmark_classifiers.py` defaults to three seeds, but only seed 0 exists in `benchmark_predictions.csv`. The one replicate available (the Veri detector) differs by 0.019 mAP50 on the farm test, but there is no replicate on the PCR set.
- **Fix:** "Run-to-run variation is not measured. It would have to exceed 20 points to explain the drop, which is far beyond the 0.02 mAP50 gap between our two detector runs." Better: run seeds 1 and 2, which the script already supports.

### I11. Table 2 uses a different n than the dataset and does not say why
- **Where:** Table 2 and Section 4.5.
- **Problem:** Table 2 lists Salmonella n = 347 and Coccidiosis n = 366, while Data says 349 and 373. The difference is the 9 "unusable" photographs (2 salmonella, 7 coccidiosis, from `grades.csv` quality = unusable; `grade_vs_models.json` "photos_graded": 1246). Section 4.5 says the alpha is "over the 1,255 photographs", which is right for the agreement statistic but invites confusion. The caption also omits which detector mode is used. I recomputed and it is always-answer top-1: 84.2% healthy, 93.3% salmonella. At the 0.25 cut, healthy would be 65.1%.
- **Fix:** Caption: "n excludes the nine photographs no rater could judge. Detector accuracy is its top class (always answers)." Also remove "MobileNetV2 is the seed 0 run", which implies other seeds exist.

---

## Minor Issues

1. **Abstract, "Removing them changes the farm accuracy by only 0.1 points".** I verified this for all models: detector at 0.25, 97.9 to 97.8; detector always-answer, 98.5 to 98.4; MobileNetV2, 99.56 to 99.52; EfficientNet-B0, 98.97 to 99.05. But 4.3 reports only the thresholded detector, while Table 1 leads with the always-answer row. Fix: add one sentence giving the change for all four rows.
2. **4.3, "inspection of the closest pairs shows they are the same image saved under two file names".** `figures/pairs/pairs.json` saves only one distance-0 pair for inspection. All 49 pairs do share width, height and class (recomputed), which supports the claim, but "inspection" covered one pair. Fix: "they have identical hashes, dimensions and classes, and the pair we inspected is the same image under two file names."
3. **4.3 / Split.** Validation also holds 53 exact copies of training photographs, and 13 test photographs copy validation ones (recomputed from `farm_hashes.csv`). Validation drove early stopping and epoch selection. Fix: mention it in 4.3.
4. **Data: 6,812 photographs against a split of 5,451 + 679 + 679 = 6,809.** Three photographs have no labels (`farm_hashes.csv` split = "unlabelled"). Fix: "6,809 have labels and enter the split".
5. **4.5, "mean form penalty 0.61 against 0.28" and "undigested feed (0.44 against 0.09)".** These reproduce only if empty sub-scores count as 0 and the 9 unusable photographs are included. With empty scores excluded, as the rubric's "leaves them empty" implies, they are 0.64 against 0.28 for form and 0.52 against 0.10 for feed. The direction is the same. Fix: state the convention, or use the second set.
6. **4.5, coccidiosis "6 of the 26 normal looking photographs".** With n = 26 the 95% Wilson CI is about 11 to 42%. Give the interval.
7. **Abstract, "both models still name them correctly".** "Both" is undefined in the abstract, and EfficientNet-B0, the best model, is left out of the grade analysis. Fix: "the detector and MobileNetV2", and add EfficientNet-B0 to Table 2.
8. **Table 1 citations.** `MobileNetV2~\cite{machuve2022}` and `EfficientNet-B0~\cite{dhungana2025}` in the table rows suggest the numbers are taken from those papers, but they are retrained here. Fix: "MobileNetV2 (as in [25])", or move the citations to the caption.
9. **Detector GPU.** `models/dropping4-laptop/README.md` says "local RTX 3060 (batch 16 ...)". The Compute section names only an RTX 4060 for the other runs. Fix: name the 3060 and batch 16 for the detector.
10. **Pen-scale metrics lack operating points.** Recall 0.80 and precision 0.93: at what confidence and IoU? Fix: state them (e.g. conf 0.25, IoU 0.5).
11. **"The box score ranks photographs well".** No ranking metric (AUROC, AURC) is reported. The evidence is accuracy rising with threshold, 78.8 to 87.4%. Fix: report AURC, or write "higher scores are more often right".
12. **Raters "Claude Opus, Claude Sonnet and Claude Haiku".** No model versions or dates are given. Fix: add the exact model identifiers.
13. **Weighted kappa citation.** Quadratic weighting is usually credited to Fleiss and Cohen (1973), and Cohen (1968) introduced weighted kappa in general. Fine as is, but consider adding Fleiss and Cohen 1973.
14. **Bibliography rendering in the PDF.** [28] ONNX Runtime prints the internal note "Cite the exact version used". [21] prints "Describes the difference hash (dHash)". The dataset entries [7], [23], [24] and [27] render with no DOI or URL. [1] renders "south-west nigeria" in lower case. BibTeX warns that `@software` is unknown to plainnat and that `qnx8sysarch` has an empty year. Fix: delete the notes, add `howpublished = {\url{https://doi.org/10.5281/zenodo.4628934}}` (and the same for the others), brace `{N}igeria`, add `year = {2026}` to qnx8sysarch, and change `@software` to `@misc`.
15. **Microkernel citation.** "Microkernels move drivers and services into isolated processes, so a fault stays in one process~\cite{klein2009sel4,qnx8sysarch}." seL4 is about formal verification. hildebrand1992, which describes QNX's architecture directly, is in the bib but never cited. Fix: cite hildebrand1992 alongside qnx8sysarch.
16. **Uncited motivation.** "Coccidiosis, salmonellosis and Newcastle disease change the colour and consistency of droppings, and farmers already look at droppings to judge flock health." No source is given. Fix: add a veterinary source.
17. **Machuve quote context.** "The original authors wrote that they did not expect their model to be affected by distribution shift." This is verbatim-accurate (local PDF: "We do not expect the model to be impacted by environment and distribution shift"). But it follows "we expect it will be able to perform effectively elsewhere in Tanzania, where the poultry disease distribution is the same." Fix: add "within Tanzania" for fairness.

---

## Suggestions

1. Report the PCR results after de-duplication (see C2) as a robustness row.
2. Run seeds 1 and 2 for both baselines. The script already supports them, and this would remove the single-seed caveat.
3. Add EfficientNet-B0 to the appearance-grade analysis (Table 2).
4. Test the framing shortcut directly. The Discussion says it has not been tested: crop every class to the same box share and re-score.
5. Time both baselines on the Pi with the existing ONNX exports. That makes Contribution 4 true as written and adds a device comparison.
6. Report the kill experiment as a small table: section, n kills, min, median and max restart time, and frames lost by the other sections.
7. Mention that Dhungana et al. call the 6,812 farm images "PCR-verified" (confirmed in their abstract via OpenAlex), which the PCR release and Machuve et al. contradict. This sharpens the paper's point about label sources.
8. Positive finding worth stating. No PCR photograph is within 61 bits of any farm photograph (minimum Hamming distance 62 of 256, recomputed), which supports "lab-confirmed photographs that no model saw".

---

## Detailed Audit Reports

### Step 0. Section map
Abstract. 1 Introduction (gap, 4 contributions). 2 Related work (droppings, cross-collection testing, edge/OS). 3 Methods: 3.1 Data, 3.2 Split, 3.3 Detector, 3.4 Pen-scale, 3.5 Baselines, 3.6 Evaluation, 3.7 Appearance grades, 3.8 QNX deployment. 4 Results: 4.1 benchmark, 4.2 errors, 4.3 duplicates, 4.4 calibration, 4.5 grades, 4.6 pen-scale, 4.7 deployed pipeline. 5 Discussion (incl. limitations, future work). 6 Conclusion. Data/code, Ethics, Compute, AI use, Acknowledgements. Two tables, eight figures. No structural anomalies. The appearance-grade material (3.7 and 4.5) is the most "bolted on" part, but it ties back to the failure analysis.

### Step 1. Storyline audit
- **Narrative summary:** Published four-class dropping classifiers report 98 to 99% on random splits of one collection. Retrained baselines and the authors' detector all score about 99% on the farm test and 75 to 78% on a second, PCR-labelled collection. Duplicates do not explain the gap, and the detector is not a better classifier. Its value is localisation at pen scale, shown with a synthetic copy-paste fine-tune. A QNX Pi pipeline shows process restart.
- **Motivation chain: WEAK.** The gap statement is false as written (C1). The second gap, "nobody is there to restart the device", motivates QNX, but the evaluation tests only process respawn (I2).
- **Section flow: PASS.** Transitions are clear. The QNX section is the loosest fit to the benchmark story.
- **Claim consistency: ISSUES FOUND.** I1 (timing), I3 (pen model on Pi), I5 (98 to 99 against 98.5 to 99.6), I4 ("the same" drop).
- **Red flags:** The title promises fault isolation, which is not evaluated. The messaging service (iMessage, DeepSeek) is described but explicitly not evaluated, which is acceptable as stated.

### Step 2. Claim verification (numbers recomputed or matched to repo files)
| Claim | Source checked | Status |
|---|---|---|
| Farm acc. 99.6 / 99.0 / 98.5, CIs 98.7-99.8 / 97.9-99.5 / 97.3-99.2 | 13_benchmark.csv; recomputed from benchmark_predictions.csv (676/679, 672/679) | Verified |
| PCR acc. 74.6 / 78.2 / 76.3, CIs 72.1-76.9 / 75.9-80.4 / 73.9-78.6 | same (936/1255, 982/1255) | Verified |
| Macro-F1 values, Table 1, all 16 cells | 13_benchmark.csv | Verified |
| 0.25-threshold row 97.9 / 97.7 / 67.1 / 70.3 | 13_benchmark.csv | Verified |
| "drop of more than 20 points" | 25.0 / 20.8 / 22.2 (30.8 thresholded) | Verified |
| NCD recall 0.70 / 0.88 against 0.53. Healthy 0.81 against 0.66 / 0.68 | 13_benchmark.csv | Verified |
| Farm diagonal 95 to 100% | 06/07 csv (94.6% rounds to 95) | Verified |
| No detection 20% healthy, 27% NCD | 68/347, 51/186 | Verified |
| NCD recall 94.6% (35/37) to 41.9% (78/186) | 07_recall_by_class.csv | Verified |
| NCD 376 photos against >2,000 for the others | summary_by_class.csv | Verified |
| 49 copies (7.2%), all correct, 97.8% (96.3-98.7) against 97.9% | 10_duplicates csv; recomputed from farm_hashes.csv | Verified |
| Others differ by at least 40 bits | recomputed (minimum nonzero = 40) | Verified |
| Coverage 78.8% to 87.4% at 27.8% answered | 08 csv | Verified |
| ECE 0.177 / 0.172, under-confident | 09 csv | Verified (PCR is under-confident in 8 of 10 bins, near-calibrated at the top) |
| Alpha 0.76, pairwise kappa 0.71-0.84, variables 0.56 / 0.57 / 0.75 / 0.74 | agreement.json | Verified |
| Self kappa 0.71-0.86, exact 37 to 47% | agreement.json | Verified |
| 9 unusable, 331 partial, 234 spread of 3 or more | grades.csv | Verified |
| Table 2 grade means, normal shares, accuracies | grade_vs_models.json | Verified (n caveat, I11) |
| 899 positives, 190 normal (83% / 87%) and 709 not (73% / 76%) | recomputed | Verified |
| 72 of 215 (33%) and 32 (15%) normal-looking healthy called salmonella | recomputed | Verified |
| Form 0.61 / 0.28, feed 0.44 / 0.09 | recomputed | Verified only with empty scores counted as 0 (Minor 5) |
| Pen recall 0.29 to 0.80, precision 0.11 to 0.93, 3.55 to 0.05 boxes, close-up mAP50 0.873 to 0.853, 4-class 0.65 | before_after.json, 11 csv | Verified |
| Laptop epoch 69 / best 49, Veri 0.854 / 0.573 against 0.873 / 0.573, 20 epochs, batch 32 | test_metrics.json, READMEs | Verified |
| Patience 20 and seed 0 (detector). Pen: 40 epochs, patience 10, stopped at 38 | train.py:195, pen_train.py, results.csv (38 rows) | Verified |
| Baselines over 98% val within 4 epochs, 20 and 8 epochs | benchmark_training_log.csv | Verified (the EfficientNet rows in that log have a stray extra column) |
| Live clip: 7 of 10 flagged, 5 within 2 s, no false flags | 12 csv; test-a1.json (7 spots, 0 without truth) | Verified (the run was on a laptop, as the paper says) |
| Pi: 168 / 618 / 608 ms, 4 threads | ortlite/README.md | Verified against docs, not re-measured |
| 95 us for a 57.6 KB round trip. Restart 20 to 33 ms. Spot-finder kill costs camera 1 frame | docs/qnx-microkernel.md | Verified against docs. n trials not documented |
| ONNX Runtime 1.24.4 from oss.qnx.com. Python binding broken because the build takes the Windows branch. 111-line C bridge. Patch prepared | ortlite/README.md, target/qnx/upstream/README.md and 0002 patch, hc_ort.c = 111 lines | Verified |
| Healthy median box 2.6% against 12 to 22% | summary_by_class.csv | Verified |
| 0.1% of pen frame | 30x30 / (1280x720) = 0.098% | Verified (arithmetic) |
| "first such test for the four-class task" | Sakib 2026 abstract | Incorrect (C1) |
| "every model timed on the device" | ortlite README | Incorrect (I1) |
| Farm photos "taken on farms", labels describe "the farm a sample came from" | Zenodo 4628934 | Incorrect for salmo/NCD (C3) |

### Step 3. Internal consistency
- **Numbers: ISSUES FOUND.** I5 (98 to 99 against 98.5 to 99.6). I11 (n 347/366 against 349/373). Minor 4 (6,812 against 6,809). Duplicate-removal row choice (Minor 1).
- **Figures and tables: CONSISTENT.** Every figure and table is referenced. Captions match the CSVs. Table 2's caption is incomplete (I11).
- **Cross-references: CONSISTENT.** No `??` in the PDF. `\ref{sec:discussion}` from 3.8 points to the right paragraph.
- **Notation: CONSISTENT.** "-like" class names are used consistently after Data. "lab-confirmed", "PCR-confirmed" and "PCR" are used interchangeably, which is acceptable.

### Step 4. Methodology review
- **Experimental design: CONCERNS.** The design is good: same split, same test sets, a fully external collection with verified zero near-duplicate overlap with the farm data. Concerns: one seed per baseline (acknowledged); a label-noisy external set (C2); a confounded farm collection (C3); a synthetic pen test (acknowledged clearly); and no accuracy measurement of the Pi pipeline (I3).
- **Metrics: APPROPRIATE.** Accuracy, macro-F1, per-class recall, Wilson CIs, risk-coverage, ECE. Operating points for the pen metrics are missing (Minor 10).
- **Statistical rigor: ADEQUATE.** Wilson intervals are used throughout. No paired tests between models (I4). Small-n cells in Table 2 are presented without intervals (Minor 6).
- **Threats to validity:** Acknowledged: single region and group, random split, synthetic pen test, AI raters, single seed, inference-only timings. Not acknowledged: PCR duplicates with conflicting labels (C2), inoculated-bird origin of two farm classes (C3), validation-set duplicates (Minor 3), and the close-up detector's white-bird false positives on the Pi (I3).

### Step 5. Citation spot-check
Citations checked: 22. Issues: 5 (Sakib used against the novelty claim, Barz/Kapoor, Bodempudi "drop", Huda range and dataset, seL4).

| Key | Claim in paper | Finding | Status |
|---|---|---|---|
| machuve2022 | 5 CNNs, MobileNetV2 98.02%, Xception 98.24%, recommended MobileNetV2, distribution-shift quote | All in local PDF (lines 647-686, 738, 781-782). The quote follows a Tanzania-specific sentence | Accurate (context, Minor 17) |
| machuve2021farm | 6,812 farm photos, Arusha/Kilimanjaro, CC BY 4.0 | Zenodo API confirms counts and licence. Salmo/NCD from inoculated birds, Sept 2020 to Feb 2021 | Mischaracterized (C3) |
| machuve2021pcr | 1,255 PCR photos, 373 / 347 / 349 / 186 | Counts match Machuve Table 1 and grades.csv | Accurate. Dataset has conflicting duplicates (C2) |
| dhungana2025 | YOLO11n then EfficientNet-B0, mAP50 0.881, 99.12% | OpenAlex abstract confirms. Calls the images "PCR-verified". Web-based tool, no device named | Accurate. "laptop" in "phone, a server or a laptop" could not be verified |
| sakib2026 | ESP32-CAM, EfficientNet-B0 on a server, 99.19% and 95.62% | Abstract confirms the numbers, four classes, FastAPI backend. "ESP32-CAM" is not in the abstract ("camera module") | Numbers accurate. ESP32-CAM could not be verified. Contradicts the novelty claim (C1) |
| bodempudi2026 | Binary Salmonella PCR +/-, US and African images, up to 85% across regions | Abstract confirms (720 US, 4,333 African images) | Accurate in Related work. "drop" not verified (I8) |
| degu2023 | YOLOv3 + ResNet-50, phone app, 98.7% | Abstract confirms (10,500 images incl. oversampling, mAP 87.48%) | Accurate |
| reyad2024 | 99.25% majority-vote ensemble | Confirmed. Dataset is "from Kaggle", not confirmed to be the Machuve copy | Accurate (dataset unverified) |
| huda2024 | 97.78% EfficientNetV2-B0 + DenseNet-121, cited in the "98 to 99%" bracket | 97.78% confirmed. Dataset not named in abstract | Mischaracterized in Intro (I9) |
| blake2020 | about GBP 10.4 billion at 2016 prices | Abstract confirms | Accurate |
| kapoor2023 | Leakage inflated results across fields | Confirmed (17 fields, 294 papers, per citation-check) | Accurate in Related work. Misused in Intro (I7) |
| barz2020 | Near-duplicates between splits of standard benchmarks | Title and content confirm (CIFAR) | Accurate in Related work. Misused in Intro (I7) |
| geirhos2020 | Shortcut learning, background/framing | Consistent with the paper | Accurate |
| guo2017 | ECE, reliability diagrams, temperature scaling | Consistent | Accurate |
| geifman2017 | Selective prediction, risk-coverage | Consistent | Accurate |
| qnx8sysarch | QNX drivers, FS and network stack are user processes | Consistent with the vendor docs and docs/qnx-microkernel.md | Accurate |
| klein2009sel4 | Microkernel fault containment | seL4 is a verification paper. Weak support | Weak (Minor 15) |
| zhang2026tinyml | Up to 270x smaller for microcontrollers | Per citation-check (arXiv abstract) | Accurate. Not re-fetched |
| nakrosis2023, aworinde2023, wang2019, li2025survey | Dataset facts | Per citation-check. Not re-fetched here | Not re-verified |
| ghiasi2021, sandler2018, tan2019, wilson1927, hayes2007, cohen1968, krawetz2013, jocher2024yolo11, onnxruntime | Method and tool references | Appropriate uses | Accurate |
| boniche2025piodata / boniche2026pio / nestler2025 | PIO and NESTLER videos, CC BY 4.0 | Per citation-check (Zenodo API) | Accurate. Not re-fetched |

### Writing rules
- Em dashes, en dashes, `---`: none in `holy-crap-paper.tex`. **Pass.**
- Semicolons in prose: none. **Pass.**
