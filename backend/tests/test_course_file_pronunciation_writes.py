"""Exercise the real pronunciation caller's three registered pointer writes."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from content.textbook_catalog import canonical
from services.course_file_writer import CourseFileWriteError, _NATIVE
from tests import test_course_file_writer as writer_fixture
from tests import test_textbook_preview_pronunciation_revision as pronunciation


class PronunciationRegisteredWriteTests(unittest.TestCase):
    def setUp(self):
        self.case = pronunciation.PronunciationRevisionTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.f = self.case.f
        self.w = writer_fixture.CourseFileWriterTest()
        self.w.setUp()
        self.addCleanup(self.w.doCleanups)
        self.writer = self.w.writer
        self.w.meta.update(previewKey=self.f.key, classroomId=self.f.cid)
        self.w.db.raw.execute('DELETE FROM learning_textbook_course_previews')
        row = self.f.service.get(self.f.key)
        columns = {r[1] for r in self.w.db.raw.execute('PRAGMA table_info(learning_textbook_course_previews)')}
        for key in set(row) - columns:
            self.w.db.raw.execute('ALTER TABLE learning_textbook_course_previews ADD COLUMN ' + key)
        self.w.db.raw.execute('INSERT INTO learning_textbook_course_previews (' + ','.join(row)
            + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))
        self.writer._read = lambda path, sha=None: self.local(path).read_bytes()
        self.writer._exists = lambda path: self.local(path).is_file()
        for name in ('plan.json', 'receipts.json', 'checkpoint.json'):
            path = self.source(self.f.folder / name)
            self.w.register(path=path, body=(self.f.folder / name).read_bytes())
        self.original = {name: (self.f.folder / name).read_bytes() for name in ('plan.json', 'receipts.json')}

    def source(self, path):
        return _NATIVE + 'classrooms/' + Path(path).resolve().relative_to(self.f.root.resolve()).as_posix()

    def local(self, path):
        prefix = _NATIVE + 'classrooms/'
        self.assertTrue(path.startswith(prefix))
        return self.f.root / path.removeprefix(prefix)

    def atomic(self, path, value):
        raw = canonical(value).encode()
        old = path.read_bytes()
        result = self.writer.write_bytes(self.source(path), raw, expected_sha256=hashlib.sha256(old).hexdigest())
        self.assertEqual(result['sha256'], hashlib.sha256(raw).hexdigest())
        # Represents only the test transport's remote GET readback.
        path.write_bytes(raw)

    def run_rotation(self, atomic=None):
        from services import textbook_preview_pronunciation_revision as module
        with patch.object(module, 'atomic_json', atomic or self.atomic), patch(
                'services.textbook_preview_revision_transaction._registered_source', return_value=True):
            return self.case.run_revision()

    def test_actual_caller_rotates_exact_plan_receipts_checkpoint_without_paid_dispatch(self):
        self.run_rotation()
        for name, original in self.original.items():
            path = self.source(self.f.folder / name)
            self.assertIsNotNone(self.w.repo.resolve(path, self.w.storage, hashlib.sha256(original).hexdigest()))
            self.assertNotEqual(self.w.repo.resolve(path, self.w.storage)['sha256'], hashlib.sha256(original).hexdigest())
        self.assertEqual(json.loads((self.f.folder / 'receipts.json').read_bytes()), [])
        self.case.assert_no_provider()
        self.assertEqual(self.w.uploader.upload.call_count, 3)

    def test_arbitrary_plan_change_and_terminal_receipt_erasure_have_no_rotation_grant(self):
        for name, value in (('plan.json', {'changed': True}), ('receipts.json', [])):
            path = self.f.folder / name
            with self.subTest(name=name), self.assertRaisesRegex(CourseFileWriteError, 'rotation_not_proven'):
                self.writer.write_bytes(self.source(path), canonical(value).encode(),
                    expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.w.uploader.upload.assert_not_called()

    def test_parent_wav_or_saved_snapshot_or_human_evidence_change_blocks_rotation(self):
        self.case.run_revision(execute=False)
        for kind in ('wav', 'saved', 'evidence'):
            with self.subTest(kind=kind):
                def atomic(path, value):
                    if kind == 'wav':
                        intent = json.loads((self.case.archive() / 'intent.json').read_bytes())
                        target = self.f.root / self.f.cid / 'audio' / next(iter(intent['parentWavs']))
                    elif kind == 'saved':
                        target = self.case.archive() / 'saved.json'
                    else:
                        target = self.case.archive() / 'parent/human-feedback.json'
                    prior = target.read_bytes()
                    target.write_bytes(b'{}')
                    try:
                        with self.assertRaises((CourseFileWriteError, ValueError)):
                            self.atomic(path, value)
                    finally:
                        target.write_bytes(prior)
                    raise RuntimeError('stop after rejected first pointer')
                with self.assertRaisesRegex(RuntimeError, 'stop after rejected'):
                    self.run_rotation(atomic)
                self.w.uploader.upload.assert_not_called()

    def test_proof_changed_while_uploading_keeps_old_head_and_uploaded_orphan(self):
        original = self.w.uploader.upload.side_effect
        def upload(**kwargs):
            target = self.case.archive() / 'saved.json'
            target.write_bytes(b'{}')
            return original(**kwargs)
        self.w.uploader.upload.side_effect = upload
        with self.assertRaises(CourseFileWriteError):
            self.run_rotation()
        plan = self.source(self.f.folder / 'plan.json')
        self.assertEqual(self.w.repo.resolve(plan, self.w.storage)['sha256'], hashlib.sha256(self.original['plan.json']).hexdigest())
        self.assertEqual(self.w.uploader.upload.call_count, 1)
        self.case.assert_no_provider()
