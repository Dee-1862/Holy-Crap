#!/system/bin/python3
"""QNX-side supervisor for the Holy Crap clip-assessment worker contract.

This wrapper does not contain a model and cannot silently substitute mock or
laptop inference.  It verifies the installed worker against a deployment
manifest, runs it as a separate target process, samples best-effort QNX
resource telemetry, and writes a result envelope for the dashboard host.

Installed worker argv contract::

    WORKER --request REQUEST.json --video VIDEO --result ASSESSMENT.json

The worker must write a complete ClipAssessment JSON object.  Python workers
are launched with the target Python interpreter; native workers are executed
directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


CONTRACT = "holy-crap.clip-assessment.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def physical_memory() -> int | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    return pages * page_size if pages > 0 and page_size > 0 else None


def qnx_free_memory() -> int | None:
    """Best-effort parse of QNX ``pidin info`` FreeMem output."""

    try:
        proc = subprocess.run(
            ["pidin", "info"], capture_output=True, text=True, timeout=3, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if "freemem" not in line.lower():
            continue
        match = re.search(r"FreeMem[^0-9]*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?)", line, re.I)
        if not match:
            continue
        multiplier = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        return int(float(match.group(1)) * multiplier[match.group(2).upper()])
    return None


class TelemetryCollector:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.samples: list[dict] = []
        self.stop = threading.Event()

    def sample(self) -> None:
        total = physical_memory()
        free = qnx_free_memory()
        self.samples.append(
            {
                "captured_at": utc_now(),
                "source": "qnx",
                "cpu_percent": None,
                "ram_used_bytes": total - free if total is not None and free is not None else None,
                "ram_total_bytes": total,
                "process_cpu_percent": None,
                "process_ram_bytes": None,
                "detail": (
                    "System RAM is sampled from QNX pidin info. Inference-process CPU/RAM "
                    "and system CPU remain null until child pidin parsing is verified on the "
                    "physical target; supervisor usage is intentionally not mislabeled."
                ),
            }
        )
        temporary = self.path.with_name(".%s.tmp" % self.path.name)
        temporary.write_text(
            json.dumps({"schema_version": 1, "samples": self.samples}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def run(self) -> None:
        while not self.stop.wait(1.0):
            self.sample()


def target_identity(detail: str) -> dict:
    return {
        "executor": "qnx",
        "hostname": platform.node() or None,
        "system": platform.system() or None,
        "release": platform.release() or None,
        "machine": platform.machine() or None,
        "runtime": "Python %s" % platform.python_version(),
        "verified": platform.system() == "QNX",
        "detail": detail,
    }


def write_envelope(path: Path, envelope: dict) -> None:
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)

    result_path = Path(args.result)
    telemetry = TelemetryCollector(result_path.with_name("telemetry.json"))
    request: dict = {}
    message = "QNX assessment worker did not start"
    status = "blocked"
    assessment = None
    thread: threading.Thread | None = None
    try:
        request_value = json.loads(Path(args.request).read_text(encoding="utf-8"))
        if not isinstance(request_value, dict):
            raise ValueError("request must be a JSON object")
        request = request_value
        if request.get("worker_contract") != CONTRACT or request.get("executor") != "qnx":
            raise ValueError("request does not match the QNX clip worker contract")
        video = Path(args.video)
        if sha256_file(video) != request.get("video_sha256"):
            raise ValueError("staged video hash does not match the request")
        manifest_value = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        if not isinstance(manifest_value, dict):
            raise ValueError("deployment manifest must be a JSON object")
        worker = Path(args.worker)
        worker_hash = manifest_value.get("worker_sha256")
        if (
            manifest_value.get("schema_version") != 1
            or manifest_value.get("contract") != CONTRACT
            or manifest_value.get("platform") != "QNX"
            or manifest_value.get("worker_path") != str(worker)
            or not isinstance(worker_hash, str)
            or SHA256_RE.fullmatch(worker_hash) is None
        ):
            raise ValueError("installed worker manifest does not match the required contract")
        if platform.system() != "QNX":
            raise ValueError("target runtime is not QNX")
        if not worker.is_file() or sha256_file(worker) != worker_hash:
            raise ValueError("installed QNX worker is missing or does not match its manifest")

        telemetry.sample()
        thread = threading.Thread(target=telemetry.run, name="qnx-telemetry", daemon=True)
        thread.start()
        assessment_path = result_path.with_name("assessment.json")
        command = [str(worker), "--request", args.request, "--video", args.video, "--result", str(assessment_path)]
        if worker.suffix == ".py":
            command.insert(0, sys.executable)
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            raise RuntimeError(
                "installed QNX assessment worker failed%s"
                % (": %s" % detail[-1] if detail else "")
            )
        assessment_value = json.loads(assessment_path.read_text(encoding="utf-8"))
        if not isinstance(assessment_value, dict):
            raise ValueError("installed QNX worker result must be a JSON object")
        assessment = assessment_value
        status = "completed"
        message = "Clip assessment completed by the verified QNX target worker"
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        status = "blocked" if isinstance(exc, (ValueError, FileNotFoundError)) else "failed"
    finally:
        telemetry.stop.set()
        if thread is not None:
            thread.join(timeout=2)
        telemetry.sample()
        envelope = {
            "schema_version": 1,
            "job_id": request.get("job_id"),
            "executor": "qnx",
            "status": status,
            "message": message,
            "target": target_identity(
                "Identity and telemetry were generated inside the QNX worker supervisor."
            ),
            "telemetry_history": telemetry.samples,
            "assessment": assessment,
        }
        write_envelope(result_path, envelope)
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
