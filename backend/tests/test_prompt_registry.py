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


if __name__ == "__main__":
    unittest.main()
