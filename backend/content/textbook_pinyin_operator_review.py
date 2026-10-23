"""Explicit operator/automatic acceptance, never a claim of perceptual listening.

Pure, portable validation. Live publication additionally compares embedded TTS
receipts/request plans to the authoritative local records and checks real WAV
bytes. Published reads bind those same original bytes through release media.
Object SHA bindings include the referenced object's own seal, if any.

Browser observations and the user's authorization must be supplied by the
operator from real evidence. This module cannot observe a browser or hear audio;
the builder does not manufacture either. Browser playback is sampled and its
exact scope is retained, while literal ASR and receipt checks cover every speech.
"""
from copy import deepcopy

from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import (
    PLAN_SCHEMA, SHA, policy_for_plan, pronunciation_symbols, validate_formal_receipt,
)
from content.textbook_preview_audio_contract import (
    audit_contract_identity, resolve_audio_contract, tts_request_id, validate_v2_audit_segment,
    validate_child_request_plan, audit_segment_plan,
)
from core.errors import ApiError

SCHEMA = 'mira.textbook.pinyin-operator-review.v1'
METHOD = 'user-authorized-automated-verification'
AUTHORIZATION_SCHEMA = 'mira.textbook.operator-verification-authorization.v1'
BROWSER_SCHEMA = 'mira.textbook.browser-quality-evidence.v1'
EVIDENCE_LIMIT = 'Protocol, complete-sentence ASR and recorded browser checks; no perceptual pronunciation or tone verification.'


def fail(message):
    raise ApiError('textbook_pinyin_operator_review_invalid', message, 409)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _fields(value, fields, description):
    if not isinstance(value, dict) or set(value) != set(fields):
        fail(description + '字段不完整或含未知字段')


def _sealed(value, description):
    if not isinstance(value, dict) or value.get('sha256') != digest({k: v for k, v in value.items() if k != 'sha256'}):
        fail(description + '摘要不一致')


def _time(value, latest):
    return type(value) is int and 0 < value <= latest


def _seal(value):
    value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
    return value


def _authorization(value, plan, latest):
    _fields(value, {'schemaVersion', 'source', 'statement', 'recordedAt', 'scope',
                   'automatedChecksAuthorized', 'publicationAuthorized',
                   'individualListeningConfirmationRequired', 'sha256'}, '用户授权')
    _sealed(value, '用户授权')
    if (value['schemaVersion'] != AUTHORIZATION_SCHEMA or value['source'] != 'user-message'
            or not _text(value['statement']) or not _time(value['recordedAt'], latest)
            or value['scope'] != {k: plan['binding'][k] for k in ('editionId', 'gradeCode', 'subject')}
            or value['automatedChecksAuthorized'] is not True or value['publicationAuthorized'] is not True
            or value['individualListeningConfirmationRequired'] is not False):
        fail('没有适用于当前教材的明确自动检查及发布授权')


def validate_operator_authorization(value, *, binding, recorded_at):
    """Reuse the same exact authorization contract before a plan is installed."""
    _authorization(value, {'binding': binding}, recorded_at)


