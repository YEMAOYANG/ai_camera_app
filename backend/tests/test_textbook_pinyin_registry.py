"""Lesson-bound production policies and private policy-rotation fixtures."""
from contextlib import contextmanager
from copy import deepcopy
from types import MappingProxyType
import unittest
from unittest.mock import Mock, patch

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_asr_reconciliation import validate_reconciliation
from content.textbook_preview_audio_contract import (
    asr_request_id, audit_contract_identity, check_receipt_pronunciation,
    compare_transcript, pronunciation_client_options, resolve_audio_contract,
    tts_request_id,
)
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from tests.test_textbook_pinyin_pronunciation import (
    PINYIN_BINDING, pinyin_plan, sign, usage_receipt, wav_receipt,
)


@contextmanager
def rotated_registry(*, allow_old=True):
    """A deliberately synthetic symbol mapping, never a usable lesson policy."""
    old = registry.registered_policy()
    new = deepcopy(old)
    new['policyVersion'] = 'mira.test.synthetic-pinyin.v2'
    new['symbols']['e'] = {'ph': 'e2', 'carrier': '鹅'}
    new['symbols']['i'] = {'ph': 'a1', 'carrier': '啊'}
    binding = tuple(PINYIN_BINDING[k] for k in registry._BINDING_FIELDS)
    allowed = {new['policyVersion']}
    if allow_old:
        allowed.add(old['policyVersion'])
    with patch.object(registry, '_POLICIES', MappingProxyType({
            old['policyVersion']: canonical(old), new['policyVersion']: canonical(new)})), \
         patch.object(registry, '_LESSON_POLICIES', MappingProxyType({binding: new['policyVersion']})), \
         patch.object(registry, '_ALLOWED_LESSON_POLICIES', MappingProxyType({binding: frozenset(allowed)})):
        yield old, new


def tts_response(request, text, version):
    policy = registry.registered_policy(version)
    result = {'success': True, 'state': 'succeeded', 'requestId': request,
        'mimeType': 'audio/wav', **wav_receipt(), **usage_receipt('e'),
        **{k: policy[k] for k in ('providerId', 'modelId', 'voiceId')},
        'providerPronunciation': registry.provider_pronunciation(text, policy_version=version)}
    result['budgetMeasurement']['characters'] = len(registry.pinyin_ssml(text, policy_version=version))
    return result


