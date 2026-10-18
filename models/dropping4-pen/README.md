# dropping4-pen

YOLO11n fine-tuned from dropping4-laptop to find droppings at the size they have in a pen camera (8 to 30 pixels in a 1280 wide frame).
Trained on the RTX 4060 laptop GPU with training/pen_train.py. This file set is the best checkpoint after 5 epochs of a run that was cut short.

Run it on 640 by 640 squares of the frame at camera size (four squares cover a 1280 by 720 frame). No zoom step is needed, unlike the close-up model.

## How it was trained

- Close-up photos: the same Machuve split as dropping4-laptop.
- Pen tiles: real droppings cut from Machuve training photos, shrunk to pen size and pasted onto empty litter in barn video frames.
  Backgrounds come from five PIO broiler house videos and two NESTLER cameras. Every frame full of birds with no pasted dropping teaches the model that birds and equipment are not droppings.
- Split by camera. Validation uses a NESTLER camera not in training. Everything shown in the live feed is held out: PIO 0002 and the NESTLER cameras behind the live clips.

## Results on held out cameras (before_after.json)

| | dropping4-laptop | dropping4-pen |
|---|---|---|
| Pen test, any class, mAP50 | 0.067 | 0.772 |
| Pen test recall | 0.29 | 0.68 |
| Pen test precision | 0.11 | 0.85 |
| Boxes per real pen tile with nothing pasted, conf 0.25 | 3.55 | 0.06 |
| Close-up test mAP50 (4 classes) | 0.873 | 0.789 |

The pen test uses test split droppings pasted onto held out cameras, so it measures finding a dropping of pen size on unseen litter.
It is synthetic. No real droppings in these videos are labelled, so field accuracy is not measured yet.
Disease class at pen size is weak (pen test 4 class mAP50 0.52). Use the pen model to find droppings and the close-up model to judge them.
Close-up accuracy dropped by 0.08, so keep dropping4-laptop for close-up photos.
