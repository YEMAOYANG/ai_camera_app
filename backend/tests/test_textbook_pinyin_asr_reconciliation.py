"""Pure, in-memory review evidence; never approves real lesson audio."""
from copy import deepcopy
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_asr_reconciliation import (
    ACCEPTANCE_METHOD, BINDING_FIELDS, CONFIRMATION_FIELDS, CONFIRMATION_SCOPE,
    HUMAN_SCHEMA, IDENTITY_FIELDS, SCHEMA, validate_reconciliation,
)
from content.textbook_pinyin_pronunciation import (
    LISTENING_SCHEMA, pronunciation_symbols, provider_pronunciation, sha_text,
)
from content.textbook_preview_audio_contract import (
    asr_request_id, audit_contract_identity, compare_transcript, new_audio_plan,
    new_pinyin_audio_plan, tts_request_id,
)
from core.errors import ApiError
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING


def seal(value):
    value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
    return value


def identity(entry):
    return {k: entry[k] for k in IDENTITY_FIELDS}


class PinyinAsrReconciliationTests(unittest.TestCase):
    def setUp(self):
        frozen = {**PINYIN_BINDING, 'manifestSha256': 'e' * 64}
        parent = new_audio_plan(preview_key='a' * 64, classroom_sha256='b' * 64,
                                core_sha256='c' * 64, frozen_input=frozen)
        plan = new_pinyin_audio_plan(preview_key='a' * 64, classroom_sha256='b' * 64,
            core_sha256='c' * 64, frozen_input=frozen, parent_plan=parent, revision_id='d' * 64)
        classroom = {'id': 'stage-original', 'stage': {'id': 'stage-original'}, 'scenes': []}
        segments, heard = [], []
        texts = [
            ('ā，第一声平平的，跟我一起读一读。', '啊，低声平平的，跟我一起读一读。'),
            ('o住进中格了，放得真好。', '窝住井中蛤蜊，放的真好。'),
            ('请你看一看图片。', '请你看一看图片。'),
        ]
        for i, (text, transcript) in enumerate(texts):
            scene_id, action_id = f's{i}', f'a{i}'
            tts = tts_request_id(plan, scene_id, action_id, text)
            audio_sha = sha_text('synthetic-WAV-' + str(i))
            action = {'id': action_id, 'type': 'speech', 'text': text, 'audioId': tts,
                      'audioUrl': '/original/' + tts + '.wav'}
            classroom['scenes'].append({'id': scene_id, 'actions': [action]})
            comparison = compare_transcript(plan, text, transcript)
            entry = {'sceneId': scene_id, 'actionId': action_id, 'text': text,
                'textSha256': sha_text(text), 'ttsRequestId': tts, 'audioSha256': audio_sha,
                'transcript': transcript, 'similarityBps': comparison['similarityBps'],
                'comparison': comparison, 'durationMs': 3000,
                'asr': {'requestId': asr_request_id(plan, tts, audio_sha), 'status': 'succeeded',
                        'completionUsable': True, 'transcript': transcript,
                        'transcriptSha256': sha_text(transcript), 'providerId': 'qwen-asr',
                        'modelId': 'qwen3-asr-flash', 'providerAsrBodySha256': '9' * 64,
                        'providerPronunciation': provider_pronunciation(text)}}
            segments.append(entry)
            if pronunciation_symbols(text):
                heard.append({**identity(entry), 'verdict': 'accepted', 'reviewer': 'Synthetic listener',
                              'reviewedAt': 1000, 'basis': 'Synthetic pronunciation-only approval'})
        listening = seal({'schemaVersion': LISTENING_SCHEMA, 'previewKey': plan['previewKey'],
            'planSha256': digest(plan), 'coreSha256': plan['coreSha256'], 'segments': heard})
        audit = seal({'schemaVersion': 'mira.textbook.audio-audit.v2', 'previewKey': plan['previewKey'],
            'sourceSha256': digest(classroom), 'passed': False, 'contract': audit_contract_identity(plan),
            'segments': segments, 'listeningReview': deepcopy(listening)})
        self.context = {'plan': plan, 'classroom': classroom, 'audit': audit, 'listening_review': listening,
                        'expected_source_sha256': digest(classroom), 'now_ms': 4000}
        self.manifest = self.make_manifest(self.context)

    def make_manifest(self, context):
        """Deliberately explicit synthetic confirmations, never inferred by production."""
        audit, listening = context['audit'], context['listening_review']
        bindings = {'previewKey': context['plan']['previewKey'], 'planSha256': digest(context['plan']),
                    'sourceSha256': context['expected_source_sha256'], 'auditSha256': digest(audit),
                    'listeningReviewSha256': digest(listening)}
        low = [x for x in audit['segments'] if x['comparison']['passed'] is False]
        human = seal({**bindings, 'schemaVersion': HUMAN_SCHEMA, 'confirmationScope': CONFIRMATION_SCOPE,
            'reviewer': 'Synthetic listener', 'reviewedAt': 2000,
            'statement': 'Synthetic fixture: I checked both full sentences against the source; no missing, wrong or extra words.',
            'segments': [{**identity(x), 'verdict': 'accepted',
                          **dict.fromkeys(CONFIRMATION_FIELDS, True)} for x in low]})
        heard = {(x['sceneId'], x['actionId']): x for x in listening['segments']}
        entries = []
        for entry, confirmation in zip(low, human['segments']):
            key = (entry['sceneId'], entry['actionId'])
            entries.append({**identity(entry), 'asrRequestId': entry['asr']['requestId'],
                'asrReceiptSha256': digest(entry['asr']), 'auditSegmentSha256': digest(entry),
                'listeningEntrySha256': digest(heard.get(key, {})), 'humanEntrySha256': digest(confirmation),
                'literalPassed': False, 'similarityBps': entry['similarityBps'],
                'acceptanceMethod': ACCEPTANCE_METHOD,
                'discrepancyRationale': 'Synthetic ASR discrepancy independently confirmed against the entire original sentence.'})
        return seal({**bindings, 'schemaVersion': SCHEMA, 'literalPassed': False,
            'acceptanceMethod': ACCEPTANCE_METHOD, 'humanReview': human, 'humanReviewSha256': digest(human),
            'reviewer': 'Synthetic operator', 'reviewedAt': 3000, 'segments': entries})

    def validate(self, manifest=None, context=None):
        return validate_reconciliation(manifest if manifest is not None else self.manifest,
                                       **(context if context is not None else self.context))

    def reseal_human(self, manifest):
        seal(manifest['humanReview'])
        manifest['humanReviewSha256'] = digest(manifest['humanReview'])
        for entry, human in zip(manifest['segments'], manifest['humanReview']['segments']):
            entry['humanEntrySha256'] = digest(human)
        return seal(manifest)

    def test_acceptance_is_independent_preserves_inputs_and_original_low_scores(self):
        before = canonical({'context': self.context, 'manifest': self.manifest})
        accepted = self.validate()
        self.assertEqual(set(accepted), {('s0', 'a0'), ('s1', 'a1')})
        self.assertEqual([x['similarityBps'] for x in accepted.values()], [7857, 5000])
        self.assertTrue(all(x['literalPassed'] is False for x in accepted.values()))
        accepted[('s0', 'a0')]['discrepancyRationale'] = 'mutate detached result'
        self.assertEqual(canonical({'context': self.context, 'manifest': self.manifest}), before)
        self.assertIs(self.context['audit']['passed'], False)
        self.assertNotEqual(self.manifest['auditSha256'], self.context['audit']['sha256'])

    def test_portable_release_allows_url_rewrite_but_not_speech_or_source_change(self):
        context = deepcopy(self.context)
        context['classroom']['id'] = context['classroom']['stage']['id'] = 'tbpub_synthetic'
        for scene in context['classroom']['scenes']:
            scene['actions'][0]['audioUrl'] = '/published/converted.mp3'
        self.assertEqual(set(self.validate(context=context)), {('s0', 'a0'), ('s1', 'a1')})
        context['expected_source_sha256'] = 'f' * 64
        with self.assertRaises(ApiError): self.validate(context=context)
        for field, value in [('id', 'another-action'), ('text', 'ā，第二声平平的。'), ('audioId', 'tbptts1_' + 'f' * 64)]:
            context = deepcopy(self.context)
            context['classroom']['scenes'][0]['actions'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(context=context)

    def test_legacy_other_subject_and_mutated_threshold_cannot_use_reconciliation(self):
        for field, value in [('schemaVersion', 'mira.textbook.preview-audio-plan.v2'), ('subject', 'english')]:
            context = deepcopy(self.context); context['plan'][field] = value
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(context=context)
        context = deepcopy(self.context); context['plan']['comparisonPolicy']['minimumSimilarityBps'] = 5000
        context['plan']['comparisonPolicySha256'] = digest(context['plan']['comparisonPolicy'])
        with self.assertRaises(ApiError): self.validate(context=context)

    def test_all_object_and_receipt_bindings_fail_closed_even_when_manifest_resealed(self):
        for field in BINDING_FIELDS | {'humanReviewSha256'}:
            manifest = deepcopy(self.manifest); manifest[field] = '0' * 64; seal(manifest)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(manifest)
        for field in IDENTITY_FIELDS | {'asrRequestId', 'asrReceiptSha256', 'auditSegmentSha256',
                'listeningEntrySha256', 'humanEntrySha256', 'similarityBps', 'discrepancyRationale'}:
            manifest = deepcopy(self.manifest)
            manifest['segments'][0][field] = '' if field == 'discrepancyRationale' else '0' * 64
            seal(manifest)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(manifest)
        manifest = deepcopy(self.manifest); manifest['reviewer'] = 'altered without seal'
        with self.assertRaises(ApiError): self.validate(manifest)

    def test_complete_exact_low_set_required_in_both_manifests(self):
        for scope in ('segments', 'humanReview'):
            for mutation in ('missing', 'duplicate', 'extra'):
                manifest = deepcopy(self.manifest)
                entries = manifest['segments'] if scope == 'segments' else manifest['humanReview']['segments']
                if mutation == 'missing': entries.pop()
                elif mutation == 'duplicate': entries.append(deepcopy(entries[0]))
                else:
                    item = deepcopy(entries[0]); item['sceneId'], item['actionId'] = 's2', 'a2'; entries.append(item)
                self.reseal_human(manifest)
                with self.subTest(scope=scope, mutation=mutation), self.assertRaises(ApiError): self.validate(manifest)

    def test_pronunciation_only_approval_does_not_confirm_whole_sentences(self):
        manifest = deepcopy(self.manifest); manifest['humanReview'] = deepcopy(self.context['listening_review'])
        manifest['humanReviewSha256'] = digest(manifest['humanReview']); seal(manifest)
        with self.assertRaises(ApiError): self.validate(manifest)
        for field, value in [('confirmationScope', 'pronunciation-only'), ('statement', ''), ('reviewer', '')]:
            manifest = deepcopy(self.manifest); manifest['humanReview'][field] = value; self.reseal_human(manifest)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(manifest)
        for field in CONFIRMATION_FIELDS | {'verdict'}:
            for value in (False, None, 1):
                manifest = deepcopy(self.manifest); manifest['humanReview']['segments'][0][field] = value
                self.reseal_human(manifest)
                with self.subTest(field=field, value=value), self.assertRaises(ApiError): self.validate(manifest)

    def test_future_stale_and_missing_confirmation_rejected(self):
        for scope, moment in [('humanReview', 500), ('humanReview', 5000), ('manifest', 5000), ('manifest', True)]:
            manifest = deepcopy(self.manifest)
            target = manifest['humanReview'] if scope == 'humanReview' else manifest
            target['reviewedAt'] = moment; self.reseal_human(manifest)
            with self.subTest(scope=scope, moment=moment), self.assertRaises(ApiError): self.validate(manifest)
        manifest = deepcopy(self.manifest); manifest['humanReview']['segments'][0].pop('noOmissions')
        self.reseal_human(manifest)
        with self.assertRaises(ApiError): self.validate(manifest)

    def test_raw_asr_status_transcript_and_comparison_recomputed_for_all_segments(self):
        mutations = [
            lambda entry: entry['asr'].update(status='failed'),
            lambda entry: entry['asr'].update(completionUsable=False),
            lambda entry: entry['asr'].update(requestId='tbpasr1_' + '0' * 64),
            lambda entry: entry['asr'].update(transcript='另一个句子'),
            lambda entry: entry['asr'].update(transcriptSha256='0' * 64),
            lambda entry: entry['asr'].update(modelId='another-model'),
            lambda entry: entry['comparison'].update(passed=not entry['comparison']['passed']),
            lambda entry: entry.update(similarityBps=entry['similarityBps'] + 1),
            lambda entry: entry['comparison'].update(passed=int(entry['comparison']['passed'])),
            lambda entry: entry.update(similarityBps=float(entry['similarityBps'])),
        ]
        for index in (0, 2):
            for mutate in mutations:
                context = deepcopy(self.context); mutate(context['audit']['segments'][index]); seal(context['audit'])
                manifest = self.make_manifest(context)
                with self.subTest(index=index, mutation=mutate), self.assertRaises(ApiError): self.validate(manifest, context)

    def test_missing_extra_duplicate_audit_segments_and_false_success_rejected(self):
        for mutation in ('missing', 'extra', 'duplicate', 'passed'):
            context = deepcopy(self.context); audit = context['audit']
            if mutation == 'missing': audit['segments'].pop()
            elif mutation == 'extra':
                entry = deepcopy(audit['segments'][0]); entry['actionId'] = 'unknown'; audit['segments'].append(entry)
            elif mutation == 'duplicate': audit['segments'].append(deepcopy(audit['segments'][0]))
            else: audit['passed'] = True
            seal(audit)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.validate(self.make_manifest(context), context)

    def test_non_pinyin_failure_and_mismatched_heard_wav_cannot_be_reconciled(self):
        context = deepcopy(self.context); entry = context['audit']['segments'][2]
        transcript = '不是这一句话。'
        entry.update(transcript=transcript, comparison=compare_transcript(context['plan'], entry['text'], transcript))
        entry['similarityBps'] = entry['comparison']['similarityBps']
        entry['asr'].update(transcript=transcript, transcriptSha256=sha_text(transcript))
        seal(context['audit'])
        with self.assertRaises(ApiError): self.validate(self.make_manifest(context), context)
        context = deepcopy(self.context); context['listening_review']['segments'][0]['audioSha256'] = '0' * 64
        seal(context['listening_review']); context['audit']['listeningReview'] = deepcopy(context['listening_review'])
        seal(context['audit'])
        with self.assertRaises(ApiError): self.validate(self.make_manifest(context), context)


if __name__ == '__main__':
    unittest.main()
