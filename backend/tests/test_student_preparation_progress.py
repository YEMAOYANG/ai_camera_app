import unittest
from unittest.mock import Mock

from repositories.learning_repository import LearningRepository


class StudentPreparationProgressTest(unittest.TestCase):
    def test_progress_uses_current_child_plan_and_never_finishes_early(self):
        for plan, expected in [
            ({"status": "running", "stage": "generating_content", "progress_percent": 10}, 10),
            ({"status": "running", "stage": "publishing", "progress_percent": 100}, 99),
            ({"status": "failed", "stage": "generating_content", "progress_percent": 42}, 42),
            ({"status": "ready", "stage": "completed", "progress_percent": 100}, 100),
            (None, None),
        ]:
            with self.subTest(plan=plan):
                conn = Mock()
                conn.execute.return_value.fetchone.side_effect = [plan, {"value": 0}]
                result = LearningRepository.student_catalog_summary(
                    object.__new__(LearningRepository), conn,
                    family_id="family-1", child_id="child-1", grade_code="primary_1",
                    grade_selection_revision=3,
                )
                self.assertEqual(result["preparationProgressPercent"], expected)
                query, params = conn.execute.call_args_list[0].args
                self.assertIn("superseded_at IS NULL", query)
                self.assertEqual(params, ("family-1", "child-1", "primary_1", 3))
