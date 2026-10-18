"""Synchronous message passing between our processes, the way QNX's microkernel does it.

On QNX this calls the kernel directly through ctypes: a server registers a name (name_attach), a client
opens it (name_open) and MsgSend copies the message straight into the server's buffer. The client stays
blocked until the server replies, so a fast camera can never pile up frames ahead of a slow detector,
and nothing is buffered in between. Each process has its own address space, so if one crashes the
others only see a failed send and carry on, which is what lets the supervisor restart it.

Elsewhere (the laptop) the same calls fall back to a localhost TCP socket, so the pipeline can be
developed and tested off the Pi. Messages are bytes, replies are bytes.
"""
from __future__ import annotations

import ctypes
import os
import socket
import struct
import sys
import threading
import time
import zlib

ON_QNX = sys.platform.startswith("qnx") or os.uname().sysname == "QNX" if hasattr(os, "uname") else False
MSG_TYPE = 0x4843             # our own message type, outside the 0..0x1FF range QNX reserves for I/O messages
IO_CONNECT = 0x100            # sent by name_open, must be answered with EOK
MAX = 1 << 17                 # largest frame, 128 KiB; larger frames are rejected, never buffered
MAX_CLIENTS = 16              # bound on concurrent persistent Linux clients: one daemon thread each


if ON_QNX:
    _c = ctypes.CDLL(None, use_errno=True)
    _c.name_attach.restype = ctypes.c_void_p
    _c.name_attach.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
    _c.name_open.argtypes = [ctypes.c_char_p, ctypes.c_int]
    _c.MsgReceive.restype = ctypes.c_long
    _c.MsgReceive.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    _c.MsgReply.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_void_p, ctypes.c_size_t]
    _c.MsgError.argtypes = [ctypes.c_long, ctypes.c_int]
    _c.MsgSend.restype = ctypes.c_long
    _c.MsgSend.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    _c.name_close.argtypes = [ctypes.c_int]


def _err(what: str) -> OSError:
    e = ctypes.get_errno()
    return OSError(e, f"{what}: {os.strerror(e)}")


class Server:
    """Register `name` and answer messages. handler(bytes) -> bytes is called for each one."""

    def __init__(self, name: str):
        self.name = name
        if ON_QNX:
            att = _c.name_attach(None, name.encode(), 0)
            if not att:
                raise _err(f"name_attach {name}")
            self.chid = ctypes.cast(att, ctypes.POINTER(ctypes.c_int))[2]   # name_attach_t: dispatch_t *dpp; int chid
            self.buf = ctypes.create_string_buffer(MAX)
        else:
            self.sock = socket.socket()
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("127.0.0.1", _port(name)))
            self.sock.listen()
            self._clients: set[socket.socket] = set()
            self._threads: set[threading.Thread] = set()
            self._clients_guard = threading.Lock()
            self._slots = threading.BoundedSemaphore(MAX_CLIENTS)
            self._closed = False

    def serve(self, handler) -> None:
        if ON_QNX:
            while True:
                rcvid = _c.MsgReceive(self.chid, self.buf, MAX, None)
                if rcvid == 0:                         # a pulse, for example a client disconnecting
                    continue
                if rcvid < 0:
                    raise _err("MsgReceive")
                kind = struct.unpack_from("<H", self.buf.raw, 0)[0]
                if kind == IO_CONNECT:
                    _c.MsgReply(rcvid, 0, None, 0)
                    continue
                if kind != MSG_TYPE:
                    _c.MsgError(rcvid, 48)             # ENOTSUP
                    continue
                n = struct.unpack_from("<I", self.buf.raw, 4)[0]
                out = handler(self.buf.raw[8:8 + n]) or b""
                _c.MsgReply(rcvid, len(out), out, len(out))   # the status MsgSend returns is the reply length
        else:
            self._serve_linux(handler)

    def _serve_linux(self, handler) -> None:
        """Accept persistent clients and answer each one on its own daemon thread.

        Concurrency is bounded: one thread per client, at most MAX_CLIENTS of
        them at once, via a semaphore, so a flood of connections or a wedged
        peer can never grow the thread count without limit. When every slot is
        busy the extra connection is closed and the client's existing reconnect
        logic retries later. close() from any thread unblocks this loop.
        """
        self.sock.settimeout(0.5)               # wake up regularly, so close() always ends this loop
        while True:
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                if self._closed:
                    return
                continue
            except OSError:
                if self._closed:
                    return
                raise
            conn.settimeout(None)               # accepted sockets stay blocking
            thread = threading.Thread(
                target=self._client_loop, args=(conn, handler),
                daemon=True, name=f"qnxipc/{self.name}")
            with self._clients_guard:
                if self._closed:
                    conn.close()
                    return
                if not self._slots.acquire(blocking=False):
                    conn.close()                # at the concurrency bound; the client reconnects
                    continue
                self._clients.add(conn)
                self._threads.add(thread)
            thread.start()

    def _client_loop(self, conn: socket.socket, handler) -> None:
        try:
            with conn:
                while True:
                    data = _recv(conn)
                    if data is None:
                        break
                    out = handler(data) or b""
                    conn.sendall(struct.pack("<I", len(out)) + out)
        except OSError:
            pass                                # peer hung up, sent a bad frame, or we are closing
        finally:
            with self._clients_guard:
                self._clients.discard(conn)
                self._threads.discard(threading.current_thread())
            self._slots.release()

    def close(self) -> None:
        """Idempotently tear down a Linux server (native QNX servers are torn down by the kernel).

        Closes the listening socket so serve() returns, closes every accepted
        client socket so the client loops unwind, and joins the client threads.
        Calling it again, or on a server that never served, is a no-op.
        """
        if ON_QNX:
            raise NotImplementedError("native QNX servers are torn down by the kernel when the process exits")
        if self._closed:
            return
        self._closed = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)  # on Linux, close() alone does not wake a thread blocked in accept()
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        with self._clients_guard:
            clients, threads = list(self._clients), list(self._threads)
        for conn in clients:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
        for thread in threads:
            try:
                thread.join(timeout=5.0)
            except RuntimeError:
                pass