def _browser(value, *, source_sha, plan, scenes, entries, latest):
    _fields(value, {'schemaVersion', 'sourceSha256', 'coreSha256', 'planSha256', 'method',
                   'reviewer', 'reviewedAt', 'coverage', 'checks', 'sha256'}, '浏览器验收')
    _sealed(value, '浏览器验收')
    if (value['schemaVersion'] != BROWSER_SCHEMA or value['sourceSha256'] != source_sha
            or value['coreSha256'] != plan['coreSha256'] or value['planSha256'] != digest(plan)
            or value['method'] != 'real-browser' or value['coverage'] != 'all-scenes-layout-and-recorded-action-samples'
            or not _text(value['reviewer']) or not _time(value['reviewedAt'], latest)
            or not isinstance(value['checks'], list)):
        fail('浏览器证据没有绑定当前课件及实际验收范围')
    layouts, interactions, playback, seen = set(), set(), set(), set()
    common = {'kind', 'sceneId', 'passed', 'observation', 'evidenceSha256'}
    for check in value['checks']:
        if not isinstance(check, dict):
            fail('浏览器检查格式无效')
        kind = check.get('kind')
        if kind not in ('picture-supported-layout', 'interaction', 'audio-playback'):
            fail('未知浏览器验收种类')
        extra = ({'actionId', 'ttsRequestId', 'audioSha256', 'events', 'syntheticAudio'}
                 if kind == 'audio-playback' else set())
        _fields(check, common | extra, '浏览器检查')
        sid = check['sceneId']
        if not _text(sid) or (kind == 'audio-playback' and not _text(check['actionId'])):
            fail('浏览器检查页面或旁白身份无效')
        identity = (kind, sid, check.get('actionId'))
        if (sid not in scenes or identity in seen or check['passed'] is not True
                or not _text(check['observation']) or not _sha(check['evidenceSha256'])):
            fail('浏览器检查缺少真实结果、来源摘要或包含重复页面')
        seen.add(identity)
        if kind == 'picture-supported-layout':
            layouts.add(sid)
        elif kind == 'interaction':
            if scenes[sid].get('type') != 'interactive':
                fail('交互验收必须对应实际互动页')
            interactions.add(sid)
        elif kind == 'audio-playback':
            if not _text(check['actionId']):
                fail('播放验收缺少旁白身份')
            entry = entries.get((sid, check['actionId']), {})
            if (check['syntheticAudio'] is not False
                    or check['events'] not in (['playing', 'ended'], ['playing', 'ready-after-playing'])
                    or not entry or any(check[k] != entry[k] for k in ('ttsRequestId', 'audioSha256'))):
                fail('播放验收必须使用当前正式音频，不能使用模拟音频或只触发点击')
            playback.add((sid, check['actionId']))
        else:
            fail('未知浏览器验收种类')
    if (layouts != set(scenes) or not playback
            or (any(s.get('type') == 'interactive' for s in scenes.values()) and not interactions)):
        fail('需要全部页面图片布局检查，以及明确记录的真实播放和互动样本')


