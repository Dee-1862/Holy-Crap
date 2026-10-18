#!/usr/bin/env python3
"""Cross-platform dev supervisor for the Holy Crap Simulation Lab.

Runs the FastAPI backend (`python -m holy_crap_simlab.cli serve`) and the Vite
frontend (`npm --prefix web run dev`), forwards Ctrl-C to both, terminates all
owned children on shutdown, and exits nonzero if either child dies unexpectedly.

Usage:
    python scripts/dev.py              # API + web
    python scripts/dev.py --api-only   # API only
    python scripts/dev.py --web-only   # web only
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time

_children: list[tuple[str, subprocess.Popen]] = []
_shutdown_requested = False
_terminating = False


def _spawn(name: str, cmd: list[str]) -> subprocess.Popen:
    """Start a child in its own process group so we can signal it as a unit."""
    kwargs: dict = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    print(f"[dev] starting {name}: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, **kwargs)
    _children.append((name, proc))
    return proc


def _terminate_children() -> None:
    """Gracefully stop owned children, then force-kill stragglers."""
    for name, proc in reversed(_children):
        if proc.poll() is not None:
            continue
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            else:
                proc.terminate()
            print(f"[dev] stopping {name}...", flush=True)
        except (ProcessLookupError, PermissionError):
            pass

    deadline = time.monotonic() + 5.0
    for _, proc in _children:
        if proc.poll() is not None:
            continue
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            break

    for name, proc in reversed(_children):
        if proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
                print(f"[dev] killed {name}", flush=True)
            except (ProcessLookupError, PermissionError):
                pass


def _handle_signal(signum: int, frame: object) -> None:
    global _shutdown_requested, _terminating
    _shutdown_requested = True
    if _terminating:
        return
    _terminating = True
    _terminate_children()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--api-only", action="store_true", help="run the API server only")
    group.add_argument("--web-only", action="store_true", help="run the Vite dev server only")
    args = parser.parse_args()

    if not args.web_only:
        _spawn("API", [sys.executable, "-m", "holy_crap_simlab.cli", "serve"])
    if not args.api_only:
        npm = shutil.which("npm") or "npm"
        _spawn("web", [npm, "--prefix", "web", "run", "dev"])

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass

    code = 0
    try:
        while True:
            if _shutdown_requested:
                break
            for name, proc in list(_children):
                rc = proc.poll()
                if rc is not None:
                    print(
                        f"[dev] {name} exited unexpectedly (exit code {rc})",
                        file=sys.stderr,
                        flush=True,
                    )
                    code = rc if rc != 0 else 1
                    _terminate_children()
                    return code
            time.sleep(0.2)
    except KeyboardInterrupt:
        _handle_signal(signal.SIGINT, None)
    finally:
        _terminate_children()

    for _, proc in _children:
        if proc.poll() is None:
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                pass

    print("[dev] all processes stopped", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
