"""Exact alias plus honest composite provenance. Synthetic evidence; zero provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_carrier_equivalence import exact_representation
from core.errors import ApiError
from services import textbook_preview_pronunciation_initialization as init
from services import textbook_pronunciation_probe_composite as composite
from services.textbook_preview_audio import core_content
from services.textbook_preview_visual_revision import sha_bytes
from tests import test_textbook_preview_pronunciation_initialization_v2 as fixtures
from tests.test_textbook_pinyin_pronunciation import wav_fixture, wav_receipt

V1 = registry.GARDEN3_POLICY_VERSION
V2 = registry.GARDEN3_V2_POLICY_VERSION
TEXT = 'cā bō li。'
SSML = '<speak><sub alias="擦玻璃">cā bō li</sub>。</speak>'
CORPUS = json.loads((Path(__file__).parent / 'fixtures/textbook_pinyin_garden3/corpus.v1.json').read_text())


class Garden3V2PolicyTests(unittest.TestCase):
    def test_only_one_of_150_exact_provider_requests_changes(self):
        changed = []
        for row in CORPUS['speech']:
            old = registry.provider_body(row['text'], policy_version=V1)
            new = registry.provider_body(row['text'], policy_version=V2)
            if old != new:
                changed.append(row['actionId'])
                self.assertEqual(new['input']['text'], SSML)
            self.assertEqual(registry.pronunciation_symbols(row['text'], policy_version=V1),
                             registry.pronunciation_symbols(row['text'], policy_version=V2))
        self.assertEqual(changed, ['speech-p9-word3'])
        self.assertEqual(registry.registered_policy(V2)['words'], {})
        self.assertEqual(registry.provider_body('一模一样。', policy_version=V2),
                         registry.provider_body('一模一样。', policy_version=V1))

    def test_exact_not_substring_or_normalization_and_unknown_runs_still_reject(self):
        for text in ('请听：'+TEXT, 'cā bō li', 'cā  bō li。', 'cā bō li！', TEXT+TEXT):
            self.assertEqual(registry.pinyin_ssml(text, policy_version=V2), registry.pinyin_ssml(text, policy_version=V1))
        for text in (' '+TEXT, TEXT+' ', 'cā bō li5。', 'cā bō lı。', 'ca\u0304 bō li。'):
            with self.subTest(text=text), self.assertRaises(ApiError): registry.pinyin_ssml(text, policy_version=V2)
        policy = registry.registered_policy(V2)
        policy['exactTextSsml'][TEXT] = 'caller supplied'
        self.assertEqual(registry.pinyin_ssml(TEXT, policy_version=V2), SSML)

    def test_old_twelve_policy_hashes_and_v1_request_identity_preserved(self):
        expected = {**CORPUS['priorHashes'], V1: CORPUS['policySha256']}
        self.assertEqual(len(expected), 12)
        for version, sha in expected.items(): self.assertEqual(digest(registry.registered_policy(version)), sha)
        for row in CORPUS['speech']:
            self.assertEqual(registry.provider_pronunciation(row['text'], policy_version=V1), row['providerPronunciation'])

    def test_alias_is_never_per_token_phoneme_carrier_evidence(self):
        policy = registry.registered_policy(V2)
        for transcript in ('擦玻璃。', '擦波璃。', TEXT):
            with self.subTest(transcript=transcript), self.assertRaisesRegex(ApiError, 'alias request'):
                exact_representation(TEXT, transcript, policy)
        # Unchanged requests still use the historical strict per-token contract.
        self.assertTrue(exact_representation('qí mǎ。', '骑马。', policy)['orthographicEquivalent'])


class CompositeInitializationTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.OperatorPronunciationInitializationTests()
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        self.fx = fx = fixture.fx
        self.policy = registry.registered_policy(V2)
        self.frozen = frozen = json.loads(fx.row['input_json'])
        frozen['nodeId'] = 'u3-l6'
        fx.f.classroom['scenes'][0]['actions'][0]['text'] = TEXT
        fx.f.save(fx.f.classroom)
        fx.f.db.execute('UPDATE learning_textbook_course_previews SET node_id=?,input_json=?,classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                       ('u3-l6', canonical(frozen), canonical(fx.f.classroom), digest(fx.f.classroom), fx.f.key))
        fx.f.db.raw.commit(); fx.row = fx.f.service.get(fx.f.key)
        self.dir = fx.f.root / 'composite-evidence'; self.dir.mkdir()
        self.old = registry.registered_policy(V1)
        original_lesson = {('revisionId' if key == 'alignmentRevisionId' else key): frozen[key]
                           for key in registry._BINDING_FIELDS}
        common = {'provider': self.old['providerId'], 'model': self.old['modelId'], 'voice': self.old['voiceId'],
                  'formalUseAllowed': False, 'sourceLesson': original_lesson}
        plans = {
            'garden3-v1': {**common, 'schemaVersion': 'mira.operator.phonetic-ssml-probe.v1',
                'policyVersion': V1, 'policyCanonicalSha256': digest(self.old), 'plannedCalls': 7,
                'samples': deepcopy(CORPUS['probeRequests'])},
            'garden3-alias-preregistration': {**common, 'schemaVersion': 'mira.operator.phrase-comparison-probe.v1',
                'parameterBasePolicyVersion': V1, 'parameterBasePolicyCanonicalSha256': digest(self.old),
                'registeredPolicyMatch': False, 'policyModificationAllowed': False,
                'plannedTtsCalls': 1, 'maximumPostAttemptsPerStage': 1,
                'samples': [{'label': 'ca-boli-natural-alias', 'sourceText': TEXT, 'expectedNaturalPhrase': '擦玻璃。',
                             'body': registry.provider_body(TEXT, policy_version=V2), 'ssml': SSML,
                             'ssmlSha256': sha_bytes(SSML.encode()),
                             'requestSha256': digest(registry.provider_body(TEXT, policy_version=V2))}]},
        }
        for sample in plans['garden3-v1']['samples']:
            target = CORPUS['probeTargets'][sample['label']]
            sample.update(target=target, phonemeCandidate=self.old['symbols'][target]['ph'], carrier=self.old['symbols'][target]['carrier'])
        self.plan = {'schemaVersion': composite.PLAN_SCHEMA, 'pronunciationPolicyVersion': V2,
                     'pronunciationPolicySha256': digest(self.policy), 'formalUseAllowed': False,
                     'sourceLesson': {key: frozen[key] for key in registry._BINDING_FIELDS},
                     'originPlans': [], 'samples': []}
        origin_shas = {}
        for origin, plan in plans.items():
            raw = canonical(plan).encode(); origin_shas[origin] = sha_bytes(raw)
            self.write(f'origins/{origin}/plan.json', raw)
            self.plan['originPlans'].append({'originId': origin, 'planSha256': sha_bytes(raw)})
        review_samples = []
        audio = wav_fixture()
        for label, (origin, original_label, text, target) in composite.SLOTS.items():
            prefix = f'origins/{origin}/{original_label}'
            request = canonical(registry.provider_body(text, policy_version=V2)).encode()
            request_sha = sha_bytes(request)
            response = {'request_id': 'synthetic-'+label, 'output': {'finish_reason': 'stop'}, 'usage': {'characters': 12}}
            response_raw = canonical(response).encode()
            metadata = {'provider': self.old['providerId'], 'model': self.old['modelId'], 'voice': self.old['voiceId'],
                        'requestSha256': request_sha, 'planSha256': origin_shas[origin], 'formalUseAllowed': False}
            intent = {**metadata, 'maxPostAttempts': 1, 'createdAt': '2026-01-01T00:00:00Z'}
            receipt = {**metadata, **wav_receipt(audio), 'status': 'succeeded', 'postAttempts': 1,
                'completedAt': '2026-01-01T00:00:01Z', 'ssmlSha256': sha_bytes(json.loads(request)['input']['text'].encode()),
                'playbackSha256': sha_bytes(audio), 'providerResponseSha256': sha_bytes(response_raw),
                'providerRequestId': response['request_id'], 'usage': response['usage']}
            if target is not None:
                receipt.update(policyVersion=V1, policyCanonicalSha256=digest(self.old), target=target,
                               phonemeCandidate=self.old['symbols'][target]['ph'])
            else:
                receipt.update(parameterBasePolicyVersion=V1, parameterBasePolicyCanonicalSha256=digest(self.old),
                               registeredPolicyMatch=False, target='cā bō li', subAlias='擦玻璃')
                intent['registeredPolicyMatch'] = False
            validation = {'schemaVersion': 'mira.operator.probe-wav-validation.v1', 'pcmUnchanged': True,
                          **{k: receipt[k] for k in ('audioNormalization', 'providerAudioSha256', 'playbackSha256', 'pcmSha256')}}
            raws = {'request.json': request, 'intent.json': canonical(intent).encode(), 'receipt.json': canonical(receipt).encode(),
                    'provider-response.json': response_raw, 'audio.wav': audio, 'playback.wav': audio,
                    'playback-validation.json': canonical(validation).encode()}
            for name, raw in raws.items(): self.write(prefix+'/'+name, raw)
            self.plan['samples'].append({'label': label, 'originId': origin, 'originLabel': original_label,
                                         'sourceText': text, 'requestSha256': request_sha})
            review_samples.append({'label': label, 'originId': origin, 'originLabel': original_label,
                'originPlanSha256': origin_shas[origin], 'files': {name: sha_bytes(raw) for name, raw in raws.items()},
                'providerRequestId': response['request_id'], 'result': init.OPERATOR_RESULT})
        self.write('plan.json', canonical(self.plan).encode())
        self.review = {**deepcopy(fixture.review), 'schemaVersion': composite.REVIEW_SCHEMA,
            'sourceSha256': digest(fx.f.classroom), 'coreSha256': digest(core_content(fx.f.classroom)),
            'pronunciationPolicyVersion': V2, 'pronunciationPolicySha256': digest(self.policy),
            'probePlanSha256': sha_bytes((self.dir/'plan.json').read_bytes()),
            'samples': review_samples, 'evidenceLimit': composite.LIMIT}
        fx.patch.update(expectedSourceSha256=self.review['sourceSha256'], expectedCoreSha256=self.review['coreSha256'],
                        pronunciationPolicyVersion=V2, pronunciationPolicySha256=digest(self.policy),
                        verifiedProbeEvidence={'path': str(self.dir/'operator-probe-review.json'), 'sha256': ''})
        self.seal()
        fx.f.runtime.reset_mock()

    def write(self, name, raw):
        path = self.dir/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)

    def seal(self):
        fixtures.seal(self.review)
        raw = canonical(self.review).encode(); self.write('operator-probe-review.json', raw)
        self.fx.patch['verifiedProbeEvidence']['sha256'] = sha_bytes(raw)

    def refresh_files(self, label):
        sample = next(s for s in self.review['samples'] if s['label'] == label)
        base = self.dir/'origins'/sample['originId']/sample['originLabel']
        sample['files'] = {name: sha_bytes((base/name).read_bytes()) for name in composite.PROBE_FILES}
        self.seal()

    def verify(self):
        files = init._evidence_files(self.fx.patch, self.policy)
        return init._verify_evidence(files, self.fx.patch, self.fx.f.key, self.frozen, self.policy)

    def test_prepare_activate_recover_preserves_both_original_plans_and_no_audio_claim(self):
        original = {p: p.read_bytes() for p in self.dir.rglob('*') if p.is_file()}
        source = (self.fx.f.root/(self.fx.f.cid+'.json')).read_bytes()
        self.assertTrue(self.fx.run_initialization(False)['prepared'])
        self.assertFalse((self.fx.f.folder/'plan.json').exists())
        result = self.fx.run_initialization()
        for field in ('publicationAllowed', 'generationDispatched', 'humanListeningVerified', 'perceptualToneVerified', 'requiresFormalHumanListening'):
            self.assertIs(result[field], False)
        self.assertTrue(result['requiresFormalOperatorReview'])
        self.assertEqual(self.fx.run_initialization(), result)
        self.assertEqual(self.fx.f.service.get(self.fx.f.key), self.fx.row)
        self.assertEqual((self.fx.f.root/(self.fx.f.cid+'.json')).read_bytes(), source)
        archive = self.fx.archive()
        intent = json.loads((archive/'intent.json').read_bytes())
        self.assertEqual(set(intent['files']), init._archive_files(self.policy, automatic=True))
        for p, raw in original.items():
            self.assertEqual(p.read_bytes(), raw)
            self.assertEqual((archive/'evidence'/p.relative_to(self.dir)).read_bytes(), raw)
        self.fx.assert_no_external_write()

    def test_missing_duplicate_extra_or_wrong_origin_rejected(self):
        old = deepcopy(self.review)
        variants = [old['samples'][:-1], old['samples']+[old['samples'][0]],
                    old['samples'][:-1]+[old['samples'][0]],
                    [{**old['samples'][0], 'originId': 'garden3-alias-preregistration'}, *old['samples'][1:]]]
        for samples in variants:
            self.review = {**deepcopy(old), 'samples': samples}; self.seal()
            with self.assertRaises(ApiError): self.verify()

    def test_alias_cannot_be_relabelled_as_phoneme_or_registered_at_generation(self):
        label = 'ca-boli-natural-alias'; path = self.dir/'origins/garden3-alias-preregistration'/label/'receipt.json'
        old = json.loads(path.read_bytes())
        for key, value in [('policyVersion', V2), ('phonemeCandidate', 'li5'), ('registeredPolicyMatch', True), ('target', 'li')]:
            path.write_text(canonical({**old, key: value})); self.refresh_files(label)
            with self.subTest(key=key), self.assertRaises(ApiError): self.verify()

    def test_original_plan_binding_cannot_be_replaced_by_composite_digest(self):
        label = 'qi-ma-context'; base = self.dir/'origins/garden3-v1'/label
        for filename in ('intent.json','receipt.json'):
            path = base/filename; raw = path.read_bytes(); item=json.loads(raw)
            item['planSha256']=self.review['probePlanSha256']; path.write_text(canonical(item)); self.refresh_files(label)
            with self.subTest(filename=filename), self.assertRaises(ApiError): self.verify()
            path.write_bytes(raw); self.refresh_files(label)

    def test_request_parameter_or_text_change_rejected_even_with_rebound_file_hash(self):
        label='ca-boli-natural-alias'; path=self.dir/'origins/garden3-alias-preregistration'/label/'request.json'
        old=json.loads(path.read_bytes())
        for field,value in [('voice','other'),('rate',1.1),('text',SSML.replace('擦玻璃','擦波璃'))]:
            item=deepcopy(old);item['input'][field]=value;path.write_text(canonical(item));self.refresh_files(label)
            with self.subTest(field=field),self.assertRaises(ApiError):self.verify()

    def test_unknown_failure_second_post_and_missing_intent_fail_closed(self):
        label='qi-ma-context'; base=self.dir/'origins/garden3-v1'/label
        for filename,field,value in [('receipt.json','status','unknown'),('receipt.json','postAttempts',2),
                                     ('intent.json','maxPostAttempts',2),('intent.json','createdAt','2027-01-01T00:00:00Z')]:
            path=base/filename;raw=path.read_bytes();item=json.loads(raw);item[field]=value
            path.write_text(canonical(item));self.refresh_files(label)
            with self.subTest(field=field),self.assertRaises(ApiError):self.verify()
            path.write_bytes(raw);self.refresh_files(label)

    def test_wav_or_response_tamper_rejected(self):
        label='qi-ma-context';base=self.dir/'origins/garden3-v1'/label
        for filename in ('audio.wav','playback.wav','provider-response.json','playback-validation.json'):
            path=base/filename;raw=path.read_bytes()
            if filename == 'playback-validation.json':
                changed=json.loads(raw);changed['pcmUnchanged']=False;path.write_text(canonical(changed))
            else:
                path.write_bytes(raw+b' ')
            self.refresh_files(label)
            with self.subTest(filename=filename),self.assertRaises(ApiError):self.verify()
            path.write_bytes(raw);self.refresh_files(label)

    def test_source_authorization_and_false_claims_remain_required(self):
        old=deepcopy(self.review)
        for field,value in [('humanListeningVerified',True),('perceptualToneVerified',True),('formalUseAllowed',True),
                            ('sourceSha256','0'*64),('coreSha256','0'*64),('evidenceLimit','li5 passed'),
                            ('schemaVersion',init.OPERATOR_REVIEW_SCHEMA)]:
            self.review={**deepcopy(old),field:value};self.seal()
            with self.subTest(field=field),self.assertRaises(ApiError):self.verify()
        self.review=deepcopy(old);self.review['authorization']['scope']['subject']='math'
        fixtures.seal(self.review['authorization']);self.seal()
        with self.assertRaises(ApiError):self.verify()

    def test_old_human_format_or_outside_evidence_symlink_rejected(self):
        with self.assertRaises(ApiError):init._archive_files(self.policy,automatic=False)
        label='qi-ma-context';path=self.dir/'origins/garden3-v1'/label/'audio.wav';raw=path.read_bytes()
        outside=self.fx.f.root/'outside.wav';outside.write_bytes(raw);path.unlink();path.symlink_to(outside)
        with self.assertRaises(ApiError):self.verify()

    def test_recovery_detects_archive_tamper_and_unknown_staging_without_overwrite(self):
        self.fx.run_initialization(False)
        path=self.fx.archive()/'evidence/origins/garden3-v1/qi-ma-context/receipt.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ApiError):self.fx.run_initialization()
        self.assertFalse((self.fx.f.folder/'plan.json').exists());self.fx.assert_no_external_write()

    def test_zero_audio_and_unknown_staging_guards_still_block_activation(self):
        self.fx.run_initialization(False)
        path=self.fx.f.folder/'plan.json.tmp';path.write_bytes(b'unknown partial request')
        with self.assertRaises(ApiError):self.fx.run_initialization()
        self.assertEqual(path.read_bytes(),b'unknown partial request')
        path.unlink();receipt=self.fx.f.folder/'receipts.json';receipt.write_bytes(b'[]')
        with self.assertRaises(ApiError):self.fx.run_initialization()
        self.assertEqual(receipt.read_bytes(),b'[]')
        self.assertFalse((self.fx.f.folder/'plan.json').exists());self.fx.assert_no_external_write()


if __name__ == '__main__': unittest.main()
