"""Exact, course-bound English ASR orthography reconciliation.

This evidence preserves the original frozen comparison and its failed score. It
only proves that one registered transcript becomes character-for-character
equal to its source after applying the registered, occurrence-bounded written
form substitutions. It performs no provider call and is not a general English
contraction, name, translation, or pronunciation waiver.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unicodedata

from content.textbook_catalog import digest
from content.textbook_preview_audio_contract import (
    audit_contract_identity, resolve_audio_contract, validate_v2_audit_segment,
)
from core.errors import ApiError


SCHEMA = 'mira.textbook.english-asr-orthography-reconciliation.v1'
METHOD = 'exact-registered-full-sentence-orthography'
POLICY = 'mira.textbook.english-asr-orthography.v1'
LIMIT = ('Only the registered segments within one preview, source and plan; every action, audio '
         'and provider transcript is hash-bound; no score mutation, provider retry, general '
         'contraction/name equivalence, human listening, pronunciation or speaking evidence.')
REGISTRY_PATH = Path(__file__).with_name('textbook_english_asr_orthography.v1.json')
REGISTRY = json.loads(REGISTRY_PATH.read_text())

RULE_PROFILES = (
    (
        {'side': 'expected', 'from': 'Lily', 'to': '莉莉',
         'sourceOccurrences': 2, 'matchIndex': 1},
        {'side': 'expected', 'from': "name's", 'to': 'name is',
         'sourceOccurrences': 1, 'matchIndex': 1},
    ),
    (
        {'side': 'expected', 'from': "I'm", 'to': 'I am',
         'sourceOccurrences': 1, 'matchIndex': 1},
    ),
)


def fail(message):
    raise ApiError('textbook_english_asr_reconciliation_invalid', message, 409)


def _sealed(value, description):
    if (not isinstance(value, dict)
            or value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'})):
        fail(description + '摘要不一致')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _speech(classroom):
    if not isinstance(classroom, dict) or not isinstance(classroom.get('scenes'), list):
        fail('当前课堂结构不完整')
    result = []
    for scene in classroom['scenes']:
        if not isinstance(scene, dict) or not _text(scene.get('id')):
            fail('当前课堂页面身份无效')
        for action in scene.get('actions', []):
            if not isinstance(action, dict):
                fail('当前课堂动作结构无效')
            if action.get('type') == 'speech':
                if not all(_text(action.get(k)) for k in ('id', 'text', 'audioId')):
                    fail('当前旁白身份不完整')
                result.append({'sceneId': scene['id'], 'actionId': action['id'],
                    'text': action['text'], 'audioId': action['audioId']})
    if not result or len({(e['sceneId'], e['actionId']) for e in result}) != len(result):
        fail('当前课堂旁白缺失或重复')
    return result


def _normalize(value):
    if not isinstance(value, str) or not value or len(value) > 8000:
        fail('正字法复核文本无效')
    if any(unicodedata.category(c).startswith('C') and c not in '\t\n\r' for c in value):
        fail('正字法复核文本含控制字符')
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold()
                   if unicodedata.category(c)[0] in {'L', 'N'})


def _replace_registered(value, rule):
    if (not isinstance(rule, dict)
            or set(rule) != {'side', 'from', 'to', 'sourceOccurrences', 'matchIndex'}
            or rule['side'] != 'expected'
            or not _text(rule['from']) or not _text(rule['to'])
            or type(rule['sourceOccurrences']) is not int
            or type(rule['matchIndex']) is not int
            or rule['sourceOccurrences'] < 1
            or not 1 <= rule['matchIndex'] <= rule['sourceOccurrences']
            or value.count(rule['from']) != rule['sourceOccurrences']):
        fail('登记的英语正字法替换范围无效')
    pieces = value.split(rule['from'])
    index = rule['matchIndex']
    return rule['from'].join(pieces[:index]) + rule['to'] + rule['from'].join(pieces[index:])


def _registered(*, plan, classroom, expected_source_sha256,
                expected_source_classroom_id=None):
    _sealed(REGISTRY, '英语正字法登记表')
    if (REGISTRY.get('schemaVersion') != 'mira.textbook.english-asr-orthography-registry.v1'
            or not isinstance(REGISTRY.get('entries'), list)):
        fail('英语正字法登记表版本无效')
    contract = resolve_audio_contract(plan)
    if (contract['subject'] != 'english'
            or contract['comparisonPolicy']['version'] != 'english-words-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('只有冻结 english-words-v1 的英语配音可使用本复核')
    if not isinstance(expected_source_sha256, str) or len(expected_source_sha256) != 64:
        fail('当前课堂摘要无效')
    candidates = [item for item in REGISTRY['entries']
                  if isinstance(item, dict)
                  and item.get('previewKey') == plan.get('previewKey')
                  and item.get('planSha256') == digest(plan)
                  and item.get('sourceSha256') == expected_source_sha256]
    if not candidates:
        fail('当前教材、预览或配音计划没有登记的英语正字法复核')
    exact = {'previewKey', 'planSha256', 'sourceClassroomId', 'sourceSha256',
        'sourceSpeechSha256', 'sceneId', 'actionId', 'textSha256', 'ttsRequestId',
        'audioSha256', 'asrRequestId', 'transcriptSha256', 'auditSegmentSha256',
        'asrReceiptSha256', 'literalSimilarityBps', 'rules', 'normalizedSha256'}
    if expected_source_classroom_id is None:
        if digest(classroom) != expected_source_sha256:
            fail('当前完整课堂字节已改变')
    elif not _text(expected_source_classroom_id):
        fail('发布记录缺少已验证的原课堂身份')
    speech = _speech(classroom)
    speech_sha = digest(speech)
    actions = {(item['sceneId'], item['actionId']): item for item in speech}
    seen = set()
    for registered in candidates:
        key = (registered.get('sceneId'), registered.get('actionId'))
        if (set(registered) != exact or key in seen or key not in actions
                or registered.get('sourceSpeechSha256') != speech_sha
                or registered.get('sourceClassroomId')
                    != (expected_source_classroom_id or classroom.get('id'))
                or tuple(registered.get('rules', [])) not in RULE_PROFILES):
            fail('登记的英语正字法条目字段或范围无效')
        seen.add(key)
    order = {key: index for index, key in enumerate(actions)}
    candidates.sort(key=lambda item: order[(item['sceneId'], item['actionId'])])
    return candidates, speech


def _entry(*, plan, classroom, audit_entry, expected_source_sha256,
           expected_source_classroom_id=None):
    registered_items, speech = _registered(plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    if not isinstance(audit_entry, dict):
        fail('登记的英语正字法段落不存在')
    key = (audit_entry.get('sceneId'), audit_entry.get('actionId'))
    registered = next((item for item in registered_items
                       if (item['sceneId'], item['actionId']) == key), None)
    target = next((item for item in speech
                   if (item['sceneId'], item['actionId'])
                   == key), None)
    if registered is None or target is None:
        fail('该英语低分段没有精确登记的正字法复核')
    if ((audit_entry.get('sceneId'), audit_entry.get('actionId'))
            != (registered['sceneId'], registered['actionId'])
            or audit_entry.get('textSha256') != registered['textSha256']
            or audit_entry.get('ttsRequestId') != registered['ttsRequestId']
            or audit_entry.get('audioSha256') != registered['audioSha256']
            or audit_entry.get('asr', {}).get('requestId') != registered['asrRequestId']
            or audit_entry.get('asr', {}).get('transcriptSha256') != registered['transcriptSha256']
            or digest(audit_entry) != registered['auditSegmentSha256']
            or digest(audit_entry.get('asr')) != registered['asrReceiptSha256']):
        fail('原始英语低分段或 provider 回执不属于登记条目')
    passed = validate_v2_audit_segment(plan, {'id': target['actionId'], 'text': target['text'],
        'audioId': target['audioId']}, audit_entry, scene_id=target['sceneId'])
    literal = audit_entry['comparison']
    if (passed is not False or literal.get('passed') is not False
            or literal.get('protectedContentMatched') is not False
            or audit_entry.get('similarityBps') != registered['literalSimilarityBps']
            or audit_entry.get('asr', {}).get('status') != 'succeeded'
            or audit_entry.get('asr', {}).get('completionUsable') is not True):
        fail('只允许保留原始 english-words-v1 失败的成功 provider 回执')
    rules = registered['rules']
    if tuple(rules) not in RULE_PROFILES:
        fail('登记条目不能扩展为其他名字或缩写规则')
    reconciled = target['text'].strip()
    for rule in rules:
        reconciled = _replace_registered(reconciled, rule)
    normalized_expected = _normalize(reconciled)
    normalized_transcript = _normalize(audit_entry['transcript'])
    normalized_sha = hashlib.sha256(normalized_expected.encode()).hexdigest()
    if (normalized_expected != normalized_transcript
            or normalized_sha != registered['normalizedSha256']):
        fail('应用登记替换后完整句没有逐字一致')
    return {
        'sceneId': registered['sceneId'], 'actionId': registered['actionId'],
        'textSha256': registered['textSha256'], 'ttsRequestId': registered['ttsRequestId'],
        'audioSha256': registered['audioSha256'], 'asrRequestId': registered['asrRequestId'],
        'transcriptSha256': registered['transcriptSha256'],
        'auditSegmentSha256': registered['auditSegmentSha256'],
        'asrReceiptSha256': registered['asrReceiptSha256'],
        'literalSimilarityBps': registered['literalSimilarityBps'], 'literalPassed': False,
        'literalComparison': deepcopy(literal), 'appliedRules': deepcopy(rules),
        'reconciledExpectedText': reconciled,
        'normalizedExpected': normalized_expected,
        'normalizedTranscript': normalized_transcript,
        'normalizedSha256': normalized_sha, 'orthographicallyEquivalent': True,
        'acceptanceMethod': METHOD,
    }


def _evidence_value(*, plan, classroom, expected_source_sha256, recorded_at,
                    segments, expected_source_classroom_id=None):
    source_classroom_id = expected_source_classroom_id or classroom['id']
    value = {'schemaVersion': SCHEMA, 'method': METHOD, 'policyVersion': POLICY,
        'previewKey': plan['previewKey'], 'sourceClassroomId': source_classroom_id,
        'sourceSha256': expected_source_sha256, 'sourceSpeechSha256': digest(_speech(classroom)),
        'planSha256': digest(plan),
        'comparisonPolicySha256': plan['comparisonPolicySha256'],
        'recordedAt': recorded_at, 'literalPassed': False,
        'minimumSimilarityBpsUnchanged': 8500, 'providerCalls': 0,
        'evidenceLimit': LIMIT, 'segments': segments}
    value['sha256'] = digest(value)
    return value


def build_evidence(*, plan, classroom, audit_entry=None, audit_entries=None,
                   expected_source_sha256, recorded_at,
                   expected_source_classroom_id=None):
    if type(recorded_at) is not int or recorded_at <= 0:
        fail('英语正字法复核时间无效')
    if audit_entries is not None and audit_entry is not None:
        fail('英语正字法复核段落输入重复')
    supplied = list(audit_entries if audit_entries is not None else [audit_entry])
    if not supplied or any(not isinstance(item, dict) for item in supplied):
        fail('英语正字法复核缺少原始低分段')
    registered, _ = _registered(plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    by_key = {(item.get('sceneId'), item.get('actionId')): item for item in supplied}
    registered_keys = [(item['sceneId'], item['actionId']) for item in registered]
    if len(by_key) != len(supplied) or set(by_key) != set(registered_keys):
        fail('英语正字法复核必须包含所有且仅包含精确登记的低分段')
    segments = [_entry(plan=plan, classroom=classroom, audit_entry=by_key[key],
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
        for key in registered_keys]
    return _evidence_value(plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256, recorded_at=recorded_at,
        segments=segments, expected_source_classroom_id=expected_source_classroom_id)


def _validate_manifest(value, *, plan, classroom, expected_source_sha256,
                       now_ms, expected_source_classroom_id=None):
    required = {'schemaVersion', 'method', 'policyVersion', 'previewKey',
        'sourceClassroomId', 'sourceSha256', 'sourceSpeechSha256', 'planSha256',
        'comparisonPolicySha256', 'recordedAt', 'literalPassed',
        'minimumSimilarityBpsUnchanged', 'providerCalls', 'evidenceLimit',
        'segments', 'sha256'}
    if (not isinstance(value, dict) or set(value) != required
            or type(value.get('recordedAt')) is not int or type(now_ms) is not int
            or not 0 < value['recordedAt'] <= now_ms
            or value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'})):
        fail('英语正字法复核清单或时间无效')
    registered, speech = _registered(plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    expected_header = _evidence_value(plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        recorded_at=value['recordedAt'], segments=value.get('segments'),
        expected_source_classroom_id=expected_source_classroom_id)
    if value != expected_header or not isinstance(value.get('segments'), list):
        fail('英语正字法复核没有绑定当前预览、计划和课堂')
    segment_keys = {'sceneId', 'actionId', 'textSha256', 'ttsRequestId',
        'audioSha256', 'asrRequestId', 'transcriptSha256', 'auditSegmentSha256',
        'asrReceiptSha256', 'literalSimilarityBps', 'literalPassed',
        'literalComparison', 'appliedRules', 'reconciledExpectedText',
        'normalizedExpected', 'normalizedTranscript', 'normalizedSha256',
        'orthographicallyEquivalent', 'acceptanceMethod'}
    actions = {(item['sceneId'], item['actionId']): item for item in speech}
    registered_by_key = {(item['sceneId'], item['actionId']): item for item in registered}
    supplied_by_key = {}
    for segment in value['segments']:
        if not isinstance(segment, dict) or set(segment) != segment_keys:
            fail('英语正字法复核段落字段无效')
        key = (segment.get('sceneId'), segment.get('actionId'))
        item, target = registered_by_key.get(key), actions.get(key)
        if item is None or target is None or key in supplied_by_key:
            fail('英语正字法复核包含未登记或重复段落')
        reconciled = target['text'].strip()
        for rule in item['rules']:
            reconciled = _replace_registered(reconciled, rule)
        normalized = _normalize(reconciled)
        literal = segment.get('literalComparison')
        identity = {
            'sceneId': item['sceneId'], 'actionId': item['actionId'],
            'textSha256': item['textSha256'], 'ttsRequestId': item['ttsRequestId'],
            'audioSha256': item['audioSha256'], 'asrRequestId': item['asrRequestId'],
            'transcriptSha256': item['transcriptSha256'],
            'auditSegmentSha256': item['auditSegmentSha256'],
            'asrReceiptSha256': item['asrReceiptSha256'],
            'literalSimilarityBps': item['literalSimilarityBps'],
        }
        if (any(segment.get(k) != v for k, v in identity.items())
                or segment.get('literalPassed') is not False
                or segment.get('appliedRules') != item['rules']
                or segment.get('reconciledExpectedText') != reconciled
                or segment.get('normalizedExpected') != normalized
                or segment.get('normalizedTranscript') != normalized
                or segment.get('normalizedSha256') != item['normalizedSha256']
                or hashlib.sha256(normalized.encode()).hexdigest() != item['normalizedSha256']
                or segment.get('orthographicallyEquivalent') is not True
                or segment.get('acceptanceMethod') != METHOD
                or not isinstance(literal, dict)
                or literal.get('comparisonPolicy') != 'english-words-v1'
                or literal.get('comparisonPolicySha256') != plan['comparisonPolicySha256']
                or literal.get('expectedComparisonText') != target['text'].strip()
                or literal.get('similarityBps') != item['literalSimilarityBps']
                or literal.get('passed') is not False
                or literal.get('protectedContentMatched') is not False):
            fail('英语正字法复核段落超出精确登记范围')
        supplied_by_key[key] = segment
    if set(supplied_by_key) != set(registered_by_key):
        fail('英语正字法复核缺少精确登记段落')
    return supplied_by_key


def validate_segment_evidence(value, *, plan, classroom, audit_entry,
                              expected_source_sha256, now_ms):
    segments = _validate_manifest(value, plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256, now_ms=now_ms)
    expected = _entry(plan=plan, classroom=classroom, audit_entry=audit_entry,
        expected_source_sha256=expected_source_sha256)
    key = (expected['sceneId'], expected['actionId'])
    if segments.get(key) != expected:
        fail('英语正字法复核与登记的原文、音频或 provider 回执不一致')
    return {key: deepcopy(expected)}


def validate_reconciliation(value, *, plan, classroom, audit,
                            expected_source_sha256, now_ms,
                            expected_source_classroom_id=None):
    if (not isinstance(audit, dict)
            or audit.get('sha256') != digest({k: v for k, v in audit.items() if k != 'sha256'})
            or audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or audit.get('previewKey') != plan.get('previewKey')
            or audit.get('sourceSha256') != expected_source_sha256
            or audit.get('contract') != audit_contract_identity(plan)
            or audit.get('passed') is not False
            or not isinstance(audit.get('segments'), list)):
        fail('必须保留完整且未改分的原始英语 ASR 审计')
    registered, speech = _registered(plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    actions = {(item['sceneId'], item['actionId']): item for item in speech}
    seen, failed = set(), {}
    for entry in audit['segments']:
        key = (entry.get('sceneId'), entry.get('actionId')) if isinstance(entry, dict) else (None, None)
        action = actions.get(key)
        if key in seen or action is None:
            fail('原始英语审计包含重复或额外段落')
        seen.add(key)
        current = {'id': action['actionId'], 'text': action['text'], 'audioId': action['audioId']}
        if not validate_v2_audit_segment(plan, current, entry, scene_id=action['sceneId']):
            failed[key] = entry
    registered_keys = [(item['sceneId'], item['actionId']) for item in registered]
    if seen != set(actions) or set(failed) != set(registered_keys):
        fail('英语正字法复核必须且只能覆盖所有精确登记的原始失败段')
    expected = build_evidence(plan=plan, classroom=classroom,
        audit_entries=[failed[key] for key in registered_keys],
        expected_source_sha256=expected_source_sha256,
        recorded_at=value.get('recordedAt') if isinstance(value, dict) else 0,
        expected_source_classroom_id=expected_source_classroom_id)
    if (not isinstance(value, dict) or type(value.get('recordedAt')) is not int
            or type(now_ms) is not int or not 0 < value['recordedAt'] <= now_ms
            or value != expected):
        fail('英语正字法复核与完整原始审计不一致')
    return {(e['sceneId'], e['actionId']): deepcopy(e) for e in expected['segments']}
