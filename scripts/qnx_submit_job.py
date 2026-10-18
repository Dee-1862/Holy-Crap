#!/usr/bin/env python3
"""Submit an argv-only job to the persistent runner on the QNX target.

Repeated ``--ssh-option KEY=VALUE`` arguments apply the same connection
settings to every ssh and scp call. This supports direct Ethernet links where
the stable ``qnxpi`` alias supplies the identity and trusted host-key alias,
while a HostName override supplies the current link-local address.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid

DEFAULT_HOST = "qnxpi"
DEFAULT_REMOTE_SPOOL = "/data/home/qnxuser/qnx-runner"
DEFAULT_WAIT_TIMEOUT = 600
DEFAULT_POLL = 1
MIN_TIMEOUT = 1
MAX_TIMEOUT = 86400


def _transport_argv(program: str, ssh_options: list[str], *arguments: str) -> list[str]:
    argv = [program]
    if program == "scp":
        argv.append("-q")
    for option in ssh_options:
        argv.extend(["-o", option])
    argv.extend(arguments)
    return argv


def _run_checked(argv: list[str]) -> bool:
    try:
        subprocess.run(argv, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(
            "transport command failed (%d): %s" % (exc.returncode, argv[0]),
            file=sys.stderr,
        )
        return False
    except OSError as exc:
        print("could not run %s: %s" % (argv[0], exc), file=sys.stderr)
        return False


def _read_remote_json(
    host: str, path: str, ssh_options: list[str]
) -> dict[str, object] | None:
    proc = subprocess.run(
        _transport_argv("ssh", ssh_options, host, "cat", path),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        value = json.loads(proc.stdout)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _wait_for_state(
    host: str,
    state_path: str,
    ssh_options: list[str],
    poll: float,
    wait_timeout: int,
) -> dict[str, object] | None:
    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        state = _read_remote_json(host, state_path, ssh_options)
        if state is not None and state.get("status") in {"done", "failed"}:
            return state
        time.sleep(poll)
    return None


def _print_remote_file(host: str, path: str, label: str, ssh_options: list[str]) -> None:
    proc = subprocess.run(
        _transport_argv("ssh", ssh_options, host, "cat", path),
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print("--- %s ---" % label)
        print(proc.stdout, end="")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qnx_submit_job.py",
        description="submit a job to the persistent qnx-runner",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--spool", default=DEFAULT_REMOTE_SPOOL)
    parser.add_argument("--cwd")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument(
        "--ssh-option",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="OpenSSH -o option applied to every ssh/scp call (repeatable)",
    )
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=DEFAULT_WAIT_TIMEOUT)
    parser.add_argument("--poll", type=float, default=DEFAULT_POLL)
    parser.add_argument("argv", nargs=argparse.REMAINDER, metavar="CMD [ARG ...]")
    args = parser.parse_args(argv)

    if args.argv and args.argv[0] == "--":
        args.argv = args.argv[1:]
    if not args.argv:
        parser.error("no command given; put '--' before the argv list")
    if args.timeout is not None and not MIN_TIMEOUT <= args.timeout <= MAX_TIMEOUT:
        parser.error("--timeout must be between %d and %d" % (MIN_TIMEOUT, MAX_TIMEOUT))
    if args.wait_timeout < 1:
        parser.error("--wait-timeout must be at least 1")
    if args.poll <= 0:
        parser.error("--poll must be greater than 0")
    for option in args.ssh_option:
        if not option or option.startswith("-") or "=" not in option:
            parser.error("--ssh-option must look like KEY=VALUE")

    environment: dict[str, str] = {}
    for specification in args.env:
        if "=" not in specification:
            parser.error("--env must look like NAME=VALUE")
        name, value = specification.split("=", 1)
        if not name:
            parser.error("--env name must not be empty")
        environment[name] = value

    job_id = "job-%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:8])
    job: dict[str, object] = {"id": job_id, "argv": args.argv}
    if args.cwd is not None:
        job["cwd"] = args.cwd
    if args.timeout is not None:
        job["timeout"] = args.timeout
    if environment:
        job["env"] = environment

    file_descriptor, local_path = tempfile.mkstemp(prefix="qnx-job-", suffix=".json")
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
            json.dump(job, stream, indent=2)
            stream.write("\n")
        temporary_remote = "%s/inbox/.%s.tmp" % (args.spool, job_id)
        final_remote = "%s/inbox/%s.json" % (args.spool, job_id)
        if not _run_checked(
            _transport_argv(
                "scp",
                args.ssh_option,
                local_path,
                "%s:%s" % (args.host, temporary_remote),
            )
        ):
            return 1
        if not _run_checked(
            _transport_argv(
                "ssh", args.ssh_option, args.host, "mv", temporary_remote, final_remote
            )
        ):
            return 1
    finally:
        try:
            os.unlink(local_path)
        except OSError:
            pass

    print("submitted %s (%d argv elements) to %s" % (job_id, len(args.argv), args.host))
    if not args.wait:
        return 0

    state_path = "%s/state/%s.json" % (args.spool, job_id)
    state = _wait_for_state(
        args.host, state_path, args.ssh_option, args.poll, args.wait_timeout
    )
    if state is None:
        print(
            "timed out after %ds waiting for job state; the job may still be running"
            % args.wait_timeout,
            file=sys.stderr,
        )
        return 124
    print(json.dumps(state, indent=2))
    _print_remote_file(
        args.host,
        "%s/logs/%s.out" % (args.spool, job_id),
        "stdout",
        args.ssh_option,
    )
    _print_remote_file(
        args.host,
        "%s/logs/%s.err" % (args.spool, job_id),
        "stderr",
        args.ssh_option,
    )
    if state.get("status") == "done":
        return int(state.get("exit_code") or 0)
    return int(state.get("exit_code") or 1)


if __name__ == "__main__":
    sys.exit(main())
