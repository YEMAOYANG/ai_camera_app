from __future__ import annotations

import unittest

from repositories.learning_repository import LearningRepository
from repositories.student_access_repository import StudentAccessRepository


class _Result:
    def __init__(self, *, rows=None, row=None, rowcount: int = 0):
        self._rows = list(rows or [])
        self._row = row
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self):
        self.calls: list[tuple[str, tuple | list | None]] = []

    def execute(self, sql: str, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if normalized.startswith("SELECT report.*") and "ORDER BY" in normalized:
            return _Result(
                rows=[
                    {"id": "report_3", "created_at": 300},
                    {"id": "report_2", "created_at": 200},
                    {"id": "report_1", "created_at": 100},
                ]
            )
        if normalized.startswith("SELECT report.*"):
            return _Result(row={"id": "report_1", "created_at": 100})
        if normalized.startswith("SELECT") and "student_trusted_devices" in normalized:
            return _Result(rows=[], row={"id": "device_1"})
        if normalized.startswith("UPDATE") and "SET status = 'revoked'" in normalized:
            return _Result(rowcount=1)
        if normalized.startswith("UPDATE"):
            return _Result(rowcount=2)
        return _Result()


class ParentStudentLinkageRepositoryContractTest(unittest.TestCase):
    def test_authorization_listing_query_is_owned_and_secret_free(self):
        repository = StudentAccessRepository(None)
        self.assertTrue(
            hasattr(repository, "list_owned_authorizations"),
            "owned authorization query is not implemented",
        )
        conn = _Connection()

        repository.list_owned_authorizations(
            conn,
            family_id="family_1",
            child_id="child_1",
        )

        sql, params = conn.calls[-1]
        self.assertIn("device.family_id = ?", sql)
        self.assertIn("device.child_id = ?", sql)
        self.assertIn("device.revoked_at IS NULL", sql)
        self.assertIn("session.revoked_at IS NULL", sql)
        self.assertEqual(params, ("family_1", "child_1"))
        for forbidden_column in (
            "device_token_hash",
            "access_hash",
            "refresh_hash",
            "pin_hash",
        ):
            self.assertNotIn(forbidden_column, sql)

    def test_authorization_revocation_lookup_locks_exact_family_child_device(self):
        repository = StudentAccessRepository(None)
        self.assertTrue(
            hasattr(repository, "get_owned_device_for_update"),
            "owned authorization locking lookup is not implemented",
        )
        self.assertTrue(
            hasattr(repository, "revoke_trusted_device"),
            "trusted device revocation is not implemented",
        )
        conn = _Connection()

        repository.get_owned_device_for_update(
            conn,
            family_id="family_1",
            child_id="child_1",
            device_id="device_1",
        )
        lookup_sql, lookup_params = conn.calls[-1]
        self.assertIn("id = ? AND family_id = ? AND child_id = ?", lookup_sql)
        self.assertIn("FOR UPDATE", lookup_sql)
        self.assertEqual(lookup_params, ("device_1", "family_1", "child_1"))

        changed = repository.revoke_trusted_device(
            conn,
            device_id="device_1",
            revoked_at=123,
        )
        revoke_sql, revoke_params = conn.calls[-1]
        self.assertTrue(changed)
        self.assertIn("revoked_at IS NULL", revoke_sql)
        self.assertEqual(revoke_params, (123, 123, "device_1"))

    def test_pin_reset_repository_mutations_return_affected_counts(self):
        repository = StudentAccessRepository(None)
        self.assertTrue(
            hasattr(repository, "revoke_principal_sessions"),
            "principal session revocation is not implemented",
        )
        self.assertTrue(
            hasattr(repository, "reset_principal_device_pin_failures"),
            "device PIN failure reset is not implemented",
        )
        conn = _Connection()

        self.assertEqual(
            repository.revoke_device_sessions(
                conn,
                device_id="device_1",
                revoked_at=123,
            ),
            2,
        )
        self.assertEqual(
            repository.revoke_principal_sessions(
                conn,
                principal_id="principal_1",
                revoked_at=123,
            ),
            2,
        )
        self.assertEqual(
            repository.reset_principal_device_pin_failures(
                conn,
                principal_id="principal_1",
                now=123,
            ),
            2,
        )

    def test_report_queries_bind_family_child_and_authoritative_session(self):
        repository = LearningRepository(None)
        self.assertTrue(
            hasattr(repository, "list_reports"),
            "parent report page query is not implemented",
        )
        self.assertTrue(
            hasattr(repository, "get_report_detail"),
            "parent report detail query is not implemented",
        )
        conn = _Connection()

        page, next_cursor = repository.list_reports(
            conn,
            family_id="family_1",
            child_id="child_1",
            subject="math",
            cursor=None,
            limit=2,
        )
        list_sql, list_params = conn.calls[-1]
        self.assertEqual([row["id"] for row in page], ["report_3", "report_2"])
        self.assertIsNotNone(next_cursor)
        self.assertIn("session.id = report.session_id", list_sql)
        self.assertIn("session.family_id = report.family_id", list_sql)
        self.assertIn("session.child_id = report.child_id", list_sql)
        self.assertIn("report.family_id = ?", list_sql)
        self.assertIn("report.child_id = ?", list_sql)
        self.assertEqual(list_params, ["family_1", "child_1", "math", 3])

        repository.get_report_detail(
            conn,
            family_id="family_1",
            child_id="child_1",
            report_id="report_1",
        )
        detail_sql, detail_params = conn.calls[-1]
        self.assertIn("report.id = ? AND report.family_id = ?", detail_sql)
        self.assertIn("report.child_id = ?", detail_sql)
        self.assertEqual(detail_params, ("report_1", "family_1", "child_1"))


if __name__ == "__main__":
    unittest.main()
