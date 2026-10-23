"""Explicit, lesson-bound acceptance of unresolved ASR; never a listening claim.

The caller must supply the actual user's decision and the verified original
probe-approval seal. This pure module cannot authenticate a conversation. It
recomputes every receipt, WAV, original ASR and unresolved identity before it
can record that decision; v1-v4 results and raw comparisons remain unchanged.
"""
from copy import deepcopy

from content.textbook_catalog import digest
from content.textbook_asr_source_reuse import acceptance, sha, validate_audit
from content.textbook_pinyin_pronunciation import policy_for_plan, pronunciation_symbols
from content.textbook_pinyin_operator_review import (
    _authorization, _browser, _fields, _seal, _sealed, _sha, _text, _time, fail,
)
from core.errors import ApiError


SCHEMA_V5 = 'mira.textbook.pinyin-operator-review.v5-explicit-acceptance'
METHOD_V5 = 'user-authorized-unresolved-asr-acceptance'
EXPLICIT_SCHEMA = 'mira.textbook.unresolved-asr-explicit-acceptance.v1'
EXPLICIT_DECISION = 'accept-unresolved-asr-for-this-lesson-and-publish'
UNRESOLVED_METHOD = 'explicit-user-accepted-unresolved-asr'
LIMIT_V5 = ('All current TTS/WAV/PCM and original ASR evidence remain independently validated. '
    'Existing automatic acceptance methods are retained; only the exact unresolved set is accepted '
    'by the recorded explicit user decision for this lesson and source. Raw failures and uncertainty '
    'remain unchanged. No additional provider calls, human listening, phonetic accuracy or perceptual tone verification.')
_FALSE = ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified')
_TRUE = ('onlyThisLesson', 'noFurtherProviderCalls', 'publicationAuthorized',
         'unresolvedAsrAccepted', 'preserveRawEvidence')
_IDENTITY = ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256', 'pcmSha256', 'originSha256')
_EXPLICIT_FIELDS = {'schemaVersion', 'source', 'questionItemId', 'question', 'statement', 'decision',
    'recordedAt', 'scope', 'sourceSha256', 'planSha256', 'auditSha256', 'approvedProbeSha256',
    'unresolvedCount', 'unresolvedSegments', 'sha256', *_FALSE, *_TRUE}


def _classify(checked, plan):
    methods, unresolved = {}, []
    for key, (entry, origin) in checked.items():
        policy = policy_for_plan(entry['target']['requestPlan'] or plan)
        try:
            methods[key] = acceptance(entry, origin, plan, policy)
        except ApiError as exc:
            # Origin/receipt validation already succeeded. Explicit content
            # acceptance cannot waive an excess-call budget or unknown errors.
            if (len(origin['attempts']) > 2 or exc.code not in (
                    'textbook_asr_source_reuse_invalid', 'textbook_pinyin_carrier_equivalence_invalid')):
                raise
            methods[key] = UNRESOLVED_METHOD
            unresolved.append({**{name: entry[name] for name in _IDENTITY},
                'asrAttempts': [{'requestId': attempt['requestId'],
                    'transcriptSha256': sha(attempt['transcript'].encode())}
                    for attempt in origin['attempts']],
                'existingAcceptanceFailure': {'code': exc.code, 'message': exc.message}})
    return methods, unresolved


def _decision(*, checked, plan, audit, expected_source_sha256, source_classroom_id,
              approved_probe_sha256, question_item_id, question, statement, decision,
              recorded_at, now_ms):
    if (not _sha(approved_probe_sha256) or not _text(question) or not _text(statement)
            or not _time(recorded_at, now_ms) or decision != EXPLICIT_DECISION
            or not isinstance(question_item_id, list) or len(question_item_id) != 3
            or question_item_id[0] != 'request_user_input_async' or not _text(question_item_id[1])
            or type(question_item_id[2]) is not int or question_item_id[2] < 0):
        fail('Explicit acceptance needs the actual scoped user decision, original probe seal and message identity')
    _, unresolved = _classify(checked, plan)
    if not unresolved:
        fail('Explicit unresolved acceptance cannot cover an already accepted lesson')
    return _seal({'schemaVersion': EXPLICIT_SCHEMA, 'source': 'user-message',
        'questionItemId': deepcopy(question_item_id), 'question': question, 'statement': statement,
        'decision': decision, 'recordedAt': recorded_at,
        'scope': {**deepcopy(plan['binding']), 'previewKey': plan['previewKey'],
                  'sourceClassroomId': source_classroom_id},
        'sourceSha256': expected_source_sha256, 'planSha256': digest(plan), 'auditSha256': digest(audit),
        'approvedProbeSha256': approved_probe_sha256, 'unresolvedCount': len(unresolved),
        'unresolvedSegments': unresolved, **{key: False for key in _FALSE},
        **{key: True for key in _TRUE}})


