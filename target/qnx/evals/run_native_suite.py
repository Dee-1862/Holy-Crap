#!/system/bin/python3
"""Orchestrate bounded, repeatable QNX native evaluation scenarios."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import IO


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
RAW = ROOT / "raw"
LOGS = ROOT / "logs"
VM_LIMIT_BYTES = 8 * 1024 * 1024 * 1024
VM_LIMIT_KIB = VM_LIMIT_BYTES // 1024
ON = ["/proc/boot/on", "-L", f"vmem:{VM_LIMIT_BYTES}"]


def run_text(argv: list[str]) -> dict[str, object]:
    started = time.monotonic_ns()
    completed = subprocess.run(argv, capture_output=True, text=True)
    finished = time.monotonic_ns()
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "started_monotonic_ns": started,
        "finished_monotonic_ns": finished,
        "duration_ms": round((finished - started) / 1_000_000.0, 3),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def read_thermal() -> dict[str, object]:
    result: dict[str, object] = {}
    for name in ("thermal", "thermal_ext"):
        path = Path("/dev") / name
        try:
            result[name] = path.read_text(encoding="utf-8").strip()
        except OSError as error:
            result[name] = {"error": str(error)}
    return result


def capture_process(pid: int) -> dict[str, object]:
    return {
        "sched": run_text(["pidin", "-p", str(pid), "sched"]),
        "rmasks": run_text(["pidin", "-p", str(pid), "rmasks"]),
        "rlimits": run_text(["pidin", "-p", str(pid), "rlimits"]),
        "memory": run_text(["pidin", "-p", str(pid), "memory"]),
    }


def start(argv: list[str], stdout: IO[bytes], stderr: IO[bytes]) -> tuple[subprocess.Popen[bytes], int]:
    started = time.monotonic_ns()
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )
    return process, started


def wait(process: subprocess.Popen[bytes], started_ns: int, argv: list[str]) -> dict[str, object]:
    returncode = process.wait(timeout=180.0)
    finished = time.monotonic_ns()
    return {
        "argv": argv,
        "pid": process.pid,
        "returncode": returncode,
        "started_monotonic_ns": started_ns,
        "finished_monotonic_ns": finished,
        "duration_ms": round((finished - started_ns) / 1_000_000.0, 3),
    }


def load_processes(duration_s: float, cpus: tuple[int, ...], prefix: str) -> list[tuple[subprocess.Popen[bytes], int, list[str], IO[bytes], IO[bytes]]]:
    processes = []
    for cpu in cpus:
        argv = ON + ["-C", str(cpu), str(ROOT / "cpu_stress"), str(duration_s)]
        out = (LOGS / f"{prefix}-cpu{cpu}.out").open("wb")
        err = (LOGS / f"{prefix}-cpu{cpu}.err").open("wb")
        process, started_ns = start(argv, out, err)
        processes.append((process, started_ns, argv, out, err))
    return processes


def finish_load(processes: list[tuple[subprocess.Popen[bytes], int, list[str], IO[bytes], IO[bytes]]]) -> list[dict[str, object]]:
    results = []
    for process, started_ns, argv, out, err in processes:
        try:
            results.append(wait(process, started_ns, argv))
        finally:
            out.close()
            err.close()
    return results


def jitter_suite() -> dict[str, object]:
    scenarios = (
        ("idle-control", False, ()),
        ("idle-fifo40", True, ()),
        ("cross-core-load-control", False, (0, 1, 2)),
        ("cross-core-load-fifo40", True, (0, 1, 2)),
        ("same-core-load-control", False, (3,)),
        ("same-core-load-fifo40", True, (3,)),
    )
    results: list[dict[str, object]] = []
    for scenario, fixed, load_cpus in scenarios:
        for trial in range(1, 6):
            prefix = f"jitter-{scenario}-trial{trial}"
            loads = load_processes(6.5, load_cpus, prefix)
            if loads:
                time.sleep(0.25)
            argv = ON + ["-C", "3"]
            if fixed:
                argv += ["-p", "40f"]
            argv += [str(ROOT / "jitter_bench"), "5000", "1000", "100", str(RAW / f"{prefix}.csv")]
            out_path = RAW / f"{prefix}.json"
            err_path = LOGS / f"{prefix}.err"
            with out_path.open("wb") as out, err_path.open("wb") as err:
                process, started_ns = start(argv, out, err)
                time.sleep(0.5)
                observed = capture_process(process.pid)
                process_result = wait(process, started_ns, argv)
            load_results = finish_load(loads)
            results.append(
                {
                    "scenario": scenario,
                    "trial": trial,
                    "fixed_priority_requested": fixed,
                    "load_cpus": list(load_cpus),
                    "process": process_result,
                    "observed_process": observed,
                    "load_processes": load_results,
                    "thermal_after": read_thermal(),
                }
            )
    return {"suite": "jitter", "trials_per_scenario": 5, "results": results}


def ipc_suite() -> dict[str, object]:
    results = []
    for trial in range(1, 6):
        prefix = f"ipc-trial{trial}"
        argv = ON + [
            "/system/bin/python3",
            str(SOURCE / "tools" / "ipc_eval.py"),
            str(RAW / f"{prefix}.csv"),
            "1000",
            "57600",
        ]
        result = run_text(argv)
        (RAW / f"{prefix}.json").write_text(str(result["stdout"]), encoding="utf-8")
        (LOGS / f"{prefix}.err").write_text(str(result["stderr"]), encoding="utf-8")
        results.append(result)
    return {"suite": "ipc", "trials": 5, "results": results}


def ncnn_suite() -> dict[str, object]:
    model = ROOT / "model"
    input_path = ROOT / "input.raw"
    scenarios = (("idle", ()), ("bounded-load", (0, 1, 2)))
    results: list[dict[str, object]] = []
    for scenario, load_cpus in scenarios:
        for trial in range(1, 6):
            prefix = f"ncnn-{scenario}-trial{trial}"
            loads = load_processes(4.5, load_cpus, prefix)
            if loads:
                time.sleep(0.25)
            argv = ON + [
                "-R",
                "15",
                str(ROOT / "ncnn_bench"),
                str(model / "model.ncnn.param"),
                str(model / "model.ncnn.bin"),
                str(input_path),
                "320",
                "21",
                "3",
                "in0",
                "out0",
                str(RAW / f"{prefix}-calls.csv"),
            ]
            out_path = RAW / f"{prefix}.json"
            err_path = LOGS / f"{prefix}.err"
            thermal_before = read_thermal()
            with out_path.open("wb") as out, err_path.open("wb") as err:
                process, started_ns = start(argv, out, err)
                time.sleep(0.25)
                observed = capture_process(process.pid)
                process_result = wait(process, started_ns, argv)
            load_results = finish_load(loads)
            results.append(
                {
                    "scenario": scenario,
                    "trial": trial,
                    "process": process_result,
                    "observed_process": observed,
                    "load_processes": load_results,
                    "thermal_before": thermal_before,
                    "thermal_after": read_thermal(),
                }
            )
    return {"suite": "ncnn", "trials_per_scenario": 5, "results": results}


def ncnn_resource_suite() -> dict[str, object]:
    model = ROOT / "model"
    input_path = ROOT / "input.raw"
    results: list[dict[str, object]] = []
    for scenario, load_cpus in (("idle", ()), ("bounded-load", (0, 1, 2))):
        prefix = f"ncnn-resource-{scenario}"
        loads = load_processes(14.0, load_cpus, prefix)
        if loads:
            time.sleep(0.25)
        argv = ON + [
            "-R",
            "15",
            str(ROOT / "ncnn_bench"),
            str(model / "model.ncnn.param"),
            str(model / "model.ncnn.bin"),
            str(input_path),
            "320",
            "101",
            "3",
            "in0",
            "out0",
            str(RAW / f"{prefix}-calls.csv"),
        ]
        out_path = RAW / f"{prefix}.json"
        err_path = LOGS / f"{prefix}.err"
        samples: list[dict[str, object]] = []
        thermal_before = read_thermal()
        with out_path.open("wb") as out, err_path.open("wb") as err:
            process, started_ns = start(argv, out, err)
            while process.poll() is None:
                sampled_ns = time.monotonic_ns()
                samples.append(
                    {
                        "sampled_monotonic_ns": sampled_ns,
                        "elapsed_ms": round((sampled_ns - started_ns) / 1_000_000.0, 3),
                        "times": run_text(["pidin", "-p", str(process.pid), "times"]),
                        "memory": run_text(["pidin", "-p", str(process.pid), "memory"]),
                    }
                )
                time.sleep(0.5)
            process_result = wait(process, started_ns, argv)
        load_results = finish_load(loads)
        results.append(
            {
                "scenario": scenario,
                "process": process_result,
                "samples": samples,
                "load_processes": load_results,
                "thermal_before": thermal_before,
                "thermal_after": read_thermal(),
            }
        )
    return {"suite": "ncnn_resource_profile", "results": results}


def fault_suite() -> dict[str, object]:
    results: list[dict[str, object]] = []
    for trial in range(1, 6):
        prefix = f"fault-trial{trial}"
        jitter_argv = ON + [
            "-C",
            "3",
            "-p",
            "40f",
            str(ROOT / "jitter_bench"),
            "16000",
            "1000",
            "100",
            str(RAW / f"{prefix}-jitter.csv"),
        ]
        jitter_out = (RAW / f"{prefix}-jitter.json").open("wb")
        jitter_err = (LOGS / f"{prefix}-jitter.err").open("wb")
        jitter, jitter_started = start(jitter_argv, jitter_out, jitter_err)
        try:
            time.sleep(0.25)
            supervisor_argv = ON + [
                "-C",
                "0",
                "/system/bin/python3",
                str(SOURCE / "fault_supervisor.py"),
                str(RAW / f"{prefix}-worker"),
            ]
            supervisor_out = (RAW / f"{prefix}-recovery.json").open("wb")
            supervisor_err = (LOGS / f"{prefix}-recovery.err").open("wb")
            supervisor, supervisor_started = start(supervisor_argv, supervisor_out, supervisor_err)
            try:
                time.sleep(0.5)
                supervisor_observed = capture_process(supervisor.pid)
                supervisor_result = wait(supervisor, supervisor_started, supervisor_argv)
            finally:
                supervisor_out.close()
                supervisor_err.close()
            jitter_result = wait(jitter, jitter_started, jitter_argv)
        finally:
            jitter_out.close()
            jitter_err.close()
            if jitter.poll() is None:
                jitter.kill()
                jitter.wait(timeout=2.0)
        results.append(
            {
                "trial": trial,
                "supervisor": supervisor_result,
                "supervisor_observed_process": supervisor_observed,
                "independent_high_priority_timer": jitter_result,
                "thermal_after": read_thermal(),
            }
        )
    return {"suite": "fault_isolation", "trials": 5, "results": results}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"jitter", "ipc", "ncnn", "resource", "fault"}:
        print("usage: run_native_suite.py jitter|ipc|ncnn|resource|fault", file=sys.stderr)
        return 64
    RAW.mkdir(exist_ok=True)
    LOGS.mkdir(exist_ok=True)
    suite = sys.argv[1]
    started = time.monotonic_ns()
    result = {
        "schema": "holy-crap-qnx-native-eval-v1",
        "suite": suite,
        "target": "QNX 8.0 RaspberryPi5 aarch64le",
        "source_commit": "7778ee028347acb8793b7fd81d3d92f63ff57d37",
        "virtual_memory_soft_limit_kib": VM_LIMIT_KIB,
        "thermal_before": read_thermal(),
        "result": {
            "jitter": jitter_suite,
            "ipc": ipc_suite,
            "ncnn": ncnn_suite,
            "resource": ncnn_resource_suite,
            "fault": fault_suite,
        }[suite](),
        "thermal_after": read_thermal(),
    }
    result["duration_ms"] = round((time.monotonic_ns() - started) / 1_000_000.0, 3)
    path = RAW / f"{suite}-suite-manifest.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "suite": suite, "manifest": str(path), "duration_ms": result["duration_ms"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

