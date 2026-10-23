"""Opt-in MySQL protocol checks, not business-service or provider acceptance.

Run with MIRA_MYSQL_LOCK_PROTOCOL=1. Only the existing validated local
ai_camera_app_test database is allowed. Each run owns randomly named InnoDB
tables; no application table is queried or changed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import json
import os
import re
from threading import Barrier, Event
import unittest
import uuid

from core.database import Database
from tests.support import validated_test_database_url


class ProtocolConflict(ValueError):
    pass


def _raw(name):
    return json.dumps({"id": "isolated-classroom", "revision": name},
                      sort_keys=True, separators=(",", ":"))


PAYLOADS = {name: _raw(name) for name in "ABC"}
SHAS = {name: hashlib.sha256(raw.encode()).hexdigest() for name, raw in PAYLOADS.items()}


@unittest.skipUnless(os.getenv("MIRA_MYSQL_LOCK_PROTOCOL") == "1",
                     "requires explicit isolated MySQL protocol opt-in")
class CourseStorageMySQLLockProtocolTest(unittest.TestCase):
    """Model the reviewed row/head protocol with real separate connections."""

    @classmethod
    def setUpClass(cls):
        cls.database = Database(validated_test_database_url())
        cls.prefix = "mira_lock_" + uuid.uuid4().hex
        cls.created = []
        # Verify the server boundary before even constructing DDL.
        with cls.database.transaction() as conn:
            identity = conn.execute("SELECT DATABASE() AS db").fetchone()
        if identity["db"] != "ai_camera_app_test":
            raise RuntimeError("isolated_test_database_required")
        definitions = {
            "previews": "id VARCHAR(32) PRIMARY KEY, classroom_sha CHAR(64) NOT NULL, "
                        "body_json LONGTEXT NOT NULL, result_json LONGTEXT NOT NULL, "
                        "status VARCHAR(32) NOT NULL, updated_at BIGINT NOT NULL",
            "heads": "id VARCHAR(32) PRIMARY KEY, content_sha CHAR(64) NOT NULL, scope_key VARCHAR(32) NOT NULL",
            "versions": "content_sha CHAR(64) PRIMARY KEY, body_json LONGTEXT NOT NULL",
            "builds": "preview_id VARCHAR(32) PRIMARY KEY, release_sha CHAR(64) NOT NULL",
        }
        try:
            with cls.database.transaction() as conn:
                for name, definition in definitions.items():
                    # Remember the exact owned name before DDL, including a
                    # lost server response after a successful CREATE.
                    cls.created.append(name)
                    conn.execute(f"CREATE TABLE {cls.table(name)} ({definition}) ENGINE=InnoDB")
        except Exception:
            cls._drop_owned()
            raise

    @classmethod
    def table(cls, name):
        identifier = cls.prefix + "_" + name
        if name not in {"previews", "heads", "versions", "builds"} or not re.fullmatch(
                r"mira_lock_[a-f0-9]{32}_(previews|heads|versions|builds)", identifier):
            raise ValueError("isolated_table_name_invalid")
        return "`" + identifier + "`"

    @classmethod
    def _drop_owned(cls):
        # Exact names only: never discover or sweep another run's tables.
        failures = []
        for name in reversed(cls.created):
            try:
                with cls.database.transaction() as conn:
                    conn.execute(f"DROP TABLE IF EXISTS {cls.table(name)}")
            except Exception as exc:
                failures.append(cls.table(name) + ":" + type(exc).__name__)
        if failures:
            raise RuntimeError("isolated_table_cleanup_failed:" + ",".join(failures))
        cls.created.clear()

    @classmethod
    def tearDownClass(cls):
        cls._drop_owned()

    @contextmanager
    def transaction(self):
        with self.database.transaction() as conn:
            conn.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            conn.execute("SET SESSION innodb_lock_wait_timeout=2")
            yield conn

    def setUp(self):
        with self.transaction() as conn:
            for name in ("builds", "heads", "previews", "versions"):
                conn.execute(f"DELETE FROM {self.table(name)}")
            for name, raw in PAYLOADS.items():
                conn.execute(f"INSERT INTO {self.table('versions')} VALUES (?,?)", (SHAS[name], raw))
            conn.execute(f"INSERT INTO {self.table('heads')} VALUES ('source',?,'scope-a')", (SHAS["A"],))
            conn.execute(f"INSERT INTO {self.table('previews')} VALUES ('preview',?,?,?,'preview_ready',1)",
                         (SHAS["A"], PAYLOADS["A"], '{"review":1}'))

    @staticmethod
    def wait(event):
        if not event.wait(5):
            raise RuntimeError("isolated_barrier_timeout")

    def head(self, conn):
        return conn.execute(f"SELECT * FROM {self.table('heads')} WHERE id='source'").fetchone()

    def preview(self, conn, *, lock=False):
        return conn.execute(f"SELECT * FROM {self.table('previews')} WHERE id='preview'"
                            + (" FOR UPDATE" if lock else "")).fetchone()

    def fresh_source(self):
        # Match CourseFileStore.resolve: a fresh ordinary-read transaction,
        # separate from the publisher's locking transaction and its snapshot.
        with self.transaction() as conn:
            row = conn.execute(f"SELECT h.content_sha,v.body_json FROM {self.table('heads')} h "
                               f"JOIN {self.table('versions')} v ON v.content_sha=h.content_sha "
                               "WHERE h.id='source'").fetchone()
        if hashlib.sha256(row["body_json"].encode()).hexdigest() != row["content_sha"]:
            raise ProtocolConflict("remote_integrity")
        return row

    def unpublished(self, conn):
        if conn.execute(f"SELECT * FROM {self.table('builds')} WHERE preview_id='preview' FOR UPDATE").fetchone():
            raise ProtocolConflict("published_immutable")

    def activate(self, target="B", *, after_head=None, before_preview=None,
                 expected_sha=None, expected_scope="scope-a"):
        with self.transaction() as conn:
            head = conn.execute(f"SELECT * FROM {self.table('heads')} WHERE id='source' FOR UPDATE").fetchone()
            if (head["content_sha"] != (expected_sha or SHAS["A"])
                    or head["scope_key"] != expected_scope):
                raise ProtocolConflict("head_conflict")
            if after_head:
                after_head()
            if before_preview:
                before_preview()
            self.preview(conn, lock=True)
            self.unpublished(conn)
            conn.execute(f"UPDATE {self.table('heads')} SET content_sha=?,scope_key=? WHERE id='source'",
                         (SHAS[target], "scope-" + target.lower()))

    def publish(self, conn, *, after_preview=None):
        row = self.preview(conn, lock=True)
        if row["classroom_sha"] != SHAS["A"] or row["status"] != "preview_ready":
            raise ProtocolConflict("sql_frozen_changed")
        if after_preview:
            after_preview()
        if self.fresh_source()["content_sha"] != row["classroom_sha"]:
            raise ProtocolConflict("remote_frozen_changed")
        conn.execute(f"INSERT INTO {self.table('builds')} VALUES ('preview',?)", (SHAS["A"],))

    def finalize(self, baseline, *, target="B", force_rollback=False):
        with self.transaction() as conn:
            current = self.preview(conn, lock=True)
            self.unpublished(conn)
            if any(current[key] != baseline[key] for key in
                   ("classroom_sha", "body_json", "result_json", "status", "updated_at")):
                raise ProtocolConflict("sql_compare_changed")
            if self.fresh_source()["content_sha"] != SHAS[target]:
                raise ProtocolConflict("remote_target_changed")
            conn.execute(f"UPDATE {self.table('previews')} SET classroom_sha=?,body_json=?,result_json=?,updated_at=2 "
                         "WHERE id='preview' AND classroom_sha=? AND status=? AND updated_at=?",
                         (SHAS[target], PAYLOADS[target], '{"review":2}', baseline["classroom_sha"],
                          baseline["status"], baseline["updated_at"]))
            if force_rollback:
                raise ProtocolConflict("simulated_commit_failure")

    def test_preflight_releases_preview_before_remote_head_activation(self):
        with self.transaction() as conn:
            baseline = dict(self.preview(conn, lock=True))
            self.unpublished(conn)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(self.activate).result(timeout=8)
        self.finalize(baseline)
        with self.transaction() as conn:
            self.assertEqual(self.preview(conn)["classroom_sha"], SHAS["B"])

    def test_publisher_preview_lock_and_ordinary_head_read_do_not_deadlock(self):
        head_locked, preview_locked = Event(), Event()

        def writer():
            with self.assertRaisesRegex(ProtocolConflict, "published_immutable"):
                self.activate(after_head=head_locked.set, before_preview=lambda: self.wait(preview_locked))

        def publisher():
            self.wait(head_locked)
            with self.transaction() as conn:
                self.publish(conn, after_preview=preview_locked.set)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(writer), pool.submit(publisher)
            try:
                second.result(timeout=8)
                first.result(timeout=8)
            finally:
                preview_locked.set()
        self.assertEqual(self.fresh_source()["content_sha"], SHAS["A"])

    def test_head_committed_before_publish_rejects_old_sql_sha(self):
        committed = Event()

        def writer():
            self.activate()
            committed.set()

        def publisher():
            self.wait(committed)
            with self.assertRaisesRegex(ProtocolConflict, "remote_frozen_changed"):
                with self.transaction() as conn:
                    self.publish(conn)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(writer), pool.submit(publisher)
            first.result(timeout=8)
            second.result(timeout=8)
        with self.transaction() as conn:
            self.assertIsNone(conn.execute(f"SELECT * FROM {self.table('builds')}").fetchone())

    def test_fresh_resolver_does_not_reuse_publisher_repeatable_read_snapshot(self):
        snapshot_ready, committed = Event(), Event()

        def writer():
            self.wait(snapshot_ready)
            self.activate()
            committed.set()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(writer)
            try:
                with self.transaction() as conn:
                    self.assertEqual(self.head(conn)["content_sha"], SHAS["A"])
                    snapshot_ready.set()
                    self.wait(committed)
                    # This is the real RR failure if a future guard reuses conn.
                    self.assertEqual(self.head(conn)["content_sha"], SHAS["A"])
                    with self.assertRaisesRegex(ProtocolConflict, "remote_frozen_changed"):
                        self.publish(conn)
                future.result(timeout=8)
            finally:
                snapshot_ready.set()

    def test_final_transaction_rejects_sql_only_and_remote_only_concurrent_edits(self):
        with self.transaction() as conn:
            baseline = dict(self.preview(conn, lock=True))
        remote_committed, edit_committed = Event(), Event()

        def competing_edit():
            self.wait(remote_committed)
            with self.transaction() as conn:
                self.preview(conn, lock=True)
                conn.execute(f"UPDATE {self.table('previews')} SET result_json=?,updated_at=3 WHERE id='preview'",
                             ('{"review":"concurrent"}',))
            edit_committed.set()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(competing_edit)
            try:
                self.activate()
                remote_committed.set()
                self.wait(edit_committed)
                with self.assertRaisesRegex(ProtocolConflict, "sql_compare_changed"):
                    self.finalize(baseline)
                future.result(timeout=8)
            finally:
                remote_committed.set()
        with self.transaction() as conn:
            self.assertEqual(self.preview(conn)["result_json"], '{"review":"concurrent"}')
            second_baseline = dict(self.preview(conn))
        self.assertEqual(self.fresh_source()["content_sha"], SHAS["B"])
        # A Native-only save can advance the remote head without changing the
        # SQL preview at all. Full-row SQL comparison alone cannot detect it.
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(self.activate, "C", expected_sha=SHAS["B"],
                        expected_scope="scope-b").result(timeout=8)
        with self.assertRaisesRegex(ProtocolConflict, "remote_target_changed"):
            self.finalize(second_baseline)
        self.assertEqual(self.fresh_source()["content_sha"], SHAS["C"])
        with self.transaction() as conn:
            self.assertEqual(dict(self.preview(conn)), second_baseline)

    def test_lost_save_response_reconciles_exact_target_without_second_save(self):
        with self.transaction() as conn:
            baseline = dict(self.preview(conn, lock=True))
        save_calls = []
        self.activate()
        save_calls.append("immutable-intent-save-attempt")
        # A fresh invocation has its original immutable baseline and exact B
        # target; discovering B finishes SQL, without repeating the remote save.
        self.assertEqual(self.fresh_source()["content_sha"], SHAS["B"])
        self.finalize(baseline)
        self.assertEqual(len(save_calls), 1)
        with self.transaction() as conn:
            self.assertEqual(self.preview(conn)["classroom_sha"], SHAS["B"])

    def test_same_sha_new_scope_is_not_accepted_as_original_head(self):
        changed = Event()

        def alias_writer():
            with self.transaction() as conn:
                conn.execute(f"SELECT * FROM {self.table('heads')} WHERE id='source' FOR UPDATE").fetchone()
                conn.execute(f"UPDATE {self.table('heads')} SET scope_key='scope-alias' WHERE id='source'")
            changed.set()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(alias_writer)
            self.wait(changed)
            with self.assertRaisesRegex(ProtocolConflict, "head_conflict"):
                self.activate(expected_sha=SHAS["A"], expected_scope="scope-a")
            future.result(timeout=8)
        self.assertEqual(self.fresh_source()["content_sha"], SHAS["A"])

    def test_failed_sql_commit_keeps_remote_version_and_blocks_old_publication(self):
        with self.transaction() as conn:
            baseline = dict(self.preview(conn, lock=True))
        self.activate()
        with self.assertRaisesRegex(ProtocolConflict, "simulated_commit_failure"):
            self.finalize(baseline, force_rollback=True)
        self.assertEqual(self.fresh_source()["content_sha"], SHAS["B"])
        with self.transaction() as conn:
            self.assertEqual(self.preview(conn)["classroom_sha"], SHAS["A"])
            with self.assertRaisesRegex(ProtocolConflict, "remote_frozen_changed"):
                self.publish(conn)


@unittest.skipUnless(os.getenv("MIRA_MYSQL_LOCK_PROTOCOL") == "1",
                     "requires explicit isolated MySQL protocol opt-in")
class CourseStorageMySQLScopeScanProtocolTest(unittest.TestCase):
    """Detect the scope scan deadlock and retry its exact immutable guard."""

    def test_scope_scan_deadlock_retries_fresh_transaction_and_preserves_immutable_guard(self):
        database = Database(validated_test_database_url())
        name = "mira_scope_" + uuid.uuid4().hex
        if re.fullmatch(r"mira_scope_[a-f0-9]{32}", name) is None:
            raise ValueError("isolated_table_name_invalid")
        table, storage, created = "`" + name + "`", "f" * 64, False
        keys = ["1" * 64, "2" * 64]
        try:
            with database.transaction() as conn:
                if conn.execute("SELECT DATABASE() AS db").fetchone()["db"] != "ai_camera_app_test":
                    raise RuntimeError("isolated_test_database_required")
                created = True
                conn.execute(f"CREATE TABLE {table} (storage_id CHAR(64) NOT NULL, scope_key CHAR(64) NOT NULL, "
                             "scope_json LONGTEXT NOT NULL, bindings_json LONGTEXT NOT NULL, "
                             "PRIMARY KEY(storage_id,scope_key)) ENGINE=InnoDB "
                             "DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin")
                for key in keys:
                    conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)",
                                 (storage, key, '{"status":"preview_ready"}', '[]'))
            barrier = Barrier(2)
            bound = {"sourcePathSha256": "a" * 64, "sha256": "b" * 64}
            sql = (f"SELECT scope_key FROM {table} WHERE storage_id=? "
                   "AND JSON_UNQUOTE(JSON_EXTRACT(scope_json,'$.status'))='published' "
                   "AND JSON_CONTAINS(bindings_json,?) LIMIT 1 FOR UPDATE")
            params = (storage, json.dumps(bound, separators=(",", ":")))

            def writer(key, *, synchronize=True):
                # This is the upload boundary: transaction retries below must
                # retain the same uploaded object and never execute it again.
                uploads, deadlocks = 1, 0
                for attempt in range(1, 4):
                    try:
                        with database.transaction() as conn:
                            conn.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                            conn.execute("SET SESSION innodb_lock_wait_timeout=2")
                            # compare_and_activate owns this path's scope before
                            # its before_activate lifecycle/policy callback.
                            conn.execute(f"SELECT * FROM {table} WHERE storage_id=? AND scope_key=? FOR UPDATE",
                                         (storage, key)).fetchone()
                            if synchronize and attempt == 1:
                                barrier.wait(timeout=5)
                            parent = conn.execute(sql, params).fetchone()
                            if parent is not None:
                                raise ProtocolConflict("published_immutable")
                        return {"attempts": attempt, "deadlocks": deadlocks, "uploads": uploads}
                    except Exception as exc:
                        if not (exc.args and exc.args[0] == 1213):
                            raise
                        deadlocks += 1
                        if attempt == 3:
                            raise

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(writer, key) for key in keys]
                results = [future.result(timeout=8) for future in futures]
            self.assertGreaterEqual(sum(result["deadlocks"] for result in results), 1)
            self.assertTrue(all(1 <= result["attempts"] <= 3 for result in results))
            self.assertEqual([result["uploads"] for result in results], [1, 1])
            # Keep the exact predicate on every retry: a matching immutable
            # publication must still be refused, never bypassed to escape locks.
            with database.transaction() as conn:
                conn.execute(f"INSERT INTO {table} VALUES (?,?,?,?)",
                             (storage, "3" * 64, '{"status":"published"}', json.dumps([bound])))
            with self.assertRaisesRegex(ProtocolConflict, "published_immutable"):
                writer(keys[0], synchronize=False)
        finally:
            if created:
                with database.transaction() as conn:
                    conn.execute(f"DROP TABLE IF EXISTS {table}")
                with database.transaction() as conn:
                    remaining = conn.execute("SELECT COUNT(*) AS n FROM information_schema.tables "
                                             "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=?", (name,)).fetchone()["n"]
                self.assertEqual(remaining, 0)


if __name__ == "__main__":
    unittest.main()
