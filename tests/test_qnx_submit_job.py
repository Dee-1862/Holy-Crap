from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "qnx_submit_job.py"
SPEC = importlib.util.spec_from_file_location("qnx_submit_job", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
qnx_submit_job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qnx_submit_job)


def test_transport_argv_applies_options_to_ssh_and_scp() -> None:
    options = ["BatchMode=yes", "HostName=169.254.55.180"]

    assert qnx_submit_job._transport_argv("ssh", options, "qnxpi", "true") == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "HostName=169.254.55.180",
        "qnxpi",
        "true",
    ]
    assert qnx_submit_job._transport_argv(
        "scp", options, "local", "qnxpi:/data/remote"
    ) == [
        "scp",
        "-q",
        "-o",
        "BatchMode=yes",
        "-o",
        "HostName=169.254.55.180",
        "local",
        "qnxpi:/data/remote",
    ]


def test_wait_for_state_ignores_running_state(monkeypatch) -> None:
    states = iter(
        [
            {"status": "running", "exit_code": None},
            {"status": "done", "exit_code": 0},
        ]
    )
    monkeypatch.setattr(qnx_submit_job, "_read_remote_json", lambda *args: next(states))
    monkeypatch.setattr(qnx_submit_job.time, "sleep", lambda seconds: None)

    state = qnx_submit_job._wait_for_state("qnxpi", "/state/job.json", [], 0.01, 2)

    assert state == {"status": "done", "exit_code": 0}
