from __future__ import annotations

import unittest
from unittest.mock import patch

from tests import support


class TestDatabaseSafetyTest(unittest.TestCase):
    def test_fresh_config_rejects_development_database_override_before_reset(self):
        unsafe = (
            "mysql+pymysql://ai_camera_app:secret@127.0.0.1:3306/"
            "ai_camera_app_dev?charset=utf8mb4"
        )
        with patch.object(
            support, "reset_mysql_test_database"
        ) as reset_database, patch.object(support, "Database") as database:
            with self.assertRaisesRegex(RuntimeError, "ai_camera_app_test"):
                support.fresh_test_config(DATABASE_URL=unsafe)
        reset_database.assert_not_called()
        database.assert_not_called()

    def test_fresh_config_rejects_remote_database_override_before_reset(self):
        unsafe = (
            "mysql+pymysql://ai_camera_app:secret@db.example.com:3306/"
            "ai_camera_app_test?charset=utf8mb4"
        )
        with patch.object(
            support, "reset_mysql_test_database"
        ) as reset_database, patch.object(support, "Database") as database:
            with self.assertRaisesRegex(RuntimeError, "local"):
                support.fresh_test_config(DATABASE_URL=unsafe)
        reset_database.assert_not_called()
        database.assert_not_called()

    def test_rejects_development_database_before_connecting(self):
        unsafe = (
            "mysql+pymysql://ai_camera_app:secret@127.0.0.1:3306/"
            "ai_camera_app_dev?charset=utf8mb4"
        )
        with patch.dict("os.environ", {"APP_TEST_DATABASE_URL": unsafe}), patch.object(
            support, "Database"
        ) as database:
            with self.assertRaisesRegex(RuntimeError, "ai_camera_app_test"):
                support.reset_mysql_test_database()
        database.assert_not_called()

    def test_rejects_nonlocal_test_database_before_connecting(self):
        unsafe = (
            "mysql+pymysql://ai_camera_app:secret@db.example.com:3306/"
            "ai_camera_app_test?charset=utf8mb4"
        )
        with patch.dict("os.environ", {"APP_TEST_DATABASE_URL": unsafe}), patch.object(
            support, "Database"
        ) as database:
            with self.assertRaisesRegex(RuntimeError, "local"):
                support.reset_mysql_test_database()
        database.assert_not_called()


if __name__ == "__main__":
    unittest.main()
