import json
import re
import unittest
from pathlib import Path

from courseware.kit import contract


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "courseware/tools/tests/fixtures/sample_body.json"


def find_actions(value):
    if isinstance(value, dict):
        if value.get("type") in contract.WIDGET_ACTION_TYPES:
            yield value
        for child in value.values():
            yield from find_actions(child)
    elif isinstance(value, list):
        for child in value:
            yield from find_actions(child)


class WidgetContractTest(unittest.TestCase):
    def test_lesson_kit_uses_contract_messages_and_stage(self):
        kit = (ROOT / "courseware/lessons/pep-math-g1-upper-tidy-review/kit.py").read_text()
        for message_type in contract.WIDGET_ACTION_TO_MESSAGE.values():
            self.assertIn(message_type, kit)
        self.assertIn(f"width:{contract.INTERACTIVE_WIDTH}px", kit)
        self.assertIn(f"height:{contract.INTERACTIVE_HEIGHT}px", kit)

    def test_audit_host_messages_are_in_contract(self):
        audit = (ROOT / "courseware/lessons/pep-math-g1-upper-tidy-review/audit.py").read_text()
        posted_types = set(re.findall(r"postMessage\(\s*\{\s*type\s*:\s*['\"]([^'\"]+)", audit))
        self.assertLessEqual(posted_types, set(contract.WIDGET_ACTION_TO_MESSAGE.values()))

    def test_widget_messages_match_fixture_actions(self):
        body = json.loads(FIXTURE.read_text())
        actions = {action["type"]: action for action in find_actions(body)}
        self.assertEqual(set(actions), contract.WIDGET_ACTION_TYPES)
        expected = {
            "widget_setState": lambda action: {"type": contract.SET_WIDGET_STATE, "state": action["state"]},
            "widget_highlight": lambda action: {"type": contract.HIGHLIGHT_ELEMENT, "target": action["target"]},
            "widget_annotation": lambda action: {"type": contract.ANNOTATE_ELEMENT, "target": action["target"], "content": action["content"]},
            "widget_reveal": lambda action: {"type": contract.REVEAL_ELEMENT, "target": action["target"]},
        }
        for action_type, action in actions.items():
            with self.subTest(action_type=action_type):
                self.assertEqual(contract.widget_message(action), expected[action_type](action))

    def test_unknown_widget_action_type_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown widget action type: 'widget_unknown'"):
            contract.widget_message({"type": "widget_unknown"})


if __name__ == "__main__":
    unittest.main()
