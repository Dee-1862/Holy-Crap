#!/usr/bin/env bash
# Veri entrypoint for the Big Broiler models: bash run_behavior.sh
# Prepares data once, then trains three models in parallel, one per GPU:
#   GPU0 cls_n (YOLO11n-cls behaviour), GPU1 det (YOLO11n chicken detector), GPU2 cls_s (YOLO11s-cls)
set -uo pipefail
JOB_START=$(date +%s)
WORK="${WORK_DIR:-$PWD/work_bb}"
cd "$(dirname "$0")"

if ! python -c "import cv2" 2>/dev/null; then
  pip_cmd="python -m pip"; $pip_cmd --version >/dev/null 2>&1 || pip_cmd="uv pip"
  $pip_cmd uninstall -y opencv-python opencv-python-headless || true
  $pip_cmd install opencv-python-headless
fi
nvidia-smi -L; nproc; free -g | head -2; df -h "$PWD" /dev/shm

NGPU=$(nvidia-smi -L | wc -l)
if [ -n "${DDP_CLS:-}" ]; then
  # Prove multi-GPU works in the sandbox before paying for the 33 GB download.
  timeout 300 torchrun --standalone --nproc_per_node "$NGPU" ddp_check.py || exit 1
fi

if [ -n "${PREPARED:-}" ]; then
  # Prepared dataset uploaded as one tar (Veri volume -> dataset -> $VERI_DATA_DIR); skip the 33 GB video download.
  mkdir -p "$WORK"
  TAR=$(find "${VERI_DATA_DIR:-/workspace/data}" -name '*.tar' | head -1)
  echo "extracting $TAR"; tar -xf "$TAR" -C "$WORK" || exit 1
  printf 'path: %s\ntrain: images/train\nval: images/val\ntest: images/test\nnames: {0: chicken}\n' "$WORK/chickens" > "$WORK/chickens/data.yaml"
  find "$WORK/behaviour" -maxdepth 2 -type d | head -20
else
  python prepare_behavior.py --out "$WORK" --workers "${PREP_WORKERS:-32}" || exit 1
fi

HOURS=$(python -c "import time; left=(${BUDGET_MIN:-110}*60 - (time.time()-$JOB_START) - 600)/3600; print(round(max(left, 1/4), 3))")
echo "training time cap: $HOURS h"

if [ -n "${DDP_CLS:-}" ]; then
  # Only the Pi behaviour classifier, on every GPU at once.
  python train_behavior.py --task cls --data "$WORK/behaviour" --name cls_n_ddp --model yolo11n-cls.pt \
    --gpus "$NGPU" --batch 128 --hours "$HOURS" --workers 10 2>&1 \
    | tee cls_n_ddp.log | grep --line-buffered -E '^metrics|SUMMARY|export|Traceback|Error|epochs completed'
  rc=${PIPESTATUS[0]}
  cp cls_n_ddp.log "$WORK/stats_behaviour.json" "${VERI_OUTPUT_DIR:-.}/" 2>/dev/null
  exit $rc
fi

CUDA_VISIBLE_DEVICES=0 python train_behavior.py --task cls --data "$WORK/behaviour" --name cls_n \
  --model yolo11n-cls.pt --hours "$HOURS" --workers 14 > cls_n.log 2>&1 &
P1=$!
CUDA_VISIBLE_DEVICES=$((1 % NGPU)) python train_behavior.py --task det --data "$WORK/chickens/data.yaml" --name det \
  --model yolo11n.pt --hours "$HOURS" --workers 14 > det.log 2>&1 &
P2=$!
P3=""
if [ "$NGPU" -ge 3 ]; then
  CUDA_VISIBLE_DEVICES=2 python train_behavior.py --task cls --data "$WORK/behaviour" --name cls_s \
    --model yolo11s-cls.pt --hours "$HOURS" --workers 14 > cls_s.log 2>&1 &
  P3=$!
fi
# Stream progress lines from all three logs into the job log.
tail -n +1 -F cls_n.log det.log ${P3:+cls_s.log} 2>/dev/null | grep --line-buffered -E '^metrics|SUMMARY|export|Traceback|Error|epochs completed' &
TAILPID=$!

rc=0
for p in $P1 $P2 $P3; do wait "$p" || rc=1; done
sleep 2; kill $TAILPID 2>/dev/null
for f in cls_n.log det.log cls_s.log; do [ -f "$f" ] && cp "$f" "${VERI_OUTPUT_DIR:-.}/" ; done
cp "$WORK/stats_behaviour.json" "${VERI_OUTPUT_DIR:-.}/" 2>/dev/null
exit $rc
