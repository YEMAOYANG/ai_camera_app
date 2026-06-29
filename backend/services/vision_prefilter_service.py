from __future__ import annotations

import base64
import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger(__name__)

PERSON_CLASS_ID = 0
_THUMB_SIZE = (160, 120)
_DEFAULT_MODEL_RELATIVE = Path("assets") / "vision" / "yolov8n.onnx"
_BACKEND_ROOT = Path(__file__).resolve().parents[1]


class PrefilterConfigurationError(RuntimeError):
    """Raised when motion + person prefilter is enabled but not fully configured."""


def backend_root() -> Path:
    return _BACKEND_ROOT


def resolve_prefilter_model_path(configured: str) -> Path:
    path = Path(configured).expanduser()
    if path.is_absolute():
        return path
    return (_BACKEND_ROOT / path).resolve()


def prefilter_is_required() -> bool:
    """Prefilter is mandatory in production; not a casual feature toggle."""
    required = os.getenv("APP_PREFILTER_REQUIRED")
    if required is not None:
        return str(required).strip().lower() in {"1", "true", "yes", "on"}
    return str(os.getenv("APP_PREFILTER_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def default_prefilter_model_path() -> Path:
    configured = str(os.getenv("APP_PREFILTER_MODEL") or "").strip()
    if configured:
        return resolve_prefilter_model_path(configured)
    return _BACKEND_ROOT / _DEFAULT_MODEL_RELATIVE


def prefilter_config() -> dict[str, Any]:
    enabled = prefilter_is_required()
    person_required = str(os.getenv("APP_PREFILTER_PERSON_REQUIRED", "1")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    model_path = default_prefilter_model_path()
    return {
        "enabled": enabled,
        "motion_threshold": float(os.getenv("APP_PREFILTER_MOTION_THRESHOLD", "0.02")),
        "motion_mask_top": float(os.getenv("APP_PREFILTER_MOTION_MASK_TOP", "0.18")),
        "person_confidence": float(os.getenv("APP_PREFILTER_PERSON_CONFIDENCE", "0.45")),
        "person_required": person_required,
        "model_path": str(model_path),
        "input_size": int(os.getenv("APP_PREFILTER_INPUT_SIZE", "640")),
    }


def ensure_prefilter_model() -> Path:
    """Dev bootstrap: export ONNX when the shipped model file is missing."""
    model_path = default_prefilter_model_path()
    if model_path.is_file():
        return model_path

    import subprocess
    import sys

    backend_root = Path(__file__).resolve().parents[1]
    script = backend_root / "scripts" / "export_yolov8n_onnx.py"
    subprocess.run([sys.executable, str(script)], cwd=str(backend_root), check=True)
    if not model_path.is_file():
        raise PrefilterConfigurationError(
            "YOLO prefilter model missing at "
            f"{model_path}. Run: cd backend && python scripts/export_yolov8n_onnx.py"
        )
    return model_path


def validate_prefilter_runtime() -> None:
    config = prefilter_config()
    if not config["enabled"]:
        raise PrefilterConfigurationError(
            "APP_PREFILTER_REQUIRED=1 is required; observation worker always runs OpenCV + YOLO prefilter. "
            "(Legacy APP_PREFILTER_ENABLED is still read when APP_PREFILTER_REQUIRED is unset.)"
        )
    if not config["person_required"]:
        raise PrefilterConfigurationError(
            "APP_PREFILTER_PERSON_REQUIRED=1 is required; person detection is mandatory."
        )
    model_path = default_prefilter_model_path()
    if not model_path.is_file():
        raise PrefilterConfigurationError(
            "YOLO prefilter model missing at "
            f"{model_path}. Run: cd backend && python scripts/export_yolov8n_onnx.py"
        )
    try:
        import cv2  # noqa: F401
    except ImportError as exc:
        raise PrefilterConfigurationError(
            "opencv-python-headless is required for motion prefilter."
        ) from exc
    try:
        import onnxruntime  # noqa: F401
    except ImportError as exc:
        raise PrefilterConfigurationError(
            "onnxruntime is required for YOLO person prefilter."
        ) from exc
    session = _load_onnx_session(str(model_path), required=True)
    if session is None:
        raise PrefilterConfigurationError(f"failed to load YOLO prefilter model: {model_path}")


@dataclass(frozen=True)
class PrefilterResult:
    motion_score: float
    motion_pixels: int
    person_detected: bool | None
    person_confidence: float
    person_count: int
    person_available: bool
    motion_available: bool
    checked_at: int
    frame_thumb_b64: str

    @property
    def prefilter_ready(self) -> bool:
        return self.motion_available and self.person_available

    @property
    def activity_detected(self) -> bool:
        config = prefilter_config()
        return self.motion_available and self.motion_score >= config["motion_threshold"]

    @property
    def should_trigger_cloud_vision(self) -> bool:
        if self.person_detected is True:
            return True
        if self.activity_detected:
            return True
        return False


def default_prefilter_runtime() -> dict[str, Any]:
    return {
        "last_frame_thumb_b64": "",
        "motion_score": 0.0,
        "motion_pixels": 0,
        "person_detected": None,
        "person_confidence": 0.0,
        "person_count": 0,
        "person_available": False,
        "motion_available": False,
        "checked_at": 0,
    }


def prefilter_runtime_from_result(result: PrefilterResult) -> dict[str, Any]:
    return {
        "last_frame_thumb_b64": result.frame_thumb_b64,
        "motion_score": result.motion_score,
        "motion_pixels": result.motion_pixels,
        "person_detected": result.person_detected,
        "person_confidence": result.person_confidence,
        "person_count": result.person_count,
        "person_available": result.person_available,
        "motion_available": result.motion_available,
        "checked_at": result.checked_at,
    }


def analyze_prefilter(
    image_bytes: bytes,
    *,
    previous: Mapping[str, Any] | None,
    now_ms: int,
) -> PrefilterResult:
    config = prefilter_config()
    previous = previous or {}
    thumb_b64, gray = _frame_thumb(image_bytes)
    motion_score = 0.0
    motion_pixels = 0
    motion_available = False
    previous_thumb = str(previous.get("last_frame_thumb_b64") or "").strip()
    if previous_thumb:
        previous_gray = _decode_thumb_gray(previous_thumb)
        if previous_gray is not None and previous_gray.shape == gray.shape:
            motion_score, motion_pixels = _motion_score(previous_gray, gray)
            motion_available = True

    if not config["enabled"]:
        raise PrefilterConfigurationError("prefilter is disabled")

    detected, confidence, count, available = _detect_person(
        image_bytes,
        model_path=config["model_path"],
        confidence_threshold=config["person_confidence"],
        input_size=config["input_size"],
        required=True,
    )
    person_detected = detected
    person_confidence = confidence
    person_count = count
    person_available = available

    return PrefilterResult(
        motion_score=motion_score,
        motion_pixels=motion_pixels,
        person_detected=person_detected,
        person_confidence=person_confidence,
        person_count=person_count,
        person_available=person_available,
        motion_available=motion_available,
        checked_at=now_ms,
        frame_thumb_b64=thumb_b64,
    )


def prefilter_blocks_cloud_skip(
    result: PrefilterResult,
    *,
    config: Mapping[str, Any] | None = None,
) -> bool:
    config = dict(config or prefilter_config())
    if not config.get("enabled"):
        return True
    if not result.prefilter_ready:
        return True
    return result.should_trigger_cloud_vision


def _frame_thumb(image_bytes: bytes) -> tuple[str, Any]:
    import cv2
    import numpy as np

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("prefilter could not decode snapshot image")
    resized = cv2.resize(image, _THUMB_SIZE, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    ok, encoded = cv2.imencode(".jpg", gray, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if not ok:
        raise ValueError("prefilter could not encode frame thumbnail")
    thumb_b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
    return thumb_b64, gray


def _decode_thumb_gray(thumb_b64: str):
    import cv2
    import numpy as np

    try:
        raw = base64.b64decode(thumb_b64)
    except (ValueError, TypeError):
        return None
    array = np.frombuffer(raw, dtype=np.uint8)
    gray = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    return gray


def _motion_mask_top_rows(height: int) -> int:
    top_fraction = float(prefilter_config().get("motion_mask_top") or 0.18)
    return max(1, int(round(height * top_fraction)))


def _motion_roi_mask(gray):
    masked = gray.copy()
    top_rows = _motion_mask_top_rows(masked.shape[0])
    masked[0:top_rows, :] = 0
    return masked


def _motion_score(previous_gray, current_gray) -> tuple[float, int]:
    import cv2

    previous_masked = _motion_roi_mask(previous_gray)
    current_masked = _motion_roi_mask(current_gray)
    diff = cv2.absdiff(previous_masked, current_masked)
    _, mask = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
    motion_pixels = int(cv2.countNonZero(mask))
    height, width = mask.shape[:2]
    total_pixels = max(1, width * (height - _motion_mask_top_rows(height)))
    return motion_pixels / total_pixels, motion_pixels


_ONNX_SESSION = None
_ONNX_MODEL_PATH = ""


def _detect_person(
    image_bytes: bytes,
    *,
    model_path: str,
    confidence_threshold: float,
    input_size: int,
    required: bool = False,
) -> tuple[bool | None, float, int, bool]:
    session = _load_onnx_session(model_path, required=required)
    if session is None:
        return None, 0.0, 0, False

    import cv2
    import numpy as np

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        return None, 0.0, 0, True

    blob, ratio, pad = _letterbox(image, input_size)
    outputs = session.run(None, {session.get_inputs()[0].name: blob})
    boxes = _parse_yolo_outputs(outputs, ratio, pad, image.shape[:2], confidence_threshold)
    person_boxes = [box for box in boxes if box[5] == PERSON_CLASS_ID]
    if not person_boxes:
        return False, 0.0, 0, True
    best = max(person_boxes, key=lambda item: item[4])
    return True, float(best[4]), len(person_boxes), True


def _load_onnx_session(model_path: str, *, required: bool = False):
    global _ONNX_SESSION, _ONNX_MODEL_PATH
    path = str(model_path or "").strip()
    if not path or not Path(path).is_file():
        if required:
            raise PrefilterConfigurationError(f"YOLO prefilter model missing: {path}")
        return None
    if _ONNX_SESSION is not None and _ONNX_MODEL_PATH == path:
        return _ONNX_SESSION
    try:
        import onnxruntime as ort
    except ImportError as exc:
        if required:
            raise PrefilterConfigurationError(
                "onnxruntime is required for YOLO person prefilter."
            ) from exc
        log.warning("onnxruntime not installed; person prefilter disabled")
        return None
    try:
        _ONNX_SESSION = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        _ONNX_MODEL_PATH = path
        return _ONNX_SESSION
    except Exception as exc:
        if required:
            raise PrefilterConfigurationError(
                f"failed to load YOLO prefilter model {path}: {exc}"
            ) from exc
        log.warning("failed to load prefilter onnx model %s: %s", path, exc)
        return None


def _letterbox(image, input_size: int):
    import numpy as np

    height, width = image.shape[:2]
    scale = min(input_size / width, input_size / height)
    new_width = int(round(width * scale))
    new_height = int(round(height * scale))
    import cv2

    resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    pad_x = (input_size - new_width) // 2
    pad_y = (input_size - new_height) // 2
    padded = np.full((input_size, input_size, 3), 114, dtype=np.uint8)
    padded[pad_y : pad_y + new_height, pad_x : pad_x + new_width] = resized
    blob = padded[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
    blob = blob[None, ...]
    return blob, scale, (pad_x, pad_y)


def _parse_yolo_outputs(outputs, ratio: float, pad: tuple[int, int], shape, confidence_threshold: float):
    import numpy as np

    if not outputs:
        return []
    prediction = outputs[0]
    if prediction.ndim == 3:
        prediction = prediction[0]
    if prediction.shape[0] in {84, 85}:
        prediction = prediction.T
    boxes: list[tuple[float, float, float, float, float, int]] = []
    height, width = shape
    pad_x, pad_y = pad
    for row in prediction:
        if row.shape[0] < 6:
            continue
        class_scores = row[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])
        if confidence < confidence_threshold:
            continue
        cx, cy, w, h = row[:4]
        x1 = (cx - w / 2 - pad_x) / ratio
        y1 = (cy - h / 2 - pad_y) / ratio
        x2 = (cx + w / 2 - pad_x) / ratio
        y2 = (cy + h / 2 - pad_y) / ratio
        x1 = max(0.0, min(float(width), x1))
        y1 = max(0.0, min(float(height), y1))
        x2 = max(0.0, min(float(width), x2))
        y2 = max(0.0, min(float(height), y2))
        boxes.append((x1, y1, x2, y2, confidence, class_id))
    return boxes
