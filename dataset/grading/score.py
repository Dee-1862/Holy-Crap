"""Check the raters' work, measure agreement and build the released dataset.

    python dataset/grading/score.py --key KEY_DIR [--pilot]

Reads dataset/grading/work/out/<rater>/*.jsonl and KEY_DIR/key.csv and writes dataset/grading/release/
    ratings_raw.csv    every rating from every rater, with the computed grade
    grades.csv         one row per photo: consensus variables (median of raters), grade, coverage, PCR class
    agreement.json     Krippendorff's alpha (ordinal) per variable and for the grade, pairwise quadratic
                       weighted kappa, each rater's agreement with itself on the hidden repeats, and grade by
                       PCR class as a validity check
With --pilot it only prints the numbers and writes nothing.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
from pathlib import Path

import krippendorff
import numpy as np
from sklearn.metrics import cohen_kappa_score

HERE = Path(__file__).resolve().parent
OUT, RELEASE = HERE / "work" / "out", HERE / "release"
VARS = ["form", "cap", "color", "blood", "mucus", "feed"]
QUALITY = {"good", "partial", "unusable"}


def grade(r: dict) -> int:
    v = {k: (r[k] or 0) for k in VARS}
    return max(1, 10 - (v["form"] + v["cap"] + v["color"] + 2 * v["blood"] + v["mucus"] + v["feed"]))


def coverage(r: dict) -> int:
    return sum(r[k] is not None for k in VARS)


def load(rater_dir: Path) -> dict[str, dict]:
    got = {}
    for f in sorted(rater_dir.glob("*.jsonl")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            r = json.loads(line)
            assert r.get("quality") in QUALITY, f"{f.name}:{n} bad quality"
            for k in VARS:
                assert r.get(k) in (0, 1, 2, None), f"{f.name}:{n} bad {k}"
            if r["quality"] == "unusable":
                r.update({k: None for k in VARS})
            got[r["id"]] = r                                # a re-graded ID keeps its last answer
    return got


def alpha(matrix: list[list]) -> float | None:
    data = np.array([[np.nan if v is None else v for v in row] for row in matrix], dtype=float)
    if np.sum(~np.isnan(data)) < 4 or len(np.unique(data[~np.isnan(data)])) < 2:
        return None
    return round(float(krippendorff.alpha(reliability_data=data, level_of_measurement="ordinal")), 3)


def kappa(a: list, b: list) -> float | None:
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 10 or len({p for pair in pairs for p in pair}) < 2:
        return None
    x, y = zip(*pairs)
    return round(float(cohen_kappa_score(x, y, weights="quadratic")), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True)
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()
    key = {r["id"]: r for r in csv.DictReader(open(Path(args.key) / "key.csv"))}
    raters = {d.name: load(d) for d in sorted(OUT.iterdir()) if d.is_dir()}
    for name, got in raters.items():
        for r in got.values():
            r["grade"] = None if r["quality"] == "unusable" else grade(r)
    ids = sorted(set.intersection(*(set(g) for g in raters.values())))      # photos every rater has graded
    names = list(raters)
    firsts = [i for i in ids if not key[i]["repeat_of"]]
    print(f"raters {names}, {len(ids)} images graded by all, {len(firsts)} distinct photos")

    report = {"raters": names, "images": len(firsts), "alpha": {}, "kappa": {}, "self": {}, "by_class": {}}
    for v in VARS + ["grade"]:
        report["alpha"][v] = alpha([[raters[n][i][v] for i in firsts] for n in names])
        report["kappa"][v] = {f"{a}~{b}": kappa([raters[a][i][v] for i in firsts], [raters[b][i][v] for i in firsts])
                              for a, b in itertools.combinations(names, 2)}
    reps = [(i, key[i]["repeat_of"]) for i in ids if key[i]["repeat_of"] and key[i]["repeat_of"] in raters[names[0]]]
    for n in names:                                         # same rater, same photo, different ID
        a = [raters[n][orig]["grade"] for i, orig in reps if orig in raters[n]]
        b = [raters[n][i]["grade"] for i, orig in reps if orig in raters[n]]
        exact = sum(x == y for x, y in zip(a, b)) / len(a) if a else None
        report["self"][n] = {"pairs": len(a), "kappa_grade": kappa(a, b), "exact_grade": None if exact is None else round(exact, 3)}

    consensus = []
    for i in firsts:
        rs = [raters[n][i] for n in names]
        row = {"id": i, "pcr_class": key[i]["pcr_class"], "source_zip": key[i]["zip"], "source_member": key[i]["member"],
               "source_md5": key[i]["md5"], "quality": statistics.mode(r["quality"] for r in rs)}
        for v in VARS:
            vals = [r[v] for r in rs if r[v] is not None]
            row[v] = None if len(vals) < 2 else int(statistics.median_low(vals))   # needs two raters who could see it
        row["grade"] = None if row["quality"] == "unusable" else grade(row)
        row["coverage"] = coverage(row)
        row["grade_spread"] = (lambda g: max(g) - min(g) if g else None)([r["grade"] for r in rs if r["grade"] is not None])
        consensus.append(row)
    for cls in sorted({r["pcr_class"] for r in consensus}):
        g = [r["grade"] for r in consensus if r["pcr_class"] == cls and r["grade"] is not None]
        report["by_class"][cls] = {"n": len(g), "mean_grade": round(statistics.mean(g), 2) if g else None,
                                   "median_grade": statistics.median(g) if g else None}
    print(json.dumps(report, indent=1))
    if args.pilot:
        return

    RELEASE.mkdir(exist_ok=True)
    with open(RELEASE / "ratings_raw.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "rater", "quality", *VARS, "grade", "note", "is_repeat_of"])
        for n in names:
            for i in ids:
                r = raters[n][i]
                w.writerow([i, n, r["quality"], *[r[v] for v in VARS], r["grade"], r.get("note", ""), key[i]["repeat_of"]])
    with open(RELEASE / "grades.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(consensus[0]))
        w.writeheader()
        w.writerows(consensus)
    (RELEASE / "agreement.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"wrote {RELEASE}")


if __name__ == "__main__":
    main()
