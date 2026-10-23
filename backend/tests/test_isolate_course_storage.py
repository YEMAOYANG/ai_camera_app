"""Isolation exercises only fresh private fixtures, never real course originals."""
from contextlib import redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.course_storage_config import CourseStorageConfig
from scripts import isolate_course_storage as isolation


class CourseStorageIsolationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('MIRA_TASK_TMPDIR'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.state = self.root / isolation.STATE_PATH / 'acceptance-fixture'
        self.config = CourseStorageConfig(mode='registry', endpoint='http://storage.invalid:9000', bucket='study')

    def source(self, name, data=b'approved original', *, present=True):
        source = 'output/current/' + name
        if present:
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return {'sourcePath': source, 'sha256': hashlib.sha256(data).hexdigest(), 'byteSize': len(data)}

    def quarantine(self, entry):
        return self.state / 'files' / entry['sourcePath']

    def run_isolate(self, heads):
        return isolation.isolate(self.root, config=self.config, heads=heads, state_dir=self.state)

    def journal(self):
        return self.state / 'journal.json'

    def test_plan_is_private_durable_and_only_exact_registered_files_and_legacy_index(self):
        entry = self.source('lesson.json')
        missing = self.source('already-remote.wav', present=False)
        history = self.root / 'output/history/unregistered.json'
        history.parent.mkdir(parents=True)
        history.write_bytes(b'never move a history directory')
        index = self.root / isolation.INDEX_PATH
        index.parent.mkdir(parents=True)
        index.write_bytes(b'old local index')
        result = isolation.plan_isolation(self.root, config=self.config, heads=[entry, missing], state_dir=self.state)
        self.assertEqual(result['phase'], 'planned')
        self.assertEqual((result['registeredFiles'], result['missingRegisteredFiles'], result['filesToMove']), (2, 1, 2))
        self.assertEqual(result['legacyIndexFiles'], 1)
        self.assertTrue((self.root / entry['sourcePath']).exists())
        self.assertFalse(self.quarantine(entry).exists())
        self.assertTrue(history.exists())
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.journal().stat().st_mode), 0o600)
        root, state, journal = isolation._load_journal(self.journal())
        self.assertEqual((root, state), (self.root, self.state))
        self.assertEqual(len(journal['entries']), 3)
        self.assertNotIn('secret', json.dumps(journal))

    def test_roundtrip_moves_bytes_with_original_mode_and_does_not_require_registry_to_restore(self):
        heads = [self.source('one.json'), self.source('two.wav', b'voice')]
        for entry in heads:
            (self.root / entry['sourcePath']).chmod(0o640)
        result = self.run_isolate(heads)
        self.assertEqual((result['phase'], result['movedThisRun']), ('isolated', 2))
        for entry in heads:
            self.assertFalse((self.root / entry['sourcePath']).exists())
            self.assertEqual(self.quarantine(entry).read_bytes(), b'voice' if entry is heads[1] else b'approved original')
            self.assertEqual(stat.S_IMODE(self.quarantine(entry).stat().st_mode), 0o640)
        with patch('core.config.AppConfig.from_env', side_effect=AssertionError('Restore must work offline')), redirect_stdout(io.StringIO()):
            self.assertEqual(isolation.main(['restore', '--journal', str(self.journal())]), 0)
        for entry in heads:
            self.assertTrue((self.root / entry['sourcePath']).is_file())
            self.assertFalse(self.quarantine(entry).exists())
        self.assertEqual(json.loads((self.state / 'cursor.json').read_text())['phase'], 'restored')

    def test_all_file_sha_mismatches_are_rejected_before_any_move_or_journal(self):
        heads = [self.source('a.json'), self.source('z.json')]
        (self.root / heads[1]['sourcePath']).write_bytes(b'changed')
        with patch.object(isolation, '_rename_exclusive') as move, self.assertRaisesRegex(isolation.IsolationError, 'integrity_mismatch'):
            self.run_isolate(heads)
        move.assert_not_called()
        self.assertFalse(self.state.exists())
        self.assertTrue(all((self.root / e['sourcePath']).exists() for e in heads))

    def test_planned_source_or_current_head_drift_is_rejected_before_first_move(self):
        heads = [self.source('a.json'), self.source('z.json')]
        isolation.plan_isolation(self.root, config=self.config, heads=heads, state_dir=self.state)
        changed = [{**heads[0], 'sha256': 'a' * 64}, heads[1]]
        with patch.object(isolation, '_rename_exclusive') as move, self.assertRaisesRegex(isolation.IsolationError, 'heads_changed'):
            self.run_isolate(changed)
        move.assert_not_called()
        (self.root / heads[1]['sourcePath']).write_bytes(b'changed')
        with patch.object(isolation, '_rename_exclusive') as move, self.assertRaisesRegex(isolation.IsolationError, 'integrity_mismatch'):
            self.run_isolate(heads)
        move.assert_not_called()
        self.assertTrue((self.root / heads[0]['sourcePath']).exists())

    def test_identical_bytes_with_changed_stat_still_reject_an_outdated_isolation_plan(self):
        heads = [self.source('a.json'), self.source('z.json')]
        isolation.plan_isolation(self.root, config=self.config, heads=heads, state_dir=self.state)
        changed = self.root / heads[1]['sourcePath']
        before = changed.stat()
        os.utime(changed, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        with patch.object(isolation, '_rename_exclusive') as move, self.assertRaisesRegex(isolation.IsolationError, 'stat_changed'):
            self.run_isolate(heads)
        move.assert_not_called()
        self.assertTrue((self.root / heads[0]['sourcePath']).exists())

    def test_crash_after_rename_before_cursor_can_restore_from_paths_and_hashes(self):
        heads = [self.source('a.json'), self.source('b.json')]
        original = isolation._rename_exclusive
        def crash(source, destination):
            original(source, destination)
            if source == self.root / heads[0]['sourcePath']:
                raise RuntimeError('simulated process interruption after rename')
        with patch.object(isolation, '_rename_exclusive', side_effect=crash), self.assertRaises(RuntimeError):
            self.run_isolate(heads)
        self.assertTrue(self.journal().exists())
        self.assertFalse((self.root / heads[0]['sourcePath']).exists())
        self.assertTrue(self.quarantine(heads[0]).exists())
        self.assertEqual(json.loads((self.state / 'cursor.json').read_text())['completed'], 0)
        result = isolation.restore_isolation(self.journal())
        self.assertEqual(result['phase'], 'restored')
        self.assertTrue(all((self.root / e['sourcePath']).exists() for e in heads))

    def test_crash_can_resume_isolation_without_trusting_small_cursor(self):
        heads = [self.source('a.json'), self.source('b.json')]
        original = isolation._rename_exclusive
        def crash(source, destination):
            original(source, destination)
            if source == self.root / heads[0]['sourcePath']:
                raise RuntimeError('crash')
        with patch.object(isolation, '_rename_exclusive', side_effect=crash), self.assertRaises(RuntimeError):
            self.run_isolate(heads)
        result = self.run_isolate(heads)
        self.assertEqual((result['completed'], result['movedThisRun']), (2, 1))
        self.assertEqual(self.run_isolate(heads)['movedThisRun'], 0)

    def test_restore_never_overwrites_different_source_and_preflights_all_pairs(self):
        heads = [self.source('a.json'), self.source('z.json')]
        self.run_isolate(heads)
        (self.root / heads[1]['sourcePath']).write_bytes(b'new authoring version')
        with patch.object(isolation, '_rename_exclusive') as move, self.assertRaisesRegex(isolation.IsolationError, 'integrity_mismatch'):
            isolation.restore_isolation(self.journal())
        move.assert_not_called()
        self.assertFalse((self.root / heads[0]['sourcePath']).exists())
        self.assertTrue(self.quarantine(heads[0]).exists())
        self.assertEqual((self.root / heads[1]['sourcePath']).read_bytes(), b'new authoring version')

    def test_restore_retains_quarantine_when_same_bytes_already_exist(self):
        heads = [self.source('a.json'), self.source('b.json')]
        self.run_isolate(heads)
        current = self.root / heads[0]['sourcePath']
        current.write_bytes(self.quarantine(heads[0]).read_bytes())
        current.chmod(0o600)
        result = isolation.restore_isolation(self.journal())
        self.assertEqual((result['retainedCopies'], result['movedThisRun']), (1, 1))
        self.assertTrue(self.quarantine(heads[0]).exists())
        self.assertEqual(stat.S_IMODE(current.stat().st_mode), 0o600)
        self.assertFalse(self.quarantine(heads[1]).exists())
        self.assertEqual(isolation.restore_isolation(self.journal())['retainedCopies'], 1)

    def test_source_leaf_and_ancestor_links_nonregular_and_unsafe_state_are_rejected(self):
        entry = self.source('a.json')
        file = self.root / entry['sourcePath']
        target = file.with_name('target.json')
        file.rename(target)
        file.symlink_to(target)
        with self.assertRaisesRegex(isolation.IsolationError, 'symlink'):
            self.run_isolate([entry])
        file.unlink()
        target.rename(file)
        directory = file.parent
        other = directory.with_name('other')
        directory.rename(other)
        directory.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(isolation.IsolationError, 'link_or_non_directory'):
            self.run_isolate([entry])
        directory.unlink()
        other.rename(directory)
        file.unlink()
        os.mkfifo(file)
        with self.assertRaisesRegex(isolation.IsolationError, 'not_regular'):
            self.run_isolate([entry])
        with self.assertRaisesRegex(isolation.IsolationError, 'state_must_be_private'):
            isolation.plan_isolation(self.root, config=self.config, heads=[entry], state_dir=self.root / 'output/quarantine')

    def test_target_ancestor_link_cross_device_and_registry_mode_fail_before_move(self):
        heads = [self.source('a.json')]
        with patch.object(isolation, '_directory_device', return_value=(self.root.stat().st_dev + 1)), \
             self.assertRaisesRegex(isolation.IsolationError, 'cross_device'):
            self.run_isolate(heads)
        with self.assertRaisesRegex(isolation.IsolationError, 'registry_mode_required'):
            isolation.isolate(self.root, config=replace(self.config, mode='manifest'), heads=heads, state_dir=self.state)
        isolation.plan_isolation(self.root, config=self.config, heads=heads, state_dir=self.state)
        (self.state / 'files').mkdir(mode=0o700)
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        (self.state / 'files/output').symlink_to(elsewhere, target_is_directory=True)
        with patch.object(isolation, '_rename_exclusive') as move, self.assertRaisesRegex(isolation.IsolationError, 'link_or_non_directory'):
            self.run_isolate(heads)
        move.assert_not_called()
        self.assertTrue((self.root / heads[0]['sourcePath']).exists())

    def test_exclusive_rename_and_journal_ownership_never_overwrite_existing_data(self):
        a, b = self.root / 'a', self.root / 'b'
        a.write_bytes(b'one')
        b.write_bytes(b'two')
        with self.assertRaises(FileExistsError):
            isolation._rename_exclusive(a, b)
        self.assertEqual((a.read_bytes(), b.read_bytes()), (b'one', b'two'))
        heads = [self.source('a.json')]
        self.run_isolate(heads)
        self.journal().chmod(0o644)
        with self.assertRaisesRegex(isolation.IsolationError, 'not_private'):
            isolation.restore_isolation(self.journal())
        self.journal().chmod(0o600)
        data = json.loads(self.journal().read_text())
        data['entries'][0]['sha256'] = 'a' * 64
        self.journal().write_text(json.dumps(data))
        with self.assertRaisesRegex(isolation.IsolationError, 'journal_integrity'):
            isolation.restore_isolation(self.journal())

    def test_hardlinked_source_aliases_reject_before_journaling_or_moving(self):
        a, b = self.source('a.json'), self.source('b.json', present=False)
        os.link(self.root / a['sourcePath'], self.root / b['sourcePath'])
        with patch.object(isolation, '_rename_exclusive') as move, self.assertRaisesRegex(isolation.IsolationError, 'alias_collision'):
            self.run_isolate([a, b])
        move.assert_not_called()
        self.assertFalse(self.state.exists())
        self.assertTrue(all((self.root / e['sourcePath']).exists() for e in (a, b)))

    def test_missing_skips_must_be_registered_and_plan_is_written_once_with_small_batch_cursors(self):
        with self.assertRaisesRegex(isolation.IsolationError, 'empty_registry'):
            self.run_isolate([])
        with self.assertRaises(ValueError):
            self.run_isolate([{'sourcePath': 'output/../secret', 'sha256': 'a' * 64, 'byteSize': 1}])
        heads = [self.source(str(n) + '.json') for n in range(5)]
        original = isolation._write_json
        writes = []
        def record(path, value, **options):
            writes.append((path.name, len(isolation._json(value))))
            return original(path, value, **options)
        with patch.object(isolation, 'BATCH', 2), patch.object(isolation, '_write_json', side_effect=record):
            self.run_isolate(heads)
        self.assertEqual(sum(name == 'journal.json' for name, size in writes), 1)
        self.assertEqual(sum(name == 'cursor.json' for name, size in writes), 5)
        self.assertTrue(all(size < 1024 for name, size in writes if name == 'cursor.json'))

    def test_heads_are_selected_from_current_head_join_in_a_read_only_snapshot(self):
        entry = self.source('a.json')
        conn, database = Mock(), Mock()
        database.connect.return_value = conn
        conn.execute.return_value.fetchall.return_value = [{**entry,
            'pathSha256': hashlib.sha256(entry['sourcePath'].encode()).hexdigest()}]
        self.assertEqual(isolation.current_heads(database, self.config), [entry])
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertIn('READ ONLY', statements[1])
        self.assertIn('FROM course_storage_heads h LEFT JOIN course_storage_files f', statements[2])
        self.assertTrue(statements[2].startswith('SELECT '))
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_dangling_registry_head_cannot_silently_disappear_from_snapshot(self):
        conn, database = Mock(), Mock()
        database.connect.return_value = conn
        conn.execute.return_value.fetchall.return_value = [{'sourcePath': None, 'pathSha256': None,
            'sha256': None, 'byteSize': None}]
        with self.assertRaisesRegex(isolation.IsolationError, 'path_identity_invalid'):
            isolation.current_heads(database, self.config)
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()
