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
MAX = 1 << 17


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
            def serve_connection(conn: socket.socket) -> None:
                with conn:
                    while True:
                        data = _recv(conn)
                        if data is None:
                            break
                        out = handler(data) or b""
                        conn.sendall(struct.pack("<I", len(out)) + out)

            while True:
                conn, _ = self.sock.accept()
                threading.Thread(target=serve_connection, args=(conn,), daemon=True).start()


class Client:
    """Send to a named server and wait for its reply. Reconnects if the server was restarted."""

    def __init__(self, name: str, wait: float = 30.0):
        self.name, self.wait = name, wait
        self.reply = ctypes.create_string_buffer(MAX) if ON_QNX else None
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
        for attempt in (1, 2):
            try:
                return self._send(data)
            except OSError:
                if attempt == 2:
                    raise
                self.close()
                self._connect()                        # the server died and came back, find it again
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
        try:
            if ON_QNX:
                _c.name_close(self.coid)
            else:
                self.sock.close()
        except Exception:
            pass


def _port(name: str) -> int:
    base = int(os.environ.get("HC_IPC_BASE", "40000"))
    return base + zlib.crc32(name.encode()) % 2000


def _recv(sock) -> bytes | None:
    head = _exact(sock, 4)
    return None if head is None else _exact(sock, struct.unpack("<I", head)[0])


def _exact(sock, n: int) -> bytes | None:
    buf = b""
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            return None
        buf += part
    return buf