class Client:
    """Send to a named server and wait for its reply. Reconnects if the server was restarted."""

    def __init__(self, name: str, wait: float = 30.0):
        self.name, self.wait = name, wait
        self.reply = ctypes.create_string_buffer(MAX) if ON_QNX else None
        # A request and its reply are one transaction on both transports.  In
        # particular, two Linux callers must never interleave frames on the
        # persistent socket or consume one another's replies.  The same lock
        # also keeps close/reconnect from replacing a connection mid-send.
        self._lifecycle_lock = threading.Lock()
        self._connect()

    def _connect(self) -> None:
        end = time.monotonic() + self.wait
        while True:
            try:
                if ON_QNX:
                    self.coid = _c.name_open(self.name.encode(), 0)
                    if self.coid < 0:
                        raise _err(f"name_open {self.name}")
                else:
                    self.sock = socket.create_connection(("127.0.0.1", _port(self.name)))
                return
            except OSError:
                if time.monotonic() > end:
                    raise
                time.sleep(0.2)

    def send(self, data: bytes) -> bytes:
        with self._lifecycle_lock:
            for attempt in (1, 2):
                try:
                    return self._send(data)
                except OSError:
                    if attempt == 2:
                        raise
                    self._close_unlocked()
                    self._connect()                    # the server died and came back, find it again
        return b""

    def _send(self, data: bytes) -> bytes:
        if ON_QNX:
            msg = struct.pack("<HHI", MSG_TYPE, 0, len(data)) + data
            n = _c.MsgSend(self.coid, msg, len(msg), self.reply, MAX)
            if n < 0:
                raise _err("MsgSend")
            return self.reply.raw[:n]
        self.sock.sendall(struct.pack("<I", len(data)) + data)
        out = _recv(self.sock)
        if out is None:
            raise OSError("server closed the connection")
        return out

    def close(self) -> None:
        with self._lifecycle_lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        """Close the current connection while the lifecycle lock is held."""
        try:
            if ON_QNX:
                _c.name_close(self.coid)
            else:
                self.sock.close()
        except Exception:
            pass


def _port(name: str) -> int:
    """Map a service name to a fixed localhost TCP port for the Linux fallback.

    Deterministic and stable: zlib.crc32 spreads the name over the same
    2000-port slice the old byte-sum mapping used, so a server and its clients
    keep finding each other after restarts, but names that used to collide
    (hc/cloud and hc/watch share a byte sum) now get distinct ports. The
    result is always in [40000, 41999]: unprivileged (>= 1024), well under
    65535, and only ever bound to 127.0.0.1.
    """
    return 40000 + zlib.crc32(name.encode()) % 2000


def _recv(sock) -> bytes | None:
    head = _exact(sock, 4)
    if head is None:
        return None
    n = struct.unpack("<I", head)[0]
    if n > MAX:
        raise OSError(f"frame of {n} bytes exceeds the {MAX} byte limit")
    return _exact(sock, n)


def _exact(sock, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            return None
        buf += part
    return buf
