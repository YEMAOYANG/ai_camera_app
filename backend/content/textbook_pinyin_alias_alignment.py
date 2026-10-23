"""One registered natural-word alias, not phoneme or perceptual evidence.

No provider calls or score changes. Builders require the actual source object;
portable validation receives the source identity verified by the release caller.
The entire original audit, formal request, WAV and no-hint ASR body stay bound.
"""
import base64
from copy import deepcopy
import hashlib
import unicodedata

from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import (
    GARDEN3_V2_POLICY_VERSION, policy_for_plan, provider_body, registered_policy,
    validate_formal_receipt, validate_receipt_wav,
)
from content.textbook_preview_audio_contract import audit_segment_plan, _normalize
from core.errors import ApiError

SCHEMA = 'mira.textbook.exact-alias-asr-evidence.v1'
METHOD = 'registered-exact-natural-word-alias-full-transcript'
TEXT = 'cā bō li。'
ALIAS = '擦玻璃'
SSML = '<speak><sub alias="擦玻璃">cā bō li</sub>。</speak>'
LIMIT = 'Exact natural-word alias content alignment only; not per-token phoneme, li5, human listening, phonetic accuracy or perceptual tone verification.'


def fail(message):
    raise ApiError('textbook_exact_alias_alignment_invalid', message, 409)


def _entry(*, source, plan, classroom, audit, expected_source_sha256):
    # Lazy imports keep the optional recheck exclusion on the same validator.
    from content.textbook_audio_recheck import raw_entries, validate_tts_request_plan, provider_body as asr_body
    scenes, actions, raw = raw_entries(plan=plan, classroom=classroom, audit=audit,
                                      expected_source_sha256=expected_source_sha256)
    if not isinstance(source, dict): fail('Missing original alias request evidence')
    fields = {'sceneId', 'actionId', 'ttsReceipt', 'audioBase64'}
    receipt = source.get('ttsReceipt')
    if isinstance(receipt, dict) and receipt.get('narrationRevisionId') is not None:
        fields.add('requestPlan')
    if set(source) != fields or not isinstance(receipt, dict): fail('Unknown alias evidence fields')
    key = source['sceneId'], source['actionId']
    action, original = actions.get(key), raw.get(key)
    if (action is None or action.get('text') != TEXT or original is None
            or original['comparison']['passed'] is not False or original['similarityBps'] != 0
            or receipt.get('status') != 'succeeded' or receipt.get('completionUsable') is False
            or receipt.get('audioSha256') != original['audioSha256']):
        fail('Only the exact formal alias source and unchanged literal-zero audit are supported')
    effective = validate_tts_request_plan(plan, scenes[key[0]], action, receipt, source.get('requestPlan'))
    policy = policy_for_plan(effective)
    registered = registered_policy(GARDEN3_V2_POLICY_VERSION)
    if (policy != registered or policy.get('words') != {}
            or policy.get('exactTextSsml') != {TEXT: SSML}
            or audit_segment_plan(plan, action, original, scene_id=key[0]).get('pronunciationPolicySha256') != digest(policy)):
        fail('The actual formal TTS and original ASR must use the registered garden3 v2 exact alias')
    validate_formal_receipt(receipt, TEXT, policy_version=policy['policyVersion'])
    response = original['asr']
    validate_formal_receipt(response, TEXT, policy_version=policy['policyVersion'])
    try:
        encoded = source['audioBase64']
        if not isinstance(encoded, str) or len(encoded) > 16_000_000: raise ValueError()
        audio = base64.b64decode(encoded, validate=True)
        if base64.b64encode(audio).decode('ascii') != encoded: raise ValueError()
    except (TypeError, ValueError): fail('Invalid alias WAV encoding')
    validate_receipt_wav(receipt, audio)
    body = provider_body(TEXT, policy_version=policy['policyVersion'])
    transcript = response.get('transcript')
    if (body['input']['text'] != SSML or response.get('completionUsable') is not True
            or not isinstance(transcript, str) or not transcript or len(transcript) > 8000
            # The shared normalizer also removes symbols/format characters.
            # This stricter alias contract permits only punctuation/whitespace
            # between the exact CJK characters, never emoji, zero-width text or
            # compatibility-character substitutions.
            or any(c not in ALIAS and not c.isspace() and not unicodedata.category(c).startswith('P')
                   for c in transcript)
            or any(unicodedata.category(c).startswith('C') and c not in '\t\n\r' for c in transcript)
            or _normalize(transcript) != ALIAS
            or response.get('providerAsrBodySha256') != hashlib.sha256(asr_body(audio)).hexdigest()
            or response['providerPronunciation'] != receipt['providerPronunciation']):
        fail('The complete no-hint ASR transcript must exactly normalize to the registered natural alias')
    metadata = action.get('audioMetadata', {})
    if (any(metadata.get(k) != policy[k] for k in ('providerId', 'modelId', 'voiceId'))
            or metadata.get('fallbackUsed') is not False):
        fail('Formal classroom audio metadata does not match the actual alias voice')
    return {**deepcopy(source), **{k: original[k] for k in ('textSha256', 'ttsRequestId', 'audioSha256')},
        'pcmSha256': receipt['pcmSha256'], 'requestPlanSha256': digest(effective),
        'policySha256': digest(policy), 'ttsReceiptSha256': digest(receipt),
        'auditSegmentSha256': digest(original), 'asrReceiptSha256': digest(response),
        'providerBodySha256': receipt['providerPronunciation']['providerBodySha256'],
        'ssmlSha256': receipt['providerPronunciation']['ssmlSha256'],
        'originalLiteralPassed': False, 'originalSimilarityBps': 0,
        'normalizedTranscript': ALIAS, 'aliasContentAligned': True}


