import copy
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from courseware.tools import check, verify


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.body = {'scenes': [
            {'type': 'slide', 'actions': [{'type': 'speech', 'id': 's1', 'text': 'Count.'},
                                         {'type': 'speech', 'id': 's2', 'text': 'Look.'}]},
            {'type': 'quiz', 'actions': [], 'content': {'questions': [
                {'id': 'q1', 'question': 'One plus one?', 'options': [
                    {'label': 'one', 'value': 'A'}, {'label': 'two', 'value': 'B'}],
                 'answer': ['B'], 'analysis': 'Two.', 'skill': 'addition'}]}}]}
        self.notes = {'objectives': ['addition'], 'keyPoint': 'count', 'difficultPoint': 'sum'}
        self.answers = {'q1': ['B']}
        self.requests = verify.build_requests(self.body, self.notes)

    def runner(self, prompt, schema, model, effort):
        if 'ok' in schema['properties']['verdicts']['items']['properties']:
            return {'verdicts': [{'id': 's1', 'ok': True, 'issue': None},
                                 {'id': 's2', 'ok': True, 'issue': None}]}
        if 'solved' in schema['properties']['verdicts']['items']['properties']:
            return {'verdicts': [{'id': 'q1', 'solved': 'B',
                                  'skillMatchesObjectives': True, 'issue': None}]}
        return {'verdicts': [{'id': 'q1', 'analysisOk': True, 'issue': None}]}

    def receipt(self, verdicts):
        return verify.build_receipt(self.body, self.notes, self.requests, verdicts, self.answers,
                                    model='verifier', effort='low', ran_at='now')

    def test_agreement_and_gate(self):
        verdicts = verify.run_requests(self.requests, self.runner, model='verifier', effort='low')
        receipt = self.receipt(verdicts)
        self.assertEqual((receipt['speechChecked'], receipt['questionsChecked']), (2, 1))
        self.assertEqual(receipt['bodySha256'], check.body_hash(self.body))
        self.assertEqual(receipt['notesSha256'], check.body_hash(self.notes))
        self.assertEqual(receipt['disagreements'], [])
        self.assertEqual([issue for issue in check.check_classroom(self.body, verification=receipt)
                          if issue['gate'] == 'G7'], [])

    def test_disagreements(self):
        original = verify.run_requests(self.requests, self.runner, model='v', effort='low')
        for index, field, value, kind in [(0, 'ok', False, 'speech'), (2, 'solved', 'A', 'answer'),
                                          (3, 'analysisOk', False, 'analysis'),
                                          (2, 'skillMatchesObjectives', False, 'skill')]:
            with self.subTest(kind=kind):
                verdicts = copy.deepcopy(original)
                verdicts[index][field] = value
                verdicts[index]['issue'] = 'Review needed'
                self.assertEqual(self.receipt(verdicts)['disagreements'],
                                 [{'kind': kind, 'id': verdicts[index]['id'], 'issue': 'Review needed'}])

    def test_missing_extra_and_malformed_verdicts(self):
        valid = self.runner('', verify._schema('speech'), '', '')['verdicts']
        variants = [valid[:1], valid + [{'id': 'extra', 'ok': True, 'issue': None}],
                    [dict(valid[0], ok='yes'), valid[1]], [valid[0], dict(valid[1], extra=1)]]
        for variant in variants:
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                verify.run_requests(self.requests[:1], lambda *args: {'verdicts': variant}, model='v', effort='low')
        for request in self.requests[1:]:
            valid_question = self.runner('', verify._schema(request['kind']), '', '')['verdicts'][0]
            for invalid in ([], [dict(valid_question, id='extra')], [dict(valid_question, issue=1)]):
                with self.subTest(kind=request['kind'], invalid=invalid), self.assertRaises(ValueError):
                    verify.run_requests([request], lambda *args: {'verdicts': invalid}, model='v', effort='low')
        verdicts = verify.run_requests(self.requests, self.runner, model='v', effort='low')
        with self.assertRaises(ValueError):
            self.receipt(verdicts[:-1])
        with self.assertRaises(ValueError):
            verify.build_receipt(self.body, self.notes, self.requests[:-1], verdicts[:-1], self.answers,
                                 model='v', effort='low', ran_at='now')

    def test_batching_and_answer_not_exposed(self):
        requests = verify.build_requests(self.body, self.notes, batch_size=1)
        self.assertEqual([len(request['items']) for request in requests], [1, 1, 1, 1])
        solve, analysis = requests[-2:]
        self.assertEqual((solve['kind'], analysis['kind']), ('question_solve', 'question_analysis'))
        self.assertNotIn('answer', solve['items'][0])
        self.assertNotIn('analysis', solve['items'][0])
        self.assertNotIn('\"answer\":', solve['prompt'])
        self.assertNotIn('Two.', solve['prompt'])
        self.assertNotIn('\"analysis\":', solve['prompt'])
        self.assertEqual(analysis['items'][0]['answer'], 'B')
        self.assertEqual(analysis['items'][0]['analysis'], 'Two.')
        self.assertIn('\"answer\": \"B\"', analysis['prompt'])
        self.assertIn('Two.', analysis['prompt'])
        body = copy.deepcopy(self.body)
        second = copy.deepcopy(body['scenes'][1]['content']['questions'][0])
        second['id'] = 'q2'
        body['scenes'][1]['content']['questions'].append(second)
        split = verify.build_requests(body, self.notes, batch_size=1)
        self.assertEqual([request['kind'] for request in split],
                         ['speech', 'speech', 'question_solve', 'question_solve',
                          'question_analysis', 'question_analysis'])
        self.assertEqual([request['items'][0]['id'] for request in split[-4:]], ['q1', 'q2', 'q1', 'q2'])
        with self.assertRaises(ValueError):
            verify.build_requests(self.body, self.notes, batch_size=0)

    @patch('courseware.tools.verify.subprocess.run')
    def test_default_runner_command_and_retry(self, run):
        calls = []
        def fake(command, **kwargs):
            calls.append((command, kwargs))
            self.assertEqual(json.loads(Path(command[command.index('--output-schema') + 1]).read_text()),
                             verify._schema('speech'))
            if len(calls) == 1:
                raise subprocess.CalledProcessError(1, command)
            Path(command[command.index('-o') + 1]).write_text('{"verdicts": []}')
            return subprocess.CompletedProcess(command, 0, stderr='')
        run.side_effect = fake
        with patch.dict('os.environ', {'MIRA_CODEX_BIN': '/fake/codex'}):
            self.assertEqual(verify.default_runner('prompt', verify._schema('speech'), 'model', 'low'),
                             {'verdicts': []})
        command, kwargs = calls[-1]
        self.assertEqual(command[:8], ['/fake/codex', 'exec', '-m', 'model', '-c',
                                      'model_reasoning_effort=low', '-s', 'read-only'])
        self.assertEqual(command[8:10], ['--skip-git-repo-check', '--ephemeral'])
        self.assertEqual(command[-1], '-')
        self.assertEqual(kwargs['input'], 'prompt')
        self.assertEqual(len(calls), 2)
        self.assertFalse(Path(kwargs['cwd']).exists())

    @patch('courseware.tools.verify.subprocess.run')
    def test_default_runner_surfaces_stderr(self, run):
        stderr = 'x' * 301 + ' diagnostic cause'
        run.side_effect = subprocess.CalledProcessError(1, ['codex'], stderr=stderr)
        with self.assertRaises(RuntimeError) as caught:
            verify.default_runner('prompt', verify._schema('speech'), 'model', 'low')
        self.assertIn(stderr[-300:], str(caught.exception))
        self.assertNotIn(stderr, str(caught.exception))
        self.assertEqual(run.call_count, 2)


if __name__ == '__main__':
    unittest.main()
