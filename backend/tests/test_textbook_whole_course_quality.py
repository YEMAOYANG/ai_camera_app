"""Whole-course intrinsic quality receipts are exact and course-bound."""
from copy import deepcopy
import unittest

from content.textbook_catalog import digest
from content.textbook_whole_course_quality import (
    DIMENSIONS, SCHEMA, validate_whole_course_quality_review,
)


class WholeCourseQualityReviewTest(unittest.TestCase):
    def setUp(self):
        self.policy_sha = digest({"policy": "v2"})
        self.classroom = {"id": "quality-course", "scenes": [
            {"id": "opening", "type": "slide"},
            {"id": "build", "type": "interactive"},
            {"id": "transfer", "type": "interactive"},
            {"id": "check", "type": "quiz"},
        ]}
        self.source_sha = digest(self.classroom)
        self.review = self._review()

    def _activity(self, scene_id):
        return {
            "sceneId": scene_id,
            "childTask": "Help the same characters change the learning world and inspect the result.",
            "states": {name: {
                "description": f"The reviewer played and preserved the {name} state for {scene_id}.",
                "evidenceSha256": digest({"scene": scene_id, "state": name}),
            } for name in ("before", "action", "after", "revise")},
            "visibleWorldChange": "The child's decision changes the pictured objects and their relationship in place.",
            "failureOrAlternative": [{
                "kind": "failure", "trigger": "The child creates a specific broken relationship.",
                "visibleOutcome": "The affected object and break point remain visible in the scene.",
                "teacherFeedback": "The teacher names that object and the observed break point.",
                "revisionStep": "The child changes the object and compares the repaired result.",
            }],
            "targetShortcutCheck": {
                "shortcut": "Repeat fixed positions without using the lesson target.",
                "outcome": "blocked",
                "evidence": "Positions and surface pictures were changed while the target relation stayed authoritative.",
            },
            "crossPageCarry": "The same characters and changed objects continue into the next course task.",
            "newContextTransfer": "The target is checked with a new arrangement and no repeated answer position.",
        }

    def _review(self):
        return {
            "schemaVersion": SCHEMA,
            "status": "passed",
            "policySha256": self.policy_sha,
            "sourceSha256": self.source_sha,
            "dimensions": {name: {"status": "passed", "evidence": [f"Observed evidence for {name}."]}
                           for name in DIMENSIONS},
            "coreActivities": [self._activity("build"), self._activity("transfer")],
            "hardFailures": [],
        }

    def validate(self, review=None, *, classroom=None, policy_sha=None, source_sha=None):
        return validate_whole_course_quality_review(
            self.review if review is None else review,
            classroom=self.classroom if classroom is None else classroom,
            policy_sha256=self.policy_sha if policy_sha is None else policy_sha,
            source_sha256=self.source_sha if source_sha is None else source_sha,
        )

    def test_complete_review_is_bound_and_digestable(self):
        result = self.validate()
        self.assertEqual(result["sha256"], digest(self.review))
        self.assertEqual(result["activityCount"], 2)

    def test_missing_or_failed_dimension_and_hard_failure_are_rejected(self):
        examples = []
        missing = deepcopy(self.review); missing["dimensions"].pop(DIMENSIONS[0]); examples.append(missing)
        failed = deepcopy(self.review); failed["dimensions"][DIMENSIONS[1]]["status"] = "failed"; examples.append(failed)
        hard = deepcopy(self.review); hard["hardFailures"] = ["The world never changes."]; examples.append(hard)
        for review in examples:
            with self.subTest(review=review), self.assertRaises(ValueError):
                self.validate(review)

    def test_every_interactive_scene_must_have_exactly_one_review(self):
        missing = deepcopy(self.review); missing["coreActivities"].pop()
        duplicate = deepcopy(self.review); duplicate["coreActivities"][1]["sceneId"] = "build"
        extra = deepcopy(self.review); extra["coreActivities"].append(self._activity("not-a-source-scene"))
        reordered = deepcopy(self.review); reordered["coreActivities"].reverse()
        no_interaction = {"id": "slides-only", "scenes": [{"id": "one", "type": "slide"}]}
        for review in (missing, duplicate, extra, reordered):
            with self.subTest(review=review), self.assertRaises(ValueError):
                self.validate(review)
        with self.assertRaises(ValueError):
            self.validate(classroom=no_interaction, source_sha=digest(no_interaction))

    def test_state_failure_and_shortcut_evidence_cannot_be_omitted(self):
        no_state = deepcopy(self.review); no_state["coreActivities"][0]["states"].pop("revise")
        no_path = deepcopy(self.review); no_path["coreActivities"][0]["failureOrAlternative"] = []
        bypass = deepcopy(self.review); bypass["coreActivities"][0]["targetShortcutCheck"]["outcome"] = "possible"
        for review in (no_state, no_path, bypass):
            with self.subTest(review=review), self.assertRaises(ValueError):
                self.validate(review)

    def test_changed_policy_source_or_unhashed_state_is_rejected(self):
        bad_state = deepcopy(self.review)
        bad_state["coreActivities"][0]["states"]["after"]["evidenceSha256"] = "not-a-sha"
        changed = deepcopy(self.classroom); changed["scenes"][1]["id"] = "changed"
        with self.assertRaises(ValueError):
            self.validate(bad_state)
        with self.assertRaises(ValueError):
            self.validate(policy_sha=digest({"policy": "other"}))
        with self.assertRaises(ValueError):
            self.validate(classroom=changed)


if __name__ == "__main__":
    unittest.main()
