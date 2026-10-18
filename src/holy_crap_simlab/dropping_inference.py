"""Small cached ONNX adapter for the committed feces model.

The committed final model is ``models/dropping4-laptop/dropping4_yolo11n_320.onnx``:
a YOLO11n detection + appearance-classification head with no objectness branch.

- Input: RGB float32 NCHW ``[1, 3, 320, 320]``, letterboxed with 114/255 fill.
- Output: ``[1, 8, N]``. Rows 0:4 are cx/cy/w/h per candidate; rows 4:8 are
  class scores in the order cocci, healthy, ncd, salmo.

The adapter keeps the highest-scoring retained candidate (score >= 0.25) and
returns its class, score, and model-space bounding box, mapped back into the
original photo's normalized coordinates. With no retained candidate the
result is ``uncertain``. Inference results are cached per input SHA-256 so
repeated candidates never re-run an identical photo.

Only numpy, Pillow, and onnxruntime are used. When the model file or runtime
is unavailable, the caller falls back to the deterministic mock and must
report ``inference_performed=false`` — this adapter never fabricates an
inference result.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import numpy as np
from PIL import Image

from .models import FecesClassifierModel, NormalizedBoundingBox

CLASS_KEYS = ("cocci", "healthy", "ncd", "salmo")
LABEL_BY_CLASS = {
    "cocci": "Coccidiosis",
    "healthy": "Healthy",
    "ncd": "New Castle Disease",
    "salmo": "Salmonella",
}
CLASS_BY_LABEL = {label: key for key, label in LABEL_BY_CLASS.items()}
SCORE_THRESHOLD = 0.25


class DroppingInferenceError(ValueError):
    """Raised when the model output cannot be interpreted safely."""


@dataclass(frozen=True)
class DroppingInferenceResult:
    scores: dict[str, float]
    class_name: str | None
    score: float
    product_label: Literal["normal", "abnormal", "uncertain"]
    model_detection_bbox: NormalizedBoundingBox | None
    raw_letterbox_bbox: tuple[float, float, float, float] | None

    @property
    def retained(self) -> bool:
        return self.class_name is not None


def letterbox_rgb(
    image: Image.Image, size: int, fill: tuple[int, int, int]
) -> tuple[Image.Image, float, float, int, int]:
    """Scale to fit ``size``x``size``, pad with ``fill``; return effective scales and pads."""

    width, height = image.size
    scale = min(size / width, size / height)
    new_width = max(1, round(width * scale))
    new_height = max(1, round(height * scale))
    resized = image.convert("RGB").resize((new_width, new_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), fill)
    pad_x = (size - new_width) // 2
    pad_y = (size - new_height) // 2
    canvas.paste(resized, (pad_x, pad_y))
    return canvas, new_width / width, new_height / height, pad_x, pad_y


def parse_dropping_output(
    raw: np.ndarray,
    *,
    scale_x: float,
    scale_y: float,
    pad_x: int,
    pad_y: int,
    image_width: int,
    image_height: int,
    input_size: int = 320,
    threshold: float = SCORE_THRESHOLD,
) -> DroppingInferenceResult:
    """Interpret a raw ``[1, 8, N]`` output; no objectness, highest retained candidate."""

    if raw.ndim != 3 or raw.shape[0] != 1 or raw.shape[1] != 8:
        raise DroppingInferenceError(
            f"unexpected model output shape {raw.shape}; expected [1, 8, N]"
        )
    if not np.isfinite(raw).all():
        raise DroppingInferenceError("model output contains non-finite values")
    columns = raw.shape[2]
    boxes = raw[0, 0:4, :]
    scores = raw[0, 4:8, :]
    best_column = -1
    best_score = 0.0
    best_class = -1
    for column in range(columns):
        class_index = int(np.argmax(scores[:, column]))
        value = float(scores[class_index, column])
        if value < threshold:
            continue
        if value > best_score:
            best_score = value
            best_column = column
            best_class = class_index
    if best_column < 0:
        return DroppingInferenceResult(
            scores={key: 0.0 for key in CLASS_KEYS},
            class_name=None,
            score=0.0,
            product_label="uncertain",
            model_detection_bbox=None,
            raw_letterbox_bbox=None,
        )
    cx, cy, width, height = (float(boxes[index, best_column]) for index in range(4))
    if not (0 <= cx <= input_size and 0 <= cy <= input_size and width > 0 and height > 0):
        raise DroppingInferenceError("model returned an invalid bounding box")
    x1 = (cx - width / 2 - pad_x) / scale_x
    y1 = (cy - height / 2 - pad_y) / scale_y
    box_width = width / scale_x
    box_height = height / scale_y
    normalized_x = min(max(x1 / image_width, 0.0), 1.0)
    normalized_y = min(max(y1 / image_height, 0.0), 1.0)
    normalized_width = min(max(box_width / image_width, 0.0), 1.0 - normalized_x)
    normalized_height = min(max(box_height / image_height, 0.0), 1.0 - normalized_y)
    class_name = CLASS_KEYS[best_class]
    return DroppingInferenceResult(
        scores={key: float(scores[index, best_column]) for index, key in enumerate(CLASS_KEYS)},
        class_name=class_name,
        score=best_score,
        product_label="normal" if class_name == "healthy" else "abnormal",
        model_detection_bbox=NormalizedBoundingBox(
            x=round(normalized_x, 6),
            y=round(normalized_y, 6),
            width=round(normalized_width, 6),
            height=round(normalized_height, 6),
        ),
        raw_letterbox_bbox=(cx, cy, width, height),
    )


class DroppingOnnxAdapter:
    """Cached ONNX adapter; falls back cleanly when unavailable."""

    MODEL_ID = "dropping4-laptop"
    MODEL_VERSION = "yolo11n-320"
    MODEL_FORMAT = "onnx"
    INPUT_SIZE = 320
    LETTERBOX_FILL = (114, 114, 114)

    def __init__(
        self,
        model_path: Path | None = None,
        session_factory: Callable[[], object] | None = None,
    ) -> None:
        default = (
            Path(__file__).resolve().parents[2]
            / "models"
            / "dropping4-laptop"
            / "dropping4_yolo11n_320.onnx"
        )
        self.model_path = Path(model_path) if model_path is not None else default
        self._session_factory = session_factory
        self._session: object | None = None
        self._session_loaded = False
        self._cache: dict[str, DroppingInferenceResult] = {}

    def runtime_name(self) -> str | None:
        try:
            import onnxruntime  # noqa: PLC0415

            return f"onnxruntime {onnxruntime.__version__}"
        except Exception:
            return None

    def model_sha256(self) -> str | None:
        sums = self.model_path.parent / "SHA256SUMS"
        if not sums.is_file():
            return None
        try:
            lines = sums.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[-1] == self.model_path.name:
                digest = parts[0]
                return digest if re.fullmatch(r"[a-f0-9]{64}", digest) else None
        return None

    def available(self) -> bool:
        if not self.model_path.is_file():
            return False
        if self.runtime_name() is None:
            return False
        expected = self.model_sha256()
        if expected:
            digest = hashlib.sha256()
            with self.model_path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                return False
        return True

    def provenance(self) -> FecesClassifierModel:
        return FecesClassifierModel(
            id=self.MODEL_ID,
            version=self.MODEL_VERSION,
            sha256=self.model_sha256(),
            format=self.MODEL_FORMAT,
            input_size=[1, 3, self.INPUT_SIZE, self.INPUT_SIZE],
            runtime=self.runtime_name() or "unavailable",
        )

    def _load_ort_session(self) -> object:
        import onnxruntime  # noqa: PLC0415

        return onnxruntime.InferenceSession(
            str(self.model_path), providers=["CPUExecutionProvider"]
        )

    def _get_session(self) -> object:
        if self._session_loaded:
            return self._session  # type: ignore[return-value]
        self._session_loaded = True
        factory = self._session_factory or (lambda: self._load_ort_session())
        self._session = factory()
        return self._session

    def _input_name(self, session: object) -> str:
        try:
            return session.get_inputs()[0].name  # type: ignore[attr-defined]
        except Exception:
            return "images"

    def infer(self, image: Image.Image, input_sha256: str) -> DroppingInferenceResult:
        """Run the model on one photo, caching the result per input SHA-256."""

        if input_sha256 in self._cache:
            return self._cache[input_sha256]
        result = self._infer_uncached(image)
        self._cache[input_sha256] = result
        return result

    def _infer_uncached(self, image: Image.Image) -> DroppingInferenceResult:
        letterboxed, scale_x, scale_y, pad_x, pad_y = letterbox_rgb(
            image, self.INPUT_SIZE, self.LETTERBOX_FILL
        )
        array = (
            np.asarray(letterboxed, dtype=np.float32).transpose(2, 0, 1)[None, :, :, :] / 255.0
        )
        session = self._get_session()
        outputs = session.run(None, {self._input_name(session): array})  # type: ignore[attr-defined]
        raw = np.asarray(outputs[0])
        return parse_dropping_output(
            raw,
            scale_x=scale_x,
            scale_y=scale_y,
            pad_x=pad_x,
            pad_y=pad_y,
            image_width=image.width,
            image_height=image.height,
            input_size=self.INPUT_SIZE,
        )
