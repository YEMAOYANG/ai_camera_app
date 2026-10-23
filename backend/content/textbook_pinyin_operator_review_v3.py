"""Explicit v3 natural-alias acceptance; v1/v2 validation is not reinterpreted.

All raw/independent ASR results remain unchanged. The sole alias evidence is
content alignment, not a tone or per-token phoneme assertion. Pure validation;
no I/O, provider calls or browser observations are manufactured here.
"""
from copy import deepcopy
from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import (
    PLAN_SCHEMA, policy_for_plan, pronunciation_symbols, validate_formal_receipt,
)
from content.textbook_preview_audio_contract import (
    resolve_audio_contract, audit_contract_identity, validate_v2_audit_segment,
    validate_child_request_plan, audit_segment_plan, tts_request_id,
)
from content.textbook_pinyin_operator_review import (
    fail, _sha, _text, _fields, _sealed, _time, _seal, _authorization, _browser,
)
SCHEMA_V3 = 'mira.textbook.pinyin-operator-review.v3'
METHOD_V3 = 'user-authorized-exact-alias-content-automated-verification'
EVIDENCE_LIMIT_V3 = 'Protocol, literal ASR, independent exact carrier orthography or one registered natural-word alias content alignment, and recorded browser checks; no human listening, per-token alias phoneme, li5 or perceptual pronunciation/tone verification.'


