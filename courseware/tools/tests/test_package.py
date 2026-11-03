import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from courseware.tools import package


def body(speech='x' * 40, interactive=2, quiz_questions=2, slides=1):
    scenes = [{'type': 'slide', 'actions': [{'type': 'speech', 'text': speech}]} for _ in range(slides)]
    scenes += [{'type': 'interactive', 'actions': []} for _ in range(interactive)]
    scenes.append({'type': 'quiz', 'actions': [], 'content': {'questions': [{}] * quiz_questions}})
    return {'stage': {'name': '本课'}, 'scenes': scenes}


class EstimateTests(unittest.TestCase):
    def test_estimate_rounds_up_to_five_minutes_and_is_clamped(self):
        # 40 characters = 10 s, one slide 20 s, two interactive pages 200 s, two questions 120 s: 350 s, under the minimum
        self.assertEqual(package.estimate_minutes(body()), 10)
        # 400 characters = 100 s, slide 20 s, six pages 600 s, four questions 240 s: 960 s = 16 minutes, rounded up to 20
        self.assertEqual(package.estimate_minutes(body('x' * 400, interactive=6, quiz_questions=4)), 20)
        self.assertEqual(package.estimate_minutes(body('x' * 40000, interactive=40)), 60)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.lesson, self.build, self.out = root / 'lesson', root / 'build', root / 'package'
        self.lesson.mkdir()
        (self.lesson / 'official-notes.json').write_text('{"resources": {}}')
        (self.lesson / 'brief.json').write_text(json.dumps({'goals': ['认识6', '会数数']}, ensure_ascii=False))
        (self.build / 'media').mkdir(parents=True)
        (self.build / 'media' / 'a.wav').write_bytes(b'wav')
        for name, value in (('body.json', body()), ('roster.json', {'老师': 'male'}), ('audit-receipt.json', {'ok': True}),
                            ('verification.json', {'verifier': {'model': 'gpt-6.1-sol'}}), ('draft.json', {'grade': 1})):
            (self.build / name).write_text(json.dumps(value, ensure_ascii=False))
        self.ids = dict(edition_id='e', revision_id='r', node_id='n', teacher_code='mira_x', author_models=['gpt-6.1-terra', 'claude-sonnet-5-5'])

    def run_package(self, issues=()):
        with patch.object(package.check, 'check_classroom', return_value=list(issues)):
            return package.package_lesson(self.lesson, self.build, self.out, **self.ids)

    def test_package_has_every_file_and_a_derived_identity(self):
        identity = self.run_package()
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ['audit-receipt.json', 'body.json', 'brief.json', 'identity.json', 'media', 'official-notes.json', 'roster.json', 'verification.json'])
        self.assertEqual((self.out / 'media' / 'a.wav').read_bytes(), b'wav')
        self.assertEqual(json.loads((self.out / 'identity.json').read_text(encoding='utf-8')), identity)
        self.assertEqual((identity['title'], identity['objective'], identity['teachingRevision'], identity['estimatedMinutes']),
                         ('本课', '认识6；会数数', '1', 10))
        self.assertEqual(identity['authorModels'], ['gpt-6.1-terra', 'claude-sonnet-5-5'])

    def test_the_lesson_is_checked_as_a_teaching_lesson(self):
        with patch.object(package.check, 'check_classroom', return_value=[]) as checker:
            package.package_lesson(self.lesson, self.build, self.out, **self.ids)
        self.assertTrue(checker.call_args.kwargs['teaching'])

    def test_a_failing_gate_stops_packaging(self):
        issue = {'gate': 'G6', 'code': 'audit_receipt_stale', 'severity': 'error'}
        with self.assertRaises(package.PackageError) as caught:
            self.run_package([issue, {'gate': 'G3', 'code': 'x', 'severity': 'warn'}])
        self.assertEqual(caught.exception.args[0], 'gates_failed')
        self.assertIn('G6 audit_receipt_stale', caught.exception.args[1])
        self.assertNotIn('G3', caught.exception.args[1])
        self.assertFalse(self.out.exists())

    def test_the_verifier_may_not_be_an_author(self):
        self.ids['author_models'] = ['GPT-6.1-SOL']
        with self.assertRaises(package.PackageError) as caught:
            self.run_package()
        self.assertEqual(caught.exception.args[0], 'verifier_not_independent')

    def test_existing_output_and_missing_goals_are_refused(self):
        self.out.mkdir()
        with self.assertRaises(package.PackageError) as caught:
            self.run_package()
        self.assertEqual(caught.exception.args[0], 'out_exists')
        self.out.rmdir()
        (self.lesson / 'brief.json').write_text('{"goals": []}')
        with self.assertRaises(package.PackageError) as caught:
            self.run_package()
        self.assertEqual(caught.exception.args[0], 'brief_goals_missing')

    def test_cli_reports_errors_with_exit_code_one(self):
        argv = ['--lesson', str(self.lesson), '--build', str(self.build), '--out', str(self.out), '--edition-id', 'e', '--revision-id', 'r',
                '--node-id', 'n', '--teacher-code', 't', '--author-model', 'gpt-6.1-sol']
        errors = StringIO()
        with patch.object(package.check, 'check_classroom', return_value=[]), redirect_stderr(errors), redirect_stdout(StringIO()):
            self.assertEqual(package.main(argv), 1)
        self.assertIn('verifier_not_independent', errors.getvalue())


if __name__ == '__main__':
    unittest.main()
