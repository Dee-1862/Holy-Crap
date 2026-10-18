#!/usr/bin/env bash
# Veri entrypoint for a 4 GPU box: prepare the pen scale data once, then train four variants at the same time,
# one per GPU, and score each the same way. bash run_pen4.sh [hours of training per variant]
set -euo pipefail
cd "$(dirname "$0")"
HOURS="${1:-1.6}"
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
nvidia-smi -L; nproc; free -g; df -h "$PWD"

echo "== data $(date -u +%H:%M)"
python fetch_pen_data.py
python pen_scale.py all --workers "$(nproc)" --pen-train-extra 6000
echo "== training $(date -u +%H:%M), $HOURS h cap per variant"

COMMON="--epochs 200 --patience 20 --hours $HOURS --workers 10 --cache ram"
run() { gpu=$1; name=$2; shift 2
  CUDA_VISIBLE_DEVICES=$gpu python pen_train.py --name "$name" $COMMON "$@" > "$OUT/$name.log" 2>&1 \
    && echo "== $name finished $(date -u +%H:%M)" || echo "== $name FAILED, see $name.log"; }
run 0 nano_main --batch 32 &
run 1 small --start yolo11s.pt --lr0 0.01 --batch 32 &
run 2 nano_960 --imgsz 960 --batch 16 &
run 3 nano_more --data data_more.yaml --batch 32 &

# progress for the job log: the last finished epoch of each run (epoch, val mAP50)
while [ "$(jobs -r | wc -l)" -gt 0 ]; do
  sleep 300
  for n in nano_main small nano_960 nano_more; do
    f="$PEN_WORK/runs/$n/results.csv"
    [ -f "$f" ] && echo "progress $n $(tail -1 "$f" | cut -d, -f1,8 | tr -d ' ')"
  done
done
wait

cp -r "$PEN_WORK/runs" "$OUT/"
for n in nano_main small nano_960 nano_more; do echo "== $n"; cat "$PEN_WORK/runs/$n/eval.json" 2>/dev/null || echo "no eval"; done
