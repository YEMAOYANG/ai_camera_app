from copy import deepcopy
import os
import unittest
from unittest.mock import patch

from integrations.openmaic_formal_media import (
    MULTISTATE_PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY,
    REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY,
    compatible_preparation_target, professional_policy, policy_from_target,
)
from integrations.openmaic_formal_playful import validate_playful_classroom
from services.learning_curriculum_preparation_contract import (
    build_preparation_target, preparation_target_fingerprint,
)


class PlayfulCourseContractTest(unittest.TestCase):
    def test_required_3d_is_runtime_opt_in_with_a_distinct_frozen_target(self):
        with patch.dict(os.environ, {"MIRA_FORMAL_PLAYFUL_REQUIRE_3D": ""}):
            original = build_preparation_target("primary_6")
        with patch.dict(os.environ, {"MIRA_FORMAL_PLAYFUL_REQUIRE_3D": "1"}):
            selected = build_preparation_target("primary_6")
        with patch.dict(os.environ, {"MIRA_FORMAL_PLAYFUL_REQUIRE_3D": ""}):
            self.assertEqual(build_preparation_target("primary_6"), original)
        self.assertEqual(policy_from_target(original), PLAYFUL_PROFESSIONAL_POLICY)
        self.assertEqual(policy_from_target(selected), REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY)
        self.assertNotEqual(preparation_target_fingerprint(original), preparation_target_fingerprint(selected))
        self.assertTrue(compatible_preparation_target(original, selected))
        self.assertTrue(compatible_preparation_target(selected, original))
        without_policy = deepcopy(selected)
        without_policy["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(PLAYFUL_PROFESSIONAL_POLICY)
        self.assertEqual(without_policy, original)

    def test_required_3d_needs_a_separate_interactive_3d_page_and_game(self):
        generation = {"professionalCreationPolicy": REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY}
        game = {"type": "interactive", "content": {"widgetType": "game", "contains3d": True}}
        with self.assertRaisesRegex(ValueError, "separate interactive 3D"):
            validate_playful_classroom(generation, {"scenes": [game]})
        with self.assertRaisesRegex(ValueError, "separate interactive 3D"):
            validate_playful_classroom(generation, {"scenes": [game,
                {"type": "slide", "content": {"widgetType": "visualization3d"}}]})
        three_d = {"type": "interactive", "content": {"widgetType": "visualization3d"}}
        with self.assertRaisesRegex(ValueError, "missing.*game"):
            validate_playful_classroom(generation, {"scenes": [three_d]})
        validate_playful_classroom(generation, {"scenes": [game, three_d]})
        validate_playful_classroom({"professionalCreationPolicy": PLAYFUL_PROFESSIONAL_POLICY}, {"scenes": [game]})

    def test_required_3d_policy_rejects_downgrades_and_type_confusion(self):
        for field, value in (("threeDUsage", "teaching_need"), ("minimumThreeDScenes", 0),
                             ("minimumThreeDScenes", True), ("minimumReplayableGames", 0)):
            with self.subTest(field=field, value=value):
                policy = deepcopy(REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY)
                policy["playfulLearningPolicy"][field] = value
                with self.assertRaises(ValueError):
                    professional_policy(policy)

    def test_new_target_is_distinct_and_old_published_target_remains_compatible(self):
        current = build_preparation_target("primary_6")
        old = deepcopy(current)
        old["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(MULTISTATE_PROFESSIONAL_POLICY)
        self.assertEqual(policy_from_target(current), PLAYFUL_PROFESSIONAL_POLICY)
        self.assertNotEqual(preparation_target_fingerprint(old), preparation_target_fingerprint(current))
        self.assertTrue(compatible_preparation_target(old, current))
        old["formalRuntimePolicy"]["professionalCreationPolicy"]["webSearch"]["enabled"] = False
        self.assertFalse(compatible_preparation_target(old, current))

    def test_new_policy_cannot_weaken_play_or_assessment_authority(self):
        for field, value in (("aiDesigned", False), ("maxQuizScenes", 4),
                             ("minimumReplayableGames", 0), ("lockedAssessmentPreserved", False)):
            with self.subTest(field=field):
                policy = deepcopy(PLAYFUL_PROFESSIONAL_POLICY)
                policy["playfulLearningPolicy"][field] = value
                with self.assertRaises(ValueError):
                    professional_policy(policy)

    def test_quiz_label_does_not_count_as_a_game_and_old_course_is_unchanged(self):
        classroom = {"scenes": [{"type": "quiz", "content": {"widgetType": "game"}}]}
        validate_playful_classroom({"professionalCreationPolicy": MULTISTATE_PROFESSIONAL_POLICY}, classroom)
        with self.assertRaisesRegex(ValueError, "missing.*game"):
            validate_playful_classroom({"professionalCreationPolicy": PLAYFUL_PROFESSIONAL_POLICY}, classroom)

    def test_too_many_quiz_pages_rejected_even_with_a_game(self):
        scenes = [{"type": "interactive", "content": {"widgetType": "game"}}]
        scenes.extend({"type": "quiz"} for _ in range(3))
        with self.assertRaisesRegex(ValueError, "too many quiz"):
            validate_playful_classroom({"professionalCreationPolicy": PLAYFUL_PROFESSIONAL_POLICY}, {"scenes": scenes})
        scenes.pop()
        validate_playful_classroom({"professionalCreationPolicy": PLAYFUL_PROFESSIONAL_POLICY}, {"scenes": scenes})
