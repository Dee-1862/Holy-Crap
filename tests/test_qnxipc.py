"""Focused tests for the Linux TCP fallback in target/qnx/edge/qnxipc.py.

Everything binds to 127.0.0.1 only; there is no external network access. The
native QNX path is never exercised here (ON_QNX is False on this host) and is
not modified by these tests.
"""

from __future__ import annotations

import importlib
import socket
import struct
import sys
import threading
import time
from pathlib import Path

import pytest

EDGE = Path(__file__).resolve().parents[1] / "target" / "qnx" / "edge"

KNOWN_SERVICES = [
    "hc/cloud",
    "hc/watch",
    "hc/uplink",
    "hc/supervisor",
    "hc/spotter",
    "hc/model",
    "hc/explain",
    "hc/bench",
]

PORT_LO, PORT_HI = 40000, 41999


@pytest.fixture
def qnxipc(monkeypatch):
    monkeypatch.syspath_prepend(str(EDGE))
    sys.modules.pop("qnxipc", None)
    module = importlib.import_module("qnxipc")
    assert module.ON_QNX is False, "these tests exercise the Linux fallback only"
    yield module
    sys.modules.pop("qnxipc", None)


def echo(data: bytes) -> bytes:
    return data


class RunningServer:
    """A Linux qnxipc.Server running on a daemon thread, with reliable cleanup."""

    def __init__(self, module, name: str, handler=None):
        self.module = module
        self.name = name
        self.server = module.Server(name)
        self.thread = threading.Thread(
            target=self.server.serve, args=(handler or echo,),
            daemon=True, name=f"test-serve/{name}")
        self.thread.start()

    def close(self) -> None:
        self.server.close()
        self.thread.join(timeout=5.0)
        assert not self.thread.is_alive(), f"accept loop for {self.name} did not terminate"


def send_frame(sock: socket.socket, data: bytes) -> None:
    sock.sendall(struct.pack("<I", len(data)) + data)


def recv_frame(sock: socket.socket, timeout: float = 5.0) -> bytes | None:
    sock.settimeout(timeout)
    head = _read_exact(sock, 4)
    if head is None:
        return None
    return _read_exact(sock, struct.unpack("<I", head)[0])


def _read_exact(sock: socket.socket, n: int) -> bytes | None:
    parts, got = [], 0
    while got < n:
        try:
            part = sock.recv(n - got)
        except OSError:
            return None
        if not part:
            return None
        parts.append(part)
        got += len(part)
    return b"".join(parts)


def expect_closed(sock: socket.socket) -> None:
    """A connection the server rejected or dropped: either a clean EOF or a reset."""
    try:
        assert sock.recv(1) == b""
    except OSError:
        pass
    finally:
        sock.close()


def test_port_mapping_is_deterministic_bounded_and_collision_free(qnxipc) -> None:
    for name in KNOWN_SERVICES:
        port = qnxipc._port(name)
        assert isinstance(port, int)
        assert PORT_LO <= port <= PORT_HI, f"{name} maps outside [{PORT_LO}, {PORT_HI}]"
        assert qnxipc._port(name) == port, "mapping must be deterministic"
    ports = [qnxipc._port(name) for name in KNOWN_SERVICES]
    assert len(set(ports)) == len(ports), "known service names must map to distinct ports"
    assert qnxipc._port("hc/cloud") != qnxipc._port("hc/watch"), "hc/cloud and hc/watch must not collide"


def test_port_mapping_is_stable_across_imports(qnxipc) -> None:
    first = [qnxipc._port(name) for name in KNOWN_SERVICES]
    sys.modules.pop("qnxipc", None)
    again = importlib.import_module("qnxipc")
    second = [again._port(name) for name in KNOWN_SERVICES]
    assert first == second


def test_request_reply_roundtrip_and_max_frame(qnxipc) -> None:
    name = "hc/t-roundtrip"
    server = RunningServer(qnxipc, name)
    client = None
    try:
        client = qnxipc.Client(name, wait=2.0)
        assert client.send(b"hello") == b"hello"
        assert client.send(b"") == b""
        big = bytes(qnxipc.MAX)
        assert client.send(big) == big, "a frame at the MAX limit must round-trip"
    finally:
        if client is not None:
            client.close()
        server.close()


