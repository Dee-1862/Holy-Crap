"""Start the edge pipeline as separate processes, each at its own priority, and restart any that dies.

    python3 supervisor.py --camera replay --mov /data/share/sensor/simulator_camera.barn.mov
    python3 supervisor.py --camera live --unit 4

This is the QNX microkernel idea at application level. In QNX even drivers, the file system and the network
stack are ordinary processes, so a fault stays inside the process that had it and that process is restarted
while everything else keeps running. Each section here has its own memory and only talks by message passing.

Priorities use QNX's real time scheduler (`on -p`, higher runs first, normal is 10), so the farmer's alerts
and the camera always run before the heavy model work:
    watch 21, camera 20, spotter 12, uplink 11, cloud 11, explain 9, model 8
"""
from __future__ import annotations

import argparse
import json
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import qnxipc

HERE = Path(__file__).resolve().parent
PY = sys.executable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", choices=["replay", "live"], default="replay")
    ap.add_argument("--mov", default="/data/share/sensor/simulator_camera.barn.mov")
    ap.add_argument("--unit", type=int, default=4)       # the Camera Module 3 on the second port
    ap.add_argument("--rate", type=float, default=2.0)
    args = ap.parse_args()
    camera = ([str(HERE / "cam" / "hccam"), "-u", str(args.unit), "-r", str(args.rate)] if args.camera == "live"
              else [PY, str(HERE / "camera.py"), "--mov", args.mov, "--rate", str(args.rate)])
    # name: (priority, command). Servers first so the senders have somewhere to report, camera last.
    sections = {
        "uplink": (11, [PY, str(HERE / "uplink.py")]),
        "cloud": (11, [PY, str(HERE / "cloudlink.py")]),
        "watch": (21, [PY, str(HERE / "watchlink.py")]),
        "site": (10, [PY, str(HERE / "sitelink.py")]),       # the deployed console over Wi-Fi, idle until ~/hc-site.json exists
        "explain": (9, [PY, str(HERE / "explain.py")]),
        "infer": (7, [PY, str(HERE / "infer.py")]),          # the detector, on the Pi, lowest priority
        "model": (8, [PY, str(HERE / "model.py")]),
        "spotter": (12, [PY, str(HERE / "spotter.py")]),
        "camera": (20, camera),
    }
    use_on = qnxipc.ON_QNX and shutil.which("on")

    def start(name: str) -> subprocess.Popen:
        prio, cmd = sections[name]
        return subprocess.Popen((["on", "-p", str(prio)] + cmd) if use_on else cmd, cwd=HERE)

    procs, info = {}, {}
    for name, (prio, _) in sections.items():
        procs[name] = start(name)
        info[name] = {"pid": procs[name].pid, "priority": prio, "restarts": 0, "started": time.time(),
                      "lastExit": None, "downFor": None}
        time.sleep(0.4)
    print("started", {n: p.pid for n, p in procs.items()}, "priorities", "on" if use_on else "off", flush=True)

    # A clean stop takes every section down with it, so a restart never leaves two copies fighting over ports.
    def stop(signum, _frame):
        for p in procs.values():
            p.terminate()
        for p in procs.values():
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
        print(f"stopped by signal {signum}", flush=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    uplink, cloud, last_cloud = None, None, 0.0
    while True:
        for name, p in procs.items():
            code = p.poll()
            if code is None:
                continue
            died = time.time()
            procs[name] = start(name)
            i = info[name]
            i.update(pid=procs[name].pid, restarts=i["restarts"] + 1, started=time.time(), lastExit=code,
                     downFor=round((time.time() - died) * 1000, 1))
            print(f"{name} exited with {code}, restarted as pid {procs[name].pid}", flush=True)
        health = json.dumps({"kind": "health", "procs": info, "t": time.time()}).encode()
        try:
            if uplink is None:
                uplink = qnxipc.Client("hc/uplink", wait=0)
            uplink.send(health)
        except OSError:
            uplink = None
        if time.time() - last_cloud > 15:
            last_cloud = time.time()
            try:
                if cloud is None:
                    cloud = qnxipc.Client("hc/cloud", wait=0)
                cloud.send(health)
            except OSError:
                cloud = None
        time.sleep(0.1)


if __name__ == "__main__":
    main()
