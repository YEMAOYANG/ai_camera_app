import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from services.course_storage_registration import archive_registration


class ArchiveRegistrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.media_path = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/current/audio/teacher.wav"
        self.manifest = {"archiveId": "fixture", "complete": True, "missingSources": [], "files": [
            {"archivePath": "原稿/output/current/plan.json", "original": True,
             "sha256": "a"*64, "byteSize": 10, "mimeType": "application/json"},
            {"archivePath": "媒体/" + self.media_path, "original": False,
             "sha256": "b"*64, "byteSize": 40, "mimeType": "audio/wav"},
            {"archivePath": "原稿/Native数据库课堂.json", "original": False,
             "sha256": "c"*64, "byteSize": 20, "mimeType": "application/json"}]}
        self.manifest_path = self.root / "manifest.json"
        self.receipt_path = self.root / "receipt.json"
        self.index = {"archiveId": "fixture", "objectDirectory": "语文/统编版/一年级上册/2026-10-23/课件", "manifestPath": str(self.manifest_path),
            "zip": {"path": str(self.root/"课程.zip")}, "sourceDigest": "d"*64, "sourceKind": "textbook_release",
            "generatedPublicFiles": [
                {"localPath": str(self.manifest_path), "relativePath": "语文/统编版/一年级上册/2026-10-23/课件/清单.json"},
                {"localPath": str(self.root/"课程.zip"), "relativePath": "语文/统编版/一年级上册/2026-10-23/课件/完整课程.zip",
                 "sha256": "e"*64, "byteSize": 1000}]}
        self.receipt_path.write_text(json.dumps({"objects": [{"objectKey": "语文/统编版/一年级上册/2026-10-23/课件/完整课程.zip",
            "etag": '"' + "f"*32 + '"'}]}))
        self.job = {"key": "1"*64, "receiptPath": str(self.receipt_path)}
        self.processor = Mock()
        self.processor._index.return_value = self.index
        self.patcher = patch("services.course_storage_registration.CourseArchiveProcessor", return_value=self.processor)
        self.patcher.start(); self.addCleanup(self.patcher.stop)
        self.write_manifest()

    def write_manifest(self):
        raw = json.dumps(self.manifest).encode()
        self.manifest_path.write_bytes(raw)
        self.index["generatedPublicFiles"][0].update(sha256=hashlib.sha256(raw).hexdigest(), byteSize=len(raw))

    def test_registers_archive_media_paths_even_without_local_or_active_manifest_copy(self):
        meta, files = archive_registration(Mock(), self.job)
        self.assertEqual({f["sourcePath"] for f in files}, {"output/current/plan.json", self.media_path})
        media = next(f for f in files if f["sourcePath"] == self.media_path)
        self.assertEqual(media["locator"]["memberPath"], "媒体/"+self.media_path)
        self.assertEqual(media["locator"]["kind"], "zip_member")
        self.assertEqual(meta["queueJobKey"], self.job["key"])
        self.assertNotEqual(meta["scopeKey"], self.job["key"])

    def test_equivalent_wav_mime_alias_does_not_duplicate_or_conflict(self):
        self.manifest["files"].insert(0, {"archivePath": "原稿/"+self.media_path, "original": True,
            "sha256": "b"*64, "byteSize": 40, "mimeType": "audio/x-wav"})
        self.write_manifest()
        _, files = archive_registration(Mock(), self.job)
        self.assertEqual(len(files), 2)
        self.assertEqual(next(f for f in files if f["sourcePath"]==self.media_path)["mimeType"], "audio/wav")

    def test_manifest_mutation_is_rejected_before_registry_write(self):
        self.manifest_path.write_bytes(self.manifest_path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError, "manifest_not_verified"):
            archive_registration(Mock(), self.job)


if __name__ == "__main__":
    unittest.main()
