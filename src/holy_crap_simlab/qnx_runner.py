"""Transport to the headless QNX Pi: probing, validation, and clip jobs.

Target-validation mode proves that exact model and scenario files reached the
physical Pi; it does not perform inference. Clip-worker mode is a separate,
fail-closed path that may run inference only after the installed QNX worker and
its deployment manifest pass hash and identity checks. Neither path silently
falls back to the local assessment pipeline.

Safety rules implemented here:

- argv only: every local subprocess call is an argv list, never ``shell=True``.
- SSH uses BatchMode and ConnectTimeout, with an optional HostName override.
- Remote files are staged with scp to dot-temp names and renamed into place
  with a single remote ``mv`` chain, so a crashed transfer never looks final.
- Identifiers (run id, names) are validated before they can reach a path.
- Remote run directories are kept for audit; nothing here deletes them.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from pydantic import ValidationError

from .models import (
    AdapterCapability,
    ClipAssessmentTarget,
    QnxFaultEvent,
    QnxFaultTestResponse,
    QnxRuntimeCapture,
    QnxRuntimeCorrelation,
    QnxRuntimeModelTiming,
    QnxRuntimeProcess,
    QnxRuntimeResponse,
    QnxRuntimeStatus,
    ResourceTelemetrySample,
    utc_now,
)

RUN_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CLIP_JOB_ID_RE = re.compile(
    r"^clip-job-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

DEFAULT_SUBMIT_JOB = Path(__file__).resolve().parents[2] / "scripts" / "qnx_submit_job.py"

DEFAULT_EDGE_STATUS_URL = "http://127.0.0.1:8088/telemetry"
DEFAULT_EDGE_CRASH_URL = "http://127.0.0.1:8088/crash"
MAX_EDGE_STATUS_BYTES = 1024 * 1024

EDGE_FAULT_TEST_PROCESSES = ("infer", "model", "cloud", "site")

_BEGIN_PYTHON = "SIMLAB_PROBE_PYTHON_BEGIN"
_END_PYTHON = "SIMLAB_PROBE_PYTHON_END"
_BEGIN_RUNNER = "SIMLAB_PROBE_RUNNER_BEGIN"
_END_RUNNER = "SIMLAB_PROBE_RUNNER_END"
_BEGIN_RUNTIMES = "SIMLAB_PROBE_RUNTIMES_BEGIN"
_END_RUNTIMES = "SIMLAB_PROBE_RUNTIMES_END"

PROBE_RUNTIME_MODULES = ("tflite_runtime", "onnxruntime", "cv2", "numpy")


class QnxRunnerError(RuntimeError):
    """A QNX transport step failed, was rejected, or timed out."""


def _require_local_http_url(name: str, value: str) -> str:
    """Edge endpoints are fetched by target-localhost Python; never allow anything else."""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost"):
        raise QnxRunnerError(
            "%s must be an http:// URL on 127.0.0.1 or localhost, got %r" % (name, value)
        )
    return value


@dataclass(frozen=True)
class QnxRunnerConfig:
    """Configuration loaded from the environment (see from_env)."""

    mode: str = "disabled"  # QNX_EXECUTOR_MODE: "disabled" | "probe" | "worker"
    ssh_alias: str = "qnxpi"  # QNX_SSH_ALIAS
    ssh_hostname: str | None = None  # QNX_SSH_HOSTNAME (optional HostName override)
    ssh_timeout: int = 20  # QNX_SSH_TIMEOUT (ConnectTimeout seconds)
    command_timeout: int = 300  # QNX_COMMAND_TIMEOUT (local ssh/scp call timeout)
    submit_job: Path = DEFAULT_SUBMIT_JOB  # QNX_SUBMIT_JOB
    remote_root: str = "/data/home/qnxuser/simlab-runs"  # QNX_REMOTE_ROOT
    remote_python: str = "/system/bin/python3"  # QNX_REMOTE_PYTHON
    runner_app_dir: str = "/data/home/qnxuser/qnx-runner-app"  # QNX_RUNNER_APP_DIR
    runner_spool: str = "/data/home/qnxuser/qnx-runner"  # QNX_RUNNER_SPOOL
    job_timeout: int = 300  # QNX_JOB_TIMEOUT (helper --timeout)
    wait_timeout: int = 600  # QNX_WAIT_TIMEOUT (helper --wait-timeout)
    worker_path: Path | None = None  # QNX_WORKER_PATH (override probe worker)
    clip_worker_remote: str | None = None  # QNX_CLIP_WORKER_REMOTE
    clip_worker_manifest: str | None = None  # QNX_CLIP_WORKER_MANIFEST
    clip_worker_manifest_sha256: str | None = None  # QNX_CLIP_WORKER_MANIFEST_SHA256
    clip_wrapper_path: Path | None = None  # QNX_CLIP_WRAPPER_PATH
    edge_status_url: str = DEFAULT_EDGE_STATUS_URL  # QNX_EDGE_STATUS_URL
    edge_crash_url: str = DEFAULT_EDGE_CRASH_URL  # QNX_EDGE_CRASH_URL
    edge_status_timeout: int = 10  # QNX_EDGE_STATUS_TIMEOUT
    edge_fault_tests: bool = False  # QNX_EDGE_FAULT_TESTS ("1" enables)

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> QnxRunnerConfig:
        env = dict(os.environ if environ is None else environ)

        def text(name: str, default: str) -> str:
            raw = env.get(name)
            return default if raw is None or raw == "" else raw

        def integer(name: str, default: int, minimum: int = 1) -> int:
            raw = env.get(name)
            if raw is None or raw == "":
                return default
            try:
                value = int(raw)
            except ValueError as exc:
                raise QnxRunnerError("%s must be an integer, got %r" % (name, raw)) from exc
            if value < minimum:
                raise QnxRunnerError("%s must be at least %d, got %d" % (name, minimum, value))
            return value

        mode = text("QNX_EXECUTOR_MODE", "disabled")
        if mode not in ("disabled", "probe", "worker"):
            raise QnxRunnerError(
                "QNX_EXECUTOR_MODE must be 'disabled', 'probe', or 'worker', got %r" % mode
            )
        worker_raw = text("QNX_WORKER_PATH", "")
        wrapper_raw = text("QNX_CLIP_WRAPPER_PATH", "")
        edge_status_url = text("QNX_EDGE_STATUS_URL", DEFAULT_EDGE_STATUS_URL)
        edge_crash_url = text("QNX_EDGE_CRASH_URL", DEFAULT_EDGE_CRASH_URL)
        _require_local_http_url("QNX_EDGE_STATUS_URL", edge_status_url)
        _require_local_http_url("QNX_EDGE_CRASH_URL", edge_crash_url)
        # This destructive-test gate deliberately follows the documented
        # contract exactly: only the literal string ``1`` enables it.
        fault_flag = env.get("QNX_EDGE_FAULT_TESTS")
        return cls(
            mode=mode,
            ssh_alias=text("QNX_SSH_ALIAS", "qnxpi"),
            ssh_hostname=text("QNX_SSH_HOSTNAME", "") or None,
            ssh_timeout=integer("QNX_SSH_TIMEOUT", 20),
            command_timeout=integer("QNX_COMMAND_TIMEOUT", 300),
            submit_job=Path(text("QNX_SUBMIT_JOB", str(DEFAULT_SUBMIT_JOB))),
            remote_root=text("QNX_REMOTE_ROOT", "/data/home/qnxuser/simlab-runs"),
            remote_python=text("QNX_REMOTE_PYTHON", "/system/bin/python3"),
            runner_app_dir=text("QNX_RUNNER_APP_DIR", "/data/home/qnxuser/qnx-runner-app"),
            runner_spool=text("QNX_RUNNER_SPOOL", "/data/home/qnxuser/qnx-runner"),
            job_timeout=integer("QNX_JOB_TIMEOUT", 300),
            wait_timeout=integer("QNX_WAIT_TIMEOUT", 600),
            worker_path=Path(worker_raw) if worker_raw else None,
            clip_worker_remote=text("QNX_CLIP_WORKER_REMOTE", "") or None,
            clip_worker_manifest=text("QNX_CLIP_WORKER_MANIFEST", "") or None,
            clip_worker_manifest_sha256=text("QNX_CLIP_WORKER_MANIFEST_SHA256", "") or None,
            clip_wrapper_path=Path(wrapper_raw) if wrapper_raw else None,
            edge_status_url=edge_status_url,
            edge_crash_url=edge_crash_url,
            edge_status_timeout=integer("QNX_EDGE_STATUS_TIMEOUT", 10),
            edge_fault_tests=fault_flag == "1",
        )

    @property
    def enabled(self) -> bool:
        return self.mode in ("probe", "worker")

    @property
    def clip_worker_configured(self) -> bool:
        return bool(
            self.mode == "worker"
            and self.clip_worker_remote
            and self.clip_worker_manifest
            and self.clip_worker_manifest_sha256
        )


@dataclass(frozen=True)
class QnxProbeReport:
    """Structured result of probe_capability."""

    reachable: bool
    python_version: str | None
    runner_output: str
    runtime_presence: dict[str, bool]
    detail: str

    @property
    def python_ok(self) -> bool:
        return self.python_version is not None

    @property
    def runner_ok(self) -> bool:
        return "runner: running" in self.runner_output

    @property
    def ready(self) -> bool:
        return self.reachable and self.python_ok and self.runner_ok

    def capability(self) -> AdapterCapability:
        return AdapterCapability(
            id="qnx",
            kind="executor",
            status="ready" if self.ready else "not_configured",
            description=self.detail,
        )


@dataclass(frozen=True)
class QnxValidationOutcome:
    """Validated receipt, captured helper output, and the kept remote run dir."""

    receipt: dict
    helper_output: str
    remote_run_dir: str


@dataclass(frozen=True)
class QnxClipAssessmentOutcome:
    """A validated target envelope from the clip-assessment worker contract."""

    status: str
    message: str
    target: dict
    telemetry_history: list[dict]
    assessment: dict | None
    helper_output: str
    remote_run_dir: str


@dataclass(frozen=True)
class QnxEdgeStatusOutcome:
    """Raw stdout of a successful remote edge status fetch; parsed by normalization."""

    output: str


@dataclass(frozen=True)
class QnxEdgeCrashOutcome:
    """Raw output of a successful remote edge fault-test request."""

    output: str
    payload: dict | None


RunnerCallable = Callable[..., "subprocess.CompletedProcess[str]"]


def default_runner(
    argv: Sequence[str], timeout: float | None = None
) -> "subprocess.CompletedProcess[str]":
    """Real subprocess runner: argv list only, never a shell."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


