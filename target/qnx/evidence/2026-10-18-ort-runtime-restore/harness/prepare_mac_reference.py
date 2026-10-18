#!/usr/bin/env python3
"""Create one reproducible real-specimen tensor and ONNX Runtime reference."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def letterbox(rgb: np.ndarray, side: int = 320) -> np.ndarray:
    height, width = rgb.shape[:2]
    scale = min(side / width, side / height)
    new_width, new_height = round(width * scale), round(height * scale)
    ys = (np.arange(new_height) + 0.5) / scale - 0.5
    xs = (np.arange(new_width) + 0.5) / scale - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, height - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None, None]
    x0 = np.clip(np.floor(xs).astype(int), 0, width - 1)
    x1 = np.clip(x0 + 1, 0, width - 1)
    fx = np.clip(xs - x0, 0, 1)[None, :, None]
    image = rgb.astype(np.float32)
    top = image[y0][:, x0] * (1 - fx) + image[y0][:, x1] * fx
    bottom = image[y1][:, x0] * (1 - fx) + image[y1][:, x1] * fx
    resized = top * (1 - fy) + bottom * fy
    canvas = np.full((side, side, 3), 114, np.float32)
    x_pad, y_pad = (side - new_width) // 2, (side - new_height) // 2
    canvas[y_pad : y_pad + new_height, x_pad : x_pad + new_width] = resized
    return np.ascontiguousarray((canvas / 255.0).transpose(2, 0, 1)[None], np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tensor = letterbox(np.asarray(Image.open(args.image).convert("RGB")))
    input_path = args.output_dir / "smoke-input-f32.bin"
    output_path = args.output_dir / "mac-output-f32.bin"
    tensor.tofile(input_path)

    session = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    session.run(None, {session.get_inputs()[0].name: tensor})
    elapsed_ms: list[float] = []
    output = None
    for _ in range(5):
        started = time.perf_counter_ns()
        output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
        elapsed_ms.append((time.perf_counter_ns() - started) / 1_000_000)
    assert output is not None
    np.ascontiguousarray(output, np.float32).tofile(output_path)

    metadata = {
        "runtime": f"onnxruntime {ort.__version__}",
        "model_sha256": sha256(args.model),
        "image_sha256": sha256(args.image),
        "input_shape": list(tensor.shape),
        "input_sha256": sha256(input_path),
        "output_shape": list(output.shape),
        "output_sha256": sha256(output_path),
        "output_elements": int(output.size),
        "output_min": float(output.min()),
        "output_max": float(output.max()),
        "timings_ms": elapsed_ms,
        "timing_mean_ms": statistics.fmean(elapsed_ms),
    }
    (args.output_dir / "mac-smoke.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
