from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch

from repositories.course_storage_repository import (
    CourseStorageRegistryError, CourseStorageRepository, MAX_SCOPE_BYTES,
    normalize_source_path, storage_id_for, storage_identity,
)
from services.course_archive_queue import storage_identity as queue_identity


class _Connection:
    """Run the repository's real reads/writes against a transactional SQLite DB."""
    def __init__(self, database):
        self.database = database

    def execute(self, sql, params=()):
        self.database.statements.append(sql)
        sql = sql.replace(" FOR UPDATE", "")
        if " ON DUPLICATE KEY UPDATE " in sql:
            sql, update = sql.split(" ON DUPLICATE KEY UPDATE ", 1)
            if "content_sha256=VALUES" in update:
                sql += (" ON CONFLICT(storage_id,source_path_sha256) DO UPDATE SET "
                        "content_sha256=excluded.content_sha256,scope_key=excluded.scope_key,updated_at=excluded.updated_at")
            else:
                sql += " ON CONFLICT DO NOTHING"
        return self.database.raw.execute(sql, tuple(params))


class _Database:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys=ON")
        self.raw.executescript("""
          CREATE TABLE course_storage_files(storage_id TEXT,source_path_sha256 TEXT,content_sha256 TEXT,
            source_path TEXT,byte_size INTEGER,mime_type TEXT,locator_json TEXT,created_at INTEGER,
            PRIMARY KEY(storage_id,source_path_sha256,content_sha256));
          CREATE TABLE course_storage_scopes(storage_id TEXT,scope_key TEXT,preview_key TEXT,content_key TEXT,
            classroom_id TEXT,course_id TEXT,course_version TEXT,scope_json TEXT,bindings_json TEXT,created_at INTEGER,
            PRIMARY KEY(storage_id,scope_key));
          CREATE TABLE course_storage_heads(storage_id TEXT,source_path_sha256 TEXT,content_sha256 TEXT,
            scope_key TEXT,updated_at INTEGER,PRIMARY KEY(storage_id,source_path_sha256),
            FOREIGN KEY(storage_id,source_path_sha256,content_sha256)
              REFERENCES course_storage_files(storage_id,source_path_sha256,content_sha256),
            FOREIGN KEY(storage_id,scope_key) REFERENCES course_storage_scopes(storage_id,scope_key));
        """)
        self.statements = []

    @contextmanager
    def transaction(self):
        with self.raw:
            yield _Connection(self)


class CourseStorageRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.database = _Database()
        self.addCleanup(self.database.raw.close)
        self.repo = CourseStorageRepository(self.database)
        self.storage = storage_id_for("http://storage.invalid:9000", "study")
        self.meta = {"scopeKey": "a" * 64, "jobKey": "a" * 64, "previewKey": "b" * 64,
                     "contentKey": "c" * 64, "classroomId": "stage-fixture", "courseId": "course-fixture",
                     "courseVersion": "v1", "sourceDigest": "d" * 64, "status": "published"}
        self.file = {"sourcePath": "output/textbook-operator-lessons/课程/authoring-job/frozen.json",
                     "sha256": hashlib.sha256(b"original").hexdigest(), "byteSize": 8,
                     "mimeType": "application/json", "locator": {"kind": "zip_member",
                       "objectKey": "科学/教材/一年级/2026-10-23/课程/完整课件.zip", "etag": '"etag-1"',
                       "versionId": "version-1", "archiveSha256": "e" * 64, "archiveByteSize": 1000,
                       "memberPath": "原稿/output/textbook-operator-lessons/课程/authoring-job/frozen.json"}}

    def register(self, *, meta=None, files=None, storage=None, activate=True):
        return self.repo.register_scope(meta or self.meta, files or [self.file], storage or self.storage, activate=activate)

    def test_identity_matches_queue_canonical_contract_and_ignores_no_prefix_field(self):
        for endpoint in ("https://EXAMPLE.invalid:443/", "http://example.invalid:80", "http://[::1]:9000"):
            with self.subTest(endpoint=endpoint):
                identity = queue_identity(endpoint, "study", "test-region")
                raw = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                self.assertEqual(storage_identity(endpoint, "study", "test-region"), identity)
                self.assertEqual(storage_id_for(endpoint, "study", "test-region"), hashlib.sha256(raw).hexdigest())
        for endpoint in ("https://user:secret@example.invalid", "https://example.invalid/other", "https://example.invalid?key=secret"):
            with self.subTest(endpoint=endpoint), self.assertRaises(CourseStorageRegistryError):
                storage_id_for(endpoint, "study")

    def test_real_transaction_registers_exact_versions_scopes_and_heads_idempotently(self):
        result = self.register()
        value = self.repo.resolve(self.file["sourcePath"], self.storage)
        self.assertEqual(value["path"], self.file["sourcePath"])
        self.assertEqual(value["sourcePathSha256"], hashlib.sha256(self.file["sourcePath"].encode()).hexdigest())
        self.assertEqual(value["locator"], self.file["locator"])
        self.assertEqual(self.register(), result)
        self.assertEqual(self.repo.scope(self.meta["scopeKey"], self.storage), result)
        for table in ("course_storage_files", "course_storage_scopes", "course_storage_heads"):
            self.assertEqual(self.database.raw.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 1)

    def test_new_scope_can_advance_head_without_losing_exact_old_content(self):
        self.register()
        newer = {**self.file, "sha256": "f" * 64, "byteSize": 19}
        meta = {**self.meta, "scopeKey": "f" * 64, "sourceDigest": "1" * 64}
        self.register(meta=meta, files=[newer], activate=False)
        self.assertEqual(self.repo.resolve(newer["sourcePath"], self.storage)["sha256"], self.file["sha256"])
        self.assertEqual(self.repo.resolve(newer["sourcePath"], self.storage, expected_sha=newer["sha256"])["byteSize"], 19)
        self.register(meta=meta, files=[newer])
        self.assertEqual(self.repo.resolve(newer["sourcePath"], self.storage)["sha256"], newer["sha256"])
        self.assertEqual(self.repo.resolve(newer["sourcePath"], self.storage, expected_sha=self.file["sha256"])["byteSize"], 8)

    def test_bulk_inactive_scopes_require_explicit_version_selection_and_preserve_other_heads(self):
        self.register(activate=False)
        newer = {**self.file, "sha256": "f" * 64, "byteSize": 19}
        extra = {**self.file, "sourcePath": "output/course/other.json", "sha256": "2" * 64}
        newer_meta = {**self.meta, "scopeKey": "f" * 64}
        self.register(meta=newer_meta, files=[newer, extra], activate=False)
        self.assertIsNone(self.repo.resolve(self.file["sourcePath"], self.storage))
        result = self.repo.activate_heads(newer_meta["scopeKey"], {newer["sourcePath"]: newer["sha256"]}, self.storage)
        self.assertEqual(result["activated"], 1)
        self.assertEqual(self.repo.resolve(newer["sourcePath"], self.storage)["sha256"], newer["sha256"])
        self.assertIsNone(self.repo.resolve(extra["sourcePath"], self.storage))
        # Merely registering the old scope again cannot undo the selected head.
        self.register(activate=False)
        self.assertEqual(self.repo.resolve(newer["sourcePath"], self.storage)["sha256"], newer["sha256"])
        self.assertEqual(self.repo.resolve(newer["sourcePath"], self.storage, expected_sha=self.file["sha256"])["byteSize"], 8)

    def test_archive_activation_only_adds_missing_paths_and_cannot_roll_back_a_newer_edit(self):
        self.register()
        edited = {**self.file, 'sha256': 'f' * 64, 'byteSize': 19}
        edited_meta = {**self.meta, 'scopeKey': 'f' * 64}
        self.register(meta=edited_meta, files=[edited])
        extra = {**self.file, 'sourcePath': 'output/current/new-evidence.json'}
        archive_meta = {**self.meta, 'scopeKey': '1' * 64}
        self.register(meta=archive_meta, files=[self.file, extra], activate=False)
        result = self.repo.activate_missing_heads(archive_meta['scopeKey'], self.storage)
        self.assertEqual((result['activated'], result['preserved']), (1, 1))
        self.assertEqual(self.repo.resolve(self.file['sourcePath'], self.storage)['sha256'], edited['sha256'])
        self.assertEqual(self.repo.head_scope(self.file['sourcePath'], self.storage)['metadata']['scopeKey'], edited_meta['scopeKey'])
        self.assertEqual(self.repo.resolve(extra['sourcePath'], self.storage)['sha256'], extra['sha256'])
        self.assertEqual(self.repo.activate_missing_heads(archive_meta['scopeKey'], self.storage)['activated'], 0)

    def test_archive_activation_preflights_all_bindings_before_creating_any_head(self):
        extra = {**self.file, 'sourcePath': 'output/current/a-first.json'}
        self.register(files=[self.file, extra], activate=False)
        self.database.raw.execute('DELETE FROM course_storage_files WHERE source_path=?', (self.file['sourcePath'],))
        self.database.raw.commit()
        with self.assertRaisesRegex(CourseStorageRegistryError, 'head_file_missing'):
            self.repo.activate_missing_heads(self.meta['scopeKey'], self.storage)
        self.assertIsNone(self.repo.resolve(extra['sourcePath'], self.storage))

    def test_explicit_head_activation_checks_all_bindings_before_any_mutation(self):
        self.register()
        newer = {**self.file, "sourcePath": "output/a-first.json", "sha256": "f" * 64}
        meta = {**self.meta, "scopeKey": "f" * 64}
        self.register(meta=meta, files=[newer], activate=False)
        self.database.statements.clear()
        for mapping in ({newer["sourcePath"]: newer["sha256"], "output/z-unbound.json": "1" * 64},
                        {self.file["sourcePath"]: self.file["sha256"]},
                        {newer["sourcePath"]: self.file["sha256"]}):
            with self.subTest(mapping=mapping), self.assertRaisesRegex(CourseStorageRegistryError, "head_not_bound"):
                self.repo.activate_heads(meta["scopeKey"], mapping, self.storage)
        self.assertFalse(any(statement.startswith(("UPDATE", "INSERT")) for statement in self.database.statements))
        self.assertIsNone(self.repo.resolve(newer["sourcePath"], self.storage))
        self.assertEqual(self.repo.resolve(self.file["sourcePath"], self.storage)["sha256"], self.file["sha256"])
        foreign = storage_id_for("http://other.invalid", "study")
        with self.assertRaisesRegex(CourseStorageRegistryError, "scope_not_found"):
            self.repo.activate_heads(meta["scopeKey"], {newer["sourcePath"]: newer["sha256"]}, foreign)

    def test_explicit_activation_refuses_missing_version_empty_selection_and_invalid_input(self):
        self.register(activate=False)
        self.database.raw.execute("DELETE FROM course_storage_files")
        self.database.raw.commit()
        with self.assertRaisesRegex(CourseStorageRegistryError, "head_file_missing"):
            self.repo.activate_heads(self.meta["scopeKey"], {self.file["sourcePath"]: self.file["sha256"]}, self.storage)
        self.database.statements.clear()
        for mapping in ({}, {"../secret": "f" * 64}, {self.file["sourcePath"]: "BAD"}):
            with self.subTest(mapping=mapping), self.assertRaises(CourseStorageRegistryError):
                self.repo.activate_heads(self.meta["scopeKey"], mapping, self.storage)
        self.assertEqual(self.database.statements, [])

    def test_shared_version_keeps_first_locator_but_rejects_size_or_mime_conflicts_atomically(self):
        self.register()
        shared = deepcopy(self.file)
        shared["locator"]["objectKey"] = "科学/其他课件.zip"
        self.register(meta={**self.meta, "scopeKey": "f" * 64}, files=[shared])
        self.assertEqual(self.repo.resolve(shared["sourcePath"], self.storage)["locator"], self.file["locator"])
        for field, invalid in (("byteSize", 9), ("mimeType", "text/plain")):
            bad = {**shared, field: invalid}
            other = {**self.file, "sourcePath": "output/a-first.json", "sha256": "2" * 64}
            with self.subTest(field=field), self.assertRaisesRegex(CourseStorageRegistryError, "file_conflict"):
                self.register(meta={**self.meta, "scopeKey": "2" * 64}, files=[other, bad])
            self.assertIsNone(self.repo.scope("2" * 64, self.storage))
            self.assertIsNone(self.repo.resolve(other["sourcePath"], self.storage, expected_sha="2" * 64))

    def revision(self, digest="f" * 64, scope="f" * 64):
        return ({**self.meta, "scopeKey": scope, "previousScopeKey": self.meta["scopeKey"]},
                {**deepcopy(self.file), "sha256": digest, "byteSize": 19})

    def test_compare_and_activate_preserves_old_version_and_selects_exact_current_scope(self):
        self.register()
        meta, file = self.revision()
        result = self.repo.compare_and_activate(meta, [file], self.storage,
            expected_old_sha=self.file["sha256"], expected_scope_key=self.meta["scopeKey"])
        self.assertEqual(result, self.repo.head_scope(file["sourcePath"], self.storage))
        self.assertEqual(self.repo.resolve(file["sourcePath"], self.storage)["sha256"], file["sha256"])
        self.assertEqual(self.repo.resolve(file["sourcePath"], self.storage, self.file["sha256"])["byteSize"], 8)
        self.register(meta={**self.meta, "scopeKey": "9" * 64}, activate=False)
        self.assertEqual(self.repo.head_scope(file["sourcePath"], self.storage)["scopeKey"], meta["scopeKey"])
        self.assertTrue(any(sql.startswith("SELECT * FROM course_storage_heads") and sql.endswith("FOR UPDATE")
                            for sql in self.database.statements))

    def test_two_revision_contenders_have_one_winner_and_stale_failure_leaves_no_version_or_scope(self):
        self.register()
        winner_meta, winner_file = self.revision()
        self.repo.compare_and_activate(winner_meta, [winner_file], self.storage, expected_old_sha=self.file["sha256"])
        loser_meta, loser_file = self.revision("2" * 64, "2" * 64)
        self.database.statements.clear()
        with self.assertRaisesRegex(CourseStorageRegistryError, "head_conflict"):
            self.repo.compare_and_activate(loser_meta, [loser_file], self.storage, expected_old_sha=self.file["sha256"])
        self.assertFalse(any(s.startswith(("INSERT", "UPDATE")) for s in self.database.statements))
        self.assertIsNone(self.repo.scope(loser_meta["scopeKey"], self.storage))
        self.assertIsNone(self.repo.resolve(loser_file["sourcePath"], self.storage, loser_file["sha256"]))
        self.assertEqual(self.repo.resolve(winner_file["sourcePath"], self.storage)["sha256"], winner_file["sha256"])

    def test_compare_and_activate_rejects_same_sha_head_scope_race(self):
        self.register()
        other = {**self.meta, "scopeKey": "2" * 64}
        self.register(meta=other)
        meta, file = self.revision()
        with self.assertRaisesRegex(CourseStorageRegistryError, "head_conflict"):
            self.repo.compare_and_activate(meta, [file], self.storage, expected_old_sha=self.file["sha256"],
                                           expected_scope_key=self.meta["scopeKey"])
        self.assertIsNone(self.repo.scope(meta["scopeKey"], self.storage))
        self.assertEqual(self.repo.head_scope(file["sourcePath"], self.storage)["scopeKey"], other["scopeKey"])

    def test_compare_and_activate_validates_immutable_scope_and_version_before_any_insert(self):
        self.register()
        meta, file = self.revision()
        self.register(meta=meta, files=[file], activate=False)
        for bad_meta, bad_file, code in (({**meta, "status": "changed"}, file, "scope_conflict"),
                                       (meta, {**file, "byteSize": 20}, "file_conflict")):
            self.database.statements.clear()
            with self.subTest(code=code), self.assertRaisesRegex(CourseStorageRegistryError, code):
                self.repo.compare_and_activate(bad_meta, [bad_file], self.storage, expected_old_sha=self.file["sha256"])
            self.assertFalse(any(s.startswith(("INSERT", "UPDATE")) for s in self.database.statements))
        self.assertEqual(self.repo.resolve(file["sourcePath"], self.storage)["sha256"], self.file["sha256"])

    def test_lifecycle_callback_is_inside_locked_transaction_and_failure_writes_nothing(self):
        self.register()
        meta, file = self.revision()
        seen = []
        def reject(conn):
            self.assertTrue(any(s.startswith("SELECT * FROM course_storage_heads") and s.endswith("FOR UPDATE")
                                for s in self.database.statements))
            self.assertFalse(any(s.startswith(("INSERT", "UPDATE")) for s in self.database.statements))
            seen.append(conn)
            raise ValueError("published lifecycle refuses write")
        self.database.statements.clear()
        with self.assertRaisesRegex(ValueError, "lifecycle refuses"):
            self.repo.compare_and_activate(meta, [file], self.storage, expected_old_sha=self.file["sha256"], before_activate=reject)
        self.assertEqual(len(seen), 1)
        self.assertIsNone(self.repo.scope(meta["scopeKey"], self.storage))
        self.assertIsNone(self.repo.resolve(file["sourcePath"], self.storage, file["sha256"]))
        self.assertEqual(self.repo.head_scope(file["sourcePath"], self.storage)["scopeKey"], self.meta["scopeKey"])

    def test_late_compare_and_swap_failure_rolls_back_inserted_scope_and_version(self):
        self.register()
        meta, file = self.revision()
        original = _Connection.execute
        def competing_update(connection, sql, params=()):
            if sql.startswith("UPDATE course_storage_heads SET"):
                return Mock(rowcount=0)
            return original(connection, sql, params)
        with patch.object(_Connection, "execute", competing_update), self.assertRaisesRegex(CourseStorageRegistryError, "head_conflict"):
            self.repo.compare_and_activate(meta, [file], self.storage, expected_old_sha=self.file["sha256"])
        self.assertIsNone(self.repo.scope(meta["scopeKey"], self.storage))
        self.assertIsNone(self.repo.resolve(file["sourcePath"], self.storage, file["sha256"]))
        self.assertEqual(self.repo.resolve(file["sourcePath"], self.storage)["sha256"], self.file["sha256"])

    def test_compare_and_activate_requires_one_existing_head_and_validates_before_sql(self):
        meta, file = self.revision()
        for files in ([], [file, {**file, "sourcePath": "output/other.json"}]):
            with self.subTest(count=len(files)), self.assertRaisesRegex(CourseStorageRegistryError, "selection_invalid"):
                self.repo.compare_and_activate(meta, files, self.storage, expected_old_sha=self.file["sha256"])
        self.assertEqual(self.database.statements, [])
        self.register(activate=False)
        with self.assertRaisesRegex(CourseStorageRegistryError, "head_not_found"):
            self.repo.compare_and_activate(meta, [file], self.storage, expected_old_sha=self.file["sha256"])
        self.assertIsNone(self.repo.head_scope(file["sourcePath"], self.storage))
        self.assertIsNone(self.repo.scope(meta["scopeKey"], self.storage))
        self.assertIsNone(self.repo.resolve(file["sourcePath"], self.storage, file["sha256"]))

    def test_compare_and_activate_keeps_first_locator_and_allows_exact_idempotent_head(self):
        self.register()
        meta, file = self.revision()
        self.register(meta=meta, files=[file], activate=False)
        elsewhere = deepcopy(file)
        elsewhere["locator"]["objectKey"] = "科学/另一份已验证课件.zip"
        self.repo.compare_and_activate(meta, [elsewhere], self.storage, expected_old_sha=self.file["sha256"])
        self.assertEqual(self.repo.resolve(file["sourcePath"], self.storage)["locator"], file["locator"])
        result = self.repo.compare_and_activate(meta, [elsewhere], self.storage,
            expected_old_sha=file["sha256"], expected_scope_key=meta["scopeKey"])
        self.assertEqual(result["scopeKey"], meta["scopeKey"])
        self.assertEqual(self.database.raw.execute("SELECT COUNT(*) FROM course_storage_files").fetchone()[0], 2)

    def test_batch_cas_checks_complete_scope_then_activates_missing_and_existing_heads_atomically(self):
        self.register()
        meta, revised = self.revision()
        extra = {**self.file, "sourcePath": "output/new-supplement.json", "sha256": "2" * 64}
        self.register(meta=meta, files=[revised, extra], activate=False)
        expected = {revised["sourcePath"]: {"sha256": self.file["sha256"], "scopeKey": self.meta["scopeKey"]},
                    extra["sourcePath"]: None}
        result = self.repo.activate_heads_if_unchanged(meta["scopeKey"], self.storage, expected)
        self.assertEqual(result["activated"], 2)
        self.assertEqual(self.repo.resolve(revised["sourcePath"], self.storage)["sha256"], revised["sha256"])
        self.assertEqual(self.repo.head_scope(extra["sourcePath"], self.storage)["scopeKey"], meta["scopeKey"])
        self.assertIsNotNone(self.repo.resolve(revised["sourcePath"], self.storage, self.file["sha256"]))

    def test_batch_cas_scope_coverage_stale_missing_or_scope_changes_reject_before_any_head_write(self):
        self.register()
        meta, revised = self.revision()
        extra = {**self.file, "sourcePath": "output/new-supplement.json", "sha256": "2" * 64}
        self.register(meta=meta, files=[revised, extra], activate=False)
        current = {"sha256": self.file["sha256"], "scopeKey": self.meta["scopeKey"]}
        cases = [({revised["sourcePath"]: current}, "head_not_bound"),
                 ({revised["sourcePath"]: None, extra["sourcePath"]: None}, "head_conflict"),
                 ({revised["sourcePath"]: {**current, "scopeKey": "3" * 64}, extra["sourcePath"]: None}, "head_conflict"),
                 ({revised["sourcePath"]: current, extra["sourcePath"]: current}, "head_conflict")]
        for expected, code in cases:
            self.database.statements.clear()
            with self.subTest(code=code), self.assertRaisesRegex(CourseStorageRegistryError, code):
                self.repo.activate_heads_if_unchanged(meta["scopeKey"], self.storage, expected)
            self.assertFalse(any(s.startswith(("INSERT", "UPDATE")) for s in self.database.statements))
            self.assertIsNone(self.repo.resolve(extra["sourcePath"], self.storage))
        self.assertEqual(self.repo.resolve(revised["sourcePath"], self.storage)["sha256"], self.file["sha256"])

    def test_batch_cas_insert_race_rolls_back_earlier_head_changes(self):
        self.register()
        meta, revised = self.revision()
        revised["sourcePath"] = "output/a-existing.json"
        self.register(meta={**self.meta, "scopeKey": "4" * 64}, files=[{**self.file, "sourcePath": revised["sourcePath"]}])
        extra = {**self.file, "sourcePath": "output/z-new.json", "sha256": "2" * 64}
        self.register(meta=meta, files=[revised, extra], activate=False)
        original = _Connection.execute
        def conflict(connection, sql, params=()):
            if sql.startswith("INSERT INTO course_storage_heads"):
                raise Exception(1062, "simulated duplicate key")
            return original(connection, sql, params)
        expected = {revised["sourcePath"]: {"sha256": self.file["sha256"], "scopeKey": "4" * 64}, extra["sourcePath"]: None}
        with patch.object(_Connection, "execute", conflict), self.assertRaisesRegex(CourseStorageRegistryError, "head_conflict"):
            self.repo.activate_heads_if_unchanged(meta["scopeKey"], self.storage, expected)
        self.assertEqual(self.repo.resolve(revised["sourcePath"], self.storage)["sha256"], self.file["sha256"])
        self.assertEqual(self.repo.head_scope(revised["sourcePath"], self.storage)["scopeKey"], "4" * 64)
        self.assertIsNone(self.repo.resolve(extra["sourcePath"], self.storage))

    def test_scope_identity_and_bindings_are_immutable_with_no_partial_new_version(self):
        self.register()
        for meta, files in (({**self.meta, "courseVersion": "changed"}, [self.file]),
                            (self.meta, [{**self.file, "sha256": "f" * 64}])):
            with self.subTest(meta=meta["courseVersion"]), self.assertRaisesRegex(CourseStorageRegistryError, "scope_conflict"):
                self.register(meta=meta, files=files)
        self.assertIsNone(self.repo.resolve(self.file["sourcePath"], self.storage, expected_sha="f" * 64))
        self.assertEqual(self.repo.resolve(self.file["sourcePath"], self.storage)["sha256"], self.file["sha256"])

    def test_storage_isolation_and_conjunctive_scope_filters(self):
        self.register()
        foreign = storage_id_for("https://storage.invalid", "other-study")
        self.assertIsNone(self.repo.resolve(self.file["sourcePath"], foreign))
        self.assertIsNone(self.repo.scope(self.meta["scopeKey"], foreign))
        self.assertEqual(len(self.repo.find_scopes(storage_id=self.storage, preview_key=self.meta["previewKey"],
                                                 course_id="course-fixture", course_version="v1")), 1)
        self.assertEqual(self.repo.find_scopes(storage_id=self.storage, classroom_id="different"), [])
        with self.assertRaisesRegex(CourseStorageRegistryError, "filter_required"):
            self.repo.find_scopes(storage_id=self.storage)

    def test_active_path_listing_has_exact_directory_and_literal_wildcard_boundaries(self):
        names = ["output/lesson_1/a.json", "output/lesson_1/revisions/b.json", "output/lesson_1-evil/c.json",
                 "output/lessonx1/d.json", "output/lesson%2/a.json", "output/lessonx2/a.json"]
        files = [{**self.file, "sourcePath": name} for name in names]
        self.register(files=files)
        self.assertEqual(self.repo.paths_under("output/lesson_1", self.storage), names[:2])
        self.assertEqual(self.repo.paths_under("output/lesson%2", self.storage), [names[4]])
        self.assertEqual(self.repo.paths_under("output/not-registered", self.storage), [])
        self.assertEqual(self.repo.paths_under("output/lesson_1", "f" * 64), [])
        inactive = {**self.file, "sourcePath": "output/lesson_1/inactive.json"}
        self.register(meta={**self.meta, "scopeKey": "f" * 64}, files=[inactive], activate=False)
        self.assertNotIn(inactive["sourcePath"], self.repo.paths_under("output/lesson_1", self.storage))
        for invalid in ("../output", "backend/services", "openmaic-runtime/.runtime/OpenMAIC/.next"):
            with self.subTest(invalid=invalid), self.assertRaises(CourseStorageRegistryError):
                self.repo.paths_under(invalid, self.storage)

    def test_source_paths_allow_only_course_roots_and_reject_secrets_programs_and_traversal_before_sql(self):
        good = ["output/course/source.py", "backend/content/textbooks/volume/source.json",
                "backend/data/learning-media/narration/file.wav", "openmaic-runtime/native-assets/review-assets/picture.png",
                "openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/jobs/asr/receipt.json"]
        for name in good:
            self.assertEqual(normalize_source_path(name), name)
        bad = ["/output/course.json", "../output/course.json", "output/../secret", "output//file", "output/./file",
               "output\\file", "output/file\n.json", "output/file\x85.json", "C:/output/file", "output/file\ud800",
               "output/.env", "output/.env.production", "output/owner.cookies", "output/key.pem", "output/private.key",
               "output/node_modules/pkg/source.json", "output/.git/config", "output/.next/source.json", "backend/services/source.py",
               "openmaic-runtime/.runtime/OpenMAIC/.next/server/file.json", "openmaic-runtime/.runtime/recovery/file.json"]
        for path in bad:
            with self.subTest(path=repr(path)), self.assertRaises(CourseStorageRegistryError):
                self.register(files=[{**self.file, "sourcePath": path}])
        self.assertEqual(self.database.statements, [])

    def test_locator_identity_and_byte_metadata_fail_before_any_database_write(self):
        loc = self.file["locator"]
        variants = [{**loc, "objectKey": "../object.zip"}, {**loc, "memberPath": "/absolute"},
                    {**loc, "memberPath": "原稿/../secret"}, {**loc, "memberPath": "原稿/.env"},
                    {**loc, "etag": '"etag"\r\nX-Key: secret'}, {**loc, "endpoint": "http://other.invalid"},
                    {**loc, "archiveSha256": "BAD"}, {**loc, "archiveByteSize": True},
                    {**loc, "versionId": "secret\nheader"}, {"kind": "object", "objectKey": "safe.json"},
                    {"kind": "http", "objectKey": "safe.json", "etag": '"etag"'}]
        for locator in variants:
            with self.subTest(locator=locator), self.assertRaises(CourseStorageRegistryError):
                self.register(files=[{**self.file, "locator": locator}])
        for field, value in (("sha256", "A" * 64), ("byteSize", -1), ("byteSize", True),
                             ("mimeType", "text/html\r\nX-Secret: value")):
            with self.subTest(field=field), self.assertRaises(CourseStorageRegistryError):
                self.register(files=[{**self.file, field: value}])
        self.assertEqual(self.database.statements, [])

    def test_duplicate_paths_and_oversized_scope_are_not_registered(self):
        for meta, files in ((self.meta, [self.file, self.file]),
                            ({**self.meta, "oversized": "x" * MAX_SCOPE_BYTES}, [self.file])):
            with self.assertRaises(CourseStorageRegistryError):
                self.register(meta=meta, files=files)
        self.assertEqual(self.database.statements, [])

    def test_direct_object_locator_and_corrupt_database_row_are_checked(self):
        direct = {**self.file, "locator": {"kind": "object", "objectKey": "语文/原稿.json", "etag": '"etag"'}}
        self.register(files=[direct])
        self.assertEqual(self.repo.resolve(direct["sourcePath"], self.storage)["locator"], direct["locator"])
        self.database.raw.execute("UPDATE course_storage_files SET source_path='output/changed.json'")
        self.database.raw.commit()
        with self.assertRaisesRegex(CourseStorageRegistryError, "record_invalid"):
            self.repo.resolve(direct["sourcePath"], self.storage)

    def test_migration_is_additive_and_contains_only_the_three_registry_tables(self):
        migration = Path(__file__).parents[1] / "migrations/089_course_storage_registry.sql"
        sql = migration.read_text()
        self.assertEqual(sql.count("CREATE TABLE IF NOT EXISTS course_storage_"), 3)
        self.assertNotRegex(sql.upper(), r"\b(?:ALTER|DROP|DELETE|TRUNCATE|UPDATE)\s+(?:TABLE\s+)?learning_")
        self.assertIn("OCTET_LENGTH(locator_json) <= 16384", sql)
        self.assertIn("OCTET_LENGTH(scope_json) + OCTET_LENGTH(bindings_json) <= 8388608", sql)


if __name__ == "__main__":
    unittest.main()
