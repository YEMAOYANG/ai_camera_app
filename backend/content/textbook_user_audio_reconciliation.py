"""Exact human confirmation of presented Chinese v2 audio discrepancies.

The operator must obtain the statement from the real conversation. This record
does not imply whole-course listening or alter any original ASR result. Live
publication still verifies provider receipts and bytes; portable validation
still binds archived media to the original audio SHA.
"""
from copy import deepcopy

from content.textbook_catalog import digest
from content.textbook_preview_audio_contract import (
    SCHEMA as PLAN_SCHEMA, audit_contract_identity, resolve_audio_contract,
    validate_v2_audit_segment,
)
from core.errors import ApiError

SCHEMA = 'mira.textbook.presented-audio-user-confirmation.v1'
METHOD = 'user-confirmed-presented-audio'
SCOPE = 'presented-segments-content-and-pronunciation'
LIMIT = 'Only these presented audio files were confirmed by the user; not whole-course listening or literal ASR success.'


def fail(message):
    raise ApiError('textbook_user_audio_reconciliation_invalid', message, 409)


def _failed_segments(*, plan, classroom, audit, expected_source_sha256):
    contract = resolve_audio_contract(plan)
    if (plan.get('schemaVersion') != PLAN_SCHEMA or contract['subject'] != 'chinese'
            or contract['comparisonPolicy']['version'] != 'literal-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('逐段用户听审仅适用于普通中文 v2 配音合同')
    if (not isinstance(audit, dict)
            or audit.get('sha256') != digest({k: v for k, v in audit.items() if k != 'sha256'})
            or audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or audit.get('previewKey') != plan['previewKey']
            or audit.get('sourceSha256') != expected_source_sha256
            or audit.get('contract') != audit_contract_identity(plan)
            or audit.get('passed') is not False
            or not isinstance(audit.get('segments'), list)):
        fail('必须保留当前完整且未改分的原始识别审核')
    actions = [(s['id'], a) for s in classroom['scenes']
               for a in s.get('actions', []) if a.get('type') == 'speech']
    by_key = {(s, a['id']): a for s, a in actions}
    if not by_key or len(by_key) != len(actions):
        fail('课堂旁白缺失或身份重复')
    seen, failed = set(), []
    for entry in audit['segments']:
        if not isinstance(entry, dict):
            fail('原始审核段落无效')
        key = entry.get('sceneId'), entry.get('actionId')
        if key not in by_key or key in seen:
            fail('原始审核段落重复或不属于当前课堂')
        seen.add(key)
        if not validate_v2_audit_segment(plan, by_key[key], entry, scene_id=key[0]):
            failed.append({k: entry[k] for k in (
                'sceneId', 'actionId', 'text', 'textSha256', 'ttsRequestId', 'audioSha256',
                'transcript', 'similarityBps')})
            failed[-1].update(asrReceiptSha256=digest(entry['asr']),
                auditSegmentSha256=digest(entry), literalPassed=False,
                acceptanceMethod=METHOD)
    if seen != set(by_key) or not failed:
        fail('逐段听审要求完整原始审核及明确的未通过段落')
    return failed


def build_confirmation(*, plan, classroom, audit, expected_source_sha256,
                       statement, conversation_id, recorded_at, presented_segments,
                       expected_source_classroom_id=None):
    """Caller supplies only identities of audio actually presented and confirmed."""
    failed = _failed_segments(plan=plan, classroom=classroom, audit=audit,
                              expected_source_sha256=expected_source_sha256)
    identities = [{k: e[k] for k in ('sceneId', 'actionId', 'textSha256', 'audioSha256')}
                  for e in failed]
    if presented_segments != identities:
        fail('用户确认范围必须精确覆盖且仅覆盖当前所有未通过音频')
    if (not isinstance(statement, str) or not statement.strip()
            or not isinstance(conversation_id, str) or not conversation_id.strip()
            or type(recorded_at) is not int or recorded_at <= 0):
        fail('必须记录真实用户原话、会话和确认记录时间')
    value = {'schemaVersion': SCHEMA, 'method': METHOD, 'scope': SCOPE,
        'previewKey': plan['previewKey'], 'sourceSha256': expected_source_sha256,
        'sourceClassroomId': expected_source_classroom_id or classroom['id'],
        'planSha256': digest(plan), 'auditSha256': digest(audit),
        'comparisonPolicySha256': plan['comparisonPolicySha256'],
        'recordedAt': recorded_at, 'userStatement': statement,
        'conversationId': conversation_id, 'presentedSegments': deepcopy(identities),
        'literalPassed': False, 'providerCalls': 0, 'evidenceLimit': LIMIT,
        'segments': failed}
    value['sha256'] = digest(value)
    return value


def validate_reconciliation(value, *, plan, classroom, audit,
                            expected_source_sha256, now_ms,
                            expected_source_classroom_id=None):
    if (not isinstance(value, dict) or type(value.get('recordedAt')) is not int
            or type(now_ms) is not int or not 0 < value['recordedAt'] <= now_ms):
        fail('用户听审记录或时间无效')
    expected = build_confirmation(plan=plan, classroom=classroom, audit=audit,
        expected_source_sha256=expected_source_sha256,
        statement=value.get('userStatement'), conversation_id=value.get('conversationId'),
        recorded_at=value['recordedAt'], presented_segments=value.get('presentedSegments'),
        expected_source_classroom_id=expected_source_classroom_id)
    if value != expected:
        fail('用户听审记录与原始音频、识别结果或当前课堂不一致')
    return {(e['sceneId'], e['actionId']): deepcopy(e) for e in expected['segments']}
