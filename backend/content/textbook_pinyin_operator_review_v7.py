"""Explicit lesson acceptance of complete same-WAV observations, never listening.

Only the caller's authentic scoped decision can accept pending target content.
WAV/PCM, source, protocol, receipt, coverage and browser failures are not waived.
"""
from copy import deepcopy

from content.textbook_catalog import digest
from content.textbook_asr_observation import SCHEMA as AUDIT_SCHEMA, FALSE, validate_observation_audit
from content.textbook_pinyin_pronunciation import policy_for_plan, pronunciation_symbols
from content.textbook_pinyin_operator_review import (
    _authorization, _browser, _fields, _sealed, _seal, _sha, _text, _time, fail,
)

SCHEMA = 'mira.textbook.pinyin-operator-review.v7-explicit-observation-acceptance'
METHOD = 'user-authorized-pending-same-wav-observation-acceptance'
DECISION_SCHEMA = 'mira.textbook.pending-asr-observation-explicit-acceptance.v1'
DECISION = 'accept-pending-asr-observations-for-this-lesson-and-publish'
PENDING_METHOD = 'explicit-user-accepted-pending-asr-observation'
LITERAL_METHOD = 'literal-asr-same-source-observation'
LIMIT = ('Every target TTS and complete WAV/PCM is independently validated against its own plan. '
    'Original ASR observations retain their own text, body, source, routines and raw records. '
    'Cross-source, conflicting, low-score and historical-excess observations remain visible; only '
    'the exact pending set is accepted by the actual user decision for this lesson. '
    'No protocol, source, receipt, physical media, coverage, browser or whole-course failure is waived. '
    'No further provider calls, human listening, phonetic accuracy or perceptual tone verification.')
TRUE = ('onlyThisLesson', 'noFurtherProviderCalls', 'publicationAuthorized',
        'pendingObservationsAccepted', 'preserveRawEvidence')
IDENTITY = ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256', 'pcmSha256',
            'pcmKey', 'primaryObservationSha256')
DECISION_FIELDS = {'schemaVersion', 'source', 'questionItemId', 'question', 'statement', 'decision',
    'recordedAt', 'scope', 'sourceSha256', 'planSha256', 'auditSha256', 'probeEvidenceSha256',
    'pendingCount', 'pendingSegments', 'sha256', *FALSE, *TRUE}


