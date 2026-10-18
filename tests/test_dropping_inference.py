from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from holy_crap_simlab.dropping_inference import (
    DroppingInferenceError,
    DroppingInferenceResult,
    DroppingOnnxAdapter,
    letterbox_rgb,
    parse_dropping_output,
)


def raw_output(columns: list[tuple[tuple[float, float, float, float], list[float]]]) -> np.ndarray:
    raw = np.zeros((1, 8, len(columns)), dtype=np.float32)
    for index, (box, scores) in enumerate(columns):
        raw[0, 0:4, index] = box
        raw[0, 4:8, index] = scores
    return raw


def test_parse_picks_highest_retained_candidate_and_maps_labels() -> None:
    raw = raw_output(
        [
            ((100, 100, 20, 20), [0.1, 0.2, 0.05, 0.15]),
            ((200, 160, 40, 40), [0.3, 0.1, 0.2, 0.4]),
        ]
    )
    result = parse_dropping_output(
        raw,
        scale_x=0.5,
        scale_y=0.5,
        pad_x=0,
        pad_y=0,
        image_width=640,
        image_height=320,
    )

    assert result.class_name == "salmo"
    assert result.score == pytest.approx(0.4)
    assert result.product_label == "abnormal"
    assert result.scores == pytest.approx(
        {
            "cocci": 0.3,
            "healthy": 0.1,
            "ncd": 0.2,
            "salmo": 0.4,
        }
    )
    assert result.model_detection_bbox is not None
    assert result.model_detection_bbox.x == pytest.approx(0.5625)
    assert result.model_detection_bbox.y == pytest.approx(0.875)
    assert result.retained is True


def test_healthy_maps_to_normal() -> None:
    raw = raw_output([((160, 160, 64, 64), [0.05, 0.9, 0.05, 0.05])])
    result = parse_dropping_output(
        raw,
        scale_x=1.0,
        scale_y=1.0,
        pad_x=0,
        pad_y=0,
        image_width=320,
        image_height=320,
    )
    assert result.class_name == "healthy"
    assert result.product_label == "normal"


def test_no_detection_above_threshold_is_uncertain() -> None:
    raw = raw_output(
        [
            ((100, 100, 20, 20), [0.24, 0.1, 0.05, 0.05]),
            ((200, 160, 40, 40), [0.2, 0.2, 0.2, 0.2]),
        ]
    )
    result = parse_dropping_output(
        raw,
        scale_x=0.5,
        scale_y=0.5,
        pad_x=0,
        pad_y=0,
        image_width=640,
        image_height=320,
    )

    assert result.class_name is None
    assert result.retained is False
    assert result.score == 0.0
    assert result.product_label == "uncertain"
    assert result.model_detection_bbox is None
    assert set(result.scores) == {"cocci", "healthy", "ncd", "salmo"}


def test_invalid_output_shape_raises() -> None:
    with pytest.raises(DroppingInferenceError, match="shape"):
        parse_dropping_output(
            np.zeros((1, 5, 3), dtype=np.float32),
            scale_x=1.0,
            scale_y=1.0,
            pad_x=0,
            pad_y=0,
            image_width=320,
            image_height=320,
        )


def test_invalid_bbox_raises() -> None:
    raw = raw_output([((-10, 160, 64, 64), [0.05, 0.9, 0.05, 0.05])])
    with pytest.raises(DroppingInferenceError, match="invalid bounding box"):
        parse_dropping_output(
            raw,
            scale_x=1.0,
            scale_y=1.0,
            pad_x=0,
            pad_y=0,
            image_width=320,
            image_height=320,
        )


def test_letterbox_scales_and_pads() -> None:
    image = Image.new("RGB", (640, 320), (10, 20, 30))
    letterboxed, scale_x, scale_y, pad_x, pad_y = letterbox_rgb(image, 320, (114, 114, 114))

    assert letterboxed.size == (320, 320)
    assert (scale_x, scale_y) == (0.5, 0.5)
    assert (pad_x, pad_y) == (0, 80)
    assert letterboxed.getpixel((0, 0)) == (114, 114, 114)
    assert letterboxed.getpixel((160, 100)) == (10, 20, 30)


class FakeSession:
    def __init__(self, raw: np.ndarray) -> None:
        self.raw = raw
        self.runs = 0
        self.feeds: list[object] = []

    def get_inputs(self):
        return [SimpleNamespace(name="images")]

    def run(self, names, feeds):
        self.runs += 1
        self.feeds.append(feeds["images"])
        return [self.raw]


def _adapter(tmp_path: Path, session: FakeSession) -> DroppingOnnxAdapter:
    return DroppingOnnxAdapter(
        model_path=tmp_path / "model.onnx", session_factory=lambda: session
    )


def test_adapter_prepares_nchw_rgb_and_caches_per_sha(tmp_path: Path) -> None:
    raw = raw_output([((160, 160, 64, 64), [0.05, 0.9, 0.05, 0.05])])
    session = FakeSession(raw)
    adapter = _adapter(tmp_path, session)
    image = Image.new("RGB", (320, 320), (255, 0, 0))

    first = adapter.infer(image, "d" * 64)
    second = adapter.infer(image, "d" * 64)

    assert first == second
    assert session.runs == 1
    feed = session.feeds[0]
    assert feed.shape == (1, 3, 320, 320)
    assert feed.dtype == np.float32
    assert feed[0, 0, 100, 100] == pytest.approx(1.0)
    assert feed[0, 1, 100, 100] == pytest.approx(0.0)

    adapter.infer(image, "e" * 64)
    assert session.runs == 2


def test_adapter_input_name_falls_back(tmp_path: Path) -> None:
    class NamelessSession:
        def run(self, names, feeds):
            assert names is None or True
            return [raw_output([((160, 160, 64, 64), [0.05, 0.9, 0.05, 0.05])])]

    adapter = DroppingOnnxAdapter(
        model_path=tmp_path / "model.onnx", session_factory=lambda: NamelessSession()
    )
    result = adapter.infer(Image.new("RGB", (320, 320)), "f" * 64)
    assert result.class_name == "healthy"


def test_adapter_unavailable_without_model_or_runtime(tmp_path: Path) -> None:
    adapter = DroppingOnnxAdapter(model_path=tmp_path / "missing.onnx")
    assert adapter.available() is False
    assert adapter.provenance().input_size == [1, 3, 320, 320]
    assert adapter.provenance().id == "dropping4-laptop"


def test_adapter_reports_sha_from_sidecar(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model bytes")
    digest = "a" * 64
    (tmp_path / "SHA256SUMS").write_text(f"{digest}  model.onnx\n", encoding="utf-8")

    adapter = DroppingOnnxAdapter(model_path=model)
    assert adapter.model_sha256() == digest


def test_uncertain_result_round_trips_through_cache(tmp_path: Path) -> None:
    raw = raw_output([((160, 160, 64, 64), [0.1, 0.1, 0.1, 0.1])])
    adapter = _adapter(tmp_path, FakeSession(raw))
    result = adapter.infer(Image.new("RGB", (320, 320)), "c" * 64)
    assert isinstance(result, DroppingInferenceResult)
    assert result.product_label == "uncertain"
    assert result.retained is False
