"""Model evaluation figures for the Holy-Crap detector, from files already in the repository.

    python evaluation.py          write every figure (PNG, SVG and PDF) and its table (CSV) to figures/

Inputs, all committed:
    results/farm_test_predictions.csv   the 679 held-out farm test photos, scored by audit_images.py
    results/pcr_predictions.csv         1,255 lab-confirmed (PCR) photos from a separate Zenodo record, never trained on
    results/farm_hashes.csv             a 256-bit difference hash of every farm photo, for the duplicate check
    models/*/results.csv                per-epoch training logs
    models/dropping4-pen/before_after.json
    app/console/public/demo-media/analysis/test-a1.json   the live test clip and its answer key

How a photo is scored: the detector is run on the whole photo and each class keeps its best box confidence. The
photo's prediction is the class with the highest score, or "no detection" when no box reaches CONF. That is the
same confidence cut the live feed uses. Proportions carry 95% Wilson intervals.

Chart method: the bundled dataviz skill. Class hues are the validated categorical slots 1 to 4 in fixed order (hc_viz).
The two photo sets take slots 7 and 5 (violet, magenta), validated as a pair: CVD and normal-vision separation pass,
magenta is under 3:1 contrast on the surface, so every mark of it carries a direct label and every figure has a table.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import hc_viz as hv

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RESULTS, FIGURES = HERE / "results", HERE / "figures"
CONF = 0.25
MODEL_ORDER = ["cocci", "healthy", "ncd", "salmo"]          # the model's output order
ORDER = hv.CLASS_ORDER                                       # display order
NONE = "none"
SET_COLOR = {"farm": "#6250d6", "pcr": "#e87ba4"}            # dataviz slots 7 and 5
SET_LABEL = {"farm": "Farm test photos (held out)", "pcr": "Lab-confirmed photos (PCR, new collection)"}
SEQ = ["#fcfcfb", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]   # dataviz blue ramp


# ---------------------------------------------------------------- statistics
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Proportion with its 95% Wilson score interval. Behaves at 0 and 1, unlike the normal approximation."""
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def scored(name: str) -> pd.DataFrame:
    """Predictions with the photo-level call, its confidence and whether it was right."""
    df = pd.read_csv(RESULTS / f"{name}.csv")
    s = df[[f"max_{c}" for c in MODEL_ORDER]].to_numpy()
    best = s.max(1)
    df["conf"] = best
    df["pred"] = np.where(best >= CONF, np.array(MODEL_ORDER)[s.argmax(1)], NONE)
    df["top"] = np.array(MODEL_ORDER)[s.argmax(1)]          # the call with no confidence cut, for coverage curves
    df["correct"] = df.pred == df.true
    return df


def nearest_train_distance() -> pd.DataFrame:
    """For each farm test photo, the Hamming distance (of 256 bits) to the closest training photo's hash."""
    h = pd.read_csv(RESULTS / "farm_hashes.csv")
    bits = np.stack([np.unpackbits(np.frombuffer(bytes.fromhex(x), np.uint8)) for x in h.dhash]).astype(bool)
    train = bits[h.split.to_numpy() == "train"]
    test = h[h.split == "test"].copy()
    test["nearest"] = [int((train != b).sum(1).min()) for b in bits[h.split.to_numpy() == "test"]]
    return test[["member", "cls", "nearest"]]


