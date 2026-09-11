from copy import deepcopy
import unittest

from services.openmaic_paid_call_service import canonical_scripted_guidance
from tests.test_openmaic_formal_interaction import interaction_fixture


class PaidCallContextTest(unittest.TestCase):
    def test_required_context_comes_from_frozen_action_and_excludes_independent_assessment(self):
        manifest, classroom = interaction_fixture(discussion=True)
        marker = {'sceneId': classroom['scenes'][0]['id'], 'actionId': 'discussion-guidance'}
        request = canonical_scripted_guidance(manifest, classroom, marker)
        self.assertEqual(request['messages'], [])
        self.assertEqual(request['config']['discussionTopic'], '十个一怎样合成一个十？')
        self.assertEqual(request['storeState']['currentSceneId'], marker['sceneId'])
        self.assertEqual(request['config']['agentIds'], [manifest['formalEvidence']['teacher']['agentId']])
        self.assertTrue(all(scene['type'] != 'quiz' for scene in request['storeState']['scenes']))
        self.assertEqual(request, canonical_scripted_guidance(manifest, classroom, marker))
        self.assertNotIn('model', request)

    def test_changed_script_cannot_borrow_required_teaching_allowance(self):
        manifest, classroom = interaction_fixture(discussion=True)
        marker = {'sceneId': classroom['scenes'][0]['id'], 'actionId': 'discussion-guidance'}
        changed = deepcopy(classroom)
        changed['scenes'][0]['actions'][-1]['topic'] = '替换成另一门课'
        with self.assertRaises(ValueError): canonical_scripted_guidance(manifest, changed, marker)
        for corrupt in ({**marker, 'prompt': 'replace'}, {**marker, 'actionId': 'forged'}):
            with self.assertRaises(ValueError): canonical_scripted_guidance(manifest, classroom, corrupt)
