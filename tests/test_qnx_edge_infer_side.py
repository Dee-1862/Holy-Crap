"""Focused off-target tests for the environment-controlled input side of the QNX edge infer server.

No QNX, no libhcort.so, no real ONNX model: importing target/qnx/edge/infer.py only needs numpy,
and the native session is opened inside main(), never at import.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest

EDGE = Path(__file__).resolve().parents[1] / "target" / "qnx" / "edge"


def load_infer(monkeypatch: pytest.MonkeyPatch, side: str | None = None):
    monkeypatch.syspath_prepend(str(EDGE))
    monkeypatch.delenv("HC_MODEL_SIDE", raising=False)
    if side is not None:
        monkeypatch.setenv("HC_MODEL_SIDE", side)
    sys.modules.pop("infer", None)
    return importlib.import_module("infer")


def test_default_side_is_640_when_env_is_unset(monkeypatch) -> None:
    infer = load_infer(monkeypatch)

    assert infer.SIDE == 640
    assert infer.model_side() == 640
    assert infer.model_side({}) == 640


def test_explicit_320_side_is_accepted(monkeypatch) -> None:
    infer = load_infer(monkeypatch, side="320")

    assert infer.SIDE == 320
    assert infer.model_side({"HC_MODEL_SIDE": "320"}) == 320


@pytest.mark.parametrize("raw", ["32", "4096", "640"])
def test_rule_boundaries_are_accepted(monkeypatch, raw: str) -> None:
    infer = load_infer(monkeypatch)
    assert infer.model_side({"HC_MODEL_SIDE": raw}) == int(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "abc",      # malformed
        "3.2",      # malformed
        "",         # malformed (empty)
        "  ",       # malformed (whitespace only)
        "0",        # non-positive
        "-320",     # non-positive
        "31",       # below the range
        "4097",     # above the range
        "99999",    # unreasonably large
        "4160",     # multiple of 32 but above the range
        "100",      # within range but not stride-aligned
        "641",      # just above 640, not stride-aligned
    ],
)
def test_invalid_sides_fail_with_a_clear_error(monkeypatch, raw: str) -> None:
    infer = load_infer(monkeypatch)
    with pytest.raises(ValueError, match="HC_MODEL_SIDE"):
        infer.model_side({"HC_MODEL_SIDE": raw})


def test_invalid_side_fails_eagerly_at_import(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(EDGE))
    monkeypatch.setenv("HC_MODEL_SIDE", "641")
    sys.modules.pop("infer", None)
    with pytest.raises(ValueError, match="HC_MODEL_SIDE"):
        importlib.import_module("infer")


def test_default_letterbox_is_640_float32_chw(monkeypatch) -> None:
    infer = load_infer(monkeypatch)

    x, s, px, py = infer.letterbox(np.full((640, 640, 3), 7, np.uint8))

    assert x.shape == (1, 3, 640, 640)
    assert x.dtype == np.float32
    assert (s, px, py) == (1.0, 0, 0)


def test_320_letterbox_produces_320_float32_chw_tensor(monkeypatch) -> None:
    infer = load_infer(monkeypatch, side="320")

    rgb = np.full((480, 640, 3), 128, np.uint8)
    x, s, px, py = infer.letterbox(rgb)

    assert x.shape == (1, 3, 320, 320)
    assert x.dtype == np.float32
    assert float(x.min()) >= 0.0 and float(x.max()) <= 1.0
    # 640x480 letterboxed into a 320 square: scale 0.5, centred vertically.
    assert s == 0.5
    assert (px, py) == (0, 40)


def test_320_detect_feeds_320_float32_tensor_to_the_session(monkeypatch) -> None:
    infer = load_infer(monkeypatch, side="320")

    class FakeSession:
        def __init__(self):
            self.inputs: list[np.ndarray] = []

        def run(self, x: np.ndarray):
            self.inputs.append(np.asarray(x))
            return np.zeros((1, 8, 2100), np.float32)

    sess = FakeSession()
    boxes = infer.detect(sess, np.full((640, 640, 3), 10, np.uint8))

    assert len(sess.inputs) == 1
    x = sess.inputs[0]
    assert x.shape == (1, 3, 320, 320)
    assert x.dtype == np.float32
    # No candidate clears CONF on the zero output, so decoding/NMS yields no boxes unchanged.
    assert boxes.shape == (0, 6)
    assert boxes.dtype == np.float32


def test_get_metadata_reports_side_without_touching_the_native_model(monkeypatch) -> None:
    infer = load_infer(monkeypatch)

    assert infer.model_info() == {
        "model": infer.MODEL.name,
        "on": "pi",
        "side": 640,
        "classes": ["cocci", "healthy", "ncd", "salmo"],
    }
    assert infer.MODEL.name == "dropping4_yolo11n_640.onnx"


def test_get_metadata_reflects_the_configured_320_side(monkeypatch) -> None:
    infer = load_infer(monkeypatch, side="320")

    info = infer.model_info()
    assert info["side"] == 320
    assert info["model"] == infer.MODEL.name
