import json
import math
import unittest
from copy import deepcopy

from content import textbook_course_interaction as ci
from content import textbook_math_subtract_zero as m
from content.textbook_catalog import digest
from core.errors import ApiError


def eq(a, b, c):
    return {'whole': a, 'change': b, 'result': c}


def mapped():
    return {'whole': 'before', 'change': 'removed', 'result': 'remaining'}


def oval():
    return [[[.5-.25*math.sin(t*math.pi/16), .5-.4*math.cos(t*math.pi/16)] for t in range(33)]]


def subtract_story(n=4, removed=None):
    removed = [2] if removed is None else removed
    return {'total': n, 'removed': removed, 'remaining': [i for i in range(1, n+1) if i not in removed],
            'equation': eq(n, len(removed), n-len(removed))}


def zero_story(typ='all-left', n=4):
    operator = 'add' if typ in ('empty', 'no-arrivals') else 'subtract'
    changed = list(range(1, n+1)) if typ == 'all-left' else []
    remaining = [] if typ == 'all-left' else list(range(1, n+1))
    return {'type': typ, 'total': n, 'operator': operator, 'changed': changed,
            'remaining': remaining, 'equation': eq(n, len(changed), len(remaining))}


def event(n, operator):
    return {'total': n, 'operator': operator, 'changed': [], 'remaining': list(range(1, n+1)),
            'executed': True, 'equation': eq(n, 0, n)}


def cases():
    story = subtract_story()
    zero = zero_story()
    return {'subtract': {
        1: [{'removed': [2, 5], 'remaining': [1, 3, 4], 'prediction': 3}],
        2: [{'removed': [3], 'remaining': [1, 2, 4], 'answer': 3}],
        3: [{**story, 'links': mapped()}],
        4: [{'total': 3, 'removed': [2], 'remaining': [1, 3], 'symbol': 'subtract',
             'mode': 'trace', 'strokes': [[[.2, .5], [.5, .5], [.8, .5]]]}],
        5: [{'removed': [2, 4], 'remaining': [1, 3, 5], 'pairs': [[5, 1], [1, 2], [3, 3]]}],
        6: [{'removed': [1, 4], 'remaining': [2, 3, 5], 'equation': eq(5, 2, 3), 'evidence': 'before'}],
        7: [{'removed': [4], 'remaining': [1, 2, 3], 'method': 'count-remaining',
             'counted': [3, 1, 2], 'countdown': [], 'answer': 3}],
        8: [{'groupA': [1, 4, 5], 'groupB': [2, 3], 'removed': [1, 4, 5], 'remaining': [2, 3], 'answer': 2}],
        9: [{'removedA': [5], 'remainingA': [1, 2, 3, 4], 'removedB': [1, 2, 3], 'remainingB': [4, 5], 'prediction': 'A'}],
        10: [{'removed': [3], 'remaining': [1, 2], 'answer': 2}],
        11: [{'story': story, 'saved': deepcopy(story)}],
        12: [{'story': story, 'saved': deepcopy(story), 'links': mapped(),
              'sourceWorkSha256': digest(story), 'storyVersion': 1, 'recordVersion': 1}],
    }, 'zero': {
        1: [{'removed': [1, 2], 'remaining': [], 'answer': 0}],
        2: [{'context': 'harbour', 'objects': [], 'position': 0, 'meaning': 'empty'},
            {'context': 'ruler', 'objects': [1], 'position': 0, 'meaning': 'origin'}],
        3: [{'order': list(range(6)), 'quantities': [list(range(1, n+1)) for n in range(6)]}],
        4: [{'mode': mode, 'strokes': oval()} for mode in ('trace', 'free')],
        5: [{'removed': [1, 2, 3, 4], 'remaining': [], 'equation': eq(4, 4, 0), 'links': mapped()}],
        6: [{'total': 3, 'removed': [1, 2, 3], 'remaining': [], 'prediction': 0}],
        7: [{'incoming': [], 'remaining': [1, 2, 3], 'gateOpen': True, 'prediction': 3}],
        8: [{'removed': [], 'remaining': [1, 2], 'executed': True, 'equation': eq(2, 0, 2)}],
        9: [{**event(3, 'add'), 'context': 'incoming'}, {**event(2, 'subtract'), 'context': 'departing'}],
        10: [{k: v for k, v in event(0, op).items() if k != 'total'} for op in ('add', 'subtract')],
        11: [event(2, 'add'), event(4, 'subtract')],
        12: [{'context': 'tools', 'objects': [], 'position': 0, 'meaning': 'empty'},
             {'context': 'path', 'objects': [1], 'position': 0, 'meaning': 'origin'}],
        13: [{'story': zero, 'saved': deepcopy(zero)}],
        14: [{'story': zero, 'saved': deepcopy(zero), 'zeroRole': 'result',
              'sourceWorkSha256': digest(zero), 'storyVersion': 1, 'recordVersion': 1}],
    }}