def build_explicit_acceptance(*, plan, classroom, audit, expected_source_sha256,
        approved_probe_sha256, question_item_id, question, statement, decision,
        recorded_at, now_ms, expected_source_classroom_id=None):
    """Bind a supplied explicit decision to the recomputed exact unresolved set.

    ``decision`` must be EXPLICIT_DECISION, deliberately without a default.
    The caller archives the authentic question/answer and original approval;
    this helper neither invents authorization nor infers consent from prose.
    """
    checked = validate_audit(audit, plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    return _decision(checked=checked, plan=plan, audit=audit,
        expected_source_sha256=expected_source_sha256,
        source_classroom_id=expected_source_classroom_id or classroom['id'],
        approved_probe_sha256=approved_probe_sha256, question_item_id=question_item_id,
        question=question, statement=statement, decision=decision, recorded_at=recorded_at, now_ms=now_ms)


def build_operator_review_v5(*, plan, classroom, audit, authorization, browser_qa, reviewer,
        reviewed_at, expected_source_sha256, now_ms, explicit_acceptance,
        expected_source_classroom_id=None):
    checked = validate_audit(audit, plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256,
        expected_source_classroom_id=expected_source_classroom_id)
    if not _text(reviewer) or not _time(reviewed_at, now_ms):
        fail('Invalid operator reviewer/time')
    _authorization(authorization, plan, reviewed_at)
    _fields(explicit_acceptance, _EXPLICIT_FIELDS, 'Explicit unresolved ASR acceptance')
    _sealed(explicit_acceptance, 'Explicit unresolved ASR acceptance')
    if (any(explicit_acceptance[key] is not False for key in _FALSE)
            or any(explicit_acceptance[key] is not True for key in _TRUE)
            or type(explicit_acceptance['unresolvedCount']) is not int):
        fail('Explicit acceptance cannot omit permission or claim human/perceptual verification')
    expected_decision = _decision(checked=checked, plan=plan, audit=audit,
        expected_source_sha256=expected_source_sha256,
        source_classroom_id=expected_source_classroom_id or classroom['id'],
        approved_probe_sha256=explicit_acceptance['approvedProbeSha256'],
        question_item_id=explicit_acceptance['questionItemId'], question=explicit_acceptance['question'],
        statement=explicit_acceptance['statement'], decision=explicit_acceptance['decision'],
        recorded_at=explicit_acceptance['recordedAt'], now_ms=reviewed_at)
    if explicit_acceptance != expected_decision:
        fail('Explicit acceptance must bind exactly all current unresolved entries and original ASR attempts')
    methods, _ = _classify(checked, plan)
    segments, plans = [], {}
    for key, (entry, origin) in checked.items():
        target = entry['target']; receipt = target['ttsReceipt']; child = target['requestPlan']
        if child is not None:
            plans[digest(child)] = child
        policy = policy_for_plan(child or plan)
        segments.append({**{name: entry[name] for name in _IDENTITY if name != 'originSha256'},
            'sensitive': bool(pronunciation_symbols(entry['text'], policy_version=policy['policyVersion'])),
            'requestPlanSha256': digest(child or plan), 'ttsReceipt': deepcopy(receipt),
            'ttsReceiptSha256': digest(receipt), 'auditSegmentSha256': digest(entry),
            'asrOriginEntrySha256': entry['originSha256'], 'originalAsrRequestId': origin['attempts'][0]['requestId'],
            'acceptanceMethod': methods[key], 'originalLiteralPassed': entry['comparison']['passed'],
            'originalSimilarityBps': entry['similarityBps']})
    _browser(browser_qa, source_sha=expected_source_sha256, plan=plan,
        scenes={scene['id']: scene for scene in classroom['scenes']},
        entries={key: value[0] for key, value in checked.items()}, latest=reviewed_at)
    return _seal({'schemaVersion': SCHEMA_V5, 'method': METHOD_V5,
        'previewKey': plan['previewKey'], 'sourceClassroomId': expected_source_classroom_id or classroom['id'],
        'sourceSha256': expected_source_sha256, 'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'policySha256': digest(policy_for_plan(plan)), 'auditSha256': digest(audit),
        'authorization': deepcopy(authorization), 'browserQa': deepcopy(browser_qa),
        'reviewer': reviewer, 'reviewedAt': reviewed_at, 'requestPlans': list(plans.values()), 'segments': segments,
        'explicitAcceptance': deepcopy(explicit_acceptance), **{key: False for key in _FALSE},
        'evidenceLimit': LIMIT_V5})


def validate_operator_review_v5(manifest, *, plan, classroom, audit, expected_source_sha256,
        now_ms, expected_source_classroom_id=None):
    _fields(manifest, {'schemaVersion', 'method', 'previewKey', 'sourceClassroomId', 'sourceSha256',
        'coreSha256', 'planSha256', 'policySha256', 'auditSha256', 'authorization', 'browserQa',
        'reviewer', 'reviewedAt', 'requestPlans', 'segments', 'explicitAcceptance',
        'evidenceLimit', 'sha256', *_FALSE}, 'Explicit ASR operator review')
    _sealed(manifest, 'Explicit ASR operator review')
    if any(manifest[key] is not False for key in _FALSE):
        fail('Explicit ASR acceptance is not human listening or perceptual verification')
    expected = build_operator_review_v5(plan=plan, classroom=classroom, audit=audit,
        authorization=manifest['authorization'], browser_qa=manifest['browserQa'], reviewer=manifest['reviewer'],
        reviewed_at=manifest['reviewedAt'], expected_source_sha256=expected_source_sha256, now_ms=now_ms,
        explicit_acceptance=manifest['explicitAcceptance'],
        expected_source_classroom_id=expected_source_classroom_id)
    if manifest != expected:
        fail('Explicit ASR review differs from current raw evidence or the recorded decision')
    return {(entry['sceneId'], entry['actionId']): deepcopy(entry) for entry in expected['segments']}
