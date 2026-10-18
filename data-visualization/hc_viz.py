"""Helpers for the data and model audit notebook.

Chart rules follow the dataviz method: one axis, thin marks, a 2 px surface gap between bars, direct
value labels instead of a number on a legend, recessive grid, and a fixed color per class so a class
never changes color between charts. The four class colors were checked with the method's palette
validator (adjacent color blind separation and normal vision floor pass in light mode). In light mode
two of the four sit under 3:1 contrast, so every bar carries a visible value label and every chart has
a data table next to it in the notebook.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e1"
BLUE = "#2a78d6"
GRAY_LIGHT = "#cfcdc6"
GRAY_MID = "#9b998f"

# Fixed order and color for every class in every chart.
CLASS_ORDER = ["healthy", "cocci", "salmo", "ncd"]
CLASS_LABEL = {
    "healthy": "Healthy",
    "cocci": "Coccidiosis-like",
    "salmo": "Salmonella-like",
    "ncd": "Newcastle-like",
}
CLASS_COLOR = {"healthy": "#2a78d6", "cocci": "#eb6834", "salmo": "#1baf7a", "ncd": "#eda100"}

FIGURES = Path(__file__).resolve().parent / "figures"


def style() -> None:
    """Quiet defaults: light surface, dark ink, no top and right spines, faint grid."""
    mpl.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "text.color": INK, "axes.titlecolor": INK, "axes.titlelocation": "left",
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlepad": 12,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.8,
        "font.family": "DejaVu Sans", "font.size": 10, "figure.dpi": 110, "savefig.dpi": 160,
        "legend.frameon": False, "lines.linewidth": 2.0, "lines.solid_capstyle": "round",
    })


def barh(ax, labels, values, colors, fmt="{:,.0f}", xmax=None, label_pad=0.012):
    """Thin horizontal bars with a 2 px surface gap and the value written at the end of each bar."""
    n = len(values)
    top = xmax or max(values) * 1.18
    ax.barh(range(n), values, color=colors, height=0.5, edgecolor=SURFACE, linewidth=2)
    for i, v in enumerate(values):
        ax.text(v + top * label_pad, i, fmt.format(v), va="center", ha="left", color=INK, fontsize=10)
    ax.set_yticks(range(n), labels)
    if not ax.yaxis_inverted():
        ax.invert_yaxis()
    ax.set_xlim(0, top)
    ax.xaxis.set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=10)


def headline(fig, title: str, subtitle: str | None = None, y: float = 0.995) -> None:
    fig.text(0.012, y, title, ha="left", va="top", fontsize=13, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.012, y - 0.065, subtitle, ha="left", va="top", fontsize=9.5, color=INK2)


def savefig(fig, name: str) -> Path:
    FIGURES.mkdir(exist_ok=True)
    path = FIGURES / f"{name}.png"
    fig.savefig(path, bbox_inches="tight")
    return path


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_json(url: str, cache: Path) -> dict:
    """Read a JSON document from the network and keep a copy so the notebook also runs offline."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            data = json.load(r)
        cache.write_text(json.dumps(data, indent=2))
        return data
    except OSError:
        if cache.exists():
            return json.loads(cache.read_text())
        raise


def download_verified(url: str, dest: Path, expected_md5: str) -> Path:
    """Download once, then check the md5 the publisher lists. A wrong hash stops the notebook."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or md5(dest) != expected_md5:
        urllib.request.urlretrieve(url, dest)
    got = md5(dest)
    if got != expected_md5:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"md5 mismatch for {dest.name}: got {got}, publisher lists {expected_md5}")
    return dest
