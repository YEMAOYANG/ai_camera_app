from dataclasses import replace
import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from core.course_storage_config import CourseStorageConfig
from services.course_file_store import (CourseFileStore, CourseFileStorageError, course_glob,
    course_write_bytes, reset_course_read_versions, _BLOCKS)


class Response(BytesIO):
    def __init__(self, data, *, status, headers):
        super().__init__(data)
        self.status, self.headers = status, headers


class CourseFileStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "output/current/plan.json"
        self.data = b'{"teacher":"approved"}'
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.etag = "a" * 32
        self.entry = {"sourcePath": "output/current/plan.json", "sha256": self.sha,
            "byteSize": len(self.data), "mimeType": "application/json",
            "locator": {"kind": "object", "objectKey": "语文/课件/教案.json", "etag": self.etag}}
        self.repo = Mock()
        self.repo.resolve.side_effect = lambda path, storage_id, expected_sha=None: self.entry
        self.config = CourseStorageConfig(mode="registry", endpoint="http://storage.invalid:9000", bucket="study")
        self.store = CourseFileStore(config=self.config, project_root=self.root, repository=self.repo)
        self.opener = Mock()
        self.requests = []
        self.remote = self.data
        self.opener.open.side_effect = self.response
        self.patcher = patch("services.course_file_store.build_opener", return_value=self.opener)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        _BLOCKS.clear()
        reset_course_read_versions()

    def response(self, request, timeout):
        self.requests.append(request)
        self.assertEqual(request.get_header("If-match"), '"' + self.etag + '"')
        self.assertIsNone(request.get_header("Authorization"))
        headers = {"ETag": '"' + self.etag + '"'}
        selected = request.get_header("Range")
        if selected:
            start, end = map(int, selected.removeprefix("bytes=").split("-"))
            headers.update({"Content-Length": str(end - start + 1),
                "Content-Range": f"bytes {start}-{end}/{len(self.remote)}"})
            return Response(self.remote[start:end+1], status=206, headers=headers)
        headers["Content-Length"] = str(len(self.remote))
        return Response(self.remote, status=200, headers=headers)

    def test_remote_object_even_if_local_is_missing_or_wrong(self):
        self.assertEqual(self.store.read_bytes(self.path, expected_sha256=self.sha), self.data)
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"wrong local copy")
        self.assertEqual(self.store.read_bytes(self.path), self.data)

    def test_registered_network_error_cannot_use_local_copy(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(self.data)
        self.opener.open.side_effect = OSError("secret")
        with self.assertRaises(CourseFileStorageError) as error:
            self.store.read_bytes(self.path)
        self.assertNotIn("secret", str(error.exception))

    def test_local_symlink_cannot_bypass_registered_remote_identity(self):
        self.path.parent.mkdir(parents=True)
        outside = self.root / "shadow.json"
        outside.write_bytes(b"local shadow")
        self.path.symlink_to(outside)
        self.assertEqual(self.store.read_bytes(self.path), self.data)

    def test_unregistered_new_authoring_path_returns_none(self):
        self.repo.resolve.return_value = None
        self.repo.resolve.side_effect = None
        self.assertIsNone(self.store.read_bytes(self.path))
        self.opener.open.assert_not_called()

    def test_wrong_registered_version_size_and_read_limit_fail_before_network(self):
        for kw in ({"expected_sha256": "b" * 64}, {"expected_bytes": 99}, {"max_bytes": 1}):
            with self.subTest(kw=kw), self.assertRaises(CourseFileStorageError):
                self.store.read_bytes(self.path, **kw)
        self.opener.open.assert_not_called()

    def test_old_registered_version_does_not_use_current_or_local(self):
        self.repo.resolve.side_effect = lambda path, storage_id, expected_sha=None: None if expected_sha else self.entry
        with self.assertRaises(CourseFileStorageError):
            self.store.read_bytes(self.path, expected_sha256="c" * 64)

    def test_zip_member_reads_only_conditional_ranges_and_checks_member_hash(self):
        body = BytesIO()
        with zipfile.ZipFile(body, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("padding.bin", b"x" * 1024 * 1024)
            archive.writestr("原稿/output/current/plan.json", self.data)
        self.remote = body.getvalue()
        self.entry["locator"] = {"kind": "zip_member", "objectKey": "语文/课件/完整课件.zip",
            "etag": self.etag, "archiveSha256": hashlib.sha256(self.remote).hexdigest(),
            "archiveByteSize": len(self.remote), "memberPath": "原稿/output/current/plan.json"}
        self.assertEqual(self.store.read_bytes(self.path), self.data)
        self.assertTrue(all(r.get_header("Range") for r in self.requests))
        self.assertLess(sum(int(r.get_header("Range").split("-")[-1]) - int(r.get_header("Range").split("=")[-1].split("-")[0]) + 1
                            for r in self.requests), len(self.remote) // 2)
        self.entry["sha256"] = "b" * 64
        with self.assertRaises(CourseFileStorageError):
            self.store.read_bytes(self.path)

    def test_zip_wrong_etag_range_size_and_member_are_rejected(self):
        self.opener.open.side_effect = lambda *a, **kw: Response(self.data, status=200,
            headers={"ETag": '"' + "b" * 32 + '"', "Content-Length": str(len(self.data))})
        with self.assertRaises(CourseFileStorageError):
            self.store.read_bytes(self.path)

    def test_registry_configuration_needs_no_local_manifest(self):
        config = CourseStorageConfig.from_env({"COURSE_STORAGE_MODE": "registry",
            "COURSE_STORAGE_ENDPOINT": "http://storage.invalid:9000", "COURSE_STORAGE_BUCKET": "study"})
        self.assertEqual(config.manifest_path, "")
        self.assertEqual(config.mode, "registry")

    def test_remote_directory_glob_preserves_nesting_and_paid_fence_discovery(self):
        self.repo.paths_under.return_value = ["output/current/claims/a/intent.json",
            "output/current/claims/a/proof.json", "output/current/claims/b/nested/intent.json"]
        directory = self.root / "output/current/claims"
        with patch("services.course_file_store.CourseFileStore", return_value=self.store):
            self.assertEqual(list(course_glob(directory, "*.json")), [])
            self.assertEqual(list(course_glob(directory, "*/intent.json")), [directory / "a/intent.json"])
            self.assertEqual(list(course_glob(directory, "intent.json", recursive=True)),
                [directory / "a/intent.json", directory / "b/nested/intent.json"])
            self.assertEqual(list(course_glob(directory)), [directory / "a", directory / "b"])

    def test_registered_write_uses_read_version_even_after_another_writer_advances_head(self):
        self.store.read_bytes(self.path)
        self.entry['sha256'] = 'b' * 64  # Another operation advanced the head.
        with patch('services.course_file_store.CourseFileStore', return_value=self.store), \
                patch('services.course_file_writer.CourseFileWriter') as writer:
            writer.return_value.write_bytes.side_effect = ValueError('course_storage_head_changed')
            with self.assertRaisesRegex(ValueError, 'head_changed'):
                course_write_bytes(self.path, b'{"teacher":"revised"}')
            self.assertEqual(writer.return_value.write_bytes.call_args.kwargs['expected_sha256'], self.sha)
        self.assertFalse(self.path.exists())

    def test_registered_write_without_an_operation_read_is_rejected(self):
        with patch('services.course_file_store.CourseFileStore', return_value=self.store), \
                patch('services.course_file_writer.CourseFileWriter') as writer:
            with self.assertRaisesRegex(CourseFileStorageError, 'read before'):
                course_write_bytes(self.path, b'{}')
            writer.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_successful_version_write_advances_only_its_read_token_without_local_shadow(self):
        self.store.read_bytes(self.path)
        revised = b'{"teacher":"revised"}'
        with patch('services.course_file_store.CourseFileStore', return_value=self.store), \
                patch('services.course_file_writer.CourseFileWriter') as writer:
            self.assertTrue(course_write_bytes(self.path, revised))
            self.assertEqual(writer.return_value.write_bytes.call_args.kwargs['expected_sha256'], self.sha)
            self.assertTrue(course_write_bytes(self.path, b'{"teacher":"final"}'))
            self.assertEqual(writer.return_value.write_bytes.call_args.kwargs['expected_sha256'],
                             hashlib.sha256(revised).hexdigest())
            reset_course_read_versions()
            with self.assertRaises(CourseFileStorageError):
                course_write_bytes(self.path, b'{}')
        self.assertFalse(self.path.exists())

    def test_unregistered_write_leaves_existing_local_atomic_creation_to_caller(self):
        self.repo.resolve.side_effect = None
        self.repo.resolve.return_value = None
        with patch('services.course_file_store.CourseFileStore', return_value=self.store), \
                patch('services.course_file_writer.CourseFileWriter') as writer:
            self.assertFalse(course_write_bytes(self.path, b'{}'))
            writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
