from __future__ import annotations

from dataclasses import replace
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote, unquote, urlsplit

from core.course_storage_config import CourseStorageConfig
from services.course_media_object_store import CourseMediaObjectStore, CourseMediaStorageError, _NoRedirect
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore


class _Response(BytesIO):
    status = 200

    def __init__(self, data: bytes, length: int | None = None):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data) if length is None else length)}


class CourseMediaObjectStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="course-media-store-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "backend/data/learning-media/narration/job/voice.wav"
        self.source.parent.mkdir(parents=True)
        self.data = b"RIFF" + bytes(4) + b"WAVE" + bytes(52)
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.manifest_path = self.root / "manifest.json"
        self.entry = {"path": self.source.relative_to(self.root).as_posix(),
                      "sha256": self.sha, "byteSize": len(self.data), "mimeType": "audio/wav",
                      "objectKey": f"mira-courseware/v1/blobs/sha256/{self.sha}"}
        self._manifest()
        self.config = CourseStorageConfig.from_env({
            "COURSE_STORAGE_MODE": "manifest", "COURSE_STORAGE_ENDPOINT": "http://storage.invalid:9000",
            "COURSE_STORAGE_BUCKET": "study", "COURSE_STORAGE_MANIFEST_PATH": str(self.manifest_path),
            "COURSE_STORAGE_ACCESS_KEY": "fixture-access", "COURSE_STORAGE_SECRET_KEY": "fixture-secret",
        })
        self.store = CourseMediaObjectStore(config=self.config, project_root=self.root)
        self.opener = Mock()
        self.opener.open.side_effect = lambda *_args, **_kwargs: _Response(self.data)
        opener_patch = patch("services.course_media_object_store.build_opener", return_value=self.opener)
        opener_patch.start()
        self.addCleanup(opener_patch.stop)

    def _manifest(self, schema="mira.course-storage.manifest.v1"):
        self.manifest_path.write_text(json.dumps({"schemaVersion": schema,
                                                 "snapshotId": "fixture", "files": [self.entry]}))

    def test_public_get_validates_real_bytes_without_a_local_copy_or_any_credentials(self):
        self.assertFalse(self.source.exists())
        actual = self.store.read(self.source, expected_sha256=self.sha, expected_bytes=len(self.data))
        self.assertEqual(actual, self.data)
        req = self.opener.open.call_args.args[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, f"http://storage.invalid:9000/study/{self.entry['objectKey']}")
        self.assertEqual(req.header_items(), [])
        self.assertNotIn("fixture-secret", repr(self.config))
        self.assertNotIn("fixture-access", repr(self.config))

    def test_unlisted_is_local_but_strict_remote_is_closed(self):
        unknown = self.source.with_name("unlisted.wav")
        self.assertIsNone(self.store.read(unknown))
        self.opener.open.assert_not_called()
        remote = CourseMediaObjectStore(config=replace(self.config, mode="remote"), project_root=self.root)
        with self.assertRaises(CourseMediaStorageError):
            remote.read(unknown)

    def test_registered_failure_never_falls_back_to_even_a_valid_local_copy(self):
        self.source.write_bytes(self.data)
        self.opener.open.side_effect = OSError("fixture-secret network error")
        with self.assertRaises(CourseMediaStorageError) as rejected:
            self.store.read(self.source)
        self.assertNotIn("fixture-secret", str(rejected.exception))

    def test_database_hash_size_and_delivery_limits_are_checked_before_network(self):
        for constraints in [{"expected_sha256": "a" * 64}, {"expected_bytes": 65}, {"max_bytes": 63}]:
            with self.subTest(constraints=constraints), self.assertRaises(CourseMediaStorageError):
                self.store.read(self.source, **constraints)
        self.opener.open.assert_not_called()

    def test_truncation_extra_bytes_wrong_hash_and_declared_length_fail_closed(self):
        for body, length in [(self.data[:-1], 64), (self.data + b"x", 65), (b"x" * 64, 64), (self.data, 65)]:
            self.opener.open.side_effect = lambda *_a, **_kw: _Response(body, length)
            with self.subTest(length=length), self.assertRaises(CourseMediaStorageError):
                self.store.read(self.source)

    def test_untrusted_manifest_key_or_path_is_rejected_and_atomic_replacement_is_seen(self):
        self.entry["objectKey"] = "../../private"
        self._manifest()
        with self.assertRaises(CourseMediaStorageError):
            self.store.read(self.source)
        self.entry["objectKey"] = f"mira-courseware/v1/blobs/sha256/{self.sha}"
        self._manifest()
        self.assertEqual(self.store.read(self.source), self.data)
        self.entry["path"] = "../private"
        self._manifest()
        with self.assertRaises(CourseMediaStorageError):
            self.store.read(self.source)

    def test_redirect_and_credential_bearing_endpoint_are_never_used(self):
        with self.assertRaises(CourseMediaStorageError):
            _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://other.invalid/private")
        env = {"COURSE_STORAGE_MODE": "manifest", "COURSE_STORAGE_ENDPOINT": "http://user:secret@storage.invalid",
               "COURSE_STORAGE_BUCKET": "study", "COURSE_STORAGE_MANIFEST_PATH": str(self.manifest_path)}
        with self.assertRaises(ValueError):
            CourseStorageConfig.from_env(env)

    def test_v2_names_and_reserved_characters_are_encoded_without_changing_byte_identity(self):
        key = "2026-10-23/语文/一年级上册-金木水火土?问#号%/金木水火土-老师讲解-%2F-001.wav"
        self.entry["objectKey"] = key
        self._manifest("mira.course-storage.manifest.v2")
        store = CourseMediaObjectStore(config=replace(self.config, prefix="2026-10-23"), project_root=self.root)
        self.assertEqual(store.read(self.source, expected_sha256=self.sha, expected_bytes=len(self.data)), self.data)
        req = self.opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "http://storage.invalid:9000/study/" +
                         "/".join(quote(segment, safe="") for segment in key.split("/")))
        parts = urlsplit(req.full_url)
        self.assertEqual(parts.query, "")
        self.assertEqual(parts.fragment, "")
        self.assertEqual(unquote(parts.path), "/study/" + key)
        self.assertIn("%252F", parts.path)
        self.assertFalse(self.source.exists())

    def test_v2_rejects_unsafe_names_mime_mismatches_and_non_media_before_network(self):
        prefix = "2026-10-23"
        store = CourseMediaObjectStore(config=replace(self.config, prefix=prefix), project_root=self.root)
        keys = [
            "2026-10-230/语文/课件/讲解.wav", f"{prefix}/语文/讲解.wav", f"{prefix}/语文/一年级/课件/讲解.wav",
            f"{prefix}/ /课件/讲解.wav", f"{prefix}/./课件/讲解.wav", f"{prefix}/语文/../讲解.wav",
            f"{prefix}/语文/课件/讲\\解.wav", f"{prefix}/语文/课件/讲\x00解.wav",
            f"{prefix}/语文/课件/讲\x7f解.wav", f"{prefix}/语文/课件/讲\x85解.wav",
            f"{prefix}/语文/{'课' * 86}/讲解.wav", f"{prefix}/语文/课件/图片.png",
            f"{prefix}/语文/课件/课件.html", f"{prefix}/语文/课件/索引.json", f"{prefix}/语文/课件/模型.glb",
        ]
        for key in keys:
            with self.subTest(key=repr(key)):
                self.entry["objectKey"] = key
                self._manifest("mira.course-storage.manifest.v2")
                with self.assertRaises(CourseMediaStorageError):
                    store.read(self.source)
        self.opener.open.assert_not_called()

    def test_subject_edition_grade_date_course_layout_requires_explicit_flag_and_matching_date(self):
        key = "语文/统编版-上册/一年级/2026-10-23/金木水火土/金木水火土-音频-001.wav"
        self.entry["objectKey"] = key
        store = CourseMediaObjectStore(config=replace(self.config, prefix="2026-10-23"), project_root=self.root)
        def write(layout="subject-edition-grade-date-course-v1"):
            self.manifest_path.write_text(json.dumps({"schemaVersion": "mira.course-storage.manifest.v2",
                "snapshotId": "subject", "keyLayout": layout, "files": [self.entry]}))
        write()
        self.assertEqual(store.read(self.source), self.data)
        for invalid in [key.replace("2026-10-23", "2026-10-22"), key.replace("/一年级/", "/../"), key + "/x"]:
            self.entry["objectKey"] = invalid
            write()
            with self.assertRaises(CourseMediaStorageError):
                store.read(self.source)
        self.entry["objectKey"] = key
        for layout in [None, "unknown-layout"]:
            write(layout)
            with self.assertRaises(CourseMediaStorageError):
                store.read(self.source)

    def test_archive_configuration_is_explicit_and_validates_storage_even_for_local_delivery(self):
        self.assertFalse(CourseStorageConfig.from_env({}).archive_enabled)
        for flag in ["yes", "mistyped"]:
            with self.assertRaises(ValueError):
                CourseStorageConfig.from_env({"COURSE_STORAGE_ARCHIVE_ENABLED": flag})
        with self.assertRaises(ValueError):
            CourseStorageConfig.from_env({"COURSE_STORAGE_ARCHIVE_ENABLED": "1"})

    def test_v1_does_not_accept_named_keys_and_v2_keeps_distinct_keys_for_equal_hashes(self):
        self.entry["objectKey"] = "2026-10-23/语文/课件一/课件一-老师讲解-001.wav"
        self._manifest()
        store = CourseMediaObjectStore(config=replace(self.config, prefix="2026-10-23"), project_root=self.root)
        with self.assertRaises(CourseMediaStorageError):
            store.read(self.source)
        other = self.source.with_name("second.wav")
        other_entry = {**self.entry, "path": other.relative_to(self.root).as_posix(),
                       "objectKey": "2026-10-23/语文/课件二/课件二-老师讲解-001.wav"}
        self.manifest_path.write_text(json.dumps({"schemaVersion": "mira.course-storage.manifest.v2",
                                                 "snapshotId": "two-courses", "files": [self.entry, other_entry]}))
        self.assertEqual(store.read(self.source), self.data)
        self.assertEqual(store.read(other), self.data)
        urls = [call.args[0].full_url for call in self.opener.open.call_args_list]
        self.assertEqual(len(set(urls)), 2)

    def test_asset_store_readback_uses_migrated_bytes_but_new_writes_stay_local(self):
        local_root = self.root / "backend/data/learning-media"
        store = FilesystemLearningMediaAssetStore(local_root, course_media_store=self.store)
        self.assertEqual(store.read_audio("narration/job/voice.wav"), self.data)
        written = store.put_audio(job_id="new", segment_id="speech", content_hash=self.sha,
                                  mime_type="audio/wav", audio=self.data)
        self.assertEqual((local_root / written.storage_key).read_bytes(), self.data)
        self.assertEqual(store.read_audio(written.storage_key), self.data)
        with self.assertRaises(ValueError):
            store.read_audio("../../private")


if __name__ == "__main__":
    unittest.main()
