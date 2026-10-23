"""Pure visual revisions preserve approved pinyin evidence; synthetic media only."""
from copy import deepcopy
import json
import hashlib
import io
import wave
import unittest
from pathlib import Path
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import bind_interactive_audio
from content.textbook_operator_revision import (
    VISUAL_PATCH_SCHEMA, inheritance_provenance, revision_candidate, sha_text,
    validate_parent, validate_visual_audio_acceptance, validate_visual_candidate_content, visual_audio_acceptance,
    verify_inherited_segment, verify_inherited_segments,
)
from content.textbook_preview_audio_contract import asr_request_id, audit_contract_identity, tts_request_id, revision_audio_plan, compare_transcript
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from services.textbook_operator_revision_service import inherited_evidence, target_input
from services.textbook_preview_audio import core_content
from tests import test_textbook_pinyin_operator_review as review_fixtures
sign = review_fixtures.sign


class VisualPinyinInheritanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = review_fixtures.OperatorReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.f = self.fixture.f
        f.manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        f.plan['binding']['manifestSha256'] = digest(f.manifest)
        f.service.repository.get_revision.return_value = {'manifest_sha256': digest(f.manifest)}
        f.service.repository.manifest.return_value = f.manifest
        image = f'/api/classroom-media/{f.cid}/media/picture.png'
        picture = b'\x89PNG\r\n\x1a\nsynthetic-picture'
        media_dir = f.root / f.cid / 'media'; media_dir.mkdir()
        (media_dir / 'picture.png').write_bytes(picture)
        f.classroom['scenes'][0]['content'] = {'canvas': {'elements': [{'type': 'image', 'src': image}]}}
        source_input = json.loads(f.row['input_json'])
        source_input.update(manifestSha256=digest(f.manifest), executionPolicy='operator-authored-saved-classroom.v1', teachingRevision='1',
            authoring={'mode': 'openmaic_pro_workbench', 'request': 'synthetic pinyin'},
            originalMedia={'assets': [{'mediaPath': image, 'sha256': hashlib.sha256(picture).hexdigest()}]},
            sourceSha256=digest(f.classroom))
        f.key = digest(source_input); source_input['previewKey'] = f.key
        f.plan['previewKey'] = f.key
        receipts = json.loads(f.row['result_json'])['audioReceipts']
        if not getattr(self, 'human_review', False):
            f.classroom['scenes'][1]['actions'][0]['text'] = 'é，请再和老师一起读。'
        revision = revision_audio_plan(f.plan, revision_id='e' * 64, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=source_input)
        revision_folder = f.root / f.cid / 'textbook-preview-audio/narration-revisions' / revision['revisionId']
        revision_folder.mkdir(parents=True); (revision_folder / 'plan.json').write_text(canonical(revision))
        self.fixture.request_plans = [] if getattr(self, 'human_review', False) else [revision]
        audio_buffer = io.BytesIO()
        with wave.open(audio_buffer, 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\x10\x27\xf0\xd8' * 12000)
        audio = audio_buffer.getvalue()
        for scene, receipt, entry in zip(f.classroom['scenes'], receipts, f.audit['segments']):
            action = scene['actions'][0]; old = action['audioId']
            request_plan = revision if scene['id'] == 's2' and not getattr(self, 'human_review', False) else f.plan
            new = tts_request_id(request_plan, scene['id'], action['id'], action['text'])
            (f.root / f.cid / 'audio' / (new + '.wav')).write_bytes(audio)
            receipt.update(review_fixtures.fixtures.wav_receipt(audio))
            entry['audioSha256'] = receipt['audioSha256']
            action.update(audioId=new, audioUrl=f'/api/classroom-media/{f.cid}/audio/{new}.wav')
            receipt.update(requestId=new, previewAudioIdentity={'planSha256': digest(request_plan), 'attempt': 1})
            if request_plan is revision:
                from content.textbook_pinyin_pronunciation import provider_pronunciation
                receipt.update(narrationRevisionId=revision['revisionId'], classroomContentSha256=revision['classroomSha256'],
                    providerPronunciation=provider_pronunciation(action['text']), **review_fixtures.usage_receipt(action['text']))
                entry.update(text=action['text'], textSha256=sha_text(action['text']), transcript=action['text'],
                    comparison=compare_transcript(f.plan, action['text'], action['text']))
                entry['asr'].update(transcript=action['text'], transcriptSha256=sha_text(action['text']),
                    providerPronunciation=provider_pronunciation(action['text']))
            entry['ttsRequestId'] = new
            entry['asr']['requestId'] = asr_request_id(f.plan, new, receipt['audioSha256'])
        action = f.classroom['scenes'][1]['actions'][0]
        html = '<html><head><meta name="mira-responsive-activity" content="low-reading-v1"></head><body><img src="' + image + '"><script id="mira-narration-cues" type="application/json">' + canonical({
            'schemaVersion': 'mira.interactive.narration-cues.v1', 'cues': [{'id': 'speak', 'text': action['text']}]}) + '</script></body></html>'
        f.classroom['scenes'][1]['content']['html'] = bind_interactive_audio(html, {'speak': action['audioUrl']}, f.cid)
        f.classroom['scenes'][2]['content']['questions'][0]['questionAudioUrl'] = f.classroom['scenes'][0]['actions'][0]['audioUrl']
        f.row.update(preview_key=f.key, revision_id=f.manifest['revisionId'], input_json=canonical(source_input),
            classroom_sha256=digest(f.classroom), classroom_json=canonical(f.classroom), result_json=canonical({'audioReceipts': receipts}))
        f.audit.update(previewKey=f.key, sourceSha256=digest(f.classroom), contract=audit_contract_identity(f.plan)); sign(f.audit)
        f.review.update(sourceSha256=digest(f.classroom))
        self.fixture.browser.update(sourceSha256=digest(f.classroom), planSha256=digest(f.plan))
        self.fixture.browser['checks'][-1].update(ttsRequestId=receipts[0]['requestId'], audioSha256=receipts[0]['audioSha256']); sign(self.fixture.browser)
        self.fixture.review = self.fixture.make_review()
        (f.root / (f.cid + '.json')).write_text(canonical(f.classroom))
        (f.root / f.cid / 'textbook-preview-audio/plan.json').write_text(canonical(f.plan))
        (f.root / f.cid / 'textbook-preview-audio/receipts.json').write_text(canonical(receipts))
        self.fixture.add_synthetic_recheck()
        if getattr(self, 'human_review', False):
            from content.textbook_pinyin_pronunciation import LISTENING_SCHEMA
            from tests import test_textbook_pinyin_asr_reconciliation as reconciliation_fixtures
            heard = [{**{k: e[k] for k in ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256')},
                      'verdict': 'accepted', 'reviewer': 'Synthetic human fixture', 'reviewedAt': 1000,
                      'basis': 'SYNTHETIC TEST ONLY original listening evidence'} for e in f.audit['segments']]
            f.listening = sign({'schemaVersion': LISTENING_SCHEMA, 'previewKey': f.key,
                'planSha256': digest(f.plan), 'coreSha256': f.plan['coreSha256'], 'segments': heard})
            f.audit['listeningReview'] = f.listening; sign(f.audit)
            reconciliation = reconciliation_fixtures.PinyinAsrReconciliationTests().make_manifest({
                'plan': f.plan, 'classroom': f.classroom, 'audit': f.audit, 'listening_review': f.listening,
                'expected_source_sha256': f.row['classroom_sha256'], 'now_ms': 4000})
            source_release = f.service.prepare(key=f.key, edition=f.manifest['editionId'], revision=f.manifest['revisionId'],
                node='u2-l1', teaching_revision='1', review=f.review, audio_audit=f.audit,
                classroom_directory=f.root, asr_reconciliation=reconciliation)
        else:
            source_release = self.fixture.prepare()
        self.parent = {'build': f.build(source_release), 'manifest': f.manifest, 'preview': deepcopy(f.row),
                       'plan': deepcopy(f.plan), 'receipts': receipts, 'audit': deepcopy(f.audit)}
        if getattr(self, 'human_review', False) and self.fixture.request_plans:
            self.parent['sourceRequestPlans'] = deepcopy(self.fixture.request_plans)
        old = f.classroom['scenes'][1]['content']['html']
        self.visual = {'schemaVersion': 'mira.textbook.preview-visual-patch.v1', 'expectedSourceSha256': digest(f.classroom),
            'reviewer': 'synthetic reviewer', 'basis': 'test stateful gameplay', 'changes': [
                {'sceneId': 's2', 'beforeHtmlSha256': sha_text(old), 'html': old.replace('<body>', '<body><div data-state="editable"></div>', 1)}]}
        self.patch_value = {'schemaVersion': VISUAL_PATCH_SCHEMA, 'parentContentKey': self.parent['build']['content_key'],
            'expectedSourceSha256': digest(f.classroom), 'teachingRevision': '2', 'reviewer': 'synthetic reviewer',
            'basis': 'test pure HTML revision', 'changes': []}
        self.candidate = revision_candidate(self.parent, self.patch_value, self.visual)
        self.input = target_input(self.parent, self.candidate)
        self.plan = {**deepcopy(f.plan), 'previewKey': self.input['previewKey'],
            'classroomSha256': digest(self.candidate['classroom']), 'coreSha256': digest(core_content(self.candidate['classroom'])),
            'revisionId': self.candidate['revisionId'], 'parentPlanSha256': digest(f.plan)}
        self.provenance = inheritance_provenance(self.candidate, self.plan)
        self.archive = f.root / 'synthetic-parent-archive'; (self.archive / 'audio').mkdir(parents=True)
        for receipt in receipts:
            name = receipt['requestId'] + '.wav'
            (self.archive / 'audio' / name).write_bytes((f.root / f.cid / 'audio' / name).read_bytes())
        self.context = {'parent': self.parent, 'candidate': self.candidate, 'provenance': self.provenance,
            'archive': self.archive, 'segments': {(s['sceneId'], s['actionId']): s for s in self.candidate['inheritedSegments']}}
        by_id = {r['requestId']: r for r in receipts}
        entries = [inherited_evidence(self.context, self.plan, scene, action, by_id[action['audioId']])
                   for scene in self.candidate['classroom']['scenes'] for action in scene.get('actions', []) if action['type'] == 'speech']
        self.audit = sign({'schemaVersion': 'mira.textbook.audio-audit.v2', 'previewKey': self.plan['previewKey'],
            'sourceSha256': digest(self.candidate['classroom']), 'contract': audit_contract_identity(self.plan),
            'operatorParentProvenanceSha256': self.provenance['sha256'], 'segments': entries,
            'passed': all(e['comparison']['passed'] for e in entries)})
        self.evidence = visual_audio_acceptance(self.parent, self.candidate, self.plan, self.provenance)

    def validate(self, evidence=None, room=None, audit=None):
        return validate_visual_audio_acceptance(evidence or self.evidence, plan=self.plan, provenance=self.provenance,
            classroom=room or self.candidate['classroom'], audit=audit or self.audit)

    def test_exact_approved_audio_transfers_without_rewriting_failed_literal_asr(self):
        self.assertFalse(self.parent['audit']['passed'])
        self.assertFalse(self.audit['passed'])
        self.assertEqual(len(self.validate()), 2)
        self.assertEqual(self.evidence['parentEvidence']['build'], self.parent['build'])
        self.assertNotIn('humanListeningVerified', self.evidence)
        with self.assertRaises(ApiError):
            validate_parent(self.parent)  # Legacy v1/v2 behavior is unchanged.

    def test_cached_source_validation_is_detached_and_full_evidence_bound(self):
        origin = validate_parent(self.parent, allow_saved_preview=True, allow_visual_ancestry=True)
        origin['teacher'].clear()
        fresh = validate_parent(self.parent, allow_saved_preview=True, allow_visual_ancestry=True)
        self.assertEqual(fresh['teacher'], self.parent['plan']['teacher'])
        bad = deepcopy(self.parent)
        bad['receipts'][0]['audioSha256'] = '0' * 64
        with self.assertRaises(ApiError):
            validate_parent(bad, allow_saved_preview=True, allow_visual_ancestry=True)

    def test_batch_keeps_later_segment_and_whole_candidate_integrity_checks(self):
        receipts = {r['requestId']: r for r in self.parent['receipts']}
        segments = [(scene, action, receipts[action['audioId']])
                    for scene in self.candidate['classroom']['scenes']
                    for action in scene.get('actions', []) if action['type'] == 'speech']
        expected = [verify_inherited_segment(self.parent, self.candidate, self.plan,
                    self.provenance, *segment) for segment in segments]
        self.assertGreater(len(segments), 1)
        with patch('content.textbook_operator_revision.revision_candidate', wraps=revision_candidate) as rebuild:
            actual = verify_inherited_segments(self.parent, self.candidate, self.plan,
                                               self.provenance, segments)
        self.assertEqual(actual, expected)
        self.assertEqual(rebuild.call_count, 1)
        changed = deepcopy(segments)
        changed[-1][2]['audioSha256'] = '0' * 64
        with self.assertRaises(ApiError):
            verify_inherited_segments(self.parent, self.candidate, self.plan, self.provenance, changed)
        changed = deepcopy(self.candidate)
        changed['classroom']['scenes'][-1]['title'] = 'Changed after review'
        with self.assertRaises(ApiError):
            verify_inherited_segments(self.parent, changed, self.plan, self.provenance, segments)

    def test_rejects_changed_quiz_speech_audio_teacher_or_forged_source_review(self):
        for mutate in (
            lambda r: r['scenes'][0]['actions'][0].update(text='new speech'),
            lambda r: r['scenes'][0]['actions'][0].update(audioId='changed'),
            lambda r: r['scenes'][0]['actions'][0]['audioMetadata'].update(voiceId='other'),
            lambda r: r['scenes'][2]['content']['questions'][0].update(answer=['B']),
            lambda r: r['scenes'][1]['content'].update(html='replaced'),
        ):
            room = deepcopy(self.candidate['classroom']); mutate(room)
            with self.assertRaises(ApiError): self.validate(room=room)
        evidence = deepcopy(self.evidence)
        frozen = json.loads(evidence['parentEvidence']['build']['review_json'])
        if getattr(self, 'human_review', False):
            frozen['release']['audioAudit']['listeningReview']['segments'][0]['verdict'] = 'rejected'
        else:
            frozen['release']['audioAudit']['pronunciationReview']['humanListeningVerified'] = True
        evidence['parentEvidence']['build']['review_json'] = canonical(frozen); sign(evidence)
        with self.assertRaises(ApiError): self.validate(evidence=evidence)
        audit = deepcopy(self.audit); audit['passed'] = True; sign(audit)
        with self.assertRaises(ApiError): self.validate(audit=audit)

    def test_prepare_register_narrate_collect_publish_with_original_revision_plan(self):
        from contextlib import redirect_stdout
        import io
        from unittest.mock import Mock
        from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
        from repositories.textbook_repository import TextbookRepository
        from services.textbook_preview_service import TextbookPreviewService
        from services.textbook_publication_service import TextbookPublicationService
        from services.textbook_operator_revision_service import prepare_revision, register_revision, load_prepared
        from services.textbook_preview_audio import narrate_preview
        from scripts import audit_textbook_audio
        from tests.test_textbook_learning import IsolatedDatabase
        f = self.f
        db = IsolatedDatabase(('082_fixed_textbook_learning.sql', '083_textbook_course_previews.sql', '087_learning_course_reuse.sql'))
        self.addCleanup(db.raw.close)
        for field in ('node_code TEXT', 'title TEXT', 'objective TEXT', 'published_at INT', 'created_at INT', 'updated_at INT'):
            db.raw.execute('ALTER TABLE learning_courses ADD COLUMN ' + field)
        repo = TextbookRepository(db)
        row = {**self.parent['preview'], 'runtime_origin': 'http://127.0.0.1:3100', 'runtime_job_id': 'synthetic',
               'created_at': 1, 'updated_at': 1}
        with repo.transaction() as conn:
            repo.import_revision(conn, f.manifest, 1)
            conn.execute('INSERT INTO learning_textbook_course_previews (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            build, _ = repo.reserve_build(conn, json.loads(self.parent['build']['input_json']), 1)
            course = {'id': 'synthetic-source', 'version': '1', 'content_json': canonical({'title': 'synthetic'})}
            conn.execute("INSERT INTO learning_courses(id,version,grade_code,subject,status,quality_status,content_json) VALUES (?,?,?,?,'published','released',?)",
                         (course['id'], course['version'], 'primary_1', 'chinese', course['content_json']))
            repo.bind_published(conn, build, course, json.loads(self.parent['build']['review_json']), 1)
        docs = {f.cid: deepcopy(f.classroom)}
        runtime = Mock(base_url='http://127.0.0.1:3100')
        def read(cid):
            if cid not in docs:
                raise OpenMaicFullRuntimeError('not_found', 'synthetic missing', status_code=404)
            return deepcopy(docs[cid])
        def save(room):
            docs[room['id']] = {**deepcopy(room), 'createdAt': 2}
            (f.root / (room['id'] + '.json')).write_text(canonical(docs[room['id']]))
        runtime.get_classroom.side_effect = read; runtime.save_preview_classroom.side_effect = save
        service = TextbookPreviewService(repo, runtime)
        source_audit = f.root / 'source-audit'; source_audit.mkdir()
        (source_audit / 'audit.json').write_text(canonical(self.parent['audit']))
        for entry in self.parent['audit']['segments']:
            (source_audit / (entry['asr']['requestId'] + '.json')).write_text(canonical(entry))
        # Candidate storage is independent of the classroom root.
        output = f.root.parent / (f.root.name + '-visual-candidate')
        self.addCleanup(lambda: __import__('shutil').rmtree(output, ignore_errors=True))
        prepared = prepare_revision(service, self.parent['build']['content_key'], f.root, self.patch_value,
                                    source_audit / 'audit.json', output, visual_patch=self.visual)
        archived_parent, candidate, frozen, intent = load_prepared(output, verify_assets=True)
        self.assertEqual(any(name.startswith('source-request-plans/') for name in intent['files']), not getattr(self, 'human_review', False))
        register_revision(service, output, f.root, budget_reference='synthetic pure visual')
        plan = json.loads((f.root / prepared['classroomId'] / 'textbook-preview-audio/plan.json').read_text())
        self.assertEqual(plan['teacher'], f.plan['teacher'])
        self.assertEqual(plan['pronunciationPolicy'], f.plan['pronunciationPolicy'])
        narrate_preview(service, prepared['previewKey'], f.root)
        argv = ['audit', '--key', prepared['previewKey'], '--classroom-directory', str(f.root),
                '--output', str(f.root / 'target-audit'), '--collect-only']
        with patch.object(audit_textbook_audio.AppConfig, 'from_env'), patch.object(audit_textbook_audio, 'Database', return_value=db), \
             patch.object(audit_textbook_audio, 'OpenMaicFullRuntimeClient', return_value=runtime), patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            audit_textbook_audio.main()
        audit = json.loads((f.root / 'target-audit/audit.json').read_text())
        self.assertFalse(audit['passed'])
        target = service.get(prepared['previewKey'])
        publisher = TextbookPublicationService(service)
        review = {**f.review, 'sourceSha256': target['classroom_sha256'], 'reviewedAt': now_ms() - 1}
        released = publisher.prepare(key=target['preview_key'], edition=target['edition_id'], revision=target['revision_id'],
            node=target['node_id'], teaching_revision='2', review=review, audio_audit=audit, classroom_directory=f.root)
        receipt = publisher.publish(released)
        self.assertEqual(validate_release(repo.get_build(db, receipt['contentKey']), f.manifest), released['release'])
        runtime.start_formal_audio_tts.assert_not_called()
        runtime.start_formal_audio_asr.assert_not_called()
        # Request-plan evidence must still be exact at registration, even after
        # the semantic source release passed validation.
        request_file = (output / 'source-audit.json' if getattr(self, 'human_review', False)
                        else next(output.glob('source-request-plans/*.json')))
        request_file.write_text('{}')
        with self.assertRaises(ApiError):
            load_prepared(output, verify_assets=True)

    def test_publication_and_portable_release_revalidate_original_review(self):
        f = self.f; room = self.candidate['classroom']; cid = room['id']; key = self.input['previewKey']
        folder = f.root / cid / 'textbook-preview-audio'; folder.mkdir(parents=True)
        (folder / 'plan.json').write_text(canonical(self.plan)); (f.root / (cid + '.json')).write_text(canonical(room))
        (f.root / cid / 'audio').mkdir()
        for segment in self.candidate['inheritedSegments']:
            name = segment['ttsRequestId'] + '.wav'
            (f.root / cid / 'audio' / name).write_bytes((self.archive / 'audio' / name).read_bytes())
        f.row.update(preview_key=key, classroom_id=cid, classroom_json=canonical(room), classroom_sha256=digest(room), input_json=canonical(self.input))
        review = {**f.review, 'sourceSha256': digest(room), 'reviewedAt': now_ms() - 1}
        with patch('services.textbook_operator_revision_service.load_inheritance', return_value=self.context), \
             patch('services.textbook_operator_revision_service._same_parent'):
            prepared = f.service.prepare(key=key, edition=f.manifest['editionId'], revision=f.manifest['revisionId'],
                node='u2-l1', teaching_revision='2', review=review, audio_audit=self.audit, classroom_directory=f.root)
        build = {**f.build(prepared), 'teaching_revision': '2'}
        released = validate_release(build, f.manifest)
        self.assertEqual(released['audioAudit']['acceptanceMethod'], 'unchanged-published-audio')
        self.assertFalse(released['audioAudit']['literalPassed'])
        self.assertNotIn('pronunciationReview', released['audioAudit'])
        self.assertEqual(released['audioAudit']['visualAudioInheritance'], self.evidence)
        f.service.preview.runtime.start_formal_audio_tts.assert_not_called()
        f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_compact_audio_delivery_preserves_exact_helper_and_source_audio_identity(self):
        from content.textbook_release import MEDIA
        candidate = self.candidate
        room = deepcopy(candidate['classroom'])
        source = {a['mediaPath']: a['sha256'] for a in candidate['parent']['originalMedia']['assets']}
        source.update({f"/api/classroom-media/{room['id']}/audio/{s['ttsRequestId']}.wav": s['audioSha256']
                       for s in candidate['inheritedSegments']})
        media = {}
        def replace(match):
            original = match.group(0)
            sha = source[original]
            audio = match[2].startswith('audio/')
            delivered_sha = sha_text('compact:' + sha)
            path = f"/api/classroom-media/tbpub_compact/{'audio' if audio else 'media'}/{delivered_sha}{'.mp3' if audio else '.webp'}"
            media[path] = {'path': path, 'sha256': delivered_sha, 'sourceSha256': sha}
            return path
        room = json.loads(MEDIA.sub(replace, canonical(room)))
        validate_visual_candidate_content(candidate, room, media=list(media.values()))
        broken = deepcopy(room)
        interactive = next(s for s in broken['scenes'] if s['type'] == 'interactive')
        interactive['content']['html'] = interactive['content']['html'].replace('previous.pause();', '', 1)
        with self.assertRaises(ValueError):
            validate_visual_candidate_content(candidate, broken, media=list(media.values()))
        changed_media = deepcopy(list(media.values()))
        next(m for m in changed_media if '/audio/' in m['path'])['sourceSha256'] = '0' * 64
        with self.assertRaises(ApiError):
            validate_visual_candidate_content(candidate, room, media=changed_media)


class VisualHumanPinyinInheritanceTests(VisualPinyinInheritanceTests):
    human_review = True


if __name__ == '__main__':
    unittest.main()