# ---------------------------------------------------------------- figure helpers
def save(fig, name: str, table: pd.DataFrame | None = None) -> None:
    FIGURES.mkdir(exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(FIGURES / f"{name}.{ext}", bbox_inches="tight", dpi=200 if ext == "png" else None)
    if table is not None:
        table.to_csv(FIGURES / f"{name}.csv", index=table.index.name is not None)
    plt.close(fig)


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def cell_ink(v: float) -> str:
    return hv.INK if v < 0.55 else "#ffffff"                 # dark text on the light half of the ramp, white on the dark


# ---------------------------------------------------------------- 05 training curves
def fig_training() -> pd.DataFrame:
    runs = {"Close-up model (dropping4-laptop)": REPO / "models/dropping4-laptop/results.csv",
            "Pen-scale model (dropping4-pen)": REPO / "models/dropping4-pen/results.csv"}
    fig, axes = plt.subplots(2, 2, figsize=(10.4, 6.4), gridspec_kw={"hspace": 0.55, "wspace": 0.18})
    rows = []
    for r, (title, path) in enumerate(runs.items()):
        d = pd.read_csv(path)
        d.columns = [c.strip() for c in d.columns]
        tr = d["train/box_loss"] + d["train/cls_loss"] + d["train/dfl_loss"]
        va = d["val/box_loss"] + d["val/cls_loss"] + d["val/dfl_loss"]
        m = d["metrics/mAP50-95(B)"]
        best = int(d.epoch[m.idxmax()])
        low = int(d.epoch[va.idxmin()])
        rows.append({"run": title, "epochs": int(d.epoch.max()), "best epoch (val mAP50-95)": best,
                     "best val mAP50-95": round(float(m.max()), 3), "lowest val loss epoch": low,
                     "val loss at end vs lowest": round(float(va.iloc[-1] - va.min()), 3),
                     "train loss at end vs lowest": round(float(tr.iloc[-1] - tr.min()), 3)})
        a = axes[r, 0]
        a.plot(d.epoch, tr, color=hv.GRAY_MID, lw=2, ls=(0, (4, 2)))
        a.plot(d.epoch, va, color=SET_COLOR["farm"], lw=2)
        a.text(d.epoch.iloc[-1] + 0.6, tr.iloc[-1], "train", color=hv.INK2, va="center", fontsize=9)
        a.text(d.epoch.iloc[-1] + 0.6, va.iloc[-1], "validation", color=hv.INK, va="center", fontsize=9)
        a.axvline(low, color=hv.GRAY_LIGHT, lw=1, ls=(0, (2, 2)), zorder=0)
        a.text(low - 0.8, a.get_ylim()[1], f"lowest val loss, epoch {low} ", color=hv.INK2, fontsize=8.5, va="top", ha="right")
        a.set_title(f"{title}\nLoss (box + class + distribution), lower is better", fontsize=10.5)
        b = axes[r, 1]
        b.plot(d.epoch, m, color=SET_COLOR["farm"], lw=2)
        b.scatter([best], [m.max()], s=40, color=SET_COLOR["farm"], edgecolor=hv.SURFACE, linewidth=2, zorder=3)
        b.annotate(f"best {m.max():.3f} at epoch {best}", (best, m.max()), xytext=(0, -40), textcoords="offset points",
                   fontsize=9, color=hv.INK, ha="center", arrowprops={"arrowstyle": "-", "color": hv.GRAY_MID, "lw": 0.8})
        b.set_title("Validation mAP50-95, higher is better", fontsize=10.5)
        for ax in (a, b):
            ax.set_xlabel("epoch")
            ax.grid(axis="y")
            ax.spines["left"].set_visible(False)
            ax.tick_params(length=0)
            ax.set_xlim(0, d.epoch.max() * 1.12)
    hv.headline(fig, "Training curves, measured from each run's results.csv",
                "Dashed gray is training loss, violet is validation. The step in the pen run's training loss near epoch 30 is where\n"
                "mosaic augmentation switches off for the last epochs, so it is not a sign of learning the training set.", y=1.08)
    t = pd.DataFrame(rows).set_index("run")
    save(fig, "05_training_curves", t)
    return t


# ---------------------------------------------------------------- 06 confusion matrices
def fig_confusion(farm: pd.DataFrame, pcr: pd.DataFrame) -> pd.DataFrame:
    cols = ORDER + [NONE]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4), gridspec_kw={"wspace": 0.42})
    out = []
    for ax, (key, df) in zip(axes, (("farm", farm), ("pcr", pcr))):
        cm = pd.crosstab(df.true, df.pred).reindex(index=ORDER, columns=cols, fill_value=0)
        share = cm.div(cm.sum(1), axis=0)
        from matplotlib.colors import LinearSegmentedColormap
        cmap = LinearSegmentedColormap.from_list("seq", SEQ)
        ax.imshow(share.to_numpy(), cmap=cmap, vmin=0, vmax=1, aspect="auto")
        for i in range(len(ORDER)):
            for j in range(len(cols)):
                v, n = share.iat[i, j], cm.iat[i, j]
                ax.text(j, i - 0.12, f"{100 * v:.0f}%", ha="center", va="center", color=cell_ink(v), fontsize=10, fontweight="bold" if i == j else "normal")
                ax.text(j, i + 0.22, f"{n}", ha="center", va="center", color=cell_ink(v), fontsize=8)
        ax.set_xticks(range(len(cols)), [hv.CLASS_LABEL.get(c, "No detection").replace("-like", "") for c in cols], rotation=30, ha="right", rotation_mode="anchor", fontsize=9)
        ax.set_yticks(range(len(ORDER)), [hv.CLASS_LABEL[c] for c in ORDER], fontsize=9.5)
        ax.set_xticks(np.arange(-0.5, len(cols)), minor=True)
        ax.set_yticks(np.arange(-0.5, len(ORDER)), minor=True)
        ax.grid(which="minor", color=hv.SURFACE, lw=2)
        ax.tick_params(which="both", length=0)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.set_xlabel("predicted", color=hv.INK2)
        ax.set_ylabel("true class", color=hv.INK2)
        acc = wilson(int(df.correct.sum()), len(df))
        ax.set_title(f"{SET_LABEL[key]}\n{len(df):,} photos, {pct(acc[0])} correct (95% CI {pct(acc[1])} to {pct(acc[2])})", fontsize=10.5)
        long = cm.stack().rename("photos").reset_index().rename(columns={"level_1": "pred", "col_0": "pred"})
        long.insert(0, "set", key)
        out.append(long)
    hv.headline(fig, "Where the photo-level calls go", "Each row sums to 100% of that true class. Bold is the share called correctly.", y=1.1)
    t = pd.concat(out, ignore_index=True)
    save(fig, "06_confusion_matrices", t)
    return t


