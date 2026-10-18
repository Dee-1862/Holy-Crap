#!/usr/bin/env bash
# Veri entrypoint: bash run.sh smoke | full
set -euo pipefail
MODE="${1:-smoke}"
JOB_START=$(date +%s)
WORK="${WORK_DIR:-$PWD/work}"
cd "$(dirname "$0")"

# The CUDA base image has no libGL, so the GUI build of OpenCV that ultralytics pulls in cannot import.
if ! python -c "import cv2" 2>/dev/null; then
  pip_cmd="python -m pip"; $pip_cmd --version >/dev/null 2>&1 || pip_cmd="uv pip"
  $pip_cmd uninstall -y opencv-python opencv-python-headless || true
  $pip_cmd install opencv-python-headless
fi
nvidia-smi || true
df -h "$PWD" /dev/shm || true
nproc; free -g || true

# Multi-GPU: NCCL normally talks through /dev/shm (64 MB in Veri's sandbox) and GPU P2P;
# use sockets instead. Prove it works before paying for the download.
NGPU=$(nvidia-smi -L 2>/dev/null | wc -l)
if [ "$NGPU" -gt 1 ] && [ -z "${SINGLE_GPU:-}" ]; then
  export NCCL_SHM_DISABLE=1 NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1
  timeout 300 torchrun --standalone --nproc_per_node "$NGPU" ddp_check.py
fi

if [ "$MODE" = "smoke" ]; then
  python prepare_data.py --out "$WORK" --mode smoke --per-class 40
  python train.py --data "$WORK/yolo/data.yaml" --pcr "$WORK/pcr" --epochs "${EPOCHS:-2}" --imgsz "${IMGSZ:-320}" --batch 16 --export-sizes 320
else
  python prepare_data.py --out "$WORK" --mode full ${PREP_ARGS:-}
  if [ -n "${BUDGET_MIN:-}" ]; then
    # Train for whatever is left of the wall-clock budget, keeping 5 min for eval/export.
    HOURS=$(python -c "import time; left=($BUDGET_MIN*60 - (time.time()-$JOB_START) - 300)/3600; print(round(max(left, 1/6), 3))")
    echo "training time cap: $HOURS h"
  fi
  python train.py --data "$WORK/yolo/data.yaml" --pcr "$WORK/pcr" --hours "${HOURS:-2}" --formats "${FORMATS:-onnx}" --cache "${CACHE:-ram}" ${TRAIN_ARGS:-}
fi