def validate_operator_review_v3(manifest, *, plan, classroom, audit, expected_source_sha256, now_ms,
                             expected_source_classroom_id=None):
    """Validate explicit orthographic evidence without altering literal-ASR failure."""
    if not isinstance(plan, dict) or plan.get('schemaVersion') != PLAN_SCHEMA:
        fail('自动拼音审核只适用于已登记的 v3 拼音合同')
    contract, policy = resolve_audio_contract(plan), policy_for_plan(plan)
    if (type(now_ms) is not int or now_ms <= 0 or not _sha(expected_source_sha256)
            or contract['comparisonPolicy']['version'] != 'literal-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('当前来源、时间或原始 ASR 比较合同无效')
    portable_source_id = expected_source_classroom_id
    if expected_source_classroom_id is None:
        if digest(classroom) != expected_source_sha256:
            fail('当前完整课堂来源摘要不一致')
        expected_source_classroom_id = classroom.get('id') if isinstance(classroom, dict) else None
    if not _text(expected_source_classroom_id):
        fail('缺少调用方核验的原课堂身份')
    _fields(manifest, {'schemaVersion', 'method', 'previewKey', 'sourceSha256', 'sourceClassroomId', 'coreSha256',
                      'planSha256', 'policySha256', 'auditSha256', 'authorization', 'browserQa',
                      'humanListeningVerified', 'perceptualToneVerified', 'evidenceLimit',
                      'reviewer', 'reviewedAt', 'requestPlans', 'asrRecheck', 'segments', 'sha256',
                      'carrierOrthographicEvidence', 'phoneticAccuracyVerified', 'exactAliasEvidence'}, '自动审核')
    _sealed(manifest, '自动审核')
    if (manifest['schemaVersion'] != SCHEMA_V3 or manifest['method'] != METHOD_V3
            or manifest['humanListeningVerified'] is not False or manifest['perceptualToneVerified'] is not False
            or manifest['evidenceLimit'] != EVIDENCE_LIMIT_V3
            or manifest['phoneticAccuracyVerified'] is not False
            or manifest['previewKey'] != plan['previewKey'] or manifest['sourceSha256'] != expected_source_sha256
            or manifest['sourceClassroomId'] != expected_source_classroom_id
            or manifest['coreSha256'] != plan['coreSha256'] or manifest['planSha256'] != digest(plan)
            or manifest['policySha256'] != digest(policy) or manifest['auditSha256'] != digest(audit)
            or not _text(manifest['reviewer']) or not _time(manifest['reviewedAt'], now_ms)
            or not isinstance(manifest['segments'], list) or not isinstance(manifest['requestPlans'], list)):
        fail('自动审核身份、证据范围或诚实能力声明不一致')
    _authorization(manifest['authorization'], plan, manifest['reviewedAt'])
    _sealed(audit, '原始 ASR 审计')
    if (audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2' or type(audit.get('passed')) is not bool
            or audit.get('previewKey') != plan['previewKey'] or audit.get('sourceSha256') != expected_source_sha256
            or audit.get('contract') != audit_contract_identity(plan) or not isinstance(audit.get('segments'), list)
            or any(k in audit for k in ('listeningReview', 'reconciliation', 'pronunciationReview'))):
        fail('自动审核必须保留完整原始 ASR，不能混用人工证据或豁免')
    scenes, actions = {}, {}
    if not isinstance(classroom, dict) or not isinstance(classroom.get('scenes'), list):
        fail('课堂结构无效')
    action_ids = set()
    for scene in classroom['scenes']:
        if not isinstance(scene, dict) or not _text(scene.get('id')) or scene['id'] in scenes:
            fail('课堂页面身份无效或重复')
        scenes[scene['id']] = scene
        if not isinstance(scene.get('actions', []), list):
            fail('课堂动作格式无效')
        for action in scene.get('actions', []):
            if not isinstance(action, dict):
                fail('课堂动作格式无效')
            if action.get('type') != 'speech':
                continue
            if (not all(_text(action.get(k)) for k in ('id', 'text', 'audioId')) or action['id'] in action_ids):
                fail('课堂旁白身份无效或重复')
            actions[(scene['id'], action['id'])] = action
            action_ids.add(action['id'])
    raw, literal_results = {}, []
    for entry in audit['segments']:
        if not isinstance(entry, dict) or not all(_text(entry.get(k)) for k in ('sceneId', 'actionId')):
            fail('ASR 条目身份无效')
        key = (entry['sceneId'], entry['actionId'])
        if (key not in actions or key in raw or type(entry.get('similarityBps')) is not int
                or not _sha(entry.get('audioSha256')) or not isinstance(entry.get('comparison'), dict)
                or type(entry['comparison'].get('passed')) is not bool
                or not isinstance(entry.get('asr'), dict) or entry['asr'].get('completionUsable') is False):
            fail('全部原始 ASR 必须有完整真实回执和比较结果')
        literal_results.append(validate_v2_audit_segment(plan, actions[key], entry, scene_id=key[0]))
        raw[key] = entry
    if not actions or set(raw) != set(actions) or audit['passed'] is not all(literal_results):
        fail('原始 ASR 没有完整覆盖全部正式旁白')
    from content.textbook_pinyin_alias_alignment import validate_evidence as validate_alias
    aligned = validate_alias(manifest['exactAliasEvidence'], plan=plan, classroom=classroom, audit=audit,
        expected_source_sha256=expected_source_sha256, now_ms=manifest['reviewedAt'],
        expected_source_classroom_id=portable_source_id)
    rechecked = {}
    if manifest['asrRecheck'] is not None:
        from content.textbook_audio_recheck import validate_asr_recheck
        original_identity_classroom = {**classroom, 'id': expected_source_classroom_id}
        rechecked = validate_asr_recheck(manifest['asrRecheck'], plan=plan, classroom=original_identity_classroom,
            audit=audit, expected_source_sha256=expected_source_sha256, now_ms=manifest['reviewedAt'],
            expected_source_classroom_id=portable_source_id)
        if manifest['asrRecheck']['intent'].get('exactAliasEvidence') != manifest['exactAliasEvidence']:
            fail('复核范围排除必须引用同一完整别名证据')
        if set(rechecked) & set(aligned):
            fail('别名不能重复混入付费复核证据')
        if not rechecked:
            fail('不需要的空复核应保留为 null')
    from content.textbook_pinyin_carrier_equivalence import validate_evidence
    equivalent = {}
    if manifest['carrierOrthographicEvidence'] is not None:
        equivalent = validate_evidence(manifest['carrierOrthographicEvidence'], plan=plan,
            classroom={**classroom, 'id': expected_source_classroom_id}, audit=audit,
            recheck=manifest['asrRecheck'], authorization=manifest['authorization'],
            expected_source_sha256=expected_source_sha256, now_ms=manifest['reviewedAt'],
            expected_source_classroom_id=portable_source_id)
    failed_rechecks = {k for k, item in rechecked.items() if item['comparison']['passed'] is not True}
    if set(equivalent) != failed_rechecks or set(equivalent) & set(aligned):
        fail('书写等价必须精确覆盖仍未通过的全部复核，不得覆盖已通过项或漏项')
    if any(item['comparison']['passed'] and item['comparison']['similarityBps'] < 8500
           for item in rechecked.values()):
        fail('原比较门槛不能修改')
    if any(not e['comparison']['passed'] and k not in rechecked and k not in aligned for k, e in raw.items()):
        fail('原始低分必须有同一音频单次独立 ASR 通过证据，不能自动豁免')
    plans = {digest(plan): plan}
    for item in manifest['requestPlans']:
        validate_child_request_plan(plan, item)
        sha = digest(item)
        if sha in plans:
            fail('旁白修订请求计划不是当前合同的唯一合法子计划')
        plans[sha] = item
    accepted, used_plans = {}, {digest(plan)}
    for item in manifest['segments']:
        _fields(item, {'sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256', 'pcmSha256',
                       'sensitive', 'requestPlanSha256', 'ttsReceipt', 'ttsReceiptSha256',
                       'asrRequestId', 'asrReceiptSha256', 'auditSegmentSha256', 'asrRecheckEntrySha256',
                       'carrierOrthographicEntrySha256', 'exactAliasEntrySha256'}, '自动审核段落')
        if not all(_text(item[k]) for k in ('sceneId', 'actionId', 'requestPlanSha256')):
            fail('自动审核段落身份无效')
        key = (item['sceneId'], item['actionId'])
        entry, request_plan, receipt = raw.get(key), plans.get(item['requestPlanSha256']), item['ttsReceipt']
        if entry is None or key in accepted or request_plan is None or not isinstance(receipt, dict):
            fail('自动审核包含重复、额外段落或未知请求计划')
        action = actions[key]
        identity = receipt.get('previewAudioIdentity', {})
        attempt = identity.get('attempt') if isinstance(identity, dict) else None
        revision = receipt.get('narrationRevisionId')
        if (type(attempt) is not int or attempt < 1
                or identity != {'planSha256': digest(request_plan), 'attempt': attempt}
                or receipt.get('status') != 'succeeded' or receipt.get('completionUsable') is False
                or receipt.get('requestId') != tts_request_id(request_plan, *key, action['text'], attempt=attempt)
                or receipt['requestId'] != action['audioId']
                or (revision is None and request_plan != plan)
                or (revision is not None and (request_plan == plan or revision != request_plan['revisionId']
                    or receipt.get('classroomContentSha256') != request_plan['classroomSha256']))):
            fail('正式 TTS 必须属于原计划或明确归档的旁白修订请求')
        if request_plan != plan:
            validate_child_request_plan(plan, request_plan, text=action['text'].strip())
        audit_plan = audit_segment_plan(plan, action, entry, scene_id=key[0])
        if audit_plan.get('pronunciationPolicySha256') != request_plan.get('pronunciationPolicySha256'):
            fail('TTS 与原始 ASR 必须绑定同一实际政策')
        effective_policy = policy_for_plan(request_plan)
        validate_formal_receipt(receipt, action['text'].strip(), policy_version=effective_policy['policyVersion'])
        if (not isinstance(action.get('audioMetadata'), dict)
                or any(action['audioMetadata'].get(k) != policy[k] for k in ('providerId', 'modelId', 'voiceId'))
                or action['audioMetadata'].get('fallbackUsed') is not False):
            fail('课堂音频元数据不对应实际声音合同')
        expected = {k: entry[k] for k in ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256')}
        expected.update(pcmSha256=receipt['pcmSha256'], ttsReceiptSha256=digest(receipt),
                        asrRequestId=entry['asr']['requestId'], asrReceiptSha256=digest(entry['asr']),
                        auditSegmentSha256=digest(entry), asrRecheckEntrySha256=digest(rechecked[key]) if key in rechecked else None,
                        carrierOrthographicEntrySha256=digest(equivalent[key]) if key in equivalent else None,
                        exactAliasEntrySha256=digest(aligned[key]) if key in aligned else None,
                        sensitive=bool(pronunciation_symbols(
                            action['text'].strip(), policy_version=effective_policy['policyVersion'])))
        if (any(item[k] != v for k, v in expected.items()) or type(item['sensitive']) is not bool
                or receipt.get('audioSha256') != entry['audioSha256']
                or (key in rechecked and rechecked[key].get('ttsReceipt') != receipt)
                or (key in aligned and aligned[key]['ttsReceipt'] != receipt)):
            fail('原文、实际 TTS/SSML/WAV/PCM 或 ASR 证据不一致')
        used_plans.add(item['requestPlanSha256'])
        accepted[key] = deepcopy(item)
    if set(accepted) != set(actions) or used_plans != set(plans) or not any(x['sensitive'] for x in accepted.values()):
        fail('自动审核必须精确覆盖所有旁白且没有未使用的请求计划')
    _browser(manifest['browserQa'], source_sha=expected_source_sha256, plan=plan,
             scenes=scenes, entries=raw, latest=manifest['reviewedAt'])
    return accepted


def build_operator_review_v3(*, plan, classroom, audit, tts_receipts, authorization, browser_qa,
                          reviewer, reviewed_at, expected_source_sha256, now_ms, request_plans=(), asr_recheck=None, carrier_orthographic_evidence=None, exact_alias_evidence=None):
    """Assemble hashes only; caller supplies actual receipts, authorization and QA."""
    if not isinstance(tts_receipts, list) or any(not isinstance(r, dict) for r in tts_receipts):
        fail('正式 TTS 回执格式无效')
    receipts = {r.get('requestId'): r for r in tts_receipts if _text(r.get('requestId'))}
    if len(receipts) != len(tts_receipts):
        fail('正式 TTS 回执身份缺失或重复')
    policy = policy_for_plan(plan)
    rechecked = {}
    if asr_recheck is not None:
        from content.textbook_audio_recheck import validate_asr_recheck
        rechecked = validate_asr_recheck(asr_recheck, plan=plan, classroom=classroom, audit=audit,
            expected_source_sha256=expected_source_sha256, now_ms=now_ms)
    from content.textbook_pinyin_carrier_equivalence import validate_evidence
    equivalent = {}
    if carrier_orthographic_evidence is not None:
        equivalent = validate_evidence(carrier_orthographic_evidence, plan=plan, classroom=classroom,
            audit=audit, recheck=asr_recheck, authorization=authorization,
            expected_source_sha256=expected_source_sha256, now_ms=reviewed_at)
    from content.textbook_pinyin_alias_alignment import validate_evidence as validate_alias
    aligned = validate_alias(exact_alias_evidence, plan=plan, classroom=classroom, audit=audit,
        expected_source_sha256=expected_source_sha256, now_ms=reviewed_at)
    segments = []
    plans = {digest(p): p for p in [plan, *request_plans]}
    for entry in audit.get('segments', []):
        receipt = receipts.get(entry.get('ttsRequestId'), {})
        effective_policy = policy_for_plan(plans.get(receipt.get('previewAudioIdentity', {}).get('planSha256'), plan))
        segments.append({**{k: entry.get(k) for k in ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256')},
            'pcmSha256': receipt.get('pcmSha256'), 'sensitive': bool(pronunciation_symbols(
                entry.get('text', ''), policy_version=effective_policy['policyVersion'])),
            'requestPlanSha256': receipt.get('previewAudioIdentity', {}).get('planSha256'),
            'ttsReceipt': deepcopy(receipt), 'ttsReceiptSha256': digest(receipt),
            'asrRequestId': entry.get('asr', {}).get('requestId'), 'asrReceiptSha256': digest(entry.get('asr')),
            'auditSegmentSha256': digest(entry),
            'asrRecheckEntrySha256': digest(rechecked[(entry['sceneId'], entry['actionId'])])
                if (entry['sceneId'], entry['actionId']) in rechecked else None,
            'carrierOrthographicEntrySha256': digest(equivalent[(entry['sceneId'], entry['actionId'])])
                if (entry['sceneId'], entry['actionId']) in equivalent else None,
            'exactAliasEntrySha256': digest(aligned[(entry['sceneId'], entry['actionId'])])
                if (entry['sceneId'], entry['actionId']) in aligned else None})
    result = _seal({'schemaVersion': SCHEMA_V3, 'method': METHOD_V3, 'previewKey': plan['previewKey'],
        'sourceSha256': expected_source_sha256, 'sourceClassroomId': classroom.get('id'),
        'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'policySha256': digest(policy), 'auditSha256': digest(audit), 'authorization': deepcopy(authorization),
        'browserQa': deepcopy(browser_qa), 'humanListeningVerified': False, 'perceptualToneVerified': False,
        'evidenceLimit': EVIDENCE_LIMIT_V3, 'phoneticAccuracyVerified': False,
        'exactAliasEvidence': deepcopy(exact_alias_evidence),
        'carrierOrthographicEvidence': deepcopy(carrier_orthographic_evidence), 'reviewer': reviewer, 'reviewedAt': reviewed_at,
        'requestPlans': deepcopy(list(request_plans)), 'asrRecheck': deepcopy(asr_recheck), 'segments': segments})
    validate_operator_review_v3(result, plan=plan, classroom=classroom, audit=audit,
                             expected_source_sha256=expected_source_sha256, now_ms=now_ms)
    return result

