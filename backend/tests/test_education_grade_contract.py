from __future__ import annotations

import unittest

from core.errors import ApiError
from schemas.education import (
    GRADE_DEFINITIONS,
    KINDERGARTEN_GROWTH,
    PRIMARY_LEARNING,
    child_education_payload,
    resolve_grade_definition,
)


class EducationGradeContractTest(unittest.TestCase):
    def test_catalog_contains_exactly_the_supported_nine_grades(self):
        self.assertEqual(
            [item.code for item in GRADE_DEFINITIONS],
            [
                "kindergarten_small",
                "kindergarten_middle",
                "kindergarten_big",
                "primary_1",
                "primary_2",
                "primary_3",
                "primary_4",
                "primary_5",
                "primary_6",
            ],
        )
        self.assertEqual(
            {item.content_mode for item in GRADE_DEFINITIONS[:3]},
            {KINDERGARTEN_GROWTH},
        )
        self.assertEqual(
            {item.content_mode for item in GRADE_DEFINITIONS[3:]},
            {PRIMARY_LEARNING},
        )
        self.assertTrue(
            all(item.kindergarten_template_grade is None for item in GRADE_DEFINITIONS[3:])
        )

    def test_legacy_aliases_resolve_but_conflicting_stage_is_rejected(self):
        legacy = resolve_grade_definition(
            legacy_grade="新三年级",
            education_stage="小学",
        )
        self.assertIsNotNone(legacy)
        self.assertEqual(legacy.code, "primary_3")

        with self.assertRaises(ApiError) as context:
            resolve_grade_definition(
                grade_code="primary_3",
                education_stage="幼儿园",
            )
        self.assertEqual(context.exception.code, "grade_stage_conflict")

    def test_backfilled_grade_without_confirmation_requires_selection(self):
        payload = child_education_payload(
            {
                "grade_code": "primary_2",
                "grade": "二年级",
                "education_stage": "小学",
                "age_stage": "小学 二年级",
                "grade_school_year_start": None,
                "grade_confirmed_at": None,
            }
        )

        self.assertEqual(payload["gradeCode"], "primary_2")
        self.assertEqual(payload["contentMode"], "primary_learning")
        self.assertTrue(payload["gradeSelectionRequired"])


if __name__ == "__main__":
    unittest.main()
