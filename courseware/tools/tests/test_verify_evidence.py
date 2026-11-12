from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from courseware.tools import check, verify


class VerifyEvidenceTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=os.environ['MIRA_TASK_TMPDIR'])
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.picture = self.root / 'option.png'
        self.picture.write_bytes(b'option image')
        self.body = {'stage': {'id': 'stage', 'createdAt': 10},
                     'scenes': [{'type': 'quiz', 'title': 'Review', 'createdAt': 10, 'actions': [
                         {'type': 'speech', 'id': 's1', 'text': 'Pick one.', 'agentId': 'teacher'}],
                         'content': {'questions': [{'id': 'q1', 'question': 'Which is one?',
                             'answer': ['A'], 'skill': 'counting', 'analysis': 'One dot.',
                             'options': [{'label': 'one', 'value': 'A'}, {'label': 'two', 'value': 'B'}],
                             'optionVisuals': {'A': {'kind': 'image',
                                 'src': '/api/classroom-media/stage/media/option.png'}}}]}}]}
        self.notes = {'objectives': ['counting']}
        self.answers = {'q1': ['A']}
        self.verdicts = [{'id': 's1', 'ok': True, 'issue': None},
                         {'id': 'q1', 'solved': 'A', 'skillMatchesObjectives': True,
                          'picturesMatch': True, 'issue': None},
                         {'id': 'q1', 'analysisOk': True, 'issue': None},
                         {'id': 'goal-1', 'verdict': 'taught', 'taughtAt': '1', 'issue': None}]
        self.draft = self.root / 'draft.json'
        self.final = self.root / 'body.json'
        self.notes_path = self.root / 'notes.json'
        self.evidence = self.root / 'verification-evidence.json'
        self.initial_receipt = self.root / 'pre-audio.json'
        self.final_receipt = self.root / 'verification.json'
        self.draft.write_text(json.dumps({'body': self.body, 'lines': []}))
        self.notes_path.write_text(json.dumps(self.notes))

    def cli(self, body, output, *extra):
        command = ['verify', '--body', str(body), '--notes', str(self.notes_path),
                   '--out', str(output), '--media', str(self.root), *extra]
        with patch('sys.argv', command), redirect_stdout(StringIO()):
            return verify.main()

    def test_real_runner_result_is_reused_without_invocation_when_only_audio_is_bound(self):
        with patch.object(verify, 'run_requests', return_value=self.verdicts) as runner:
            self.assertEqual(self.cli(self.draft, self.initial_receipt, '--save-evidence', str(self.evidence)), 0)
            runner.assert_called_once()
        before = self.evidence.read_bytes()
        original = json.loads(self.initial_receipt.read_text())
        final = deepcopy(self.body)
        final['stage']['createdAt'] = 20
        scene = final['scenes'][0]
        scene['createdAt'] = 20
        scene['actions'][0].update(audioId='audio', audioUrl='audio')
        scene['content']['questions'][0]['questionAudioUrl'] = 'audio'
        self.final.write_text(json.dumps(final))
        with patch.object(verify, 'run_requests') as runner:
            self.assertEqual(self.cli(self.final, self.final_receipt, '--reuse-evidence', str(self.evidence)), 0)
            runner.assert_not_called()
        self.assertEqual(self.evidence.read_bytes(), before)
        receipt = json.loads(self.final_receipt.read_text())
        self.assertEqual(receipt['verifier'], original['verifier'])
        self.assertEqual(receipt['bodySha256'], check.body_hash(final))
        self.assertEqual(receipt['reusedEvidence']['reviewedBodySha256'], original['bodySha256'])
        self.assertEqual(receipt['goalsChecked'], 1)

    def test_refuses_content_notes_picture_model_and_missing_verdict_changes(self):
        with patch.object(verify, 'run_requests', return_value=self.verdicts):
            self.assertEqual(self.cli(self.draft, self.initial_receipt, '--save-evidence', str(self.evidence)), 0)
        evidence = json.loads(self.evidence.read_text())

        def reuse(body, notes, **options):
            requests = verify.build_requests(body, notes, media=self.root, teaching=True)
            return verify.verification_from_evidence(body, notes, requests, self.answers,
                options.get('evidence', evidence), model=options.get('model', verify.VERIFIER_MODEL),
                effort=verify.VERIFIER_EFFORT)

        changed = deepcopy(self.body)
        changed['scenes'][0]['actions'][0]['text'] = 'Choose a pair.'
        with self.assertRaisesRegex(ValueError, 'inputs differ'):
            reuse(changed, self.notes)
        with self.assertRaisesRegex(ValueError, 'inputs differ'):
            reuse(self.body, {'objectives': ['subtraction']})
        with self.assertRaisesRegex(ValueError, 'different model'):
            reuse(self.body, self.notes, model='different')
        with self.assertRaisesRegex(ValueError, 'Verdict count'):
            reuse(self.body, self.notes, evidence={**evidence, 'verdicts': self.verdicts[:-1]})
        self.picture.write_bytes(b'different bytes')
        with self.assertRaisesRegex(ValueError, 'inputs differ'):
            reuse(self.body, self.notes)