# ---------------------------------------------------------------- 07 recall with intervals
def fig_recall(farm: pd.DataFrame, pcr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, df in (("farm", farm), ("pcr", pcr)):
        for c in ORDER + ["all"]:
            sub = df if c == "all" else df[df.true == c]
            p, lo, hi = wilson(int(sub.correct.sum()), len(sub))
            rows.append({"set": key, "class": c, "photos": len(sub), "correct": int(sub.correct.sum()), "recall": p, "ci_low": lo, "ci_high": hi})
    t = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(9.6, 4.2))
    labels = [hv.CLASS_LABEL[c] for c in ORDER] + ["All photos"]
    for k, key in enumerate(("farm", "pcr")):
        sub = t[t.set == key]
        y = np.arange(len(labels)) + (-0.17 if k == 0 else 0.17)
        ax.hlines(y, sub.ci_low, sub.ci_high, color=SET_COLOR[key], lw=2)
        ax.scatter(sub.recall, y, s=52, color=SET_COLOR[key], edgecolor=hv.SURFACE, linewidth=2, zorder=3, label=SET_LABEL[key], clip_on=False)
        for yy, (_, r) in zip(y, sub.iterrows()):
            ax.text(1.015, yy, f"{pct(r.recall)}  ({r.correct}/{r.photos})", va="center", fontsize=8.8, color=hv.INK, transform=ax.get_yaxis_transform())
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.axhline(len(ORDER) - 0.5, color=hv.GRID, lw=1)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(lambda v, _: f"{100 * v:.0f}%")
    ax.grid(axis="x")
    ax.tick_params(length=0)
    ax.set_xlabel("share of photos of that class called correctly (recall), with 95% Wilson interval")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=9, handletextpad=0.3, columnspacing=1.4)
    hv.headline(fig, "The held-out farm test overstates how the model does on new photos",
                f"Same model, same rules (best box at least {CONF:.2f}). The lab-confirmed photos come from a separate collection.", y=1.13)
    save(fig, "07_recall_by_class", t.round(4))
    return t


# ---------------------------------------------------------------- 08 accuracy against coverage
def coverage_curve(df: pd.DataFrame) -> pd.DataFrame:
    """Answer only when the best box clears a threshold: how many photos get an answer and how many answers are right."""
    order = df.sort_values("conf", ascending=False)
    right = (order.top == order.true).to_numpy().cumsum()
    n = np.arange(1, len(order) + 1)
    return pd.DataFrame({"threshold": order.conf.to_numpy(), "coverage": n / len(order), "accuracy": right / n})


