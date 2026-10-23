"""One independent recognition per original WAV, preserving the complete raw audit.

This is automatic evidence, never perceptual listening. The fixed request ID is
independent of reason, output path, time and transcript, so these cannot create
another paid attempt. Embedded WAV bytes make provider-body validation portable.
"""
import base64
from copy import deepcopy
import hashlib
import json

from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import (
    PLAN_SCHEMA, policy_for_plan, validate_formal_receipt, validate_receipt_wav,
)
from content.textbook_preview_audio_contract import (
    audit_contract_identity, compare_transcript, resolve_audio_contract,
    tts_request_id, validate_v2_audit_segment, validate_child_request_plan, audit_segment_plan,
)
from core.errors import ApiError

SCHEMA = 'mira.textbook.audio-asr-recheck.v1'
INTENT_SCHEMA = 'mira.textbook.audio-asr-recheck-intent.v1'
SCHEMA_ALIAS = 'mira.textbook.audio-asr-recheck.v2-exact-alias'
INTENT_SCHEMA_ALIAS = 'mira.textbook.audio-asr-recheck-intent.v2-exact-alias'
PURPOSE = 'mira.textbook.asr-recheck.once.v1'
EVIDENCE_LIMIT = 'Independent same-audio ASR; not human listening or perceptual tone verification.'


def fail(message):
    raise ApiError('textbook_audio_recheck_invalid', message, 409)


def seal(value):
    value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
    return value


def _sealed(value):
    if not isinstance(value, dict) or value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'}):
        fail('独立复核证据摘要不一致')


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        fail('独立复核字段不完整或包含未知字段')


def request_id(original_asr_request_id, audio_sha256):
    return 'tbpasr1_' + digest({'purpose': PURPOSE, 'originalAsrRequestId': original_asr_request_id,
                              'audioSha256': audio_sha256})


def provider_body(audio):
    """Exact native JSON.stringify order; deliberately no expected text or hints."""
    body = {'model': 'qwen3-asr-flash', 'input': {'messages': [{'role': 'user',
        'content': [{'audio': 'data:audio/wav;base64,' + base64.b64encode(audio).decode('ascii')}]}]},
        'parameters': {'asr_options': {'language': 'zh'}}}
    return json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def raw_entries(*, plan, classroom, audit, expected_source_sha256):
    if not isinstance(plan, dict) or plan.get('schemaVersion') != PLAN_SCHEMA:
        fail('独立复核仅支持已冻结的正式拼音合同')
    contract = resolve_audio_contract(plan)
    if contract['comparisonPolicy']['version'] != 'literal-v1' or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500:
        fail('原始比较合同不可变更')
    _sealed(audit)
    if (audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or audit.get('previewKey') != plan['previewKey'] or audit.get('sourceSha256') != expected_source_sha256
            or audit.get('contract') != audit_contract_identity(plan) or type(audit.get('passed')) is not bool
            or not isinstance(audit.get('segments'), list)
            or any(k in audit for k in ('listeningReview', 'reconciliation', 'pronunciationReview'))):
        fail('必须保留完整原始 ASR 审核及真实通过状态')
    actions, scenes, raw = {}, {}, {}
    for scene in classroom.get('scenes', []):
        if scene['id'] in scenes: fail('重复页面')
        scenes[scene['id']] = scene
        for action in scene.get('actions', []):
            if action.get('type') != 'speech': continue
            key = (scene['id'], action['id'])
            if key in actions: fail('重复旁白')
            actions[key] = action
    for entry in audit['segments']:
        key = (entry.get('sceneId'), entry.get('actionId'))
        if key not in actions or key in raw: fail('原始审核包含重复或额外段落')
        validate_v2_audit_segment(plan, actions[key], entry, scene_id=key[0])
        if entry['asr'].get('completionUsable') is False: fail('原始识别不可用')
        raw[key] = entry
    if not actions or set(raw) != set(actions) or audit['passed'] is not all(e['comparison']['passed'] for e in raw.values()):
        fail('原始审核没有精确覆盖全部旁白')
    return scenes, actions, raw


def logical_request(plan, classroom, scene, action, receipt, original):
    teacher = plan['teacher']; profile = teacher['teacherProfile']
    return {'requestId': request_id(original['asr']['requestId'], original['audioSha256']),
        'classroomId': classroom['id'], 'classroomContentSha256': receipt.get('classroomContentSha256', plan['classroomSha256']),
        'subject': 'chinese', 'teacherProfileId': profile['id'], 'teacherProfileVersion': profile['version'],
        'teacherProfileSha256': profile['contentHash'], 'teacherGender': teacher['teacherGender'],
        'sceneId': scene['id'], 'sceneOrder': scene.get('order', 0), 'actionId': action['id'],
        'narrationSegmentId': action['id'], 'ttsRequestId': action['audioId'], 'audioSha256': original['audioSha256']}


