"""Bounded four-model sparse-frame evaluation harness for the QNX Pi.

Runs four ONNX models through ortlite's `Session` bridge over a caller-supplied
raw RGB24 frame file and writes one deterministic JSON report. This is an
evaluation only: the highest-score YOLO candidate per detector is decoded, not
validated, and nothing in the report is a diagnosis.

Model contracts for this evaluation:
    chicken      input [1,3,640,640]  output [1,5,8400]   detector, one class
    behaviour    input [1,3,224,224]  output [1,7]        7-way classifier
    pen_feces    input [1,3,640,640]  output [1,8,8400]   detector, four classes
    crop_feces   input [1,3,640,640]  output [1,8,8400]   appearance detector, four classes

Requires numpy plus a caller-supplied directory containing ortlite.py
(--ortlite). Reads only the bounded raw RGB24 file, never the source video.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

MIN_SIDE = 1
MAX_SIDE = 8192
MAX_FRAME_COUNT = 4096
MAX_THREADS = 64
MAX_TOTAL_BYTES = 1 << 30
MIN_CROP_PX = 2
HASH_CHUNK = 1 << 20

CONTRACTS = {
    "chicken": {"input": [1, 3, 640, 640], "output": [1, 5, 8400]},
    "behaviour": {"input": [1, 3, 224, 224], "output": [1, 7]},
    "pen_feces": {"input": [1, 3, 640, 640], "output": [1, 8, 8400]},
    "crop_feces": {"input": [1, 3, 640, 640], "output": [1, 8, 8400]},
}

CLASS_ORDER = ["cocci", "healthy", "ncd", "salmo"]
CLASS_ORDER_SOURCE = "target/qnx/edge/infer.py:31 CLASSES"

LIMITATIONS = [
    "sparse_frame_sample: only the supplied raw frames are evaluated, not the whole source clip",
    "top_candidate_not_validated: the single highest-score YOLO candidate per detector is "
    "decoded, not validated, and may be a false positive",
    "no_temporal_association: frames are evaluated independently with no tracking across time",
    "no_full_clip_assessment: no clip-level conclusion is produced",
    "no_diagnosis: recorded class scores are measurements, not diagnoses",
    "no_nms_or_multibox: only the single top candidate per detector is decoded; "
    "no NMS or multi-box evaluation",
    "non_finite_outputs_coerced_to_zero: any non-finite model output is recorded "
    "as 0.0 so the JSON stays finite",
]

METHOD_NOTES = [
    "crop_feces.best_class_scores are per-class maxima over all 8400 candidate "
    "positions of the cropped input",
    "detector boxes are decoded in model space and mapped back to source pixels "
    "with the letterbox scale and padding",
    "pen_feces crop uses zero expansion margin (minimum practical margin); "
    "the crop_feces input is letterboxed to 640x640 regardless",
]


def positive_int(name, lo, hi):
    """argparse type factory for bounded positive integers."""

    def check(value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise argparse.ArgumentTypeError(
                f"{name} must be an integer, got {value!r}"
            ) from None
        if number < lo or number > hi:
            raise argparse.ArgumentTypeError(
                f"{name} must be in {lo}..{hi}, got {value!r}"
            )
        return number

    return check


def parse_args(argv):
    """Parse and bound-check every command line argument."""
    parser = argparse.ArgumentParser(
        prog="four_model_sparse",
        description="Four-model sparse-frame evaluation harness (QNX / ortlite).",
    )
    parser.add_argument(
        "--frames", required=True,
        help="raw RGB24 file: frame_count frames of width*height*3 bytes")
    parser.add_argument(
        "--width", required=True, type=positive_int("--width", MIN_SIDE, MAX_SIDE))
    parser.add_argument(
        "--height", required=True, type=positive_int("--height", MIN_SIDE, MAX_SIDE))
    parser.add_argument(
        "--frame-count", required=True,
        type=positive_int("--frame-count", 1, MAX_FRAME_COUNT))
    parser.add_argument(
        "--chicken-model", required=True,
        help="YOLO detector ONNX, input [1,3,640,640], output [1,5,8400]")
    parser.add_argument(
        "--behaviour-model", required=True,
        help="classifier ONNX, input [1,3,224,224], output [1,7]")
    parser.add_argument(
        "--pen-feces-model", required=True,
        help="YOLO detector ONNX, input [1,3,640,640], output [1,8,8400]")
    parser.add_argument(
        "--crop-feces-model", required=True,
        help="YOLO appearance ONNX, input [1,3,640,640], output [1,8,8400]")
    parser.add_argument("--result", required=True, help="output JSON path")
    parser.add_argument(
        "--threads", default=2, type=positive_int("--threads", 1, MAX_THREADS))
    parser.add_argument("--ortlite", required=True,
                        help="directory containing ortlite.py")
    return parser.parse_args(argv)


def contract_side(contract, name):
    """Square input side of a model contract, validated as [1, 3, side, side]."""
    shape = contract["input"]
    if len(shape) != 4 or shape[0] != 1 or shape[1] != 3 or shape[2] != shape[3]:
        raise ValueError(f"{name}: input contract must be [1, 3, side, side], got {shape}")
    return int(shape[2])


def validate_contracts():
    """Fail early if any built-in model contract is malformed."""
    for name, contract in CONTRACTS.items():
        contract_side(contract, name)
        if not contract["output"] or contract["output"][0] != 1:
            raise ValueError(f"{name}: output contract batch must be 1, got {contract['output']}")


def read_frames(path, width, height, frame_count):
    """Strictly validate the raw RGB24 file and load it as (N, H, W, 3) uint8."""
    path = Path(path)
    expected = width * height * 3 * frame_count
    if expected > MAX_TOTAL_BYTES:
        raise ValueError(
            f"raw frame buffer of {expected} bytes exceeds the {MAX_TOTAL_BYTES} byte cap")
    if not path.is_file():
        raise ValueError(f"frames file not found: {path}")
    actual = os.path.getsize(path)
    if actual != expected:
        raise ValueError(
            f"{path} holds {actual} bytes; expected exactly {expected} "
            f"= {width}x{height}x3x{frame_count}"
        )
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size != expected:
        raise ValueError(f"read {data.size} bytes from {path}, expected {expected}")
    return data.reshape(frame_count, height, width, 3)


def sha256_file(path):
    """Hex SHA-256 of a file, read in bounded chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(HASH_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def import_session(ortlite_dir):
    """Import Session from the caller-supplied ortlite directory."""
    root = Path(ortlite_dir)
    if not root.is_dir() or not (root / "ortlite.py").is_file():
        raise ValueError(
            f"--ortlite must be a directory containing ortlite.py, got {ortlite_dir!r}")
    sys.path.insert(0, str(root))
    try:
        from ortlite import Session
    except Exception as exc:
        raise RuntimeError(f"cannot import Session from {root}: {exc}") from exc
    return Session


def open_session(Session, path, threads):
    """Open one model session once; ONNX Runtime's registry banner is suppressed."""
    devnull, saved = os.open(os.devnull, os.O_WRONLY), os.dup(2)
    os.dup2(devnull, 2)
    try:
        session = Session(str(path), threads=threads)
    finally:
        os.dup2(saved, 2)
        os.close(devnull)
    return session


def load_models(args, Session):
    """Load each model exactly once and record hash, load wall ms and shapes."""
    model_files = {
        "chicken": args.chicken_model,
        "behaviour": args.behaviour_model,
        "pen_feces": args.pen_feces_model,
        "crop_feces": args.crop_feces_model,
    }
    sessions, meta = {}, {}
    for name, model_path in model_files.items():
        path = Path(model_path)
        if not path.is_file() or os.path.getsize(path) == 0:
            raise ValueError(f"{name} model is not a non-empty file: {path}")
        record = {
            "source_path": str(path),
            "source_sha256": sha256_file(path),
            "threads": args.threads,
            "input_shape_expected": list(CONTRACTS[name]["input"]),
            "input_shape_actual": None,
            "output_shape_expected": list(CONTRACTS[name]["output"]),
            "output_shape_actual": None,
            "load_wall_ms": None,
            "calls": [],
            "total_run_wall_ms": None,
            "total_run_cpu_ms": None,
        }
        started = time.perf_counter()
        try:
            sessions[name] = open_session(Session, path, args.threads)
        except Exception as exc:
            raise RuntimeError(f"cannot load {name} model {path}: {exc}") from exc
        record["load_wall_ms"] = r((time.perf_counter() - started) * 1000.0, 6)
        side = contract_side(CONTRACTS[name], name)
        record["input_shape_actual"] = [1, 3, side, side]
        meta[name] = record
    return sessions, meta


def timed_run(session, x):
    """One model call with exact wall and process CPU milliseconds."""
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    out = session.run(x)
    wall_ms = (time.perf_counter() - wall_started) * 1000.0
    cpu_ms = (time.process_time() - cpu_started) * 1000.0
    return out, wall_ms, cpu_ms


def run_checked(session, x, expected_shape, name):
    """Run once and enforce the contract output shape."""
    out, wall_ms, cpu_ms = timed_run(session, x)
    shape = [int(d) for d in np.asarray(out).shape]
    if shape != expected_shape:
        raise RuntimeError(f"{name}: output shape {shape} does not match contract {expected_shape}")
    return out, shape, wall_ms, cpu_ms


def note_call(meta, name, frame_index, wall_ms, cpu_ms, out_shape):
    """Append one per-call timing record and remember the actual output shape."""
    record = meta[name]
    if record["output_shape_actual"] is None:
        record["output_shape_actual"] = out_shape
    record["calls"].append(
        {"frame": frame_index, "wall_ms": r(wall_ms, 6), "cpu_ms": r(cpu_ms, 6)}
    )


def letterbox(rgb, side):
    """Bilinear resize into a square side x side canvas with grey padding.

    Mirrors target/qnx/edge/infer.py letterbox() exactly, except the square
    side is a parameter. Returns (input, scale, pad_x, pad_y).
    """
    h, w = rgb.shape[:2]
    scale = min(side / w, side / h)
    new_w, new_h = round(w * scale), round(h * scale)
    ys = (np.arange(new_h) + 0.5) / scale - 0.5
    xs = (np.arange(new_w) + 0.5) / scale - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, h - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    fy = np.clip(ys - y0, 0, 1)[:, None, None]
    x0 = np.clip(np.floor(xs).astype(int), 0, w - 1)
    x1 = np.clip(x0 + 1, 0, w - 1)
    fx = np.clip(xs - x0, 0, 1)[None, :, None]
    img = rgb.astype(np.float32)
    top = img[y0][:, x0] * (1 - fx) + img[y0][:, x1] * fx
    bottom = img[y1][:, x0] * (1 - fx) + img[y1][:, x1] * fx
    resized = top * (1 - fy) + bottom * fy
    canvas = np.full((side, side, 3), 114, np.float32)
    pad_x, pad_y = (side - new_w) // 2, (side - new_h) // 2
    canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized
    return (canvas / 255.0).transpose(2, 0, 1)[None], scale, pad_x, pad_y


def yolo_matrix(out, name):
    """YOLO output as a (candidates, channels) float32 matrix."""
    pred = np.asarray(out, np.float32)
    if pred.ndim != 3 or pred.shape[0] != 1:
        raise RuntimeError(f"{name}: expected [1, C, N] output, got {list(pred.shape)}")
    return pred[0].T


def clip_box(box, frame_w, frame_h):
    """Clip a decoded box to the source frame."""
    x1, y1, x2, y2 = box
    return [
        min(max(float(x1), 0.0), float(frame_w)),
        min(max(float(y1), 0.0), float(frame_h)),
        min(max(float(x2), 0.0), float(frame_w)),
        min(max(float(y2), 0.0), float(frame_h)),
    ]


def decode_top(matrix, scale, pad_x, pad_y, frame_w, frame_h, name):
    """Decode the single highest-score YOLO candidate to a clipped source box.

    Evaluation only: the candidate is not validated as a real detection.
    """
    channels = matrix.shape[1]
    if channels < 5:
        raise RuntimeError(f"{name}: need at least 5 channels, got {channels}")
    boxes, scores = matrix[:, :4], matrix[:, 4:]
    safe = np.where(np.isfinite(scores), scores, np.float32(-np.inf))
    flat = int(safe.argmax())
    candidate, cls = flat // safe.shape[1], flat % safe.shape[1]
    score = float(safe[candidate, cls])
    cx, cy, bw, bh = (float(v) for v in boxes[candidate])
    x1 = (cx - bw / 2.0 - pad_x) / scale
    y1 = (cy - bh / 2.0 - pad_y) / scale
    x2 = (cx + bw / 2.0 - pad_x) / scale
    y2 = (cy + bh / 2.0 - pad_y) / scale
    finite = all(math.isfinite(v) for v in (x1, y1, x2, y2, score))
    if not finite:
        x1, y1, x2, y2, score = 0.0, 0.0, 0.0, 0.0, 0.0
    box = clip_box((x1, y1, x2, y2), frame_w, frame_h)
    return {
        "score": r(score, 6),
        "class_index": int(cls),
        "finite": bool(finite),
        "box": [r(v, 2) for v in box],
    }


def crop_from_box(frame, box):
    """Integer crop of a clipped float box; None when unusably small."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = box
    ix1 = min(max(int(round(x1)), 0), w)
    iy1 = min(max(int(round(y1)), 0), h)
    ix2 = min(max(int(round(x2)), 0), w)
    iy2 = min(max(int(round(y2)), 0), h)
    if ix2 - ix1 < MIN_CROP_PX or iy2 - iy1 < MIN_CROP_PX:
        return None, None
    return frame[iy1:iy2, ix1:ix2].copy(), [ix1, iy1, ix2, iy2]


def centered_crop(frame, kind):
    """Centered fallback crop: 'quarter' is half each dimension, 'small' is a centered square."""
    h, w = frame.shape[:2]
    if kind == "quarter":
        crop_w, crop_h = max(1, w // 2), max(1, h // 2)
    elif kind == "small":
        crop_w = crop_h = max(1, min(w, h) // 2)
    else:
        raise ValueError(f"unknown centered crop kind {kind!r}")
    x0, y0 = (w - crop_w) // 2, (h - crop_h) // 2
    return frame[y0:y0 + crop_h, x0:x0 + crop_w].copy(), [x0, y0, x0 + crop_w, y0 + crop_h]


def pick_crop(frame, top, fallback_kind):
    """Choose the candidate crop, or a centered fallback when it is unusable."""
    if top["finite"]:
        crop, crop_px = crop_from_box(frame, top["box"])
        if crop is not None:
            return crop, crop_px, "top_candidate", None
        crop, crop_px = centered_crop(frame, fallback_kind)
        return crop, crop_px, f"{fallback_kind}_center_fallback", "degenerate_box"
    crop, crop_px = centered_crop(frame, fallback_kind)
    return crop, crop_px, f"{fallback_kind}_center_fallback", "non_finite_candidate"


def softmax(z):
    """Stable softmax over a 1-D array of logits."""
    values = np.asarray(z, np.float64).ravel()
    if not np.isfinite(values).any():
        return np.zeros_like(values)
    values = values - np.max(values)
    exp = np.exp(values)
    return exp / np.sum(exp)


def r(value, digits):
    """Round a float to digits for deterministic JSON output."""
    return round(float(value), digits)


def json_safe(value):
    """Convert numpy values and coerce non-finite floats to 0.0 for finite JSON."""
    if isinstance(value, np.ndarray):
        return [json_safe(v) for v in value.tolist()]
    if isinstance(value, (np.floating, np.integer)):
        value = value.item()
    if isinstance(value, float):
        return value if math.isfinite(value) else 0.0
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return value


def chicken_stage(frame, out, scale, pad_x, pad_y, width, height, behaviour_sess,
                  behaviour_side, behaviour_shape, meta, frame_index):
    """Decode the top chicken candidate, crop it, and run the behaviour model."""
    top = decode_top(yolo_matrix(out, "chicken"), scale, pad_x, pad_y,
                     width, height, "chicken")
    stage = {"top_candidate": top, "crop_source": None,
             "crop_fallback_reason": None, "crop_px": None}
    crop, crop_px, source, reason = pick_crop(frame, top, "quarter")
    stage["crop_source"] = source
    stage["crop_fallback_reason"] = reason
    stage["crop_px"] = crop_px
    xb, _, _, _ = letterbox(crop, behaviour_side)
    bout, bshape, wall_ms, cpu_ms = run_checked(
        behaviour_sess, xb, behaviour_shape, "behaviour")
    note_call(meta, "behaviour", frame_index, wall_ms, cpu_ms, bshape)
    raw = [float(v) for v in np.asarray(bout, np.float32).ravel()]
    probs = softmax(bout)
    stage["behaviour"] = {
        "raw_output_shape": bshape,
        "raw_output": [r(v, 6) for v in raw],
        "softmax_probabilities": [r(float(v), 6) for v in probs],
    }
    return stage


def pen_feces_stage(frame, out, scale, pad_x, pad_y, width, height, crop_sess,
                    crop_side, crop_shape, meta, frame_index):
    """Decode the top pen-feces candidate, crop it tight, run the crop-feces model."""
    top = decode_top(yolo_matrix(out, "pen_feces"), scale, pad_x, pad_y,
                     width, height, "pen_feces")
    stage = {"top_candidate": top, "crop_margin_px": 0, "crop_source": None,
             "crop_fallback_reason": None, "crop_px": None}
    crop, crop_px, source, reason = pick_crop(frame, top, "small")
    stage["crop_source"] = source
    stage["crop_fallback_reason"] = reason
    stage["crop_px"] = crop_px
    xc, _, _, _ = letterbox(crop, crop_side)
    cout, cshape, wall_ms, cpu_ms = run_checked(
        crop_sess, xc, crop_shape, "crop_feces")
    note_call(meta, "crop_feces", frame_index, wall_ms, cpu_ms, cshape)
    matrix = yolo_matrix(cout, "crop_feces")
    scores = matrix[:, 4:8]
    safe = np.where(np.isfinite(scores), scores, np.float32(-np.inf))
    best = safe.max(axis=0)
    stage["crop_feces"] = {
        "raw_output_shape": cshape,
        "best_class_scores": {CLASS_ORDER[k]: r(float(best[k]), 6) for k in range(4)},
        "class_order": list(CLASS_ORDER),
        "class_order_source": CLASS_ORDER_SOURCE,
    }
    return stage


def evaluate_frames(frames, args, sessions, meta):
    """Run all four models over every decoded frame and collect per-frame records."""
    width, height = args.width, args.height
    detector_side = contract_side(CONTRACTS["chicken"], "chicken")
    behaviour_side = contract_side(CONTRACTS["behaviour"], "behaviour")
    detector_shape = CONTRACTS["chicken"]["output"]
    behaviour_shape = CONTRACTS["behaviour"]["output"]
    pen_shape = CONTRACTS["pen_feces"]["output"]
    crop_shape = CONTRACTS["crop_feces"]["output"]
    records = []
    for index in range(frames.shape[0]):
        frame = frames[index]
        record = {"frame_index": index}

        x, scale, pad_x, pad_y = letterbox(frame, detector_side)
        out, shape, wall_ms, cpu_ms = run_checked(
            sessions["chicken"], x, detector_shape, "chicken")
        note_call(meta, "chicken", index, wall_ms, cpu_ms, shape)
        record["chicken"] = chicken_stage(
            frame, out, scale, pad_x, pad_y, width, height,
            sessions["behaviour"], behaviour_side, behaviour_shape, meta, index)

        x, scale, pad_x, pad_y = letterbox(frame, detector_side)
        out, shape, wall_ms, cpu_ms = run_checked(
            sessions["pen_feces"], x, pen_shape, "pen_feces")
        note_call(meta, "pen_feces", index, wall_ms, cpu_ms, shape)
        record["pen_feces"] = pen_feces_stage(
            frame, out, scale, pad_x, pad_y, width, height,
            sessions["crop_feces"], detector_side, crop_shape, meta, index)

        records.append(record)
    return records


def main(argv=None):
    args = parse_args(argv)
    validate_contracts()
    frames = read_frames(args.frames, args.width, args.height, args.frame_count)
    Session = import_session(args.ortlite)
    total_started = time.perf_counter()
    cpu_started = time.process_time()
    sessions, meta = load_models(args, Session)
    frame_records = evaluate_frames(frames, args, sessions, meta)
    total_wall_ms = (time.perf_counter() - total_started) * 1000.0
    total_cpu_ms = (time.process_time() - cpu_started) * 1000.0
    for record in meta.values():
        record["total_run_wall_ms"] = r(sum(c["wall_ms"] for c in record["calls"]), 6)
        record["total_run_cpu_ms"] = r(sum(c["cpu_ms"] for c in record["calls"]), 6)
    result = {
        "schema_version": 1,
        "evaluation_kind": "four_model_sparse_frame",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "python_version": sys.version.split()[0],
            "python_pid": os.getpid(),
            "numpy_version": np.__version__,
            "platform": sys.platform,
        },
        "input": {
            "frames_path": str(Path(args.frames).resolve()),
            "width": args.width,
            "height": args.height,
            "frame_count": args.frame_count,
            "raw_bytes": args.width * args.height * 3 * args.frame_count,
            "threads": args.threads,
        },
        "models": meta,
        "frames": frame_records,
        "timing": {
            "total_wall_ms": r(total_wall_ms, 6),
            "total_process_cpu_ms": r(total_cpu_ms, 6),
        },
        "method_notes": METHOD_NOTES,
        "limitations": LIMITATIONS,
    }
    out_path = Path(args.result)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(json_safe(result), handle, indent=2)
        handle.write("\n")
    print(f"four_model_sparse: wrote {out_path} in {r(total_wall_ms, 6)} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
