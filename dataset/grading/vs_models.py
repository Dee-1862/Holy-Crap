"""Do the classifiers fail on PCR positive droppings that look normal?

    python dataset/grading/vs_models.py

Joins dataset/grading/release/grades.csv (appearance grade per PCR photo) with the per photo predictions in
data-visualization/results: pcr_predictions.csv (YOLO11n detector, highest box score per class) and
benchmark_predictions.csv (MobileNetV2, set pcr). A photo is called correct when the top class matches its PCR
class. Writes dataset/grading/release/grade_vs_models.json with accuracy by grade band and PCR class, and the share
of PCR positive photos that look normal (grade 9 or 10).
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "data-visualization" / "results"
TO_KEY = {"coccidiosis": "cocci", "healthy": "healthy", "ncd": "ncd", "salmonella": "salmo"}
BANDS = [("1-5", 1, 5), ("6-8", 6, 8), ("9-10", 9, 10)]


def band(g: int) -> str:
    return next(name for name, lo, hi in BANDS if lo <= g <= hi)


def main():
    grades = {Path(r["source_member"]).name: r for r in csv.DictReader(open(HERE / "release" / "grades.csv")) if r["grade"]}
    models = {}
    det = {}
    for r in csv.DictReader(open(RESULTS / "pcr_predictions.csv")):
        s = {k: float(r[f"max_{k}"]) for k in TO_KEY.values()}
        det[Path(r["member"]).name] = max(s, key=s.get)
    models["yolo11n_detector"] = det
    mob = {}
    for r in csv.DictReader(open(RESULTS / "benchmark_predictions.csv")):
        if r["set"] == "pcr":
            s = {k: float(r[f"p_{k}"]) for k in TO_KEY.values()}
            mob[Path(r["member"]).name] = max(s, key=s.get)
    models["mobilenet_v2"] = mob

    out = {"photos_graded": len(grades), "models": {}, "looks_normal_share": {}}
    by_cls = defaultdict(list)
    for name, r in grades.items():
        by_cls[r["pcr_class"]].append(int(r["grade"]))
    for cls, gs in sorted(by_cls.items()):
        out["looks_normal_share"][cls] = {"n": len(gs), "grade_9_10": round(sum(g >= 9 for g in gs) / len(gs), 3),
                                          "mean_grade": round(sum(gs) / len(gs), 2)}
    for m, pred in models.items():
        cells = defaultdict(lambda: [0, 0])               # (pcr class, band) -> [correct, total]
        for name, r in grades.items():
            if name not in pred:
                continue
            key = (r["pcr_class"], band(int(r["grade"])))
            cells[key][1] += 1
            cells[key][0] += pred[name] == TO_KEY[r["pcr_class"]]
        table = {}
        for cls in sorted(by_cls):
            table[cls] = {b: (None if not cells[(cls, b)][1] else
                              {"n": cells[(cls, b)][1], "accuracy": round(cells[(cls, b)][0] / cells[(cls, b)][1], 3)})
                          for b, _, _ in BANDS}
        sick = [(c, b) for c in by_cls if c != "healthy" for b, _, _ in BANDS]
        def acc(keys):
            c = sum(cells[k][0] for k in keys); n = sum(cells[k][1] for k in keys)
            return None if not n else {"n": n, "accuracy": round(c / n, 3)}
        out["models"][m] = {"by_class_and_band": table,
                            "pcr_positive_looks_abnormal": acc([k for k in sick if k[1] != "9-10"]),
                            "pcr_positive_looks_normal": acc([k for k in sick if k[1] == "9-10"])}
    (HERE / "release" / "grade_vs_models.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