def _checked(*, plan, classroom, audit, expected_source_sha256, expected_source_classroom_id=None):
    checked = validate_observation_audit(audit, plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    pending = [{**{k: e[k] for k in IDENTITY}, 'pendingReasons': deepcopy(e['pendingReasons']),
        'observations': deepcopy(e['observations']), 'auditSegmentSha256': digest(e)}
        for e in checked.values() if e['acceptancePending']]
    return checked, pending


def _decision(*, plan, audit, pending, source_sha, source_id, probe_evidence_sha256,
              question_item_id, question, statement, decision, recorded_at, now_ms):
    if (not pending or not _sha(probe_evidence_sha256) or not _text(question) or not _text(statement)
            or not _time(recorded_at, now_ms) or decision != DECISION
            or not isinstance(question_item_id, list) or len(question_item_id) != 3
            or question_item_id[0] != 'request_user_input_async' or not _text(question_item_id[1])
            or type(question_item_id[2]) is not int or question_item_id[2] < 0):
        fail('The actual scoped pending-observation decision and original probe evidence are required')
    return _seal({'schemaVersion': DECISION_SCHEMA, 'source': 'user-message',
        'questionItemId': deepcopy(question_item_id), 'question': question, 'statement': statement,
        'decision': decision, 'recordedAt': recorded_at,
        'scope': {**deepcopy(plan['binding']), 'previewKey': plan['previewKey'], 'sourceClassroomId': source_id},
        'sourceSha256': source_sha, 'planSha256': digest(plan), 'auditSha256': digest(audit),
        'probeEvidenceSha256': probe_evidence_sha256, 'pendingCount': len(pending),
        'pendingSegments': deepcopy(pending), **{k: False for k in FALSE}, **{k: True for k in TRUE}})


def build_explicit_acceptance_v7(*, plan, classroom, audit, expected_source_sha256,
        probe_evidence_sha256, question_item_id, question, statement, decision,
        recorded_at, now_ms, expected_source_classroom_id=None):
    _, pending = _checked(plan=plan, classroom=classroom, audit=audit,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    return _decision(plan=plan, audit=audit, pending=pending, source_sha=expected_source_sha256,
        source_id=expected_source_classroom_id or classroom['id'],
        probe_evidence_sha256=probe_evidence_sha256, question_item_id=question_item_id,
        question=question, statement=statement, decision=decision, recorded_at=recorded_at, now_ms=now_ms)


def build_operator_review_v7(*, plan, classroom, audit, authorization, browser_qa, reviewer,
        reviewed_at, expected_source_sha256, now_ms, explicit_acceptance,
        expected_source_classroom_id=None):
    checked, pending = _checked(plan=plan, classroom=classroom, audit=audit,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    if not _text(reviewer) or not _time(reviewed_at, now_ms): fail('Invalid operator reviewer/time')
    _authorization(authorization, plan, reviewed_at)
    source_id = expected_source_classroom_id or classroom['id']
    if pending:
        _fields(explicit_acceptance, DECISION_FIELDS, 'Explicit pending-observation acceptance')
        _sealed(explicit_acceptance, 'Explicit pending-observation acceptance')
        if (any(explicit_acceptance[k] is not False for k in FALSE)
                or any(explicit_acceptance[k] is not True for k in TRUE)
                or type(explicit_acceptance['pendingCount']) is not int):
            fail('Pending acceptance cannot claim listening or omit its scope')
        expected = _decision(plan=plan, audit=audit, pending=pending, source_sha=expected_source_sha256,
            source_id=source_id, probe_evidence_sha256=explicit_acceptance['probeEvidenceSha256'],
            question_item_id=explicit_acceptance['questionItemId'], question=explicit_acceptance['question'],
            statement=explicit_acceptance['statement'], decision=explicit_acceptance['decision'],
            recorded_at=explicit_acceptance['recordedAt'], now_ms=reviewed_at)
        if expected != explicit_acceptance: fail('The decision must bind exactly the current pending set and observations')
    elif explicit_acceptance is not None:
        fail('A pending decision cannot be supplied for a fully literal same-source lesson')
    segments, plans = [], {}
    for e in checked.values():
        target = e['target']; child = target['requestPlan']; receipt = target['ttsReceipt']
        if child is not None: plans[digest(child)] = deepcopy(child)
        policy = policy_for_plan(child or plan)
        segments.append({**{k: e[k] for k in IDENTITY},
            'sensitive': bool(pronunciation_symbols(e['text'], policy_version=policy['policyVersion'])),
            'requestPlanSha256': digest(child or plan), 'ttsReceipt': deepcopy(receipt),
            'ttsReceiptSha256': digest(receipt), 'auditSegmentSha256': digest(e),
            'originalLiteralPassed': e['comparison']['passed'], 'originalSimilarityBps': e['similarityBps'],
            'acceptanceMethod': PENDING_METHOD if e['acceptancePending'] else LITERAL_METHOD,
            'explicitAcceptanceSha256': digest(explicit_acceptance) if e['acceptancePending'] else None})
    _browser(browser_qa, source_sha=expected_source_sha256, plan=plan,
        scenes={s['id']: s for s in classroom['scenes']}, entries=checked, latest=reviewed_at)
    return _seal({'schemaVersion': SCHEMA, 'method': METHOD, 'previewKey': plan['previewKey'],
        'sourceClassroomId': source_id, 'sourceSha256': expected_source_sha256,
        'coreSha256': plan['coreSha256'], 'planSha256': digest(plan), 'policySha256': digest(policy_for_plan(plan)),
        'auditSha256': digest(audit), 'authorization': deepcopy(authorization), 'browserQa': deepcopy(browser_qa),
        'reviewer': reviewer, 'reviewedAt': reviewed_at, 'requestPlans': list(plans.values()),
        'segments': segments, 'explicitAcceptance': deepcopy(explicit_acceptance),
        **{k: False for k in FALSE}, 'noFurtherProviderCalls': True, 'evidenceLimit': LIMIT})


def validate_operator_review_v7(manifest, *, plan, classroom, audit, expected_source_sha256,
        now_ms, expected_source_classroom_id=None):
    _fields(manifest, {'schemaVersion', 'method', 'previewKey', 'sourceClassroomId', 'sourceSha256',
        'coreSha256', 'planSha256', 'policySha256', 'auditSha256', 'authorization', 'browserQa',
        'reviewer', 'reviewedAt', 'requestPlans', 'segments', 'explicitAcceptance', 'evidenceLimit',
        'noFurtherProviderCalls', 'sha256', *FALSE}, 'Explicit observation review')
    _sealed(manifest, 'Explicit observation review')
    if (any(manifest[k] is not False for k in FALSE) or manifest['noFurtherProviderCalls'] is not True
            or audit.get('schemaVersion') != AUDIT_SCHEMA):
        fail('Observation review requires its own complete audit and exact capability boundaries')
    expected = build_operator_review_v7(plan=plan, classroom=classroom, audit=audit,
        authorization=manifest['authorization'], browser_qa=manifest['browserQa'], reviewer=manifest['reviewer'],
        reviewed_at=manifest['reviewedAt'], expected_source_sha256=expected_source_sha256, now_ms=now_ms,
        explicit_acceptance=manifest['explicitAcceptance'],
        expected_source_classroom_id=expected_source_classroom_id)
    if manifest != expected: fail('Observation review differs from current original evidence or the supplied decision')
    return {(s['sceneId'], s['actionId']): deepcopy(s) for s in expected['segments']}


def accepts_validated_observation_segment(review, item, entry):
    """Discriminator used only AFTER full v7 validation, never a standalone waiver."""
    return (isinstance(review, dict) and review.get('schemaVersion') == SCHEMA
        and item.get('auditSegmentSha256') == digest(entry)
        and all(item.get(k) == entry.get(k) for k in IDENTITY)
        and ((entry.get('acceptancePending') is False and item.get('acceptanceMethod') == LITERAL_METHOD
              and entry.get('comparison', {}).get('passed') is True)
            or (entry.get('acceptancePending') is True and item.get('acceptanceMethod') == PENDING_METHOD
                and item.get('explicitAcceptanceSha256') == digest(review.get('explicitAcceptance')))))