def validate_operator_review(manifest, *, plan, classroom, audit, expected_source_sha256, now_ms,
                             expected_source_classroom_id=None):
    """Return detached complete speech evidence; never waive literal-ASR failure."""
    if not isinstance(plan, dict) or plan.get('schemaVersion') != PLAN_SCHEMA:
        fail('自动拼音审核只适用于已登记的 v3 拼音合同')
    contract, policy = resolve_audio_contract(plan), policy_for_plan(plan)
    if (type(now_ms) is not int or now_ms <= 0 or not _sha(expected_source_sha256)
            or contract['comparisonPolicy']['version'] != 'literal-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('当前来源、时间或原始 ASR 比较合同无效')
    if expected_source_classroom_id is None:
        expected_source_classroom_id = classroom.get('id') if isinstance(classroom, dict) else None
    if not _text(expected_source_classroom_id):
        fail('缺少调用方核验的原课堂身份')
    _fields(manifest, {'schemaVersion', 'method', 'previewKey', 'sourceSha256', 'sourceClassroomId', 'coreSha256',
                      'planSha256', 'policySha256', 'auditSha256', 'authorization', 'browserQa',
                      'humanListeningVerified', 'perceptualToneVerified', 'evidenceLimit',
                      'reviewer', 'reviewedAt', 'requestPlans', 'asrRecheck', 'segments', 'sha256'}, '自动审核')
    _sealed(manifest, '自动审核')
    if (manifest['schemaVersion'] != SCHEMA or manifest['method'] != METHOD
            or manifest['humanListeningVerified'] is not False or manifest['perceptualToneVerified'] is not False
            or manifest['evidenceLimit'] != EVIDENCE_LIMIT
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
    rechecked = {}
    if manifest['asrRecheck'] is not None:
        from content.textbook_audio_recheck import validate_asr_recheck
        original_identity_classroom = {**classroom, 'id': expected_source_classroom_id}
        rechecked = validate_asr_recheck(manifest['asrRecheck'], plan=plan, classroom=original_identity_classroom,
            audit=audit, expected_source_sha256=expected_source_sha256, now_ms=manifest['reviewedAt'])
        if not rechecked or any(x.get('comparison', {}).get('passed') is not True
                               or x.get('comparison', {}).get('similarityBps', 0) < 8500 for x in rechecked.values()):
            fail('单次独立 ASR 复核仍未通过，不能自动接受或重复刷分')
    if any(not e['comparison']['passed'] and k not in rechecked for k, e in raw.items()):
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
                       'asrRequestId', 'asrReceiptSha256', 'auditSegmentSha256', 'asrRecheckEntrySha256'}, '自动审核段落')
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
                        sensitive=bool(pronunciation_symbols(
                            action['text'].strip(), policy_version=effective_policy['policyVersion'])))
        if (any(item[k] != v for k, v in expected.items()) or type(item['sensitive']) is not bool
                or receipt.get('audioSha256') != entry['audioSha256']
                or (key in rechecked and rechecked[key].get('ttsReceipt') != receipt)):
            fail('原文、实际 TTS/SSML/WAV/PCM 或 ASR 证据不一致')
        used_plans.add(item['requestPlanSha256'])
        accepted[key] = deepcopy(item)
    if set(accepted) != set(actions) or used_plans != set(plans) or not any(x['sensitive'] for x in accepted.values()):
        fail('自动审核必须精确覆盖所有旁白且没有未使用的请求计划')
    _browser(manifest['browserQa'], source_sha=expected_source_sha256, plan=plan,
             scenes=scenes, entries=raw, latest=manifest['reviewedAt'])
    return accepted


def build_operator_review(*, plan, classroom, audit, tts_receipts, authorization, browser_qa,
                          reviewer, reviewed_at, expected_source_sha256, now_ms, request_plans=(), asr_recheck=None):
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
                if (entry['sceneId'], entry['actionId']) in rechecked else None})
    result = _seal({'schemaVersion': SCHEMA, 'method': METHOD, 'previewKey': plan['previewKey'],
        'sourceSha256': expected_source_sha256, 'sourceClassroomId': classroom.get('id'),
        'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'policySha256': digest(policy), 'auditSha256': digest(audit), 'authorization': deepcopy(authorization),
        'browserQa': deepcopy(browser_qa), 'humanListeningVerified': False, 'perceptualToneVerified': False,
        'evidenceLimit': EVIDENCE_LIMIT, 'reviewer': reviewer, 'reviewedAt': reviewed_at,
        'requestPlans': deepcopy(list(request_plans)), 'asrRecheck': deepcopy(asr_recheck), 'segments': segments})
    validate_operator_review(result, plan=plan, classroom=classroom, audit=audit,
                             expected_source_sha256=expected_source_sha256, now_ms=now_ms)
    return result


