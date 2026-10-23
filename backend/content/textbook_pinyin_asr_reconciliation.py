"""Independent human review of v3 pinyin ASR discrepancies; no I/O or score edits.

All ``*Sha256`` object bindings use ``digest`` of the complete referenced object,
including its seal when present. This differs from that object's own ``sha256``
seal (which omits itself). The caller must authenticate the actual human statement;
the explicit scope/flags below must never be inferred from pronunciation approval.

The caller supplies ``expected_source_sha256`` from its verified original source or
publication frozen record, not from this manifest. A published classroom may have
renamed stage/media URLs, but must retain every original speech ID/text/audio ID.
Live publication must still verify all original TTS receipts and WAV bytes; portable
release validation must still verify their original SHA through archived media.
This helper does not replace either check and never reports literal ASR success.
"""
from copy import deepcopy

from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import (
    PLAN_SCHEMA, SHA, policy_for_plan, pronunciation_symbols, validate_listening_review,
)
from content.textbook_preview_audio_contract import (
    audit_contract_identity, resolve_audio_contract, tts_request_id,
    validate_v2_audit_segment,
)
from core.errors import ApiError


SCHEMA = 'mira.textbook.pinyin-asr-reconciliation.v1'
HUMAN_SCHEMA = 'mira.textbook.pinyin-whole-sentence-listening.v1'
ACCEPTANCE_METHOD = 'human-listening-reconciliation'
CONFIRMATION_SCOPE = 'whole-sentence-content-and-pronunciation'
IDENTITY_FIELDS = {'sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256'}
BINDING_FIELDS = {'previewKey', 'planSha256', 'sourceSha256', 'auditSha256', 'listeningReviewSha256'}
CONFIRMATION_FIELDS = {'wholeSentenceMatchesSource', 'noOmissions', 'noSubstitutions', 'noAdditions'}


def fail(message):
    raise ApiError('textbook_pinyin_asr_reconciliation_invalid', message, 409)


def _fields(value, expected, description):
    if not isinstance(value, dict) or set(value) != expected:
        fail(description + '字段不完整或含未知字段')


