from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from core.course_storage_config import CourseStorageConfig
from repositories.course_storage_repository import CourseStorageRepository, storage_id_for
from scripts import verify_course_storage_writes as tool
from tests.test_course_storage_repository import _Database


class CourseStorageShadowWriteVerificationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve() / "write-verifications"
        self.state = self.base / "fixture-shadow"
        p = patch.object(tool, "STATE_ROOT", self.base)
        p.start(); self.addCleanup(p.stop)
        self.db = _Database()
        self.addCleanup(self.db.raw.close)
        self.db.raw.create_function("JSON_UNQUOTE", 1, lambda value: value)
        self.db.raw.create_function("JSON_CONTAINS", 2, tool._contains)
        self.db.raw.executescript("""
          CREATE TABLE learning_textbook_course_previews(preview_key TEXT,classroom_id TEXT,status TEXT,classroom_sha256 TEXT);
          CREATE TABLE learning_textbook_course_builds(content_key TEXT,status TEXT,input_json TEXT);
        """)
        self.key = "b" * 64
        self.cid = "stage-shadow"
        self.path = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + self.cid + ".json"
        self.room = {"id": self.cid, "stage": {"id": self.cid, "name": "真实来源的影子"}, "scenes": [{"id": "scene-1"}]}
        self.raw = tool.packed(self.room)
        self.sha = tool.digest(self.raw)
        self.config = CourseStorageConfig(mode="registry", endpoint="http://storage.invalid:9000", bucket="study")
        self.storage = {"endpoint": self.config.endpoint, "bucket": "study", "region": "us-east-1"}
        self.storage_id = storage_id_for(**self.storage)
        self.meta = {"scopeKey": "a" * 64, "previewKey": self.key, "classroomId": self.cid,
            "status": "generated_saved", "sourceKind": "textbook_preview", "sourceDigest": "f" * 64,
            "storageDirectory": "语文/教材/一年级/2026-10-23/影子来源"}
        self.repo = CourseStorageRepository(self.db)
        self.repo.register_scope(self.meta, [{"sourcePath": self.path, "sha256": self.sha, "byteSize": len(self.raw),
            "mimeType": "application/json", "locator": {"kind": "object", "objectKey": "原有/完整原稿.json", "etag": '"original"'}}], self.storage_id)
        self.db.raw.execute("INSERT INTO learning_textbook_course_previews VALUES(?,?,?,?)", (self.key, self.cid, "review_required", self.sha))
        self.db.raw.commit()
        self.app_config = SimpleNamespace(DATABASE_URL="postgresql://unused.invalid/test", INTERNAL_API_TOKEN="fixture-internal-token-that-is-private")
        p = patch.object(tool.CourseStorageConfig, "from_env", return_value=self.config)
        p.start(); self.addCleanup(p.stop)

    def prepare(self):
        with patch.object(tool.CourseFileStore, "read_bytes", return_value=self.raw):
            return tool.prepare(self.key, self.state, app_config=self.app_config, database=self.db)

    def test_prepare_seeds_only_one_exact_head_version_and_keeps_real_rows_unchanged(self):
        before = tool._snapshot(self.db, self.key, self.storage)
        result = self.prepare()
        self.assertEqual(result["originalSha256"], self.sha)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.state / "shadow.sqlite3").stat().st_mode & 0o777, 0o600)
        database = tool.ShadowDatabase(self.state / "shadow.sqlite3")
        repository = CourseStorageRepository(database)
        self.assertEqual(repository.resolve(self.path, self.storage_id)["sha256"], self.sha)
        with database.transaction() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM course_storage_files").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT status FROM learning_textbook_course_previews").fetchone()[0], "review_required")
        self.assertEqual(tool._snapshot(self.db, self.key, self.storage), before)

    def test_prepare_rejects_published_preview_and_shared_published_original_before_creating_state(self):
        self.db.raw.execute("INSERT INTO learning_textbook_course_builds VALUES(?,?,?)",
            ("c" * 64, "published", json.dumps({"previewKey": self.key})))
        self.db.raw.commit()
        with self.assertRaisesRegex(tool.ShadowVerificationError, "preview_is_published"):
            self.prepare()
        self.assertFalse(self.state.exists())
        self.db.raw.execute("DELETE FROM learning_textbook_course_builds")
        self.db.raw.commit()
        self.repo.register_scope({**self.meta, "scopeKey": "c" * 64, "status": "published"},
            [{"sourcePath": self.path, "sha256": self.sha, "byteSize": len(self.raw), "mimeType": "application/json",
              "locator": {"kind": "object", "objectKey": "发布/原稿.json", "etag": '"published"'}}], self.storage_id, activate=False)
        with self.assertRaisesRegex(tool.ShadowVerificationError, "published_parent_reference"):
            self.prepare()
        self.assertFalse(self.state.exists())

    def test_private_boundary_rejects_outside_linked_or_tampered_state(self):
        with self.assertRaisesRegex(tool.ShadowVerificationError, "state_path_invalid"):
            tool._directory(Path(self.tmp.name) / "outside-collection", create=True)
        self.prepare()
        baseline = self.state / "baseline.json"
        value = json.loads(baseline.read_bytes())
        value["snapshot"]["preview"]["status"] = "published"
        baseline.write_bytes(tool.packed(value))
        with self.assertRaisesRegex(tool.ShadowVerificationError, "baseline_invalid"):
            tool._load(self.state)

    def test_production_guard_blueprint_lifecycle_and_cas_write_only_shadow_database(self):
        self.prepare()
        before = tool._snapshot(self.db, self.key, self.storage)
        bodies = {self.sha: self.raw}
        def read(_store, source, *, expected_sha256=None, **_kw):
            if expected_sha256 is None:
                repository = _store.repository
                expected_sha256 = repository.resolve(self.path, self.storage_id)["sha256"]
            return bodies[expected_sha256]
        def upload(_uploader, *, object_key, raw, storage):
            self.assertEqual(storage, self.storage)
            bodies[tool.digest(raw)] = raw
            return {"kind": "object", "objectKey": object_key, "etag": '"new-verified"'}
        with patch.object(tool.Database, "connect", side_effect=AssertionError("real business DB may not connect")), \
             patch.object(tool.CourseFileStore, "read_bytes", autospec=True, side_effect=read), \
             patch.object(tool.NodeCourseFileUploader, "upload", autospec=True, side_effect=upload):
            app, restore = tool.create_shadow_app(self.state, app_config=self.app_config)
            self.addCleanup(restore)
            client = app.test_client()
            url = "/internal/learning/course-storage/file"
            self.assertEqual(client.get(url, query_string={"path": self.path}).status_code, 401)
            headers = {"X-Mira-Internal-Token": self.app_config.INTERNAL_API_TOKEN,
                       "Content-Type": "application/json", "If-Match": self.sha}
            revised = deepcopy(self.room)
            revised["stage"]["name"] = "影子编辑"
            result = client.put(url, query_string={"path": self.path}, data=tool.packed(revised), headers=headers)
            self.assertEqual(result.status_code, 200, result.json)
            self.assertEqual(result.json["asset"]["sha256"], tool.digest(tool.packed(revised)))
            self.assertEqual(client.put(url, query_string={"path": self.path}, data=self.raw, headers=headers).status_code, 409)
            old = client.get(url, query_string={"path": self.path, "sha256": self.sha}, headers=headers)
            self.assertEqual(old.data, self.raw)
            self.assertEqual(old.headers["X-Mira-File-Source"], "remote")
        self.assertEqual(tool._snapshot(self.db, self.key, self.storage), before)
        database = tool.ShadowDatabase(self.state / "shadow.sqlite3")
        with database.transaction() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM course_storage_files").fetchone()[0], 2)
            self.assertGreaterEqual(conn.execute("SELECT COUNT(*) FROM shadow_internal_audits").fetchone()[0], 4)
        attempts = [json.loads(line) for line in (self.state / "object-attempts.jsonl").read_text().splitlines()]
        self.assertEqual([line["phase"] for line in attempts], ["attempt", "verified"])
        self.assertEqual(attempts[0]["objectKey"], attempts[1]["objectKey"])

    def test_verifier_uses_same_cid_old_version_readback_and_rejects_stale_write(self):
        self.prepare()
        changed = deepcopy(self.room)
        changed["stage"]["name"] += "〔存储写入验收〕"
        changed_sha = tool.digest(tool.packed(changed))
        sequence = [(200, {"X-Mira-File-Sha256": self.sha}, tool.packed({"classroom": self.room})),
                    (201, {"X-Mira-File-Sha256": changed_sha}, b"{}"),
                    (200, {"X-Mira-File-Sha256": changed_sha}, tool.packed({"classroom": changed})),
                    (409, {}, b"{}"), (200, {"X-Mira-File-Source": "remote"}, self.raw),
                    (201, {"X-Mira-File-Sha256": "f" * 64}, b"{}"), (200, {}, tool.packed({"classroom": self.room}))]
        with patch.object(tool, "_http", side_effect=sequence) as http:
            result = tool.verify(self.state, "http://127.0.0.1:3103", "http://127.0.0.1:8003",
                                 app_config=self.app_config, database=self.db)
        self.assertTrue(result["realDatabaseUnchanged"])
        self.assertEqual(http.call_args_list[3].kwargs["headers"]["If-Match"], self.sha)
        self.assertIn("sha256=" + self.sha, http.call_args_list[4].args[0])
        self.assertEqual(http.call_args_list[5].kwargs["headers"]["If-Match"], changed_sha)
        self.assertTrue(result["oldVersionReadback"])

    def test_verifier_refuses_nonloopback_or_source_metadata_changes_before_http(self):
        self.prepare()
        with patch.object(tool, "_http") as http:
            for url in ("https://127.0.0.1:3103", "http://example.invalid:3103", "http://127.0.0.1:3103/path", "http://user:pass@127.0.0.1:3103"):
                with self.assertRaises(tool.ShadowVerificationError):
                    tool.verify(self.state, url, "http://127.0.0.1:8003", app_config=self.app_config, database=self.db)
            self.db.raw.execute("UPDATE learning_textbook_course_previews SET status='preview_ready'")
            with self.assertRaisesRegex(tool.ShadowVerificationError, "real_source_changed"):
                tool.verify(self.state, "http://127.0.0.1:3103", "http://127.0.0.1:8003", app_config=self.app_config, database=self.db)
            http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