# v1 definitions above remain byte-identical. The explicit v2 dispatcher neither
# edits their input nor constructs a passing surrogate audit for them.
SCHEMA_V2 = 'mira.textbook.pinyin-operator-review.v2'
METHOD_V2 = 'user-authorized-exact-carrier-automated-verification'
EVIDENCE_LIMIT_V2 = 'Protocol, literal ASR or exact written carrier equivalence and recorded browser checks; no human listening, phonetic accuracy or perceptual tone verification.'
_V1_VALIDATOR = validate_operator_review
def _validate_operator_review_v2(manifest, *, plan, classroom, audit, expected_source_sha256, now_ms,
                             expected_source_classroom_id=None):
    """Validate explicit orthographic evidence without altering literal-ASR failure."""
    if not isinstance(plan, dict) or plan.get('schemaVersion') != PLAN_SCHEMA:
        fail('自动拼音审核只适用于已登记的 v3 拼音合同')
    contract, policy = resolve_audio_contract(plan), policy_for_plan(plan)
    if (type(now_ms) is not int or now_ms <= 0 or not _sha(expected_source_sha256)
            or contract['comparisonPolicy']['version'] != 'literal-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('当前来源、时间或原始 ASR 比较合同无效')
    if expected_source_classroom_id is None:
        expected_source_classroom_id = classroom.get('id') if isinstance(classroom, dict) else None
    if not _text(expected_source_classroom_id):
        fail('缺少调用方核验的原课堂身份')
    _fields(manifest, {'schemaVersion', 'method', 'previewKey', 'sourceSha256', 'sourceClassroomId', 'coreSha256',
                      'planSha256', 'policySha256', 'auditSha256', 'authorization', 'browserQa',
                      'humanListeningVerified', 'perceptualToneVerified', 'evidenceLimit',
                      'reviewer', 'reviewedAt', 'requestPlans', 'asrRecheck', 'segments', 'sha256',
                      'carrierOrthographicEvidence', 'phoneticAccuracyVerified'}, '自动审核')
    _sealed(manifest, '自动审核')
    if (manifest['schemaVersion'] != SCHEMA_V2 or manifest['method'] != METHOD_V2
            or manifest['humanListeningVerified'] is not False or manifest['perceptualToneVerified'] is not False
            or manifest['evidenceLimit'] != EVIDENCE_LIMIT_V2
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
    rechecked = {}
    if manifest['asrRecheck'] is not None:
        from content.textbook_audio_recheck import validate_asr_recheck
        original_identity_classroom = {**classroom, 'id': expected_source_classroom_id}
        rechecked = validate_asr_recheck(manifest['asrRecheck'], plan=plan, classroom=original_identity_classroom,
            audit=audit, expected_source_sha256=expected_source_sha256, now_ms=manifest['reviewedAt'])
        if not rechecked:
            fail('v2 必须有真实单次独立复核记录')
    from content.textbook_pinyin_carrier_equivalence import validate_evidence
    equivalent = validate_evidence(manifest['carrierOrthographicEvidence'], plan=plan,
        classroom={**classroom, 'id': expected_source_classroom_id}, audit=audit,
        recheck=manifest['asrRecheck'], authorization=manifest['authorization'],
        expected_source_sha256=expected_source_sha256, now_ms=manifest['reviewedAt'])
    failed_rechecks = {k for k, item in rechecked.items() if item['comparison']['passed'] is not True}
    if not equivalent or set(equivalent) != failed_rechecks:
        fail('书写等价必须精确覆盖仍未通过的全部复核，不得覆盖已通过项或漏项')
    if any(item['comparison']['passed'] and item['comparison']['similarityBps'] < 8500
           for item in rechecked.values()):
        fail('原比较门槛不能修改')
    if any(not e['comparison']['passed'] and k not in rechecked for k, e in raw.items()):
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
                       'carrierOrthographicEntrySha256'}, '自动审核段落')
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
                        sensitive=bool(pronunciation_symbols(
                            action['text'].strip(), policy_version=effective_policy['policyVersion'])))
        if (any(item[k] != v for k, v in expected.items()) or type(item['sensitive']) is not bool
                or receipt.get('audioSha256') != entry['audioSha256']
                or (key in rechecked and rechecked[key].get('ttsReceipt') != receipt)):
            fail('原文、实际 TTS/SSML/WAV/PCM 或 ASR 证据不一致')
        used_plans.add(item['requestPlanSha256'])
        accepted[key] = deepcopy(item)
    if set(accepted) != set(actions) or used_plans != set(plans) or not any(x['sensitive'] for x in accepted.values()):
        fail('自动审核必须精确覆盖所有旁白且没有未使用的请求计划')
    _browser(manifest['browserQa'], source_sha=expected_source_sha256, plan=plan,
             scenes=scenes, entries=raw, latest=manifest['reviewedAt'])
    return accepted