def _sealed(value, description):
    if (not isinstance(value, dict)
            or value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'})):
        fail(description + '摘要不一致')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _key(value):
    if not isinstance(value, dict) or not all(_text(value.get(k)) for k in ('sceneId', 'actionId')):
        fail('审核段落身份不完整')
    return value['sceneId'], value['actionId']


def _time(value, now_ms):
    return type(value) is int and 0 < value <= now_ms


def validate_reconciliation(manifest, *, plan, classroom, audit, listening_review,
                            expected_source_sha256, now_ms):
    """Return detached ``(sceneId, actionId) -> accepted discrepancy`` entries.

    Reject missing/extra/duplicate low-score entries, even if outer hashes have
    been recomputed. The manifest embeds a separately sealed ``humanReview``;
    its exact entries and statement explicitly confirm whole-sentence fidelity.
    No legacy/v2 or non-pinyin failure can use this path.
    """
    if not isinstance(plan, dict) or plan.get('schemaVersion') != PLAN_SCHEMA:
        fail('只有正式 v3 拼音配音可进行独立人工复核')
    contract = resolve_audio_contract(plan)
    policy = policy_for_plan(plan)
    if (type(now_ms) is not int or now_ms <= 0
            or not isinstance(expected_source_sha256, str) or not SHA.fullmatch(expected_source_sha256)
            or contract['comparisonPolicy']['version'] != 'literal-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('原始课堂摘要、时间或逐字比较合同无效')
    _sealed(audit, '原始 ASR 审计')
    if (audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or audit.get('previewKey') != plan['previewKey']
            or audit.get('sourceSha256') != expected_source_sha256
            or audit.get('contract') != audit_contract_identity(plan)
            or audit.get('listeningReview') != listening_review
            or audit.get('passed') is not False
            or not isinstance(audit.get('segments'), list)):
        fail('必须保留当前完整原始审计及其未通过状态')

    if not isinstance(classroom, dict) or not isinstance(classroom.get('scenes'), list):
        fail('当前课堂结构不完整')
    actions = {}
    action_ids = set()
    for scene in classroom['scenes']:
        if (not isinstance(scene, dict) or not _text(scene.get('id'))
                or not isinstance(scene.get('actions', []), list)):
            fail('当前课堂页面结构不完整')
        for action in scene.get('actions', []):
            if not isinstance(action, dict):
                fail('当前课堂动作结构不完整')
            if action.get('type') != 'speech':
                continue
            if not all(_text(action.get(k)) for k in ('id', 'text', 'audioId')):
                fail('当前旁白缺少原文或正式音频身份')
            key = (scene['id'], action['id'])
            if key in actions or action['id'] in action_ids:
                fail('当前课堂旁白身份重复')
            if action['audioId'] != tts_request_id(plan, *key, action['text']):
                fail('当前旁白不属于冻结的正式拼音配音计划')
            actions[key] = action
            action_ids.add(action['id'])
    heard = validate_listening_review(plan, classroom, listening_review, now_ms=now_ms)
    seen, low = set(), {}
    for entry in audit['segments']:
        key = _key(entry)
        if key in seen or key not in actions:
            fail('原始审计含重复或额外旁白')
        seen.add(key)
        if (not isinstance(entry.get('asr'), dict)
                or not isinstance(entry.get('comparison'), dict)
                or type(entry['comparison'].get('passed')) is not bool
                or type(entry.get('similarityBps')) is not int
                or not isinstance(entry.get('audioSha256'), str) or not SHA.fullmatch(entry['audioSha256'])
                or entry['asr'].get('completionUsable') is False):
            fail('原始 ASR 回执或音频摘要无效')
        passed = validate_v2_audit_segment(plan, actions[key], entry, scene_id=key[0])
        if key in heard and any(heard[key][k] != entry.get(k) for k in IDENTITY_FIELDS):
            fail('人听证据与原始审计的正式音频不一致')
        if not passed:
            if (entry['similarityBps'] >= 8500 or not pronunciation_symbols(
                    entry['text'], policy_version=policy['policyVersion'])
                    or key not in heard):
                fail('独立人工复核只接受有精确人听证据的拼音低分段')
            low[key] = entry
    if not actions or seen != set(actions) or not low:
        fail('原始审计必须完整覆盖当前课堂且有明确拼音低分段')

    bindings = {'previewKey': plan['previewKey'], 'planSha256': digest(plan),
                'sourceSha256': expected_source_sha256, 'auditSha256': digest(audit),
                'listeningReviewSha256': digest(listening_review)}
    _fields(manifest, BINDING_FIELDS | {'schemaVersion', 'literalPassed', 'acceptanceMethod',
            'humanReview', 'humanReviewSha256', 'reviewer', 'reviewedAt', 'segments', 'sha256'}, '人工复核清单')
    _sealed(manifest, '人工复核清单')
    if (manifest['schemaVersion'] != SCHEMA or manifest['literalPassed'] is not False
            or manifest['acceptanceMethod'] != ACCEPTANCE_METHOD
            or any(manifest[k] != v for k, v in bindings.items())
            or not _text(manifest['reviewer']) or not _time(manifest['reviewedAt'], now_ms)
            or not isinstance(manifest['segments'], list)):
        fail('人工复核清单与当前证据不一致')

    human = manifest['humanReview']
    _fields(human, BINDING_FIELDS | {'schemaVersion', 'confirmationScope', 'reviewer',
            'reviewedAt', 'statement', 'segments', 'sha256'}, '整句人听记录')
    _sealed(human, '整句人听记录')
    if (human['schemaVersion'] != HUMAN_SCHEMA or human['confirmationScope'] != CONFIRMATION_SCOPE
            or any(human[k] != v for k, v in bindings.items())
            or manifest['humanReviewSha256'] != digest(human)
            or not _text(human['reviewer']) or not _text(human['statement'])
            or not _time(human['reviewedAt'], manifest['reviewedAt'])
            or not isinstance(human['segments'], list)):
        fail('需要明确的整句内容人听确认，不能用仅发音确认代替')
    confirmations = {}
    for item in human['segments']:
        _fields(item, IDENTITY_FIELDS | CONFIRMATION_FIELDS | {'verdict'}, '整句确认条目')
        key = _key(item)
        if (key in confirmations or key not in low or item['verdict'] != 'accepted'
                or any(item[k] is not True for k in CONFIRMATION_FIELDS)
                or any(item[k] != low[key].get(k) for k in IDENTITY_FIELDS)
                or human['reviewedAt'] < heard[key]['reviewedAt']):
            fail('整句确认必须逐段对应原始正式音频且明确无漏读、错读或多读')
        confirmations[key] = item
    if set(confirmations) != set(low):
        fail('整句确认没有精确覆盖全部低分段')

    accepted = {}
    for item in manifest['segments']:
        _fields(item, IDENTITY_FIELDS | {'asrRequestId', 'asrReceiptSha256', 'auditSegmentSha256',
                'listeningEntrySha256', 'humanEntrySha256', 'literalPassed', 'similarityBps',
                'acceptanceMethod', 'discrepancyRationale'}, '差异复核条目')
        key = _key(item)
        if key in accepted or key not in low:
            fail('差异复核包含重复或额外段落')
        entry = low[key]
        expected = {**{k: entry[k] for k in IDENTITY_FIELDS},
                    'asrRequestId': entry['asr']['requestId'], 'asrReceiptSha256': digest(entry['asr']),
                    'auditSegmentSha256': digest(entry), 'listeningEntrySha256': digest(heard[key]),
                    'humanEntrySha256': digest(confirmations[key]), 'literalPassed': False,
                    'similarityBps': entry['similarityBps'], 'acceptanceMethod': ACCEPTANCE_METHOD}
        if (any(item[k] != v for k, v in expected.items()) or item['literalPassed'] is not False
                or type(item['similarityBps']) is not int or not _text(item['discrepancyRationale'])):
            fail('差异复核没有绑定原始回执、原分数或明确的人工差异理由')
        accepted[key] = deepcopy(item)
    if set(accepted) != set(low):
        fail('差异复核没有精确覆盖全部低分段')
    return accepted
