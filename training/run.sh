#!/usr/bin/env bash
# Veri entrypoint: bash run.sh smoke | full
set -euo pipefail
MODE="${1:-smoke}"
WORK="${WORK_DIR:-$PWD/work}"
cd "$(dirname "$0")"

# The CUDA base image has no libGL, so the GUI build of OpenCV that ultralytics pulls in cannot import.
if ! python -c "import cv2" 2>/dev/null; then
  pip_cmd="python -m pip"; $pip_cmd --version >/dev/null 2>&1 || pip_cmd="uv pip"
  $pip_cmd uninstall -y opencv-python opencv-python-headless || true
  $pip_cmd install opencv-python-headless
fi
nvidia-smi || true
df -h "$PWD" || true

if [ "$MODE" = "smoke" ]; then
  python prepare_data.py --out "$WORK" --mode smoke --per-class 40
  python train.py --data "$WORK/yolo/data.yaml" --pcr "$WORK/pcr" --epochs 2 --imgsz 320 --batch 16 --export-sizes 320
else
  python prepare_data.py --out "$WORK" --mode full
  python train.py --data "$WORK/yolo/data.yaml" --pcr "$WORK/pcr" --hours "${HOURS:-2}"
fi
