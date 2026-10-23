"""Synthetic formal records only; no providers, real users, DB or browser."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_asr_observation import (
    SCHEMA, OBSERVATION_SCHEMA, build_observation_audit, validate_observation_audit, verify_observation,
)
from content.textbook_asr_source_reuse import sha, verify_origin, validate_audit as validate_origin_audit
from content.textbook_audio_recheck import seal
from content.textbook_pinyin_operator_review import validate_operator_review
from content.textbook_pinyin_pronunciation import pronunciation_identity
from content.textbook_pinyin_operator_review_v7 import (
    DECISION, METHOD, build_explicit_acceptance_v7, build_operator_review_v7,
)
from core.errors import ApiError
from services.learning_media_materialization_service import asr_similarity_bps
from services.textbook_asr_observation import (
    package_observation, verify_live_observation_audit, package_cached_routines,
    package_collected_origins, assemble_observation_audit,
)
from tests import test_textbook_asr_source_reuse as fixtures
from tests import test_textbook_asr_failed_recovery as recovery_fixtures


def encoded(value): return base64.b64encode(canonical(value).encode()).decode('ascii')


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.orig = fixtures.AsrOriginTests(); self.orig.setUp(); self.addCleanup(self.orig.doCleanups)
        self.fx, self.f = self.orig.fx, self.orig.f
        # The reused fixture's root itself is a TemporaryDirectory. Nest its
        # classrooms so the sibling Native history stays private to this test.
        previous = self.f.root; nested = previous / 'classrooms'; nested.mkdir()
        for p in list(previous.iterdir()):
            if p != nested: p.rename(nested / p.name)
        self.f.root = nested
        self.native = self.f.root.parent / 'formal-audio'
        self.probes = self.f.root / 'empty-probe-history'; self.probes.mkdir()
        self.f.service.preview.authoring_output_root = self.probes
        self.observations = [self.observation(o) for o in self.orig.origins]
        self.audit = self.make_audit(); self.decision = self.make_decision(); self.review = self.make_review()

    def observation(self, origin, container='routine-cache'):
        f = verify_origin(origin); attempt = origin['attempts'][0]; request = attempt['request']; response = attempt['response']
        stamp = '2026-10-22T00:00:00.000Z'
        job = {'schemaVersion': 'mira.openmaic.formal-audio-job.v1', 'kind': 'asr', **request,
            'requestSha256': digest({'logicalRequest': request, 'providerPronunciation': f['receipt']['providerPronunciation']}),
            'languageCode': 'zh-CN', 'state': 'succeeded', 'providerId': 'qwen-asr', 'modelId': 'qwen3-asr-flash',
            'fallbackUsed': False, 'providerPronunciation': f['receipt']['providerPronunciation'],
            'providerAsrBodySha256': response['providerAsrBodySha256'], 'transcriptSha256': response['transcriptSha256'],
            **{k: stamp for k in ('createdAt', 'updatedAt', 'providerAttemptedAt', 'providerCompletedAt', 'completedAt')}}
        transcript = {k: response[k] for k in ('requestId', 'transcript', 'transcriptSha256')}
        transcript['audioSha256'] = sha(f['audio'])
        tts_job = {**deepcopy(f['receipt']), 'schemaVersion': 'mira.openmaic.formal-audio-job.v1',
            'kind': 'tts', 'state': 'succeeded', 'classroomId': origin['classroomId'],
            'classroomContentSha256': f['receipt'].get('classroomContentSha256', origin['plan']['classroomSha256']),
            'sceneId': origin['source']['sceneId'], 'sceneOrder': origin['source']['sceneOrder'],
            'actionId': origin['source']['action']['id'], 'narrationSegmentId': origin['source']['action']['id'],
            'textSha256': sha(f['text'].encode()), 'fallbackUsed': False}
        teacher = f['effectivePlan']['teacher']; profile = teacher['teacherProfile']
        logical = {'requestId': origin['source']['action']['audioId'], 'classroomId': origin['classroomId'],
            'classroomContentSha256': f['receipt'].get('classroomContentSha256', origin['plan']['classroomSha256']),
            'subject': f['effectivePlan']['subject'], 'teacherProfileId': profile['id'],
            'teacherProfileVersion': profile['version'], 'teacherProfileSha256': profile['contentHash'],
            'teacherGender': teacher['teacherGender'], 'sceneId': origin['source']['sceneId'],
            'sceneOrder': origin['source']['sceneOrder'], 'actionId': origin['source']['action']['id'],
            'narrationSegmentId': origin['source']['action']['id'], 'text': f['text'], 'textSha256': sha(f['text'].encode())}
        logical['pronunciationProfile'] = pronunciation_identity(f['text'], policy_version=f['policy']['policyVersion'])
        tts_job.update({k: v for k, v in logical.items() if k not in ('text', 'pronunciationProfile')})
        tts_job.update(requestSha256=digest({'logicalRequest': logical,
            'providerPronunciation': f['receipt']['providerPronunciation']}), voiceGender=teacher['voiceGender'],
            languageCode='zh-CN')
        norm = f['receipt']['audioNormalization']
        duration = norm['pcmByteLength'] * 1000 // (norm['sampleRate'] * norm['channels'] * norm['bitsPerSample'] // 8)
        cache = {'sceneId': origin['source']['sceneId'], 'actionId': origin['source']['action']['id'],
            'ttsRequestId': origin['source']['action']['audioId'], 'audioSha256': sha(f['audio']),
            'textSha256': sha(f['text'].encode()), 'text': f['text'], 'transcript': response['transcript'],
            'durationMs': duration, 'similarityBps': asr_similarity_bps(f['text'], response['transcript']), 'asr': response}
        result = {'schemaVersion': OBSERVATION_SCHEMA, 'origin': deepcopy(origin), 'rawEvidence': {
            'jobBase64': encoded(job), 'ttsJobBase64': encoded(tts_job), 'transcriptBase64': encoded(transcript),
            'receiptBase64': encoded(cache if container == 'routine-cache' else response), 'receiptContainer': container}}
        verify_observation(result)
        for relative, value in [
            ('jobs/asr/'+sha(response['requestId'].encode())+'.json', job),
            ('jobs/tts/'+sha(origin['source']['action']['audioId'].encode())+'.json', tts_job),
            ('transcripts/'+sha(response['requestId'].encode())+'.json', transcript)]:
            p = self.native / relative; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(canonical(value))
        return result

    def make_audit(self, **changes):
        args = dict(plan=self.f.plan, classroom=self.f.classroom, targets=self.orig.targets, observations=self.observations)
        args.update(changes)
        return build_observation_audit(**args)

    def context(self):
        return dict(plan=self.f.plan, classroom=self.f.classroom, audit=self.audit,
            expected_source_sha256=digest(self.f.classroom), now_ms=self.fx.now)

    def make_decision(self, **changes):
        args = self.context(); args.update(probe_evidence_sha256='8'*64,
            question_item_id=['request_user_input_async', 'synthetic-observation-question-not-real-user', 0],
            question='SYNTHETIC TEST ONLY: accept these pending observations for this lesson?',
            statement='SYNTHETIC TEST ONLY: explicitly accept and publish this lesson.',
            decision=DECISION, recorded_at=self.fx.now-100)
        args.update(changes)
        return build_explicit_acceptance_v7(**args)

    def make_review(self, **changes):
        args = self.context(); args.update(authorization=self.fx.auth, browser_qa=self.fx.browser,
            reviewer='Synthetic fixture only', reviewed_at=self.fx.now, explicit_acceptance=self.decision)
        args.update(changes)
        return build_operator_review_v7(**args)

    def validate(self, audit=None, review=None):
        args = self.context(); args.update(audit=self.audit if audit is None else audit)
        return validate_operator_review(self.review if review is None else review, **args)

    def prepare(self):
        self.f.audit = self.audit
        return self.fx.prepare(self.review)

    def test_complete_pending_review_and_portable_release_keep_original_bytes(self):
        original = canonical(self.observations)
        self.assertEqual(len(self.validate()), 2)
        prepared = self.prepare(); release = self.fx.read(prepared)
        self.assertEqual(release['audioAudit']['literalAudit'], self.audit)
        self.assertEqual(release['audioAudit']['acceptanceMethod'], METHOD)
        self.assertEqual(canonical(self.observations), original)
        self.assertNotIn('origins', self.audit)
        self.assertNotIn('asrRecheck', self.review)
        for k in ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified'):
            self.assertIs(self.audit[k], False); self.assertIs(self.review[k], False)
        self.f.service.preview.runtime.start_formal_audio_tts.assert_not_called()
        self.f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_cross_text_body_same_wav_is_pending_not_exact_source_or_alias(self):
        # The target still has its own valid TTS/SSML identity, but uses bytes
        # for another original text. A literal score cannot make this exact-source.
        scene = self.f.classroom['scenes'][1]; action = scene['actions'][0]
        action['text'] = '请再看一看。'
        self.fx.receipts[1] = self.fx.audio_receipt(scene, action, self.f.plan)
        self.fx.sync_source(); self.orig.targets[1] = self.orig.target(scene, 1)
        self.observations = self.observations[:1]
        self.audit = self.make_audit(); self.decision = self.make_decision(); self.review = self.make_review()
        entry = self.audit['segments'][1]
        self.assertIn('different-original-text-or-tts-body', entry['pendingReasons'])
        self.assertFalse(entry['observations'][0]['textAndBodyMatch'])
        self.assertFalse(entry['observations'][0]['sameOriginalSource'])
        self.assertEqual(self.audit['observations'][0], self.observations[0])
        self.assertEqual(len(self.validate()), 2)
        self.fx.read(self.prepare())
        with self.assertRaises(ApiError): self.make_review(explicit_acceptance=None)

    def test_historical_excess_retains_every_original_routine_and_forbids_calls(self):
        extra = self.orig.excess_origins(3)
        self.observations += [self.observation(o) for o in extra]
        self.audit = self.make_audit(); self.decision = self.make_decision(); self.review = self.make_review()
        excess = next(h for h in self.audit['pcmHistory'] if h['historicalExcess'])
        self.assertEqual(excess['attemptCount'], 4)
        self.assertTrue(excess['noFurtherProviderCalls'])
        self.assertEqual({o['origin']['attempts'][0]['role'] for o in self.observations}, {'routine'})
        self.assertIn('historical-excess-routines-retained', self.audit['segments'][0]['pendingReasons'])
        self.fx.read(self.prepare())

    def test_all_observations_are_compared_no_best_score_or_alias_selection(self):
        origin = self.orig.excess_origins(1)[0]
        origin['attempts'][0]['response'].update(transcript='完全不同', transcriptSha256=sha('完全不同'.encode()))
        self.observations.append(self.observation(origin))
        self.audit = self.make_audit()
        self.assertEqual(len(self.audit['segments'][0]['observations']), 2)
        self.assertIn('literal-comparison-unresolved', self.audit['segments'][0]['pendingReasons'])
        self.assertTrue(self.audit['segments'][0]['acceptancePending'])

    def test_raw_source_wav_protocol_receipt_role_and_pending_tampering_rejected(self):
        mutations = [
            lambda a: a['observations'][0]['origin']['attempts'][0].update(role='recheck'),
            lambda a: a['observations'][0]['origin']['attempts'][0]['response'].update(status='failed'),
            lambda a: a['observations'][0]['origin']['attempts'][0]['response'].update(providerAsrBodySha256='0'*64),
            lambda a: a['observations'][0]['origin']['source']['ttsReceipt'].update(pcmSha256='0'*64),
            lambda a: a['observations'][0]['origin']['source']['action'].update(text='错误的原文'),
            lambda a: a['observations'][0]['rawEvidence'].update(jobBase64=encoded({'state':'succeeded'})),
            lambda a: a['observations'][0]['rawEvidence'].update(receiptBase64=encoded({'status':'succeeded'})),
            lambda a: a['segments'][0]['comparison'].update(passed=True),
            lambda a: a['segments'][0].update(acceptancePending=False, pendingReasons=[]),
            lambda a: a['segments'][0]['target']['ttsReceipt'].update(audioSha256='0'*64),
            lambda a: a.update(humanListeningVerified=True),
            lambda a: a['pcmHistory'][0]['requestIds'].append('hidden-new-request'),
            lambda a: a['segments'].pop(),
            lambda a: a['observations'].append(deepcopy(a['observations'][0])),
        ]
        for i, mutate in enumerate(mutations):
            audit = deepcopy(self.audit); mutate(audit); seal(audit)
            with self.subTest(i=i), self.assertRaises((ApiError, KeyError)):
                self.validate(audit=audit)

    def test_explicit_scope_browser_and_false_claims_cannot_be_waived(self):
        for field in ('sourceSha256', 'planSha256', 'auditSha256', 'pendingCount'):
            decision = deepcopy(self.decision); decision[field] = decision[field]+1 if field == 'pendingCount' else '0'*64; seal(decision)
            with self.subTest(field=field), self.assertRaises(ApiError): self.make_review(explicit_acceptance=decision)
        for flag in ('humanListeningVerified','phoneticAccuracyVerified','perceptualToneVerified'):
            review = deepcopy(self.review); review[flag] = True; seal(review)
            with self.subTest(flag=flag), self.assertRaises(ApiError): self.validate(review=review)
        browser = deepcopy(self.fx.browser); browser['checks'] = []; seal(browser)
        with self.assertRaises(ApiError): self.make_review(browser_qa=browser)
        with self.assertRaises(ApiError): self.make_decision(decision='accept-all-future-lessons')

    def test_live_original_bytes_unknown_attempt_and_physical_wav_are_not_waived(self):
        fact = verify_observation(self.observations[0]); p = self.native/'jobs/asr'/(sha(fact['requestId'].encode())+'.json')
        raw = p.read_bytes(); p.write_bytes(raw+b' ')
        with self.assertRaises(ApiError): self.prepare()
        p.write_bytes(raw)
        hidden = json.loads(raw); hidden['requestId'] = 'tbpasr1_'+'9'*64; hidden['state'] = 'ambiguous'
        other = self.native/'jobs/asr'/'extra.json'; other.write_text(canonical(hidden))
        with self.assertRaisesRegex(ApiError, 'omits known'): self.prepare()
        other.unlink()
        wav = self.f.root/self.f.cid/'audio'/(self.orig.targets[0]['action']['audioId']+'.wav')
        wav.write_bytes(wav.read_bytes()[:-2]+b'\x09\x00')
        with self.assertRaises(ApiError): self.prepare()

    def test_original_cache_and_transport_raw_records_are_supported_without_calls(self):
        origin = self.orig.origins[0]; observation = self.observation(origin, 'transport-response')
        p = self.f.root/'original-response.json'; p.write_bytes(base64.b64decode(observation['rawEvidence']['receiptBase64']))
        result = package_observation(origin=origin, native_audio_directory=self.native,
            receipt_path=p, receipt_container='transport-response')
        self.assertEqual(result, observation)

    def test_old_origin_and_routine_schemas_cannot_accept_new_observation_envelope(self):
        with self.assertRaises(ApiError):
            validate_origin_audit(self.audit, plan=self.f.plan, classroom=self.f.classroom,
                expected_source_sha256=digest(self.f.classroom))
        old = deepcopy(self.review); old['schemaVersion'] = 'mira.textbook.pinyin-operator-review.v6-explicit-routine-acceptance'; seal(old)
        with self.assertRaises(ApiError): self.validate(review=old)

    def test_portable_release_rejects_resealed_observation_or_target_mutations(self):
        prepared = self.prepare(); release = self.fx.read(prepared)
        self.assertEqual(release['audioAudit']['pronunciationReview'], self.review)
        altered = deepcopy(prepared)
        altered['release']['audioAudit']['literalAudit']['segments'][0]['pendingReasons'] = []
        seal(altered['release']['audioAudit']['literalAudit']); seal(altered['release'])
        with self.assertRaises(ApiError): self.fx.read(altered)

    def test_recorded_failed_recovery_preserves_failed_raw_bytes_and_two_attempts(self):
        fixture = recovery_fixtures.FailedRoutineRecoveryTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        recovered_audit = fixture.collect()  # Fake client from the existing test fixture only.
        recovered = fixture.recovery_origin(recovered_audit)
        observations = [self.observation(fixture.original.origins[0]),
                        self.observation(recovered, 'transport-response')]
        audit = build_observation_audit(plan=fixture.f.plan, classroom=fixture.f.classroom,
            targets=fixture.original.targets, observations=observations)
        validate_observation_audit(audit, plan=fixture.f.plan, classroom=fixture.f.classroom,
            expected_source_sha256=digest(fixture.f.classroom))
        group = next(h for h in audit['pcmHistory'] if fixture.failed_id in h['requestIds'])
        self.assertEqual(group['attemptCount'], 2)
        self.assertTrue(group['noFurtherProviderCalls'])
        self.assertEqual(base64.b64decode(recovered['failureRecovery']['failedJobBase64']), fixture.job_raw)
        self.assertEqual(base64.b64decode(recovered['failureRecovery']['failedCacheBase64']), fixture.cache_raw)
        self.assertEqual(fixture.client._request_formal_audio_json.call_count, 1)

    def test_booleans_cannot_be_replaced_with_equal_numeric_values(self):
        for mutate in (
            lambda a: a.update(passed=int(a['passed'])),
            lambda a: a.update(humanListeningVerified=0),
            lambda a: a.update(noFurtherProviderCalls=1),
            lambda a: a['segments'][0].update(acceptancePending=1),
            lambda a: a['segments'][0]['observations'][0].update(sameOriginalSource=1),
            lambda a: a['segments'][0]['comparison'].update(passed=0),
        ):
            audit = deepcopy(self.audit); mutate(audit); seal(audit)
            with self.subTest(mutate=mutate), self.assertRaises(ApiError): self.validate(audit=audit)

    def test_complete_wav_and_source_plan_are_required_not_pcm_only(self):
        targets = deepcopy(self.orig.targets)
        targets[0]['audioBase64'] = base64.b64encode(base64.b64decode(targets[0]['audioBase64'])[:-1]+b'\x04').decode()
        with self.assertRaises(ApiError): self.make_audit(targets=targets)
        audit = deepcopy(self.audit); audit['observations'][0]['origin']['plan']['coreSha256'] = '0'*64
        seal(audit)
        with self.assertRaises(ApiError): self.validate(audit=audit)
        with self.assertRaises(ApiError): self.make_audit(observations=[])

    def test_read_only_packaging_helpers_import_original_cache_and_collector_claims(self):
        folder = self.f.root/self.f.cid/'textbook-preview-audio'
        (folder/'receipts.json').write_text(canonical(self.fx.receipts))
        cache = self.f.root/'raw-cache'; cache.mkdir()
        for observation in self.observations:
            rid = verify_observation(observation)['requestId']
            (cache/(rid+'.json')).write_bytes(base64.b64decode(observation['rawEvidence']['receiptBase64']))
        packed = package_cached_routines(plan=self.f.plan, classroom=self.f.classroom,
            audio_directory=self.f.root/self.f.cid, routine_cache_directory=cache,
            native_audio_directory=self.native)
        self.assertEqual(packed['unsuccessfulRoutines'], [])
        audit = assemble_observation_audit(plan=self.f.plan, classroom=self.f.classroom,
            audio_directory=self.f.root/self.f.cid, observations=packed['observations'])
        self.assertEqual(audit['schemaVersion'], SCHEMA)
        for origin in self.orig.origins:
            f = verify_origin(origin); rid = f['attempts'][0]['requestId']
            path = self.f.root/'.textbook-asr-pcm-ledger-v1'/f['pcmKey']/'claims'/rid/'response.json'
            path.parent.mkdir(parents=True); path.write_text(canonical(origin['attempts'][0]['response']))
        claims = package_collected_origins(origins=self.orig.origins, classroom_directory=self.f.root,
            native_audio_directory=self.native)
        self.assertEqual(len(claims), 2)
        self.assertTrue(all(o['rawEvidence']['receiptContainer']=='transport-response' for o in claims))

    def test_original_native_http_container_is_preserved_before_receipt_adaptation(self):
        observation = deepcopy(self.observations[0]); f = verify_observation(observation)
        job = json.loads(base64.b64decode(observation['rawEvidence']['jobBase64']))
        original_http = {**job, 'success': True, 'done': True, 'transcript': f['response']['transcript']}
        observation['rawEvidence'].update(receiptBase64=encoded(original_http), receiptContainer='native-response')
        self.assertEqual(verify_observation(observation)['response'], f['response'])
        for mutate in (lambda j: j.update(done=False), lambda j: j.update(sceneId='wrong-source'),
                       lambda j: j.update(transcript='wrong transcript')):
            bad = deepcopy(observation); raw = deepcopy(original_http); mutate(raw)
            bad['rawEvidence']['receiptBase64'] = encoded(raw)
            with self.subTest(mutate=mutate), self.assertRaises(ApiError): verify_observation(bad)

    def test_full_native_tts_logical_identity_and_request_digest_are_required(self):
        for key, value in [('subject','english'), ('teacherProfileId','wrong-teacher'),
                           ('teacherProfileVersion',99), ('teacherProfileSha256','0'*64),
                           ('teacherGender','male'), ('requestSha256','0'*64)]:
            bad = deepcopy(self.observations[0]); raw = json.loads(base64.b64decode(bad['rawEvidence']['ttsJobBase64']))
            raw[key] = value; bad['rawEvidence']['ttsJobBase64'] = encoded(raw)
            with self.subTest(key=key), self.assertRaises(ApiError): verify_observation(bad)

    def test_unknown_shared_ledger_intent_without_native_job_is_not_hidden(self):
        f = verify_observation(self.observations[0]); rid = 'tbpasr1_'+'9'*64
        claim = {'schemaVersion':'mira.textbook.asr-pcm-dispatch.v1','pcmKey':f['pcmKey'],
            'requestId':rid,'request':{**f['origin']['attempts'][0]['request'],'requestId':rid},
            'originSha256':digest({**f['origin'],'attempts':[]}), 'historySha256':digest({}),
            'createdAt':self.fx.now,'maximumPostAttempts':1,'maximumAttemptsPerPcm':2,
            'unknownConsumesAttempt':True,'providerHints':None}
        p = self.f.root/'.textbook-asr-pcm-ledger-v1'/f['pcmKey']/'claims'/rid/'intent.json'
        p.parent.mkdir(parents=True);p.write_text(canonical(claim))
        with self.assertRaisesRegex(ApiError,'omits known'): self.prepare()


if __name__ == '__main__': unittest.main()
