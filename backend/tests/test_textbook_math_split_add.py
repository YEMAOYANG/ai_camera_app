import unittest
from copy import deepcopy

from content import textbook_math_split_add as m, textbook_course_interaction as ci
from core.errors import ApiError


def release(kind):
    binding = {'editionId': m.EDITION, 'revisionId': m.REVISION,
               'nodeId': next(k for k, v in m.NODES.items() if v == kind)}
    room = {'scenes': [{'id': f'scene-p{i}', 'order': i,
                       'type': 'interactive' if 2 <= i <= 11 else 'slide',
                       'content': {'html': f'<main>{kind}-{i}</main>'}}
                      for i in range(1, 13)]}
    return {'classroom': room, 'textbookBinding': binding,
            'interactionCompletionContract': ci.build_contract(room, binding)}


def cases():
    split = {
        2: [{'phase': n-1, 'left': ['ball-1'], 'right': [f'ball-{i}' for i in range(2, n+1)], 'unsent': []} for n in [2, 3]],
        3: [{'left': [f'lamp-{c}' for c in 'abcde'[:n]], 'right': [f'lamp-{c}' for c in 'abcde'[n:]]} for n in range(1, 5)],
        4: [{'left': ['L1', 'L2', 'L3'], 'right': ['L4', 'L5'], 'beforeLeft': ['L1', 'L2'], 'beforeRight': ['L3', 'L4', 'L5'], 'predictionLeft': 'more', 'predictionTotal': 'same'}],
        5: [{'round': 0, 'left': ['m2', 'm3', 'm4'], 'right': ['m1'], 'prediction': False, 'swaps': 1},
            {'round': 1, 'left': ['m3', 'm4'], 'right': ['m1', 'm2'], 'prediction': True, 'swaps': 1}],
        6: [{'round': r, 'left': [1], 'right': list(range(2, n+1)), 'prediction': n, 'gateOpen': True} for r, n in enumerate([4, 3, 5])],
        7: [{'photo': 'p5b', 'whole': 5, 'left': 2, 'right': 3}],
        8: [{'round': r, 'prediction': n, 'revealed': True} for r, n in enumerate([1, 2, 2])],
        9: [{'total': total, 'left': list(range(n)), 'right': list(range(n, total)), 'supply': []} for total in range(2, 6) for n in range(1, total)],
        10: [{'level': 0, 'left': ['lamp-a'], 'right': ['lamp-b', 'lamp-c'], 'prediction': None, 'revealed': False},
             {'level': 1, 'left': ['converge-l1', 'converge-l2'], 'right': ['converge-r1', 'converge-r2', 'converge-r3'], 'prediction': 5, 'revealed': True},
             {'level': 2, 'left': ['hide-v1', 'hide-v2'], 'right': ['hide-h1', 'hide-h2'], 'prediction': 2, 'revealed': True}],
        11: [{'total': 3, 'left': [1], 'right': [2, 3], 'hiddenSide': 'right', 'partnerGuess': 1, 'revealed': True,
              'saved': {'total': 3, 'left': [1], 'right': [2, 3], 'hiddenDock': 'right'}}],
    }
    add = {
        2: [{'round': r, 'prediction': n, 'gates': [True, True]} for r, n in enumerate([3, 4])],
        3: [{'A': 2, 'B': 1, 'C': 3}],
        4: [{'strokes': [[[60, 110], [160, 110]], [[110, 60], [110, 160]]], 'a': ['L1_a'], 'b': ['L2_b']}],
        5: [{'original': [1, 2], 'new': [3, 4, 5], 'total': 5}],
        6: [{'method': 'countOn', 'original': ['orig-1', 'orig-2'], 'new': ['new-1', 'new-2'], 'order': ['orig-1', 'orig-2', 'new-1', 'new-2'], 'left': [], 'right': []}],
        7: [{'left': ['l1', 'l2', 'l3', 'l4'], 'right': ['r1', 'r2', 'r3', 'r4'], 'plan': []}],
        8: [{'order': o, 'prediction': 3} for o in ['AB', 'BA']],
        9: [{'leftDots': 2, 'rightDots': 2, 'eqLeft': 2, 'eqRight': 2, 'eqTotal': 4}],
        10: [{'level': r, 'answer': n} for r, n in enumerate([5, 2, 'right'])],
        11: [{'part1': [{'id': 'i1', 'prop': 'boat'}], 'part2': [{'id': 'i2', 'prop': 'boat'}, {'id': 'i3', 'prop': 'crate'}], 'equation': {'num1': 1, 'num2': 2, 'sum': 3}}],
    }
    return {'split': split, 'add': add}


