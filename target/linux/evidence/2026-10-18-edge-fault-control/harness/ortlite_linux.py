"""Disposable Linux adapter for the QNX ortlite Session interface.

This file is used only in the Linux control benchmark's temporary staging
directory.  The production QNX edge tree continues to use libhcort.so.
"""
from __future__ import annotations

import numpy as np
import onnxruntime as ort


class Session:
    def __init__(self, model: str, threads: int = 4, max_out: int = 1 << 22):
        del max_out
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(
            model,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    def run(self, x: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(x, np.float32)
        return self.session.run(None, {self.input_name: x})[0]
