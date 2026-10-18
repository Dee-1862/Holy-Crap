# Data visualization

An audit of the data and the detector behind Holy-Crap. The notebook downloads the published dataset labels, checks them against the publisher's checksum, rebuilds the train, validation and test split, checks the model files, and charts what the evidence does and does not show.

Open [01_data_and_model_audit.html](01_data_and_model_audit.html) to read it without installing anything. The notebook [01_data_and_model_audit.ipynb](01_data_and_model_audit.ipynb) is saved with its outputs, so it also reads fine on GitHub.

The second notebook, [02_model_evaluation](02_model_evaluation.html) ([ipynb](02_model_evaluation.ipynb)), asks how good the detector really is. It runs offline in a few seconds from committed files only.

## Main findings

| Finding | Number | Figure |
|---|---|---|
| Held-out farm test photos called right | 97.9% of 679 (95% CI 96.6 to 98.8%) | 07 |
| Lab-confirmed (PCR) photos from a separate collection called right | 67.1% of 1,255 (95% CI 64.4 to 69.6%) | 07 |
| Weakest class on new photos | Newcastle-like, 41.9% of 186 | 06, 07 |
| Test photos that are exact copies of a training photo | 49 of 679 (7.2%), removing them gives 97.8% | 10 |
| Box score as a probability | It is not, the model is right more often than its score says | 09 |
| Pen-scale fine-tune, unseen cameras | recall 0.29 to 0.80, precision 0.11 to 0.93 | 11 |
| Live test clip | 7 of 10 placed droppings found, 0 false flags | 12 |

The farm test number describes photos like the training photos. The lab-confirmed number is the better guide to new photos.

## What is checked

| Check | How | Result |
|---|---|---|
| The data is the published dataset | Zenodo API for record 4628934, then md5 of the downloaded label file against the md5 Zenodo lists | Verified |
| Class counts match our docs | Counted from the official YOLO boxes | Boxes match. Two classes differ by 1 and 2 photos only because a few label files are empty |
| The test set is separate and the size the README says | Rebuilt the split with the same code and seed as `training/prepare_data.py` | 679 test photos, each photo in one split |
| Oversampling only touches train | Read from `prepare_data.py` | Verified |
| The model files are the ones reported on | SHA256 recomputed for the laptop and Veri models, ONNX loaded and run once | Verified |
| Reported test scores | Read from `models/dropping4-laptop/test_metrics.json` and `models/dropping4-veri/test_metrics.json` | Reported, not recomputed here |
| Training against validation curves | `results.csv` from the close-up and pen runs, measured in notebook 2 | Validation stops improving while training loss keeps falling, early stopping keeps the best epoch (49 and 28) |
| Duplicates across the split | 256-bit difference hash of every farm photo, nearest training photo for each test photo | 49 exact copies, they barely change the score |
| A second source | Lab-confirmed (PCR) photos, Zenodo 5801834, never trained on | 67.1% against 97.9%, the farm test does not carry over |

## What it does not claim

It does **not** show that the model will hold up in a new barn. The lab-confirmed photos show a large drop on a new collection. What is still missing:

- A split by farm or visit. The publisher does not ship visit metadata.
- A test where every class is photographed from the same distance, to rule out the size shortcut below.
- Calibration of the box score before it is shown to anyone as a percentage.

The notebook also flags a possible shortcut: healthy droppings are photographed much smaller in the frame than the other classes (median 2.6% of the photo against 12 to 22%). A model could learn camera distance instead of appearance, so that should be tested before trusting class level scores.

## Run it

```
cd data-visualization
python -m venv .venv
.venv\Scripts\activate          # macOS and Linux: source .venv/bin/activate
pip install -r requirements.txt
jupyter lab 01_data_and_model_audit.ipynb
```

The first run downloads a 1.8 MB label file from Zenodo into `data/` (ignored by git). It needs network once. To refresh the saved copy:

```
jupyter nbconvert --to notebook --execute --inplace 01_data_and_model_audit.ipynb
jupyter nbconvert --to html 01_data_and_model_audit.ipynb
```

## Files

```
hc_viz.py                         chart style, fixed class colors, download and checksum helpers
01_data_and_model_audit.ipynb     the audit, saved with outputs
01_data_and_model_audit.html      the same, readable without Jupyter
02_model_evaluation.ipynb         how good the detector is: second source, duplicates, calibration, pen scale, live clip
02_model_evaluation.html          the same, readable without Jupyter
evaluation.py                     the figures of notebook 2, also runnable alone: python evaluation.py
audit_images.py                   the image audits behind results/
results/                          per-photo scores and hashes from audit_images.py
figures/                          charts as PNG, SVG and PDF, with the CSV table behind each
requirements.txt
```

## Chart method

Charts follow the bundled dataviz method: the form is chosen for the job (bars for counts, a cumulative curve for size, small multiples for score against data), one axis only, thin bars with a gap between them, the value written on every bar, fixed colors per class in every chart, and a data table beside each chart. The four class colors were run through the method's palette validator. They pass the color blind separation and normal vision checks. Two of them sit below 3:1 contrast on the light surface, which the method allows only when values are labelled and a table is shown, so both are done here.

No third party skills were downloaded for this. The charting method comes from the dataviz skill that is already installed.

## Image audits

`audit_images.py` produced the duplicate check and the lab-confirmed (PCR) scores used by notebook 2. It downloads about 13 GB once into `data/raw` (ignored by git), checks each zip against Zenodo's md5, then hashes or scores each photo and keeps only small CSV files in `results/`, which are committed. Teammates do not need to run it. `figures/pairs/` holds the three closest test and training pairs, Machuve et al. photos under CC BY 4.0.

```
python audit_images.py all      # about 13 GB, resumable
python audit_images.py clean    # delete the downloaded zips afterwards
```
