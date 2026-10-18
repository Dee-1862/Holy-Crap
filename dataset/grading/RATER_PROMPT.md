# Rater instructions (given word for word to each AI rater)

You are one of three independent raters grading photos of single chicken droppings. Other raters grade the
same photos without seeing your answers, and you must not look for theirs.

Read `dataset/grading/RUBRIC.md` first and follow it exactly.

Your batch is the list of IDs below. For each ID, open `dataset/grading/work/images/<ID>.jpg` with the Read
tool, look at it, and score it. Grade every ID in the order given. Do not open any other file in the
repository, and do not look for labels, file names, keys or other raters' work: the photos are blind on
purpose and the study depends on it. Do not run code to analyse the images. Judge them by eye.

Write one JSON object per line to the output file named below, nothing else in the file:

    {"id": "HC-0123", "quality": "good", "form": 0, "cap": 1, "color": 0, "blood": 0, "mucus": null, "feed": 0, "note": "Firm brown dropping, cap thin and smeared"}

- `quality` is `good`, `partial` or `unusable`.
- Each of `form`, `cap`, `color`, `blood`, `mucus`, `feed` is 0, 1, 2 or null (cannot judge from this photo).
- Do not write a grade. It is computed from your scores.
- `note` is at most 120 characters.

Write the file as you go, so nothing is lost if you stop early. When done, reply with only the number of
lines written.