def fig_coverage(farm: pd.DataFrame, pcr: pd.DataFrame) -> pd.DataFrame:
    fig, ax = plt.subplots(figsize=(8.8, 4.4))
    rows = []
    for key, df in (("farm", farm), ("pcr", pcr)):
        cv = coverage_curve(df)
        ax.plot(cv.coverage, cv.accuracy, color=SET_COLOR[key], lw=2, label=SET_LABEL[key])
        for th in (0.25, 0.5, 0.8):
            k = cv[cv.threshold >= th]
            if len(k):
                r = k.iloc[-1]
                rows.append({"set": key, "threshold": th, "answered": round(float(r.coverage), 4), "accuracy of answers": round(float(r.accuracy), 4)})
                ax.scatter([r.coverage], [r.accuracy], s=46, color=SET_COLOR[key], edgecolor=hv.SURFACE, linewidth=2, zorder=3)
                ax.annotate(f"{th:.2f}", (r.coverage, r.accuracy), xytext=(-6, -14) if key == "farm" else (5, -13), ha="right" if key == "farm" else "left", textcoords="offset points", fontsize=8.5, color=hv.INK2)
        ax.text(1.01, cv.accuracy.iloc[-1], f"{pct(cv.accuracy.iloc[-1])} if it always answers", va="center", fontsize=8.8, color=hv.INK)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0.5, 1.005)
    for axis in (ax.xaxis, ax.yaxis):
        axis.set_major_formatter(lambda v, _: f"{100 * v:.0f}%")
    ax.grid(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    ax.set_xlabel("share of photos the model answers (it stays silent below the confidence threshold)")
    ax.set_ylabel("share of its answers that are right")
    ax.legend(loc="lower left", fontsize=9)
    hv.headline(fig, "Answering less often makes the answers more reliable, but not enough on new photos",
                "Dots mark confidence thresholds 0.25, 0.50 and 0.80. Moving left means a higher threshold.", y=1.1)
    t = pd.DataFrame(rows)
    save(fig, "08_accuracy_vs_coverage", t)
    return t


# ---------------------------------------------------------------- 09 calibration
def fig_calibration(farm: pd.DataFrame, pcr: pd.DataFrame, bins: int = 10) -> pd.DataFrame:
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.4), sharey=True, gridspec_kw={"wspace": 0.12})
    rows = []
    for ax, (key, df) in zip(axes, (("farm", farm), ("pcr", pcr))):
        edges = np.linspace(0, 1, bins + 1)
        idx = np.clip(np.digitize(df.conf, edges) - 1, 0, bins - 1)
        right = (df.top == df.true).to_numpy()
        ece = 0.0
        for b in range(bins):
            m = idx == b
            if not m.any():
                continue
            conf, acc = float(df.conf[m].mean()), float(right[m].mean())
            ece += m.mean() * abs(acc - conf)
            rows.append({"set": key, "bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}", "photos": int(m.sum()), "mean confidence": round(conf, 3), "accuracy": round(acc, 3)})
        t = pd.DataFrame([r for r in rows if r["set"] == key])
        ax.plot([0, 1], [0, 1], color=hv.GRAY_LIGHT, lw=1.2, ls=(0, (3, 2)))
        ax.text(0.62, 0.55, "confidence = share right", rotation=45, rotation_mode="anchor", ha="center", fontsize=8.5, color=hv.INK2,
                transform_rotates_text=True)
        few = t[t.photos < 10]
        for _, rr in few.iterrows():
            ax.annotate(f"{rr.photos} photo{'s' if rr.photos > 1 else ''}", (rr["mean confidence"], rr.accuracy), xytext=(0, 9),
                        textcoords="offset points", ha="center", fontsize=7.5, color=hv.INK2)
        ax.plot(t["mean confidence"], t.accuracy, color=SET_COLOR[key], lw=2)
        ax.scatter(t["mean confidence"], t.accuracy, s=np.clip(t.photos, 8, 400) * 0.6 + 14, color=SET_COLOR[key], edgecolor=hv.SURFACE, linewidth=2, zorder=3)
        ax.set_title(f"{SET_LABEL[key]}\nexpected calibration error {ece:.3f}", fontsize=10.5)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1.03)
        ax.grid(True)
        ax.spines["left"].set_visible(False)
        ax.tick_params(length=0)
        ax.set_xlabel("model confidence (best box)")
        rows.append({"set": key, "bin": "ECE", "photos": len(df), "mean confidence": None, "accuracy": round(ece, 4)})
    axes[0].set_ylabel("share right")
    hv.headline(fig, "The box score is not a probability: the model is right more often than its score says",
                "Photos grouped into ten score bins, dot size shows how many photos each holds. Bins with under 10 photos are labelled\n"
                "and should not be read. The score ranks photos well (fig. 8) but needs calibrating before it is shown as a percentage.", y=1.13)
    t = pd.DataFrame(rows)
    save(fig, "09_calibration", t)
    return t


