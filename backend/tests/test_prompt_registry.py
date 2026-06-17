from __future__ import annotations

import unittest
from pathlib import Path

from services.prompt_registry import PromptRegistry


class PromptRegistryTest(unittest.TestCase):
    def test_lists_versioned_prompts(self):
        root = Path(__file__).resolve().parents[1] / "prompts"
        prompts = PromptRegistry(root).list_prompts()
        ids = {(prompt.prompt_id, prompt.version) for prompt in prompts}

        self.assertIn(("task.observation.summary", "v1"), ids)
        self.assertIn(("task.reminder.voice", "v1"), ids)
        self.assertIn(("reminder.toy_cleanup", "v1"), ids)
        self.assertIn(("reminder.posture", "v1"), ids)
        self.assertIn(("reminder.meal_start", "v1"), ids)
        self.assertIn(("reminder.meal_habit", "v1"), ids)
        self.assertIn(("reminder.nap_time", "v1"), ids)
        self.assertIn(("reminder.bedtime", "v1"), ids)
        self.assertIn(("reminder.wake_up", "v1"), ids)
        self.assertIn(("reminder.transition", "v1"), ids)
        self.assertIn(("reminder.fallback", "v1"), ids)
        self.assertIn(("vision.scene_observation", "v1"), ids)
        self.assertIn(("vision.behavior_summary", "v1"), ids)


if __name__ == "__main__":
    unittest.main()
