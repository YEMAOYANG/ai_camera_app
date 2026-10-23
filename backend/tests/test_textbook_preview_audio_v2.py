"""Cross-subject preview audio uses isolated SQLite, temporary media and mocks."""
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import io
import hashlib
import json
import unittest
from unittest.mock import patch

from content.textbook_audio_language import ENGLISH_AUTO_LANGUAGE_POLICY_SHA256
from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import AUDIO_SCRIPT, without_audio_helper
from content.textbook_preview_audio_contract import new_audio_plan
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts import audit_textbook_audio as audit_script
from scripts import textbook_preview as preview_script
from services import textbook_preview_audio as audio_service
from services.textbook_preview_audio import core_content, narrate_preview
from services.textbook_preview_narration_revision import SCHEMA, revise_preview_narration
from services.textbook_preview_visual_revision import sha_bytes
from services.textbook_publication_service import TextbookPublicationService
from tests import test_textbook_preview_visual_revision as fixtures
from content.textbook_preview_audio_contract import tts_request_id


def policy_receipt():
    return {'policyVersion': 'mira.textbook.english-auto-language.v1',
            'policySha256': ENGLISH_AUTO_LANGUAGE_POLICY_SHA256, 'providerBodySha256': 'f' * 64}


class PreviewAudioV2Tests(unittest.TestCase):
    def fixture(self, subject='chinese', first_text=None, text_overrides=None):
        f = fixtures.VisualRevisionTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        row = f.service.get(f.key)
        frozen = json.loads(row['input_json'])
        with f.service.repository.transaction() as conn:
            revision = f.service.repository.get_revision(conn, row['edition_id'], row['revision_id'])
            manifest = f.service.repository.manifest(revision)
            manifest['subject'] = subject
            conn.execute('UPDATE learning_textbook_revisions SET subject=?,manifest_json=?,manifest_sha256=?',
                         (subject, canonical(manifest), digest(manifest)))
        frozen.update(subject=subject, manifestSha256=digest(manifest))
        f.db.execute('UPDATE learning_textbook_course_previews SET input_json=? WHERE preview_key=?',
                     (canonical(frozen), f.key))
        if first_text:
            f.classroom['scenes'][0]['actions'][0]['text'] = first_text
        for action_id, text in (text_overrides or {}).items():
            action = next((action for scene in f.classroom['scenes']
                           for action in scene.get('actions', [])
                           if action.get('id') == action_id), None)
            if action is None:
                raise AssertionError('unknown fixture speech action: ' + action_id)
            action['text'] = text
        f.plan = new_audio_plan(preview_key=f.key, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=frozen)
        teacher = f.plan['teacher']
        replacements = {}
        for scene, receipt in zip(f.classroom['scenes'], f.result['audioReceipts']):
            action = scene['actions'][0]
            old = action['audioId']
            request = tts_request_id(f.plan, scene['id'], action['id'], action['text'])
            replacements[old] = request
            (f.root / f.cid / 'audio' / (request + '.wav')).write_bytes((f.root / f.cid / 'audio' / (old + '.wav')).read_bytes())
            receipt.update(requestId=request, previewAudioIdentity={'planSha256': digest(f.plan), 'attempt': 1})
            if subject == 'english':
                receipt['providerLanguagePolicy'] = policy_receipt()
            action['audioMetadata'] = {'schemaVersion': 'mira.openmaic.speech-audio.v1',
                'providerId': teacher['tts']['providerId'], 'modelId': teacher['tts']['modelId'],
                'voiceId': teacher['voiceId'], 'fallbackUsed': False}
        raw = canonical(f.classroom)
        for old, new in replacements.items():
            raw = raw.replace(old, new)
        f.classroom = json.loads(raw)
        self.persist(f)
        (f.folder / 'plan.json').write_text(canonical(f.plan))
        f.source_sha = digest(f.classroom)
        html = f.classroom['scenes'][5]['content']['html']
        f.patch['expectedSourceSha256'] = f.source_sha
        f.patch['changes'][0].update(beforeHtmlSha256=sha_bytes(html.encode()), html=html.replace('M10 20H30', 'M10 20H30 M20 10V30'))
        f.runtime.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
        f.transcript_override = None
        f.transcript_overrides = {}
        def recognize(**kwargs):
            action = next(a for s in f.classroom['scenes'] for a in s.get('actions', []) if a.get('id') == kwargs['action_id'])
            text = f.transcript_overrides.get(kwargs['action_id'],
                f.transcript_override if kwargs['action_id'] == 'action-0'
                and f.transcript_override is not None else action['text'])
            result = {'status': 'succeeded', 'completionUsable': True,
                      'requestId': kwargs['request_id'], 'transcript': text,
                      'transcriptSha256': sha_bytes(text.encode())}
            if subject == 'english':
                result['providerLanguagePolicy'] = policy_receipt()
            return result
        f.runtime.start_formal_audio_asr.side_effect = recognize
        return f

    def persist(self, f):
        f.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=?,result_json=? WHERE preview_key=?',
                     (canonical(f.classroom), digest(f.classroom), canonical(f.result), f.key))
        f.db.raw.commit()
        (f.root / (f.cid + '.json')).write_text(canonical(f.classroom))
        (f.folder / 'receipts.json').write_text(canonical(f.result.get('audioReceipts', [])))

    def audit(self, f, extra_args=()):
        output = f.root / 'audit'
        argv = ['audit_textbook_audio.py', '--key', f.key, '--classroom-directory', str(f.root), '--output', str(output), *extra_args]
        with patch.object(audit_script.AppConfig, 'from_env'), patch.object(audit_script, 'Database', return_value=f.db), \
                patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=f.runtime), \
                patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            audit_script.main()
        return json.loads((output / 'audit.json').read_text())

    def prepare(self, f, audit):
        row = f.service.get(f.key)
        review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
                  'publicationAuthorized': True, 'reviewer': 'test', 'basis': 'isolated review',
                  'sourceSha256': row['classroom_sha256'], 'reviewedAt': now_ms() - 1}
        return TextbookPublicationService(f.service).prepare(key=f.key, edition=row['edition_id'],
            revision=row['revision_id'], node=row['node_id'], teaching_revision='v2-test', review=review,
            audio_audit=audit, classroom_directory=f.root)

    def english_reconciliation(self, f, audit, segment_rules=None):
        from content import textbook_english_asr_reconciliation as english
        if segment_rules is None:
            segment_rules = {0: [
                {'side': 'expected', 'from': 'Lily', 'to': '莉莉',
                 'sourceOccurrences': 2, 'matchIndex': 1},
                {'side': 'expected', 'from': "name's", 'to': 'name is',
                 'sourceOccurrences': 1, 'matchIndex': 1},
            ]}
        speech = [{'sceneId': scene['id'], 'actionId': action['id'],
                   'text': action['text'], 'audioId': action.get('audioId')}
                  for scene in f.classroom['scenes'] for action in scene.get('actions', [])
                  if action.get('type') == 'speech']
        entries = []
        for index, rules in segment_rules.items():
            entry = audit['segments'][index]
            rewritten = entry['text']
            for rule in rules:
                rewritten = english._replace_registered(rewritten, rule)
            normalized = english._normalize(rewritten)
            entries.append({'previewKey': f.plan['previewKey'], 'planSha256': digest(f.plan),
                'sourceClassroomId': f.classroom['id'], 'sourceSha256': digest(f.classroom),
                'sourceSpeechSha256': digest(speech), 'sceneId': entry['sceneId'],
                'actionId': entry['actionId'], 'textSha256': entry['textSha256'],
                'ttsRequestId': entry['ttsRequestId'], 'audioSha256': entry['audioSha256'],
                'asrRequestId': entry['asr']['requestId'],
                'transcriptSha256': entry['asr']['transcriptSha256'],
                'auditSegmentSha256': digest(entry), 'asrReceiptSha256': digest(entry['asr']),
                'literalSimilarityBps': entry['similarityBps'],
                'rules': rules, 'normalizedSha256': sha_bytes(normalized.encode())})
        registry = {'schemaVersion': 'mira.textbook.english-asr-orthography-registry.v1',
            'entries': entries}
        registry['sha256'] = digest(registry)
        with patch.object(english, 'REGISTRY', registry):
            evidence = english.build_evidence(plan=f.plan, classroom=f.classroom,
                audit_entries=[audit['segments'][index] for index in segment_rules],
                expected_source_sha256=digest(f.classroom),
                recorded_at=now_ms())
        return english, registry, evidence

    def unnarrated(self):
        f = self.fixture()
        audio = next((f.root / f.cid / 'audio').glob('*.wav')).read_bytes()
        f.classroom = core_content(f.classroom)
        for scene in f.classroom['scenes']:
            if scene['type'] == 'interactive':
                scene['content']['html'] = without_audio_helper(scene['content']['html'])
            for question in scene['content'].get('questions', []):
                question.pop('questionAudioUrl', None)
        f.result = {}
        self.persist(f)
        f.db.execute("UPDATE learning_textbook_course_previews SET status='review_required' WHERE preview_key=?", (f.key,))
        f.db.raw.commit()
        (f.folder / 'plan.json').unlink()
        f.provider_receipts = {}
        def read(request, **_policy_options):
            if request not in f.provider_receipts:
                raise OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
            return deepcopy(f.provider_receipts[request])
        def speak(**kw):
            value = {'requestId': kw['request_id'], 'status': 'succeeded', 'audioSha256': sha_bytes(audio)}
            f.provider_receipts[kw['request_id']] = value
            return deepcopy(value)
        f.runtime.get_formal_audio_tts.side_effect = read
        f.runtime.start_formal_audio_tts.side_effect = speak
        f.runtime.download_formal_audio_tts.return_value = audio
        return f

    def selection(self, f, *indexes):
        return {'schemaVersion': 'mira.textbook.speech-selection.v1', 'previewKey': f.key,
                'coreSha256': digest(core_content(f.classroom)),
                'speeches': [{'sceneId': f'scene-{i}', 'actionId': f'action-{i}'} for i in indexes]}

    def recorded_retry(self, status='ambiguous', index=1):
        f = self.unnarrated()
        selection = self.selection(f, index)
        f.runtime.start_formal_audio_tts.side_effect = lambda **kw: {
            'requestId': kw['request_id'], 'status': status, 'audioSha256': None}
        narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        plan_path = f.folder / 'plan.json'
        receipts_path = f.folder / 'receipts.json'
        plan = json.loads(plan_path.read_text())
        fences = {'planSha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                  'coreSha256': selection['coreSha256'],
                  'classroomSha256': f.service.get(f.key)['classroom_sha256'],
                  'receiptsSha256': hashlib.sha256(receipts_path.read_bytes()).hexdigest()}
        f.runtime.get_formal_audio_tts.reset_mock()
        f.runtime.start_formal_audio_tts.reset_mock()
        return f, selection, plan, fences

    def test_sample_stays_partial_and_full_narration_reuses_exact_successes(self):
        f = self.unnarrated()
        selection = self.selection(f, 0, 5)
        original_core = selection['coreSha256']
        progress = []
        result = narrate_preview(f.service, f.key, f.root, speech_selection=selection, progress=progress.append)
        plan_bytes = (f.folder / 'plan.json').read_bytes()
        plan = json.loads(plan_bytes)
        self.assertEqual(plan['coreSha256'], original_core)
        self.assertEqual({c.kwargs['action_id'] for c in f.runtime.start_formal_audio_tts.call_args_list}, {'action-0', 'action-5'})
        self.assertTrue(all(p['totalAudio'] == 8 for p in progress))
        self.assertEqual((result['status'], result['result']['audioPartial']), ('review_required', True))
        self.assertEqual((result['result']['audioCompleted'], result['result']['audioTotal']), (2, 8))
        self.assertNotIn('frozenPreview', result['result'])
        self.assertNotIn(AUDIO_SCRIPT, f.classroom['scenes'][5]['content']['html'])
        self.assertNotIn('questionAudioUrl', f.classroom['scenes'][6]['content']['questions'][0])
        with self.assertRaises(ApiError): f.service.freeze(f.key)
        with self.assertRaises(ApiError): self.prepare(f, {})
        sample_receipts = json.loads((f.folder / 'receipts.json').read_text())
        sample_bytes = {r['requestId']: (f.root / f.cid / 'audio' / (r['requestId'] + '.wav')).read_bytes()
                        for r in sample_receipts}
        # Repeating the same selection does not even query or redownload a
        # successful clip, and completing the lesson keeps its original plan.
        gets = f.runtime.get_formal_audio_tts.call_count
        narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(f.runtime.get_formal_audio_tts.call_count, gets)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 2)
        full = narrate_preview(f.service, f.key, f.root)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 8)
        self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 8)
        self.assertEqual((full['status'], full['result']['audioPartial']), ('preview_ready', False))
        self.assertEqual(full['result']['audioCompleted'], 8)
        self.assertEqual((f.folder / 'plan.json').read_bytes(), plan_bytes)
        self.assertIn(AUDIO_SCRIPT, f.classroom['scenes'][5]['content']['html'])
        self.assertIn('questionAudioUrl', f.classroom['scenes'][6]['content']['questions'][0])
        final_receipts = {r['requestId']: r for r in json.loads((f.folder / 'receipts.json').read_text())}
        for receipt in sample_receipts:
            request = receipt['requestId']
            self.assertEqual(final_receipts[request], receipt)
            self.assertEqual((f.root / f.cid / 'audio' / (request + '.wav')).read_bytes(), sample_bytes[request])

    def test_invalid_sample_is_rejected_before_runtime_or_plan_creation(self):
        f = self.unnarrated()
        valid = self.selection(f, 0)
        invalid = [[], {}, {**valid, 'speeches': []}, {**valid, 'speeches': valid['speeches'] * 2},
                   {**valid, 'speeches': [{'sceneId': 'scene-0', 'actionId': 'missing'}]},
                   {**valid, 'speeches': [{'sceneId': 'scene-0', 'actionId': ['action-0']}]},
                   {**valid, 'previewKey': 'another-preview'}, {**valid, 'coreSha256': '0' * 64},
                   {**valid, 'schemaVersion': 'unknown'}, {**valid, 'unexpected': True}]
        for selection in invalid:
            with self.subTest(selection=selection), self.assertRaises(ApiError) as error:
                narrate_preview(f.service, f.key, f.root, speech_selection=selection)
            self.assertEqual(error.exception.code, 'textbook_preview_audio_selection_invalid')
        self.assertFalse((f.folder / 'plan.json').exists())
        f.runtime.get_classroom.assert_not_called()
        f.runtime.get_formal_audio_tts.assert_not_called()
        f.runtime.start_formal_audio_tts.assert_not_called()

    def test_selecting_all_speeches_still_requires_explicit_full_completion(self):
        f = self.unnarrated()
        result = narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, *range(8)))
        self.assertEqual(result['result']['issues'], [])
        self.assertEqual(result['result']['audioCompleted'], 8)
        self.assertTrue(result['result']['audioPartial'])
        self.assertEqual(result['status'], 'review_required')
        with self.assertRaises(ApiError): f.service.freeze(f.key)
        with self.assertRaises(ApiError): self.prepare(f, {})
        self.assertNotIn(AUDIO_SCRIPT, f.classroom['scenes'][5]['content']['html'])
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 8)

    def test_unselected_receipts_including_crash_checkpoint_are_preserved(self):
        f = self.unnarrated()
        narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 0))
        plan = json.loads((f.folder / 'plan.json').read_text())
        f.result = json.loads(f.service.get(f.key)['result_json'])
        originals = deepcopy(f.result['audioReceipts'])
        for i, status in ((1, 'failed'), (2, 'ambiguous'), (3, 'succeeded'), (5, 'unknown')):
            scene = f.classroom['scenes'][i]
            request = tts_request_id(plan, scene['id'], scene['actions'][0]['id'], scene['actions'][0]['text'])
            originals.append({'requestId': request, 'status': status, 'audioSha256': None})
        # The last request was claimed after the DB checkpoint, before a crash.
        f.result['audioReceipts'] = deepcopy(originals[:-1])
        self.persist(f)
        (f.folder / 'receipts.json').write_text(canonical(originals))
        f.runtime.get_formal_audio_tts.reset_mock()
        f.runtime.start_formal_audio_tts.reset_mock()
        narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 4))
        after = json.loads(f.service.get(f.key)['result_json'])['audioReceipts']
        self.assertEqual(after[:-1], originals)
        self.assertEqual(json.loads((f.folder / 'receipts.json').read_text()), after)
        self.assertEqual(f.runtime.get_formal_audio_tts.call_count, 1)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_args.kwargs['action_id'], 'action-4')
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)

    def test_selected_recorded_unknown_or_failure_is_never_redispatched_on_404(self):
        for status in ('ambiguous', 'unknown', 'running', 'failed'):
            with self.subTest(status=status):
                f = self.unnarrated()
                narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 0))
                plan = json.loads((f.folder / 'plan.json').read_text())
                f.result = json.loads(f.service.get(f.key)['result_json'])
                request = tts_request_id(plan, 'scene-1', 'action-1', f.classroom['scenes'][1]['actions'][0]['text'])
                recorded = {'requestId': request, 'status': status, 'audioSha256': None}
                f.result['audioReceipts'].append(recorded)
                self.persist(f)
                f.runtime.start_formal_audio_tts.reset_mock()
                result = narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 1))
                self.assertEqual(result['result']['audioStopCode'], 'textbook_preview_audio_' + status)
                self.assertEqual(json.loads((f.folder / 'receipts.json').read_text())[-1], recorded)
                f.runtime.start_formal_audio_tts.assert_not_called()

    def test_new_ambiguous_sample_has_one_attempt_and_cannot_complete(self):
        f = self.unnarrated()
        f.runtime.start_formal_audio_tts.side_effect = lambda **kw: {
            'requestId': kw['request_id'], 'status': 'ambiguous', 'audioSha256': None}
        result = narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 0))
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(result['result']['audioStopCode'], 'textbook_preview_audio_ambiguous')
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(len(json.loads((f.folder / 'receipts.json').read_text())), 1)
        f.runtime.download_formal_audio_tts.assert_not_called()

    def test_explicit_recorded_failure_retry_dispatches_only_attempt_two_and_stops(self):
        f, selection, plan, fences = self.recorded_retry()
        audio = next((f.root / f.cid / 'audio').glob('*.wav')).read_bytes()
        f.runtime.start_formal_audio_tts.side_effect = lambda **kw: {
            'requestId': kw['request_id'], 'status': 'succeeded', 'audioSha256': sha_bytes(audio)}
        f.runtime.download_formal_audio_tts.return_value = audio
        progress = []
        result = narrate_preview(f.service, f.key, f.root, speech_selection=selection,
            retry_recorded_failure=True, retry_attempt=2, retry_fences=fences, progress=progress.append)
        action = f.classroom['scenes'][1]['actions'][0]
        expected = tts_request_id(plan, 'scene-1', 'action-1', action['text'], attempt=2)
        prior = tts_request_id(plan, 'scene-1', 'action-1', action['text'])
        self.assertEqual(f.runtime.get_formal_audio_tts.call_args.args[0], expected)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_args.kwargs['request_id'], expected)
        self.assertEqual(action['audioId'], expected)
        self.assertEqual(progress, [{'completedAudio': 2, 'totalAudio': 8}])
        self.assertEqual((result['result']['audioCompleted'], result['result']['audioPartial']), (1, True))
        self.assertFalse(any(a.get('audioId') for scene in f.classroom['scenes'][2:]
                             for a in scene.get('actions', []) if a.get('type') == 'speech'))
        receipts = json.loads((f.folder / 'receipts.json').read_text())
        self.assertEqual([(r['requestId'], r['status']) for r in receipts],
                         [(prior, 'ambiguous'), (expected, 'succeeded')])
        self.assertEqual(receipts[-1]['previewAudioIdentity'], {'planSha256': digest(plan), 'attempt': 2})
        claim = json.loads((f.folder / 'retry-claims' / (expected + '.json')).read_text())
        self.assertEqual((claim['priorRequestId'], claim['priorStatus'], claim['requestId'], claim['attempt']),
                         (prior, 'ambiguous', expected, 2))
        self.assertEqual(claim['fences'], fences)
        self.assertEqual(claim['sha256'], digest({k: v for k, v in claim.items() if k != 'sha256'}))

    def test_explicit_fifth_retry_keeps_four_failures_and_dispatches_once(self):
        f, selection, plan, fences = self.recorded_retry()
        action = f.classroom['scenes'][1]['actions'][0]
        receipts_path = f.folder / 'receipts.json'
        receipts = json.loads(receipts_path.read_text())
        for attempt in range(2, 5):
            receipts.append({'requestId': tts_request_id(plan, 'scene-1', 'action-1', action['text'], attempt=attempt),
                             'status': 'ambiguous', 'audioSha256': None,
                             'previewAudioIdentity': {'planSha256': digest(plan), 'attempt': attempt}})
        receipts_path.write_text(canonical(receipts))
        fences['receiptsSha256'] = hashlib.sha256(receipts_path.read_bytes()).hexdigest()
        f.runtime.start_formal_audio_tts.side_effect = lambda **kw: {
            'requestId': kw['request_id'], 'status': 'ambiguous', 'audioSha256': None}
        result = narrate_preview(f.service, f.key, f.root, speech_selection=selection,
            retry_recorded_failure=True, retry_attempt=5, retry_fences=fences)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_args.kwargs['request_id'],
                         tts_request_id(plan, 'scene-1', 'action-1', action['text'], attempt=5))
        self.assertEqual(result['result']['audioStopCode'], 'textbook_preview_audio_ambiguous')
        self.assertEqual(json.loads(receipts_path.read_text())[:4], receipts)
        self.assertEqual(len(json.loads(receipts_path.read_text())), 5)

    def test_explicit_recorded_failed_retry_is_permitted_and_still_stops(self):
        f, selection, plan, fences = self.recorded_retry(status='failed')
        audio = next((f.root / f.cid / 'audio').glob('*.wav')).read_bytes()
        f.runtime.start_formal_audio_tts.side_effect = lambda **kw: {
            'requestId': kw['request_id'], 'status': 'succeeded', 'audioSha256': sha_bytes(audio)}
        f.runtime.download_formal_audio_tts.return_value = audio
        narrate_preview(f.service, f.key, f.root, speech_selection=selection,
            retry_recorded_failure=True, retry_attempt=2, retry_fences=fences)
        action = f.classroom['scenes'][1]['actions'][0]
        expected = tts_request_id(plan, 'scene-1', 'action-1', action['text'], attempt=2)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(action['audioId'], expected)
        self.assertFalse(any(a.get('audioId') for scene in f.classroom['scenes'][2:]
                             for a in scene.get('actions', []) if a.get('type') == 'speech'))

    def test_recorded_failure_retry_rejects_nonterminal_prior_without_provider_call(self):
        for status in ('succeeded', 'running', 'unknown'):
            with self.subTest(status=status):
                f, selection, _plan, fences = self.recorded_retry(status=status)
                with self.assertRaises(ApiError) as error:
                    narrate_preview(f.service, f.key, f.root, speech_selection=selection,
                        retry_recorded_failure=True, retry_attempt=2, retry_fences=fences)
                self.assertEqual(error.exception.code, 'textbook_preview_audio_retry_invalid')
                f.runtime.get_formal_audio_tts.assert_not_called()
                f.runtime.start_formal_audio_tts.assert_not_called()

    def test_recorded_failure_retry_rejects_jump_multiple_selection_and_changed_fences(self):
        f, selection, _plan, fences = self.recorded_retry()
        cases = [
            ('attempt', selection, 3, fences),
            ('multiple', self.selection(f, 1, 2), 2, fences),
            ('different-action', self.selection(f, 2), 2, fences),
            *[(field, selection, 2, {**fences, field: '0' * 64}) for field in fences],
        ]
        for label, chosen, attempt, expected in cases:
            with self.subTest(case=label), self.assertRaises(ApiError):
                narrate_preview(f.service, f.key, f.root, speech_selection=chosen,
                    retry_recorded_failure=True, retry_attempt=attempt, retry_fences=expected)
        f.runtime.get_formal_audio_tts.assert_not_called()
        f.runtime.start_formal_audio_tts.assert_not_called()

    def test_recorded_failure_retry_refuses_existing_attempt_two_without_post(self):
        f, selection, plan, fences = self.recorded_retry()
        action = f.classroom['scenes'][1]['actions'][0]
        expected = tts_request_id(plan, 'scene-1', 'action-1', action['text'], attempt=2)
        f.provider_receipts[expected] = {'requestId': expected, 'status': 'succeeded',
                                         'audioSha256': 'a' * 64, 'mimeType': 'audio/wav'}
        with self.assertRaises(ApiError) as error:
            narrate_preview(f.service, f.key, f.root, speech_selection=selection,
                retry_recorded_failure=True, retry_attempt=2, retry_fences=fences)
        self.assertEqual(error.exception.code, 'textbook_preview_audio_retry_target_exists')
        self.assertEqual(f.runtime.get_formal_audio_tts.call_count, 1)
        f.runtime.start_formal_audio_tts.assert_not_called()
        self.assertFalse((f.folder / 'retry-claims' / (expected + '.json')).exists())

    def test_dispatch_timeout_retains_unknown_claim_and_missing_receipt_cannot_retry(self):
        f = self.unnarrated()
        selection = self.selection(f, 0)
        f.runtime.start_formal_audio_tts.side_effect = OpenMaicFullRuntimeError('timeout', 'unknown outcome')
        result = narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(result['result']['audioStopCode'], 'timeout')
        recorded = json.loads((f.folder / 'receipts.json').read_text())
        self.assertEqual(recorded[0]['status'], 'unknown')
        result = narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(result['result']['audioStopCode'], 'textbook_preview_audio_unknown')
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(json.loads((f.folder / 'receipts.json').read_text()), recorded)

    def test_sample_recovers_success_checkpoint_after_classroom_save_crash_without_new_tts(self):
        f = self.unnarrated()
        selection = self.selection(f, 0)
        f.runtime.save_preview_classroom.side_effect = OpenMaicFullRuntimeError('save_failed', 'crash')
        with self.assertRaises(OpenMaicFullRuntimeError):
            narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertNotIn('audioReceipts', json.loads(f.service.get(f.key)['result_json']))
        checkpoint = json.loads((f.folder / 'receipts.json').read_text())
        self.assertEqual(checkpoint[0]['status'], 'succeeded')
        f.runtime.save_preview_classroom.side_effect = f.save
        narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(f.runtime.get_formal_audio_tts.call_count, 1)
        self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 1)
        self.assertEqual(json.loads(f.service.get(f.key)['result_json'])['audioReceipts'], checkpoint)

    def test_unknown_to_success_save_crash_reconciles_only_authoritative_exact_receipt(self):
        f = self.unnarrated()
        selection = self.selection(f, 0)
        f.runtime.start_formal_audio_tts.side_effect = OpenMaicFullRuntimeError('timeout', 'unknown')
        narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        request = json.loads((f.folder / 'receipts.json').read_text())[0]['requestId']
        success = {'requestId': request, 'status': 'succeeded',
                   'audioSha256': sha_bytes(f.runtime.download_formal_audio_tts.return_value)}
        f.provider_receipts[request] = success
        f.runtime.save_preview_classroom.side_effect = OpenMaicFullRuntimeError('save_failed', 'lost before save')
        with self.assertRaises(OpenMaicFullRuntimeError):
            narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(json.loads(f.service.get(f.key)['result_json'])['audioReceipts'][0]['status'], 'unknown')
        checkpoint = (f.folder / 'receipts.json').read_bytes()
        f.runtime.save_preview_classroom.side_effect = f.save
        for changed in ({**success, 'audioSha256': '0' * 64}, {**success, 'status': 'running'},
                        {**success, 'requestId': 'another-request'}):
            with self.subTest(authority=changed):
                f.runtime.get_formal_audio_tts.side_effect = lambda _, value=changed: value
                with self.assertRaises(ApiError):
                    narrate_preview(f.service, f.key, f.root, speech_selection=selection)
                self.assertEqual((f.folder / 'receipts.json').read_bytes(), checkpoint)
                self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        f.runtime.get_formal_audio_tts.side_effect = lambda _: deepcopy(success)
        result = narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(result['result']['audioCompleted'], 1)
        self.assertEqual(json.loads(f.service.get(f.key)['result_json'])['audioReceipts'][0]['status'], 'succeeded')
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 1)

    def test_completed_binding_recovers_lost_save_response_or_db_write_without_tts(self):
        for boundary in ('response', 'database'):
            with self.subTest(boundary=boundary):
                f = self.unnarrated()
                narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 0))
                source = f.service.get(f.key)['classroom_sha256']
                plan = (f.folder / 'plan.json').read_bytes()
                def save_then_lose_response(value):
                    f.save(value)
                    raise OpenMaicFullRuntimeError('save_response_lost', 'saved without response')
                if boundary == 'response':
                    f.runtime.save_preview_classroom.side_effect = save_then_lose_response
                    with self.assertRaises(OpenMaicFullRuntimeError):
                        narrate_preview(f.service, f.key, f.root)
                else:
                    with patch.object(audio_service, 'store_audio_result', side_effect=RuntimeError('DB unavailable')):
                        with self.assertRaises(RuntimeError):
                            narrate_preview(f.service, f.key, f.root)
                self.assertEqual(f.service.get(f.key)['classroom_sha256'], source)
                self.assertIn(AUDIO_SCRIPT, f.classroom['scenes'][5]['content']['html'])
                final_bytes = (f.root / (f.cid + '.json')).read_bytes()
                receipts = (f.folder / 'receipts.json').read_bytes()
                saves = f.runtime.save_preview_classroom.call_count
                f.runtime.save_preview_classroom.side_effect = f.save
                recovered = narrate_preview(f.service, f.key, f.root)
                self.assertEqual(recovered['status'], 'preview_ready')
                self.assertFalse(recovered['result']['audioPartial'])
                self.assertEqual(recovered['result']['audioCompleted'], 8)
                self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 8)
                self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 8)
                self.assertEqual(f.runtime.save_preview_classroom.call_count, saves)
                self.assertEqual((f.root / (f.cid + '.json')).read_bytes(), final_bytes)
                self.assertEqual((f.folder / 'receipts.json').read_bytes(), receipts)
                self.assertEqual((f.folder / 'plan.json').read_bytes(), plan)

    def test_lost_save_recovery_rejects_real_edit_or_changed_wav_without_overwrite(self):
        for change in ('content', 'wav'):
            with self.subTest(change=change):
                f = self.unnarrated()
                narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 0))
                before = f.service.get(f.key)['classroom_sha256']
                def save_then_lose_response(value):
                    f.save(value)
                    raise OpenMaicFullRuntimeError('save_response_lost', 'saved without response')
                f.runtime.save_preview_classroom.side_effect = save_then_lose_response
                with self.assertRaises(OpenMaicFullRuntimeError):
                    narrate_preview(f.service, f.key, f.root)
                if change == 'content':
                    f.classroom['scenes'][0]['content']['canvas']['independentEdit'] = 'keep this'
                    f.save(f.classroom)
                else:
                    request = f.classroom['scenes'][0]['actions'][0]['audioId']
                    (f.root / f.cid / 'audio' / (request + '.wav')).write_bytes(b'changed')
                saved_bytes = (f.root / (f.cid + '.json')).read_bytes()
                saves = f.runtime.save_preview_classroom.call_count
                with self.assertRaises(ApiError):
                    narrate_preview(f.service, f.key, f.root)
                self.assertEqual(f.service.get(f.key)['classroom_sha256'], before)
                self.assertEqual((f.root / (f.cid + '.json')).read_bytes(), saved_bytes)
                self.assertEqual(f.runtime.save_preview_classroom.call_count, saves)
                self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 8)

    def test_sample_refuses_conflicting_checkpoint_before_any_provider_call(self):
        f = self.unnarrated()
        narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 0))
        receipts = json.loads((f.folder / 'receipts.json').read_text())
        receipts[0]['audioSha256'] = '0' * 64
        (f.folder / 'receipts.json').write_text(canonical(receipts))
        f.runtime.get_formal_audio_tts.reset_mock()
        f.runtime.start_formal_audio_tts.reset_mock()
        with self.assertRaises(ApiError):
            narrate_preview(f.service, f.key, f.root, speech_selection=self.selection(f, 1))
        f.runtime.get_formal_audio_tts.assert_not_called()
        f.runtime.start_formal_audio_tts.assert_not_called()

    def test_sample_cli_reads_bound_selection_and_rejects_other_actions(self):
        f = self.unnarrated()
        selection = f.root / 'selection.json'
        selection.write_text(canonical(self.selection(f, 0)))
        argv = ['textbook_preview.py', 'narrate', '--key', f.key, '--classroom-directory', str(f.root),
                '--speech-selection', str(selection)]
        with patch.object(preview_script.AppConfig, 'from_env'), patch.object(preview_script, 'Database', return_value=f.db), \
                patch.object(preview_script, 'OpenMaicFullRuntimeClient', return_value=f.runtime), \
                patch.object(preview_script, 'TextbookPreviewService', return_value=f.service), \
                patch('sys.argv', argv), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(preview_script.main(), 0)
        self.assertIn('"audioPartial": true', output.getvalue())
        argv[1] = 'freeze'
        with patch.object(preview_script.AppConfig, 'from_env') as config, patch('sys.argv', argv), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            preview_script.main()
        config.assert_not_called()

    def test_recorded_failure_retry_cli_requires_and_forwards_exact_fences(self):
        f, selection_value, plan, fences = self.recorded_retry()
        selection = f.root / 'retry-selection.json'
        selection.write_text(canonical(selection_value))
        audio = next((f.root / f.cid / 'audio').glob('*.wav')).read_bytes()
        f.runtime.start_formal_audio_tts.side_effect = lambda **kw: {
            'requestId': kw['request_id'], 'status': 'succeeded', 'audioSha256': sha_bytes(audio)}
        f.runtime.download_formal_audio_tts.return_value = audio
        argv = ['textbook_preview.py', 'narrate', '--key', f.key, '--classroom-directory', str(f.root),
                '--speech-selection', str(selection), '--retry-recorded-failure', '--attempt', '2',
                '--expected-plan-sha256', fences['planSha256'], '--expected-core-sha256', fences['coreSha256'],
                '--expected-classroom-sha256', fences['classroomSha256'],
                '--expected-receipts-sha256', fences['receiptsSha256']]
        with patch.object(preview_script.AppConfig, 'from_env'), patch.object(preview_script, 'Database', return_value=f.db), \
                patch.object(preview_script, 'OpenMaicFullRuntimeClient', return_value=f.runtime), \
                patch.object(preview_script, 'TextbookPreviewService', return_value=f.service), \
                patch('sys.argv', argv), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(preview_script.main(), 0)
        action = f.classroom['scenes'][1]['actions'][0]
        self.assertEqual(action['audioId'], tts_request_id(plan, 'scene-1', 'action-1', action['text'], attempt=2))
        self.assertIn('"audioCompleted": 1', output.getvalue())
        incomplete = argv[:-2]
        with patch.object(preview_script.AppConfig, 'from_env') as config, patch('sys.argv', incomplete), \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            preview_script.main()
        config.assert_not_called()

    def test_new_narration_dispatches_each_subject_teacher_and_english_policy(self):
        for subject in ('chinese', 'math', 'english', 'science'):
            with self.subTest(subject=subject):
                f = self.fixture(subject)
                audio = next((f.root / f.cid / 'audio').glob('*.wav')).read_bytes()
                f.classroom = {'id': f.cid, 'stage': {'id': f.cid}, 'scenes': [{'id': 'scene', 'order': 1,
                    'type': 'slide', 'content': {}, 'actions': [{'type': 'speech', 'id': 'line', 'text': '请看图片。'}]}]}
                f.result = {}
                self.persist(f)
                f.db.execute("UPDATE learning_textbook_course_previews SET status='review_required' WHERE preview_key=?", (f.key,))
                f.db.raw.commit()
                (f.folder / 'plan.json').unlink()
                f.runtime.get_formal_audio_tts.side_effect = OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
                def speak(**kw):
                    value = {'requestId': kw['request_id'], 'status': 'succeeded', 'audioSha256': sha_bytes(audio)}
                    if subject == 'english': value['providerLanguagePolicy'] = policy_receipt()
                    return value
                f.runtime.start_formal_audio_tts.side_effect = speak
                f.runtime.download_formal_audio_tts.return_value = audio
                narrate_preview(f.service, f.key, f.root)
                saved = json.loads((f.folder / 'plan.json').read_text())
                call = f.runtime.start_formal_audio_tts.call_args.kwargs
                self.assertEqual(call['subject'], subject)
                self.assertEqual(call['teacher_profile_id'], saved['teacher']['teacherProfile']['id'])
                self.assertEqual(call['request_id'], tts_request_id(saved, 'scene', 'line', '请看图片。'))

    def test_ready_fastpath_validates_contract_and_exact_request_without_dispatch(self):
        f = self.fixture('english')
        before = (f.folder / 'plan.json').read_bytes()
        narrate_preview(f.service, f.key, f.root)
        self.assertEqual((f.folder / 'plan.json').read_bytes(), before)
        f.runtime.start_formal_audio_tts.assert_not_called()
        f.runtime.get_classroom.assert_not_called()
        f.result['audioReceipts'][0]['previewAudioIdentity']['attempt'] = 2
        self.persist(f)
        with self.assertRaises(ApiError): narrate_preview(f.service, f.key, f.root)
        f.result['audioReceipts'][0]['previewAudioIdentity']['attempt'] = 1
        f.result['audioReceipts'][0].pop('providerLanguagePolicy')
        self.persist(f)
        with self.assertRaises(ApiError): narrate_preview(f.service, f.key, f.root)
        frozen = json.loads(f.service.get(f.key)['input_json'])
        frozen['subject'] = 'math'
        f.db.execute('UPDATE learning_textbook_course_previews SET input_json=? WHERE preview_key=?', (canonical(frozen), f.key))
        with self.assertRaises(ApiError): narrate_preview(f.service, f.key, f.root)
        f.runtime.start_formal_audio_tts.assert_not_called()

    def test_math_wrong_count_above_85_percent_cannot_publish_or_forge_policy_evidence(self):
        f = self.fixture('math', '请你仔细数一数校园里面一共有三个花盆。')
        f.transcript_override = '请你仔细数一数校园里面一共有四个花盆。'
        audit = self.audit(f)
        self.assertFalse(audit['passed'])
        self.assertGreaterEqual(audit['segments'][0]['similarityBps'], 8500)
        audit['passed'] = True
        audit['sha256'] = digest({k: v for k, v in audit.items() if k != 'sha256'})
        with self.assertRaises(ApiError): self.prepare(f, audit)
        audit['segments'][0]['comparison']['passed'] = True
        audit['sha256'] = digest({k: v for k, v in audit.items() if k != 'sha256'})
        with self.assertRaises(ApiError): self.prepare(f, audit)

    def test_strict_segment_gate_stops_before_dispatching_the_next_asr(self):
        f = self.fixture('english', '请跟老师说，Hello, I am Mia.')
        f.transcript_override = '请跟老师说，Hello, I am Nina.'
        output = f.root / 'strict-audit'
        argv = ['audit_textbook_audio.py', '--key', f.key,
                '--classroom-directory', str(f.root), '--output', str(output),
                '--strict-segment-gate']
        with patch.object(audit_script.AppConfig, 'from_env'), \
                patch.object(audit_script, 'Database', return_value=f.db), \
                patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=f.runtime), \
                patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'comparison did not pass'):
                audit_script.main()
        self.assertEqual(f.runtime.start_formal_audio_asr.call_count, 1)
        self.assertEqual(len(list(output.glob('tbbasr2_*.json'))), 1)
        self.assertFalse((output / 'audit.json').exists())

    def test_terminal_asr_recovery_keeps_failure_and_never_dispatches_twice(self):
        f = self.fixture('math', '这里有两位伙伴。')
        recognize = f.runtime.start_formal_audio_asr.side_effect
        def rejected(**kwargs):
            return {'requestId': kwargs['request_id'], 'status': 'failed',
                    'completionUsable': False, 'transcript': None, 'transcriptSha256': None}
        f.runtime.start_formal_audio_asr.side_effect = rejected
        with self.assertRaises(ApiError):
            self.audit(f)
        original_path = next((f.root / 'audit').glob('tbasr_*.json'))
        original_bytes = original_path.read_bytes()
        original = json.loads(original_bytes)
        rid = original['asr']['requestId']
        def lookup(request, **kwargs):
            if request == rid:
                return original['asr']
            raise OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
        f.runtime.get_formal_audio_asr.side_effect = lookup
        f.runtime.start_formal_audio_asr.side_effect = recognize
        audit = self.audit(f, ['--recover-failed-asr', rid])
        self.assertTrue(audit['passed'])
        prepared = self.prepare(f, audit)
        frozen = prepared['frozen']
        build = {'status': 'published', 'content_key': frozen['contentKey'],
            'node_id': frozen['textbookBinding']['nodeId'], 'teaching_revision': 'v2-test',
            'input_json': canonical(frozen), 'review_json': canonical(prepared['review'])}
        self.assertEqual(validate_release(build, prepared['manifest']), prepared['release'])
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(audit['segments'][0]['asr']['requestId'], rid + '_terminal1')
        from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
        self.assertEqual(OpenMaicFullRuntimeClient._formal_audio_request_id(rid + '_terminal1'), rid + '_terminal1')
        self.assertEqual(audit['segments'][0]['asrTerminalRecovery']['originalEntry'], original)
        calls = f.runtime.start_formal_audio_asr.call_count
        self.assertEqual(self.audit(f), audit)
        self.assertEqual(f.runtime.start_formal_audio_asr.call_count, calls)
        from content.textbook_preview_audio_contract import validate_v2_audit_segment, compare_transcript
        first = f.classroom['scenes'][0]
        action = first['actions'][0]
        changed = deepcopy(audit['segments'][0])
        changed['transcript'] = '这里有三位伙伴。'
        changed['asr']['transcript'] = changed['transcript']
        changed['asr']['transcriptSha256'] = sha_bytes(changed['transcript'].encode())
        changed['comparison'] = compare_transcript(f.plan, action['text'], changed['transcript'])
        changed['similarityBps'] = changed['comparison']['similarityBps']
        self.assertFalse(validate_v2_audit_segment(f.plan, action, changed, scene_id=first['id']))
        changed = deepcopy(audit['segments'][0])
        changed['asrTerminalRecovery']['originalEntry']['asr']['status'] = 'ambiguous'
        with self.assertRaises(ApiError):
            validate_v2_audit_segment(f.plan, action, changed, scene_id=first['id'])

    def test_terminal_asr_recovery_rejects_unresolved_or_successful_requests(self):
        from content.textbook_asr_terminal_recovery import evidence
        f = self.fixture('math', '这里有两位伙伴。')
        audit = self.audit(f)
        first = f.classroom['scenes'][0]
        action = first['actions'][0]
        original = deepcopy(audit['segments'][0])
        for status in ['running', 'unknown', 'ambiguous', 'succeeded']:
            original['asr']['status'] = status
            with self.assertRaises(ApiError):
                evidence(original, plan_sha256=digest(f.plan), action=action,
                    scene_id=first['id'], expected_request_id=original['asr']['requestId'],
                    audio_sha256=original['audioSha256'])

    def test_english_terminal_recovery_keeps_the_reserved_auto_language_namespace(self):
        from content.textbook_asr_terminal_recovery import request_id
        original = 'tbbasr2_' + 'a' * 64
        recovered = request_id(original)
        self.assertRegex(recovered, r'^tbbreasr2_[a-f0-9]{64}$')
        self.assertNotEqual(recovered, original)
        self.assertEqual(request_id(original), recovered)

    def test_registered_english_orthography_reconciliation_is_exact_and_provider_free(self):
        from content import textbook_english_asr_reconciliation as english
        f = self.fixture('english', "再听一次Lily的回答：My name's Lily.")
        f.transcript_override = '再听一次莉莉的回答，My name is Lily。'
        audit = self.audit(f)
        self.assertFalse(audit['passed'])
        self.assertEqual(audit['segments'][0]['similarityBps'], 7727)
        english, registry, evidence = self.english_reconciliation(f, audit)
        calls = f.runtime.start_formal_audio_asr.call_count
        with patch.object(english, 'REGISTRY', registry):
            accepted = english.validate_segment_evidence(evidence, plan=f.plan,
                classroom=f.classroom, audit_entry=audit['segments'][0],
                expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            complete = english.validate_reconciliation(evidence, plan=f.plan,
                classroom=f.classroom, audit=audit,
                expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            self.assertEqual(set(accepted), {(audit['segments'][0]['sceneId'], audit['segments'][0]['actionId'])})
            self.assertEqual(accepted, complete)
            self.assertFalse(accepted[next(iter(accepted))]['literalPassed'])
            self.assertTrue(accepted[next(iter(accepted))]['orthographicallyEquivalent'])
            bad = deepcopy(evidence)
            bad['segments'][0]['appliedRules'][0]['from'] = 'Billy'
            bad['sha256'] = digest({k: v for k, v in bad.items() if k != 'sha256'})
            with self.assertRaises(ApiError):
                english.validate_segment_evidence(bad, plan=f.plan, classroom=f.classroom,
                    audit_entry=audit['segments'][0], expected_source_sha256=digest(f.classroom),
                    now_ms=now_ms())
            other = deepcopy(audit['segments'][1])
            with self.assertRaises(ApiError):
                english.validate_segment_evidence(evidence, plan=f.plan, classroom=f.classroom,
                    audit_entry=other, expected_source_sha256=digest(f.classroom), now_ms=now_ms())
        self.assertEqual(f.runtime.start_formal_audio_asr.call_count, calls)

    def test_registered_english_contraction_reconciliation_is_segment_bound_and_not_global(self):
        from content import textbook_english_asr_reconciliation as english
        first = "再听一次Lily的回答：My name's Lily."
        second = ("介绍自己时也有两种说法。Lily这样说：My name's Lily. "
                  "Ben这样说：I'm Ben. 两种都可以。")
        f = self.fixture('english', text_overrides={'action-0': first, 'action-1': second})
        f.transcript_overrides = {
            'action-0': '再听一次莉莉的回答，My name is Lily。',
            'action-1': ("介绍自己时也有两种说法， Lily 这样说， My name's Lily ， "
                         "Ben 这样说， I am Ben ，两种都可以。"),
        }
        audit = self.audit(f)
        self.assertFalse(audit['passed'])
        self.assertFalse(audit['segments'][0]['comparison']['passed'])
        self.assertFalse(audit['segments'][1]['comparison']['passed'])
        self.assertGreaterEqual(audit['segments'][1]['similarityBps'], 8500)
        lily_rules = [
            {'side': 'expected', 'from': 'Lily', 'to': '莉莉',
             'sourceOccurrences': 2, 'matchIndex': 1},
            {'side': 'expected', 'from': "name's", 'to': 'name is',
             'sourceOccurrences': 1, 'matchIndex': 1},
        ]
        im_rule = [{'side': 'expected', 'from': "I'm", 'to': 'I am',
                    'sourceOccurrences': 1, 'matchIndex': 1}]
        english, registry, evidence = self.english_reconciliation(
            f, audit, {0: lily_rules, 1: im_rule})
        calls = f.runtime.start_formal_audio_asr.call_count
        with patch.object(english, 'REGISTRY', registry):
            accepted = {}
            for entry in audit['segments'][:2]:
                accepted.update(english.validate_segment_evidence(evidence, plan=f.plan,
                    classroom=f.classroom, audit_entry=entry,
                    expected_source_sha256=digest(f.classroom), now_ms=now_ms()))
            complete = english.validate_reconciliation(evidence, plan=f.plan,
                classroom=f.classroom, audit=audit,
                expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            self.assertEqual(accepted, complete)
            self.assertEqual(len(complete), 2)
            second_key = (audit['segments'][1]['sceneId'], audit['segments'][1]['actionId'])
            self.assertEqual(complete[second_key]['appliedRules'], im_rule)
            self.assertEqual(complete[second_key]['literalSimilarityBps'],
                             audit['segments'][1]['similarityBps'])
            row = f.service.get(f.key)
            review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True,
                'sourceUsageConfirmed': True, 'publicationAuthorized': True,
                'reviewer': 'test', 'basis': 'two exact registered English orthographies',
                'sourceSha256': row['classroom_sha256'], 'reviewedAt': now_ms() - 1}
            prepared = TextbookPublicationService(f.service).prepare(key=f.key,
                edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
                teaching_revision='v2-test-two-exact-segments', review=review,
                audio_audit=audit, classroom_directory=f.root,
                asr_reconciliation=evidence)
            frozen = prepared['frozen']
            build = {'status': 'published', 'content_key': frozen['contentKey'],
                'node_id': frozen['textbookBinding']['nodeId'],
                'teaching_revision': 'v2-test-two-exact-segments',
                'input_json': canonical(frozen),
                'review_json': canonical(prepared['review'])}
            self.assertEqual(validate_release(build, prepared['manifest']), prepared['release'])
            with self.assertRaises(ApiError):
                english.validate_segment_evidence(evidence, plan=f.plan,
                    classroom=f.classroom, audit_entry=audit['segments'][2],
                    expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            missing = deepcopy(evidence)
            missing['segments'].pop()
            missing['sha256'] = digest({k: v for k, v in missing.items() if k != 'sha256'})
            with self.assertRaises(ApiError):
                english.validate_segment_evidence(missing, plan=f.plan,
                    classroom=f.classroom, audit_entry=audit['segments'][0],
                    expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            changed_audio = deepcopy(evidence)
            changed_audio['segments'][1]['audioSha256'] = '0' * 64
            changed_audio['sha256'] = digest({k: v for k, v in changed_audio.items() if k != 'sha256'})
            with self.assertRaises(ApiError):
                english.validate_segment_evidence(changed_audio, plan=f.plan,
                    classroom=f.classroom, audit_entry=audit['segments'][1],
                    expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            widened = deepcopy(registry)
            widened['entries'][1]['rules'][0]['from'] = "We're"
            widened['sha256'] = digest({k: v for k, v in widened.items() if k != 'sha256'})
            with patch.object(english, 'REGISTRY', widened), self.assertRaises(ApiError):
                english.validate_segment_evidence(evidence, plan=f.plan,
                    classroom=f.classroom, audit_entry=audit['segments'][1],
                    expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            other_plan = deepcopy(f.plan)
            other_plan['previewKey'] = '0' * 64
            with self.assertRaises(ApiError):
                english.validate_segment_evidence(evidence, plan=other_plan,
                    classroom=f.classroom, audit_entry=audit['segments'][1],
                    expected_source_sha256=digest(f.classroom), now_ms=now_ms())
            extra_failure = deepcopy(audit)
            extra_failure['segments'][2]['comparison']['passed'] = False
            extra_failure['segments'][2]['comparison']['protectedContentMatched'] = False
            extra_failure['sha256'] = digest({k: v for k, v in extra_failure.items() if k != 'sha256'})
            with self.assertRaises(ApiError):
                english.validate_reconciliation(evidence, plan=f.plan,
                    classroom=f.classroom, audit=extra_failure,
                    expected_source_sha256=digest(f.classroom), now_ms=now_ms())
        self.assertEqual(f.runtime.start_formal_audio_asr.call_count, calls)

    def test_strict_gate_resumes_only_registered_english_failure_and_publication_preserves_it(self):
        from content import textbook_english_asr_reconciliation as english
        f = self.fixture('english', "再听一次Lily的回答：My name's Lily.")
        f.transcript_override = '再听一次莉莉的回答，My name is Lily。'
        original = self.audit(f)
        english, registry, evidence = self.english_reconciliation(f, original)
        output = f.root / 'strict-reconciled-audit'
        output.mkdir()
        first = original['segments'][0]
        source_raw = f.root / 'audit' / (first['asr']['requestId'] + '.json')
        (output / source_raw.name).write_bytes(source_raw.read_bytes())
        manifest_path = f.root / 'english-reconciliation.json'
        manifest_path.write_text(canonical(evidence))
        f.runtime.start_formal_audio_asr.reset_mock()
        argv = ['audit_textbook_audio.py', '--key', f.key, '--classroom-directory', str(f.root),
                '--output', str(output), '--strict-segment-gate',
                '--asr-reconciliation', str(manifest_path)]
        with patch.object(english, 'REGISTRY', registry), \
                patch.object(audit_script.AppConfig, 'from_env'), \
                patch.object(audit_script, 'Database', return_value=f.db), \
                patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=f.runtime), \
                patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            audit_script.main()
        audited = json.loads((output / 'audit.json').read_text())
        self.assertEqual(f.runtime.start_formal_audio_asr.call_count, len(audited['segments']) - 1)
        self.assertFalse(audited['passed'])
        self.assertEqual(audited['segments'][0], first)
        row = f.service.get(f.key)
        review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True,
            'sourceUsageConfirmed': True, 'publicationAuthorized': True,
            'reviewer': 'test', 'basis': 'exact registered English orthography',
            'sourceSha256': row['classroom_sha256'], 'reviewedAt': now_ms() - 1}
        with patch.object(english, 'REGISTRY', registry):
            prepared = TextbookPublicationService(f.service).prepare(key=f.key,
                edition=row['edition_id'], revision=row['revision_id'], node=row['node_id'],
                teaching_revision='v2-test', review=review, audio_audit=audited,
                classroom_directory=f.root, asr_reconciliation=evidence)
            frozen, release = prepared['frozen'], prepared['release']
            build = {'status': 'published', 'content_key': frozen['contentKey'],
                'node_id': frozen['textbookBinding']['nodeId'], 'teaching_revision': 'v2-test',
                'input_json': canonical(frozen), 'review_json': canonical(prepared['review'])}
            self.assertEqual(validate_release(build, prepared['manifest']), release)
        self.assertEqual(release['audioAudit']['acceptanceMethod'], english.METHOD)
        self.assertFalse(release['audioAudit']['literalPassed'])
        self.assertEqual(release['audioAudit']['literalAudit'], audited)

    def test_english_visual_revision_audit_cache_and_release_share_frozen_contract(self):
        f = self.fixture('english', '请跟老师说，Hello, I am Mia.')
        first = self.audit(f)
        cache = {p.name: p.read_bytes() for p in (f.root / 'audit').glob('tbbasr2_*.json')}
        original_plan = (f.folder / 'plan.json').read_bytes()
        f.apply()
        second = self.audit(f)
        self.assertNotEqual(first['sourceSha256'], second['sourceSha256'])
        self.assertEqual(first['contract'], second['contract'])
        self.assertEqual(cache, {p.name: p.read_bytes() for p in (f.root / 'audit').glob('tbbasr2_*.json')})
        self.assertEqual(f.runtime.start_formal_audio_asr.call_count, 8)
        self.assertEqual({c.kwargs['subject'] for c in f.runtime.start_formal_audio_asr.call_args_list}, {'english'})
        prepared = self.prepare(f, second)
        frozen, release = prepared['frozen'], prepared['release']
        build = {'status': 'published', 'content_key': frozen['contentKey'], 'node_id': frozen['textbookBinding']['nodeId'],
            'teaching_revision': 'v2-test', 'input_json': canonical(frozen), 'review_json': canonical(prepared['review'])}
        self.assertEqual(validate_release(build, prepared['manifest']), release)
        self.assertEqual((f.folder / 'plan.json').read_bytes(), original_plan)
        f.runtime.start_formal_audio_tts.assert_not_called()
        changed = deepcopy(second)
        changed['contract']['comparisonPolicySha256'] = '0' * 64
        changed['sha256'] = digest({k: v for k, v in changed.items() if k != 'sha256'})
        with self.assertRaises(ApiError): self.prepare(f, changed)

    def test_math_local_repair_preserves_contract_and_only_audits_replaced_audio(self):
        f = self.fixture('math', '请你仔细数一数校园里面一共有三个花盆。')
        f.transcript_override = '请你仔细数一数校园里面一共有四个花盆。'
        failed = self.audit(f)
        audit_path = f.root / 'failed.json'
        audit_path.write_text(canonical(failed))
        source = deepcopy(f.classroom)
        old_plan = (f.folder / 'plan.json').read_bytes()
        old_audio = {p.name: p.read_bytes() for p in (f.root / f.cid / 'audio').glob('*.wav')}
        audio = next(iter(old_audio.values()))
        providers = {}
        def get(request):
            if request not in providers: raise OpenMaicFullRuntimeError('not_found', 'missing', status_code=404)
            return providers[request]
        def speak(**kw):
            value = {'requestId': kw['request_id'], 'status': 'succeeded', 'audioSha256': sha_bytes(audio)}
            providers[kw['request_id']] = value
            return value
        f.runtime.get_formal_audio_tts.side_effect = get
        f.runtime.start_formal_audio_tts.side_effect = speak
        f.runtime.download_formal_audio_tts.return_value = audio
        action = source['scenes'][0]['actions'][0]
        change = {'schemaVersion': SCHEMA, 'expectedSourceSha256': digest(source), 'reviewer': 'test', 'basis': '明确数字失败',
            'changes': [{'sceneId': 'scene-0', 'actionId': action['id'], 'beforeTextSha256': sha_bytes(action['text'].encode()),
                         'text': '校园里有三个花盆，请你数一数。'}]}
        result = revise_preview_narration(f.service, f.key, f.root, change, audit_path, execute=True)
        revised = json.loads((f.folder / 'narration-revisions' / result['revisionId'] / 'plan.json').read_text())
        self.assertEqual(revised['parentPlanSha256'], digest(f.plan))
        self.assertEqual(revised['comparisonPolicy'], f.plan['comparisonPolicy'])
        self.assertEqual((f.folder / 'plan.json').read_bytes(), old_plan)
        for name, raw in old_audio.items(): self.assertEqual((f.root / f.cid / 'audio' / name).read_bytes(), raw)
        self.assertEqual(source['scenes'][1:], f.classroom['scenes'][1:])
        narrate_preview(f.service, f.key, f.root)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        f.transcript_override = None
        complete = self.audit(f)
        self.assertTrue(complete['passed'])
        self.assertEqual(f.runtime.start_formal_audio_asr.call_count, 9)
        self.assertEqual(f.runtime.start_formal_audio_asr.call_args.kwargs['classroom_content_sha256'], revised['classroomSha256'])
        self.prepare(f, complete)

    def test_changed_target_directory_is_refused_before_media_archival(self):
        f = self.fixture('math')
        audit = self.audit(f)
        row = f.service.get(f.key)
        with f.service.repository.transaction() as conn:
            revision = f.service.repository.get_revision(conn, row['edition_id'], row['revision_id'])
            manifest = f.service.repository.manifest(revision)
            manifest['units'][0]['lessons'][0]['brief']['objectives'] = ['新的目录教学目标']
            conn.execute('UPDATE learning_textbook_revisions SET manifest_json=?,manifest_sha256=?',
                         (canonical(manifest), digest(manifest)))
        with self.assertRaises(ApiError): self.prepare(f, audit)
        self.assertEqual(list(f.root.glob('tbpub_*')), [])


if __name__ == '__main__': unittest.main()
