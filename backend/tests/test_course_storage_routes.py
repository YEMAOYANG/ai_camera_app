from copy import deepcopy
import hashlib
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from core.course_storage_config import CourseStorageConfig
from core.errors import ApiError
from routes.internal.course_storage import internal_course_storage_bp, MAX_HTTP_FILE_BYTES


class _Guard:
    def authorize(self, **kwargs):
        if kwargs["headers"].get("X-Mira-Internal-Token") != "fixture-token":
            raise ApiError("invalid_internal_token", "内部调用未通过校验", 401)
        return {"sourceName": "native-runtime"}


class CourseStorageRoutesTest(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["DATABASE_URL"] = "mysql+pymysql://unused.invalid/test"
        app.register_blueprint(internal_course_storage_bp, url_prefix="/internal/learning/course-storage")
        self.client = app.test_client()
        self.data = b'{"original":"course"}'
        self.asset = {"sourcePath": "output/course/frozen.json", "path": "output/course/frozen.json",
                      "sha256": hashlib.sha256(self.data).hexdigest(), "byteSize": len(self.data),
                      "mimeType": "application/json", "locator": {"kind": "object",
                      "objectKey": "科学/课件/原稿.json", "etag": '"fixture-etag"'}}
        self.repo = Mock()
        self.repo.resolve.side_effect = lambda *_a, **_kw: deepcopy(self.asset)
        self.config = CourseStorageConfig(mode="remote", endpoint="http://storage.invalid:9000/", bucket="study",
            region="us-east-1", access_key="fixture-access-secret", secret_key="fixture-private-secret")
        for target, value in (("internal_request_guard", _Guard()), ("CourseStorageRepository", self.repo)):
            p = patch("routes.internal.course_storage." + target, return_value=value)
            p.start(); self.addCleanup(p.stop)
        p = patch("routes.internal.course_storage.CourseStorageConfig.from_env", return_value=self.config)
        p.start(); self.addCleanup(p.stop)
        p = patch("routes.internal.course_storage._read_remote", return_value=self.data)
        self.reader = p.start(); self.addCleanup(p.stop)
        self.headers = {"X-Mira-Internal-Token": "fixture-token"}

    def get(self, endpoint="asset", query=None, headers=None):
        return self.client.get("/internal/learning/course-storage/" + endpoint,
            query_string=query or {"path": self.asset["path"]}, headers=self.headers if headers is None else headers)

    def test_both_endpoints_require_existing_internal_guard_before_registry_or_source_read(self):
        for endpoint in ("asset", "file"):
            result = self.get(endpoint, headers={})
            self.assertEqual(result.status_code, 401)
            self.assertEqual(result.json["error"]["code"], "invalid_internal_token")
        self.repo.resolve.assert_not_called()
        self.reader.assert_not_called()

    def test_asset_exposes_only_exact_locator_storage_and_aliases_without_credentials(self):
        result = self.get(query={"path": self.asset["path"], "sha256": self.asset["sha256"]})
        self.assertEqual(result.status_code, 200)
        value = result.json["asset"]
        self.assertEqual(value["sourcePath"], value["path"])
        self.assertEqual(value["locator"], self.asset["locator"])
        self.assertEqual(value["storage"], {"endpoint": "http://storage.invalid:9000", "bucket": "study", "region": "us-east-1"})
        self.assertNotIn("secret", result.get_data(as_text=True))
        self.assertEqual(self.repo.resolve.call_args.kwargs["expected_sha"], self.asset["sha256"])
        self.reader.assert_not_called()

    def test_unknown_has_the_native_not_found_contract_and_never_reads_any_source(self):
        self.repo.resolve.side_effect = None
        self.repo.resolve.return_value = None
        for endpoint in ("asset", "file"):
            result = self.get(endpoint)
            self.assertEqual(result.status_code, 404)
            self.assertEqual(result.json["error"]["code"], "course_storage_asset_not_found")
        self.reader.assert_not_called()

    def test_invalid_or_ambiguous_requests_fail_before_resolve_or_reader(self):
        variants = ({"path": "../secret"}, {"path": "output/.env"}, {"path": "/etc/passwd"},
                    {"path": "backend/services/server.py"}, {"path": "output/course/frozen.json", "sha256": "BAD"},
                    {"path": "output/course/frozen.json", "url": "http://private.invalid"},
                    [("path", "output/course/a.json"), ("path", "output/course/b.json")],
                    [("path", self.asset["path"]), ("sha256", "a" * 64), ("sha256", "b" * 64)])
        for query in variants:
            with self.subTest(query=query):
                result = self.get("file", query=query)
                self.assertEqual(result.status_code, 400, result.json)
        self.repo.resolve.assert_not_called()
        self.reader.assert_not_called()

    def test_file_pins_resolved_version_and_checks_full_bytes_before_returning_remote_headers(self):
        result = self.get("file")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data, self.data)
        self.assertEqual(result.headers["X-Mira-File-Sha256"], self.asset["sha256"])
        self.assertEqual(result.headers["X-Mira-File-Source"], "remote")
        self.assertEqual(result.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(result.headers["Content-Type"], "application/json")
        self.assertEqual(self.reader.call_args.args[3], self.asset["sha256"])
        self.assertIs(self.reader.call_args.args[0], self.config)
        self.assertIs(self.reader.call_args.args[1], self.repo)

    def test_oversize_rejected_before_network_and_storage_faults_do_not_fall_back_or_leak(self):
        self.asset["byteSize"] = MAX_HTTP_FILE_BYTES + 1
        self.assertEqual(self.get("file").status_code, 413)
        self.reader.assert_not_called()
        self.asset["byteSize"] = len(self.data)
        for result in (self.data[:-1], b"x" * len(self.data), None):
            self.reader.return_value = result
            self.assertEqual(self.get("file").status_code, 502)
        self.reader.side_effect = OSError("fixture-private-secret provider dump")
        failed = self.get("file")
        self.assertEqual(failed.status_code, 502)
        self.assertNotIn("fixture-private-secret", failed.get_data(as_text=True))
        self.repo.resolve.side_effect = RuntimeError("fixture-access-secret database error")
        failed = self.get("asset")
        self.assertEqual(failed.status_code, 502)
        self.assertNotIn("fixture-access-secret", failed.get_data(as_text=True))

    def put(self, *, body=None, headers=None, query=None):
        return self.client.put("/internal/learning/course-storage/file", data=body or self.data,
            query_string=query or {"path": self.asset["path"]},
            headers=headers if headers is not None else {**self.headers, "If-Match": self.asset["sha256"], "Content-Type": "application/json"})

    def test_put_requires_guard_read_version_and_json_before_registry_or_writer(self):
        with patch("routes.internal.course_storage._write_remote") as writer:
            self.assertEqual(self.put(headers={}).status_code, 401)
            self.assertEqual(self.put(headers=self.headers).status_code, 428)
            self.assertEqual(self.put(headers={**self.headers, "If-Match": '"' + self.asset["sha256"] + '"', "Content-Type": "application/json"}).status_code, 428)
            self.assertEqual(self.put(headers={**self.headers, "If-Match": self.asset["sha256"], "Content-Type": "text/plain"}).status_code, 400)
            self.repo.resolve.assert_not_called()
            writer.assert_not_called()

    def test_put_preserves_exact_bytes_uses_if_match_and_returns_full_asset(self):
        storage = {"endpoint": "http://storage.invalid:9000", "bucket": "study", "region": "us-east-1"}
        with patch("routes.internal.course_storage._write_remote", return_value={**self.asset, "storage": storage}) as writer:
            result = self.put(body=b'{ "original" : "course" }\n')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["asset"]["storage"], storage)
            self.assertEqual(writer.call_args.args[3], b'{ "original" : "course" }\n')
            self.assertEqual(writer.call_args.args[4], self.asset["sha256"])
            self.assertIsNone(self.repo.resolve.call_args.kwargs["expected_sha"])
            self.reader.assert_not_called()

    def test_put_missing_stale_oversize_or_extra_version_query_cannot_write(self):
        with patch("routes.internal.course_storage._write_remote") as writer:
            self.repo.resolve.side_effect = None
            self.repo.resolve.return_value = None
            self.assertEqual(self.put().status_code, 404)
            self.repo.resolve.return_value = {**self.asset, "sha256": "f" * 64}
            self.assertEqual(self.put().status_code, 409)
            self.repo.resolve.return_value = self.asset
            self.assertEqual(self.put(query={"path": self.asset["path"], "sha256": self.asset["sha256"]}).status_code, 400)
            with patch("routes.internal.course_storage.MAX_HTTP_FILE_BYTES", 8):
                self.assertEqual(self.put(body=b'{"too":"large"}').status_code, 413)
            writer.assert_not_called()

    def test_put_upload_and_cas_errors_are_explicit_and_do_not_leak(self):
        from services.course_file_writer import CourseFileWriteError
        with patch("routes.internal.course_storage._write_remote") as writer:
            for code, status in (("course_storage_head_conflict", 409), ("course_storage_upload_failed", 502),
                                 ("course_storage_published_immutable", 409)):
                writer.side_effect = CourseFileWriteError(code, status)
                result = self.put()
                self.assertEqual(result.status_code, status)
                self.assertEqual(result.json["error"]["code"], code)
            writer.side_effect = RuntimeError("fixture-private-secret")
            failed = self.put()
            self.assertEqual(failed.status_code, 502)
            self.assertNotIn("fixture-private-secret", failed.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
