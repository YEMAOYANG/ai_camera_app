from copy import deepcopy
import hashlib
import json
import unittest

from services.openmaic_student_participation import controls_for_objective, reviewed_controls
from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService


class StudentParticipationTest(unittest.TestCase):
    def test_sibling_preset_is_real_participation_without_granting_reset_or_other_controls(self):
        html = '<div><button id="example">3/5 × 2</button><button id="other">3/5 × 3</button><button id="reset">Reset</button></div><button id="outside">Next</button>'
        objective = {"objectiveIndex": 0, "operation": {"sceneId": "p4", "controlSelector": "#example", "action": "click"},
                     "exploration": {"reset": {"selector": "#reset"}, "states": []}}
        controls = controls_for_objective(html, objective)
        self.assertEqual({item["controlSelector"] for item in controls}, {"#example", "#other"})
        payload = {"sceneId": "p4", "objectiveIndex": 0, "controlSelector": "#other", "action": "click", "value": "", "feedbackText": "三份五分之三是五分之九"}
        derived = {**objective, "participationControls": controls}
        self.assertTrue(OpenMaicRuntimeEventService._operation_matches(derived, payload))
        for change in ({"controlSelector": "#reset"}, {"controlSelector": "#outside"}, {"sceneId": "another"}, {"feedbackText": ""}):
            self.assertFalse(OpenMaicRuntimeEventService._operation_matches(derived, {**payload, **change}))
        self.assertNotIn("participationControls", objective)

    def test_duplicate_disabled_and_submit_controls_are_not_alternatives(self):
        html = '<div><button id="example"></button><button id="duplicate"></button><button id="duplicate"></button><button id="disabled" disabled></button><button id="submit" type="submit"></button></div>'
        objective = {"operation": {"controlSelector": "#example", "action": "click"}}
        self.assertEqual(controls_for_objective(html, objective), [{"controlSelector": "#example", "action": "click"}])

    def test_each_reviewed_english_row_accepts_both_choices_but_not_other_groups(self):
        pairs = [("he", "him"), ("her", "she"), ("we", "us"), ("me", "i"), ("them", "they")]
        groups = ''.join('<div class="row"><div class="tiles">' + ''.join(
            f'<button id="pick-{word}" type="button">{word}</button>' for word in pair
        ) + '<button id="disabled-' + str(index) + '" disabled></button></div></div>'
            for index, pair in enumerate(pairs))
        html = '<main>' + groups + '<button id="reset">Reset</button><div><button id="outside">Next</button></div></main>'
        objective = {"operation": {"controlSelector": "#pick-him", "action": "click"},
            "exploration": {"reset": {"selector": "#reset"}, "states": [
                {"operations": [{"selector": "#pick-" + pair[1], "action": "click"}]} for pair in pairs]}}
        controls = controls_for_objective(html, objective)
        self.assertEqual({row["controlSelector"] for row in controls},
            {"#pick-" + word for pair in pairs for word in pair})
        self.assertEqual(len(controls), 10)

    def test_unpublished_document_cannot_add_controls(self):
        classroom = {"stage": {"id": "participation-hash-test"}, "scenes": []}
        digest = hashlib.sha256(json.dumps(classroom, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
        modified = deepcopy(classroom)
        modified["stage"]["title"] = "changed"
        with self.assertRaises(ValueError):
            reviewed_controls(classroom_id=classroom["stage"]["id"], content_sha256=digest, objectives=[], reader=lambda _: modified)


if __name__ == '__main__':
    unittest.main()