class QnxRunner:
    """Probe QNX, validate artifacts, and run verified deployed clip workers."""

    def __init__(
        self,
        config: QnxRunnerConfig | None = None,
        subprocess_runner: RunnerCallable | None = None,
    ) -> None:
        self.config = config or QnxRunnerConfig.from_env()
        self._subprocess_runner = subprocess_runner

    # --- argv construction -------------------------------------------------

    def _ssh_options(self) -> list[str]:
        options = [
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=%d" % self.config.ssh_timeout,
        ]
        if self.config.ssh_hostname:
            options += ["-o", "HostName=%s" % self.config.ssh_hostname]
        return options

    def _ssh_argv(self, *command: str) -> list[str]:
        return ["ssh", *self._ssh_options(), self.config.ssh_alias, *command]

    def _scp_argv(self, source: str, destination: str) -> list[str]:
        return ["scp", "-q", *self._ssh_options(), source, destination]

    def _run(
        self, argv: Sequence[str], timeout: float, runner: RunnerCallable | None
    ) -> "subprocess.CompletedProcess[str]":
        try:
            return (runner or self._subprocess_runner or default_runner)(argv, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise QnxRunnerError(
                "command timed out after %.0fs: %s" % (exc.timeout or 0, argv[0])
            ) from exc
        except OSError as exc:
            raise QnxRunnerError("could not run %s: %s" % (argv[0], exc)) from exc

    def _checked(
        self, argv: Sequence[str], timeout: float, runner: RunnerCallable | None, what: str
    ) -> "subprocess.CompletedProcess[str]":
        proc = self._run(argv, timeout, runner)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise QnxRunnerError(
                "%s failed (%d): %s" % (what, proc.returncode, detail or "no output")
            )
        return proc

    # --- identifier validation ---------------------------------------------

    def _validate_run_id(self, run_id: str) -> str:
        if not isinstance(run_id, str) or RUN_ID_RE.fullmatch(run_id) is None:
            raise QnxRunnerError(
                "unsafe run_id %r; expected a lowercase UUID like "
                "'8d3f1a2b-9c4e-4f5a-9b1c-2d3e4f5a6b7c'" % (run_id,)
            )
        return run_id

    def _validate_name(self, label: str, name: str) -> str:
        if not isinstance(name, str) or NAME_RE.fullmatch(name) is None:
            raise QnxRunnerError(
                "%s %r is unsafe; use only [A-Za-z0-9._-], starting alphanumeric"
                % (label, name)
            )
        return name

    # --- probing ------------------------------------------------------------

    def probe_capability(self, runner: RunnerCallable | None = None) -> QnxProbeReport:
        """Check SSH, target Python, the qnx-runner, and runtime presence in one remote call."""
        if not self.config.enabled:
            return QnxProbeReport(
                reachable=False,
                python_version=None,
                runner_output="",
                runtime_presence={},
                detail="QNX executor disabled (QNX_EXECUTOR_MODE=%r); set it to 'probe' or 'worker'"
                % self.config.mode,
            )
        python = shlex.quote(self.config.remote_python)
        status_script = shlex.quote("%s/status-runner.sh" % self.config.runner_app_dir)
        checks = []
        for module in PROBE_RUNTIME_MODULES:
            checks.append(
                '%s -c "import %s" >/dev/null 2>&1 && echo "PRESENT %s" || echo "ABSENT %s"'
                % (python, module, module, module)
            )
        for path in (self.config.runner_app_dir, self.config.runner_spool):
            checks.append(
                "[ -e %s ] && echo 'PRESENT %s' || echo 'ABSENT %s'"
                % (shlex.quote(path), path, path)
            )
        remote_command = "; ".join(
            [
                "echo %s" % shlex.quote(_BEGIN_PYTHON),
                "%s --version 2>&1" % python,
                "echo %s" % shlex.quote(_END_PYTHON),
                "echo %s" % shlex.quote(_BEGIN_RUNNER),
                "%s 2>&1" % status_script,
                "echo %s" % shlex.quote(_END_RUNNER),
                "echo %s" % shlex.quote(_BEGIN_RUNTIMES),
                *checks,
                "echo %s" % shlex.quote(_END_RUNTIMES),
            ]
        )
        proc = self._run(self._ssh_argv(remote_command), self.config.command_timeout, runner)
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            detail = "SSH to %s failed" % self.config.ssh_alias
            if proc.stderr and proc.stderr.strip():
                detail += ": %s" % proc.stderr.strip().splitlines()[0]
            return QnxProbeReport(
                reachable=False,
                python_version=None,
                runner_output="",
                runtime_presence={},
                detail=detail,
            )
        sections = self._parse_probe_output(proc.stdout or "")
        python_version = None
        for line in sections.get("python", []):
            if line.startswith("Python "):
                python_version = line.split()[1]
                break
        runner_output = "\n".join(sections.get("runner", [])).strip()
        runtime_presence = {}
        for line in sections.get("runtimes", []):
            if line.startswith("PRESENT ") and len(line) > 8:
                runtime_presence[line[8:].strip()] = True
            elif line.startswith("ABSENT ") and len(line) > 7:
                runtime_presence[line[7:].strip()] = False
        parts = [
            "ssh=%s" % ("ok" if proc.returncode == 0 else "failed"),
            "python=%s" % (python_version or "missing"),
            "runner=%s" % ("running" if "runner: running" in runner_output else "not running"),
        ]
        parts += ["%s=%s" % (key, "present" if value else "absent") for key, value in sorted(runtime_presence.items())]
        report = QnxProbeReport(
            reachable=True,
            python_version=python_version,
            runner_output=runner_output,
            runtime_presence=runtime_presence,
            detail="QNX Pi probe: " + ", ".join(parts),
        )
        return report

    @staticmethod
    def _parse_probe_output(stdout: str) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current: str | None = None
        markers = {
            _BEGIN_PYTHON: "python",
            _END_PYTHON: None,
            _BEGIN_RUNNER: "runner",
            _END_RUNNER: None,
            _BEGIN_RUNTIMES: "runtimes",
            _END_RUNTIMES: None,
        }
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if line in markers:
                current = markers[line]
                continue
            if current:
                sections.setdefault(current, []).append(line)
        return sections

    # --- edge runtime status -------------------------------------------------

    def _edge_fetch_timeout(self) -> float:
        return float(self.config.edge_status_timeout + self.config.ssh_timeout)

    def _require_local_edge_urls(self) -> None:
        _require_local_http_url("QNX_EDGE_STATUS_URL", self.config.edge_status_url)
        _require_local_http_url("QNX_EDGE_CRASH_URL", self.config.edge_crash_url)

    def _edge_status_remote_code(self) -> str:
        """Python source that fetches the edge status endpoint on the target.

        The URL is embedded with json.dumps and the whole source travels as one
        shlex-quoted argv element, so target-localhost only is reachable and no
        local or remote shell ever interpolates it.
        """
        self._require_local_edge_urls()
        url = json.dumps(self.config.edge_status_url)
        timeout = self.config.edge_status_timeout
        maximum = MAX_EDGE_STATUS_BYTES
        return (
            "import sys, urllib.request as _u\n"
            "try:\n"
            f"    with _u.urlopen({url}, timeout={timeout}) as _r:\n"
            "        _cl = _r.headers.get('Content-Length')\n"
            "        if _cl is not None:\n"
            "            try:\n"
            "                _declared = int(_cl)\n"
            "            except ValueError:\n"
            "                raise ValueError('invalid Content-Length')\n"
            f"            if _declared < 0 or _declared > {maximum}:\n"
            "                raise ValueError('edge telemetry Content-Length exceeds limit')\n"
            f"        _b = _r.read({maximum + 1})\n"
            f"        if len(_b) > {maximum}:\n"
            "            raise ValueError('edge telemetry body exceeds limit')\n"
            "        if _cl is not None and len(_b) != _declared:\n"
            "            raise ValueError('truncated edge telemetry body')\n"
            "except Exception as _e:\n"
            '    sys.stderr.write("SIMLAB_EDGE_FETCH_ERROR: %s: %s\\n" % (type(_e).__name__, _e))\n'
            "    raise SystemExit(1)\n"
            'sys.stdout.write(_b.decode("utf-8", "replace"))\n'
        )

    def _edge_crash_remote_code(self, process_name: str) -> str:
        """Python source that POSTs one allowlisted fault test to the edge."""
        self._require_local_edge_urls()
        query = urllib.parse.urlencode({"proc": process_name})
        url = json.dumps(self.config.edge_crash_url + "?" + query)
        timeout = self.config.edge_status_timeout
        return (
            "import sys, json as _j, urllib.request as _u, urllib.error as _ue\n"
            f'_req = _u.Request({url}, data=_j.dumps({{}}).encode("utf-8"), method="POST")\n'
            "try:\n"
            f"    with _u.urlopen(_req, timeout={timeout}) as _r:\n"
            "        _b = _r.read()\n"
            "except _ue.HTTPError as _e:\n"
            '    sys.stdout.write(_e.read().decode("utf-8", "replace"))\n'
            "    raise SystemExit(2)\n"
            "except Exception as _e:\n"
            '    sys.stderr.write("SIMLAB_EDGE_CRASH_ERROR: %s: %s\\n" % (type(_e).__name__, _e))\n'
            "    raise SystemExit(1)\n"
            'sys.stdout.write(_b.decode("utf-8", "replace"))\n'
        )

    def edge_status(self, runner: RunnerCallable | None = None) -> QnxEdgeStatusOutcome:
        """Fetch the target edge status with the configured target Python over SSH.

        Transport failures raise QnxRunnerError; interpreting the returned text
        is the caller's job (see normalize_edge_status).
        """
        if not self.config.enabled:
            raise QnxRunnerError(
                "QNX runtime status is not configured (QNX_EXECUTOR_MODE=%r); no Pi contact"
                % self.config.mode
            )
        code = self._edge_status_remote_code()
        argv = self._ssh_argv(
            shlex.quote(self.config.remote_python), "-c", shlex.quote(code)
        )
        proc = self._run(argv, self._edge_fetch_timeout(), runner)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise QnxRunnerError(
                "edge status fetch failed (%d): %s" % (proc.returncode, detail or "no output")
            )
        return QnxEdgeStatusOutcome(output=proc.stdout or "")

    def edge_crash(
        self, process_name: str, runner: RunnerCallable | None = None
    ) -> QnxEdgeCrashOutcome:
        """Ask the target edge to SIGKILL one allowlisted supervised process.

        The allowlist is enforced here and again in the service layer, before
        any subprocess starts. The process name is embedded only into the
        argv-passed Python source; nothing reaches a shell.
        """
        if process_name not in EDGE_FAULT_TEST_PROCESSES:
            raise QnxRunnerError(
                "fault test process %r is not allowlisted; expected one of %s"
                % (process_name, ", ".join(EDGE_FAULT_TEST_PROCESSES))
            )
        if not self.config.edge_fault_tests:
            raise QnxRunnerError(
                "fault tests are disabled (QNX_EDGE_FAULT_TESTS is not enabled)"
            )
        if not self.config.enabled:
            raise QnxRunnerError(
                "QNX executor is disabled (QNX_EXECUTOR_MODE=%r); fault tests need a reachable target"
                % self.config.mode
            )
        code = self._edge_crash_remote_code(process_name)
        argv = self._ssh_argv(
            shlex.quote(self.config.remote_python), "-c", shlex.quote(code)
        )
        proc = self._run(argv, self._edge_fetch_timeout(), runner)
        output = (proc.stdout or "").strip()
        if proc.returncode == 2:
            raise QnxRunnerError(
                "target rejected the fault test for %r: %s"
                % (process_name, output or "no response body")
            )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip() or output or "no output"
            raise QnxRunnerError(
                "fault test request failed (%d): %s" % (proc.returncode, detail)
            )
        try:
            payload = json.loads(output or "null")
        except ValueError:
            payload = None
        return QnxEdgeCrashOutcome(
            output=output,
            payload=payload if isinstance(payload, dict) else None,
        )

    # --- target validation ---------------------------------------------------

    def _worker_bytes(self) -> bytes:
        if self.config.worker_path is not None:
            path = self.config.worker_path
        else:
            path = Path(__file__).resolve().parents[2] / "target" / "qnx" / "simlab_probe.py"
        try:
            return path.read_bytes()
        except OSError as exc:
            raise QnxRunnerError("cannot read probe worker %s: %s" % (path, exc)) from exc

    def _clip_wrapper_bytes(self) -> bytes:
        path = self.config.clip_wrapper_path or (
            Path(__file__).resolve().parents[2]
            / "target"
            / "qnx"
            / "clip_assessment_worker.py"
        )
        try:
            return path.read_bytes()
        except OSError as exc:
            raise QnxRunnerError("cannot read QNX clip wrapper %s: %s" % (path, exc)) from exc

    def _clip_worker_configuration(self) -> tuple[str, str, str]:
        if self.config.mode != "worker":
            raise QnxRunnerError(
                "QNX clip inference is not deployment-ready: QNX_EXECUTOR_MODE must be "
                "'worker'. The probe mode validates transport only; local inference was not used."
            )
        worker = self.config.clip_worker_remote
        manifest = self.config.clip_worker_manifest
        expected_hash = self.config.clip_worker_manifest_sha256
        if not worker or not worker.startswith("/"):
            raise QnxRunnerError(
                "QNX clip inference is not deployment-ready: QNX_CLIP_WORKER_REMOTE must "
                "name the installed absolute target worker path"
            )
        if not manifest or not manifest.startswith("/"):
            raise QnxRunnerError(
                "QNX clip inference is not deployment-ready: QNX_CLIP_WORKER_MANIFEST must "
                "name the installed absolute deployment manifest path"
            )
        if not expected_hash or SHA256_RE.fullmatch(expected_hash) is None:
            raise QnxRunnerError(
                "QNX clip inference is not deployment-ready: "
                "QNX_CLIP_WORKER_MANIFEST_SHA256 must be the reviewed 64-character manifest hash"
            )
        return worker, manifest, expected_hash

    def assess_clip_on_target(
        self,
        *,
        job_id: str,
        video_path: Path,
        request: dict,
        progress: Callable[[int, str, str], None] | None = None,
        telemetry: Callable[[list[dict]], None] | None = None,
        runner: RunnerCallable | None = None,
    ) -> QnxClipAssessmentOutcome:
        """Execute the explicit clip-worker contract through the persistent QNX runner.

        This is deliberately fail closed.  The reviewed deployment manifest must
        be downloaded from the physical target and hash-verified before video
        bytes are staged.  A transport, manifest, runtime, or worker failure is
        returned to the caller; this method never invokes the local pipeline.
        """

        if CLIP_JOB_ID_RE.fullmatch(job_id) is None:
            raise QnxRunnerError("unsafe clip assessment job id %r" % job_id)
        worker, manifest_path, expected_manifest_hash = self._clip_worker_configuration()
        video_path = Path(video_path).expanduser().resolve()
        if not video_path.is_file():
            raise QnxRunnerError("clip video does not exist: %s" % video_path)
        try:
            digest = hashlib.sha256()
            with video_path.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            video_hash = digest.hexdigest()
        except OSError as exc:
            raise QnxRunnerError("cannot read clip video %s: %s" % (video_path, exc)) from exc

        if progress:
            progress(3, "qnx_probe", "Checking the QNX Pi and persistent runner")
        report = self.probe_capability(runner=runner)
        if not report.ready:
            raise QnxRunnerError(report.detail)

        request_payload = dict(request)
        request_payload.update(
            {
                "schema_version": 1,
                "job_id": job_id,
                "executor": "qnx",
                "video_sha256": video_hash,
                "worker_contract": "holy-crap.clip-assessment.v1",
            }
        )
        run_dir = "%s/%s" % (self.config.remote_root.rstrip("/"), job_id)
        with tempfile.TemporaryDirectory(prefix="qnx-clip-stage-") as temp_name:
            stage = Path(temp_name)
            local_manifest = stage / "deployment-manifest.json"
            if progress:
                progress(6, "qnx_verifying", "Verifying the installed QNX worker manifest")
            self._checked(
                self._scp_argv(
                    "%s:%s" % (self.config.ssh_alias, manifest_path), str(local_manifest)
                ),
                self.config.command_timeout,
                runner,
                "QNX worker manifest download",
            )
            manifest_bytes = local_manifest.read_bytes()
            actual_manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
            if actual_manifest_hash != expected_manifest_hash:
                raise QnxRunnerError(
                    "QNX clip worker manifest hash mismatch; target deployment is not trusted"
                )
            try:
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise QnxRunnerError("QNX clip worker manifest is invalid JSON: %s" % exc) from exc
            if not isinstance(manifest, dict):
                raise QnxRunnerError("QNX clip worker manifest must be a JSON object")
            if (
                manifest.get("schema_version") != 1
                or manifest.get("contract") != "holy-crap.clip-assessment.v1"
                or manifest.get("worker_path") != worker
                or manifest.get("platform") != "QNX"
                or not isinstance(manifest.get("worker_sha256"), str)
                or SHA256_RE.fullmatch(manifest["worker_sha256"]) is None
            ):
                raise QnxRunnerError(
                    "QNX clip worker manifest does not match the required deployment contract"
                )

            payloads = {
                "request.json": (json.dumps(request_payload, indent=2) + "\n").encode("utf-8"),
                "clip_assessment_worker.py": self._clip_wrapper_bytes(),
            }
            if progress:
                progress(
                    10,
                    "qnx_staging",
                    "Sending the source video to QNX; the target worker will apply the selected range",
                )
            self._checked(
                self._ssh_argv("mkdir", "-p", run_dir),
                self.config.command_timeout,
                runner,
                "QNX clip run directory",
            )
            for name, data in payloads.items():
                local = stage / name
                local.write_bytes(data)
                self._checked(
                    self._scp_argv(
                        str(local), "%s:%s/.%s.part" % (self.config.ssh_alias, run_dir, name)
                    ),
                    self.config.command_timeout,
                    runner,
                    "QNX clip upload %s" % name,
                )
            # Stream the source file through scp rather than reading a potentially
            # multi-gigabyte video into API memory. The target contract applies
            # segment_start_s/segment_end_s during decode.
            self._checked(
                self._scp_argv(
                    str(video_path),
                    "%s:%s/.video.bin.part" % (self.config.ssh_alias, run_dir),
                ),
                self.config.command_timeout,
                runner,
                "QNX clip upload video.bin",
            )
            rename_chain = " && ".join(
                ["cd %s" % shlex.quote(run_dir)]
                + ["mv .%s.part %s" % (name, name) for name in payloads]
                + ["mv .video.bin.part video.bin"]
            )
            self._checked(
                self._ssh_argv(rename_chain),
                self.config.command_timeout,
                runner,
                "QNX clip atomic stage",
            )
            if progress:
                progress(15, "qnx_running", "QNX accepted the job; target worker is assessing the clip")
            helper_argv = [
                str(self.config.submit_job),
                "--host",
                self.config.ssh_alias,
                "--ssh-option",
                "BatchMode=yes",
                "--ssh-option",
                "ConnectTimeout=%d" % self.config.ssh_timeout,
            ]
            if self.config.ssh_hostname:
                helper_argv += ["--ssh-option", "HostName=%s" % self.config.ssh_hostname]
            helper_argv += [
                "--cwd",
                run_dir,
                "--timeout",
                str(self.config.job_timeout),
                "--",
                self.config.remote_python,
                "clip_assessment_worker.py",
                "--request",
                "request.json",
                "--video",
                "video.bin",
                "--worker",
                worker,
                "--manifest",
                manifest_path,
                "--result",
                "result-envelope.json",
            ]
            helper_timeout = float(
                self.config.command_timeout
            )
            proc = self._run(helper_argv, helper_timeout, runner)
            helper_output = "\n".join(
                part for part in (proc.stdout or "", proc.stderr or "") if part
            )
            if proc.returncode != 0:
                raise QnxRunnerError(
                    "QNX persistent runner submission failed (%d): %s"
                    % (proc.returncode, helper_output.strip() or "no target output")
                )
            match = re.search(r"submitted\s+(job-[A-Za-z0-9-]+)", proc.stdout or "")
            if match is None:
                raise QnxRunnerError("QNX persistent runner did not return a job id")
            runner_job_id = match.group(1)
            state_path = "%s/state/%s.json" % (
                self.config.runner_spool.rstrip("/"),
                runner_job_id,
            )
            telemetry_path = "%s/telemetry.json" % run_dir
            deadline = time.monotonic() + self.config.wait_timeout
            final_state: dict | None = None
            last_telemetry_count = -1
            while time.monotonic() < deadline:
                telemetry_proc = self._run(
                    self._ssh_argv("cat", telemetry_path),
                    self.config.command_timeout,
                    runner,
                )
                if telemetry_proc.returncode == 0 and (telemetry_proc.stdout or "").strip():
                    try:
                        live_payload = json.loads(telemetry_proc.stdout)
                    except ValueError:
                        live_payload = None
                    samples = live_payload.get("samples") if isinstance(live_payload, dict) else None
                    if isinstance(samples, list) and len(samples) != last_telemetry_count:
                        last_telemetry_count = len(samples)
                        if telemetry:
                            telemetry(samples)
                        if progress:
                            progress(
                                min(90, 15 + len(samples)),
                                "qnx_running",
                                "QNX target is assessing the clip (%d telemetry samples)"
                                % len(samples),
                            )
                state_proc = self._run(
                    self._ssh_argv("cat", state_path),
                    self.config.command_timeout,
                    runner,
                )
                if state_proc.returncode == 0 and (state_proc.stdout or "").strip():
                    try:
                        state_value = json.loads(state_proc.stdout)
                    except ValueError:
                        state_value = None
                    if isinstance(state_value, dict) and state_value.get("status") in (
                        "done",
                        "failed",
                    ):
                        final_state = state_value
                        break
                time.sleep(1)
            if final_state is None:
                raise QnxRunnerError(
                    "timed out waiting for QNX clip job; it may still be running on the target"
                )

            # Even a blocked worker writes a result envelope before the runner
            # reports its nonzero exit. Retrieve that receipt before classifying
            # the assessment outcome.
            envelope_path = stage / "result-envelope.json"
            download = self._run(
                self._scp_argv(
                    "%s:%s/result-envelope.json" % (self.config.ssh_alias, run_dir),
                    str(envelope_path),
                ),
                self.config.command_timeout,
                runner,
            )
            if download.returncode != 0 or not envelope_path.is_file():
                if final_state.get("status") == "failed":
                    raise QnxRunnerError(
                        "QNX persistent runner failed (%s) without a result envelope"
                        % final_state.get("exit_code")
                    )
                raise QnxRunnerError("QNX target did not return a clip assessment envelope")
            try:
                envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise QnxRunnerError("QNX clip result envelope is invalid JSON: %s" % exc) from exc
            self._validate_clip_envelope(envelope, job_id)
            if progress:
                progress(98, "qnx_receipt", "Validated QNX target identity and result receipt")
            return QnxClipAssessmentOutcome(
                status=envelope["status"],
                message=envelope["message"],
                target=envelope["target"],
                telemetry_history=envelope["telemetry_history"],
                assessment=envelope.get("assessment"),
                helper_output=helper_output,
                remote_run_dir=run_dir,
            )

    @staticmethod
    def _validate_clip_envelope(envelope: object, job_id: str) -> None:
        if not isinstance(envelope, dict):
            raise QnxRunnerError("QNX clip result envelope must be a JSON object")
        if envelope.get("schema_version") != 1 or envelope.get("job_id") != job_id:
            raise QnxRunnerError("QNX clip result envelope does not match the submitted job")
        if envelope.get("executor") != "qnx":
            raise QnxRunnerError("QNX clip result envelope has the wrong executor")
        if envelope.get("status") not in ("completed", "blocked", "failed"):
            raise QnxRunnerError("QNX clip result envelope has an invalid status")
        if not isinstance(envelope.get("message"), str):
            raise QnxRunnerError("QNX clip result envelope is missing a message")
        target = envelope.get("target")
        if (
            not isinstance(target, dict)
            or target.get("executor") != "qnx"
            or target.get("system") != "QNX"
            or target.get("verified") is not True
        ):
            raise QnxRunnerError("QNX clip result did not prove a QNX target identity")
        telemetry = envelope.get("telemetry_history")
        if not isinstance(telemetry, list):
            raise QnxRunnerError("QNX clip result is missing telemetry history")
        if envelope.get("status") == "completed" and not isinstance(
            envelope.get("assessment"), dict
        ):
            raise QnxRunnerError("completed QNX clip result is missing the assessment")

    def validate_on_target(
        self,
        *,
        run_id: str,
        model_path: Path,
        model_name: str,
        scenario_path: Path,
        scenario_name: str,
        runner: RunnerCallable | None = None,
    ) -> QnxValidationOutcome:
        """Stage one model and one scenario, run the probe on the Pi, and validate the receipt.

        Never claims inference; the remote worker reports ``inference_performed: false``
        and this method refuses receipts that claim otherwise. Remote files are kept
        for audit.
        """
        if not self.config.enabled:
            raise QnxRunnerError(
                "QNX executor is disabled (QNX_EXECUTOR_MODE=%r); set it to 'probe' before "
                "running target validation" % self.config.mode
            )
        run_id = self._validate_run_id(run_id)
        self._validate_name("model name", model_name)
        self._validate_name("scenario name", scenario_name)

        model_path = Path(model_path).expanduser().resolve()
        scenario_path = Path(scenario_path).expanduser().resolve()
        if not model_path.is_file():
            raise QnxRunnerError("model file does not exist: %s" % model_path)
        if not scenario_path.is_file():
            raise QnxRunnerError("scenario file does not exist: %s" % scenario_path)
        try:
            model_bytes = model_path.read_bytes()
        except OSError as exc:
            raise QnxRunnerError("cannot read model file %s: %s" % (model_path, exc)) from exc
        try:
            scenario_bytes = scenario_path.read_bytes()
        except OSError as exc:
            raise QnxRunnerError("cannot read scenario file %s: %s" % (scenario_path, exc)) from exc
        try:
            json.loads(scenario_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise QnxRunnerError("scenario file is not valid UTF-8 JSON: %s" % exc) from exc

        model_hash = hashlib.sha256(model_bytes).hexdigest()
        scenario_hash = hashlib.sha256(scenario_bytes).hexdigest()
        request = {
            "run_id": run_id,
            "model": {"name": model_name, "sha256": model_hash},
            "scenario": {"name": scenario_name, "sha256": scenario_hash},
        }
        payloads = {
            "model.bin": model_bytes,
            "scenario.json": scenario_bytes,
            "request.json": (json.dumps(request, indent=2) + "\n").encode("utf-8"),
            "simlab_probe.py": self._worker_bytes(),
        }

        run_dir = "%s/run-%s" % (self.config.remote_root.rstrip("/"), run_id)
        with tempfile.TemporaryDirectory(prefix="qnx-stage-") as temp_name:
            stage = Path(temp_name)
            for name, data in payloads.items():
                (stage / name).write_bytes(data)

            self._checked(
                self._ssh_argv("mkdir", "-p", run_dir),
                self.config.command_timeout,
                runner,
                "mkdir",
            )
            for name in payloads:
                self._checked(
                    self._scp_argv(
                        str(stage / name),
                        "%s:%s/.%s.part" % (self.config.ssh_alias, run_dir, name),
                    ),
                    self.config.command_timeout,
                    runner,
                    "scp %s" % name,
                )
            rename_chain = " && ".join(
                ["cd %s" % shlex.quote(run_dir)]
                + ["mv .%s.part %s" % (name, name) for name in payloads]
            )
            self._checked(
                self._ssh_argv(rename_chain),
                self.config.command_timeout,
                runner,
                "remote rename",
            )

            helper_argv = [
                str(self.config.submit_job),
                "--host",
                self.config.ssh_alias,
                "--ssh-option",
                "BatchMode=yes",
                "--ssh-option",
                "ConnectTimeout=%d" % self.config.ssh_timeout,
            ]
            if self.config.ssh_hostname:
                helper_argv += [
                    "--ssh-option",
                    "HostName=%s" % self.config.ssh_hostname,
                ]
            helper_argv += [
                "--cwd",
                run_dir,
                "--timeout",
                str(self.config.job_timeout),
                "--wait",
                "--wait-timeout",
                str(self.config.wait_timeout),
                "--",
                self.config.remote_python,
                "simlab_probe.py",
                "--request",
                "request.json",
                "--scenario",
                "scenario.json",
                "--model",
                "model.bin",
                "--result",
                "receipt.json",
            ]
            helper_timeout = float(
                self.config.command_timeout + self.config.job_timeout + self.config.wait_timeout
            )
            proc = self._run(helper_argv, helper_timeout, runner)
            helper_output = "\n".join(
                part for part in (proc.stdout or "", proc.stderr or "") if part
            )
            if proc.returncode != 0:
                raise QnxRunnerError(
                    "runner helper exited %d: %s"
                    % (proc.returncode, helper_output.strip() or "(no output)")
                )

            receipt_local = stage / "receipt.json"
            self._checked(
                self._scp_argv(
                    "%s:%s/receipt.json" % (self.config.ssh_alias, run_dir),
                    str(receipt_local),
                ),
                self.config.command_timeout,
                runner,
                "receipt download",
            )
            try:
                receipt = json.loads(receipt_local.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise QnxRunnerError("malformed receipt JSON: %s" % exc) from exc
            if not isinstance(receipt, dict):
                raise QnxRunnerError("malformed receipt: expected a JSON object")
            self._validate_receipt(receipt, run_id, model_hash, scenario_hash)

        return QnxValidationOutcome(
            receipt=receipt,
            helper_output=helper_output,
            remote_run_dir=run_dir,
        )

    @staticmethod
    def _validate_receipt(
        receipt: dict, run_id: str, model_hash: str, scenario_hash: str
    ) -> None:
        if receipt.get("schema_version") != 1:
            raise QnxRunnerError("receipt schema_version must be 1, got %r" % receipt.get("schema_version"))
        if receipt.get("run_id") != run_id:
            raise QnxRunnerError(
                "receipt run_id %r does not match requested %r" % (receipt.get("run_id"), run_id)
            )
        model = receipt.get("model")
        scenario = receipt.get("scenario")
        if not isinstance(model, dict) or model.get("sha256") != model_hash:
            raise QnxRunnerError("receipt model hash does not match the staged model")
        if not isinstance(scenario, dict) or scenario.get("sha256") != scenario_hash:
            raise QnxRunnerError("receipt scenario hash does not match the staged scenario")
        if receipt.get("inference_performed") is not False:
            raise QnxRunnerError("receipt must report inference_performed=false")


# --- edge status normalization ------------------------------------------------
#
# The edge pipeline's status JSON is untrusted target output. Everything below
# converts it into the typed QnxRuntimeResponse without ever raising: malformed
# or unrecognized payloads become status=partial with a concise truthful
# detail, and wrongly typed fields are dropped with a warning instead of
# crashing the API.


class _EdgeFieldReader:
    """Strict type checks that never raise; collects what was ignored."""

    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warn(self, text: str) -> None:
        if len(self.warnings) < 20:
            self.warnings.append(text)

    def _bad(self, label: str, value: object) -> None:
        self.warn("ignored malformed %s %r" % (label, repr(value)[:80]))

    def integer(self, value: object, label: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            self._bad(label, value)
            return None
        return value

    def number(self, value: object, label: str) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._bad(label, value)
            return None
        if not math.isfinite(value):
            self._bad(label, value)
            return None
        return float(value)

    def flag(self, value: object, label: str) -> bool | None:
        if value is None:
            return None
        if not isinstance(value, bool):
            self._bad(label, value)
            return None
        return value

    def text(self, value: object, label: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            self._bad(label, value)
            return None
        if not value.strip():
            return None
        return value[:256]


def _pick(documents: Sequence[dict], keys: Sequence[str]) -> object:
    """First present key across documents; target blocks are merged caller-side."""
    for document in documents:
        for key in keys:
            if key in document:
                return document[key]
    return None


def _safe_model(factory: Callable[[], object], reader: _EdgeFieldReader, label: str,
                fallback: object = None) -> object:
    try:
        return factory()
    except (ValidationError, ValueError, TypeError) as exc:
        reader.warn("%s were rejected: %s" % (label, exc))
        return fallback


def _read_datetime(value: object) -> datetime | None:
    """Accept ISO strings or numeric epoch seconds; unknown formats stay null."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return None


def _runtime_target(ssh_alias: str) -> ClipAssessmentTarget:
    """The configured transport identity, explicitly unverified by status."""
    return ClipAssessmentTarget(
        executor="qnx",
        hostname=ssh_alias,
        verified=False,
        detail="target identity is not proven by the edge status endpoint",
    )


def _runtime_partial(
    detail: str, ssh_alias: str, fault_tests_enabled: bool
) -> QnxRuntimeResponse:
    return QnxRuntimeResponse(
        status=QnxRuntimeStatus.PARTIAL,
        detail="edge-stream runtime only; not the clip-assessment worker. " + detail,
        target=_runtime_target(ssh_alias),
        # A malformed or legacy payload cannot prove the independent target
        # gate, so the effective gate always fails closed.
        fault_tests_enabled=False,
        target_fault_tests_enabled=None,
    )


def _normalize_processes(source: object, reader: _EdgeFieldReader) -> list[QnxRuntimeProcess]:
    entries: list[tuple[str, object]] = []
    if isinstance(source, dict):
        entries = [(str(key)[:128], value) for key, value in source.items()]
    elif isinstance(source, list):
        for item in source:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                entries.append((item["name"][:128], item))
            else:
                reader.warn("ignored a malformed process entry")
    processes: list[QnxRuntimeProcess] = []
    for name, raw in entries:
        if not isinstance(raw, dict):
            reader.warn("ignored malformed process entry %r" % name)
            continue
        entry: dict = raw
        pid = reader.integer(entry.get("pid"), "pid")
        configured = reader.integer(entry.get("priority"), "configured priority")
        observed_priority = reader.integer(
            _pick([entry], ("observedPriority", "observed_priority")), "observed priority"
        )
        policy = reader.text(
            _pick([entry], ("policy", "schedulingPolicy", "scheduling_policy")),
            "scheduling policy",
        )
        runmask = reader.text(_pick([entry], ("runmask",)), "runmask")
        observation_detail = reader.text(
            _pick([entry], ("observedDetail", "observation_detail")),
            "observation detail",
        )
        observed_block = entry.get("observed")
        if isinstance(observed_block, dict):
            if observed_priority is None:
                observed_priority = reader.integer(
                    observed_block.get("priority"), "observed priority"
                )
            if policy is None:
                policy = reader.text(observed_block.get("policy"), "scheduling policy")
            if runmask is None:
                runmask = reader.text(observed_block.get("runmask"), "runmask")
        restarts = reader.integer(entry.get("restarts"), "restarts")
        started = _read_datetime(_pick([entry], ("startedAt", "started_at", "started")))
        last_exit_raw = _pick([entry], ("lastExit", "last_exit"))
        last_exit = (
            reader.integer(last_exit_raw, "lastExit") if last_exit_raw is not None else None
        )
        respawn = reader.number(
            _pick([entry], ("downFor", "respawnMs", "respawn_ms")), "respawn ms"
        )
        ready = reader.flag(_pick([entry], ("ready",)), "ready")
        process = _safe_model(
            lambda: QnxRuntimeProcess(
                name=name,
                pid=pid,
                configured_priority=configured,
                observed_priority=observed_priority,
                scheduling_policy=policy,
                runmask=runmask,
                observation_detail=observation_detail,
                restarts=restarts,
                started_at=started,
                last_exit=last_exit,
                respawn_ms=respawn,
                ready=ready,
            ),
            reader,
            "process %s" % name,
            fallback=QnxRuntimeProcess(name=name),
        )
        processes.append(process)
    return processes


def _normalize_capture(
    capture_block: dict, timing_block: dict, data: dict, reader: _EdgeFieldReader
) -> QnxRuntimeCapture | None:
    sources = [capture_block, timing_block, data]
    frames = reader.integer(_pick(sources, ("frames",)), "frames")
    fps = reader.number(_pick(sources, ("fps",)), "fps")
    dropped = reader.integer(_pick(sources, ("dropped",)), "dropped")
    warm = reader.flag(_pick(sources, ("warm",)), "warm")
    last_frame_age = reader.number(
        _pick(sources, ("lastFrameAgeS", "last_frame_age_s")), "lastFrameAgeS"
    )
    if last_frame_age is None:
        last_frame = reader.number(
            _pick(sources, ("lastFrame", "last_frame")), "lastFrame"
        )
        captured = reader.number(
            _pick(sources, ("now", "capturedAt", "captured_at")), "capture timestamp"
        )
        if last_frame is not None and captured is not None and captured >= last_frame:
            last_frame_age = captured - last_frame
    target_period = reader.number(
        _pick(sources, ("targetPeriodMs", "target_period_ms")), "targetPeriodMs"
    )
    if target_period is None:
        rate = reader.number(
            _pick(sources, ("rate", "targetRate", "target_rate")), "capture rate"
        )
        if rate is not None and rate > 0:
            target_period = 1000.0 / rate
    period_p50 = reader.number(
        _pick(sources, ("periodP50Ms", "period_p50_ms")), "periodP50Ms"
    )
    period_p95 = reader.number(
        _pick(sources, ("periodP95Ms", "period_p95_ms")), "periodP95Ms"
    )
    period_p99 = reader.number(
        _pick(sources, ("periodP99Ms", "period_p99_ms")), "periodP99Ms"
    )
    period_max = reader.number(
        _pick(sources, ("periodMaxMs", "period_max_ms")), "periodMaxMs"
    )
    deadline_misses = reader.integer(
        _pick(sources, ("deadlineMisses", "deadline_misses")), "deadlineMisses"
    )
    deadline_miss_percent = reader.number(
        _pick(sources, ("deadlineMissPercent", "deadline_miss_percent")),
        "deadlineMissPercent",
    )
    sample_count = reader.integer(
        _pick(sources, ("sampleCount", "sample_count")), "sampleCount"
    )
    return _safe_model(
        lambda: QnxRuntimeCapture(
            frames=frames,
            fps=fps,
            dropped=dropped,
            warm=warm,
            last_frame_age_s=last_frame_age,
            target_period_ms=target_period,
            period_p50_ms=period_p50,
            period_p95_ms=period_p95,
            period_p99_ms=period_p99,
            period_max_ms=period_max,
            deadline_misses=deadline_misses,
            deadline_miss_percent=deadline_miss_percent,
            sample_count=sample_count,
        ),
        reader,
        "capture metrics",
    )


def _normalize_resources(
    data: dict, reader: _EdgeFieldReader
) -> ResourceTelemetrySample | None:
    resources_block = data.get("resources")
    model_stats = data.get("modelStats")
    if not isinstance(model_stats, dict):
        model_stats = data.get("model_stats")
    model_resources = model_stats.get("resources") if isinstance(model_stats, dict) else None
    sources = []
    if isinstance(resources_block, dict):
        sources.append(resources_block)
    if isinstance(model_resources, dict):
        sources.append(model_resources)
    if isinstance(model_stats, dict):
        sources.append(model_stats)
    sources.append(data)
    cpu = reader.number(_pick(sources, ("cpuPercent", "cpu_percent")), "cpuPercent")
    ram_used = reader.integer(
        _pick(sources, ("ramUsedBytes", "ram_used_bytes")), "ramUsedBytes"
    )
    ram_total = reader.integer(
        _pick(sources, ("ramTotalBytes", "ram_total_bytes")), "ramTotalBytes"
    )
    proc_cpu = reader.number(
        _pick(sources, ("processCpuPercent", "process_cpu_percent")), "processCpuPercent"
    )
    proc_ram = reader.integer(
        _pick(sources, ("processRamBytes", "process_ram_bytes")), "processRamBytes"
    )
    detail = reader.text(_pick(sources, ("detail",)), "resource detail")
    if all(value is None for value in (cpu, ram_used, ram_total, proc_cpu, proc_ram)):
        return None
    return _safe_model(
        lambda: ResourceTelemetrySample(
            captured_at=utc_now(),
            source="qnx",
            cpu_percent=cpu,
            ram_used_bytes=ram_used,
            ram_total_bytes=ram_total,
            process_cpu_percent=proc_cpu,
            process_ram_bytes=proc_ram,
            detail=detail or "normalized from the edge status resource fields",
        ),
        reader,
        "resource fields",
    )


def _normalize_model_timing(
    data: dict, reader: _EdgeFieldReader
) -> QnxRuntimeModelTiming | None:
    direct = data.get("modelTiming")
    if not isinstance(direct, dict):
        direct = data.get("model_timing")
    stats = data.get("modelStats")
    if not isinstance(stats, dict):
        stats = data.get("model_stats")
    if isinstance(direct, dict):
        timing = direct
    elif isinstance(stats, dict):
        timing = stats.get("successfulInferenceTiming")
        if not isinstance(timing, dict):
            timing = stats.get("successful_inference_timing")
        if not isinstance(timing, dict):
            timing = stats.get("inferenceTiming")
        if not isinstance(timing, dict):
            timing = stats.get("inference_timing")
        if not isinstance(timing, dict):
            # Some status implementations expose the timing object directly.
            timing = stats
    else:
        return None
    sample_count = reader.integer(
        _pick([timing], ("sampleCount", "sample_count")), "model timing sampleCount"
    )
    last_ms = reader.number(_pick([timing], ("lastMs", "last_ms")), "model timing lastMs")
    p50_ms = reader.number(_pick([timing], ("p50Ms", "p50_ms")), "model timing p50Ms")
    p95_ms = reader.number(_pick([timing], ("p95Ms", "p95_ms")), "model timing p95Ms")
    p99_ms = reader.number(_pick([timing], ("p99Ms", "p99_ms")), "model timing p99Ms")
    max_ms = reader.number(_pick([timing], ("maxMs", "max_ms")), "model timing maxMs")
    failed = None
    if isinstance(stats, dict):
        failed = stats.get("failedAttemptTiming")
        if not isinstance(failed, dict):
            failed = stats.get("failed_attempt_timing")
    failed = failed if isinstance(failed, dict) else {}
    failed_sample_count = reader.integer(
        _pick([failed], ("sampleCount", "sample_count")), "failed model timing sampleCount"
    )
    failed_last_ms = reader.number(_pick([failed], ("lastMs", "last_ms")), "failed model timing lastMs")
    failed_p50_ms = reader.number(_pick([failed], ("p50Ms", "p50_ms")), "failed model timing p50Ms")
    failed_p95_ms = reader.number(_pick([failed], ("p95Ms", "p95_ms")), "failed model timing p95Ms")
    failed_p99_ms = reader.number(_pick([failed], ("p99Ms", "p99_ms")), "failed model timing p99Ms")
    failed_max_ms = reader.number(_pick([failed], ("maxMs", "max_ms")), "failed model timing maxMs")
    counter_source = stats if isinstance(stats, dict) else direct if isinstance(direct, dict) else {}
    checked = reader.integer(_pick([counter_source], ("checked",)), "model checked")
    unreachable = reader.integer(_pick([counter_source], ("unreachable",)), "model unreachable")
    worker_errors = reader.integer(
        _pick([counter_source], ("workerErrors", "worker_errors")), "model workerErrors"
    )
    evicted = reader.integer(_pick([counter_source], ("evicted",)), "model evicted")
    dropped = reader.integer(_pick([counter_source], ("dropped",)), "model dropped")
    all_values = (
        sample_count, last_ms, p50_ms, p95_ms, p99_ms, max_ms,
        failed_sample_count, failed_last_ms, failed_p50_ms, failed_p95_ms,
        failed_p99_ms, failed_max_ms, checked, unreachable, worker_errors, evicted, dropped,
    )
    if all(value is None for value in all_values):
        return None
    return _safe_model(
        lambda: QnxRuntimeModelTiming(
            sample_count=sample_count,
            last_ms=last_ms,
            p50_ms=p50_ms,
            p95_ms=p95_ms,
            p99_ms=p99_ms,
            max_ms=max_ms,
            failed_sample_count=failed_sample_count,
            failed_last_ms=failed_last_ms,
            failed_p50_ms=failed_p50_ms,
            failed_p95_ms=failed_p95_ms,
            failed_p99_ms=failed_p99_ms,
            failed_max_ms=failed_max_ms,
            checked=checked,
            unreachable=unreachable,
            worker_errors=worker_errors,
            evicted=evicted,
            dropped=dropped,
        ),
        reader,
        "model timing",
    )


def _normalize_correlation(
    data: dict, reader: _EdgeFieldReader
) -> QnxRuntimeCorrelation | None:
    block = data.get("correlation")
    sources = [block, data] if isinstance(block, dict) else [data]
    job_id = reader.text(_pick(sources, ("jobId", "job_id")), "correlation job id")

    def digest(keys: tuple[str, ...], label: str) -> str | None:
        value = reader.text(_pick(sources, keys), label)
        if value is None:
            return None
        if SHA256_RE.fullmatch(value) is None:
            reader.warn("ignored malformed %s" % label)
            return None
        return value

    clip_sha256 = digest(("clipSha256", "clip_sha256"), "clip sha256")
    model_sha256 = digest(("modelSha256", "model_sha256"), "model sha256")
    worker_sha256 = digest(("workerSha256", "worker_sha256"), "worker sha256")
    if all(value is None for value in (job_id, clip_sha256, model_sha256, worker_sha256)):
        return None
    return _safe_model(
        lambda: QnxRuntimeCorrelation(
            job_id=job_id,
            clip_sha256=clip_sha256,
            model_sha256=model_sha256,
            worker_sha256=worker_sha256,
        ),
        reader,
        "runtime correlation",
    )


def _normalize_latest_fault(data: dict, reader: _EdgeFieldReader) -> QnxFaultEvent | None:
    events = data.get("faults")
    if not isinstance(events, list) or not events:
        events = data.get("crashes")
    if not isinstance(events, list) or not events:
        return None
    event = events[-1]
    if not isinstance(event, dict):
        reader.warn("the latest fault event is not an object")
        return None
    process = reader.text(
        _pick([event], ("proc", "process", "name")), "fault process"
    )
    if not process:
        reader.warn("the latest fault event is missing its process name")
        return None
    old_pid = reader.integer(_pick([event], ("oldPid", "old_pid", "pid")), "fault old pid")
    new_pid = reader.integer(_pick([event], ("newPid", "new_pid")), "fault new pid")
    requested_at = _read_datetime(_pick([event], ("requestedAt", "requested_at", "t")))
    detected_at = _read_datetime(_pick([event], ("detectedAt", "detected_at")))
    spawned_at = _read_datetime(_pick([event], ("spawnedAt", "spawned_at")))
    ready_at = _read_datetime(_pick([event], ("readyAt", "ready_at")))
    first_result_at = _read_datetime(_pick([event], ("firstResultAt", "first_result_at")))
    respawn_ms = reader.number(_pick([event], ("respawnMs", "respawn_ms")), "respawn ms")
    recovery_ms = reader.number(
        _pick([event], ("recoveryMs", "recovery_ms")), "recovery ms"
    )
    state = reader.text(_pick([event], ("state",)), "fault state")
    if state is None:
        state = "respawned" if new_pid is not None else "requested"
    return _safe_model(
        lambda: QnxFaultEvent(
            process=process[:128],
            old_pid=old_pid,
            new_pid=new_pid,
            requested_at=requested_at,
            detected_at=detected_at,
            spawned_at=spawned_at,
            ready_at=ready_at,
            first_result_at=first_result_at,
            respawn_ms=respawn_ms,
            recovery_ms=recovery_ms,
            state=state[:64],
        ),
        reader,
        "the latest fault event",
    )


def normalize_edge_status_payload(
    payload: object,
    *,
    ssh_alias: str,
    fault_tests_enabled: bool,
) -> QnxRuntimeResponse:
    """Normalize an untrusted edge status payload; never raises."""
    reader = _EdgeFieldReader()
    target = _runtime_target(ssh_alias)
    if not isinstance(payload, dict):
        return _runtime_partial(
            "target edge status is not a JSON object",
            ssh_alias,
            fault_tests_enabled,
        )
    data = dict(payload)
    block = data.get("runtime")
    if isinstance(block, dict):
        data.update(block)
    procs = data.get("procs")
    processes_source: object = procs if isinstance(procs, dict) else data.get("processes")
    native_ipc = reader.flag(_pick([data], ("nativeIpc", "native_ipc")), "nativeIpc")
    recognized = (
        isinstance(procs, dict)
        or isinstance(processes_source, list)
        or native_ipc is not None
    )
    if not recognized:
        return _runtime_partial(
            (
                "target edge status is missing expected fields (procs/nativeIpc); "
                "the target may be running an older pipeline"
            ),
            ssh_alias,
            fault_tests_enabled,
        )
    capture_block = data.get("capture")
    capture_block = capture_block if isinstance(capture_block, dict) else {}
    timing_block = data.get("captureTiming")
    if not isinstance(timing_block, dict):
        timing_block = data.get("capture_timing", {})
    timing_block = timing_block if isinstance(timing_block, dict) else {}
    processes = _normalize_processes(processes_source, reader)
    capture = _normalize_capture(capture_block, timing_block, data, reader)
    resources = _normalize_resources(data, reader)
    model_timing = _normalize_model_timing(data, reader)
    correlation = _normalize_correlation(data, reader)
    latest_fault = _normalize_latest_fault(data, reader)
    source_mode = reader.text(
        _pick([data], ("source", "sourceMode", "source_mode")), "source"
    )
    scheduler_profile = reader.text(
        _pick([data], ("schedulerProfile", "scheduler_profile")), "schedulerProfile"
    )
    qnx_priorities_active = reader.flag(
        _pick([data], ("qnxPrioritiesActive", "qnx_priorities_active")),
        "qnxPrioritiesActive",
    )
    target_status_schema = reader.text(
        _pick([data], ("statusSchema", "status_schema", "schema", "contract")),
        "target status schema",
    )
    version_raw = _pick(
        [data],
        ("statusVersion", "status_version", "schemaVersion", "schema_version", "version"),
    )
    target_status_version: int | str | None
    if version_raw is None:
        target_status_version = None
    elif isinstance(version_raw, bool) or not isinstance(version_raw, (int, str)):
        reader.warn("ignored malformed target status version %r" % repr(version_raw)[:80])
        target_status_version = None
    elif isinstance(version_raw, str) and not version_raw.strip():
        target_status_version = None
    else:
        target_status_version = version_raw
    target_fault_tests_enabled = reader.flag(
        _pick([data], ("faultTestsEnabled", "fault_tests_enabled")),
        "target faultTestsEnabled",
    )

    missing: list[str] = []
    if native_ipc is None:
        missing.append("nativeIpc")
    if not processes:
        missing.append("processes")
    elif not any(process.pid is not None and process.pid > 0 for process in processes):
        missing.append("live process PID")
    if source_mode is None:
        missing.append("source")
    if capture is None or capture.frames is None:
        missing.append("capture.frames")
    if capture is None or capture.fps is None:
        missing.append("capture.fps")
    if capture is None or capture.dropped is None:
        missing.append("capture.dropped")
    schema_pairs = {
        ("holy-crap.edge-telemetry", 1),
        ("holy-crap.edge-status", 2),
    }
    if target_status_schema is None:
        missing.append("status schema")
    if target_status_version is None:
        missing.append("status version")
    if (target_status_schema is not None and target_status_version is not None
            and (target_status_schema, target_status_version) not in schema_pairs):
        reader.warn(
            "unsupported target status contract %r v%r"
            % (target_status_schema, target_status_version)
        )

    status = (
        QnxRuntimeStatus.PARTIAL
        if reader.warnings or missing
        else QnxRuntimeStatus.READY
    )
    detail = (
        "edge-stream runtime normalized from the target; this is not the "
        "clip-assessment worker"
    )
    if missing:
        detail += " (missing essential fields: %s)" % ", ".join(missing)
    if reader.warnings:
        shown = "; ".join(reader.warnings[:3])
        if len(reader.warnings) > 3:
            shown += "; and %d more" % (len(reader.warnings) - 3)
        detail += " (normalization warnings: %s)" % shown
    return QnxRuntimeResponse(
        status=status,
        captured_at=utc_now(),
        detail=detail,
        target=target,
        native_ipc=native_ipc,
        source_mode=source_mode,
        scheduler_profile=scheduler_profile,
        qnx_priorities_active=qnx_priorities_active,
        target_status_schema=target_status_schema,
        target_status_version=target_status_version,
        correlation=correlation,
        capture=capture,
        model_timing=model_timing,
        processes=processes,
        resources=resources,
        fault_tests_enabled=(
            fault_tests_enabled and target_fault_tests_enabled is True
        ),
        target_fault_tests_enabled=target_fault_tests_enabled,
        latest_fault=latest_fault,
    )


def normalize_edge_status(
    output: str,
    *,
    ssh_alias: str,
    fault_tests_enabled: bool,
) -> QnxRuntimeResponse:
    """Normalize untrusted edge status text into the typed runtime response.

    Transport failures belong to the caller; this function turns anything else
    into an honest ready/partial snapshot and never raises.
    """
    if not output or not output.strip():
        return _runtime_partial(
            "the target edge status endpoint returned empty output",
            ssh_alias,
            fault_tests_enabled,
        )
    try:
        payload = json.loads(output)
    except ValueError as exc:
        return _runtime_partial(
            "target edge status is not valid JSON: %s" % exc,
            ssh_alias,
            fault_tests_enabled,
        )
    return normalize_edge_status_payload(
        payload, ssh_alias=ssh_alias, fault_tests_enabled=fault_tests_enabled
    )


def normalize_edge_crash_response(
    process_name: str, payload: object, output: str = ""
) -> QnxFaultTestResponse:
    """Normalize an untrusted edge /crash response; never raises."""
    if isinstance(payload, dict):
        if "accepted" in payload and payload.get("accepted") is not True:
            detail = payload.get("error") or payload.get("detail")
            return QnxFaultTestResponse(
                process=process_name,
                accepted=False,
                detail=(
                    str(detail)[:256]
                    if detail
                    else "target explicitly rejected the fault test"
                ),
            )
        killed = payload.get("killed")
        pid = payload.get("pid")
        if (
            killed == process_name
            and isinstance(pid, int)
            and not isinstance(pid, bool)
            and pid > 0
        ):
            return QnxFaultTestResponse(process=process_name, accepted=True, pid=pid)
        if isinstance(killed, str):
            reasons = []
            if killed != process_name:
                reasons.append(
                    "target reported process %r instead of %r" % (killed, process_name)
                )
            if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
                reasons.append("target did not report a positive pid")
            return QnxFaultTestResponse(
                process=process_name,
                accepted=False,
                detail="; ".join(reasons) or "unrecognized target response",
            )
        if payload.get("error"):
            return QnxFaultTestResponse(
                process=process_name,
                accepted=False,
                detail=str(payload.get("error"))[:256],
            )
    detail = "unrecognized target response"
    if output:
        detail += ": %s" % output[:200]
    return QnxFaultTestResponse(process=process_name, accepted=False, detail=detail)