# ---------------------------------------------------------------- 10 duplicates across the split
def fig_duplicates(farm: pd.DataFrame) -> pd.DataFrame:
    near = nearest_train_distance()
    j = farm.merge(near[["member", "nearest"]], on="member", how="left")
    dup = j.nearest == 0
    fig, ax = plt.subplots(figsize=(9.0, 3.8))
    edges = np.arange(0, 132, 4)
    counts, _ = np.histogram(near.nearest, bins=edges)
    colors = [SET_COLOR["pcr"] if lo == 0 else SET_COLOR["farm"] for lo in edges[:-1]]
    ax.bar(edges[:-1], counts, width=4, align="edge", color=colors, edgecolor=hv.SURFACE, linewidth=2)
    ax.annotate(f"{int(dup.sum())} test photos ({pct(dup.mean())})\nare exact copies of a training photo",
                (2, counts[0]), xytext=(18, -4), textcoords="offset points", fontsize=9, color=hv.INK, va="top")
    ax.set_xlabel("bits that differ from the closest training photo (of 256), 0 means the same picture")
    ax.set_ylabel("test photos")
    ax.grid(axis="y")
    ax.spines["left"].set_visible(False)
    ax.tick_params(length=0)
    a_all = wilson(int(j.correct.sum()), len(j))
    a_clean = wilson(int(j.correct[~dup].sum()), int((~dup).sum()))
    hv.headline(fig, "Some test photos are also in training, but they do not explain the farm score",
                f"All {len(j)} test photos: {pct(a_all[0])} correct. Without the {int(dup.sum())} copies: {pct(a_clean[0])} "
                f"(95% CI {pct(a_clean[1])} to {pct(a_clean[2])}).", y=1.12)
    t = pd.DataFrame([
        {"test photos": "all", "photos": len(j), "correct": int(j.correct.sum()), "accuracy": round(a_all[0], 4), "ci_low": round(a_all[1], 4), "ci_high": round(a_all[2], 4)},
        {"test photos": "exact copies of a training photo", "photos": int(dup.sum()), "correct": int(j.correct[dup].sum()), "accuracy": round(float(j.correct[dup].mean()), 4), "ci_low": None, "ci_high": None},
        {"test photos": "without the copies", "photos": int((~dup).sum()), "correct": int(j.correct[~dup].sum()), "accuracy": round(a_clean[0], 4), "ci_low": round(a_clean[1], 4), "ci_high": round(a_clean[2], 4)},
    ]).set_index("test photos")
    dups_by_class = near[near.nearest == 0].cls.value_counts().reindex(ORDER, fill_value=0)
    t.attrs["by_class"] = dups_by_class
    save(fig, "10_duplicates_across_split", t)
    return t


# ---------------------------------------------------------------- 11 pen-scale fine-tune
def fig_pen() -> pd.DataFrame:
    ba = json.loads((REPO / "models/dropping4-pen/before_after.json").read_text())
    before, after = ba[0], ba[1]
    metrics = [("pen_test_recall_any_class", "Pen scale: droppings found (recall)"),
               ("pen_test_precision_any_class", "Pen scale: flags that are droppings (precision)"),
               ("pen_test_map50_any_class", "Pen scale: mAP50, any class"),
               ("pen_test_map50_4class", "Pen scale: mAP50, right class"),
               ("closeup_test_map50", "Close-up photos: mAP50")]
    fig, ax = plt.subplots(figsize=(9.4, 3.6))
    for i, (k, label) in enumerate(metrics):
        b, a = before[k], after[k]
        ax.plot([b, a], [i, i], color=hv.GRAY_LIGHT, lw=2, zorder=1)
        ax.scatter([b], [i], s=52, facecolor=hv.SURFACE, edgecolor=hv.GRAY_MID, linewidth=2, zorder=3)
        ax.scatter([a], [i], s=52, color=SET_COLOR["farm"], edgecolor=hv.SURFACE, linewidth=2, zorder=3)
        ax.text(1.02, i, f"{b:.3f} → {a:.3f}", va="center", fontsize=9, color=hv.INK, transform=ax.get_yaxis_transform())
    ax.set_yticks(range(len(metrics)), [m[1] for m in metrics])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.grid(axis="x")
    ax.tick_params(length=0)
    ax.scatter([], [], s=52, facecolor=hv.SURFACE, edgecolor=hv.GRAY_MID, linewidth=2, label="close-up model, before")
    ax.scatter([], [], s=52, color=SET_COLOR["farm"], label="pen-scale fine-tune, after")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=9)
    fig.subplots_adjust(left=0.3)
    hv.headline(fig, "Fine-tuning on pen-scale views fixes small droppings without losing close-ups",
                "Pen test split by camera, so no camera is in both training and test.", y=1.16)
    t = pd.DataFrame([{"metric": label, "before": before[k], "after": after[k]} for k, label in metrics]).set_index("metric")
    save(fig, "11_pen_scale_before_after", t)
    return t