def test_multiple_persistent_clients_are_served_concurrently(qnxipc) -> None:
    name = "hc/t-multi"
    server = RunningServer(qnxipc, name)
    clients = []
    try:
        errors = []

        def run(i: int) -> None:
            try:
                client = qnxipc.Client(name, wait=2.0)
                clients.append(client)
                for j in range(5):
                    payload = f"{i}:{j}".encode()
                    if client.send(payload) != payload:
                        errors.append((i, j, "wrong reply"))
            except Exception as exc:  # noqa: BLE001
                errors.append((i, repr(exc)))

        threads = [threading.Thread(target=run, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15.0)
        assert not any(thread.is_alive() for thread in threads)
        assert errors == []
        for i, client in enumerate(clients):            # every connection stayed persistent
            payload = f"tail:{i}".encode()
            assert client.send(payload) == payload
    finally:
        for client in clients:
            client.close()
        server.close()


def test_one_client_serializes_concurrent_request_reply_transactions(qnxipc) -> None:
    """One persistent client never overlaps frames or mismatches replies."""
    name = "hc/t-shared-client"
    server = RunningServer(qnxipc, name)
    client = None
    try:
        client = qnxipc.Client(name, wait=2.0)
        real_socket = client.sock
        state_guard = threading.Lock()
        active_sends = 0
        max_active_sends = 0

        class ObservedSocket:
            def sendall(self, data: bytes) -> None:
                nonlocal active_sends, max_active_sends
                with state_guard:
                    active_sends += 1
                    max_active_sends = max(max_active_sends, active_sends)
                try:
                    # Give all callers a deterministic opportunity to overlap.
                    time.sleep(0.01)
                    real_socket.sendall(data)
                finally:
                    with state_guard:
                        active_sends -= 1

            def recv(self, size: int) -> bytes:
                return real_socket.recv(size)

            def close(self) -> None:
                real_socket.close()

        client.sock = ObservedSocket()
        barrier = threading.Barrier(9)
        replies: dict[int, bytes] = {}
        errors: list[BaseException] = []

        def send_shared(index: int) -> None:
            payload = (f"shared-{index}:" + "x" * (index * 37)).encode()
            try:
                barrier.wait(timeout=5.0)
                replies[index] = client.send(payload)
            except BaseException as exc:  # noqa: BLE001 - retain thread failures
                errors.append(exc)

        threads = [threading.Thread(target=send_shared, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5.0)
        for thread in threads:
            thread.join(timeout=10.0)

        assert not any(thread.is_alive() for thread in threads)
        assert errors == []
        assert max_active_sends == 1
        for index in range(8):
            expected = (f"shared-{index}:" + "x" * (index * 37)).encode()
            assert replies[index] == expected
    finally:
        if client is not None:
            client.close()
        server.close()


def test_reconnect_retry_does_not_reenter_client_lock(qnxipc) -> None:
    name = "hc/t-reconnect-lock"
    server = RunningServer(qnxipc, name)
    client = None
    try:
        client = qnxipc.Client(name, wait=2.0)
        send_real = client._send
        calls = 0

        def fail_once(data: bytes) -> bytes:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("simulated stale connection")
            return send_real(data)

        client._send = fail_once
        result: list[bytes] = []
        error: list[BaseException] = []

        def run() -> None:
            try:
                result.append(client.send(b"after-reconnect"))
            except BaseException as exc:  # noqa: BLE001 - retain thread failure
                error.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=5.0)

        assert not thread.is_alive(), "retry deadlocked while reconnecting"
        assert error == []
        assert result == [b"after-reconnect"]
        assert calls == 2
    finally:
        if client is not None:
            client.close()
        server.close()


def test_persistent_client_does_not_starve_a_later_client(qnxipc) -> None:
    name = "hc/t-health"
    server = RunningServer(qnxipc, name)
    first = None
    try:
        first = qnxipc.Client(name, wait=2.0)
        assert first.send(b"warm") == b"warm"           # stays connected and idle forever
        outcome = {}

        def health() -> None:
            client = qnxipc.Client(name, wait=2.0)
            started = time.monotonic()
            outcome["reply"] = client.send(b"ping")
            outcome["elapsed"] = time.monotonic() - started
            client.close()

        thread = threading.Thread(target=health)
        thread.start()
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "health client was starved by a persistent client"
        assert outcome.get("reply") == b"ping"
        assert outcome["elapsed"] < 2.0, f"reply took {outcome['elapsed']:.3f}s"
        assert first.send(b"still-connected") == b"still-connected"
    finally:
        if first is not None:
            first.close()
        server.close()


def test_oversized_and_malformed_frames_cannot_hurt_the_server(qnxipc) -> None:
    name = "hc/t-frames"
    server = RunningServer(qnxipc, name)
    client = None
    try:
        port = qnxipc._port(name)
        oversized = socket.create_connection(("127.0.0.1", port), timeout=5.0)
        oversized.sendall(struct.pack("<I", qnxipc.MAX + 1) + b"x" * 32)
        expect_closed(oversized)

        bogus = socket.create_connection(("127.0.0.1", port), timeout=5.0)
        bogus.sendall(struct.pack("<I", 0xFFFFFFFF))
        expect_closed(bogus)

        torn = socket.create_connection(("127.0.0.1", port), timeout=5.0)
        torn.sendall(b"\x01\x00\x00")                   # truncated header, then vanish
        torn.close()

        client = qnxipc.Client(name, wait=2.0)
        assert client.send(b"alive") == b"alive", "server must keep serving after bad frames"
    finally:
        if client is not None:
            client.close()
        server.close()


def test_connection_concurrency_is_bounded(qnxipc, monkeypatch) -> None:
    monkeypatch.setattr(qnxipc, "MAX_CLIENTS", 1)
    name = "hc/t-bound"
    server = RunningServer(qnxipc, name)
    first = None
    try:
        first = qnxipc.Client(name, wait=2.0)
        assert first.send(b"one") == b"one"             # holds the only slot
        second = socket.create_connection(("127.0.0.1", qnxipc._port(name)), timeout=5.0)
        second.settimeout(5.0)
        try:
            send_frame(second, b"two")
        except OSError:
            pass                                        # shed at the bound: reset is fine too
        expect_closed(second)
        assert first.send(b"one-still-works") == b"one-still-works"
    finally:
        if first is not None:
            first.close()
        server.close()


def test_close_is_idempotent_and_terminates_all_loops(qnxipc) -> None:
    name = "hc/t-close"
    server = RunningServer(qnxipc, name)
    client = None
    try:
        client = qnxipc.Client(name, wait=2.0)
        assert client.send(b"a") == b"a"
        server.server.close()
        server.server.close()                           # idempotent
        server.thread.join(timeout=5.0)
        assert not server.thread.is_alive(), "accept loop survived close()"
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and any(
            t.is_alive() and t.name.startswith("qnxipc/") for t in threading.enumerate()
        ):
            time.sleep(0.05)
        alive = [t.name for t in threading.enumerate() if t.is_alive() and t.name.startswith("qnxipc/")]
        assert alive == [], f"client threads survived close(): {alive}"
        with pytest.raises(OSError):
            qnxipc.Client(name, wait=0.5)               # nobody is listening any more
    finally:
        if client is not None:
            client.close()
        server.close()
