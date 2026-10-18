#!/usr/bin/env bash
# Veri entrypoint for the pen scale fine-tune: bash run_pen.sh [extra pen_train.py arguments]
# Fetches the data, builds the same camera split as on the laptop, trains, scores, and saves to $VERI_OUTPUT_DIR.
set -euo pipefail
cd "$(dirname "$0")"
OUT="${VERI_OUTPUT_DIR:-$PWD/out}"
export PEN_RAW="$PWD/data/raw" PEN_VIDEOS="$PWD/data/videos" PEN_WORK="$PWD/work/pen"
export PEN_SPLIT_CSV="$PWD/no-csv-rebuild-split" PEN_START="$PWD/start.pt"
mkdir -p "$OUT" "$PEN_RAW" "$PEN_VIDEOS"

# Veri's uploader rejects binary files, so the starting model comes from the public repo, checked by SHA256.
curl -fsSL -o start.pt https://raw.githubusercontent.com/RishitRai/Holy-Crap/main/models/dropping4-laptop/dropping4_yolo11n.pt
echo "0daa534bf909f7873423919cd61864b40537b88e038c57e18f41bfb6de7e7cad  start.pt" | sha256sum -c -

# Same fix as run.sh: the CUDA base image has no libGL for the GUI build of OpenCV.
if ! python -c "import cv2" 2>/dev/null; then
  pip_cmd="python -m pip"; $pip_cmd --version >/dev/null 2>&1 || pip_cmd="uv pip"
  $pip_cmd uninstall -y opencv-python opencv-python-headless || true
  $pip_cmd install opencv-python-headless
fi
command -v bsdtar >/dev/null || (apt-get update -qq && apt-get install -y -qq libarchive-tools) || true
nvidia-smi || true; nproc; free -g || true; df -h "$PWD" || true

python fetch_pen_data.py
python pen_scale.py all --workers "$(nproc)" ${PEN_SCALE_ARGS:-}
python pen_train.py --workers 8 --cache disk "$@" 2>&1 | tee "$OUT/train.log"

cp -r "$PEN_WORK/runs" "$OUT/" || true
cp "$PEN_WORK"/eval.json "$PEN_WORK"/tweaks_*.json "$OUT/" || true
