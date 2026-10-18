#!/usr/bin/env python3
"""Simulation-lab target-validation probe worker (QNX Pi, stdlib only).

This worker runs on the physical Pi and proves that one exact model file and
one canonical scenario JSON reached the target and were processed there. It
deliberately performs no inference: the Pi has no TensorFlow Lite, ONNX,
OpenCV, or NumPy runtime, and this probe never claims otherwise.

It is invoked by the qnx-runner with argv (no shell) as:

    /system/bin/python3 simlab_probe.py \
        --request request.json --scenario scenario.json \
        --model model.bin --result receipt.json

On success it atomically writes a receipt JSON. On any validation failure or
hash mismatch it exits nonzero and writes no receipt, so a remote run
directory with no receipt proves failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
from datetime import datetime, timezone

SCHEMA_VERSION = 1
INFERENCE_REASON = "No QNX inference runtime is installed or configured."
READ_CHUNK = 1024 * 1024

RUN_ID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
SHA256_RE = r"^[a-f0-9]{64}$"
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"

EXIT_FAILURE = 2


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _matches(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None


def sha256_of(path: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(READ_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def platform_details() -> dict[str, str]:
    details: dict[str, str] = {}
    for name, getter in (
        ("system", platform.system),
        ("machine", platform.machine),
        ("release", platform.release),
        ("python_version", platform.python_version),
    ):
        try:
            details[name] = getter() or ""
        except Exception:
            details[name] = ""
    return details


def load_request(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            request = json.load(handle)
    except (OSError, ValueError) as exc:
        print("simlab_probe: cannot read request JSON: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_FAILURE)
    if not isinstance(request, dict):
        print("simlab_probe: request JSON must be an object", file=sys.stderr)
        sys.exit(EXIT_FAILURE)

    run_id = request.get("run_id")
    if not isinstance(run_id, str) or not _matches(RUN_ID_RE, run_id):
        print("simlab_probe: run_id is missing or unsafe", file=sys.stderr)
        sys.exit(EXIT_FAILURE)

    for kind in ("model", "scenario"):
        entry = request.get(kind)
        if not isinstance(entry, dict):
            print("simlab_probe: %s entry is missing or invalid" % kind, file=sys.stderr)
            sys.exit(EXIT_FAILURE)
        name = entry.get("name")
        digest = entry.get("sha256")
        if not isinstance(name, str) or not _matches(NAME_RE, name):
            print("simlab_probe: %s name is missing or unsafe" % kind, file=sys.stderr)
            sys.exit(EXIT_FAILURE)
        if not isinstance(digest, str) or not _matches(SHA256_RE, digest):
            print("simlab_probe: %s sha256 must be 64 lowercase hex characters" % kind, file=sys.stderr)
            sys.exit(EXIT_FAILURE)
    return request


def verify_hashes(request: dict, scenario_path: str, model_path: str) -> dict:
    if not os.path.isfile(model_path):
        print("simlab_probe: model file missing: %s" % model_path, file=sys.stderr)
        sys.exit(EXIT_FAILURE)
    if not os.path.isfile(scenario_path):
        print("simlab_probe: scenario file missing: %s" % scenario_path, file=sys.stderr)
        sys.exit(EXIT_FAILURE)

    try:
        with open(scenario_path, "r", encoding="utf-8") as handle:
            scenario_text = handle.read()
    except OSError as exc:
        print("simlab_probe: cannot read scenario file: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_FAILURE)
    try:
        json.loads(scenario_text)
    except ValueError as exc:
        print("simlab_probe: scenario file is not valid JSON: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_FAILURE)

    model_hash, model_size = sha256_of(model_path)
    scenario_hash = hashlib.sha256(scenario_text.encode("utf-8")).hexdigest()
    scenario_size = len(scenario_text.encode("utf-8"))

    expected_model = request["model"]["sha256"]
    expected_scenario = request["scenario"]["sha256"]
    if model_hash != expected_model:
        print(
            "simlab_probe: model hash mismatch (expected %s, got %s)"
            % (expected_model, model_hash),
            file=sys.stderr,
        )
        sys.exit(EXIT_FAILURE)
    if scenario_hash != expected_scenario:
        print(
            "simlab_probe: scenario hash mismatch (expected %s, got %s)"
            % (expected_scenario, scenario_hash),
            file=sys.stderr,
        )
        sys.exit(EXIT_FAILURE)

    return {
        "run_id": request["run_id"],
        "model": {
            "name": request["model"]["name"],
            "sha256": model_hash,
            "size_bytes": model_size,
        },
        "scenario": {
            "name": request["scenario"]["name"],
            "sha256": scenario_hash,
            "size_bytes": scenario_size,
        },
    }


def atomic_write_json(path: str, payload: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    temporary = "%s/.receipt.json.%d.tmp" % (directory, os.getpid())
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def build_receipt(verified: dict, started_at: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": verified["run_id"],
        "model": verified["model"],
        "scenario": verified["scenario"],
        "platform": platform_details(),
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "inference_performed": False,
        "inference_reason": INFERENCE_REASON,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="simlab_probe.py",
        description="Prove one model and one scenario reached the QNX Pi (no inference).",
    )
    parser.add_argument("--request", required=True, help="validated request JSON path")
    parser.add_argument("--scenario", required=True, help="canonical scenario JSON path")
    parser.add_argument("--model", required=True, help="model artifact path")
    parser.add_argument("--result", required=True, help="receipt output path")
    args = parser.parse_args(argv)

    try:
        os.unlink(args.result)
    except OSError:
        pass

    started_at = utc_now_iso()
    request = load_request(args.request)
    verified = verify_hashes(request, args.scenario, args.model)
    receipt = build_receipt(verified, started_at)
    atomic_write_json(args.result, receipt)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