def _assemble(*, sources, plan, classroom, audit, expected_source_sha256, recorded_at):
    if type(recorded_at) is not int or recorded_at <= 0: fail('Invalid evidence time')
    if not isinstance(sources, list) or len(sources) != 1:
        fail('Exactly one registered alias action is supported')
    entry = _entry(source=sources[0], plan=plan, classroom=classroom, audit=audit,
                   expected_source_sha256=expected_source_sha256)
    # All speech identities/texts/audio IDs are portable across media relocation.
    speech = [{'sceneId': s['id'], 'actionId': a['id'], 'text': a['text'], 'audioId': a.get('audioId')}
              for s in classroom['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
    value = {'schemaVersion': SCHEMA, 'method': METHOD, 'previewKey': plan['previewKey'],
        'sourceClassroomId': classroom['id'], 'sourceSha256': expected_source_sha256,
        'sourceSpeechSha256': digest(speech), 'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'auditSha256': digest(audit), 'recordedAt': recorded_at, 'segments': [entry],
        'minimumSimilarityBpsUnchanged': 8500, 'humanListeningVerified': False,
        'phoneticAccuracyVerified': False, 'perceptualToneVerified': False,
        'perTokenPhonemeVerified': False, 'evidenceLimit': LIMIT}
    value['sha256'] = digest(value)
    return value


def build_evidence(*, sources, plan, classroom, audit, expected_source_sha256, recorded_at):
    if digest(classroom) != expected_source_sha256: fail('Current full source bytes changed')
    return _assemble(sources=sources, plan=plan, classroom=classroom, audit=audit,
                     expected_source_sha256=expected_source_sha256, recorded_at=recorded_at)


def validate_evidence(value, *, plan, classroom, audit, expected_source_sha256, now_ms,
                      expected_source_classroom_id=None):
    """Only a portable release caller may supply its independently frozen source ID."""
    if expected_source_classroom_id is None:
        if digest(classroom) != expected_source_sha256: fail('Current full source bytes changed')
    elif not isinstance(expected_source_classroom_id, str) or not expected_source_classroom_id:
        fail('Missing verified original classroom identity')
    if (not isinstance(value, dict) or not isinstance(value.get('segments'), list)
            or type(value.get('recordedAt')) is not int or type(now_ms) is not int
            or not 0 < value['recordedAt'] <= now_ms):
        fail('Invalid alias manifest/time')
    sources = []
    for item in value['segments']:
        if not isinstance(item, dict): fail('Invalid alias entry')
        fields = {'sceneId', 'actionId', 'ttsReceipt', 'audioBase64'}
        if isinstance(item.get('ttsReceipt'), dict) and item['ttsReceipt'].get('narrationRevisionId') is not None:
            fields.add('requestPlan')
        sources.append({k: item.get(k) for k in fields})
    original = classroom if expected_source_classroom_id is None else {**classroom, 'id': expected_source_classroom_id}
    expected = _assemble(sources=sources, plan=plan, classroom=original, audit=audit,
                         expected_source_sha256=expected_source_sha256, recorded_at=value['recordedAt'])
    if value != expected: fail('Alias evidence differs from its original formal request and complete raw ASR')
    return {(e['sceneId'], e['actionId']): deepcopy(e) for e in expected['segments']}
