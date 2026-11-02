"""Read-only local checks and separately runnable database publication cases."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from content.courseware_release import build_release
from content.textbook_catalog import canonical, digest
from repositories.textbook_repository import TextbookRepository
from services.courseware_publish_service import CoursewarePublishService
from tests.test_courseware_release import sample_inputs, refresh_receipts


def write_lesson(root, inputs):
    root.mkdir(parents=True, exist_ok=True)
    identity = {**inputs['identity'], 'manifest': inputs['manifest'], 'confirmation': inputs['confirmation']}
    for filename, value in [('identity.json', identity), ('body.json', inputs['body']),
            ('official-notes.json', inputs['notes']), ('brief.json', inputs['brief']),
            ('audit-receipt.json', inputs['receipt']), ('verification.json', inputs['verification']),
            ('roster.json', inputs['roster'])]:
        (root / filename).write_text(canonical(value), encoding='utf-8')
    media = root / 'media'
    media.mkdir(exist_ok=True)
    for name, raw in inputs['media'].items():
        (media / name).write_bytes(raw)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in root.rglob('*')}


class CoursewarePublishServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = sample_inputs()
        self.lesson = self.root / 'lesson'
        write_lesson(self.lesson, self.inputs)
        self.repo = MagicMock(spec=TextbookRepository)
        self.repo.get_build.return_value = None
        self.service = CoursewarePublishService(self.repo, classroom_directory=self.root / 'classrooms')

    def test_check_writes_nothing(self):
        before = snapshot(self.root)
        result = self.service.check(self.lesson)
        self.assertTrue(result['ok'], result)
        self.assertEqual(snapshot(self.root), before)
        self.repo.transaction.assert_not_called()
        self.assertEqual(set(result['gates']), {'G%d' % i for i in range(9)})

    def test_check_reads_author_models_and_estimated_minutes_from_identity(self):
        result = self.service.check(self.lesson)
        self.assertTrue(result['ok'], result)
        prepared = result['prepared']
        self.assertEqual(prepared['content_json']['estimatedMinutes'], 15)
        self.assertEqual(prepared['frozen']['identity']['authorModels'], self.inputs['identity']['authorModels'])
        self.assertIn(self.inputs['verification']['verifier']['model'], prepared['review']['basis'])

    def test_check_rejects_receipt_verifier_used_by_an_author(self):
        self.inputs['identity']['authorModels'].append('FIXTURE-VERIFIER')
        write_lesson(self.lesson, self.inputs)
        result = self.service.check(self.lesson)
        self.assertEqual(result['errors'], ['verification_not_independent'])

    def test_check_requires_estimated_minutes_in_identity(self):
        self.inputs['identity'].pop('estimatedMinutes')
        write_lesson(self.lesson, self.inputs)
        result = self.service.check(self.lesson)
        self.assertEqual(result['errors'], ['estimated_minutes_invalid'])

    def test_check_missing_confirmation_does_not_invent_authorization(self):
        identity = json.loads((self.lesson / 'identity.json').read_text())
        identity.pop('confirmation')
        (self.lesson / 'identity.json').write_text(canonical(identity))
        result = self.service.check(self.lesson)
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors'], ['authorization_missing'])

    def test_shared_checker_blocks_missing_picture_options(self):
        self.inputs['body']['scenes'][1]['content']['questions'][0].pop('optionVisuals')
        refresh_receipts(self.inputs)
        write_lesson(self.lesson, self.inputs)
        result = self.service.check(self.lesson)
        self.assertFalse(result['ok'])
        self.assertIn('quiz_visuals_invalid', [issue['code'] for issue in result['issues']])

    def test_materialize_copies_verified_bytes_to_mime_directories(self):
        prepared = build_release(self.inputs)
        self.service._materialize(prepared, self.inputs['media'])
        for entry in prepared['frozen']['media']:
            destination = self.root / 'classrooms' / prepared['release']['classroomId'] / entry['relative']
            self.assertEqual(destination.read_bytes(), self.inputs['media'][entry['sourceName']])
        before = snapshot(self.root)
        self.service._materialize(prepared, self.inputs['media'])
        self.assertEqual(before, snapshot(self.root))

    def test_media_conflict_rejected_without_overwrite(self):
        prepared = build_release(self.inputs)
        entry = prepared['frozen']['media'][0]
        target = self.root / 'classrooms' / prepared['release']['classroomId'] / entry['relative']
        target.parent.mkdir(parents=True)
        target.write_bytes(b'conflicting existing bytes')
        with self.assertRaisesRegex(ValueError, '^media_conflict$'):
            self.service.publish(self.lesson, apply=True)
        self.assertEqual(target.read_bytes(), b'conflicting existing bytes')
        self.repo.transaction.assert_not_called()

    def test_materialize_rechecks_bytes(self):
        prepared = build_release(self.inputs)
        media = dict(self.inputs['media'])
        media[next(iter(media))] += b'changed'
        with self.assertRaisesRegex(ValueError, '^media_hash_mismatch$'):
            self.service._materialize(prepared, media)

    def test_lesson_symlink(self):
        target = self.lesson / 'body.json'
        original = target.read_bytes()
        target.unlink()
        replacement = self.root / 'replacement.json'
        replacement.write_bytes(original)
        target.symlink_to(replacement)
        result = self.service.check(self.lesson)
        self.assertEqual(result['errors'], ['lesson_symlink'])

    def test_dry_run_uses_only_selects_and_writes_no_files(self):
        conn = self.repo.transaction.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = []
        before = snapshot(self.root)
        result = self.service.publish(self.lesson)
        self.assertEqual(result['status'], 'plan')
        self.assertFalse(result['applied'])
        self.assertEqual(before, snapshot(self.root))
        self.repo.reserve_build.assert_not_called()
        self.assertTrue(all(call.args[0].startswith('SELECT') and 'FOR UPDATE' not in call.args[0]
            for call in conn.execute.call_args_list))

    def publication_transaction(self, *, status='prepared'):
        prepared = build_release(self.inputs)
        course, frozen = prepared['course'], prepared['frozen']
        build = {'status': status, 'content_key': frozen['contentKey'], 'node_id': self.inputs['identity']['nodeId'],
            'teaching_revision': '1', 'input_json': canonical(frozen), 'review_json': canonical(prepared['review']),
            'course_id': course['id'], 'course_version': course['version'],
            'course_content_sha256': digest(prepared['content_json'])}
        conn = self.repo.transaction.return_value.__enter__.return_value
        revision = {'manifest_json': canonical(self.inputs['manifest']), 'manifest_sha256': digest(self.inputs['manifest'])}

        def execute(sql, params=()):
            if sql.startswith('SELECT * FROM learning_textbook_revisions'):
                self.assertTrue((self.root / 'classrooms' / prepared['release']['classroomId']).is_dir())
                return SimpleNamespace(fetchone=lambda: revision)
            if sql.startswith('SELECT * FROM learning_courses'):
                return SimpleNamespace(fetchone=lambda: None if 'FOR UPDATE' in sql else course)
            return SimpleNamespace(fetchall=lambda: [])
        conn.execute.side_effect = execute
        self.repo.reserve_build.return_value = (build, True)
        self.repo.bind_published.return_value = True
        self.repo.get_build.return_value = {**build, 'status': 'published'}
        self.repo.manifest.side_effect = TextbookRepository.manifest
        self.repo.parse.side_effect = TextbookRepository.parse
        return prepared, build, revision

    def test_publish_materializes_before_one_transaction_and_final_validation(self):
        self.publication_transaction()
        result = self.service.publish(self.lesson, apply=True)
        self.assertTrue(result['created'])
        self.assertEqual(result['archiveStatus'], 'archive pending')
        self.repo.transaction.assert_called_once()
        self.repo.bind_published.assert_called_once()

    def test_build_retired(self):
        self.publication_transaction(status='retired')
        with self.assertRaisesRegex(ValueError, '^build_retired$'):
            self.service.publish(self.lesson, apply=True)
        self.repo.bind_published.assert_not_called()

    def test_build_status_invalid(self):
        self.publication_transaction(status='failed')
        with self.assertRaisesRegex(ValueError, '^build_status_invalid$'):
            self.service.publish(self.lesson, apply=True)

    def test_review_conflict(self):
        _, build, _ = self.publication_transaction(status='published')
        review = json.loads(build['review_json'])
        review['basis'] = 'different evidence'
        build['review_json'] = canonical(review)
        with self.assertRaisesRegex(ValueError, '^review_conflict$'):
            self.service.publish(self.lesson, apply=True)

    def test_course_conflict(self):
        self.publication_transaction(status='published')
        with self.assertRaisesRegex(ValueError, '^course_conflict$'):
            self.service.publish(self.lesson, apply=True)

    def test_manifest_mismatch_inside_lock(self):
        _, _, revision = self.publication_transaction()
        revision['manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, '^manifest_mismatch$'):
            self.service.publish(self.lesson, apply=True)
        self.repo.reserve_build.assert_not_called()

    def test_manifest_missing(self):
        identity = json.loads((self.lesson / 'identity.json').read_text())
        identity.pop('manifest')
        (self.lesson / 'identity.json').write_text(canonical(identity))
        self.repo.get_revision.return_value = None
        self.assertEqual(self.service.check(self.lesson)['errors'], ['manifest_missing'])

    def test_repository_missing(self):
        service = CoursewarePublishService(None, classroom_directory=self.root / 'classrooms')
        with self.assertRaisesRegex(ValueError, '^repository_missing$'):
            service.publish(self.lesson)

    def test_status_identity_invalid(self):
        for kwargs in ({}, {'classroom_id': 'bad'}, {'content_key': 'bad'},
                       {'content_key': 'a' * 64, 'classroom_id': 'tbpub_' + 'a' * 24}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, '^status_identity_invalid$'):
                self.service.status(**kwargs)
        self.repo.transaction.assert_not_called()

    def test_classroom_ambiguous(self):
        conn = self.repo.transaction.return_value.__enter__.return_value
        conn.execute.return_value.fetchall.return_value = [{'content_key': 'a' * 64}, {'content_key': 'a' * 24 + 'b' * 40}]
        with self.assertRaisesRegex(ValueError, '^classroom_ambiguous$'):
            self.service.status(classroom_id='tbpub_' + 'a' * 24)

    def test_status_reports_registration_without_claiming_playback(self):
        key = 'a' * 64
        conn = self.repo.transaction.return_value.__enter__.return_value
        self.repo.get_build.return_value = {'content_key': key, 'status': 'published'}
        conn.execute.return_value.fetchall.return_value = []
        result = self.service.status(key)
        self.assertFalse(result['registered'])
        self.assertEqual(result['archiveStatus'], 'archive pending')
        conn.execute.return_value.fetchall.return_value = [{'content_key': key}]
        self.assertTrue(self.service.status(key)['registered'])
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in conn.execute.call_args_list))
        self.assertNotIn('playable', result)

    def test_cli_check_json_runs_without_database_or_configuration(self):
        from scripts.publish_courseware import main
        before = snapshot(self.root)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = main(['check', '--lesson-dir', str(self.lesson), '--json'])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertTrue(result['ok'], result)
        self.assertEqual(before, snapshot(self.root))

    def test_cli_publish_requires_all_owner_evidence(self):
        from scripts.publish_courseware import main
        with redirect_stdout(io.StringIO()), patch('sys.stderr', new=io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(['publish', '--lesson-dir', str(self.lesson), '--owner-quote', 'Publish'])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_check_reports_missing_file_without_writes(self):
        from scripts.publish_courseware import main
        (self.lesson / 'brief.json').unlink()
        before = snapshot(self.root)
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(['check', '--lesson-dir', str(self.lesson), '--json']), 1)
        self.assertFalse(json.loads(stdout.getvalue())['ok'])
        self.assertEqual(before, snapshot(self.root))

    def test_cli_publish_plan_apply_and_status_dispatch(self):
        from scripts.publish_courseware import main
        factory = MagicMock()
        factory.return_value.publish.return_value = {'ok': True, 'archiveStatus': 'archive pending',
            'openSessionsOnRetiredBuilds': 3}
        factory.return_value.status.return_value = {'registered': False, 'archiveStatus': 'archive pending'}
        config = MagicMock()
        config.AppConfig.from_env.return_value = SimpleNamespace(DATABASE_URL='unused-test-url')
        database = MagicMock()
        publish_args = ['publish', '--lesson-dir', str(self.lesson), '--owner-quote', 'Publish this lesson',
            '--confirmed-at', self.inputs['confirmation']['confirmedAt'],
            '--author-attestation', self.inputs['confirmation']['authorAttestation']]
        with patch.dict('sys.modules', {'core.config': config, 'core.database': database}), patch(
                'services.courseware_publish_service.CoursewarePublishService', factory):
            for args in (publish_args, publish_args + ['--apply'], ['status', '--classroom-id', 'tbpub_' + 'a' * 24]):
                with self.subTest(args=args), redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(main(args), 0)
                    self.assertEqual(json.loads(stdout.getvalue())['archiveStatus'], 'archive pending')
        calls = factory.return_value.publish.call_args_list
        self.assertFalse(calls[0].kwargs['apply'])
        self.assertTrue(calls[1].kwargs['apply'])
        self.assertEqual(calls[1].kwargs['confirmation']['confirmedBy'], 'owner')
        factory.return_value.status.assert_called_once_with(classroom_id='tbpub_' + 'a' * 24)


class CoursewarePublishDatabaseTests(unittest.TestCase):
    """Database contract cases; run separately in an authorized database test run."""
    def setUp(self):
        from tests.test_textbook_learning import IsolatedDatabase, sample
        self.db = IsolatedDatabase()
        self.addCleanup(self.db.raw.close)
        for name, kind in [('title', 'TEXT'), ('objective', 'TEXT'), ('node_code', 'TEXT'),
                ('published_at', 'INT'), ('created_at', 'INT'), ('updated_at', 'INT')]:
            self.db.execute('ALTER TABLE learning_courses ADD COLUMN ' + name + ' ' + kind)
        self.db.execute('CREATE TABLE course_storage_scopes (storage_id TEXT,scope_key TEXT,content_key TEXT,classroom_id TEXT)')
        self.repo = TextbookRepository(self.db)
        self.inputs = sample_inputs()
        manifest = sample(reviewed=True)
        node = manifest['units'][0]['lessons'][0]
        node['brief']['objectives'] = ['Compare pictured quantities']
        manifest['units'][0]['lessons'][1]['brief'] = deepcopy(node['brief'])
        self.inputs['manifest'] = manifest
        self.inputs['identity'].update(editionId=manifest['editionId'], revisionId=manifest['revisionId'], nodeId=node['nodeId'])
        self.repo.import_revision(self.db, manifest, 1)
        self.db.raw.commit()
        self.temp = tempfile.TemporaryDirectory(dir=os.environ['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lesson = self.root / 'lesson'
        write_lesson(self.lesson, self.inputs)
        self.service = CoursewarePublishService(self.repo, classroom_directory=self.root / 'classrooms', clock=lambda: 100)

    def publish(self, revision):
        self.inputs['identity']['teachingRevision'] = revision
        write_lesson(self.lesson, self.inputs)
        return self.service.publish(self.lesson, apply=True)

    def test_check_writes_no_database_rows_or_files(self):
        before = snapshot(self.root)
        changes = self.db.raw.total_changes
        self.assertTrue(self.service.check(self.lesson)['ok'])
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(changes, self.db.raw.total_changes)

    def test_publication_becomes_directory_choice(self):
        from services.textbook_directory_access import published_node_directory_entries
        result = self.publish('1')
        manifest = self.inputs['manifest']
        entries = published_node_directory_entries(self.repo, {'grade_code': manifest['gradeCode']},
            self.repo.directory_builds(self.db, manifest['editionId'], manifest['revisionId']), manifest)
        self.assertEqual(entries[self.inputs['identity']['nodeId']][0]['content_key'], result['contentKey'])
        self.assertEqual(result['archiveStatus'], 'archive pending')

    def test_retires_only_same_node_and_counts_open_sessions(self):
        old = self.publish('1')
        old_course = self.db.execute('SELECT * FROM learning_courses').fetchone()
        other = deepcopy(self.inputs)
        other['identity']['nodeId'] = other['manifest']['units'][0]['lessons'][1]['nodeId']
        other_dir = self.root / 'other-lesson'
        write_lesson(other_dir, other)
        other_release = self.service.publish(other_dir, apply=True)
        other_before = self.repo.get_build(self.db, other_release['contentKey'])
        self.db.execute("INSERT INTO learning_sessions VALUES (?,?,?,?,?,?)", ('open', 'family', 'child', old['courseId'], old['courseVersion'], 'in_progress'))
        self.db.execute("INSERT INTO learning_sessions VALUES (?,?,?,?,?,?)", ('done', 'family', 'child', old['courseId'], old['courseVersion'], 'completed'))
        self.db.raw.commit()
        new = self.publish('2')
        self.assertEqual(new['retiredBuilds'], 1)
        self.assertEqual(new['openSessionsOnRetiredBuilds'], 1)
        self.assertEqual(self.repo.get_build(self.db, old['contentKey'])['status'], 'retired')
        self.assertEqual(self.repo.get_build(self.db, other_release['contentKey']), other_before)
        retired = self.db.execute('SELECT * FROM learning_courses WHERE id=?', (old['courseId'],)).fetchone()
        self.assertEqual((retired['status'], retired['quality_status'], retired['retired_at'], retired['updated_at']),
                         ('retired', 'superseded', 100, 100))
        unchanged = ('status', 'quality_status', 'retired_at', 'updated_at')
        self.assertEqual({k: retired[k] for k in retired.keys() if k not in unchanged},
                         {k: old_course[k] for k in old_course.keys() if k not in unchanged})
        other_course = self.db.execute('SELECT * FROM learning_courses WHERE id=?', (other_release['courseId'],)).fetchone()
        self.assertEqual((other_course['status'], other_course['retired_at']), ('published', None))
        self.assertEqual(len(self.db.execute('SELECT * FROM learning_sessions').fetchall()), 2)

    def test_same_key_is_unchanged(self):
        first = self.publish('1')
        before = self.repo.get_build(self.db, first['contentKey'])
        second = self.publish('1')
        self.assertFalse(second['created'])
        self.assertEqual(self.repo.get_build(self.db, first['contentKey']), before)
        self.assertEqual(len(self.db.execute('SELECT * FROM learning_courses').fetchall()), 1)

    def test_changed_review_same_key_is_rejected(self):
        first = self.publish('1')
        saved = self.repo.get_build(self.db, first['contentKey'])
        review = json.loads(saved['review_json'])
        review['basis'] += ' Changed review.'
        self.db.execute('UPDATE learning_textbook_course_builds SET review_json=? WHERE content_key=?', (canonical(review), first['contentKey']))
        self.db.raw.commit()
        with self.assertRaisesRegex(ValueError, '^review_conflict$'):
            self.publish('1')
        self.assertEqual(json.loads(self.repo.get_build(self.db, first['contentKey'])['review_json']), review)

    def test_transaction_failure_preserves_previous_publication(self):
        old = self.publish('1')
        original = self.service._predecessors

        def fail(conn, frozen):
            original(conn, frozen)
            raise RuntimeError('injected transaction failure')
        with patch.object(self.service, '_predecessors', side_effect=fail), self.assertRaisesRegex(RuntimeError, 'injected'):
            self.publish('2')
        self.assertEqual(self.repo.get_build(self.db, old['contentKey'])['status'], 'published')
        self.assertEqual(len(self.db.execute('SELECT * FROM learning_courses').fetchall()), 1)
        self.assertEqual(len(self.db.execute('SELECT * FROM learning_textbook_course_builds').fetchall()), 1)
        self.assertEqual(self.db.execute('SELECT status, retired_at FROM learning_courses').fetchone()['retired_at'], None)

    def test_retired_key_never_resurrected(self):
        old = self.publish('1')
        self.publish('2')
        with self.assertRaisesRegex(ValueError, '^build_retired$'):
            self.publish('1')
        self.assertEqual(self.repo.get_build(self.db, old['contentKey'])['status'], 'retired')

    def test_media_conflict_leaves_old_build_published(self):
        old = self.publish('1')
        self.inputs['identity']['teachingRevision'] = '2'
        prepared = build_release(self.inputs)
        entry = prepared['frozen']['media'][0]
        target = self.root / 'classrooms' / prepared['release']['classroomId'] / entry['relative']
        target.parent.mkdir(parents=True)
        target.write_bytes(b'conflict')
        with self.assertRaisesRegex(ValueError, '^media_conflict$'):
            self.publish('2')
        self.assertEqual(self.repo.get_build(self.db, old['contentKey'])['status'], 'published')
        self.assertEqual(target.read_bytes(), b'conflict')

    def test_status_reports_registration(self):
        release = self.publish('1')
        self.assertFalse(self.service.status(classroom_id=release['classroomId'])['registered'])
        self.db.execute('INSERT INTO course_storage_scopes VALUES (?,?,?,?)', ('storage', 'scope', release['contentKey'], release['classroomId']))
        self.db.raw.commit()
        self.assertTrue(self.service.status(release['contentKey'])['registered'])
        self.assertEqual(self.publish('1')['archiveStatus'], 'registered')


if __name__ == '__main__':
    unittest.main()
