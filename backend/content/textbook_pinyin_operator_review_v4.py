"""Explicit origin-audit acceptance; v1-v3 receipts and branches stay intact."""
from copy import deepcopy
from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import policy_for_plan, pronunciation_symbols
from content.textbook_asr_source_reuse import validate_audit, acceptance
from content.textbook_pinyin_operator_review import _fields, _sealed, _seal, _authorization, _browser, _text, _time, fail

SCHEMA_V4 = 'mira.textbook.pinyin-operator-review.v4-asr-origin'
METHOD_V4 = 'automatic-asr-original-source-reuse'
LIMIT_V4 = 'Every current TTS independently bound to unchanged original ASR WAV/PCM and exact text/body/voice; literal ASR, bounded recheck, sealed all-literal historical-excess consensus, strict carrier orthography or exact registered natural alias content only. No human listening, phonetic accuracy or perceptual tone verification.'


def build_operator_review_v4(*, plan, classroom, audit, authorization, browser_qa, reviewer,
                             reviewed_at, expected_source_sha256, now_ms,
                             expected_source_classroom_id=None):
    checked = validate_audit(audit, plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256, expected_source_classroom_id=expected_source_classroom_id)
    if not _text(reviewer) or not _time(reviewed_at, now_ms): fail('Invalid operator reviewer/time')
    _authorization(authorization, plan, reviewed_at)
    segments, plans = [], {}
    for key, (entry, origin) in checked.items():
        target = entry['target']; receipt = target['ttsReceipt']; child = target['requestPlan']
        if child is not None: plans[digest(child)] = child
        policy = policy_for_plan(child or plan)
        method = acceptance(entry, origin, plan, policy)
        segments.append({**{k: entry[k] for k in ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256', 'pcmSha256')},
            'sensitive': bool(pronunciation_symbols(entry['text'], policy_version=policy['policyVersion'])),
            'requestPlanSha256': digest(child or plan), 'ttsReceipt': deepcopy(receipt),
            'ttsReceiptSha256': digest(receipt), 'auditSegmentSha256': digest(entry),
            'asrOriginEntrySha256': entry['originSha256'], 'originalAsrRequestId': origin['attempts'][0]['requestId'],
            'acceptanceMethod': method,
            'originalLiteralPassed': entry['comparison']['passed'], 'originalSimilarityBps': entry['similarityBps']})
    _browser(browser_qa, source_sha=expected_source_sha256, plan=plan,
        scenes={s['id']: s for s in classroom['scenes']}, entries={k: v[0] for k, v in checked.items()}, latest=reviewed_at)
    return _seal({'schemaVersion': SCHEMA_V4, 'method': METHOD_V4,
        'previewKey': plan['previewKey'], 'sourceClassroomId': expected_source_classroom_id or classroom['id'],
        'sourceSha256': expected_source_sha256, 'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'policySha256': digest(policy_for_plan(plan)), 'auditSha256': digest(audit),
        'authorization': deepcopy(authorization), 'browserQa': deepcopy(browser_qa),
        'reviewer': reviewer, 'reviewedAt': reviewed_at, 'requestPlans': list(plans.values()), 'segments': segments,
        'humanListeningVerified': False, 'phoneticAccuracyVerified': False, 'perceptualToneVerified': False,
        'evidenceLimit': LIMIT_V4})


def validate_operator_review_v4(manifest, *, plan, classroom, audit, expected_source_sha256, now_ms,
                                expected_source_classroom_id=None):
    keys = {'schemaVersion', 'method', 'previewKey', 'sourceClassroomId', 'sourceSha256', 'coreSha256',
        'planSha256', 'policySha256', 'auditSha256', 'authorization', 'browserQa', 'reviewer', 'reviewedAt',
        'requestPlans', 'segments', 'humanListeningVerified', 'phoneticAccuracyVerified',
        'perceptualToneVerified', 'evidenceLimit', 'sha256'}
    _fields(manifest, keys, 'ASR 来源自动审核'); _sealed(manifest, 'ASR 来源自动审核')
    expected = build_operator_review_v4(plan=plan, classroom=classroom, audit=audit,
        authorization=manifest['authorization'], browser_qa=manifest['browserQa'], reviewer=manifest['reviewer'],
        reviewed_at=manifest['reviewedAt'], expected_source_sha256=expected_source_sha256, now_ms=now_ms,
        expected_source_classroom_id=expected_source_classroom_id)
    if manifest != expected: fail('ASR source review differs from actual raw evidence and current TTS')
    return {(e['sceneId'], e['actionId']): deepcopy(e) for e in expected['segments']}
