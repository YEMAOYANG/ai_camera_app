import unittest
from content.primary_skill_boundaries import boundaries_for
from services.learning_availability_state import personal_learning_state


class PersonalLearningAvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.courses = [{"id": subject, "version": "1", "subject": subject,
                         "node_code": boundaries_for("primary_1", subject)[0].skill_id}
                        for subject in ("chinese", "math", "english")]
        self.supply = {"scopeReady": True, "scopeSkills": [{"subject": row["subject"], "skillId": row["node_code"]}
                                                          for row in self.courses]}

    def state(self, courses=None, mastery=None, **supply):
        return personal_learning_state(grade_code="primary_1", courses=self.courses if courses is None else courses,
            mastery=mastery or {}, supply={**self.supply, **supply})

    def test_ready_courses_are_personal_and_future_prerequisites_are_not_available(self):
        future = {"id": "later", "version": "1", "subject": "math",
                  "node_code": boundaries_for("primary_1", "math")[1].skill_id}
        state = self.state(courses=[*self.courses, future])
        self.assertEqual(state["availableCourseCount"], 3)
        self.assertEqual(state["publishedCourseCount"], 4)
        self.assertEqual(state["availabilityStatus"], "ready")

    def test_scope_completion_does_not_claim_unopened_next_unit_is_generating(self):
        state = self.state(mastery={f"{row['subject']}:{row['node_code']}": "mastered" for row in self.courses})
        self.assertEqual(state["availabilityStatus"], "scope_completed")
        self.assertEqual(state["reviewCourseCount"], 3)
        self.assertEqual(state["newCourseCount"], 0)

    def test_struggling_child_gets_reinforcement_not_false_scope_completion(self):
        state = self.state(mastery={f"{row['subject']}:{row['node_code']}": "developing" for row in self.courses})
        self.assertEqual(state["availabilityStatus"], "ready")
        self.assertEqual(state["reviewCourseCount"], 3)
        self.assertEqual(state["newCourseCount"], 0)

    def test_withdrawn_assets_do_not_erase_completed_scope_or_claim_a_new_job(self):
        mastery = {f"{row['subject']}:{row['node_code']}": "mastered" for row in self.courses}
        self.assertEqual(self.state(courses=[], mastery=mastery, scopeReady=False)["availabilityStatus"], "scope_completed")
        self.assertEqual(self.state(courses=[], paused=True)["availabilityStatus"], "paused")
        self.assertEqual(personal_learning_state(grade_code="primary_2", courses=[], mastery={}, supply=None,
                                                grade_open=False)["availabilityStatus"], "not_open")

    def test_other_student_mastery_is_not_implicitly_used(self):
        self.assertEqual(self.state()["newCourseCount"], 3)
        self.assertEqual(self.state(courses=[])["availableCourseCount"], 0)

    def test_mastered_future_course_after_a_gap_is_not_available_or_completed(self):
        second = boundaries_for("primary_1", "math")[1].skill_id
        future = {"id": "future", "version": "1", "subject": "math", "node_code": second}
        state = self.state(courses=[future], mastery={f"math:{second}": "mastered"},
                           scopeSkills=[{"subject": "math", "skillId": second}])
        self.assertEqual(state["publishedCourseCount"], 1)
        self.assertEqual(state["availableCourseCount"], 0)
        self.assertEqual(state["reviewCourseCount"], 0)
        self.assertEqual(state["availabilityStatus"], "preparing")

    def test_no_current_asset_offers_only_prior_review_and_preserves_supply_state(self):
        first, second, third = boundaries_for("primary_1", "math")
        courses = [{"id": boundary.skill_id, "version": "1", "subject": "math", "node_code": boundary.skill_id}
                   for boundary in (first, third)]
        mastery = {f"math:{first.skill_id}": "mastered", f"math:{third.skill_id}": "mastered"}
        state = self.state(courses=courses, mastery=mastery, paused=True,
                           scopeSkills=[{"subject": "math", "skillId": boundary.skill_id}
                                        for boundary in (first, second, third)])
        self.assertEqual(state["availableCourseCount"], 1)
        self.assertEqual(state["reviewCourseCount"], 1)
        self.assertEqual(state["newCourseCount"], 0)
        self.assertEqual(state["availabilityStatus"], "paused")

    def test_same_named_skill_in_another_subject_does_not_unlock(self):
        english = boundaries_for("primary_3", "english")
        last = english[-1]
        state = personal_learning_state(grade_code="primary_3",
            courses=[{"id": "english-reading", "version": "1", "subject": "english", "node_code": last.skill_id}],
            mastery={f"chinese:{boundary.skill_id}": "mastered" for boundary in english}, supply=None)
        self.assertEqual(state["availableCourseCount"], 0)

    def test_unknown_skill_is_published_but_never_available(self):
        row = {"id": "unknown", "version": "1", "subject": "math", "node_code": "unknown"}
        state = self.state(courses=[row], mastery={"math:unknown": "mastered"},
                           scopeSkills=[{"subject": "math", "skillId": "unknown"}])
        self.assertEqual(state["publishedCourseCount"], 1)
        self.assertEqual(state["availableCourseCount"], 0)
        self.assertEqual(state["availabilityStatus"], "preparing")


if __name__ == "__main__":
    unittest.main()
