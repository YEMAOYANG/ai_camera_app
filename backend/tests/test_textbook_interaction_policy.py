"""Policy snapshot identity checks; pedagogical acceptance still needs real play."""
from copy import deepcopy
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
        self.assertEqual(frozen['policy']['version'], 2)
        self.assertIn('wholeCourseQualityContract', frozen['policy'])
        self.assertIn(
            'child_visible_world_model',
            {rule['id'] for rule in frozen['policy']['rules']},
        )

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
