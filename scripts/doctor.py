#!/usr/bin/env python3
"""Read-only prerequisites report for the Holy Crap Simulation Lab dev environment.

Checks the local toolchain without writing anything, touching the QNX Pi, or
printing environment values or secrets. Exit code is nonzero when any core
prerequisite fails; optional integration checks are informational only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 11)
MIN_NODE_MAJOR = 20


def _run(cmd: list[str], timeout: float = 20.0) -> tuple[bool, str]:
    """Run a command and return (success, first output line). Never raises."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, "not found"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    first = output.splitlines()[0] if output else "no output"
    return proc.returncode == 0, first


def check_python() -> tuple[bool, str]:
    version = sys.version_info
    ok = version >= MIN_PYTHON
    return (
        ok,
        f"{sys.executable} is Python {version.major}.{version.minor}.{version.micro} "
        f"(need >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})",
    )


def check_node() -> tuple[bool, str]:
    node = shutil.which("node")
    if not node:
        return False, "node not found on PATH"
    ok, first = _run([node, "--version"])
    if not ok:
        return False, f"node failed: {first}"
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", first)
    if not match:
        return False, f"unparseable node version: {first}"
    major, minor, patch = (int(part) for part in match.groups())
    ok = major >= MIN_NODE_MAJOR
    return ok, f"node {major}.{minor}.{patch} (need >= {MIN_NODE_MAJOR})"


def check_npm() -> tuple[bool, str]:
    npm = shutil.which("npm")
    if not npm:
        return False, "npm not found on PATH"
    ok, first = _run([npm, "--version"])
    if not ok:
        return False, f"npm failed: {first}"
    return True, f"npm {first}"


def check_ffmpeg() -> tuple[bool, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "ffmpeg not found on PATH"
    ok, first = _run([ffmpeg, "-version"])
    if not ok:
        return False, f"ffmpeg failed: {first}"
    match = re.search(r"ffmpeg version (\S+)", first)
    return True, f"ffmpeg {match.group(1)}" if match else first


def _find_blender() -> str | None:
    blender = shutil.which("blender")
    if blender:
        return blender
    if sys.platform == "darwin":
        mac_app = Path("/Applications/Blender.app/Contents/MacOS/Blender")
        if mac_app.is_file():
            return str(mac_app)
    return None


def check_blender() -> tuple[bool, str]:
    blender = _find_blender()
    if not blender:
        return False, "blender not found on PATH (macOS app bundle checked too)"
    ok, first = _run([blender, "--version"])
    if not ok:
        return False, f"blender failed: {first}"
    match = re.search(r"Blender (\S+)", first)
    return True, f"blender {match.group(1)}" if match else first


def check_ssh_alias() -> tuple[bool, str]:
    """Check that the QNX Pi SSH alias exists in ~/.ssh/config.

    Only the alias *name* is reported; hosts, users, and identities are never
    printed.
    """
    alias = os.environ.get("QNX_SSH_ALIAS", "qnxpi")
    config = Path.home() / ".ssh" / "config"
    if not config.is_file():
        return False, f"SSH config not found at {config}; alias {alias!r} not declared"
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"cannot read SSH config: {exc}"
    declared: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0].lower() == "host":
            declared.update(
                part.lower()
                for part in parts[1:]
                if not any(ch in part for ch in "*?!")
            )
    if alias.lower() in declared:
        return True, f"SSH alias {alias!r} declared in {config}"
    return False, f"SSH alias {alias!r} not declared in {config}"


def check_artifact_dir() -> tuple[bool, str]:
    """Check that HOLY_CRAP_HOME (or the default) can be written to.

    Read-only: never creates the directory. Only the resolved path is printed.
    """
    env_dir = os.environ.get("HOLY_CRAP_HOME")
    if env_dir:
        target = Path(env_dir).expanduser()
        source = "HOLY_CRAP_HOME"
    else:
        target = Path(".simlab")
        source = "default (./.simlab)"
    if target.exists():
        if not target.is_dir():
            return False, f"{target} (from {source}) exists but is not a directory"
        if os.access(target, os.W_OK):
            return True, f"{target} (from {source}) is writable"
        return False, f"{target} (from {source}) is not writable"
    ancestor = target
    while not ancestor.exists() and ancestor.parent != ancestor:
        ancestor = ancestor.parent
    if ancestor.is_dir() and os.access(ancestor, os.W_OK):
        return True, f"{target} (from {source}) does not exist yet but can be created"
    return False, f"{target} (from {source}) cannot be created (parent not writable)"


def main() -> int:
    core_checks: list[tuple[str, object]] = [
        (f"Python >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]}", check_python),
        (f"Node >= {MIN_NODE_MAJOR}", check_node),
        ("npm", check_npm),
        ("writable artifact directory", check_artifact_dir),
    ]
    optional_checks: list[tuple[str, object]] = [
        ("ffmpeg (real-video replay)", check_ffmpeg),
        ("Blender (3D renderer)", check_blender),
        ("QNX SSH alias", check_ssh_alias),
    ]

    print("Core prerequisites (required)")
    print("------------------------------")
    failures = 0
    for label, check in core_checks:
        ok, message = check()  # type: ignore[operator]
        print(f"[{'OK' if ok else 'FAIL'}] {label}: {message}")
        if not ok:
            failures += 1

    print()
    print("Optional integration checks")
    print("----------------------------")
    for label, check in optional_checks:
        ok, message = check()  # type: ignore[operator]
        print(f"[{'OK' if ok else 'WARN'}] {label}: {message}")

    print()
    if failures:
        print(f"{failures} core prerequisite(s) failed. Fix them before `make bootstrap`.")
        return 1
    print("All core prerequisites satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
