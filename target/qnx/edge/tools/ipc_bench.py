"""Check native message passing on the Pi and time a frame sized round trip.

    python3 tools/ipc_bench.py            starts a server process and a client process
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import qnxipc  # noqa: E402

NAME = "hc/bench"

if len(sys.argv) > 1 and sys.argv[1] == "server":
    qnxipc.Server(NAME).serve(lambda data: data[:16])
else:
    pid = os.fork()
    if pid == 0:
        os.execv(sys.executable, [sys.executable, os.path.abspath(__file__), "server"])
    try:
        c = qnxipc.Client(NAME)
        frame = bytes(320 * 180)
        assert c.send(b"hello world 1234") == b"hello world 1234"
        n, t0 = 200, time.perf_counter()
        for _ in range(n):
            c.send(frame)
        dt = (time.perf_counter() - t0) / n
        print(f"native QNX message passing: {qnxipc.ON_QNX}, {len(frame)} byte frame round trip {dt * 1e6:.0f} us")
    finally:
        os.kill(pid, 9)