def validate_tts_request_plan(plan, scene, action, receipt, request_plan=None):
    """Verify the original request, including an explicitly archived amendment.

    The portable child plan changes only the request's content/revision binding;
    it cannot change the parent teacher, pronunciation or comparison contract.
    """
    revision = receipt.get('narrationRevisionId')
    segment_plan = plan
    if revision is not None:
        if not isinstance(request_plan, dict): fail('修订音频缺少原始请求计划')
        validate_child_request_plan(plan, request_plan, text=action['text'].strip())
        if (request_plan['revisionId'] != revision
                or receipt.get('classroomContentSha256') != request_plan['classroomSha256']):
            fail('修订请求计划不能改变原合同或课堂请求摘要')
        segment_plan = request_plan
    elif request_plan is not None:
        fail('原始音频不能附加其他请求计划')
    elif receipt.get('classroomContentSha256', plan['classroomSha256']) != plan['classroomSha256']:
        fail('原始课堂请求摘要不一致')
    identity = receipt.get('previewAudioIdentity', {})
    attempt = identity.get('attempt') if isinstance(identity, dict) else None
    if (type(attempt) is not int or attempt < 1
            or identity != {'planSha256': digest(segment_plan), 'attempt': attempt}
            or receipt.get('requestId') != action['audioId']
            or action['audioId'] != tts_request_id(segment_plan, scene['id'], action['id'], action['text'], attempt=attempt)):
        fail('原始配音计划或请求身份不匹配')
    return segment_plan


def build_intent(*, plan, classroom, audit, expected_source_sha256, selections, created_at,
                 exact_alias_evidence=None, expected_source_classroom_id=None):
    _, _, raw = raw_entries(plan=plan, classroom=classroom, audit=audit, expected_source_sha256=expected_source_sha256)
    aligned = {}
    if exact_alias_evidence is not None:
        from content.textbook_pinyin_alias_alignment import validate_evidence
        aligned = validate_evidence(exact_alias_evidence, plan=plan, classroom=classroom, audit=audit,
            expected_source_sha256=expected_source_sha256, now_ms=created_at,
            expected_source_classroom_id=expected_source_classroom_id)
    selected, seen = [], set()
    for choice in selections:
        _fields(choice, {'sceneId', 'actionId', 'reason'})
        key = (choice['sceneId'], choice['actionId']); original = raw.get(key)
        if (key in seen or key in aligned or original is None or original['similarityBps'] >= 10000
                or not isinstance(choice['reason'], str) or not choice['reason'].strip()):
            fail('仅可一次复核预先说明理由的真实差异段落')
        seen.add(key)
        selected.append({**choice, 'originalSegmentSha256': digest(original),
            'originalAsrRequestId': original['asr']['requestId'],
            'requestId': request_id(original['asr']['requestId'], original['audioSha256'])})
    if (not selected and not aligned) or not {k for k, e in raw.items() if not e['comparison']['passed']} <= seen | set(aligned):
        fail('独立复核必须包含全部原始低分段落')
    return seal({**({'exactAliasEvidence': deepcopy(exact_alias_evidence)} if aligned else {}),
        'schemaVersion': INTENT_SCHEMA_ALIAS if aligned else INTENT_SCHEMA, 'purpose': PURPOSE, 'previewKey': plan['previewKey'],
        'sourceSha256': expected_source_sha256, 'planSha256': digest(plan), 'rawAuditSha256': digest(audit),
        'createdAt': created_at, 'selection': selected, 'maximumAttemptsPerOriginal': 1,
        'hintsSentToProvider': False, 'evidenceLimit': EVIDENCE_LIMIT})


