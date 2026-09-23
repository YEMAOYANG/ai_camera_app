import unittest

from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION,
    SUPPORTED_PRIMARY_SUBJECTS,
    boundaries_for,
)
from services.learning_difficulty import available_skill_order
from services.learning_progression import course_progression, eligible_skill_order


class LearningProgressionTest(unittest.TestCase):
    def test_every_grade_and_subject_only_unlocks_the_next_skill_and_prior_review(self):
        for grade in range(1, 7):
            for subject in SUPPORTED_PRIMARY_SUBJECTS:
                grade_code = f"primary_{grade}"
                boundaries = boundaries_for(grade_code, subject)
                self.assertTrue(boundaries)
                for current in range(len(boundaries) + 1):
                    mastery = {boundary.skill_id: {"mastery_level": "mastered"}
                               for boundary in boundaries[:current]}
                    with self.subTest(grade=grade, subject=subject, current=current):
                        for index, boundary in enumerate(boundaries):
                            result = course_progression(grade_code=grade_code, subject=subject,
                                                        skill_id=boundary.skill_id, mastery=mastery)
                            status = "mastered" if index < current else "available" if index == current else "locked"
                            self.assertEqual(result["schemaVersion"], "mira.learning.progression.v1")
                            self.assertEqual(result["curriculumVersion"], PRIMARY_CURRICULUM_VERSION)
                            self.assertEqual(result["granularity"], "skill_boundary")
                            self.assertEqual(result["sequence"], index + 1)
                            self.assertEqual(result["learningStatus"], status)
                            self.assertEqual(result["canStart"], index <= current)
                            expected_blockers = [item.skill_id for item in boundaries[current:index]] if index > current else []
                            self.assertEqual(result["blockedBySkillIds"], expected_blockers)
                        expected = ([boundaries[current].skill_id] if current < len(boundaries) else [])
                        expected += [boundary.skill_id for boundary in reversed(boundaries[:current])]
                        self.assertEqual(eligible_skill_order(boundaries, mastery), expected)
                        self.assertEqual(available_skill_order(boundaries, mastery), expected)

    def test_later_mastery_records_cannot_bypass_an_earlier_gap(self):
        boundaries = boundaries_for("primary_1", "chinese")
        mastery = {boundary.skill_id: {"mastery_level": "mastered"}
                   for boundary in boundaries[1:]}
        self.assertEqual(eligible_skill_order(boundaries, mastery), [boundaries[0].skill_id])
        for boundary in boundaries[1:]:
            result = course_progression(grade_code="primary_1", subject="chinese",
                                        skill_id=boundary.skill_id, mastery=mastery)
            self.assertFalse(result["canStart"])
            self.assertEqual(result["learningStatus"], "locked")
            self.assertIn(boundaries[0].skill_id, result["blockedBySkillIds"])

    def test_missing_and_malformed_mastery_records_never_unlock_the_next_skill(self):
        first, second, *_ = boundaries_for("primary_1", "math")
        for mastery in (None, {}, {first.skill_id: None}, {first.skill_id: {}},
                        {first.skill_id: "mastered"}, {first.skill_id: {"mastery_level": "unknown"}},
                        {first.skill_id: {"mastery_level": ["mastered"]}}):
            with self.subTest(mastery=mastery):
                first_state = course_progression(grade_code="primary_1", subject="math",
                                                 skill_id=first.skill_id, mastery=mastery)
                self.assertEqual(first_state["learningStatus"], "available")
                second_state = course_progression(grade_code="primary_1", subject="math",
                                                  skill_id=second.skill_id, mastery=mastery)
                self.assertFalse(second_state["canStart"])

    def test_practice_required_on_current_skill_and_prior_review_remains_available(self):
        first, second, third, *_ = boundaries_for("primary_1", "chinese")
        for level in ("developing", "needs_practice"):
            mastery = {first.skill_id: {"mastery_level": "mastered"},
                       second.skill_id: {"mastery_level": level}}
            current = course_progression(grade_code="primary_1", subject="chinese",
                                         skill_id=second.skill_id, mastery=mastery)
            self.assertEqual(current["learningStatus"], "needs_practice")
            self.assertTrue(current["canStart"])
            self.assertEqual(eligible_skill_order((first, second, third), mastery),
                             [second.skill_id, first.skill_id])

    def test_subject_and_grade_scope_and_unknown_skills_fail_closed(self):
        for grade, subject, skill in (("primary_1", "english", "number_sense_20"),
                                      ("primary_6", "math", "number_sense_20"),
                                      ("primary_1", "science", "number_sense_20"),
                                      ("primary_7", "math", "number_sense_20"),
                                      ("primary_1", "math", "unregistered")):
            result = course_progression(grade_code=grade, subject=subject, skill_id=skill,
                                        mastery={skill: {"mastery_level": "mastered"}})
            self.assertEqual(result["sequence"], 0)
            self.assertEqual(result["learningStatus"], "locked")
            self.assertFalse(result["canStart"])
            self.assertTrue(result["message"])


if __name__ == "__main__":
    unittest.main()
