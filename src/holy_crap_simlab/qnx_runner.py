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
import os
import re
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from .models import AdapterCapability

RUN_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CLIP_JOB_ID_RE = re.compile(
    r"^clip-job-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
