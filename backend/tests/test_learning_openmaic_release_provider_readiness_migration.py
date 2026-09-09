from __future__ import annotations

import re
import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "065_learning_openmaic_release_provider_readiness.sql"
)


class LearningOpenMaicReleaseProviderReadinessMigrationTest(unittest.TestCase):
    def test_release_canary_identity_is_unique(self) -> None:
        sql = re.sub(r"\s+", " ", MIGRATION.read_text(encoding="utf-8")).lower()

        self.assertIn("add unique index", sql)
        self.assertIn("release_id, grade_code, target_fingerprint", sql)


if __name__ == "__main__":
    unittest.main()
