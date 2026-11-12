import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from courseware.kit import page
from courseware.tools import package, verify, verify_presentation


_CSS = page.page('', '', '', 'K.game(K.gameTemplates.arcade({}));').split('<style>', 1)[1].split('</style>', 1)[0]
_OLD_TAG = '<div id="teacher-target" class="g-anchor" style="left:588px;top:89px;width:104px;height:74px"></div>'
_NEW_TAG = _OLD_TAG.replace('left:588px;top:89px', 'left:564px;top:3px')
_OLD_SPAN = ('<span id="teacher-target" class="g-anchor" aria-hidden="true" '
             'style="left:588px;top:89px;width:104px;height:74px"></span>')
_NEW_SPAN = _OLD_SPAN.replace('left:588px;top:89px', 'left:564px;top:3px')
_PLACEHOLDERS = tuple(f'<span id="game-{name}" aria-hidden="true"></span>'
                      for name in ('goal', 'player', 'target'))
_BODY_OPEN = '<div id="cv"><div id="play">'
_SCRIPT_END = '</script></body></html>'
_HANDOFF_KIND = verify_presentation.HANDOFF_CLEANUP
_WRAPPER = verify_presentation._HANDOFF_WRAPPER


class VerifyPresentationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('MIRA_TASK_TMPDIR'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.work = self.root / 'work'
        self.prior_media, self.media = self.root / 'old', self.work / 'media'
        self.prior_media.mkdir()
        self.media.mkdir(parents=True)
        self.picture = 'question.png'
        self.background = 'pic-' + sha256(b'registered image').hexdigest() + '.png'
        for media in (self.prior_media, self.media):
            (media / self.picture).write_bytes(b'quiz image')
            (media / self.background).write_bytes(b'registered image')
        self.notes = {'objectives': ['Identify the pictured target.']}
        html = ('<html><head><style>' + _CSS + '</style></head><body>' + _BODY_OPEN
                + '<div id="game-player" class="g-anchor"></div>' + _OLD_TAG + '</div></div>'
                + '<script>const image="/api/classroom-media/lesson/media/' + self.background
                + '";</script></body></html>')
        self.prior = {
            'stage': {'id': 'lesson', 'name': 'Review', 'createdAt': 100},
            'scenes': [
                {'id': 'activity', 'type': 'interactive', 'title': 'Find the card', 'content': {'html': html},
                 'actions': [
                     {'id': 'anchor', 'type': 'widget_highlight', 'target': '#teacher-target'},
                     {'id': 'say', 'type': 'speech', 'text': 'Find the round card.'},
                 ]},
                {'id': 'quiz', 'type': 'quiz', 'title': 'Check', 'actions': [], 'content': {'questions': [{
                    'id': 'q', 'question': 'Which card is round?', 'skill': 'shape', 'answer': ['A'],
                    'analysis': 'This card has a round edge.',
                    'options': [{'value': 'A', 'label': 'round'}, {'value': 'B', 'label': 'square'}],
                    'optionVisuals': {'A': {'kind': 'image', 'src': '/api/classroom-media/lesson/media/question.png'}},
                }]}},
            ],
        }
        self.body = self.change_html(self.prior, _OLD_TAG, _NEW_TAG)
        self.verdicts = [
            {'id': 'say', 'ok': True, 'issue': None},
            {'id': 'q', 'solved': 'A', 'skillMatchesObjectives': True, 'picturesMatch': True, 'issue': None},
            {'id': 'q', 'analysisOk': True, 'issue': None},
            {'id': 'goal-1', 'verdict': 'taught', 'taughtAt': '1', 'issue': None},
        ]

    @staticmethod
    def change_html(body, before, after):
        changed = deepcopy(body)
        changed['scenes'][0]['content']['html'] = changed['scenes'][0]['content']['html'].replace(before, after)
        return changed

    def baseline(self, body):
        requests = verify.build_requests(body, self.notes, media=self.prior_media, teaching=True)
        evidence = {
            'schemaVersion': verify.EVIDENCE_SCHEMA, 'inputSha256': verify.evidence_input_hash(body, requests),
            'reviewedBodySha256': verify.body_hash(body), 'notesSha256': verify.body_hash(self.notes),
            'model': verify.VERIFIER_MODEL, 'effort': verify.VERIFIER_EFFORT,
            'ranAt': '2026-11-10T15:00:00+00:00', 'verdicts': self.verdicts,
        }
        return (json.dumps(evidence, indent=2) + '\n').encode()

    def prove(self, body=None, prior=None, **changes):
        prior = self.prior if prior is None else prior
        raw = self.baseline(prior)
        fields = {'body': self.body if body is None else body, 'prior_body': prior,
                  'notes': self.notes, 'media': self.media, 'prior_media': self.prior_media,
                  'prior_evidence': raw, 'prior_evidence_sha256': sha256(raw).hexdigest()}
        fields.update(changes)
        return verify_presentation.create_proof(**fields)

    def span_bodies(self):
        prior = self.change_html(self.prior, _OLD_TAG, _OLD_SPAN)
        prior = self.change_html(prior, '<div id="game-player" class="g-anchor"></div>', ''.join(_PLACEHOLDERS))
        return prior, self.change_html(prior, _OLD_SPAN, _NEW_SPAN)

    def handoff_bodies(self, template='magnetMarbles'):
        prior = deepcopy(self.prior)
        scene = prior['scenes'][0]
        markup = ('<span id="game-player" aria-hidden="true"></span>'
                  '<span id="teacher-target" class="g-anchor" aria-hidden="true" '
                  'style="left:120px;top:90px;width:100px;height:80px"></span>')
        script = ('K.ready({title:"Find the card"});\n'
                  'const ids = {round: "round"};\n'
                  'const pairs = Object.keys(ids).map(key => [key, key]);\n'
                  f'K.game(K.gameTemplates.{template}({{\n'
                  f'art:{{backdrop:"/api/classroom-media/lesson/media/{self.background}"}}, pairs,\n'
                  '}));\n')
        scene['content']['html'] = page.page('Find the card', markup, '', script)
        scene['actions'].insert(0, {'id': 'begin', 'type': 'widget_setState',
                                    'state': {'demo': True, 'level': 1, 'pause': True}})
        scene['actions'].append({'id': 'handoff', 'type': 'widget_setState',
                                 'state': {'demo': False, 'level': 1, 'pause': False}})
        return prior, self.change_html(prior, _SCRIPT_END, _WRAPPER + _SCRIPT_END)

    def test_portable_replay_and_package_with_bound_audio_do_not_call_a_model(self):
        with patch.object(verify, 'run_requests') as runner:
            receipt, proof = self.prove()
            self.assertEqual(receipt['disagreements'], [])
            self.assertEqual(proof['prior']['evidenceUtf8'].encode(), self.baseline(self.prior))
            self.assertEqual(receipt['verifier']['ranAt'], '2026-11-10T15:00:00+00:00')
            self.assertEqual(receipt['reusedEvidence']['reviewedBodySha256'], verify.body_hash(self.prior))
            self.prior_media.rename(self.root / 'unavailable-prior-media')
            voiced = deepcopy(self.body)
            voiced['stage']['updatedAt'] = 220
            voiced['scenes'][0]['actions'][1].update(audioId='voice', audioUrl='/api/classroom-media/lesson/media/voice.wav')
            voiced['scenes'][1]['content']['questions'][0]['questionAudioUrl'] = '/api/classroom-media/lesson/media/q.wav'
            self.assertEqual(verify_presentation.replay(self.body, self.notes, self.media, proof), receipt)
            voice_receipt = verify_presentation.replay(voiced, self.notes, self.media, proof)
            self.assertEqual(voice_receipt['bodySha256'], verify.body_hash(voiced))
            self.assertEqual(voice_receipt['reusedEvidence'], receipt['reusedEvidence'])
            sidecar = self.work / package.VERIFICATION_EVIDENCE
            sidecar.write_text(json.dumps(proof))
            for name, value in (('body.json', voiced), ('notes.json', self.notes)):
                (self.work / name).write_text(json.dumps(value))
            out = self.work / 'replayed.json'
            argv = ['verify', '--body', str(self.work / 'body.json'), '--notes', str(self.work / 'notes.json'),
                    '--out', str(out), '--reuse-evidence', str(sidecar)]
            with patch('sys.argv', argv), redirect_stdout(StringIO()):
                result = verify.main()
            runner.assert_not_called()
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(out.read_text()), voice_receipt)
            package._check_verification_evidence(self.work, voiced, self.notes, voice_receipt)
            source = self.root / 'source'
            source.mkdir()
            for name, value in (('official-notes.json', self.notes), ('brief.json', {'goals': self.notes['objectives']})):
                (source / name).write_text(json.dumps(value))
            for name, value in (('roster.json', {}), ('audit-receipt.json', {}), ('play-receipt.json', {}),
                                ('draft.json', {'grade': 1}), ('verification.json', voice_receipt)):
                (self.work / name).write_text(json.dumps(value))
            for name in ('voice.wav', 'q.wav'):
                (self.media / name).write_bytes(b'audio test fixture')
            release = self.root / 'package'
            with patch.object(package.check, 'check_classroom', return_value=[]):
                package.package_lesson(source, self.work, release, edition_id='edition', revision_id='revision',
                                       node_id='node', teacher_code='teacher', author_models=['author'])
            self.assertEqual(json.loads((release / package.VERIFICATION_EVIDENCE).read_text()), proof)

    def test_rejects_a_different_delta_even_when_every_request_is_identical(self):
        _, proof = self.prove()
        for before, after in [
            ('left:564px', 'left:565px'),
            ('width:104px', 'width:105px'),
            ('id="teacher-target"', 'id="another-target"'),
            ('class="g-anchor" style', 'class="g-anchor" onclick="run()" style'),
            ('</body>', '<script>run()</script></body>'),
            ('top:86px', 'top:87px'),
        ]:
            with self.subTest(after=after), self.assertRaises(ValueError):
                verify_presentation.replay(self.change_html(self.body, before, after), self.notes, self.media, proof)
        changed = deepcopy(self.body)
        changed['scenes'][0]['actions'][1]['text'] = 'Look for a square.'
        with self.assertRaises(ValueError):
            verify_presentation.replay(changed, self.notes, self.media, proof)

    def test_static_span_translation_reuses_evidence_with_untouched_placeholders(self):
        prior, body = self.span_bodies()
        with patch.object(verify, 'run_requests') as runner:
            receipt, proof = self.prove(body, prior)
            self.assertEqual(receipt['disagreements'], [])
            self.assertEqual(verify_presentation.replay(body, self.notes, self.media, proof), receipt)
            self.assertEqual(proof['prior']['evidenceUtf8'].encode(), self.baseline(prior))
            runner.assert_not_called()

    def test_static_span_replay_rejects_changes_to_fixed_anchor_or_dynamic_placeholders(self):
        prior, body = self.span_bodies()
        _, proof = self.prove(body, prior)
        for before, after in [
            ('left:564px', 'left:565px'),
            ('height:74px', 'height:75px'),
            (_NEW_SPAN, _NEW_TAG),
            (_NEW_SPAN, _NEW_SPAN.replace('g-anchor', 'another-class')),
            (_NEW_SPAN, _NEW_SPAN.replace('></span>', '>text</span>')),
            (_NEW_SPAN, _NEW_SPAN.replace('aria-hidden', 'onclick="run()" aria-hidden')),
            (_PLACEHOLDERS[0], ''),
            (_PLACEHOLDERS[0], _PLACEHOLDERS[0].replace('game-goal', 'other-goal')),
            (_PLACEHOLDERS[0], _PLACEHOLDERS[0].replace('></span>', '>text</span>')),
            (_PLACEHOLDERS[0], _PLACEHOLDERS[0].replace('></span>', ' style="left:1px"></span>')),
            (''.join(_PLACEHOLDERS), ''.join(reversed(_PLACEHOLDERS))),
        ]:
            with self.subTest(after=after), self.assertRaises(ValueError):
                verify_presentation.replay(self.change_html(body, before, after), self.notes, self.media, proof)

    def test_static_span_proof_rejects_noncanonical_original_markup(self):
        prior, _ = self.span_bodies()
        for before, after in [
            (_OLD_SPAN, _OLD_SPAN.replace(' aria-hidden="true"', '')),
            (_OLD_SPAN, _OLD_SPAN.replace('></span>', '>text</span>')),
            (_OLD_SPAN, _OLD_SPAN.replace('aria-hidden', 'data-extra="value" aria-hidden')),
            (_PLACEHOLDERS[0], _PLACEHOLDERS[0].replace(' aria-hidden', ' class="g-anchor" aria-hidden')),
            (_PLACEHOLDERS[0], _PLACEHOLDERS[0].replace('></span>',
                                                      ' style="left:120px;top:90px;width:100px;height:80px"></span>')),
            (_PLACEHOLDERS[0], _PLACEHOLDERS[0].replace('game-goal', 'teacher-target')),
        ]:
            original = self.change_html(prior, before, after)
            current = self.change_html(original, 'left:588px;top:89px', 'left:564px;top:3px')
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.prove(current, original)

    def test_rejects_unreferenced_nested_nonempty_and_ambiguous_old_anchors(self):
        for before, after in [
            (_OLD_TAG, '<section>' + _OLD_TAG + '</section>'),
            (_OLD_TAG, _OLD_TAG.replace('></div>', '>text</div>')),
            (_OLD_TAG, _OLD_TAG + _OLD_TAG),
            (_CSS, _CSS + '#play{top:0}'),
            (_CSS, _CSS + 'div{top:0!important}'),
            (_CSS, _CSS + '[id="play"]{left:0}'),
            ('</head>', '<style media="all">div{left:0}</style></head>'),
            ('</head>', '<link href="other.css" rel="stylesheet"></head>'),
            ('const image=', 'const selector="#teacher-target";const image='),
        ]:
            prior = self.change_html(self.prior, before, after)
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.prove(prior=prior, body=self.change_html(prior, _OLD_TAG, _NEW_TAG))
        prior = deepcopy(self.prior)
        prior['scenes'][0]['actions'][0]['target'] = '#game-player'
        with self.assertRaisesRegex(ValueError, 'teacher highlight'):
            self.prove(prior=prior, body=self.change_html(prior, _OLD_TAG, _NEW_TAG))

    def test_rejects_wrong_pins_old_disagreements_and_changed_media(self):
        with self.assertRaisesRegex(ValueError, 'prior evidence SHA'):
            self.prove(prior_evidence_sha256='0' * 64)
        receipt, proof = self.prove()
        with self.assertRaisesRegex(ValueError, 'official notes'):
            verify_presentation.replay(self.body, {'objectives': ['Another goal']}, self.media, proof)
        self.verdicts[0].update(ok=False, issue='Wrong target.')
        with self.assertRaisesRegex(ValueError, 'passing original'):
            self.prove()
        for filename in (self.picture, self.background):
            f = self.media / filename
            original = f.read_bytes()
            f.write_bytes(b'changed')
            with self.subTest(file=filename), self.assertRaises(ValueError):
                verify_presentation.replay(self.body, self.notes, self.media, proof)
            f.write_bytes(original)
        sidecar = self.work / package.VERIFICATION_EVIDENCE
        broken = deepcopy(proof)
        broken['inputSha256'] = '0' * 64
        receipt['reusedEvidence']['sha256'] = verify.body_hash(broken)
        sidecar.write_text(json.dumps(broken))
        with self.assertRaisesRegex(package.PackageError, 'verification_evidence_changed'):
            package._check_verification_evidence(self.work, self.body, self.notes, receipt)
        receipt.pop('reusedEvidence')
        with self.assertRaisesRegex(package.PackageError, 'missing replay evidence reference'):
            package._check_verification_evidence(self.work, self.body, self.notes, receipt)

    def test_cli_refuses_unpinned_current_body_without_creating_evidence(self):
        for name, value in (('body.json', self.body), ('prior.json', self.prior), ('notes.json', self.notes)):
            (self.root / name).write_text(json.dumps(value))
        raw = self.baseline(self.prior)
        (self.root / 'prior-evidence.json').write_bytes(raw)
        args = [
            '--body', str(self.root / 'body.json'), '--notes', str(self.root / 'notes.json'),
            '--media', str(self.media), '--prior-media', str(self.prior_media), '--prior-body', str(self.root / 'prior.json'),
            '--prior-evidence', str(self.root / 'prior-evidence.json'), '--prior-evidence-sha256', sha256(raw).hexdigest(),
            '--out', str(self.root / 'receipt.json'), '--save-evidence', str(self.root / 'proof.json'),
            '--expected-input-sha256', '0' * 64,
        ]
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as stopped:
            verify_presentation.main(args)
        self.assertEqual(stopped.exception.code, 2)
        self.assertFalse((self.root / 'receipt.json').exists())
        self.assertFalse((self.root / 'proof.json').exists())

    def test_handoff_proof_is_typed_portable_and_replays_through_verify_and_package(self):
        self.assertEqual(len(_WRAPPER.encode()), 232)
        self.assertEqual(sha256(_WRAPPER.encode()).hexdigest(),
                         '18134d91b3492ea63082a9620fba41701b8e5ff9776b28709044cb6f82254f1e')
        for template in ('magnetMarbles', 'listenDelivery'):
            with self.subTest(template=template), patch.object(verify, 'run_requests') as runner:
                prior, body = self.handoff_bodies(template)
                original_raw = self.baseline(prior)
                receipt, proof = self.prove(body, prior, change_kind=_HANDOFF_KIND)
                self.assertEqual(receipt['disagreements'], [])
                self.assertEqual(proof['prior']['evidenceUtf8'].encode(), original_raw)
                self.assertEqual(proof['changeKind'], _HANDOFF_KIND)
                self.assertEqual(receipt['reusedEvidence']['changeKind'], _HANDOFF_KIND)
                self.assertEqual(receipt['reusedEvidence']['reviewedBodySha256'], verify.body_hash(prior))
                self.assertEqual(receipt['verifier']['ranAt'], '2026-11-10T15:00:00+00:00')
                voiced = deepcopy(body)
                voiced['stage']['updatedAt'] = 220
                voiced['scenes'][0]['actions'][2].update(audioId='voice', audioUrl='/api/classroom-media/lesson/media/voice.wav')
                self.prior_media.rename(self.root / 'unavailable-prior-media')
                try:
                    voiced_receipt = verify_presentation.replay(voiced, self.notes, self.media, proof)
                    self.assertEqual(voiced_receipt['bodySha256'], verify.body_hash(voiced))
                    self.assertEqual(voiced_receipt['reusedEvidence'], receipt['reusedEvidence'])
                    sidecar = self.work / package.VERIFICATION_EVIDENCE
                    sidecar.write_text(json.dumps(proof))
                    (self.work / 'body.json').write_text(json.dumps(voiced))
                    (self.work / 'notes.json').write_text(json.dumps(self.notes))
                    out = self.work / 'replayed.json'
                    args = ['verify', '--body', str(self.work / 'body.json'), '--notes', str(self.work / 'notes.json'),
                            '--out', str(out), '--reuse-evidence', str(sidecar)]
                    with patch('sys.argv', args), redirect_stdout(StringIO()):
                        self.assertEqual(verify.main(), 0)
                    self.assertEqual(json.loads(out.read_text()), voiced_receipt)
                    package._check_verification_evidence(self.work, voiced, self.notes, voiced_receipt)
                    runner.assert_not_called()
                finally:
                    (self.root / 'unavailable-prior-media').rename(self.prior_media)

    def test_handoff_rejects_any_change_other_than_the_one_terminal_wrapper(self):
        prior, body = self.handoff_bodies()
        _, proof = self.prove(body, prior, change_kind=_HANDOFF_KIND)
        for changed in (
            prior,
            self.change_html(body, _WRAPPER, _WRAPPER * 2),
            self.change_html(body, _WRAPPER, _WRAPPER.replace('=== false', '!== false')),
            self.change_html(body, _WRAPPER, _WRAPPER + 'trackState();\n'),
            self.change_html(prior, '<script>K.ready', '<script>' + _WRAPPER + 'K.ready'),
            self.change_html(prior, '</body>', '<script>' + _WRAPPER + '</script></body>'),
            self.change_html(body, 'left:120px', 'left:121px'),
            self.change_html(body, 'Find the card', 'Use a different card'),
            self.change_html(body, 'top:86px', 'top:87px'),
        ):
            with self.subTest(html=verify.body_hash(changed)), self.assertRaises(ValueError):
                verify_presentation.replay(changed, self.notes, self.media, proof)
        changed = deepcopy(body)
        changed['scenes'][0]['actions'][-1]['state']['pause'] = True
        with self.assertRaisesRegex(ValueError, 'beyond the allowed presentation'):
            verify_presentation.replay(changed, self.notes, self.media, proof)
        changed = deepcopy(body)
        changed['scenes'][1]['content']['questions'][0]['answer'] = ['B']
        with self.assertRaises(ValueError):
            verify_presentation.replay(changed, self.notes, self.media, proof)
        for kind in (None, verify_presentation.STATIC_ANCHOR, 'arbitrary-script'):
            altered = {**proof, 'changeKind': kind}
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'Malformed presentation'):
                verify_presentation.replay(body, self.notes, self.media, altered)

    def test_handoff_rejects_untrusted_prior_game_shapes_and_missing_real_reset(self):
        prior, _ = self.handoff_bodies()
        for before, after in (
            ('K.game(K.gameTemplates.', 'const setGameState = null;\nK.game(K.gameTemplates.'),
            ('K.game(K.gameTemplates.', 'K.onState = () => {};\nK.game(K.gameTemplates.'),
            ('K.game(K.gameTemplates.', 'sideEffect();\nK.game(K.gameTemplates.'),
            ('K.game(K.gameTemplates.', '/*\nK.game(K.gameTemplates.'),
            ('K.game(K.gameTemplates.', 'const x = `\nK.game(K.gameTemplates.'),
            ('K.game(K.gameTemplates.', 'const behavior = {get value(){return 1}};\nK.game(K.gameTemplates.'),
            ('<script>K.ready', '<script src="different.js">K.ready'),
            ('<script>K.ready', '<!--<script>K.ready'),
            ('<script>K.ready', '<textarea><script>K.ready'),
            ('class="g-anchor"', 'class="g-anchor" onclick="showAnswer()"'),
            ('top:86px', 'top:87px'),
            ('K.highlight=function(sel)', 'K.highlight=function(other)'),
        ):
            original = self.change_html(prior, before, after)
            self.assertNotEqual(original, prior)
            with self.subTest(change=after), self.assertRaises(ValueError):
                self.prove(self.change_html(original, _SCRIPT_END, _WRAPPER + _SCRIPT_END),
                           original, change_kind=_HANDOFF_KIND)
        for kind in ('missingDemo', 'missingHighlight', 'missingHandoff', 'numericFalse'):
            original = deepcopy(prior)
            actions = original['scenes'][0]['actions']
            if kind == 'numericFalse':
                actions[-1]['state']['demo'] = 0
            else:
                index = {'missingDemo': 0, 'missingHighlight': 1, 'missingHandoff': -1}[kind]
                del actions[index]
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'existing teacher'):
                self.prove(self.change_html(original, _SCRIPT_END, _WRAPPER + _SCRIPT_END),
                           original, change_kind=_HANDOFF_KIND)
