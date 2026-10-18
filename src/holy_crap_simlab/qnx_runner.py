"""Transport to the headless QNX Pi: probing, staging, and target validation.

This module never claims to run inference on the Pi. Its target-validation
mode proves that one exact model file and one canonical scenario JSON reached
the physical QNX Pi and were processed there, by running the dependency-free
`target/qnx/simlab_probe.py` worker through the persistent qnx-runner.

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
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .models import AdapterCapability

RUN_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

DEFAULT_SUBMIT_JOB = Path(__file__).resolve().parents[2] / "scripts" / "qnx_submit_job.py"

_BEGIN_PYTHON = "SIMLAB_PROBE_PYTHON_BEGIN"
_END_PYTHON = "SIMLAB_PROBE_PYTHON_END"
_BEGIN_RUNNER = "SIMLAB_PROBE_RUNNER_BEGIN"
_END_RUNNER = "SIMLAB_PROBE_RUNNER_END"
_BEGIN_RUNTIMES = "SIMLAB_PROBE_RUNTIMES_BEGIN"
_END_RUNTIMES = "SIMLAB_PROBE_RUNTIMES_END"

PROBE_RUNTIME_MODULES = ("tflite_runtime", "onnxruntime", "cv2", "numpy")


class QnxRunnerError(RuntimeError):
    """A QNX transport step failed, was rejected, or timed out."""


@dataclass(frozen=True)
class QnxRunnerConfig:
    """Configuration loaded from the environment (see from_env)."""

    mode: str = "disabled"  # QNX_EXECUTOR_MODE: "disabled" | "probe"
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
        if mode not in ("disabled", "probe"):
            raise QnxRunnerError(
                "QNX_EXECUTOR_MODE must be 'disabled' or 'probe', got %r" % mode
            )
        worker_raw = text("QNX_WORKER_PATH", "")
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
        )

    @property
    def enabled(self) -> bool:
        return self.mode == "probe"


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


RunnerCallable = Callable[..., "subprocess.CompletedProcess[str]"]


def default_runner(
    argv: Sequence[str], timeout: float | None = None
) -> "subprocess.CompletedProcess[str]":
    """Real subprocess runner: argv list only, never a shell."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


class QnxRunner:
    """Probe and target-validate the QNX Pi without ever claiming inference."""

    def __init__(self, config: QnxRunnerConfig | None = None) -> None:
        self.config = config or QnxRunnerConfig.from_env()

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
            return (runner or default_runner)(argv, timeout=timeout)
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
                detail="QNX executor disabled (QNX_EXECUTOR_MODE=%r); set it to 'probe'"
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
