"""Dependency-light resource telemetry for local assessment jobs.

The sampler intentionally returns ``None`` when an operating-system metric is
not available.  It never substitutes synthetic values.  System CPU includes
child processes such as ffmpeg; process metrics describe this API worker.
"""

from __future__ import annotations

import os
import platform
import resource
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .models import ClipAssessmentTarget, ResourceTelemetrySample


def local_target_identity() -> ClipAssessmentTarget:
    return ClipAssessmentTarget(
        executor="local",
        hostname=platform.node() or None,
        system=platform.system() or None,
        release=platform.release() or None,
        machine=platform.machine() or None,
        runtime="Python %s" % platform.python_version(),
        verified=True,
        detail="Assessment executes in the local Simulation Lab API process.",
    )


class LocalTelemetrySampler:
    """Sample real host/process utilization without requiring psutil."""

    def __init__(self, minimum_interval_s: float = 0.5) -> None:
        self.minimum_interval_s = minimum_interval_s
        self._last_wall = time.monotonic()
        self._last_process_cpu = time.process_time()
        self._last_proc_cpu: tuple[int, int] | None = self._read_proc_cpu()
        self._last_sample_at = 0.0
        self._last_sample: ResourceTelemetrySample | None = None

    def sample(self, *, force: bool = False) -> ResourceTelemetrySample:
        now = time.monotonic()
        if (
            not force
            and self._last_sample is not None
            and now - self._last_sample_at < self.minimum_interval_s
        ):
            return self._last_sample

        process_now = time.process_time()
        elapsed = max(now - self._last_wall, 1e-9)
        process_cpu = max(0.0, (process_now - self._last_process_cpu) / elapsed * 100.0)
        self._last_wall = now
        self._last_process_cpu = process_now

        system_cpu, cpu_detail = self._system_cpu_percent()
        ram_used, ram_total, ram_detail = self._memory_bytes()
        details = [
            "Process CPU/RAM cover the API worker; system metrics include model subprocesses."
        ]
        if cpu_detail:
            details.append(cpu_detail)
        if ram_detail:
            details.append(ram_detail)
        sample = ResourceTelemetrySample(
            captured_at=datetime.now(timezone.utc),
            source="local",
            cpu_percent=round(system_cpu, 2) if system_cpu is not None else None,
            ram_used_bytes=ram_used,
            ram_total_bytes=ram_total,
            process_cpu_percent=round(process_cpu, 2),
            process_ram_bytes=self._process_rss_bytes(),
            detail=" ".join(details),
        )
        self._last_sample_at = now
        self._last_sample = sample
        return sample

    @staticmethod
    def _read_proc_cpu() -> tuple[int, int] | None:
        try:
            values = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()[1:]
            ticks = [int(value) for value in values]
        except (OSError, ValueError, IndexError):
            return None
        idle = ticks[3] + (ticks[4] if len(ticks) > 4 else 0)
        return sum(ticks), idle

    def _system_cpu_percent(self) -> tuple[float | None, str | None]:
        current = self._read_proc_cpu()
        if current is not None and self._last_proc_cpu is not None:
            total_delta = current[0] - self._last_proc_cpu[0]
            idle_delta = current[1] - self._last_proc_cpu[1]
            self._last_proc_cpu = current
            if total_delta > 0:
                return max(0.0, min(100.0, (total_delta - idle_delta) / total_delta * 100)), None
        elif current is not None:
            self._last_proc_cpu = current

        # Darwin exposes current per-process percentages through ps. Summing
        # and normalizing by logical CPUs yields whole-host utilization.
        if platform.system() == "Darwin":
            try:
                completed = subprocess.run(
                    ["ps", "-A", "-o", "%cpu="],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if completed.returncode == 0:
                    total = sum(float(value) for value in completed.stdout.split())
                    return min(100.0, total / max(1, os.cpu_count() or 1)), None
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        return None, "System CPU utilization is unavailable on this host."

    @staticmethod
    def _physical_memory_bytes() -> int | None:
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
        except (AttributeError, OSError, ValueError):
            return None
        return pages * page_size if pages > 0 and page_size > 0 else None

    def _memory_bytes(self) -> tuple[int | None, int | None, str | None]:
        total = self._physical_memory_bytes()
        try:
            lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
            values = {
                line.split(":", 1)[0]: int(line.split()[1]) * 1024
                for line in lines
                if ":" in line and len(line.split()) >= 2
            }
            proc_total = values.get("MemTotal")
            available = values.get("MemAvailable")
            if proc_total is not None and available is not None:
                return proc_total - available, proc_total, None
        except (OSError, ValueError):
            pass

        if platform.system() == "Darwin" and total is not None:
            try:
                completed = subprocess.run(
                    ["vm_stat"], check=False, capture_output=True, text=True, timeout=2
                )
                if completed.returncode == 0:
                    values: dict[str, int] = {}
                    for line in completed.stdout.splitlines()[1:]:
                        if ":" not in line:
                            continue
                        name, raw = line.split(":", 1)
                        values[name.strip()] = int(raw.strip().rstrip("."))
                    page_size = os.sysconf("SC_PAGE_SIZE")
                    reclaimable = sum(
                        values.get(name, 0)
                        for name in ("Pages free", "Pages inactive", "Pages speculative")
                    ) * page_size
                    return max(0, total - reclaimable), total, None
            except (OSError, ValueError, subprocess.TimeoutExpired):
                pass
        return None, total, "Used system RAM is unavailable on this host." if total else "System RAM is unavailable on this host."

    @staticmethod
    def _process_rss_bytes() -> int | None:
        try:
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except (ValueError, OSError):
            return None
        # Darwin reports bytes; Linux and QNX Python conventionally report KiB.
        return int(rss if platform.system() == "Darwin" else rss * 1024)
