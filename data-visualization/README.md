# Data visualization

An audit of the data and the detector behind Holy-Crap. The notebook downloads the published dataset labels, checks them against the publisher's checksum, rebuilds the train, validation and test split, checks the model files, and charts what the evidence does and does not show.

Open [01_data_and_model_audit.html](01_data_and_model_audit.html) to read it without installing anything. The notebook [01_data_and_model_audit.ipynb](01_data_and_model_audit.ipynb) is saved with its outputs, so it also reads fine on GitHub.

## What is checked

| Check | How | Result |
|---|---|---|
| The data is the published dataset | Zenodo API for record 4628934, then md5 of the downloaded label file against the md5 Zenodo lists | Verified |
| Class counts match our docs | Counted from the official YOLO boxes | Boxes match. Two classes differ by 1 and 2 photos only because a few label files are empty |
| The test set is separate and the size the README says | Rebuilt the split with the same code and seed as `training/prepare_data.py` | 679 test photos, each photo in one split |
| Oversampling only touches train | Read from `prepare_data.py` | Verified |
| The model files are the ones reported on | SHA256 recomputed, ONNX loaded and run once | Verified |
| Reported test scores | Read from `models/dropping4-e37/test_metrics.json` | Reported, not recomputed here |

## What it does not claim

It does **not** show that the model is free of overfitting, and it says so in the notebook. The pieces that would show it are not in the repository yet:

- Training and validation curves (`results.csv` from the training run). The notebook draws them automatically when the file exists. Set `HC_RESULTS_CSV` or drop it in `training/work/train/`.
- A split by farm or visit. The current split is random by photo, so the same visit can be on both sides.
- A lab confirmed (PCR) check, and a near duplicate check across splits.
- A final model. The snapshot is epoch 37 of 100.

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
figures/                          PNG charts and the CSV tables behind them
requirements.txt
```

## Chart method

Charts follow the bundled dataviz method: the form is chosen for the job (bars for counts, a cumulative curve for size, small multiples for score against data), one axis only, thin bars with a gap between them, the value written on every bar, fixed colors per class in every chart, and a data table beside each chart. The four class colors were run through the method's palette validator. They pass the color blind separation and normal vision checks. Two of them sit below 3:1 contrast on the light surface, which the method allows only when values are labelled and a table is shown, so both are done here.

No third party skills were downloaded for this. The charting method comes from the dataviz skill that is already installed.
