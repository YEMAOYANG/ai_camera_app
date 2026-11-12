import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from courseware.tools import check, package


class PackageEvidenceTest(unittest.TestCase):
    def test_copies_recorded_model_evidence_and_refuses_changed_bytes(self):
        with tempfile.TemporaryDirectory(dir=os.environ['MIRA_TASK_TMPDIR']) as tmp:
            root = Path(tmp)
            source, work = root / 'source', root / 'work'
            source.mkdir()
            (work / 'media').mkdir(parents=True)
            for filename, value in {
                'official-notes.json': {'objectives': ['目标']},
                'brief.json': {'goals': ['目标']},
            }.items():
                (source / filename).write_text(json.dumps(value))
            evidence = {'verdicts': [{'id': 'goal-1', 'verdict': 'taught'}]}
            for filename, value in {
                'body.json': {'stage': {'name': '课'}, 'scenes': []},
                'roster.json': {}, 'audit-receipt.json': {}, 'play-receipt.json': {},
                'draft.json': {'grade': 1},
                'verification.json': {'verifier': {'model': 'verifier'}, 'goalsChecked': 1,
                                      'reusedEvidence': {'sha256': check.body_hash(evidence)}},
                package.VERIFICATION_EVIDENCE: evidence,
            }.items():
                (work / filename).write_text(json.dumps(value))

            def pack(out):
                return package.package_lesson(source, work, out, edition_id='edition', revision_id='revision',
                    node_id='node', teacher_code='teacher', author_models=['author'])

            with patch.object(check, 'check_classroom', return_value=[]):
                pack(root / 'release')
                self.assertEqual((root / 'release' / package.VERIFICATION_EVIDENCE).read_bytes(),
                                 (work / package.VERIFICATION_EVIDENCE).read_bytes())
                (work / package.VERIFICATION_EVIDENCE).write_text('{"verdicts":[]}')
                with self.assertRaisesRegex(package.PackageError, 'verification_evidence_changed'):
                    pack(root / 'bad-release')
            self.assertFalse((root / 'bad-release').exists())
