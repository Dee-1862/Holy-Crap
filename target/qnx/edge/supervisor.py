"""Start the edge pipeline as separate processes and restart any that dies.

    python3 supervisor.py --replay ../hc-replay/pen-wide.gray --rate 2

This is the QNX microkernel idea at application level. In QNX even drivers, the file system and the
network stack are ordinary processes, so a fault stays inside the process that had it and that process
can be restarted while everything else keeps running. Here the camera, the spot finder and the uplink
are three processes with their own memory that only talk by message passing. Kill one and the others
carry on; this supervisor starts it again and reports the restart to the dashboard.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import qnxipc

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay", required=True)
    ap.add_argument("--rate", type=float, default=2.0)
    args = ap.parse_args()
    # uplink first so the others have somewhere to report, camera last so the spot finder is listening
    cmds = {
        "uplink": [sys.executable, str(HERE / "uplink.py")],
        "spotter": [sys.executable, str(HERE / "spotter.py")],
        "camera": [sys.executable, str(HERE / "camera.py"), "--replay", args.replay, "--rate", str(args.rate)],
    }
    procs, info = {}, {n: {"pid": None, "restarts": 0, "started": 0.0, "lastExit": None, "downFor": None} for n in cmds}
    uplink = None
    for name, cmd in cmds.items():
        procs[name] = subprocess.Popen(cmd, cwd=HERE)
        info[name].update(pid=procs[name].pid, started=time.time())
        time.sleep(0.5)
    print("started", {n: p.pid for n, p in procs.items()}, flush=True)
    while True:
        for name, p in procs.items():
            code = p.poll()
            if code is None:
                continue
            died = time.time()
            procs[name] = subprocess.Popen(cmds[name], cwd=HERE)
            back = time.time()
            i = info[name]
            i.update(pid=procs[name].pid, restarts=i["restarts"] + 1, started=back, lastExit=code,
                     downFor=round((back - died) * 1000, 1))
            print(f"{name} exited with {code}, restarted as pid {procs[name].pid}", flush=True)
        try:
            if uplink is None:
                uplink = qnxipc.Client("hc/uplink", wait=0)
            uplink.send(json.dumps({"kind": "health", "procs": info}).encode())
        except OSError:
            uplink = None
        time.sleep(0.1)


if __name__ == "__main__":
    main()
