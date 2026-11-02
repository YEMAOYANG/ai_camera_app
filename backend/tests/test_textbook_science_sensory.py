import unittest
from copy import deepcopy
from content import textbook_science_sensory as s, textbook_course_interaction as ci
from core.errors import ApiError


PATHS = {2: ['eye', 'ear', 'hand'], 3: ['eye', 'ear', 'hand'],
         4: ['bell', 'chime'], 5: ['bell', 'open', 'chime', 'revise'],
         7: ['rotate', 'eye', 'hand', 'nose', 'tongue'],
         8: ['probe', 'stoneB', 'stoneA'],
         9: ['left', 'listen', 'right', 'listen', 'right', 'listen', 'water', 'bird'],
         10: ['colour', 'source', 'texture', 'source', 'taste', 'source', 'infer'],
         11: ['paint', 'test', 'bump', 'tone', 'test'],
         12: ['verify', 'tongue', 'eye', 'ear', 'hand', 'bell', 'verify', 'ball', 'verify']}


class ScienceSensoryTest(unittest.TestCase):
    def test_complete_all_pages_with_exact_binding_and_noncontiguous_indexes(self):
        room = {'scenes': [{'id': f'scene-p{i}', 'order': i,
            'type': 'interactive' if i in s.PAGES else 'slide', 'content': {'html': f'<main>{i}</main>'}}
            for i in range(1, 14)]}
        release = {'classroom': room, 'textbookBinding': s.BINDING,
                   'interactionCompletionContract': ci.build_contract(room, s.BINDING)}
        progress = {}; count = 0
        for p, actions in PATHS.items():
            work = s.fresh_work()
            for action in ['start'] + actions:
                s.transition(p, work, action); count += 1
                ci.apply_operation(progress, release=release, scene_index=p-1, scene_id=f'scene-p{p}',
                    contract_sha256=release['interactionCompletionContract']['sha256'],
                    operation_id=f'op-{count}', operation={'name': 'act', 'action': action, 'work': deepcopy(work)})
            self.assertTrue(progress['courseInteraction']['scenes'][f'scene-p{p}']['completed'], p)
        self.assertTrue(ci.completion_ready(progress, release))
        self.assertEqual(ci.recovery_state(progress, release)['scenes']['scene-p12']['lastWork']['firstGuess'], 'bell')
        release['classroom']['scenes'].pop(5)
        with self.assertRaises(ApiError): ci.validate_contract(release)

    def test_observation_and_reveal_do_not_credit_guess_as_verification(self):
        page = s.initial_page('science-sensory-p12.v1'); w = s.fresh_work()
        for action in ['start', 'eye', 'ear', 'hand', 'ball', 'verify']:
            s.transition(12, w, action)
            s.apply_page(page['validator'], page, dict(name='act', action=action, work=deepcopy(w)))
        self.assertFalse(page['completed'])
        s.transition(12, w, 'verify')
        s.apply_page(page['validator'], page, dict(name='act', action='verify', work=w))
        self.assertTrue(page['completed'])

    def test_forged_work_and_credit_do_not_mutate_page(self):
        state = s.initial_page('science-sensory-p5.v1')
        for action, patch in [('start', {'started': 1}), ('start', {'complete': True}),
                              ('open', {'revealed': True}), ('start', {'firstGuess': 'chime'})]:
            w = s.fresh_work(); w['started'] = True; w.update(patch)
            before = deepcopy(state)
            with self.assertRaises(ApiError): s.apply_page(state['validator'], state, dict(name='act', action=action, work=w))
            self.assertEqual(state, before)
        self.assertIsNone(s.validators({**s.BINDING, 'nodeId': 'different'}))

    def test_error_correction_history_survives_reset(self):
        state = s.initial_page('science-sensory-p11.v1'); w = s.fresh_work()
        for action in ['start', 'paint', 'test', 'help', 'bump', 'tone', 'test', 'reset']:
            s.transition(11, w, action)
            s.apply_page(state['validator'], state, dict(name='act', action=action, work=deepcopy(w)))
        self.assertFalse(state['completed']); self.assertEqual(state['helpCount'], 1)
        self.assertIn('stopped', [x['outcome'] for x in state['attempts']])
        self.assertIn('arrived', [x['outcome'] for x in state['attempts']])


if __name__ == '__main__': unittest.main()