def validate_asr_recheck(manifest, *, plan, classroom, audit, expected_source_sha256, now_ms,
                         expected_source_classroom_id=None):
    scenes, actions, raw = raw_entries(plan=plan, classroom=classroom, audit=audit, expected_source_sha256=expected_source_sha256)
    _fields(manifest, {'schemaVersion', 'intent', 'segments', 'createdAt', 'sha256'})
    _sealed(manifest)
    intent = manifest['intent']; _sealed(intent)
    if not isinstance(intent.get('selection'), list): fail('缺少调用前固定范围')
    expected = build_intent(plan=plan, classroom=classroom, audit=audit, expected_source_sha256=expected_source_sha256,
        selections=[{k: x.get(k) for k in ('sceneId', 'actionId', 'reason')} for x in intent['selection']],
        created_at=intent.get('createdAt'),
        exact_alias_evidence=intent.get('exactAliasEvidence') if intent.get('schemaVersion') == INTENT_SCHEMA_ALIAS else None,
        expected_source_classroom_id=expected_source_classroom_id)
    schema = SCHEMA_ALIAS if expected['schemaVersion'] == INTENT_SCHEMA_ALIAS else SCHEMA
    if (intent != expected or manifest['schemaVersion'] != schema or not isinstance(manifest['segments'], list)
            or type(now_ms) is not int or type(intent['createdAt']) is not int or type(manifest['createdAt']) is not int
            or not 0 < intent['createdAt'] <= manifest['createdAt'] <= now_ms):
        fail('复核意图、范围、策略或时间不一致')
    selected = {(s['sceneId'], s['actionId']): s for s in intent['selection']}
    accepted = {}
    for entry in manifest['segments']:
        fields = {'sceneId', 'actionId', 'originalSegmentSha256', 'request', 'requestSha256',
            'ttsReceipt', 'ttsReceiptSha256', 'audioBase64', 'asr', 'asrSha256', 'comparison', 'observedAt'}
        if isinstance(entry, dict) and isinstance(entry.get('ttsReceipt'), dict) and entry['ttsReceipt'].get('narrationRevisionId') is not None:
            fields.add('requestPlan')
        _fields(entry, fields)
        key = (entry['sceneId'], entry['actionId'])
        if key not in selected or key in accepted: fail('复核结果遗漏、重复或越过固定范围')
        original, action, receipt = raw[key], actions[key], entry['ttsReceipt']
        if (not isinstance(receipt, dict) or receipt.get('status') != 'succeeded'
                or receipt.get('completionUsable') is False or receipt.get('requestId') != action['audioId']
                or receipt.get('audioSha256') != original['audioSha256']
                or entry['ttsReceiptSha256'] != digest(receipt)):
            fail('复核必须使用原始计划中同一正式 TTS 音频')
        effective = validate_tts_request_plan(plan, scenes[key[0]], action, receipt, entry.get('requestPlan'))
        if audit_segment_plan(plan, action, original, scene_id=key[0]).get('pronunciationPolicySha256') != effective.get('pronunciationPolicySha256'):
            fail('原始识别和复核必须继承同一实际 TTS 政策')
        policy = policy_for_plan(effective)
        validate_formal_receipt(receipt, action['text'].strip(), policy_version=policy['policyVersion'])
        try:
            if not isinstance(entry['audioBase64'], str) or len(entry['audioBase64']) > 16_000_000: raise ValueError()
            audio = base64.b64decode(entry['audioBase64'], validate=True)
            if base64.b64encode(audio).decode('ascii') != entry['audioBase64']: raise ValueError()
        except (ValueError, TypeError): fail('复核音频编码无效')
        validate_receipt_wav(receipt, audio)
        body_sha = hashlib.sha256(provider_body(audio)).hexdigest()
        response = entry['asr']; validate_formal_receipt(response, action['text'].strip(), policy_version=policy['policyVersion'])
        request = logical_request(plan, classroom, scenes[key[0]], action, receipt, original)
        transcript = response.get('transcript')
        if (entry['request'] != request or entry['requestSha256'] != digest(request)
                or entry['originalSegmentSha256'] != digest(original) or entry['asrSha256'] != digest(response)
                or response.get('requestId') != selected[key]['requestId'] or response.get('status') != 'succeeded'
                or response.get('completionUsable') is not True or not isinstance(transcript, str) or not transcript.strip()
                or len(transcript) > 8000 or response.get('transcriptSha256') != hashlib.sha256(transcript.encode()).hexdigest()
                or response.get('providerAsrBodySha256') != body_sha
                or original['asr'].get('providerAsrBodySha256') != body_sha
                or response['providerPronunciation'] != receipt['providerPronunciation']
                or entry['comparison'] != compare_transcript(plan, action['text'], transcript)
                or type(entry['observedAt']) is not int or not intent['createdAt'] <= entry['observedAt'] <= manifest['createdAt']):
            fail('独立识别不是同一无提示音频、固定单次请求及真实回执')
        accepted[key] = deepcopy(entry)
    if set(accepted) != set(selected): fail('全部已选复核必须保留，包括仍未通过的结果')
    return accepted