class SplitAddCompletionTest(unittest.TestCase):
    def test_twenty_pages_and_full_release_recovery(self):
        for kind, pages in cases().items():
            rel, progress, seq = release(kind), {}, 0
            for page, works in pages.items():
                for work in works:
                    seq += 1
                    ci.apply_operation(progress, release=rel, scene_id=f'scene-p{page}', scene_index=page-1,
                                       contract_sha256=rel['interactionCompletionContract']['sha256'],
                                       operation_id=f'math-{seq}', operation={'name': 'submit', 'work': work})
            self.assertTrue(ci.completion_ready(progress, rel), kind)
            self.assertEqual(len(ci.recovery_state(progress, rel)['scenes']), 10)

    def test_no_skip_duplicate_objects_or_completion_flags(self):
        v = 'math-split-p2.v1'
        for w in [cases()['split'][2][1],
                  {'phase': 1, 'left': ['ball-1'], 'right': ['ball-1'], 'unsent': []},
                  {**cases()['split'][2][0], 'completed': True}]:
            with self.assertRaises(ApiError):
                m.apply_page(v, m.initial_page(v), {'name': 'submit', 'work': w})

    def test_wrong_math_feedback_and_help_are_retained(self):
        v = 'math-add-p3.v1'; state = m.initial_page(v)
        wrong = {'A': 2, 'B': 1, 'C': 4}
        for name in ['help', 'submit']:
            m.apply_page(v, state, {'name': name, 'work': wrong})
        self.assertFalse(state['completed'])
        m.apply_page(v, state, {'name': 'submit', 'work': {'A': 2, 'B': 1, 'C': 3}})
        self.assertEqual([a['correct'] for a in state['attempts']], [False, True])
        self.assertEqual(state['attempts'][1]['helpCount'], 1)
        self.assertEqual(state['evidenceBoundary'], 'client_reported_picture_supported_practice')

    def test_plus_requires_crossing_geometry_and_stroke_direction(self):
        good = cases()['add'][4][0]['strokes']
        self.assertTrue(m.plus_trace(good))
        for bad in [good[::-1], [good[0][::-1], good[1]],
                    [[[10, 10], [100, 10]], [[180, 50], [180, 150]]],
                    [[[60, 110], [90, 10], [160, 110]], good[1]]]:
            self.assertFalse(m.plus_trace(bad))

    def test_impossibility_requires_all_observed_partitions(self):
        v = 'math-split-p9.v1'; state = m.initial_page(v)
        for n in [1, 2, 3]:
            work = {'total': 5, 'left': list(range(n)), 'right': list(range(n, 5)), 'supply': []}
            m.apply_page(v, state, {'name': 'submit', 'work': work})
            self.assertNotIn('5', state['passedTasks'])
        m.apply_page(v, state, {'name': 'submit', 'work': {'total': 5, 'left': [0, 1, 2, 3], 'right': [4], 'supply': []}})
        self.assertIn('5', state['passedTasks'])
        self.assertNotIn('4', state['passedTasks'])

    def test_creation_checks_own_objects_and_multiple_valid_works(self):
        v = 'math-add-p11.v1'
        for a, b in [(1, 1), (2, 3), (3, 1)]:
            work = {'part1': [{'id': f'a{i}', 'prop': 'boat'} for i in range(a)],
                    'part2': [{'id': f'b{i}', 'prop': 'ball'} for i in range(b)],
                    'equation': {'num1': a, 'num2': b, 'sum': a+b}}
            state = m.initial_page(v)
            wrong = deepcopy(work); wrong['equation']['sum'] = 1
            m.apply_page(v, state, {'name': 'submit', 'work': wrong})
            self.assertFalse(state['completed'])
            m.apply_page(v, state, {'name': 'submit', 'work': work})
            self.assertTrue(state['completed'])

    def test_missing_or_changed_scene_cannot_shrink_completion(self):
        for kind in ['split', 'add']:
            for mutate in [lambda r: r['classroom']['scenes'].pop(4),
                           lambda r: r['classroom']['scenes'][4]['content'].update(html='changed')]:
                rel = release(kind); mutate(rel)
                with self.assertRaises(ApiError):
                    ci.validate_contract(rel)


if __name__ == '__main__':
    unittest.main()
