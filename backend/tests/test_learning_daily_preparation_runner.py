from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from services.learning_daily_preparation_runner import LearningDailyPreparationRunner


class LearningDailyPreparationRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = LearningDailyPreparationRunner()
        self.zone = ZoneInfo("Asia/Shanghai")
        self.calls: list[str] = []

    def _prepare(self, learning_date: str) -> dict:
        self.calls.append(learning_date)
        return {"ok": True, "date": learning_date, "createdCount": 3}

    def test_runs_after_five_and_rechecks_same_day_for_new_children(self) -> None:
        before = self.runner.run_due_once(
            now=datetime(2026, 8, 12, 4, 59, tzinfo=self.zone),
            hour=5,
            minute=0,
            prepare=self._prepare,
        )
        first = self.runner.run_due_once(
            now=datetime(2026, 8, 12, 10, 30, tzinfo=self.zone),
            hour=5,
            minute=0,
            prepare=self._prepare,
        )
        replay = self.runner.run_due_once(
            now=datetime(2026, 8, 12, 18, 0, tzinfo=self.zone),
            hour=5,
            minute=0,
            prepare=self._prepare,
        )

        self.assertIsNone(before)
        self.assertEqual(first["createdCount"], 3)
        self.assertEqual(replay["createdCount"], 3)
        self.assertEqual(self.calls, ["2026-08-12", "2026-08-12"])
        self.assertEqual(self.runner.status()["lastPreparedDate"], "2026-08-12")

    def test_next_local_date_runs_again(self) -> None:
        for day in (12, 13):
            self.runner.run_due_once(
                now=datetime(2026, 8, day, 5, 0, tzinfo=self.zone),
                hour=5,
                minute=0,
                prepare=self._prepare,
            )
        self.assertEqual(self.calls, ["2026-08-12", "2026-08-13"])

    def test_failure_is_not_marked_prepared_and_can_retry(self) -> None:
        attempts = 0

        def flaky(learning_date: str) -> dict:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("database unavailable")
            return self._prepare(learning_date)

        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            self.runner.run_due_once(
                now=datetime(2026, 8, 12, 5, 0, tzinfo=self.zone),
                hour=5,
                minute=0,
                prepare=flaky,
            )
        result = self.runner.run_due_once(
            now=datetime(2026, 8, 12, 5, 1, tzinfo=self.zone),
            hour=5,
            minute=0,
            prepare=flaky,
        )

        self.assertEqual(result["date"], "2026-08-12")
        self.assertEqual(attempts, 2)
        self.assertEqual(self.runner.status()["lastError"], "")

    def test_partial_child_failure_is_retried_instead_of_marked_prepared(self) -> None:
        attempts = 0

        def partial_then_success(learning_date: str) -> dict:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return {
                    "ok": False,
                    "date": learning_date,
                    "createdCount": 1,
                    "failures": [{"childId": "child_2", "code": "temporary"}],
                }
            return {"ok": True, "date": learning_date, "createdCount": 1}

        partial = self.runner.run_due_once(
            now=datetime(2026, 8, 12, 5, 0, tzinfo=self.zone),
            hour=5,
            minute=0,
            prepare=partial_then_success,
        )
        retried = self.runner.run_due_once(
            now=datetime(2026, 8, 12, 5, 1, tzinfo=self.zone),
            hour=5,
            minute=0,
            prepare=partial_then_success,
        )

        self.assertFalse(partial["ok"])
        self.assertTrue(retried["ok"])
        self.assertEqual(attempts, 2)
        self.assertEqual(self.runner.status()["lastPreparedDate"], "2026-08-12")
        self.assertEqual(self.runner.status()["lastError"], "")


if __name__ == "__main__":
    unittest.main()