# ---------------------------------------------------------------- 12 live test clip
def fig_live_clip() -> pd.DataFrame:
    d = json.loads((REPO / "app/console/public/demo-media/analysis/test-a1.json").read_text())
    truth = sorted(d["truth"], key=lambda x: x["t"])
    spots = d.get("spots", [])
    false = [s for s in spots if not s.get("truth")]
    fig, ax = plt.subplots(figsize=(9.6, 3.9))
    rows = []
    for i, t in enumerate(truth):
        col = hv.CLASS_COLOR[t["cls"]]
        ax.scatter([t["t"]], [i], s=40, facecolor=hv.SURFACE, edgecolor=col, linewidth=2, zorder=3)
        if t["foundAt"] is not None:
            ax.plot([t["t"], t["foundAt"]], [i, i], color=col, lw=2)
            ax.scatter([t["foundAt"]], [i], s=40, color=col, edgecolor=hv.SURFACE, linewidth=2, zorder=3)
            ax.text(t["foundAt"] + 2, i, f"found after {t['foundAt'] - t['t']:.1f} s", va="center", fontsize=8.5, color=hv.INK2)
        else:
            ax.text(t["t"] + 3, i, "missed", va="center", fontsize=8.5, color=hv.INK)
        rows.append({"dropping": i + 1, "class": hv.CLASS_LABEL[t["cls"]], "placed at s": t["t"], "found at s": t["foundAt"],
                     "delay s": round(t["foundAt"] - t["t"], 2) if t["foundAt"] is not None else None})
    ax.set_yticks(range(len(truth)), [f"{i + 1}. {hv.CLASS_LABEL[t['cls']].replace('-like', '')}" for i, t in enumerate(truth)], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, d["duration"])
    ax.set_xlabel("seconds into the clip")
    ax.grid(axis="x")
    ax.tick_params(length=0)
    found = sum(t["foundAt"] is not None for t in truth)
    hv.headline(fig, f"Live test clip: {found} of {len(truth)} placed droppings found, {len(false)} false flags",
                "Hollow dot: a test dropping pasted into the held-out pen video. Filled dot: the pen model flags it.", y=1.12)
    t = pd.DataFrame(rows).set_index("dropping")
    save(fig, "12_live_clip_answer_key", t)
    return t


# ---------------------------------------------------------------- 13 benchmark against earlier classifiers
BENCH_LABEL = {"mobilenet_v2": "MobileNetV2 (Machuve et al.)", "efficientnet_b0": "EfficientNet-B0 (Dhungana et al.)",
               "resnet50": "ResNet-50 (reference)", "yolo11n_top": "YOLO11n detector (ours), always answers",
               "yolo11n": "YOLO11n detector (ours), 0.25 cut"}


def macro_f1(true: np.ndarray, pred: np.ndarray) -> float:
    f = []
    for c in MODEL_ORDER:
        tp = int(((pred == c) & (true == c)).sum())
        p = tp / max(1, int((pred == c).sum()))
        r = tp / max(1, int((true == c).sum()))
        f.append(0.0 if p + r == 0 else 2 * p * r / (p + r))
    return float(np.mean(f))


