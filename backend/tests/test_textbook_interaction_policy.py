"""Policy snapshot identity checks; pedagogical acceptance still needs real play."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from content.textbook_catalog import digest
from content.textbook_interaction_policy import freeze_interaction_policy, interaction_policy_prompt


class InteractionPolicySnapshotTest(unittest.TestCase):
    def test_frozen_policy_renders_without_reading_current_registry(self):
        frozen = freeze_interaction_policy()
        expected = interaction_policy_prompt(frozen)
        with patch('pathlib.Path.read_text', side_effect=OSError('registry unavailable')):
            self.assertEqual(interaction_policy_prompt(frozen), expected)
        self.assertIn(frozen['sha256'], expected)
        self.assertIn(frozen['policy']['policyId'], expected)
        self.assertEqual(frozen['policy']['version'], 8)
        self.assertIn('wholeCourseQualityContract', frozen['policy'])
        self.assertIn(
            'child_visible_world_model',
            {rule['id'] for rule in frozen['policy']['rules']},
        )
        self.assertIn(
            'official_source_review_before_authoring',
            {rule['id'] for rule in frozen['policy']['rules']},
        )
        self.assertEqual(
            frozen['policy']['officialResourceReviewContract']['requiredResources'],
            ['video', 'courseware', 'teachingDesign', 'learningTaskSheet', 'afterClassExercise'],
        )
        contract = frozen['policy']['officialResourceReviewContract']
        self.assertEqual(contract['acceptedStatuses'], ['reviewed', 'not_provided'])
        self.assertEqual(contract['userApprovedUnavailableException']['conditionalStatus'], 'waived_unavailable')
        self.assertEqual(contract['userApprovedUnavailableException']['allowedResourceTypes'], ['video', 'courseware'])
        self.assertEqual(contract['videoModalityReview']['schemaVersion'],
                         'mira.official-video-modality-review.v1')
        self.assertIn('supplementary_only_not_audio_review', contract['videoModalityReview']['audio'])
        self.assertIn('DRM', contract['videoModalityReview']['noAudio'])
        self.assertIn('48px', frozen['policy']['htmlGameExperienceContract']['controls'])
        self.assertIn('全宽药丸', frozen['policy']['htmlGameExperienceContract']['controls'])
        game_shell = frozen['policy']['htmlGameExperienceContract']['gameShell']
        self.assertIn('ready→playing', game_shell['stateMachine'])
        self.assertIn('教师预录音', game_shell['readyOverlay'])
        self.assertIn('正式积分账本', game_shell['hud'])
        self.assertIn('相邻关卡', game_shell['levelProgression'])
        self.assertIn(
            'free_html_game_stage_and_compact_controls',
            {rule['id'] for rule in frozen['policy']['rules']},
        )
        self.assertIn(
            'level_game_shell_with_start_hud_and_retry',
            {rule['id'] for rule in frozen['policy']['rules']},
        )
        practice = frozen['policy']['postClassPracticeContract']
        self.assertIn('inCoursePractice', practice['inCourseUse'])
        self.assertIn('activityId', practice['inCourseUse'])
        self.assertIn('goalId', practice['inCourseUse'])
        self.assertIn('sourceLocations', practice['inCourseUse'])
        self.assertNotIn('语文园地四', json.dumps(frozen['policy'], ensure_ascii=False))

    def test_content_tampering_fails_before_render(self):
        frozen = freeze_interaction_policy()
        frozen['policy']['rules'][0]['requirement'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'digest'):
            interaction_policy_prompt(frozen)

    def test_duplicate_rule_identity_is_invalid_even_with_matching_hash(self):
        frozen = freeze_interaction_policy()
        frozen['policy']['rules'].append(deepcopy(frozen['policy']['rules'][0]))
        frozen['sha256'] = digest(frozen['policy'])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            interaction_policy_prompt(frozen)

    def test_new_policy_snapshot_cannot_mutate_an_earlier_snapshot(self):
        previous = freeze_interaction_policy()
        original_prompt = interaction_policy_prompt(previous)
        later = freeze_interaction_policy()
        later['policy']['version'] += 1
        later['policy']['rules'][0]['requirement'] = 'new generation requirement'
        later['sha256'] = digest(later['policy'])
        self.assertNotEqual(interaction_policy_prompt(later), original_prompt)
        self.assertEqual(interaction_policy_prompt(previous), original_prompt)


if __name__ == '__main__':
    unittest.main()
