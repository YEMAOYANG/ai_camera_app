"""Isolation exercises only fresh private fixtures, never real course originals."""
from contextlib import redirect_stderr, redirect_stdout
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

    def registry_scope(self, scope_key, entries, *, preview_key=None, content_key=None):
        metadata = {'scopeKey': scope_key}
        if preview_key is not None:
            metadata['previewKey'] = preview_key
        if content_key is not None:
            metadata['contentKey'] = content_key
        return {'storage_id': isolation.storage_id_for(self.config.endpoint, self.config.bucket, self.config.region),
            'scope_key': scope_key, 'preview_key': preview_key, 'content_key': content_key,
            'classroom_id': None, 'course_id': None, 'course_version': None,
            'scope_json': json.dumps(metadata),
            'bindings_json': json.dumps([{'sourcePath': e['sourcePath'], 'sha256': e['sha256'],
                'sourcePathSha256': hashlib.sha256(e['sourcePath'].encode()).hexdigest()} for e in entries])}

    def scoped_database(self, scopes, heads, *, current=True, owners=None):
        conn, database = Mock(), Mock()
        database.connect.return_value = conn
        def execute(sql, params=()):
            cursor = Mock()
            if sql.startswith(('SET ', 'START ')):
                return cursor
            if sql.startswith(('SELECT p.preview_key', 'SELECT b.content_key')):
                cursor.fetchone.return_value = {'key': params[0]} if current else None
            elif 'FROM course_storage_scopes' in sql and 'AND scope_key=?' in sql:
                cursor.fetchone.return_value = (owners or {}).get(params[1])
            elif 'FROM course_storage_scopes' in sql:
                cursor.fetchall.return_value = scopes
            elif 'FROM course_storage_heads' in sql:
                cursor.fetchall.return_value = [{**e, 'pathSha256': hashlib.sha256(e['sourcePath'].encode()).hexdigest()}
                    for e in heads]
            else:
                raise AssertionError(sql)
            return cursor
        conn.execute.side_effect = execute
        return database, conn

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

    def test_preview_scope_selects_only_bound_current_heads_in_read_only_snapshot(self):
        key, owner = 'a' * 64, 'b' * 64
        entry = self.source('one.json')
        shared = self.source('shared.png', b'picture')
        scopes = [self.registry_scope(owner, [entry, shared], preview_key=key)]
        # A same-version shared dependency remains eligible even when another
        # course owns its head. Its actual current owner is fenced in the plan.
        expected = [{**entry, 'scopeKey': owner}, {**shared, 'scopeKey': 'c' * 64}]
        database, conn = self.scoped_database(scopes, expected)
        self.assertEqual(isolation.current_heads(database, self.config, preview_key=key), expected)
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertIn('READ ONLY', statements[1])
        self.assertIn('p.status IN', statements[2])
        self.assertIn('r.retired_at IS NULL', statements[2])
        self.assertIn('preview_key=?', statements[3])
        self.assertIn('h.source_path_sha256 IN (?,?)', statements[4])
        self.assertTrue(all(sql.startswith(('SELECT ', 'SET ', 'START ')) for sql in statements))
        conn.rollback.assert_called_once()
        conn.close.assert_called_once()

    def test_content_scope_requires_current_published_released_nonretired_build(self):
        key, owner = 'a' * 64, 'b' * 64
        entry = {**self.source('one.json'), 'scopeKey': owner}
        database, conn = self.scoped_database([self.registry_scope(owner, [entry], content_key=key)], [entry])
        self.assertEqual(isolation.current_heads(database, self.config, content_key=key), [entry])
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertIn("b.status='published'", statements[2])
        self.assertIn("c.quality_status='released'", statements[2])
        self.assertIn('c.retired_at IS NULL AND r.retired_at IS NULL', statements[2])
        self.assertIn('content_key=?', statements[3])

    def test_scoped_selection_rejects_retired_missing_or_unusable_course_before_reading_scopes(self):
        database, conn = self.scoped_database([], [], current=False)
        with self.assertRaisesRegex(isolation.IsolationError, 'scope_not_current'):
            isolation.current_heads(database, self.config, preview_key='a' * 64)
        self.assertEqual(len(conn.execute.call_args_list), 3)

    def test_scoped_selection_uses_new_head_only_when_current_owner_binds_same_course(self):
        key, old_owner, new_owner = 'a' * 64, 'b' * 64, 'c' * 64
        old = self.source('one.json', b'old')
        current = {**self.source('one.json', b'current'), 'scopeKey': new_owner}
        scopes = [self.registry_scope(old_owner, [old], preview_key=key)]
        database, _ = self.scoped_database(scopes, [current],
            owners={new_owner: self.registry_scope(new_owner, [current], preview_key=key)})
        self.assertEqual(isolation.current_heads(database, self.config, preview_key=key), [current])
        other_owner = self.registry_scope(new_owner, [current], preview_key='d' * 64)
        database, _ = self.scoped_database(scopes, [current], owners={new_owner: other_owner})
        with self.assertRaisesRegex(isolation.IsolationError, 'scope_head_conflict'):
            isolation.current_heads(database, self.config, preview_key=key)

    def test_scoped_selection_does_not_silently_skip_missing_current_head(self):
        key, owner = 'a' * 64, 'b' * 64
        entry = self.source('one.json')
        database, _ = self.scoped_database([self.registry_scope(owner, [entry], preview_key=key)], [])
        with self.assertRaisesRegex(isolation.IsolationError, 'scope_head_missing'):
            isolation.current_heads(database, self.config, preview_key=key)

    def test_scoped_roundtrip_never_inspects_or_moves_global_index_and_restores_offline(self):
        key, owner = 'a' * 64, 'b' * 64
        entry = {**self.source('one.json'), 'scopeKey': owner}
        other = self.source('other-course.json')
        index = self.root / isolation.INDEX_PATH
        index.parent.mkdir(parents=True)
        index.write_bytes(b'keep global index')
        result = isolation.isolate(self.root, config=self.config, heads=[entry], state_dir=self.state, preview_key=key)
        self.assertEqual((result['filesToMove'], result['legacyIndexFiles']), (1, 0))
        self.assertEqual(index.read_bytes(), b'keep global index')
        self.assertTrue((self.root / other['sourcePath']).exists())
        journal = isolation._load_journal(self.journal())[2]
        self.assertEqual(journal['scope'], {'previewKey': key})
        self.assertEqual(journal['entries'][0]['scopeKey'], owner)
        self.assertEqual(journal['headsSha256'], isolation._sha(isolation._json([entry])))
        with patch('core.config.AppConfig.from_env', side_effect=AssertionError('offline restore')), redirect_stdout(io.StringIO()):
            self.assertEqual(isolation.main(['restore', '--journal', str(self.journal())]), 0)
        self.assertTrue((self.root / entry['sourcePath']).exists())
        self.assertEqual(index.read_bytes(), b'keep global index')

    def test_scoped_resume_fences_selector_and_head_owner_even_for_identical_file_bytes(self):
        key = 'a' * 64
        entry = {**self.source('one.json'), 'scopeKey': 'b' * 64}
        isolation.plan_isolation(self.root, config=self.config, heads=[entry], state_dir=self.state, preview_key=key)
        with patch.object(isolation, '_rename_exclusive') as move:
            for selection in ({}, {'content_key': key}, {'preview_key': 'c' * 64}):
                with self.assertRaisesRegex(isolation.IsolationError, 'scope_changed'):
                    isolation.isolate(self.root, config=self.config, heads=[entry], state_dir=self.state, **selection)
            with self.assertRaisesRegex(isolation.IsolationError, 'heads_changed'):
                isolation.isolate(self.root, config=self.config, heads=[{**entry, 'scopeKey': 'd' * 64}],
                                  state_dir=self.state, preview_key=key)
            move.assert_not_called()
        self.assertTrue((self.root / entry['sourcePath']).exists())

    def test_scoped_plan_rejects_missing_owner_and_local_version_mismatch_before_journal(self):
        key = 'a' * 64
        entry = self.source('one.json')
        with self.assertRaisesRegex(isolation.IsolationError, 'scoped_heads_required'):
            isolation.plan_isolation(self.root, config=self.config, heads=[entry], state_dir=self.state, preview_key=key)
        current = {**entry, 'scopeKey': 'b' * 64, 'sha256': 'c' * 64}
        with self.assertRaisesRegex(isolation.IsolationError, 'integrity_mismatch'):
            isolation.isolate(self.root, config=self.config, heads=[current], state_dir=self.state, preview_key=key)
        self.assertFalse(self.state.exists())
        self.assertTrue((self.root / entry['sourcePath']).exists())

    def test_scope_api_and_cli_selectors_are_validated_before_database_or_movement(self):
        database = Mock()
        for selection in ({'preview_key': 'not-a-key'}, {'preview_key': 'a' * 64, 'content_key': 'b' * 64}):
            with self.assertRaises(isolation.IsolationError):
                isolation.current_heads(database, self.config, **selection)
        database.connect.assert_not_called()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            isolation.main(['plan', '--project-root', str(self.root), '--preview-key', 'a' * 64,
                            '--content-key', 'b' * 64])
        self.assertEqual(error.exception.code, 2)

    def test_cli_forwards_exact_selector_to_selection_and_isolation_and_keeps_default(self):
        for operation in ('plan', 'isolate'):
            for option in (None, '--preview-key', '--content-key'):
                selection = {'preview_key': None, 'content_key': None}
                argv = [operation, '--project-root', str(self.root), '--state-dir', str(self.state)]
                if option is not None:
                    argv += [option, 'a' * 64]
                    selection[option[2:].replace('-', '_')] = 'a' * 64
                expected_heads, database = [self.source('one.json')], Mock()
                function = 'plan_isolation' if operation == 'plan' else 'isolate'
                with patch('core.config.AppConfig.from_env', return_value=Mock(DATABASE_URL='private-fixture')), \
                     patch('core.database.Database', return_value=database), \
                     patch.object(isolation.CourseStorageConfig, 'from_env', return_value=self.config), \
                     patch.object(isolation, 'current_heads', return_value=expected_heads) as select, \
                     patch.object(isolation, function, return_value={'phase': 'fixture'}) as run, \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(isolation.main(argv), 0)
                select.assert_called_once_with(database, self.config, **selection)
                run.assert_called_once_with(str(self.root), config=self.config, heads=expected_heads,
                                            state_dir=str(self.state), **selection)
