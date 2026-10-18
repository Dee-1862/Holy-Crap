"""Find the QNX Pi on a direct Ethernet cable and keep an SSH alias pointing at it.

For a second setup (a Windows laptop with its own Pi) next to the main one, so the two never share
an alias. It writes only its own block in ~/.ssh/config, marked with comments, and leaves every
other entry alone. The main setup keeps `qnxpi`; this one is `qnxpi-win` by default.

    python scripts/pi_win.py              find the Pi, update the alias, test SSH
    python scripts/pi_win.py --alias NAME use another alias

With a cable straight between laptop and Pi, both pick a 169.254.x.x address that can change after a
reboot, so this looks the Pi up by its Raspberry Pi network card prefix each time. HostKeyAlias keeps the
Pi's host key under the alias name, so a new address does not trigger a host key warning.
The block pins the SHA-2 MACs. The Pi offers only AES-CTR ciphers, and with those Windows OpenSSH 9.5
picks umac-128, which fails with "Corrupted MAC on input".
Then use it like the main setup:  ssh qnxpi-win   or   QNX_SSH_ALIAS=qnxpi-win python scripts/doctor.py
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PI_PREFIXES = ("28-cd-c1", "2c-cf-67", "88-a2-9e", "b8-27-eb", "d8-3a-dd", "dc-a6-32", "e4-5f-01")
CONFIG = Path.home() / ".ssh" / "config"


def find_pi() -> str | None:
    for ip in ("169.254.255.255",):                       # a broadcast ping fills the neighbour table
        subprocess.run(["ping", "-n" if sys.platform == "win32" else "-c", "1", ip], capture_output=True)
    table = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout.lower().replace(":", "-")
    for line in table.splitlines():
        m = re.match(r"\s*(169\.254\.\d+\.\d+)\s+([0-9a-f-]{17})", line)
        if m and m.group(2).startswith(PI_PREFIXES):
            return m.group(1)
    return None


def write_alias(alias: str, host: str, user: str, key: Path) -> None:
    begin, end = f"# >>> {alias} (scripts/pi_win.py)", f"# <<< {alias}"
    block = (f"{begin}\nHost {alias}\n    HostName {host}\n    User {user}\n    IdentityFile {key.as_posix()}\n"
             f"    IdentitiesOnly yes\n    HostKeyAlias {alias}\n    MACs hmac-sha2-256-etm@openssh.com,hmac-sha2-256\n    ConnectTimeout 10\n    ServerAliveInterval 30\n{end}\n")
    text = CONFIG.read_text() if CONFIG.exists() else ""
    if begin in text:
        text = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + ("\n\n" if text else "") + block
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", default="qnxpi-win")
    ap.add_argument("--user", default="qnxuser")
    ap.add_argument("--key", type=Path, default=Path.home() / ".ssh" / "id_ed25519")
    ap.add_argument("--host", help="skip the search and use this address")
    args = ap.parse_args()
    host = args.host or find_pi()
    if not host:
        print("No Raspberry Pi found on a 169.254 link. Is the cable in and the Pi booted?")
        return 1
    write_alias(args.alias, host, args.user, args.key)
    print(f"{args.alias} -> {args.user}@{host}  (written to {CONFIG})")
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", args.alias, "uname -a"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print("SSH works:", r.stdout.strip())
        return 0
    if "Permission denied" in r.stderr:
        pub = args.key.with_suffix(".pub")
        print("The Pi answers but does not know this laptop's key yet. Run this once and type the qnxuser password:")
        print(f'  type "{pub}" | ssh {args.alias} "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"')
    else:
        print(r.stderr.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
