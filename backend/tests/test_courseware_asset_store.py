import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.course_storage_config import CourseStorageConfig
from services.courseware_asset_store import (
    CoursewareAssetNotFound, CoursewareAssetStorageError, CoursewareAssetStore,
)


class _Response:
    def __init__(self, body, *, etag='"0123456789abcdef0123456789abcdef"'):
        self.body = body
        self.offset = 0
        self.status = 200
        self.headers = {"Content-Length": str(len(body)), "Content-Encoding": "identity", "ETag": etag}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        if size < 0:
            size = len(self.body) - self.offset
        value = self.body[self.offset:self.offset + size]
        self.offset += len(value)
        return value


class _Opener:
    def __init__(self, body):
        self.body = body
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return _Response(self.body)


class CoursewareAssetStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.body = b"verified course picture"
        self.sha = hashlib.sha256(self.body).hexdigest()
        self.path = Path(self.temp.name) / "manifest.json"
        self.entry = {
            "sourcePath": "student-web/public/textbooks/navigation-v1/picture.png",
            "publicPath": "/textbooks/navigation-v1/picture.png",
            "objectKey": "courseware/v1/picture.png", "sha256": self.sha,
            "byteSize": len(self.body), "mimeType": "image/png",
            "etag": '"0123456789abcdef0123456789abcdef"',
        }
        self.manifest = {
            "schemaVersion": "mira.courseware-assets.v1", "snapshotId": "fixture-v1",
            "storage": {"endpoint": "http://storage.invalid:9000", "bucket": "study", "region": "us-east-1"},
            "files": [self.entry],
        }
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.config = CourseStorageConfig(mode="registry", endpoint="http://storage.invalid:9000",
            bucket="study", region="us-east-1")

    def store(self, body=None):
        opener = _Opener(self.body if body is None else body)
        return CoursewareAssetStore(config=self.config, manifest_path=self.path, opener=opener), opener

    def test_listed_asset_is_read_remotely_and_fully_verified(self):
        store, opener = self.store()
        entry, body = store.read_public("textbooks/navigation-v1/picture.png")
        self.assertEqual(body, self.body)
        self.assertEqual(entry["sha256"], self.sha)
        request, timeout = opener.requests[0]
        self.assertEqual(request.get_header("If-match"), self.entry["etag"])
        self.assertIn("/study/courseware/v1/picture.png", request.full_url)
        self.assertEqual(timeout, 10)

    def test_unlisted_path_never_opens_storage_or_falls_back_to_disk(self):
        store, opener = self.store()
        with self.assertRaises(CoursewareAssetNotFound):
            store.read_public("textbooks/navigation-v1/missing.png")
        self.assertEqual(opener.requests, [])

    def test_changed_bytes_or_storage_identity_fail_closed(self):
        store, _ = self.store(b"changed course picture")
        with self.assertRaises(CoursewareAssetStorageError):
            store.read_public("textbooks/navigation-v1/picture.png")
        wrong = CourseStorageConfig(mode="registry", endpoint="http://other.invalid:9000",
            bucket="study", region="us-east-1")
        with self.assertRaises(CoursewareAssetStorageError):
            CoursewareAssetStore(config=wrong, manifest_path=self.path).read_public(
                "textbooks/navigation-v1/picture.png")

    def test_public_path_must_match_its_recovery_source(self):
        self.manifest["files"][0]["publicPath"] = "/textbooks/other.png"
        self.path.write_text(json.dumps(self.manifest), encoding="utf-8")
        store, _ = self.store()
        with self.assertRaises(CoursewareAssetStorageError):
            store.read_public("textbooks/other.png")

    def test_non_object_manifest_fails_closed_with_sanitized_error(self):
        self.path.write_text("[]", encoding="utf-8")
        store, opener = self.store()
        with self.assertRaisesRegex(CoursewareAssetStorageError, "manifest is invalid"):
            store.read_public("textbooks/navigation-v1/picture.png")
        self.assertEqual(opener.requests, [])


if __name__ == "__main__":
    unittest.main()
