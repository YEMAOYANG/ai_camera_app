from __future__ import annotations

import unittest
from unittest.mock import patch

from tests import support


class TestDatabaseSafetyTest(unittest.TestCase):
    def test_fresh_config_rejects_development_database_override_before_reset(self):
        unsafe = "postgresql://mira:secret@127.0.0.1:5433/mira"
        with patch.object(
            support, "reset_test_database"
        ) as reset_database, patch.object(support, "Database") as database:
            with self.assertRaisesRegex(RuntimeError, "mira_test"):
                support.fresh_test_config(DATABASE_URL=unsafe)
        reset_database.assert_not_called()
        database.assert_not_called()

    def test_fresh_config_rejects_remote_database_override_before_reset(self):
        unsafe = "postgresql://mira:secret@db.example.com:5433/mira_test"
        with patch.object(
            support, "reset_test_database"
        ) as reset_database, patch.object(support, "Database") as database:
            with self.assertRaisesRegex(RuntimeError, "local"):
                support.fresh_test_config(DATABASE_URL=unsafe)
        reset_database.assert_not_called()
        database.assert_not_called()

    def test_rejects_development_database_before_connecting(self):
        unsafe = "postgresql://mira:secret@127.0.0.1:5433/mira"
        with patch.dict("os.environ", {"APP_TEST_DATABASE_URL": unsafe}), patch.object(
            support, "Database"
        ) as database:
            with self.assertRaisesRegex(RuntimeError, "mira_test"):
                support.reset_test_database()
        database.assert_not_called()

    def test_rejects_nonlocal_test_database_before_connecting(self):
        unsafe = "postgresql://mira:secret@db.example.com:5433/mira_test"
        with patch.dict("os.environ", {"APP_TEST_DATABASE_URL": unsafe}), patch.object(
            support, "Database"
        ) as database:
            with self.assertRaisesRegex(RuntimeError, "local"):
                support.reset_test_database()
        database.assert_not_called()

    def test_rejects_a_legacy_mysql_test_database_before_connecting(self):
        unsafe = "mysql+pymysql://ai_camera_app:secret@127.0.0.1:3306/mira_test"
        with patch.dict("os.environ", {"APP_TEST_DATABASE_URL": unsafe}), patch.object(
            support, "Database"
        ) as database:
            with self.assertRaisesRegex(RuntimeError, "postgresql://"):
                support.reset_test_database()
        database.assert_not_called()

    def test_accepts_a_suffixed_parallel_test_database(self):
        url = "postgresql://mira:secret@127.0.0.1:5433/mira_test_adhoc"
        self.assertEqual(support.validated_test_database_url(url), url)
        with self.assertRaisesRegex(RuntimeError, "mira_test"):
            support.validated_test_database_url("postgresql://mira:secret@127.0.0.1:5433/mira_testing")


if __name__ == "__main__":
    unittest.main()