class PinyinRegistryTests(unittest.TestCase):
    def test_registry_is_detached_from_callers_and_legacy_alias(self):
        expected = registry.registered_policy()
        copy = registry.registered_policy()
        copy['symbols']['e']['ph'] = 'wrong'
        with patch.dict(registry.POLICY, {'voiceId': 'caller-injected'}):
            self.assertEqual(registry.registered_policy(), expected)
            self.assertEqual(registry.policy_for_plan(pinyin_plan()), expected)
        self.assertEqual(registry.POLICY_SHA256, digest(expected))

    def test_missing_unknown_or_unallowed_plan_identity_fails_closed(self):
        plan = pinyin_plan()
        cases = []
        for version in (None, '', 'mira.unregistered.v1'):
            bad = deepcopy(plan)
            bad['pronunciationPolicy']['policyVersion'] = version
            bad['pronunciationPolicySha256'] = digest(bad['pronunciationPolicy'])
            cases.append(bad)
        missing = deepcopy(plan)
        missing['pronunciationPolicy'].pop('policyVersion')
        cases.append(missing)
        for field in ('editionId', 'alignmentRevisionId', 'nodeId', 'gradeCode'):
            bad = deepcopy(plan)
            bad['binding'][field] += '-other'
            cases.append(bad)
        for bad in cases:
            with self.subTest(plan=bad['pronunciationPolicy'].get('policyVersion'), binding=bad['binding']), self.assertRaises(ApiError):
                resolve_audio_contract(bad)
        with self.assertRaises(ApiError):
            registry.select_policy({**PINYIN_BINDING, 'nodeId': 'unregistered-next-lesson'})

    def test_iuu_requires_initialization_and_cannot_substitute_aoe_policy(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u2-l2'}
        policy = registry.select_policy(binding)
        self.assertEqual(policy['policyVersion'], 'mira.textbook.pinyin-iuu-ssml.v1')
        self.assertEqual(digest(policy), '09776788ae5c1dfbbf137179be923550e5838256f5abd30ae8b78b5493f2f8fb')
        self.assertTrue(registry.initialization_required(binding))
        for other in (None, {}, PINYIN_BINDING, {**binding, 'gradeCode': 'primary_2'},
                      {**binding, 'nodeId': ['u2-l2']}):
            self.assertFalse(registry.initialization_required(other))
        plan = pinyin_plan()
        plan['binding'] = binding
        with self.assertRaises(ApiError):
            registry.policy_for_plan(plan)
        plan['pronunciationPolicy'] = policy
        plan['pronunciationPolicySha256'] = digest(policy)
        self.assertEqual(registry.policy_for_plan(plan), policy)
        plan['binding'] = PINYIN_BINDING
        with self.assertRaises(ApiError):
            registry.policy_for_plan(plan)

    def test_iuu_ssml_retains_tones_and_rejects_unregistered_letters(self):
        version = registry.IUU_POLICY_VERSION
        text = '请听，i ī í ǐ ì，u ū ú ǔ ù，ü ǖ ǘ ǚ ǜ。'
        symbols = registry.pronunciation_symbols(text, policy_version=version)
        self.assertEqual([item['ph'] for item in symbols],
                         ['yi1', 'yi1', 'yi2', 'yi3', 'yi4',
                          'wu1', 'wu1', 'wu2', 'wu3', 'wu4',
                          'yu1', 'yu1', 'yu2', 'yu3', 'yu4'])
        self.assertEqual([item['carrier'] for item in symbols], ['衣'] * 5 + ['乌'] * 5 + ['迂'] * 5)
        body = registry.provider_body(text, policy_version=version)
        self.assertEqual(body['input']['voice'], 'longanwen_v3')
        self.assertEqual(body['input']['text'].count('<phoneme '), 15)
        self.assertIn('<phoneme alphabet="py" ph="yu3">迂</phoneme>', body['input']['text'])
        self.assertEqual(registry.pinyin_ssml('请听 & 再试。', policy_version=version),
                         '<speak>请听 &amp; 再试。</speak>')
        for unsupported in ('e', 'a', 'o', 'A', 'yi', 'u\u0308'):
            with self.subTest(unsupported=unsupported), self.assertRaises(ApiError):
                registry.pinyin_ssml('请读' + unsupported, policy_version=version)
        self.assertEqual(registry.POLICY_SHA256,
                         'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7')

    def test_current_default_rotation_preserves_historical_allowed_plan(self):
        old_plan = pinyin_plan()
        before = canonical(old_plan)
        request = tts_request_id(old_plan, 's', 'a', 'e，请跟读。')
        with rotated_registry() as (old, new):
            new_plan = pinyin_plan()
            self.assertEqual(registry.policy_for_plan(old_plan), old)
            self.assertEqual(registry.policy_for_plan(new_plan), new)
            self.assertEqual(pronunciation_client_options(old_plan), {'pronunciation_policy_version': old['policyVersion']})
            self.assertEqual(pronunciation_client_options(new_plan), {'pronunciation_policy_version': new['policyVersion']})
            self.assertEqual(tts_request_id(old_plan, 's', 'a', 'e，请跟读。'), request)
            self.assertNotEqual(tts_request_id(new_plan, 's', 'a', 'e，请跟读。'), request)
            resolve_audio_contract(old_plan)
            resolve_audio_contract(new_plan)
        self.assertEqual(canonical(old_plan), before)
        with rotated_registry(allow_old=False), self.assertRaises(ApiError):
            resolve_audio_contract(old_plan)

    def test_receipt_cannot_select_its_policy_even_with_same_provider_and_voice(self):
        old_plan = pinyin_plan()
        with rotated_registry() as (old, new):
            new_plan = pinyin_plan()
            for expected_plan, wrong_policy in ((old_plan, new), (new_plan, old)):
                text = 'e，请跟读。'
                request = tts_request_id(expected_plan, 's', 'a', text)
                expected = registry.policy_for_plan(expected_plan)['policyVersion']
                good = tts_response(request, text, expected)
                check_receipt_pronunciation(expected_plan, {**good, 'status': 'succeeded'}, text)
                bad = tts_response(request, text, wrong_policy['policyVersion'])
                with self.assertRaises(ApiError):
                    check_receipt_pronunciation(expected_plan, {**bad, 'status': 'succeeded'}, text)
                client = OpenMaicFullRuntimeClient('http://127.0.0.1:3100', formal_audio_internal_token='synthetic-token-' * 3)
                client._request_formal_audio_json = Mock(return_value=bad)
                with self.assertRaises(OpenMaicFullRuntimeError):
                    client.get_formal_audio_tts(request, **pronunciation_client_options(expected_plan))
                asr_request = asr_request_id(expected_plan, request, good['audioSha256'])
                asr = {'success': True, 'state': 'succeeded', 'requestId': asr_request,
                    'transcriptSha256': registry.sha_text(text), 'providerId': 'qwen-asr',
                    'modelId': 'qwen3-asr-flash', 'providerAsrBodySha256': '9' * 64,
                    'providerPronunciation': bad['providerPronunciation']}
                client._request_formal_audio_json.return_value = asr
                with self.assertRaises(OpenMaicFullRuntimeError):
                    client.get_formal_audio_asr(asr_request, **pronunciation_client_options(expected_plan))
            bad_plan = deepcopy(new_plan)
            bad_plan['teacher']['voiceId'] = 'caller-injected'
            with self.assertRaises(ApiError): resolve_audio_contract(bad_plan)

    def test_unregistered_client_selector_never_reaches_transport(self):
        client = OpenMaicFullRuntimeClient('http://127.0.0.1:3100', formal_audio_internal_token='synthetic-token-' * 3)
        client._request_formal_audio_json = Mock()
        for request in ('tbptts1_' + 'a' * 64, 'tbpasr1_' + 'b' * 64):
            with self.assertRaises(OpenMaicFullRuntimeError):
                client.get_formal_audio_tts(request, pronunciation_policy_version='caller-injected')
        with self.assertRaises(OpenMaicFullRuntimeError):
            client.get_formal_audio_tts('tbtts_fixture', pronunciation_policy_version=registry.AOE_POLICY_VERSION)
        client._request_formal_audio_json.assert_not_called()

    def test_listening_and_reconciliation_use_selected_symbols_and_receipts(self):
        from tests.test_textbook_pinyin_asr_reconciliation import PinyinAsrReconciliationTests
        fixture = PinyinAsrReconciliationTests()
        fixture.setUp()
        context = fixture.context
        with rotated_registry() as (_, new):
            plan = pinyin_plan()
            version = new['policyVersion']
            context['plan'] = plan
            segments = context['audit']['segments']
            for scene, entry in zip(context['classroom']['scenes'], segments):
                action = scene['actions'][0]
                action['text'] = action['text'].replace('ā', 'i')
                text = action['text']
                action['audioId'] = tts_request_id(plan, scene['id'], action['id'], text)
                entry.update(text=text, textSha256=registry.sha_text(text), ttsRequestId=action['audioId'])
                comparison = compare_transcript(plan, text, entry['transcript'])
                entry.update(comparison=comparison, similarityBps=comparison['similarityBps'])
                entry['asr'].update(requestId=asr_request_id(plan, action['audioId'], entry['audioSha256']),
                    providerPronunciation=registry.provider_pronunciation(text, policy_version=version))
            listening = context['listening_review']
            listening.update(planSha256=digest(plan), coreSha256=plan['coreSha256'])
            for heard, entry in zip(listening['segments'], segments):
                heard.update(textSha256=entry['textSha256'], ttsRequestId=entry['ttsRequestId'])
            sign(listening)
            context['expected_source_sha256'] = digest(context['classroom'])
            audit = context['audit']
            audit.update(sourceSha256=context['expected_source_sha256'], contract=audit_contract_identity(plan),
                         listeningReview=deepcopy(listening))
            sign(audit)
            manifest = fixture.make_manifest(context)
            self.assertEqual(len(validate_reconciliation(manifest, **context)), 2)
            # Re-sealing every outer object cannot legitimize a different policy's receipt.
            segments[1]['asr']['providerPronunciation'] = registry.provider_pronunciation(segments[1]['text'])
            sign(audit)
            manifest = fixture.make_manifest(context)
            with self.assertRaises(ApiError): validate_reconciliation(manifest, **context)

    def test_narrator_passes_frozen_selector_through_get_and_post(self):
        from tests.test_textbook_pinyin_narrator import PinyinNarratorTests
        from services.textbook_preview_audio import narrate_preview
        harness = PinyinNarratorTests()
        self.addCleanup(harness.doCleanups)
        with rotated_registry() as (_, new):
            fixture = harness.fixture()
            version = new['policyVersion']
            def dispatch(method, route, payload, **kwargs):
                self.assertEqual(payload['pronunciationProfile'], registry.pronunciation_identity(payload['text'], policy_version=version))
                self.assertEqual(set(payload['pronunciationProfile']), {'policyVersion', 'policySha256', 'ssmlSha256'})
                self.assertNotIn('pronunciation_policy_version', payload)
                return tts_response(payload['requestId'], payload['text'], version)
            fixture.client._request_formal_audio_json.side_effect = dispatch
            result = narrate_preview(fixture.service, fixture.key, fixture.root)
            self.assertEqual(result['status'], 'preview_ready')
            self.assertEqual(fixture.runtime.start_formal_audio_tts.call_count, 8)
            for call in fixture.runtime.get_formal_audio_tts.call_args_list + fixture.runtime.start_formal_audio_tts.call_args_list:
                self.assertEqual(call.kwargs['pronunciation_policy_version'], version)