def before_prediction(kind, page, work):
    w = deepcopy(work)
    if kind == 'subtract' and page == 9:
        for side in ('A', 'B'):
            w['removed'+side] = []; w['remaining'+side] = list(range(1, 6))
    elif kind == 'zero' and page == 7:
        w['gateOpen'] = False
    else:
        w['removed'] = []; w['remaining'] = list(range(1, (5 if kind == 'subtract' else w['total'])+1))
    return w


def release(kind):
    binding = {'editionId': m.EDITION, 'revisionId': m.REVISION,
               'nodeId': next(k for k, v in m.NODES.items() if v == kind)}
    room = {'scenes': [{'id': f'scene-p{p}', 'order': p, 'type': 'interactive',
                       'content': {'html': f'<main>{kind}-{p}</main>'}}
                      for p in range(1, m.PAGE_COUNTS[kind]+1)]}
    return {'classroom': room, 'textbookBinding': binding,
            'interactionCompletionContract': ci.build_contract(room, binding)}


class SubtractZeroTest(unittest.TestCase):
    def apply(self, kind, page, state, name, work, previous=None):
        m.apply_page(f'math-{kind}-p{page}.v1', state, {'name': name, 'work': work}, previous=previous)

    def fresh(self, kind, page):
        return m.initial_page(f'math-{kind}-p{page}.v1')

    def test_all_twenty_six_pages_complete_and_restore_only_from_server(self):
        for kind, pages in cases().items():
            rel, progress, seq = release(kind), {}, 0
            def op(page, name, work):
                nonlocal seq
                seq += 1
                return ci.apply_operation(progress, release=rel, scene_index=page-1, scene_id=f'scene-p{page}',
                    contract_sha256=rel['interactionCompletionContract']['sha256'], operation_id=f'op-{seq}',
                    operation={'name': name, 'work': work})
            for page, works in pages.items():
                for work in works:
                    if (kind, page) in m.PREDICTION_PAGES:
                        op(page, 'predict', before_prediction(kind, page, work))
                    op(page, 'submit', work)
                self.assertTrue(progress['courseInteraction']['scenes'][f'scene-p{page}']['completed'], (kind, page))
            self.assertTrue(ci.completion_ready(progress, rel))
            progress['activityCheckpoint'] = {'completed': True, 'score': 100}
            restored = ci.recovery_state(progress, rel)
            self.assertEqual(len(restored['scenes']), m.PAGE_COUNTS[kind])
            self.assertEqual(json.loads(json.dumps(restored)), restored)
            restored['scenes']['scene-p1']['attempts'].clear()
            self.assertTrue(progress['courseInteraction']['scenes']['scene-p1']['attempts'])

    def test_exact_binding_all_pages_and_hashes_are_required(self):
        for kind in m.PAGE_COUNTS:
            for mutate in (lambda r: r['classroom']['scenes'].pop(0),
                           lambda r: r['classroom']['scenes'][0].update(type='slide'),
                           lambda r: r['classroom']['scenes'][0]['content'].update(html='changed'),
                           lambda r: r['textbookBinding'].update(nodeId='unknown'),
                           lambda r: r['classroom']['scenes'].reverse()):
                rel = release(kind); mutate(rel)
                with self.assertRaises(ApiError): ci.validate_contract(rel)
            self.assertEqual([s['sceneIndex'] for s in release(kind)['interactionCompletionContract']['scenes']],
                             list(range(m.PAGE_COUNTS[kind])))
        self.assertIsNone(m.validators({'editionId': m.EDITION, 'revisionId': m.REVISION, 'nodeId': 'unknown'}))

    def test_forged_flags_unknown_fields_and_object_identity_are_atomic_errors(self):
        good = cases()['subtract'][2][0]
        for bad in ({**good, 'completed': True}, {**good, 'score': 100},
                    {**good, 'firstAttempt': True}, {**good, 'removed': [3, 3]},
                    {**good, 'remaining': [1, 2, 5]}, {**good, 'removed': [True]}):
            state = self.fresh('subtract', 2); old = deepcopy(state)
            with self.assertRaises(ApiError): self.apply('subtract', 2, state, 'submit', bad)
            self.assertEqual(state, old)
        with self.assertRaises(ApiError): self.apply('subtract', 2, self.fresh('subtract', 2), 'complete', good)

    def test_wrong_first_attempt_help_retry_undo_and_replay_do_not_rewrite_evidence(self):
        state = self.fresh('subtract', 10)
        wrong = {**cases()['subtract'][10][0], 'answer': 1}
        self.apply('subtract', 10, state, 'submit', wrong)
        original = deepcopy(state['firstAttempts']['task'])
        for name in ('replay', 'hint', 'demonstration', 'retry', 'undo'):
            self.apply('subtract', 10, state, name, wrong)
        self.apply('subtract', 10, state, 'submit', cases()['subtract'][10][0])
        self.assertTrue(state['completed']); self.assertEqual(state['firstAttempts']['task'], original)
        self.assertEqual([a['correct'] for a in state['attempts']], [False, True])
        self.assertEqual(state['attempts'][-1]['support'], {'replay': 1, 'hint': 1, 'demonstration': 1})
        self.assertEqual((state['undoCount'], state['retryCount']), (1, 1))
        before = deepcopy(state)
        with self.assertRaises(ApiError): self.apply('subtract', 10, state, 'replay', wrong)
        self.assertEqual(state, before)
        self.apply('subtract', 10, state, 'work', wrong)
        self.assertFalse(state['completed'])
        self.assertEqual(state['oralSkill'], 'unobserved')

    def test_predictions_must_precede_events_and_first_prediction_survives_revision(self):
        for kind, page in m.PREDICTION_PAGES:
            good = cases()[kind][page][0]; state = self.fresh(kind, page)
            with self.assertRaises(ApiError): self.apply(kind, page, state, 'submit', good)
            with self.assertRaises(ApiError): self.apply(kind, page, state, 'predict', good)
            wrong = before_prediction(kind, page, good)
            wrong['prediction'] = 'B' if page == 9 else 1
            self.apply(kind, page, state, 'predict', wrong)
            first = deepcopy(state['firstPredictions']['task'])
            self.apply(kind, page, state, 'submit', {**good, 'prediction': wrong['prediction']})
            self.assertFalse(state['completed'])
            self.apply(kind, page, state, 'undo', before_prediction(kind, page, good))
            self.apply(kind, page, state, 'predict', before_prediction(kind, page, good))
            self.apply(kind, page, state, 'submit', good)
            self.assertTrue(state['completed']); self.assertEqual(state['firstPredictions']['task'], first)

    def test_prediction_revision_keeps_visible_world_and_original_evidence(self):
        for kind, page in m.PREDICTION_PAGES:
            state = self.fresh(kind, page)
            good = cases()[kind][page][0]
            wrong = before_prediction(kind, page, good)
            wrong['prediction'] = 'B' if page == 9 else 1
            self.apply(kind, page, state, 'predict', wrong)
            first = deepcopy(state['firstPredictions']['task'])
            self.apply(kind, page, state, 'submit', {**good, 'prediction': wrong['prediction']})
            self.apply(kind, page, state, 'predict', good)
            self.assertEqual(state['firstPredictions']['task'], first)
            self.assertTrue(state['latestPredictions']['task']['afterReveal'])
            self.assertEqual(state['latestPredictions']['task']['priorExposure'], 1)
            self.assertEqual(state['latestPredictions']['task']['priorAttempts'], 1)
            self.apply(kind, page, state, 'submit', good)
            self.assertTrue(state['completed'])
            self.assertFalse(state['attempts'][0]['correct'])

        state = self.fresh('subtract', 1)
        good = cases()['subtract'][1][0]
        self.apply('subtract', 1, state, 'predict', before_prediction('subtract', 1, good))
        self.apply('subtract', 1, state, 'work', good)
        before = deepcopy(state)
        with self.assertRaises(ApiError):
            self.apply('subtract', 1, state, 'predict', {
                'removed': [1, 2], 'remaining': [3, 4, 5], 'prediction': 3})
        self.assertEqual(state, before)

        unseen_prediction = self.fresh('subtract', 1)
        self.apply('subtract', 1, unseen_prediction, 'work', good)
        with self.assertRaises(ApiError):
            self.apply('subtract', 1, unseen_prediction, 'predict', good)

    def test_source_context_comes_only_from_completed_server_work(self):
        for kind, source_page in [('subtract', 11), ('zero', 13)]:
            rel, progress = release(kind), {}
            target_id = f'scene-p{source_page+1}'
            missing = ci.recovery_state(progress, rel)['sourceContexts'][target_id]
            self.assertFalse(missing['available'])
            self.assertIsNone(missing['saved'])
            self.assertIsNone(missing['sourceWorkSha256'])
            progress['activityCheckpoint'] = {'saved': cases()[kind][source_page][0]['saved'], 'completed': True}
            self.assertEqual(ci.recovery_state(progress, rel)['sourceContexts'][target_id], missing)
            work = cases()[kind][source_page][0]
            ci.apply_operation(progress, release=rel, scene_index=source_page-1,
                scene_id=f'scene-p{source_page}', contract_sha256=rel['interactionCompletionContract']['sha256'],
                operation_id='source-save', operation={'name': 'submit', 'work': work})
            source = ci.recovery_state(progress, rel)['sourceContexts'][target_id]
            self.assertTrue(source['available'])
            self.assertEqual(source['sourceSceneId'], f'scene-p{source_page}')
            self.assertEqual(source['saved'], work['saved'])
            self.assertEqual(source['sourceWorkSha256'], digest(work['saved']))
            source['saved']['equation']['whole'] = 999
            self.assertNotEqual(ci.recovery_state(progress, rel)['sourceContexts'][target_id]['saved'], source['saved'])

        previous = self.fresh('zero', 13)
        self.apply('zero', 13, previous, 'submit', cases()['zero'][13][0])
        state = self.fresh('zero', 14)
        unanswered = {**cases()['zero'][14][0], 'zeroRole': None}
        self.apply('zero', 14, state, 'work', unanswered, previous)
        self.assertFalse(state['completed'])
        self.assertEqual(state['attempts'], [])
        self.apply('zero', 14, state, 'submit', unanswered, previous)
        self.assertFalse(state['completed'])

    def test_multiple_real_object_subsets_and_open_stories_are_valid(self):
        for gone in ([1], [2], [3], [4]):
            state = self.fresh('subtract', 2)
            self.apply('subtract', 2, state, 'submit', {'removed': gone, 'remaining': [i for i in range(1, 5) if i not in gone], 'answer': 3})
            self.assertTrue(state['completed'])
        for n in range(2, 6):
            for count in range(1, n):
                story = subtract_story(n, list(range(1, count+1))); state = self.fresh('subtract', 11)
                self.apply('subtract', 11, state, 'submit', {'story': story, 'saved': deepcopy(story)})
                self.assertTrue(state['completed'])
        for typ, n in [('empty', 0), ('all-left', 1), ('no-arrivals', 5), ('no-departures', 0)]:
            story = zero_story(typ, n); state = self.fresh('zero', 13)
            self.apply('zero', 13, state, 'submit', {'story': story, 'saved': deepcopy(story)})
            self.assertTrue(state['completed'])

    def test_geometry_requires_actual_ink_direction_and_one_stroke(self):
        good = oval(); self.assertTrue(m.zero_trace(good))
        for bad in ([good[0][::-1]], [good[0][8:]+good[0][:8]], [good[0]+good[0][1:]],
                    [good[0][:17], good[0][16:]], [[[.2, .2], [.8, .8]]],
                    [[[.5, .1], [.1, .5], [.5, .9], [.9, .5], [.5, .1]]]):
            self.assertFalse(m.zero_trace(bad))
        for bad in ([[[float('nan'), .1], [.5, .9]]], [[[True, .1], [.5, .9]]], [[[2, .1], [.5, .9]]]):
            with self.assertRaises(ApiError): m.zero_trace(bad)
        self.assertTrue(m.minus_trace([[[.2, .5], [.8, .5]]]))
        self.assertFalse(m.minus_trace([[[.8, .5], [.2, .5]]]))

    def test_trace_and_accessible_point_evidence_are_separate(self):
        good = cases()['subtract'][4][0]
        state = self.fresh('subtract', 4)
        self.apply('subtract', 4, state, 'submit', {**good, 'strokes': [good['strokes'][0][::-1]]})
        self.assertFalse(state['completed'])
        self.apply('subtract', 4, state, 'submit', {**good, 'mode': 'point', 'strokes': []})
        self.assertTrue(state['completed'])
        self.assertEqual(state['attempts'][-1]['writingEvidence'], 'unobserved')
        self.assertFalse(state['attempts'][-1]['screenTraceMatches'])
        zero = self.fresh('zero', 4)
        with self.assertRaises(ApiError): self.apply('zero', 4, zero, 'submit', {'mode': 'free', 'strokes': oval()})

    def test_reveal_without_submit_then_undo_cannot_claim_unexposed_first_prediction(self):
        for kind, page in m.PREDICTION_PAGES:
            state = self.fresh(kind, page); work = cases()[kind][page][0]
            self.apply(kind, page, state, 'work', work)
            self.assertEqual(state['exposureCount'], 1)
            self.apply(kind, page, state, 'undo', before_prediction(kind, page, work))
            self.apply(kind, page, state, 'predict', before_prediction(kind, page, work))
            self.assertEqual(state['firstPredictions']['task']['priorExposure'], 1)
            self.apply(kind, page, state, 'submit', work)
            self.assertEqual(state['exposureCount'], 2)
            self.assertEqual(state['firstPredictions']['task']['priorExposure'], 1)

    def test_wrong_math_and_directions_cannot_complete(self):
        bad_cases = [
            ('subtract', 3, {**cases()['subtract'][3][0], 'links': {**mapped(), 'whole': 'remaining'}}),
            ('subtract', 5, {'removed': [1], 'remaining': [2, 3, 4, 5], 'pairs': [[2, 1], [3, 2], [4, 3]]}),
            ('subtract', 6, {**cases()['subtract'][6][0], 'equation': eq(3, 2, 3)}),
            ('subtract', 7, {**cases()['subtract'][7][0], 'counted': [1, 2]}),
            ('subtract', 8, {**cases()['subtract'][8][0], 'removed': [2, 3], 'remaining': [1, 4, 5]}),
            ('zero', 2, {**cases()['zero'][2][0], 'meaning': 'origin'}),
            ('zero', 3, {**cases()['zero'][3][0], 'order': [1, 0, 2, 3, 4, 5]}),
            ('zero', 5, {**cases()['zero'][5][0], 'links': {**mapped(), 'change': 'before'}}),
            ('zero', 8, {**cases()['zero'][8][0], 'removed': [1], 'remaining': [2], 'equation': eq(2, 1, 1)}),
            ('zero', 9, {**cases()['zero'][9][0], 'operator': 'subtract'}),
            ('zero', 10, {**cases()['zero'][10][0], 'executed': False}),
        ]
        for kind, page, work in bad_cases:
            state = self.fresh(kind, page); self.apply(kind, page, state, 'submit', work)
            self.assertFalse(state['completed'], (kind, page))
            self.assertFalse(state['attempts'][-1]['correct'], (kind, page))

    def test_zero_counterexample_has_finite_varied_conditions_not_a_pass_flag(self):
        state = self.fresh('zero', 11)
        for operator in ('add', 'subtract'):
            self.apply('zero', 11, state, 'submit', event(2, operator))
        self.assertFalse(state['completed'])
        illegal = {**event(2, 'add'), 'changed': [3], 'remaining': [1, 2, 3], 'equation': eq(2, 1, 3)}
        self.apply('zero', 11, state, 'submit', illegal)
        self.assertFalse(state['attempts'][-1]['correct'])
        self.apply('zero', 11, state, 'submit', event(4, 'add'))
        self.assertTrue(state['completed'])

    def test_zero_p11_independent_trials_survive_a_later_draft_and_retry(self):
        state = self.fresh('zero', 11)
        add = event(2, 'add')
        subtract = event(3, 'subtract')
        self.apply('zero', 11, state, 'submit', add)
        first = deepcopy(state['firstAttempts']['add'])
        # This is the actual interaction order: changing the total first still
        # leaves the previous operator selected, followed by switching it.
        self.apply('zero', 11, state, 'work', {**event(3, 'add'), 'executed': False})
        self.apply('zero', 11, state, 'work', {**subtract, 'executed': False})
        self.apply('zero', 11, state, 'submit', subtract)
        self.assertTrue(state['completed'])
        self.assertEqual(state['passedTasks'], ['add', 'subtract', 'different-n'])
        attempts = deepcopy(state['attempts'])
        self.apply('zero', 11, state, 'retry', {**event(4, 'add'), 'executed': False})
        self.apply('zero', 11, state, 'submit', {**event(4, 'add'), 'executed': False})
        self.assertTrue(state['completed'])
        self.assertEqual(state['attempts'][:2], attempts)
        self.assertEqual(state['firstAttempts']['add'], first)
        self.assertFalse(state['attempts'][-1]['correct'])
        self.assertEqual(state['retryCount'], 1)
        self.assertEqual(state['support'], {'replay': 0, 'hint': 0, 'demonstration': 0})

    def test_zero_p11_requires_real_correct_varied_trials_and_honors_trial_window(self):
        state = self.fresh('zero', 11)
        self.apply('zero', 11, state, 'submit', event(2, 'add'))
        self.apply('zero', 11, state, 'submit', event(2, 'subtract'))
        self.assertFalse(state['completed'])
        self.apply('zero', 11, state, 'work', event(3, 'subtract'))
        self.assertFalse(state['completed'])  # A draft is not a trial.
        self.apply('zero', 11, state, 'submit', {**event(3, 'subtract'), 'executed': False})
        self.assertFalse(state['completed'])  # Failed submit is not a trial success.
        self.apply('zero', 11, state, 'submit', event(3, 'subtract'))
        self.assertTrue(state['completed'])
        # The authored page retains its latest 64 trials.
        for _ in range(64):
            self.apply('zero', 11, state, 'submit', event(2, 'add'))
        self.assertFalse(state['completed'])
        self.apply('zero', 11, state, 'submit', event(3, 'subtract'))
        self.assertTrue(state['completed'])

    def test_zero_p11_older_session_projects_consistently_without_mutating_reads(self):
        rel, progress = release('zero'), {}
        def op(seq, name, work, page=11):
            return ci.apply_operation(progress, release=rel, scene_index=page-1, scene_id=f'scene-p{page}',
                contract_sha256=rel['interactionCompletionContract']['sha256'], operation_id=f'op-{seq}',
                operation={'name': name, 'work': work})
        op(1, 'submit', event(2, 'add'))
        op(2, 'work', {**event(3, 'add'), 'executed': False})
        op(3, 'work', {**event(3, 'subtract'), 'executed': False})
        op(4, 'submit', event(3, 'subtract'))
        # Replicate the old backend's faulty summary without changing evidence.
        scenes = progress['courseInteraction']['scenes']
        for name, page in scenes.items():
            if name != 'scene-p11':
                page['completed'] = True
        p11 = scenes['scene-p11']
        p11['passedTasks'] = ['subtract', 'different-n']
        p11['completed'] = False
        p11['phase'] = 'playing'
        before = deepcopy(progress)
        recovered = ci.recovery_state(progress, rel)['scenes']['scene-p11']
        self.assertTrue(recovered['completed'])
        self.assertTrue(ci.completion_ready(progress, rel))
        duplicate = op(4, 'submit', event(3, 'subtract'))
        self.assertTrue(duplicate['completed'])
        self.assertTrue(duplicate['allActivitiesCompleted'])
        self.assertEqual(progress, before)  # GET and duplicate are both read-only.
        old_evidence = {k: deepcopy(p11[k]) for k in ('attempts', 'firstAttempts', 'history', 'support')}
        op(5, 'work', cases()['zero'][1][0], page=1)
        p11 = progress['courseInteraction']['scenes']['scene-p11']
        self.assertTrue(p11['completed'])
        self.assertEqual({k: p11[k] for k in old_evidence}, old_evidence)

    def test_zero_p11_invalid_stored_success_fails_closed_and_does_not_write(self):
        rel = release('zero')
        state = ci.initial(rel['interactionCompletionContract'])
        progress = {'courseInteraction': state}
        for page in state['scenes'].values():
            page['completed'] = True
        p11 = state['scenes']['scene-p11']
        p11['attempts'] = [{'task': 'add', 'correct': True,
                            'work': {**event(2, 'add'), 'executed': False}}]
        before = deepcopy(progress)
        self.assertFalse(ci.completion_ready(progress, rel))
        with self.assertRaises(ApiError):
            ci.recovery_state(progress, rel)
        with self.assertRaises(ApiError):
            ci.apply_operation(progress, release=rel, scene_index=10, scene_id='scene-p11',
                contract_sha256=rel['interactionCompletionContract']['sha256'], operation_id='bad',
                operation={'name': 'submit', 'work': event(3, 'subtract')})
        self.assertEqual(progress, before)

    def test_zero_p11_all_attempts_match_ordered_submit_history_and_are_revalidated(self):
        base = self.fresh('zero', 11)
        add, subtract = event(2, 'add'), event(3, 'subtract')
        self.apply('zero', 11, base, 'submit', add)
        self.apply('zero', 11, base, 'hint', add)
        self.apply('zero', 11, base, 'submit', {**subtract, 'executed': False})
        self.apply('zero', 11, base, 'submit', subtract)
        self.assertTrue(base['completed'])
        self.assertEqual([a['correct'] for a in base['attempts']], [True, False, True])
        before = deepcopy(base)
        m.reconcile_zero_p11_trials(base)
        self.assertEqual(base, before)  # Never changes attempts, support, or history.
        mutations = [
            lambda s: s['attempts'][0].update(correct=False),
            lambda s: s['attempts'][1].update(correct=True),
            lambda s: s['attempts'][1]['work'].update(executed=True),
            lambda s: s['attempts'][1].update(task='add'),
            lambda s: s['attempts'][1].update(workVersion=500),
            lambda s: s['attempts'][1]['support'].update(hint=0),
            lambda s: s['attempts'][1]['support'].update(hint=True),
            lambda s: s['attempts'][1].update(workVersion=True),
            lambda s: s['history'].pop(0),
            lambda s: s['history'].append(deepcopy(s['history'][-1])),
            lambda s: s['attempts'].reverse(),
            lambda s: s['history'][-1].update(name='invented'),
        ]
        for mutate in mutations:
            state = deepcopy(before)
            mutate(state)
            altered = deepcopy(state)
            with self.subTest(mutator=mutate), self.assertRaises(ApiError):
                m.reconcile_zero_p11_trials(state)
            self.assertEqual(state, altered)  # Reject atomically.

    def test_zero_p11_validates_attempts_beyond_retained_trial_window(self):
        state = self.fresh('zero', 11)
        for _ in range(65):
            self.apply('zero', 11, state, 'submit', event(2, 'add'))
        self.apply('zero', 11, state, 'submit', event(3, 'subtract'))
        self.assertTrue(state['completed'])
        # The old out-of-window attempt must still match its server history.
        state['attempts'][0]['support']['hint'] = 1
        before = deepcopy(state)
        with self.assertRaises(ApiError):
            m.reconcile_zero_p11_trials(state)
        self.assertEqual(state, before)

    def test_zero_p11_bad_history_fails_completion_recovery_and_new_operation(self):
        rel, progress = release('zero'), {}
        def op(identifier, work):
            return ci.apply_operation(progress, release=rel, scene_index=10, scene_id='scene-p11',
                contract_sha256=rel['interactionCompletionContract']['sha256'], operation_id=identifier,
                operation={'name': 'submit', 'work': work})
        op('first', event(2, 'add'))
        op('last', event(3, 'subtract'))
        for page in progress['courseInteraction']['scenes'].values():
            page['completed'] = True
        progress['courseInteraction']['scenes']['scene-p11']['history'][0]['workVersion'] += 1
        before = deepcopy(progress)
        self.assertFalse(ci.completion_ready(progress, rel))
        with self.assertRaises(ApiError): ci.recovery_state(progress, rel)
        with self.assertRaises(ApiError): op('last', event(3, 'subtract'))
        with self.assertRaises(ApiError): op('new', event(4, 'add'))
        self.assertEqual(progress, before)

    def test_explanation_binds_real_previous_saved_story_and_invalidates_stale_record(self):
        for kind, creation, explanation in [('subtract', 11, 12), ('zero', 13, 14)]:
            work = cases()[kind][explanation][0]; state = self.fresh(kind, explanation)
            with self.assertRaises(ApiError): self.apply(kind, explanation, state, 'submit', work)
            prior = self.fresh(kind, creation)
            self.apply(kind, creation, prior, 'submit', cases()[kind][creation][0])
            self.apply(kind, creation, prior, 'hint', cases()[kind][creation][0])
            with self.assertRaises(ApiError):
                self.apply(kind, explanation, state, 'submit', {**work, 'sourceWorkSha256': '0'*64}, prior)
            different = subtract_story(5, [2, 3]) if kind == 'subtract' else zero_story('no-arrivals', 2)
            with self.assertRaises(ApiError):
                self.apply(kind, explanation, state, 'submit', {**work, 'story': different,
                    'saved': deepcopy(different), 'storyVersion': 2, 'recordVersion': 2}, prior)
            self.apply(kind, explanation, state, 'submit', {**work, 'storyVersion': 2}, prior)
            self.assertFalse(state['completed'])
            self.apply(kind, explanation, state, 'submit', work, prior)
            self.assertTrue(state['completed'])
            self.assertEqual(state['attempts'][-1]['sourceEvidence']['support']['hint'], 1)
            self.assertEqual(state['oralSkill'], 'unobserved'); self.assertEqual(state['paperHandwriting'], 'unobserved')

    def test_transport_duplicate_is_idempotent_conflict_rejected(self):
        rel, progress = release('subtract'), {}
        args = dict(release=rel, scene_index=1, scene_id='scene-p2',
                    contract_sha256=rel['interactionCompletionContract']['sha256'], operation_id='same')
        op = {'name': 'submit', 'work': cases()['subtract'][2][0]}
        ci.apply_operation(progress, operation=op, **args)
        ci.apply_operation(progress, operation=op, **args)
        self.assertEqual(len(progress['courseInteraction']['scenes']['scene-p2']['attempts']), 1)
        with self.assertRaises(ApiError): ci.apply_operation(progress, operation={**op, 'name': 'hint'}, **args)

    def test_editing_saved_source_invalidates_later_explanation_without_erasing_attempts(self):
        for kind, creation, explanation in [('subtract', 11, 12), ('zero', 13, 14)]:
            rel, progress = release(kind), {}
            def op(page, identifier, work):
                ci.apply_operation(progress, release=rel, scene_index=page-1, scene_id=f'scene-p{page}',
                    contract_sha256=rel['interactionCompletionContract']['sha256'], operation_id=identifier,
                    operation={'name': 'submit', 'work': work})
            op(creation, 'create', cases()[kind][creation][0])
            op(explanation, 'explain', cases()[kind][explanation][0])
            self.assertTrue(progress['courseInteraction']['scenes'][f'scene-p{explanation}']['completed'])
            story = subtract_story(5, [1, 4]) if kind == 'subtract' else zero_story('no-arrivals', 2)
            op(creation, 'edit', {'story': story, 'saved': deepcopy(story)})
            explanation_state = progress['courseInteraction']['scenes'][f'scene-p{explanation}']
            self.assertFalse(explanation_state['completed'])
            self.assertEqual(len(explanation_state['attempts']), 1)


if __name__ == '__main__':
    unittest.main()
