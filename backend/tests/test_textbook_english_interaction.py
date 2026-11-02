import unittest
from copy import deepcopy
from content import textbook_english_interaction as e, textbook_course_interaction as ci
from core.errors import ApiError


def work(page, r=0):
    w = {'round': r, 'seed': 42, 'started': True, 'poses': [0, 0], 'door': 0, 'window': 0,
         'selected': 0, 'turnSwap': 0, 'lastAction': None, 'route': [], 'oral': 'none', 'chosen': 'stand'}
    if page == 4:
        w['route'] = [{'cmd': x, 'actor': 0} for x in e.ROUTES[r]]
    elif page == 7:
        w['chosen'] = e.COMMANDS[7][r]; w['oral'] = 'self-reported'
    else:
        actor = r % 2 if page in [5, 8, 9] else 0
        cmd = e.COMMANDS[page][r]; w['selected'] = actor; w['lastAction'] = {'cmd': cmd, 'actor': actor}
        if cmd in ['stand', 'sit']:
            w['poses'][actor] = 1 if cmd == 'stand' else 0
        else:
            w[cmd] = 1
    return w


class EnglishInteractionTest(unittest.TestCase):
    def test_full_course_requires_all_rounds_and_recovers_without_mastery(self):
        room = {'scenes': [{'id': f'scene-p{i}', 'order': i,
            'type': 'interactive' if 2 <= i <= 9 else 'slide', 'content': {'html': f'<main>{i}</main>'}}
            for i in range(1, 11)]}
        release = {'classroom': room, 'textbookBinding': e.BINDING,
                   'interactionCompletionContract': ci.build_contract(room, e.BINDING)}
        progress = {}; n = 0
        for page in range(2, 10):
            for r in range(2 if page == 4 else 4):
                self.assertFalse(ci.completion_ready(progress, release))
                n += 1
                ci.apply_operation(progress, release=release, scene_id=f'scene-p{page}', scene_index=page-1,
                    contract_sha256=release['interactionCompletionContract']['sha256'], operation_id=f'op-{n}',
                    operation={'name': 'submit', 'work': work(page, r)})
        self.assertTrue(ci.completion_ready(progress, release))
        oral = ci.recovery_state(progress, release)['scenes']['scene-p7']['attempts']
        self.assertTrue(all(x['correct'] is None and x['oralAccuracy'] == 'unobserved' for x in oral))
        release['classroom']['scenes'].pop(3)
        with self.assertRaises(ApiError): ci.validate_contract(release)

    def test_incorrect_objects_actor_and_route_do_not_complete(self):
        for page, change, reason in [(2, {'poses': [0, 0]}, 'wrong_pose'),
                (3, {'door': 0, 'window': 1}, 'wrong_object'),
                (3, {'window': 1}, 'extra_open_object'),
                (5, {'lastAction': {'cmd': 'stand', 'actor': 1}}, 'wrong_person'),
                (4, {'route': [{'cmd': 'sit', 'actor': 0}] * 3}, 'route_mismatch')]:
            s = e.initial_page(f'english-classroom-p{page}.v1'); w = work(page); w.update(change)
            e.apply_page(s['validator'], s, {'name': 'submit', 'work': w})
            self.assertEqual(s['attempts'][0]['reason'], reason)
            self.assertFalse(s['completed']); self.assertFalse(s['passedTasks'])
            e.apply_page(s['validator'], s, {'name': 'submit', 'work': work(page)})
            self.assertEqual(s['passedTasks'], [0])

    def test_help_work_forged_credit_and_round_skip(self):
        s = e.initial_page('english-classroom-p9.v1')
        for name in ['help', 'work']:
            e.apply_page(s['validator'], s, {'name': name, 'work': work(9)})
        self.assertEqual(s['passedTasks'], []); self.assertEqual(s['helpCount'], 1)
        for patch in [{'round': 2}, {'seed': 43}, {'round': True}, {'poses': [float('nan'), 0]},
                      {'completed': True}, {'chosen': []}, {'lastAction': {'cmd': [], 'actor': 0}},
                      {'lastAction': {'cmd': 'jump', 'actor': 0}}]:
            w = work(9); w.update(patch)
            with self.assertRaises(ApiError): e.apply_page(s['validator'], deepcopy(s), {'name': 'submit', 'work': w})
        self.assertIsNone(e.validators({**e.BINDING, 'nodeId': 'another'}))
