import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from copy import deepcopy
from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from courseware.kit import slides
from courseware.tools import check, package, verify, verify_delta


class VerifyDeltaTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=os.environ['MIRA_TASK_TMPDIR'])
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.prior_media, self.media = self.root / 'prior', self.root / 'current'
        for path in (self.prior_media, self.media):
            path.mkdir()
            (path / 'option.png').write_bytes(b'one original picture')
        self.notes = {'objectives': ['sort by color', 'count objects'], 'keyPoint': 'use the clue'}
        self.prior = {
            'stage': {'id': 'stage', 'name': 'Review', 'createdAt': 10},
            'scenes': [
                {'id': 'scene-a', 'type': 'slide', 'title': 'Color', 'actions': [
                    {'id': 'a', 'type': 'speech', 'text': 'Look at the red card.'},
                    {'id': 'b', 'type': 'speech', 'text': 'Sort cards by color.'},
                ]},
                {'id': 'scene-b', 'type': 'slide', 'title': 'Count', 'actions': [
                    {'id': 'c', 'type': 'speech', 'text': 'Count every object once.'},
                ]},
                {'id': 'scene-quiz', 'type': 'quiz', 'title': 'Check', 'actions': [],
                 'content': {'questions': [{
                     'id': 'q', 'question': 'Which is one?', 'answer': ['A'], 'skill': 'counting',
                     'analysis': 'One dot.', 'options': [
                         {'label': 'one', 'value': 'A'}, {'label': 'two', 'value': 'B'},
                     ], 'optionVisuals': {'A': {
                         'kind': 'image', 'src': '/api/classroom-media/stage/media/option.png',
                     }},
                 }]}},
            ],
        }
        self.body = deepcopy(self.prior)
        self.body['scenes'][0]['actions'][0]['text'] = 'Look at the red card beside the blue card.'
        self.verdicts = [
            {'id': 'a', 'ok': True, 'issue': None},
            {'id': 'b', 'ok': True, 'issue': 'verbatim old verdict field'},
            {'id': 'c', 'ok': True, 'issue': None},
            {'id': 'q', 'solved': 'A', 'skillMatchesObjectives': True, 'picturesMatch': True, 'issue': None},
            {'id': 'q', 'analysisOk': True, 'issue': None},
            {'id': 'goal-1', 'verdict': 'taught', 'taughtAt': '1', 'issue': None},
            {'id': 'goal-2', 'verdict': 'taught', 'taughtAt': '2', 'issue': None},
            {'id': 'keyPoint', 'verdict': 'weak', 'taughtAt': '2', 'issue': 'Explain the clue.'},
        ]
        self.fresh = [
            {'id': 'a', 'ok': True, 'issue': None},
            {'id': 'goal-1', 'verdict': 'taught', 'taughtAt': '1', 'issue': None},
            {'id': 'keyPoint', 'verdict': 'taught', 'taughtAt': '2', 'issue': None},
        ]

    def baseline(self):
        requests = verify.build_requests(self.prior, self.notes, media=self.prior_media, teaching=True)
        value = {'schemaVersion': verify.EVIDENCE_SCHEMA,
                 'inputSha256': verify.evidence_input_hash(self.prior, requests),
                 'reviewedBodySha256': verify.body_hash(self.prior), 'notesSha256': verify.body_hash(self.notes),
                 'model': verify.VERIFIER_MODEL, 'effort': verify.VERIFIER_EFFORT,
                 'ranAt': '2026-11-10T15:00:00+00:00', 'verdicts': self.verdicts}
        raw = (json.dumps(value, indent=2) + '\n').encode()
        return raw, sha256(raw).hexdigest()

    def plan(self, **changes):
        raw, pin = self.baseline()
        fields = dict(body=self.body, notes=self.notes, media=self.media, prior_body=self.prior,
                      prior_notes=self.notes, prior_media=self.prior_media, prior_evidence=raw,
                      prior_evidence_sha256=pin)
        fields.update(changes)
        return verify_delta.plan_review(**fields)

    @staticmethod
    def selected(plan):
        return [(r['kind'], [x['id'] for x in r['items']]) for r in plan.requests]

    def run_fixture(self, plan=None):
        runner = Mock(return_value=self.fresh)
        with patch.object(verify, 'run_requests', runner):
            receipt, evidence = verify_delta.run_review(plan or self.plan(), jobs=1)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[0], (plan or self.plan()).requests)
        return receipt, evidence

    def test_reuses_exact_old_verdicts_and_reviews_affected_and_previously_weak_targets(self):
        plan = self.plan()
        self.assertEqual(self.selected(plan), [('speech', ['a']), ('teaching', ['goal-1', 'keyPoint'])])
        receipt, evidence = self.run_fixture(plan)
        self.assertEqual(receipt['schemaVersion'], 'mira.courseware.verification.v1')
        self.assertEqual(receipt['disagreements'], [])
        self.assertEqual((receipt['speechChecked'], receipt['questionsChecked'], receipt['goalsChecked']), (3, 1, 3))
        self.assertEqual(evidence['deltaVerdicts'], self.fresh)
        for kind, ident, expected in [
            ('speech', 'b', self.verdicts[1]), ('question_solve', 'q', self.verdicts[3]),
            ('question_analysis', 'q', self.verdicts[4]), ('teaching', 'goal-2', self.verdicts[6]),
        ]:
            self.assertEqual(plan.reused[(kind, ident)], expected)

    def test_old_input_and_old_evidence_must_match_before_a_plan_exists(self):
        raw, pin = self.baseline()
        prior = deepcopy(self.prior)
        prior['scenes'][0]['actions'][0]['text'] = 'Changed historical text.'
        with self.assertRaisesRegex(ValueError, 'prior body'):
            self.plan(prior_body=prior)
        with self.assertRaisesRegex(ValueError, 'prior evidence SHA'):
            self.plan(prior_evidence=raw + b' ', prior_evidence_sha256=pin)
        with self.assertRaisesRegex(ValueError, 'official notes'):
            self.plan(notes={**self.notes, 'keyPoint': 'A different clue'})
        (self.prior_media / 'option.png').write_bytes(b'changed historical picture')
        with self.assertRaisesRegex(ValueError, 'prior verifier inputs'):
            self.plan(prior_evidence=raw, prior_evidence_sha256=pin)

    def test_current_picture_bytes_select_both_quiz_kinds(self):
        (self.media / 'option.png').write_bytes(b'a new picture under the same filename')
        selected = dict(self.selected(self.plan()))
        self.assertEqual(selected['question_solve'], ['q'])
        self.assertEqual(selected['question_analysis'], ['q'])

    def test_old_rejection_is_never_reused_and_bad_scene_reference_requires_review(self):
        self.verdicts[1]['ok'] = False
        self.verdicts[1]['issue'] = 'Needs correction.'
        self.verdicts[6]['taughtAt'] = '2 and elsewhere'
        selected = dict(self.selected(self.plan()))
        self.assertEqual(selected['speech'], ['a', 'b'])
        self.assertEqual(selected['teaching'], ['goal-1', 'goal-2', 'keyPoint'])

    def test_removing_a_cited_speech_rechecks_the_goal(self):
        self.body['scenes'][1]['actions'].clear()
        self.assertIn('goal-2', dict(self.selected(self.plan()))['teaching'])

    def test_cli_rejects_unapproved_current_input_before_claim_or_runner(self):
        raw, pin = self.baseline()
        prior, current, notes, proof = (self.root / name for name in ('prior.json', 'next.json', 'notes.json', 'prior-proof.json'))
        for path, data in ((prior, self.prior), (current, self.body), (notes, self.notes)):
            path.write_text(json.dumps(data))
        proof.write_bytes(raw)
        receipt, evidence = self.root / 'receipt.json', self.root / 'evidence.json'
        args = [
            'run', '--body', str(current), '--notes', str(notes), '--media', str(self.media),
            '--prior-body', str(prior), '--prior-media', str(self.prior_media),
            '--prior-evidence', str(proof), '--prior-evidence-sha256', pin,
            '--out', str(receipt), '--save-evidence', str(evidence), '--expected-input-sha256', '0' * 64,
        ]
        errors = StringIO()
        with patch.object(verify, 'run_requests') as runner, redirect_stderr(errors), self.assertRaises(SystemExit) as status:
            verify_delta.main(args)
        self.assertEqual(status.exception.code, 2)
        self.assertIn('Current input does not match the approved SHA', errors.getvalue())
        runner.assert_not_called()
        self.assertFalse(receipt.exists())
        self.assertFalse(evidence.exists())

    def test_ignores_only_proven_derived_stage_names_and_canvas_ids(self):
        for body, stage in ((self.prior, 'prior-stage'), (self.body, 'next-stage')):
            body['stage']['id'] = stage
            for scene in body['scenes']:
                scene['stageId'] = stage
            slide = body['scenes'][1]
            slide['content'] = {'canvas': slides.canvas([{
                'id': 'exhibit', 'type': 'image', 'src': f'/api/classroom-media/{stage}/media/option.png',
            }])}
            quiz = body['scenes'][2]['content']['questions'][0]
            quiz['optionVisuals']['A']['src'] = f'/api/classroom-media/{stage}/media/option.png'
        selected = dict(self.selected(self.plan()))
        self.assertEqual(selected['teaching'], ['goal-1', 'keyPoint'])
        self.assertNotIn('question_solve', selected)
        canvas = self.body['scenes'][1]['content']['canvas']
        canvas['id'] = 'not-the-compiler-id'
        self.assertIn('goal-2', dict(self.selected(self.plan()))['teaching'])
        canvas['elements'][0]['src'] = '/api/classroom-media/next-stage/media/different.png'
        self.body['scenes'][1]['content']['canvas'] = slides.canvas(canvas['elements'])
        self.assertIn('goal-2', dict(self.selected(self.plan()))['teaching'])

    def test_replay_works_without_original_media_and_rejects_tampering(self):
        receipt, evidence = self.run_fixture()
        (self.prior_media / 'option.png').unlink()
        voiced = deepcopy(self.body)
        voiced['stage']['updatedAt'] = 20
        voiced['scenes'][0]['actions'][0].update(audioId='audio', audioUrl='url')
        replayed = verify_delta.replay(voiced, self.notes, self.media, evidence)
        self.assertEqual(replayed['bodySha256'], verify.body_hash(voiced))
        self.assertEqual(replayed['verifier'], receipt['verifier'])
        damaged = deepcopy(evidence)
        damaged['deltaVerdicts'].append(self.verdicts[1])
        with self.assertRaises(ValueError):
            verify_delta.replay(voiced, self.notes, self.media, damaged)
        damaged = deepcopy(evidence)
        damaged['prior']['pictures']['option.png'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'prior verifier inputs'):
            verify_delta.replay(voiced, self.notes, self.media, damaged)
        (self.media / 'option.png').write_bytes(b'current picture has changed')
        with self.assertRaisesRegex(ValueError, 'current verifier inputs'):
            verify_delta.replay(voiced, self.notes, self.media, evidence)

    def test_package_rejects_arbitrary_combination_even_if_sidecar_hash_matches(self):
        receipt, evidence = self.run_fixture()
        source, work = self.root / 'source', self.root / 'work'
        source.mkdir()
        work.mkdir()
        self.media.rename(work / 'media')
        for name, data in {
            'official-notes.json': self.notes, 'brief.json': {'goals': self.notes['objectives']},
        }.items():
            (source / name).write_text(json.dumps(data))
        for name, data in {
            'body.json': self.body, 'roster.json': {}, 'audit-receipt.json': {},
            'play-receipt.json': {}, 'draft.json': {'grade': 1},
            'verification.json': receipt, package.VERIFICATION_EVIDENCE: evidence,
        }.items():
            (work / name).write_text(json.dumps(data))

        def pack(name):
            return package.package_lesson(source, work, self.root / name, edition_id='e', revision_id='r',
                                          node_id='n', teacher_code='teacher', author_models=['author'])

        with patch.object(check, 'check_classroom', return_value=[]):
            pack('good')
            evidence['deltaVerdicts'].pop()
            receipt['reusedEvidence']['sha256'] = verify.body_hash(evidence)
            (work / package.VERIFICATION_EVIDENCE).write_text(json.dumps(evidence))
            (work / 'verification.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(package.PackageError, 'verification_evidence_changed'):
                pack('bad')
        self.assertFalse((self.root / 'bad').exists())

    def append_fixture(self, *, extra_failure=False):
        second_plan = self.plan()
        second_verdicts = deepcopy(self.fresh)
        second_verdicts[1].update(verdict='weak', issue='Show the color clue aloud.')
        second_verdicts[2].update(taughtAt='1,2')
        if extra_failure:
            second_verdicts[2].update(verdict='weak', issue='Explain the clue again.')
        with patch.object(verify_delta, '_run_requests', return_value=second_verdicts):
            _, second = verify_delta.run_review(second_plan)
        prior = json.dumps(second, ensure_ascii=False, indent=2).encode()
        candidate = deepcopy(self.body)
        candidate['scenes'][0]['actions'][0]['text'] += ' Follow the red edge.'
        candidate['scenes'][0]['actions'][1]['text'] += ' Follow me once.'
        return candidate, prior

    def append_fields(self, candidate, prior):
        requests = verify.build_requests(candidate, self.notes, media=self.media, teaching=True)
        prior_pin = sha256(prior).hexdigest()
        auth = {'schemaVersion': verify_delta.APPEND_AUTHORIZATION_SCHEMA, 'confirmedBy': 'owner',
                'userQuote': 'Review these two additions and this learning goal once.',
                'confirmedAt': json.loads(prior)['ranAt'], 'priorDeltaSha256': prior_pin,
                'canonicalBodySha256': verify.body_hash(verify._evidence_body(candidate)),
                'inputSha256': verify.evidence_input_hash(candidate, requests),
                'speechIds': ['a', 'b'], 'goalId': 'goal-1'}
        return dict(body=candidate, notes=self.notes, media=self.media, prior_body=self.body,
                    prior_notes=self.notes, prior_media=self.prior_media, prior_evidence=prior,
                    prior_evidence_sha256=prior_pin, append_authorization=auth)

    def test_append_only_uses_real_second_round_and_replays_for_packaging(self):
        body, prior = self.append_fixture()
        fields = self.append_fields(body, prior)
        plan = verify_delta.plan_review(**fields)
        self.assertEqual(self.selected(plan), [('speech', ['a', 'b']), ('teaching', ['goal-1'])])
        self.assertEqual(plan.reused['teaching', 'keyPoint']['taughtAt'], '1,2')
        self.assertFalse(any(request['images'] for request in plan.requests))
        self.assertIn('Count every object once.', plan.requests[-1]['prompt'])
        new_verdicts = [deepcopy(self.verdicts[i]) for i in (0, 1, 5)]
        with patch.object(verify_delta, '_run_requests', return_value=new_verdicts) as runner:
            receipt, evidence = verify_delta.run_review(plan)
        runner.assert_called_once()
        self.assertEqual(receipt['disagreements'], [])
        self.assertEqual(evidence['appendAuthorization'], fields['append_authorization'])
        self.assertEqual(verify_delta.replay(body, self.notes, self.media, evidence), receipt)

        voiced = deepcopy(body)
        voiced['scenes'][0]['actions'][0].update(audioId='voice-id', audioUrl='voice-url')
        voiced_receipt = verify_delta.replay(voiced, self.notes, self.media, evidence)
        self.assertEqual(voiced_receipt['bodySha256'], verify.body_hash(voiced))
        (self.root / package.VERIFICATION_EVIDENCE).write_text(json.dumps(evidence))
        # The package uses work/media; expose the already verified fixture under that normal name.
        self.media.rename(self.root / 'media')
        package._check_verification_evidence(self.root, voiced, self.notes, voiced_receipt)
        voiced_receipt['goalsChecked'] += 1
        with self.assertRaisesRegex(package.PackageError, 'does not reconstruct'):
            package._check_verification_evidence(self.root, voiced, self.notes, voiced_receipt)

    def test_append_only_rejects_deletion_replacement_or_other_content_changes(self):
        body, prior = self.append_fixture()
        for change in ('remove', 'replace', 'empty', 'third-speech', 'quiz', 'title'):
            with self.subTest(change=change):
                candidate = deepcopy(body)
                actions = candidate['scenes'][0]['actions']
                if change == 'remove':
                    actions.pop()
                elif change == 'replace':
                    actions[0]['text'] = 'Replace the approved prefix.'
                elif change == 'empty':
                    actions[0]['text'] = self.body['scenes'][0]['actions'][0]['text'] + ' '
                elif change == 'third-speech':
                    candidate['scenes'][1]['actions'][0]['text'] += ' An unapproved sentence.'
                elif change == 'quiz':
                    candidate['scenes'][2]['content']['questions'][0]['analysis'] = 'Different analysis.'
                else:
                    candidate['scenes'][0]['title'] = 'Different page title.'
                with self.assertRaisesRegex(ValueError, 'Append-only review'):
                    verify_delta.plan_review(**self.append_fields(candidate, prior))

    def test_append_only_rejects_wrong_authority_extra_unresolved_item_and_image_changes(self):
        body, prior = self.append_fixture()
        fields = self.append_fields(body, prior)
        for field in ('priorDeltaSha256', 'inputSha256', 'canonicalBodySha256', 'confirmedBy', 'userQuote'):
            with self.subTest(field=field):
                invalid = {**fields['append_authorization'], field: ''}
                with self.assertRaisesRegex(ValueError, 'authorization does not match'):
                    verify_delta.plan_review(**{**fields, 'append_authorization': invalid})
        with self.assertRaisesRegex(ValueError, 'scope comes exclusively'):
            verify_delta.plan_review(**fields, extra_goals=('keyPoint',))
        with self.assertRaisesRegex(ValueError, 'original first-round'):
            verify_delta.plan_review(**{**fields, 'append_authorization': None})
        bad_body, bad_prior = self.append_fixture(extra_failure=True)
        with self.assertRaisesRegex(ValueError, 'only unresolved prior item'):
            verify_delta.plan_review(**self.append_fields(bad_body, bad_prior))
        (self.media / 'option.png').write_bytes(b'changed picture')
        with self.assertRaisesRegex(ValueError, 'unchanged quiz pictures'):
            verify_delta.plan_review(**self.append_fields(body, prior))

    def test_append_only_rejects_tampered_historical_or_current_request_and_records_disagreement(self):
        body, prior = self.append_fixture()
        fields = self.append_fields(body, prior)
        bad_prior = json.loads(prior)
        bad_prior['deltaRequestSha256'][0] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Delta requests do not match'):
            verify_delta.plan_review(**self.append_fields(body, json.dumps(bad_prior).encode()))
        plan = verify_delta.plan_review(**fields)
        verdicts = [deepcopy(self.verdicts[i]) for i in (0, 1, 5)]
        verdicts[-1].update(verdict='weak', issue='The new example still needs guidance.', taughtAt='无')
        with patch.object(verify_delta, '_run_requests', return_value=verdicts):
            receipt, evidence = verify_delta.run_review(plan)
        self.assertEqual([row['id'] for row in receipt['disagreements']], ['goal-1'])
        self.assertEqual(evidence['deltaVerdicts'][-1]['taughtAt'], '无')
        verdicts[-1].update(verdict='missing', issue='No model example.', taughtAt='')
        with patch.object(verify_delta, '_run_requests', return_value=verdicts):
            rejected, saved = verify_delta.run_review(plan)
        self.assertEqual([row['id'] for row in rejected['disagreements']], ['goal-1'])
        self.assertEqual(saved['deltaVerdicts'][-1]['taughtAt'], '')
        tampered = deepcopy(evidence)
        tampered['deltaRequestSha256'][0] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'requests or timestamp'):
            verify_delta.replay(body, self.notes, self.media, tampered)
        tampered = deepcopy(evidence)
        tampered['deltaVerdicts'][-1].update(verdict='taught', issue=None, taughtAt='2')
        with self.assertRaisesRegex(ValueError, 'invalid teaching citations'):
            verify_delta.replay(body, self.notes, self.media, tampered)
        save_received = Mock()
        with patch.object(verify_delta, '_run_requests', return_value=tampered['deltaVerdicts']):
            with self.assertRaisesRegex(ValueError, 'invalid teaching citations'):
                verify_delta.run_review(plan, save_received=save_received)
        save_received.assert_called_once()
        self.assertEqual(save_received.call_args.args[0]['deltaVerdicts'], tampered['deltaVerdicts'])
        plan.requests[0]['prompt'] += ' Changed after the approved plan.'
        with patch.object(verify_delta, '_run_requests') as runner:
            with self.assertRaisesRegex(ValueError, 'plan changed before submission'):
                verify_delta.run_review(plan)
        runner.assert_not_called()

    def test_append_only_cli_claim_prevents_a_second_submission(self):
        body, prior = self.append_fixture()
        fields = self.append_fields(body, prior)
        candidate, previous, notes, evidence, owner = (
            self.root / name for name in ('next.json', 'previous.json', 'notes.json', 'old-delta.json', 'owner.json'))
        for path, data in ((candidate, body), (previous, self.body), (notes, self.notes),
                           (owner, fields['append_authorization'])):
            path.write_text(json.dumps(data))
        evidence.write_bytes(prior)
        auth = fields['append_authorization']
        args = ['run', '--body', str(candidate), '--media', str(self.media), '--notes', str(notes),
                '--prior-body', str(previous), '--prior-media', str(self.prior_media),
                '--prior-evidence', str(evidence), '--prior-evidence-sha256', auth['priorDeltaSha256'],
                '--append-authorization', str(owner), '--expected-input-sha256', auth['inputSha256']]
        fresh = [deepcopy(self.verdicts[i]) for i in (0, 1, 5)]
        def output_args(name):
            return ['--out', str(self.root / f'{name}-receipt.json'),
                    '--save-evidence', str(self.root / f'{name}-evidence.json')]
        with patch.object(verify_delta, '_run_requests', return_value=fresh) as runner:
            self.assertEqual(verify_delta.main(args + output_args('first')), 0)
            with redirect_stderr(StringIO()) as errors, self.assertRaises(SystemExit) as status:
                verify_delta.main(args + output_args('second'))
            self.assertEqual(status.exception.code, 2)
            self.assertIn('already been claimed', errors.getvalue())
        runner.assert_called_once()
        self.assertFalse((self.root / 'second-evidence.json').exists())

    def presentation_fixture(self):
        art = b'content-addressed slide picture'
        self.slide_picture = 'pic-' + sha256(art).hexdigest() + '.png'
        for media in (self.prior_media, self.media):
            (media / self.slide_picture).write_bytes(art)
        for body in (self.prior, self.body):
            for n, scene in enumerate(body['scenes'][:2]):
                scene['content'] = {'canvas': slides.canvas([
                    {'id': 'left', 'type': 'text', 'content': 'Left'},
                    {'id': 'right', 'type': 'text', 'content': 'Right'},
                    {'id': 'illustration', 'type': 'image',
                     'src': '/api/classroom-media/stage/media/' + self.slide_picture},
                ])}
                scene['actions'][0:0] = [
                    {'id': f'{n}-left', 'type': 'spotlight', 'elementId': 'left'},
                    {'id': f'{n}-right', 'type': 'spotlight', 'elementId': 'right'},
                ]
        return self.run_fixture()

    @staticmethod
    def swap(body, index=0):
        result = deepcopy(body)
        first, second = result['scenes'][index]['actions'][:2]
        first['elementId'], second['elementId'] = second['elementId'], first['elementId']
        return result

    def test_rebinds_only_a_proven_in_scene_spotlight_swap_to_the_new_body(self):
        prior_receipt, evidence = self.presentation_fixture()
        original_proof = deepcopy(evidence)
        current = self.swap(self.body)
        with patch.object(verify, 'run_requests') as runner:
            receipt = verify_delta.replay(current, self.notes, self.media, evidence)
            self.assertEqual(verify_delta.replay(self.body, self.notes, self.media, evidence), prior_receipt)
        runner.assert_not_called()
        self.assertEqual(evidence, original_proof)
        self.assertEqual(receipt['bodySha256'], verify.body_hash(current))
        self.assertNotEqual(receipt['bodySha256'], prior_receipt['bodySha256'])
        self.assertEqual(receipt['disagreements'], prior_receipt['disagreements'])
        self.assertEqual(receipt['reusedEvidence']['sha256'], prior_receipt['reusedEvidence']['sha256'])
        self.assertEqual(receipt['reusedEvidence']['presentationRebind']['sceneId'], 'scene-a')

        work = self.root / 'work'
        work.mkdir()
        self.media.rename(work / 'media')
        (work / package.VERIFICATION_EVIDENCE).write_text(json.dumps(evidence))
        package._check_verification_evidence(work, current, self.notes, receipt)
        forged = deepcopy(receipt)
        forged['reusedEvidence']['presentationRebind']['sceneId'] = 'scene-b'
        with self.assertRaisesRegex(package.PackageError, 'verification_evidence_changed'):
            package._check_verification_evidence(work, current, self.notes, forged)

    def test_rebind_rejects_non_swap_deleted_invalid_and_cross_scene_actions(self):
        _, evidence = self.presentation_fixture()
        invalid = self.swap(self.body)
        invalid['scenes'][0]['actions'][0]['elementId'] = 'missing'
        deleted = self.swap(self.body)
        deleted['scenes'][0]['actions'].pop(0)
        reordered = self.swap(self.body)
        reordered['scenes'][0]['actions'].reverse()
        cross_scene = deepcopy(self.body)
        cross_scene['scenes'][0]['actions'][0]['elementId'] = 'right'
        cross_scene['scenes'][1]['actions'][1]['elementId'] = 'left'
        moved_both = self.swap(self.swap(self.body), index=1)
        other_field = self.swap(self.body)
        other_field['scenes'][0]['actions'][0]['type'] = 'laser'
        for altered in (invalid, deleted, reordered, cross_scene, moved_both, other_field):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                verify_delta.replay(altered, self.notes, self.media, evidence)

    def test_rebind_rejects_spoken_text_quiz_picture_and_original_proof_changes(self):
        _, evidence = self.presentation_fixture()
        narration = self.swap(self.body)
        narration['scenes'][0]['actions'][2]['text'] = 'Different spoken instructions.'
        quiz = self.swap(self.body)
        quiz['scenes'][2]['content']['questions'][0]['answer'] = ['B']
        altered_canvas = self.swap(self.body)
        altered_canvas['scenes'][0]['content']['canvas']['elements'][0]['content'] = 'Different visual text'
        for altered in (narration, quiz, altered_canvas):
            with self.assertRaises(ValueError):
                verify_delta.replay(altered, self.notes, self.media, evidence)
        broken = deepcopy(evidence)
        broken['deltaVerdicts'].pop()
        with self.assertRaises(ValueError):
            verify_delta.replay(self.swap(self.body), self.notes, self.media, broken)
        picture = self.media / self.slide_picture
        original = picture.read_bytes()
        picture.write_bytes(b'changed slide image under the same content-addressed name')
        with self.assertRaisesRegex(ValueError, 'Presentation media differs'):
            verify_delta.replay(self.swap(self.body), self.notes, self.media, evidence)
        picture.write_bytes(original)
        (self.media / 'option.png').write_bytes(b'changed quiz image')
        with self.assertRaises(ValueError):
            verify_delta.replay(self.swap(self.body), self.notes, self.media, evidence)
