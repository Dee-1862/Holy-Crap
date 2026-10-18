"""ONNX Runtime on the QNX Pi through a small C bridge (hc_ort.c), with the same run() call as onnxruntime.

    from ortlite import Session
    s = Session("model.onnx", threads=4)
    y = s.run(x)          # x: float32 numpy array, returns the first output as a numpy array

QNX's python3-onnxruntime package is missing its compiled module, so this calls libonnxruntime.so directly.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path

import numpy as np

_LIB = None


def _lib():
    global _LIB
    if _LIB is None:
        path = os.environ.get("HC_ORT_LIB", str(Path(__file__).with_name("libhcort.so")))
        lib = ctypes.CDLL(path)
        lib.hc_init.restype = ctypes.c_int
        lib.hc_error.restype = ctypes.c_char_p
        lib.hc_open.restype = ctypes.c_void_p
        lib.hc_open.argtypes = [ctypes.c_char_p, ctypes.c_int]
        lib.hc_run.restype = ctypes.c_long
        lib.hc_run.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64), ctypes.c_int,
                               ctypes.c_void_p, ctypes.c_long, ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_int)]
        lib.hc_close.argtypes = [ctypes.c_void_p]
        if lib.hc_init() != 0:
            raise RuntimeError("ONNX Runtime API not available")
        _LIB = lib
    return _LIB


class Session:
    def __init__(self, model: str, threads: int = 4, max_out: int = 1 << 22):
        self.lib = _lib()
        self.h = self.lib.hc_open(str(model).encode(), threads)
        if not self.h:
            raise RuntimeError(f"cannot open {model}: {self.lib.hc_error().decode()}")
        self.out = np.empty(max_out, np.float32)

    def run(self, x: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(x, np.float32)
        shape = (ctypes.c_int64 * x.ndim)(*x.shape)
        out_shape = (ctypes.c_int64 * 8)()
        out_ndim = ctypes.c_int(0)
        n = self.lib.hc_run(self.h, x.ctypes.data, shape, x.ndim, self.out.ctypes.data, self.out.size,
                            out_shape, ctypes.byref(out_ndim))
        if n < 0:
            raise RuntimeError(self.lib.hc_error().decode())
        return self.out[:n].reshape([out_shape[i] for i in range(out_ndim.value)]).copy()

    def __del__(self):
        if getattr(self, "h", None):
            self.lib.hc_close(self.h)
            self.h = None
