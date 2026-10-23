"""Published local revisions: SQLite :memory:, synthetic media, mocked runtime."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import fcntl
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

from content.textbook_catalog import canonical, digest
from content.textbook_operator_revision import VISUAL_PATCH_SCHEMA, sha_text, validate_parent
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from repositories.textbook_repository import TextbookRepository
from scripts import audit_textbook_audio
from scripts import revise_published_textbook
from services.textbook_operator_revision_service import prepare_revision, register_revision, load_prepared
from services.textbook_preview_audio import narrate_preview
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_preview_visual_revision import sha_bytes, revise_preview_visuals
from services.textbook_publication_service import TextbookPublicationService
from tests.test_textbook_learning import IsolatedDatabase
from tests import test_textbook_operator_revision as fixtures


class OperatorRevisionServiceTests(unittest.TestCase):
    def setUp(self):
        self.db = IsolatedDatabase(('082_fixed_textbook_learning.sql', '083_textbook_course_previews.sql', '087_learning_course_reuse.sql'))
        self.addCleanup(self.db.raw.close)
        for field in ('node_code TEXT', 'title TEXT', 'objective TEXT', 'published_at INT', 'created_at INT', 'updated_at INT'):
            self.db.raw.execute('ALTER TABLE learning_courses ADD COLUMN ' + field)
        self.repo = TextbookRepository(self.db)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'classrooms'
        self.root.mkdir()
        self.output = self.base / 'candidate'
        self.audit_dir = self.base / 'source-audit'
        self.audit_dir.mkdir()
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
            wav.writeframes(b'\x10\x27\xf0\xd8' * 12000)
        self.audio, self.picture = buffer.getvalue(), getattr(self, 'fixture_picture', b'\x89PNG\r\n\x1a\nsynthetic-picture')
        p = fixtures.parent_fixture(v2=getattr(self, 'fixture_v2', False),
                                    retry=True, audio_sha=sha_bytes(self.audio), image_sha=sha_bytes(self.picture),
                                    quiz_intro=getattr(self, 'quiz_intro', False), saved_preview=getattr(self, 'fixture_saved', False),
                                    quiz_audio_alias=getattr(self, 'fixture_quiz_alias', False))
        self.parent_key = p['build']['content_key']
        self.source_key, self.source_cid = p['preview']['preview_key'], p['preview']['classroom_id']
        self.source_folder = self.root / self.source_cid / 'textbook-preview-audio'
        self.source_folder.mkdir(parents=True)
        self.docs = {self.source_cid: json.loads(p['preview']['classroom_json'])}
        (self.root / (self.source_cid + '.json')).write_text(p['preview']['classroom_json'])
        for name, obj in [('plan.json', p['plan']), ('receipts.json', p['receipts'])]:
            (self.source_folder / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2))
        self.source_audit = self.audit_dir / 'audit.json'
        self.source_audit.write_text(json.dumps(p['audit'], ensure_ascii=False, indent=2))
        for entry in p['audit']['segments']:
            (self.audit_dir / (entry['asr']['requestId'] + '.json')).write_text(canonical(entry))
            path = self.root / self.source_cid / 'audio' / (entry['ttsRequestId'] + '.wav')
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(self.audio)
        image = self.root / self.source_cid / 'media/picture.png'
        image.parent.mkdir(); image.write_bytes(self.picture)
        if getattr(self, 'fixture_quiz_alias', False):
            (self.root / self.source_cid / 'audio/question-1.wav').write_bytes(self.audio)
        release = json.loads(p['build']['review_json'])['release']
        for m in release['media']:
            path = self.root / '/'.join(m['path'].split('/')[3:])
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(self.audio)
        preview = {**p['preview'], 'runtime_origin': 'http://127.0.0.1:3100', 'runtime_job_id': 'source-session', 'created_at': 1, 'updated_at': 1}
        with self.repo.transaction() as conn:
            self.repo.import_revision(conn, p['manifest'], 1)
            if 'sourceManifest' in p:
                self.repo.import_revision(conn, p['sourceManifest'], 1)
            conn.execute('INSERT INTO learning_textbook_course_previews (' + ','.join(preview) + ') VALUES (' + ','.join('?' for _ in preview) + ')', tuple(preview.values()))
            frozen = json.loads(p['build']['input_json'])
            build, _ = self.repo.reserve_build(conn, frozen, 1)
            course = {'id': 'source-course', 'version': '3', 'content_json': canonical({'title': 'source'})}
            conn.execute("INSERT INTO learning_courses(id,version,grade_code,subject,status,quality_status,content_json) VALUES (?,?,?,?,'published','released',?)",
                (course['id'], course['version'], 'primary_1', 'chinese', course['content_json']))
            self.repo.bind_published(conn, build, course, json.loads(p['build']['review_json']), 1)
        self.runtime = Mock(base_url='http://127.0.0.1:3100')
        def read(cid):
            if cid not in self.docs:
                raise OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
            return deepcopy(self.docs[cid])
        def save(room):
            self.docs[room['id']] = {**deepcopy(room), 'createdAt': 2}
            (self.root / (room['id'] + '.json')).write_text(canonical(self.docs[room['id']]))
        self.runtime.get_classroom.side_effect, self.runtime.save_preview_classroom.side_effect = read, save
        self.service = TextbookPreviewService(self.repo, self.runtime)
        self.patch = fixtures.patch_for(p, [fixtures.OperatorRevisionContractTests().speech_change()])
        self.before_rows = self.parent_rows()
        self.before_files = self.source_files()

    def parent_rows(self):
        return [self.repo.get_build(self.db, self.parent_key), self.service.get(self.source_key)]

    def source_files(self):
        return {str(p.relative_to(self.base)): p.read_bytes() for d in (self.root / self.source_cid, self.audit_dir)
                for p in d.rglob('*') if p.is_file() and p.name != 'operator.lock'} | {
            self.source_cid + '.json': (self.root / (self.source_cid + '.json')).read_bytes()}

    def prepare(self, **kw):
        return prepare_revision(self.service, self.parent_key, self.root, self.patch, self.source_audit, self.output, **kw)

    def register(self):
        return register_revision(self.service, self.output, self.root, budget_reference='explicit test scope: one corrected sentence')

    def configure_paid_mocks(self):
        calls = {}
        def get(request):
            if request not in calls: raise OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
            return calls[request]
        def speak(**kw):
            value = {'status': 'succeeded', 'requestId': kw['request_id'], 'audioSha256': sha_bytes(self.audio)}
            calls[kw['request_id']] = value
            return value
        self.runtime.get_formal_audio_tts.side_effect = get
        self.runtime.start_formal_audio_tts.side_effect = speak
        self.runtime.download_formal_audio_tts.return_value = self.audio
        self.runtime.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
        def recognize(**kw):
            action = next(a for s in self.docs[kw['classroom_id']]['scenes'] for a in s.get('actions', []) if a['id'] == kw['action_id'])
            return {'status': 'succeeded', 'requestId': kw['request_id'], 'transcript': action['text'], 'transcriptSha256': sha_text(action['text'])}
        self.runtime.start_formal_audio_asr.side_effect = recognize

    def audit(self, key):
        argv = ['audit_textbook_audio', '--key', key, '--classroom-directory', str(self.root), '--output', str(self.base / 'target-audit')]
        with patch.object(audit_textbook_audio.AppConfig, 'from_env'), patch.object(audit_textbook_audio, 'Database', return_value=self.db), \
             patch.object(audit_textbook_audio, 'OpenMaicFullRuntimeClient', return_value=self.runtime), patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            audit_textbook_audio.main()
        return json.loads((self.base / 'target-audit/audit.json').read_text())

    def test_prepare_register_narrate_audit_publish_reuses_exact_parent_and_only_changes_one_line(self):
        prepared = self.prepare()
        self.assertEqual((prepared['changedSpeechCount'], prepared['inheritedSpeechCount']), (1, 2))
        self.assertEqual(prepared, self.prepare())
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM learning_textbook_course_previews').fetchone()['n'], 1)
        self.runtime.assert_not_called()
        registered = self.register()
        key = prepared['previewKey']
        self.assertEqual(self.register(), registered)
        self.runtime.save_preview_classroom.assert_called_once()
        self.configure_paid_mocks()
        narrate_preview(self.service, key, self.root)
        self.runtime.start_formal_audio_tts.assert_called_once()
        audit = self.audit(key)
        self.assertTrue(audit['passed'])
        self.assertEqual(sum('operatorParent' in e for e in audit['segments']), 2)
        self.runtime.start_formal_audio_asr.assert_called_once()
        narrate_preview(self.service, key, self.root)
        self.assertEqual(audit, self.audit(key))
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.start_formal_audio_asr.assert_called_once()
        row = self.service.get(key)
        old_receipts = json.loads(self.before_rows[1]['result_json'])['audioReceipts']
        old_by_id = {r['requestId']: r for r in old_receipts}
        changed = {(c['sceneId'], c['actionId']) for c in self.patch['changes'] if c['kind'] == 'speech'}
        parent_room = json.loads(self.before_rows[1]['classroom_json'])
        inherited_ids = {a['audioId'] for s in parent_room['scenes'] for a in s['actions']
                         if a['type'] == 'speech' and (s['id'], a['id']) not in changed}
        new_id = self.runtime.start_formal_audio_tts.call_args.kwargs['request_id']
        receipts = json.loads(row['result_json'])['audioReceipts']
        by_id = {r['requestId']: r for r in receipts}
        self.assertEqual((len(inherited_ids), len(receipts), len(by_id)), (2, 3, 3))
        self.assertNotIn(new_id, old_by_id)
        self.assertEqual(set(by_id), inherited_ids | {new_id})
        for request in inherited_ids:
            self.assertEqual(by_id[request], old_by_id[request])
        self.assertEqual(by_id[new_id]['status'], 'succeeded')
        self.assertEqual(by_id[new_id]['audioSha256'], sha_bytes(self.audio))
        publisher = TextbookPublicationService(self.service)
        review = dict(alignmentConfirmed=True, originalExpressionConfirmed=True, sourceUsageConfirmed=True,
            publicationAuthorized=True, reviewer='test', basis='new complete review', sourceSha256=row['classroom_sha256'], reviewedAt=now_ms() - 1)
        altered = deepcopy(audit)
        altered['segments'][1].pop('operatorParent')
        altered['sha256'] = digest({k: v for k, v in altered.items() if k != 'sha256'})
        with self.assertRaises(ApiError):
            publisher.prepare(key=key, edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
                teaching_revision='4', review=review, audio_audit=altered, classroom_directory=self.root)
        release = publisher.prepare(key=key, edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
            teaching_revision='4', review=review, audio_audit=audit, classroom_directory=self.root)
        receipt = publisher.publish(release)
        self.assertEqual(receipt['status'], 'published')
        build = self.repo.get_build(self.db, receipt['contentKey'])
        self.assertEqual(validate_release(build, release['manifest']), release['release'])
        self.assertEqual(self.before_rows, self.parent_rows())
        self.assertEqual(self.before_files, self.source_files())
        validate_release(self.parent_rows()[0], release['manifest'])

    def test_visual_v3_revises_published_child_with_complete_ancestry_without_paid_calls(self):
        prepared = self.prepare()
        self.register(); self.configure_paid_mocks()
        narrate_preview(self.service, prepared['previewKey'], self.root)
        audit = self.audit(prepared['previewKey'])
        row = self.service.get(prepared['previewKey'])
        publisher = TextbookPublicationService(self.service)
        review = dict(alignmentConfirmed=True, originalExpressionConfirmed=True, sourceUsageConfirmed=True,
            publicationAuthorized=True, reviewer='test', basis='review source child',
            sourceSha256=row['classroom_sha256'], reviewedAt=now_ms() - 1)
        release = publisher.prepare(key=row['preview_key'], edition=row['edition_id'], revision=row['revision_id'],
            node=row['node_id'], teaching_revision='4', review=review, audio_audit=audit, classroom_directory=self.root)
        receipt = publisher.publish(release)
        source_audit = self.base / 'target-audit/audit.json'
        parent = {'preview': row, 'build': self.repo.get_build(self.db, receipt['contentKey'])}
        patch_value = {**fixtures.patch_for(parent, []), 'schemaVersion': VISUAL_PATCH_SCHEMA, 'teachingRevision': '5'}
        output = self.base / 'second-candidate'
        second = prepare_revision(self.service, receipt['contentKey'], self.root, patch_value,
            source_audit, output, visual_patch=fixtures.visual_patch_for(parent))
        source, candidate, frozen, intent = load_prepared(output, verify_assets=True)
        self.assertIn('sourceInheritance', source)
        self.assertIn('source-inheritance/prepared.json', intent['files'])
        self.assertEqual(second['inheritedSpeechCount'], 3)
        original = deepcopy(source)
        for mutate in (
            lambda p: p['sourceInheritance']['provenance'].update(sha256='0' * 64),
            lambda p: p['sourceInheritance']['candidate']['patch'].update(basis='forged'),
            lambda p: p['audit']['segments'][1]['operatorParent'].update(sourceEntrySha256='0' * 64),
        ):
            bad = deepcopy(original); mutate(bad)
            with self.assertRaises(ApiError):
                validate_parent(bad, allow_saved_preview=True, allow_visual_ancestry=True)
        tts_count, asr_count = self.runtime.start_formal_audio_tts.call_count, self.runtime.start_formal_audio_asr.call_count
        register_revision(self.service, output, self.root, budget_reference='visual-only test')
        narrate_preview(self.service, second['previewKey'], self.root)
        second_audit = self.audit(second['previewKey'])
        self.assertTrue(second_audit['passed'])
        self.assertEqual((self.runtime.start_formal_audio_tts.call_count, self.runtime.start_formal_audio_asr.call_count),
                         (tts_count, asr_count))
        row = self.service.get(second['previewKey'])
        review.update(sourceSha256=row['classroom_sha256'], reviewedAt=now_ms() - 1)
        second_release = publisher.prepare(key=row['preview_key'], edition=row['edition_id'], revision=row['revision_id'],
            node=row['node_id'], teaching_revision='5', review=review, audio_audit=second_audit, classroom_directory=self.root)
        receipt = publisher.publish(second_release)
        self.assertEqual(validate_release(self.repo.get_build(self.db, receipt['contentKey']), second_release['manifest']), second_release['release'])
        archived = output / 'source-inheritance/parent.json'
        archived.write_text('{}')
        with self.assertRaises(ApiError):
            load_prepared(output, verify_assets=True)

    def test_visual_patch_precedes_plan_and_existing_post_audio_visual_tool_still_works(self):
        old = self.docs[self.source_cid]['scenes'][1]['content']['html']
        visual = {'schemaVersion': 'mira.textbook.preview-visual-patch.v1', 'expectedSourceSha256': self.patch['expectedSourceSha256'],
            'reviewer': 'test', 'basis': 'stroke path feedback', 'changes': [{'sceneId': 'interactive', 'beforeHtmlSha256': sha_text(old),
                'html': '<svg><path d="M1 1L2 2"/></svg>' + old}]}
        prepared = self.prepare(visual_patch=visual)
        self.register(); self.configure_paid_mocks()
        key, cid = prepared['previewKey'], prepared['classroomId']
        plan_bytes = (self.root / cid / 'textbook-preview-audio/plan.json').read_bytes()
        narrate_preview(self.service, key, self.root)
        current = self.service.get(key)
        old = json.loads(current['classroom_json'])['scenes'][1]['content']['html']
        visual.update(expectedSourceSha256=current['classroom_sha256'], changes=[{'sceneId': 'interactive',
            'beforeHtmlSha256': sha_text(old), 'html': old.replace('M1 1L2 2', 'M1 1L3 3')}])
        revise_preview_visuals(self.service, key, self.root, visual)
        self.assertEqual((self.root / cid / 'textbook-preview-audio/plan.json').read_bytes(), plan_bytes)
        self.assertTrue(self.audit(key)['passed'])
        self.runtime.start_formal_audio_tts.assert_called_once()

    def test_pure_visual_roundtrip_inherits_every_wav_and_asr_without_provider_calls(self):
        self.patch['changes'] = []
        parent = {'preview': self.before_rows[1]}
        visual = fixtures.visual_patch_for(parent)
        for name in ('get_formal_audio_tts', 'start_formal_audio_tts', 'download_formal_audio_tts',
                     'get_formal_audio_asr', 'start_formal_audio_asr'):
            getattr(self.runtime, name).side_effect = AssertionError('Provider call forbidden in visual-only revision')
        prepared = self.prepare(visual_patch=visual)
        self.assertEqual((prepared['changedSpeechCount'], prepared['inheritedSpeechCount']), (0, 3))
        self.register()
        key, cid = prepared['previewKey'], prepared['classroomId']
        narrate_preview(self.service, key, self.root)
        row = self.service.get(key)
        self.assertEqual(row['status'], 'preview_ready')
        audit = self.audit(key)
        self.assertTrue(audit['passed'])
        self.assertEqual(len(audit['segments']), 3)
        old_audit = json.loads(self.source_audit.read_text())
        for entry in audit['segments']:
            old = next(e for e in old_audit['segments'] if e['actionId'] == entry['actionId'])
            self.assertEqual(entry['asr'], old['asr'])
            self.assertEqual(entry['transcript'], old['transcript'])
            self.assertIn('operatorParent', entry)
            name = entry['ttsRequestId'] + '.wav'
            self.assertEqual((self.root / cid / 'audio' / name).read_bytes(),
                             (self.root / self.source_cid / 'audio' / name).read_bytes())
        expected_receipts = [r for r in json.loads(self.before_rows[1]['result_json'])['audioReceipts'] if r['status'] == 'succeeded']
        self.assertEqual(json.loads(row['result_json'])['audioReceipts'], expected_receipts)
        self.assertEqual(self.service.freeze(key)['status'], 'preview_ready')
        publisher = TextbookPublicationService(self.service)
        review = dict(alignmentConfirmed=True, originalExpressionConfirmed=True, sourceUsageConfirmed=True,
            publicationAuthorized=True, reviewer='test', basis='new full visual review, exact source audio',
            sourceSha256=row['classroom_sha256'], reviewedAt=now_ms() - 1)
        release = publisher.prepare(key=key, edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
            teaching_revision='4', review=review, audio_audit=audit, classroom_directory=self.root)
        receipt = publisher.publish(release)
        self.assertEqual(receipt['status'], 'published')
        self.assertEqual(self.before_rows, self.parent_rows())
        self.assertEqual(self.before_files, self.source_files())
        for name in ('get_formal_audio_tts', 'start_formal_audio_tts', 'download_formal_audio_tts',
                     'get_formal_audio_asr', 'start_formal_audio_asr'):
            getattr(self.runtime, name).assert_not_called()

    def test_unknown_save_is_reconciled_and_never_resent(self):
        self.prepare()
        save = self.runtime.save_preview_classroom.side_effect
        def lost(room):
            save(room)
            raise TimeoutError('lost response')
        self.runtime.save_preview_classroom.side_effect = lost
        with self.assertRaises(TimeoutError): self.register()
        self.register()
        self.runtime.save_preview_classroom.assert_called_once()
        self.assertEqual(self.before_rows, self.parent_rows())

    def test_unknown_save_without_artifact_and_changed_parent_fail_closed(self):
        self.prepare()
        self.runtime.save_preview_classroom.side_effect = TimeoutError('unknown dispatch')
        with self.assertRaises(TimeoutError): self.register()
        with self.assertRaises(ApiError): self.register()
        self.runtime.save_preview_classroom.assert_called_once()
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM learning_textbook_course_previews').fetchone()['n'], 1)

    def test_changed_source_archive_or_asset_and_active_lock_refuse_before_register(self):
        with (self.source_folder / 'operator.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ApiError): self.prepare()
        self.prepare()
        self.db.execute('UPDATE learning_textbook_course_previews SET updated_at=2 WHERE preview_key=?', (self.source_key,))
        self.db.raw.commit()
        with self.assertRaises(ApiError): self.register()
        self.runtime.save_preview_classroom.assert_not_called()
        (self.output / 'source-receipts.json').write_text('[]')
        with self.assertRaises(ApiError): load_prepared(self.output)

    def test_missing_or_tampered_provenance_cannot_fall_back_to_new_paid_calls(self):
        prepared = self.prepare()
        self.register(); self.configure_paid_mocks()
        archive = self.root / prepared['classroomId'] / 'textbook-preview-audio/operator-parent'
        provenance = archive / 'provenance.json'
        value = json.loads(provenance.read_text())
        value['inheritedSegments'] = []
        value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
        provenance.write_text(canonical(value))
        with self.assertRaises(ApiError): narrate_preview(self.service, prepared['previewKey'], self.root)
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.assertEqual(self.before_files, self.source_files())

    def test_asr_archive_cannot_be_relabeled_by_rehashing_file_list(self):
        self.prepare()
        path = next((self.output / 'asr').glob('*.json'))
        entry = json.loads(path.read_text())
        entry['durationMs'] += 100
        path.write_text(canonical(entry))
        intent_path = self.output / 'prepared.json'
        intent = json.loads(intent_path.read_text())
        intent['files'][str(path.relative_to(self.output))] = sha_bytes(path.read_bytes())
        intent['sha256'] = digest({k: v for k, v in intent.items() if k != 'sha256'})
        intent_path.write_text(canonical(intent))
        with self.assertRaises(ApiError): self.register()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_cli_failure_is_nonzero_and_unknown_runtime_details_are_not_printed(self):
        argv = ['revise_published_textbook', 'register', '--candidate', '/unused',
                '--classroom-directory', '/unused', '--budget-reference', 'test']
        for error in (ApiError('known_conflict', '安全的来源冲突提示', 409),
                      TimeoutError('password=secret-token; private provider response')):
            stderr, stdout = io.StringIO(), io.StringIO()
            with patch('sys.argv', argv), patch.object(revise_published_textbook, 'execute', side_effect=error), \
                    redirect_stderr(stderr), redirect_stdout(stdout):
                self.assertEqual(revise_published_textbook.main(), 1)
            self.assertEqual(stdout.getvalue(), '')
            result = json.loads(stderr.getvalue())
            self.assertFalse(result['ok'])
            self.assertNotIn('secret-token', stderr.getvalue())
            self.assertNotIn('Traceback', stderr.getvalue())
            if isinstance(error, ApiError):
                self.assertEqual(result['error'], 'known_conflict')
            else:
                self.assertEqual(result['exceptionType'], 'TimeoutError')
                self.assertIn('不要删除标记', result['message'])


class PureVisualV2ServiceTests(unittest.TestCase):
    fixture_v2 = True
    setUp = OperatorRevisionServiceTests.setUp
    parent_rows = OperatorRevisionServiceTests.parent_rows
    source_files = OperatorRevisionServiceTests.source_files
    prepare = OperatorRevisionServiceTests.prepare
    register = OperatorRevisionServiceTests.register
    audit = OperatorRevisionServiceTests.audit
    test_pure_visual_roundtrip = OperatorRevisionServiceTests.test_pure_visual_roundtrip_inherits_every_wav_and_asr_without_provider_calls


if __name__ == '__main__': unittest.main()


class SavedVisualRevisionTests(unittest.TestCase):
    fixture_saved = True
    setUp = OperatorRevisionServiceTests.setUp
    parent_rows = OperatorRevisionServiceTests.parent_rows
    source_files = OperatorRevisionServiceTests.source_files
    prepare = OperatorRevisionServiceTests.prepare
    register = OperatorRevisionServiceTests.register
    configure_paid_mocks = OperatorRevisionServiceTests.configure_paid_mocks
    audit = OperatorRevisionServiceTests.audit

    def test_saved_preview_visual_revision_updates_binding_and_preserves_all_audio(self):
        self.patch.update(schemaVersion=VISUAL_PATCH_SCHEMA, changes=[])
        parent = {'preview': self.service.get(self.source_key)}
        result = self.prepare(visual_patch=fixtures.visual_patch_for(parent))
        source, candidate, frozen, _ = load_prepared(self.output, verify_assets=True)
        self.assertIn('sourceManifest', source)
        self.assertEqual(frozen['alignmentRevisionId'], source['manifest']['revisionId'])
        self.register(); self.configure_paid_mocks()
        narrate_preview(self.service, result['previewKey'], self.root)
        audit = self.audit(result['previewKey'])
        self.assertTrue(audit['passed'])
        row = self.service.get(result['previewKey'])
        review = dict(alignmentConfirmed=True, originalExpressionConfirmed=True, sourceUsageConfirmed=True,
            publicationAuthorized=True, reviewer='test', basis='saved source visual revision',
            sourceSha256=row['classroom_sha256'], reviewedAt=now_ms() - 1)
        publisher = TextbookPublicationService(self.service)
        released = publisher.prepare(key=row['preview_key'], edition=row['edition_id'], revision=row['revision_id'],
            node=row['node_id'], teaching_revision='4', review=review, audio_audit=audit, classroom_directory=self.root)
        published = publisher.publish(released)
        self.assertEqual(validate_release(self.repo.get_build(self.db, published['contentKey']), source['manifest']), released['release'])
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.start_formal_audio_asr.assert_not_called()
        self.assertEqual(self.parent_rows(), self.before_rows)
        self.assertEqual(self.source_files(), self.before_files)


class SavedQuizAliasVisualTests(SavedVisualRevisionTests):
    fixture_quiz_alias = True

    def test_quiz_alias_bytes_and_binding_are_preserved_and_tampering_is_rejected(self):
        self.patch.update(schemaVersion=VISUAL_PATCH_SCHEMA, changes=[])
        parent = {'preview': self.service.get(self.source_key)}
        prepared = self.prepare(visual_patch=fixtures.visual_patch_for(parent))
        original, candidate, _, _ = load_prepared(self.output, verify_assets=True)
        self.assertEqual(len(candidate['parent']['audioAliases']), 1)
        alias = candidate['parent']['audioAliases'][0]
        self.assertEqual(alias['audioSha256'], sha_bytes(self.audio))
        self.assertEqual((self.output / 'audio-aliases/question-1.wav').read_bytes(), self.audio)
        bad = deepcopy(original)
        review = json.loads(bad['build']['review_json'])
        q = review['release']['classroom']['scenes'][-1]['content']['questions'][0]
        q['question'] = '别的问题。'
        review['release']['classroomSha256'] = digest(review['release']['classroom'])
        review['release']['sha256'] = digest({k: v for k, v in review['release'].items() if k != 'sha256'})
        bad['build']['review_json'] = canonical(review)
        with self.assertRaises(ApiError):
            validate_parent(bad, allow_saved_preview=True, allow_visual_ancestry=True)
        path = self.root / self.source_cid / 'audio/question-1.wav'
        path.write_bytes(b'wrong alias bytes')
        with self.assertRaises(ApiError):
            self.register()
        path.write_bytes(self.audio)
        self.register()
        target = self.root / prepared['classroomId'] / 'audio/question-1.wav'
        self.assertEqual(target.read_bytes(), self.audio)
        target.write_bytes(b'wrong target alias')
        self.configure_paid_mocks()
        narrate_preview(self.service, prepared['previewKey'], self.root)
        audit = self.audit(prepared['previewKey'])
        row = self.service.get(prepared['previewKey'])
        with self.assertRaises(ApiError):
            TextbookPublicationService(self.service).prepare(key=row['preview_key'], edition=row['edition_id'],
                revision=row['revision_id'], node=row['node_id'], teaching_revision='4', review={}, audio_audit=audit,
                classroom_directory=self.root)
