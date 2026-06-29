from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pathlib import Path

from services.vision_prefilter_service import (
    PrefilterConfigurationError,
    analyze_prefilter,
    backend_root,
    default_prefilter_model_path,
    ensure_prefilter_model,
    prefilter_blocks_cloud_skip,
    prefilter_runtime_from_result,
    resolve_prefilter_model_path,
    validate_prefilter_runtime,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_PERSON_SAMPLE = _FIXTURES_DIR / "person_sample.jpg"


class VisionPrefilterServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model_path = default_prefilter_model_path()
        if not cls.model_path.is_file():
            raise unittest.SkipTest(
                f"YOLO model missing at {cls.model_path}; run backend/scripts/export_yolov8n_onnx.py"
            )

    def test_validate_prefilter_runtime_ok(self):
        validate_prefilter_runtime()

    def test_validate_prefilter_runtime_missing_model(self):
        with patch(
            "services.vision_prefilter_service.default_prefilter_model_path",
            return_value=default_prefilter_model_path().parent / "missing.onnx",
        ):
            with self.assertRaises(PrefilterConfigurationError):
                validate_prefilter_runtime()

    def test_prefilter_disabled_raises(self):
        with patch.dict(
            os.environ,
            {"APP_PREFILTER_REQUIRED": "0", "APP_PREFILTER_ENABLED": "0"},
            clear=False,
        ):
            with self.assertRaises(PrefilterConfigurationError):
                validate_prefilter_runtime()

    def test_person_sample_detects_human(self):
        if not _PERSON_SAMPLE.is_file():
            self.skipTest(f"person fixture missing at {_PERSON_SAMPLE}")
        image = _PERSON_SAMPLE.read_bytes()
        result = analyze_prefilter(image, previous=None, now_ms=1_000)
        self.assertTrue(result.person_available)
        self.assertTrue(result.person_detected)
        self.assertGreater(result.person_confidence, 0.45)
        self.assertGreaterEqual(result.person_count, 1)
        self.assertTrue(prefilter_blocks_cloud_skip(result))

    def test_relative_model_path_resolves_from_backend_root(self):
        resolved = resolve_prefilter_model_path("assets/vision/yolov8n.onnx")
        self.assertEqual(resolved, backend_root() / "assets" / "vision" / "yolov8n.onnx")

    def test_same_frame_has_low_motion(self):
        image = _solid_jpeg(120, 140, 160)
        first = analyze_prefilter(image, previous=None, now_ms=1_000)
        second = analyze_prefilter(
            image,
            previous=prefilter_runtime_from_result(first),
            now_ms=2_000,
        )
        self.assertTrue(second.motion_available)
        self.assertLess(second.motion_score, 0.02)

    def test_timestamp_overlay_does_not_trigger_motion(self):
        base = _solid_jpeg(120, 140, 160)
        first = analyze_prefilter(base, previous=None, now_ms=1_000)
        overlay = _solid_jpeg_with_top_overlay(base, text_band=(255, 255, 255))
        second = analyze_prefilter(
            overlay,
            previous=prefilter_runtime_from_result(first),
            now_ms=2_000,
        )
        self.assertTrue(second.motion_available)
        self.assertLess(second.motion_score, 0.02)
        self.assertFalse(second.activity_detected)

    def test_changed_frame_has_motion(self):
        first_image = _solid_jpeg(120, 140, 160)
        second_image = _solid_jpeg(220, 40, 60)
        first = analyze_prefilter(first_image, previous=None, now_ms=1_000)
        second = analyze_prefilter(
            second_image,
            previous=prefilter_runtime_from_result(first),
            now_ms=2_000,
        )
        self.assertTrue(second.motion_available)
        self.assertGreater(second.motion_score, 0.02)
        self.assertTrue(second.activity_detected)
        self.assertTrue(prefilter_blocks_cloud_skip(second))

    def test_solid_frame_no_person_blocks_absence_skip_when_ready(self):
        image = _solid_jpeg(120, 140, 160)
        first = analyze_prefilter(image, previous=None, now_ms=1_000)
        second = analyze_prefilter(
            image,
            previous=prefilter_runtime_from_result(first),
            now_ms=2_000,
        )
        self.assertTrue(second.person_available)
        self.assertFalse(second.person_detected)
        self.assertFalse(prefilter_blocks_cloud_skip(second))


class VisionPrefilterModelBootstrapTest(unittest.TestCase):
    def test_ensure_prefilter_model_returns_existing_path(self):
        model_path = default_prefilter_model_path()
        if not model_path.is_file():
            self.skipTest(f"YOLO model missing at {model_path}")
        resolved = ensure_prefilter_model()
        self.assertEqual(resolved, model_path)
        self.assertTrue(resolved.is_file())


def _solid_jpeg(red: int, green: int, blue: int) -> bytes:
    from PIL import Image
    import io

    image = Image.new("RGB", (64, 64), color=(red, green, blue))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _solid_jpeg_with_top_overlay(base_jpeg: bytes, *, text_band: tuple[int, int, int]) -> bytes:
    from PIL import Image, ImageDraw
    import io

    image = Image.open(io.BytesIO(base_jpeg)).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    band_height = max(4, height // 6)
    draw.rectangle((0, 0, width, band_height), fill=text_band)
    draw.text((2, 1), "2026-06-29 15:30:01", fill=(0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
