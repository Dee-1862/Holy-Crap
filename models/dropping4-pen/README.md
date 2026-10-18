# dropping4-pen

YOLO11n fine-tuned from dropping4-laptop to find droppings at the size they have in a pen camera (8 to 30 pixels in a 1280 wide frame).
Trained on the RTX 4060 laptop GPU with training/pen_train.py. Early stopping ended the run at epoch 38, the best epoch was 27 (results.csv, results.png).

Run it on 640 by 640 squares of the frame at camera size (four squares cover a 1280 by 720 frame). No zoom step is needed, unlike the close-up model.

## How it was trained

- Close-up photos: the same Machuve split as dropping4-laptop.
- Pen tiles: real droppings cut from Machuve training photos, shrunk to pen size and pasted onto empty litter in barn video frames.
  Backgrounds come from five PIO broiler house videos and two NESTLER cameras. Every frame full of birds with no pasted dropping teaches the model that birds and equipment are not droppings.
- Split by camera. Validation uses a NESTLER camera not in training. Everything shown in the live feed is held out: PIO 0002 and the NESTLER cameras behind the live clips.

## Results on held out cameras (before_after.json)

| | dropping4-laptop | dropping4-pen |
|---|---|---|
| Pen test, any class, mAP50 | 0.067 | 0.875 |
| Pen test recall | 0.29 | 0.80 |
| Pen test precision | 0.11 | 0.93 |
| Boxes per real pen tile with nothing pasted, conf 0.25 | 3.55 | 0.05 |
| Close-up test mAP50 (4 classes) | 0.873 | 0.853 |

The pen test uses test split droppings pasted onto held out cameras, so it measures finding a dropping of pen size on unseen litter.
It is synthetic. No real droppings in these videos are labelled, so field accuracy is not measured yet.
Disease class at pen size is weaker (pen test 4 class mAP50 0.65). Use the pen model to find droppings and the close-up model to judge them.

Overfitting: validation loss flattened from about epoch 25 while training loss kept falling. Early stopping kept epoch 27.
Of the run time filters, the litter check now lowers recall (0.735 to 0.695 in training/pen_tweaks.py) and the size limit changes nothing, so the live feed uses neither beyond the size limit.
