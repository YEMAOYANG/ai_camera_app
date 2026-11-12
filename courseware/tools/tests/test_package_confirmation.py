from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from courseware.tools import package


class PackageConfirmationTest(unittest.TestCase):
    args = ['--lesson', 'lesson', '--build', 'build', '--out', 'package',
            '--edition-id', 'edition', '--revision-id', 'revision', '--node-id', 'node',
            '--teacher-code', 'teacher', '--author-model', 'author']

    def test_passes_the_exact_owner_quote_and_attestation(self):
        quote = '我授权：每门课通过后直接发布。'
        time = '2026-11-09T14:14:27+08:00'
        attestation = '使用原创插画。'
        with patch.object(package, 'package_lesson', return_value={}) as pack, redirect_stdout(StringIO()):
            self.assertEqual(package.main(self.args + ['--owner-quote', quote, '--confirmed-at', time,
                                                       '--author-attestation', attestation]), 0)
        self.assertEqual(pack.call_args.kwargs['confirmation'],
                         {'userQuote': quote, 'confirmedAt': time, 'confirmedBy': 'owner',
                          'authorAttestation': attestation})

    def test_partial_confirmation_never_creates_a_package(self):
        with patch.object(package, 'package_lesson') as pack, redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                package.main(self.args + ['--owner-quote', '我授权'])
        pack.assert_not_called()
