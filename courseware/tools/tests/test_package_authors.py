import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from courseware.tools import package
from courseware.tools.tests.test_package import body


class PageAuthorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.lesson, self.build, self.out = root / 'lesson', root / 'build', root / 'package'
        self.lesson.mkdir()
        (self.lesson / 'official-notes.json').write_text('{"resources": {}}')
        (self.lesson / 'brief.json').write_text(json.dumps({'goals': ['认识6']}, ensure_ascii=False))
        (self.build / 'media').mkdir(parents=True)
        for name, value in (('body.json', body()), ('roster.json', {'老师': 'male'}), ('audit-receipt.json', {'ok': True}),
                            ('draft.json', {'grade': 1})):
            (self.build / name).write_text(json.dumps(value, ensure_ascii=False))

    def package(self, verifier, authors, page_authors):
        (self.build / 'verification.json').write_text(json.dumps({'verifier': {'model': verifier}, 'goalsChecked': 3}))
        with patch.object(package.check, 'check_classroom', return_value=[]):
            return package.package_lesson(self.lesson, self.build, self.out, edition_id='e', revision_id='r', node_id='n',
                                          teacher_code='mira_x', author_models=authors, page_author_models=page_authors)

    def test_a_page_only_author_may_verify_and_is_still_recorded_as_an_author(self):
        identity = self.package('gpt-6-luna', ['gpt-6.1-sol', 'claude-sonnet-5-5'], ['gpt-6-luna', 'gpt-6.1-sol'])
        self.assertEqual(identity['authorModels'], ['gpt-6.1-sol', 'claude-sonnet-5-5', 'gpt-6-luna'])

    def test_a_model_that_wrote_lines_or_questions_may_not_verify(self):
        with self.assertRaises(package.PackageError) as caught:
            self.package('GPT-6.1-SOL', ['gpt-6.1-sol'], ['gpt-6-luna'])
        self.assertEqual(caught.exception.args[0], 'verifier_not_independent')
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
