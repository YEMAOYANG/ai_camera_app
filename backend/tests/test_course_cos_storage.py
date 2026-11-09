from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.course_storage_config import CourseStorageConfig
from services.course_cos_object_transport import CourseCosResponse, open_cos_object
from services.course_file_store import _RemoteObject
from services.course_media_object_store import CourseMediaObjectStore
from services.courseware_asset_store import CoursewareAssetStore


class _SdkBody:
    def __init__(self, chunks, status=206):
        content = BytesIO(b"".join(chunks))
        self.raw = Mock(status=status)
        self.raw.read.side_effect = lambda size, decode_content: content.read(-1 if size is None else size)

    def get_raw_stream(self):
        return self.raw


class _Response(BytesIO):
    def __init__(self, data, *, status, headers):
        super().__init__(data)
        self.status = status
        self.headers = headers


def _config(**changes):
    values = {
        "COURSE_STORAGE_MODE": "registry",
        "COURSE_STORAGE_PROVIDER": "tencent-cos",
        "COURSE_STORAGE_ADDRESSING_STYLE": "virtual",
        "COURSE_STORAGE_ENDPOINT": "https://cos.ap-guangzhou.myqcloud.com",
        "COURSE_STORAGE_BUCKET": "study-1350855375",
        "COURSE_STORAGE_REGION": "ap-guangzhou",
        "COURSE_STORAGE_ACCESS_KEY": "fixture-secret-id",
        "COURSE_STORAGE_SECRET_KEY": "fixture-secret-key",
    }
    values.update(changes)
    return CourseStorageConfig.from_env(values)


class CourseCosStorageTest(unittest.TestCase):
    def test_cos_configuration_requires_private_signed_virtual_host_settings(self):
        config = _config()
        self.assertEqual(config.provider, "tencent-cos")
        self.assertEqual(config.addressing_style, "virtual")
        self.assertNotIn("fixture-secret", repr(config))
        invalid = [
            {"COURSE_STORAGE_ADDRESSING_STYLE": "path"},
            {"COURSE_STORAGE_ENDPOINT": "https://study-1350855375.cos.ap-guangzhou.myqcloud.com"},
            {"COURSE_STORAGE_ENDPOINT": "http://cos.ap-guangzhou.myqcloud.com"},
            {"COURSE_STORAGE_BUCKET": "study"},
            {"COURSE_STORAGE_ACCESS_KEY": ""},
            {"COURSE_STORAGE_SECRET_KEY": ""},
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                _config(**changes)

    @patch("qcloud_cos.CosS3Client")
    @patch("qcloud_cos.CosConfig")
    def test_official_sdk_signs_private_range_and_pinned_version(self, sdk_config, sdk_client):
        body = _SdkBody([b"ab", b"cdef"])
        sdk_client.return_value.get_object.return_value = {
            "Body": body,
            "Content-Length": "6",
            "Content-Range": "bytes 1-6/10",
            "ETag": '"' + "a" * 32 + '"',
        }
        with open_cos_object(
            _config(), "课程/原稿.json", range_header="bytes=1-6",
            if_match='"' + "a" * 32 + '"', version_id="fixture-version",
        ) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers.get("content-length"), "6")
            self.assertEqual(response.read(3), b"abc")
            self.assertEqual(response.read(), b"def")
        sdk_config.assert_called_once_with(
            Region="ap-guangzhou", SecretId="fixture-secret-id", SecretKey="fixture-secret-key",
            Scheme="https", Timeout=10, AllowRedirects=False, SignHost=True,
            AutoSwitchDomainOnRetry=False,
        )
        sdk_client.return_value.get_object.assert_called_once_with(
            Bucket="study-1350855375", Key="课程/原稿.json", Range="bytes=1-6",
            IfMatch='"' + "a" * 32 + '"', VersionId="fixture-version", AcceptEncoding="identity",
        )
        client_options = sdk_client.call_args.kwargs
        self.assertEqual(client_options["retry"], 0)
        self.assertFalse(client_options["session"].trust_env)
        body.raw.close.assert_called_once_with()

    def test_actual_http_status_and_stream_errors_are_preserved_and_sanitized(self):
        body = _SdkBody([b"abc"], status=200)
        session = Mock()
        with CourseCosResponse({"Body": body}, session=session) as response:
            self.assertEqual(response.status, 200)
            body.raw.read.side_effect = RuntimeError("fixture-secret-key")
            with self.assertRaises(OSError) as error:
                response.read(3)
            self.assertNotIn("fixture-secret", str(error.exception))
        session.close.assert_called_once_with()

    def test_registry_reader_preserves_etag_version_and_exact_range(self):
        data = b'0123456789'
        etag = "b" * 32
        response = _Response(data[2:6], status=206, headers={
            "ETag": f'"{etag}"', "Content-Length": "4", "Content-Range": "bytes 2-5/10",
        })
        with patch("services.course_cos_object_transport.open_cos_object", return_value=response) as opened:
            remote = _RemoteObject(_config(), {
                "objectKey": "课程/原稿.json", "etag": etag, "versionId": "version-1",
            }, len(data))
            self.assertEqual(remote.get(2, 6), b"2345")
        opened.assert_called_once_with(
            remote.config, "课程/原稿.json", range_header="bytes=2-5",
            if_match=f'"{etag}"', version_id="version-1",
        )

    def test_manifest_media_uses_signed_cos_read_and_still_hashes_all_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "backend/data/learning-media/narration/job/voice.wav"
            data = b"RIFF" + bytes(4) + b"WAVE" + bytes(52)
            checksum = hashlib.sha256(data).hexdigest()
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schemaVersion": "mira.course-storage.manifest.v1", "snapshotId": "cos-fixture",
                "files": [{"path": source.relative_to(root).as_posix(), "sha256": checksum,
                    "byteSize": len(data), "mimeType": "audio/wav",
                    "objectKey": f"mira-courseware/v1/blobs/sha256/{checksum}"}],
            }))
            config = _config(
                COURSE_STORAGE_MODE="manifest", COURSE_STORAGE_MANIFEST_PATH=str(manifest)
            )
            response = _Response(data, status=200, headers={"Content-Length": str(len(data))})
            with patch("services.course_cos_object_transport.open_cos_object", return_value=response) as opened:
                actual = CourseMediaObjectStore(config=config, project_root=root).read(source)
            self.assertEqual(actual, data)
            opened.assert_called_once_with(config, f"mira-courseware/v1/blobs/sha256/{checksum}")

    def test_courseware_asset_reader_signs_the_manifest_version_and_keeps_hash_checks(self):
        config = _config()
        data = b"course image bytes"
        entry = {"objectKey": "assets/image.png", "byteSize": len(data),
                 "sha256": hashlib.sha256(data).hexdigest(), "etag": '"' + "a" * 32 + '"',
                 "versionId": "cos-image-version"}
        response = _Response(data, status=200, headers={
            "ETag": entry["etag"], "Content-Length": str(len(data)),
        })
        with patch("services.course_cos_object_transport.open_cos_object", return_value=response) as opened:
            actual = CoursewareAssetStore(config=config)._download(config, entry)
        self.assertEqual(actual, data)
        opened.assert_called_once_with(config, entry["objectKey"], if_match=entry["etag"],
                                      version_id="cos-image-version")


if __name__ == "__main__":
    unittest.main()
