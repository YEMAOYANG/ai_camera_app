import hashlib
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from routes.api.v2.student_textbooks import student_textbooks_bp
from services.courseware_asset_store import CoursewareAssetNotFound, CoursewareAssetStorageError


class CoursewareAssetRouteTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(student_textbooks_bp, url_prefix="/api/v2/student/learning/textbooks")
        self.client = app.test_client()
        self.body = b"remote textbook picture"
        self.entry = {"mimeType": "image/webp", "byteSize": len(self.body),
            "sha256": hashlib.sha256(self.body).hexdigest(),
            "etag": '"0123456789abcdef0123456789abcdef"'}
        self.store = Mock()
        self.store.read_public.return_value = (self.entry, self.body)
        patcher = patch("routes.api.v2.student_textbooks.courseware_asset_store", return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, suffix="textbooks/navigation-v1/picture.webp"):
        return self.client.get("/api/v2/student/learning/textbooks/assets/" + suffix)

    def test_returns_only_verified_remote_bytes_with_immutable_headers(self):
        result = self.get()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, self.body)
        self.assertEqual(result.headers["X-Mira-File-Source"], "remote")
        self.assertEqual(result.headers["X-Mira-File-Sha256"], self.entry["sha256"])
        self.assertEqual(result.headers["Cache-Control"], "public, max-age=31536000, immutable")
        self.store.read_public.assert_called_once_with("textbooks/navigation-v1/picture.webp")

    def test_course_cover_dispatches_by_immutable_content_key(self):
        key = "a" * 64
        with patch("routes.api.v2.student_textbooks.textbook_learning_service") as service, patch(
            "services.textbook_directory_cover.read_directory_cover", return_value=(self.entry, self.body)
        ) as read_cover:
            result = self.get(f"textbooks/course-covers-v2/{key}.webp")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, self.body)
        read_cover.assert_called_once_with(service.return_value.repository, key)
        self.store.read_public.assert_not_called()

    def test_unknown_invalid_and_storage_errors_are_explicit_and_sanitized(self):
        self.store.read_public.side_effect = CoursewareAssetNotFound("private location")
        self.assertEqual(self.get().status_code, 404)
        self.store.read_public.side_effect = CoursewareAssetStorageError("private endpoint")
        failed = self.get()
        self.assertEqual(failed.status_code, 502)
        self.assertNotIn("private endpoint", failed.get_data(as_text=True))
        self.store.reset_mock()
        bad = self.client.get("/api/v2/student/learning/textbooks/assets/textbooks/a.png?path=other")
        self.assertEqual(bad.status_code, 400)
        self.store.read_public.assert_not_called()


if __name__ == "__main__":
    unittest.main()