def build_operator_review_v2(*, plan, classroom, audit, tts_receipts, authorization, browser_qa,
                          reviewer, reviewed_at, expected_source_sha256, now_ms, request_plans=(), asr_recheck=None, carrier_orthographic_evidence=None):
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
    equivalent = validate_evidence(carrier_orthographic_evidence, plan=plan, classroom=classroom,
        audit=audit, recheck=asr_recheck, authorization=authorization,
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
                if (entry['sceneId'], entry['actionId']) in equivalent else None})
    result = _seal({'schemaVersion': SCHEMA_V2, 'method': METHOD_V2, 'previewKey': plan['previewKey'],
        'sourceSha256': expected_source_sha256, 'sourceClassroomId': classroom.get('id'),
        'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'policySha256': digest(policy), 'auditSha256': digest(audit), 'authorization': deepcopy(authorization),
        'browserQa': deepcopy(browser_qa), 'humanListeningVerified': False, 'perceptualToneVerified': False,
        'evidenceLimit': EVIDENCE_LIMIT_V2, 'phoneticAccuracyVerified': False,
        'carrierOrthographicEvidence': deepcopy(carrier_orthographic_evidence), 'reviewer': reviewer, 'reviewedAt': reviewed_at,
        'requestPlans': deepcopy(list(request_plans)), 'asrRecheck': deepcopy(asr_recheck), 'segments': segments})
    validate_operator_review(result, plan=plan, classroom=classroom, audit=audit,
                             expected_source_sha256=expected_source_sha256, now_ms=now_ms)
    return result


def validate_operator_review(manifest, **kwargs):
    if isinstance(manifest, dict) and manifest.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v7-explicit-observation-acceptance':
        from content.textbook_pinyin_operator_review_v7 import validate_operator_review_v7
        return validate_operator_review_v7(manifest, **kwargs)
    if isinstance(manifest, dict) and manifest.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v6-explicit-routine-acceptance':
        from content.textbook_pinyin_operator_review_v6 import validate_operator_review_v6
        return validate_operator_review_v6(manifest, **kwargs)
    if isinstance(manifest, dict) and manifest.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v5-explicit-acceptance':
        from content.textbook_pinyin_operator_review_v5 import validate_operator_review_v5
        return validate_operator_review_v5(manifest, **kwargs)
    if isinstance(manifest, dict) and manifest.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v4-asr-origin':
        from content.textbook_pinyin_operator_review_v4 import validate_operator_review_v4
        return validate_operator_review_v4(manifest, **kwargs)
    if isinstance(manifest, dict) and manifest.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v3':
        from content.textbook_pinyin_operator_review_v3 import validate_operator_review_v3
        return validate_operator_review_v3(manifest, **kwargs)
    if isinstance(manifest, dict) and manifest.get('schemaVersion') == SCHEMA_V2:
        return _validate_operator_review_v2(manifest, **kwargs)
    return _V1_VALIDATOR(manifest, **kwargs)


def operator_acceptance_method(review):
    if review.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v7-explicit-observation-acceptance':
        return 'user-authorized-pending-same-wav-observation-acceptance'
    if review.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v6-explicit-routine-acceptance':
        return 'user-authorized-unresolved-routine-asr-acceptance'
    if review.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v5-explicit-acceptance':
        return 'user-authorized-unresolved-asr-acceptance'
    if review.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v4-asr-origin':
        return 'automatic-asr-original-source-reuse'
    if review.get('schemaVersion') == 'mira.textbook.pinyin-operator-review.v3':
        return 'automatic-asr-with-exact-natural-alias-content'
    if review.get('schemaVersion') == SCHEMA_V2:
        return 'independent-asr-with-exact-carrier-orthography'
    return 'independent-asr-recheck' if review['asrRecheck'] is not None else 'literal-asr'
