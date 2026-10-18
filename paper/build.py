"""Join the paper into one LaTeX file and, if a compiler is given, build the PDF.

    python paper/build.py                          writes paper/holy-crap-paper.tex
    python paper/build.py --tectonic PATH          also builds paper/holy-crap-paper.pdf with Tectonic

The single file inlines every \\input{sections/...} of main.tex, so it can be uploaded to Overleaf or sent to
co-authors as one file next to references.bib and figures/. It also counts the TODO markers still left.
"""
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "holy-crap-paper.tex"


def flatten(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\\input\{([^}]+)\}", lambda m: flatten(HERE / (m.group(1) if m.group(1).endswith(".tex") else m.group(1) + ".tex")), text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tectonic", help="path to the tectonic executable")
    a = ap.parse_args()
    text = flatten(HERE / "main.tex")
    OUT.write_text(text, encoding="utf-8")
    todos = re.findall(r"\\todo\{([^}]*)\}", text)
    print(f"wrote {OUT.name}, {len(text.split())} words, {len(todos)} TODO markers left")
    for t in todos:
        print("  TODO:", t or "(empty)")
    if a.tectonic:
        subprocess.run([a.tectonic, "--keep-logs", OUT.name], cwd=HERE, check=True)
        print("built", OUT.with_suffix(".pdf").name)


if __name__ == "__main__":
    main()