def bench_table(farm: pd.DataFrame, pcr: pd.DataFrame) -> pd.DataFrame:
    """One row per model, seed and test set: accuracy with its Wilson interval, macro-F1 and per-class recall.
    Classifiers always answer (the top softmax class). The detector is scored as everywhere else in this file."""
    runs = []
    path = RESULTS / "benchmark_predictions.csv"
    if path.exists():
        b = pd.read_csv(path)
        b["pred"] = np.array(MODEL_ORDER)[b[[f"p_{c}" for c in MODEL_ORDER]].to_numpy().argmax(1)]
        for (model, seed, st), g in b.groupby(["model", "seed", "set"]):
            runs.append((model, seed, "farm" if st == "farm_test" else "pcr", g.true.to_numpy(), g.pred.to_numpy()))
    for key, df in (("farm", farm), ("pcr", pcr)):
        runs.append(("yolo11n", 0, key, df.true.to_numpy(), df.pred.to_numpy()))
        runs.append(("yolo11n_top", 0, key, df.true.to_numpy(), df.top.to_numpy()))     # always answers, like a classifier
    out = []
    for model, seed, st, true, pred in runs:
        acc, lo, hi = wilson(int((true == pred).sum()), len(true))
        r = {"model": model, "seed": seed, "set": st, "photos": len(true), "accuracy": acc, "ci_low": lo, "ci_high": hi,
             "macro_f1": macro_f1(true, pred)}
        for c in MODEL_ORDER:
            r[f"recall_{c}"] = float((pred[true == c] == c).mean())
        out.append(r)
    return pd.DataFrame(out)


def fig_benchmark(farm: pd.DataFrame, pcr: pd.DataFrame) -> pd.DataFrame:
    t = bench_table(farm, pcr)
    summary = t.groupby(["model", "set"]).agg(seeds=("seed", "nunique"), accuracy=("accuracy", "mean"), acc_min=("accuracy", "min"),
                                              acc_max=("accuracy", "max"), macro_f1=("macro_f1", "mean"),
                                              recall_ncd=("recall_ncd", "mean")).reset_index()
    models = [m for m in BENCH_LABEL if m in set(summary.model)]
    fig, ax = plt.subplots(figsize=(9.6, 1.25 * len(models) + 1.2))
    for k, key in enumerate(("farm", "pcr")):
        sub = summary[summary.set == key].set_index("model").reindex(models)
        y = np.arange(len(models)) + (-0.17 if k == 0 else 0.17)
        ax.hlines(y, sub.acc_min, sub.acc_max, color=SET_COLOR[key], lw=6, alpha=0.35)
        ax.scatter(sub.accuracy, y, s=52, color=SET_COLOR[key], edgecolor=hv.SURFACE, linewidth=2, zorder=3,
                   label=SET_LABEL[key], clip_on=False)
        for yy, (_, r) in zip(y, sub.iterrows()):
            spread = f" (seeds {pct(r.acc_min)} to {pct(r.acc_max)})" if r.seeds > 1 else " (one run)"
            ax.text(1.015, yy, f"{pct(r.accuracy)}{spread}", va="center", fontsize=8.8, color=hv.INK, transform=ax.get_yaxis_transform())
    ax.set_yticks(range(len(models)), [BENCH_LABEL[m] for m in models])
    ax.invert_yaxis()
    ax.set_xlim(0.4, 1)
    ax.xaxis.set_major_formatter(lambda v, _: f"{100 * v:.0f}%")
    ax.grid(axis="x")
    ax.tick_params(length=0)
    ax.set_xlabel("share of photos called correctly. The dot is the mean over seeds, the band the range across seeds")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=9)
    hv.headline(fig, "Every model scores high on the farm test and drops on the lab-confirmed photos",
                "All models trained on the same 5,451 photos and tested on the same photos. The classifiers always answer. "
                "The detector says\nno detection below 0.25, which counts as wrong here.", y=1.0 + 1.1 / fig.get_figheight())
    save(fig, "13_benchmark", t.round(4))
    return summary


def main():
    hv.style()
    farm, pcr = scored("farm_test_predictions"), scored("pcr_predictions")
    for name, fn in [("training", fig_training), ("pen", fig_pen), ("live", fig_live_clip)]:
        print(name, "\n", fn(), "\n")
    print(fig_confusion(farm, pcr).head(), "\n")
    print(fig_recall(farm, pcr).round(3), "\n")
    print(fig_coverage(farm, pcr), "\n")
    print(fig_calibration(farm, pcr), "\n")
    print(fig_duplicates(farm), "\n")
    print(fig_benchmark(farm, pcr), "\n")


if __name__ == "__main__":
    main()
