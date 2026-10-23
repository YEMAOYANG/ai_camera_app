"""Explicit lesson-bound acceptance over an unchanged routine v2 ASR audit.

Every action retains its own original routine request and receipt, including
equal PCM produced for repeated instructions. No origin/recheck is invented,
no score is rewritten, and no provider operation is implemented here. The
caller supplies and archives the actual user's decision and probe evidence;
this pure module cannot authenticate a conversation or perform listening.
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

SCHEMA_V6 = 'mira.textbook.pinyin-operator-review.v6-explicit-routine-acceptance'
METHOD_V6 = 'user-authorized-unresolved-routine-asr-acceptance'
EXPLICIT_SCHEMA = 'mira.textbook.unresolved-asr-explicit-acceptance.v2-raw-routine'
EXPLICIT_DECISION = 'accept-unresolved-asr-for-this-lesson-and-publish'
UNRESOLVED_METHOD = 'explicit-user-accepted-unresolved-routine-asr'
LIMIT_V6 = ('All original routine v2 ASR entries, request identities, transcripts, scores and '
    'TTS/WAV/PCM evidence are preserved. Equal PCM across different actions is not relabelled '
    'as independent rechecks or origin reuse. Only the exact failed set is accepted by the '
    'recorded explicit user decision for this lesson and source. No further provider calls, '
    'human listening, phonetic accuracy or perceptual tone verification.')
_FALSE = ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified')
_TRUE = ('onlyThisLesson', 'noFurtherProviderCalls', 'publicationAuthorized',
         'unresolvedAsrAccepted', 'preserveRawEvidence')
_IDENTITY = ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256', 'pcmSha256',
             'asrRequestId', 'asrReceiptSha256', 'transcriptSha256', 'auditSegmentSha256')
_DECISION_FIELDS = {'schemaVersion', 'source', 'questionItemId', 'question', 'statement', 'decision',
    'recordedAt', 'scope', 'sourceSha256', 'planSha256', 'auditSha256', 'probeEvidenceSha256',
    'unresolvedCount', 'unresolvedSegments', 'sha256', *_FALSE, *_TRUE}


def _checked(*, plan, classroom, audit, tts_receipts, expected_source_sha256, now_ms,
             request_plans=(), expected_source_classroom_id=None):
    """Recompute v1/v3 receipt checks without constructing a passing surrogate."""
    if not isinstance(plan, dict) or plan.get('schemaVersion') != PLAN_SCHEMA:
        fail('Explicit routine acceptance requires the registered pinyin contract')
    contract, policy = resolve_audio_contract(plan), policy_for_plan(plan)
    if (type(now_ms) is not int or now_ms <= 0 or not _sha(expected_source_sha256)
            or contract['comparisonPolicy']['version'] != 'literal-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('Original source and literal comparison contract must remain unchanged')
    if not isinstance(classroom, dict) or not isinstance(classroom.get('scenes'), list):
        fail('Invalid classroom structure')
    if expected_source_classroom_id is None:
        if digest(classroom) != expected_source_sha256:
            fail('Current complete source differs from the accepted source')
        expected_source_classroom_id = classroom.get('id')
    if not _text(expected_source_classroom_id):
        fail('Original classroom identity is required')
    _sealed(audit, 'Original routine ASR audit')
    if (audit.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or type(audit.get('passed')) is not bool
            or audit.get('previewKey') != plan['previewKey']
            or audit.get('sourceSha256') != expected_source_sha256
            or audit.get('contract') != audit_contract_identity(plan)
            or not isinstance(audit.get('segments'), list)
            or any(k in audit for k in ('listeningReview', 'reconciliation', 'pronunciationReview',
                                       'asrRecheck', 'origins', 'probeProtocol'))):
        fail('Explicit routine acceptance requires the complete unmodified v2 audit')
    scenes, actions, action_ids = {}, {}, set()
    for scene in classroom['scenes']:
        if (not isinstance(scene, dict) or not _text(scene.get('id')) or scene['id'] in scenes
                or not isinstance(scene.get('actions', []), list)):
            fail('Invalid or duplicate scene identity')
        scenes[scene['id']] = scene
        for action in scene.get('actions', []):
            if not isinstance(action, dict):
                fail('Invalid action')
            if action.get('type') != 'speech':
                continue
            if (not all(_text(action.get(k)) for k in ('id', 'text', 'audioId'))
                    or action['id'] in action_ids):
                fail('Invalid or duplicate speech identity')
            action_ids.add(action['id'])
            actions[(scene['id'], action['id'])] = action
    if (not isinstance(tts_receipts, list) or not tts_receipts
            or any(not isinstance(r, dict) or not _text(r.get('requestId')) for r in tts_receipts)
            or not isinstance(request_plans, (list, tuple))):
        fail('Complete actual TTS receipts and request plans are required')
    receipts = {r['requestId']: r for r in tts_receipts}
    if (len(receipts) != len(tts_receipts)
            or set(receipts) != {a['audioId'] for a in actions.values()}
            or len(receipts) != len(actions)):
        fail('Every action must retain exactly its own actual TTS receipt')
    plans = {digest(plan): plan}
    for child in request_plans:
        validate_child_request_plan(plan, child)
        if digest(child) in plans:
            fail('Duplicate child request plan')
        plans[digest(child)] = child
    raw, segments, literal_results, asr_ids, used_plans = {}, [], [], set(), {digest(plan)}
    for entry in audit['segments']:
        if not isinstance(entry, dict) or not all(_text(entry.get(k)) for k in ('sceneId', 'actionId')):
            fail('Invalid routine ASR identity')
        key = (entry['sceneId'], entry['actionId'])
        response = entry.get('asr')
        if (key not in actions or key in raw or type(entry.get('similarityBps')) is not int
                or not _sha(entry.get('audioSha256')) or not isinstance(entry.get('comparison'), dict)
                or type(entry['comparison'].get('passed')) is not bool or not isinstance(response, dict)
                or response.get('completionUsable') is False
                or not _text(response.get('requestId')) or response['requestId'] in asr_ids
                or any(k in entry for k in ('originSha256', 'target', 'asrRecheckEntrySha256'))):
            fail('Every original routine response must remain complete, unique and unrelabeled')
        action, receipt = actions[key], receipts[actions[key]['audioId']]
        passed = validate_v2_audit_segment(plan, action, entry, scene_id=key[0])
        literal_results.append(passed)
        identity = receipt.get('previewAudioIdentity', {})
        attempt = identity.get('attempt') if isinstance(identity, dict) else None
        request_plan = plans.get(identity.get('planSha256')) if isinstance(identity, dict) else None
        revision = receipt.get('narrationRevisionId')
        if (request_plan is None or type(attempt) is not int or attempt < 1
                or identity != {'planSha256': digest(request_plan), 'attempt': attempt}
                or receipt.get('status') != 'succeeded' or receipt.get('completionUsable') is False
                or receipt.get('requestId') != tts_request_id(request_plan, *key, action['text'], attempt=attempt)
                or receipt['requestId'] != action['audioId']
                or (revision is None and request_plan != plan)
                or (revision is not None and (request_plan == plan or revision != request_plan['revisionId']
                    or receipt.get('classroomContentSha256') != request_plan['classroomSha256']))):
            fail('TTS identity must belong to its original or archived child request')
        if request_plan != plan:
            validate_child_request_plan(plan, request_plan, text=action['text'].strip())
        audit_plan = audit_segment_plan(plan, action, entry, scene_id=key[0])
        if audit_plan.get('pronunciationPolicySha256') != request_plan.get('pronunciationPolicySha256'):
            fail('TTS and original ASR must use the same actual policy')
        effective_policy = policy_for_plan(request_plan)
        validate_formal_receipt(receipt, action['text'].strip(), policy_version=effective_policy['policyVersion'])
        if (not isinstance(action.get('audioMetadata'), dict)
                or any(action['audioMetadata'].get(k) != policy[k] for k in ('providerId', 'modelId', 'voiceId'))
                or action['audioMetadata'].get('fallbackUsed') is not False
                or receipt.get('audioSha256') != entry['audioSha256']):
            fail('Actual audio and teacher metadata differ from the verified receipt')
        segments.append({**{k: entry[k] for k in ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256')},
            'pcmSha256': receipt['pcmSha256'],
            'sensitive': bool(pronunciation_symbols(action['text'].strip(), policy_version=effective_policy['policyVersion'])),
            'requestPlanSha256': digest(request_plan), 'ttsReceipt': deepcopy(receipt),
            'ttsReceiptSha256': digest(receipt), 'asrRequestId': response['requestId'],
            'asrReceiptSha256': digest(response), 'transcriptSha256': response['transcriptSha256'],
            'auditSegmentSha256': digest(entry), 'originalLiteralPassed': passed,
            'originalSimilarityBps': entry['similarityBps'],
            'acceptanceMethod': 'literal-asr' if passed else UNRESOLVED_METHOD})
        raw[key] = entry
        asr_ids.add(response['requestId'])
        used_plans.add(digest(request_plan))
    if (not actions or set(raw) != set(actions) or audit['passed'] is not all(literal_results)
            or used_plans != set(plans) or not any(s['sensitive'] for s in segments)):
        fail('Complete original speech, receipt, comparison and used-plan coverage is required')
    return segments, raw, scenes, expected_source_classroom_id


def _decision(*, segments, plan, audit, source_sha, source_id, probe_evidence_sha256,
              question_item_id, question, statement, decision, recorded_at, now_ms):
    if (not _sha(probe_evidence_sha256) or not _text(question) or not _text(statement)
            or not _time(recorded_at, now_ms) or decision != EXPLICIT_DECISION
            or not isinstance(question_item_id, list) or len(question_item_id) != 3
            or question_item_id[0] != 'request_user_input_async' or not _text(question_item_id[1])
            or type(question_item_id[2]) is not int or question_item_id[2] < 0):
        fail('Actual scoped user decision, message identity and original probe evidence are required')
    unresolved = [{**{k: s[k] for k in _IDENTITY}, 'originalSimilarityBps': s['originalSimilarityBps']}
                  for s in segments if s['originalLiteralPassed'] is False]
    if not unresolved:
        fail('Explicit unresolved acceptance cannot cover an already accepted lesson')
    return _seal({'schemaVersion': EXPLICIT_SCHEMA, 'source': 'user-message',
        'questionItemId': deepcopy(question_item_id), 'question': question, 'statement': statement,
        'decision': decision, 'recordedAt': recorded_at,
        'scope': {**deepcopy(plan['binding']), 'previewKey': plan['previewKey'], 'sourceClassroomId': source_id},
        'sourceSha256': source_sha, 'planSha256': digest(plan), 'auditSha256': digest(audit),
        'probeEvidenceSha256': probe_evidence_sha256, 'unresolvedCount': len(unresolved),
        'unresolvedSegments': unresolved, **{k: False for k in _FALSE}, **{k: True for k in _TRUE}})


def build_explicit_acceptance_v6(*, plan, classroom, audit, tts_receipts, expected_source_sha256,
        probe_evidence_sha256, question_item_id, question, statement, decision, recorded_at, now_ms,
        request_plans=(), expected_source_classroom_id=None):
    segments, _, _, source_id = _checked(plan=plan, classroom=classroom, audit=audit,
        tts_receipts=tts_receipts, expected_source_sha256=expected_source_sha256, now_ms=now_ms,
        request_plans=request_plans, expected_source_classroom_id=expected_source_classroom_id)
    return _decision(segments=segments, plan=plan, audit=audit, source_sha=expected_source_sha256,
        source_id=source_id, probe_evidence_sha256=probe_evidence_sha256, question_item_id=question_item_id,
        question=question, statement=statement, decision=decision, recorded_at=recorded_at, now_ms=now_ms)


def build_operator_review_v6(*, plan, classroom, audit, tts_receipts, authorization, browser_qa,
        reviewer, reviewed_at, expected_source_sha256, now_ms, explicit_acceptance,
        request_plans=(), expected_source_classroom_id=None):
    segments, raw, scenes, source_id = _checked(plan=plan, classroom=classroom, audit=audit,
        tts_receipts=tts_receipts, expected_source_sha256=expected_source_sha256, now_ms=now_ms,
        request_plans=request_plans, expected_source_classroom_id=expected_source_classroom_id)
    if not _text(reviewer) or not _time(reviewed_at, now_ms):
        fail('Invalid operator reviewer/time')
    _authorization(authorization, plan, reviewed_at)
    _fields(explicit_acceptance, _DECISION_FIELDS, 'Explicit routine ASR acceptance')
    _sealed(explicit_acceptance, 'Explicit routine ASR acceptance')
    if (any(explicit_acceptance[k] is not False for k in _FALSE)
            or any(explicit_acceptance[k] is not True for k in _TRUE)
            or type(explicit_acceptance['unresolvedCount']) is not int):
        fail('Explicit acceptance cannot omit permission or claim perceptual verification')
    expected = _decision(segments=segments, plan=plan, audit=audit, source_sha=expected_source_sha256,
        source_id=source_id, probe_evidence_sha256=explicit_acceptance['probeEvidenceSha256'],
        question_item_id=explicit_acceptance['questionItemId'], question=explicit_acceptance['question'],
        statement=explicit_acceptance['statement'], decision=explicit_acceptance['decision'],
        recorded_at=explicit_acceptance['recordedAt'], now_ms=reviewed_at)
    if explicit_acceptance != expected:
        fail('Decision must bind exactly the failed current routine entries and every original identity')
    for segment in segments:
        segment['explicitAcceptanceSha256'] = digest(expected) if not segment['originalLiteralPassed'] else None
    _browser(browser_qa, source_sha=expected_source_sha256, plan=plan, scenes=scenes, entries=raw, latest=reviewed_at)
    return _seal({'schemaVersion': SCHEMA_V6, 'method': METHOD_V6, 'previewKey': plan['previewKey'],
        'sourceClassroomId': source_id, 'sourceSha256': expected_source_sha256,
        'coreSha256': plan['coreSha256'], 'planSha256': digest(plan), 'policySha256': digest(policy_for_plan(plan)),
        'auditSha256': digest(audit), 'authorization': deepcopy(authorization), 'browserQa': deepcopy(browser_qa),
        'reviewer': reviewer, 'reviewedAt': reviewed_at, 'requestPlans': deepcopy(list(request_plans)),
        'segments': segments, 'explicitAcceptance': deepcopy(expected),
        **{k: False for k in _FALSE}, 'evidenceLimit': LIMIT_V6})


def validate_operator_review_v6(manifest, *, plan, classroom, audit, expected_source_sha256,
        now_ms, expected_source_classroom_id=None):
    _fields(manifest, {'schemaVersion', 'method', 'previewKey', 'sourceClassroomId', 'sourceSha256',
        'coreSha256', 'planSha256', 'policySha256', 'auditSha256', 'authorization', 'browserQa',
        'reviewer', 'reviewedAt', 'requestPlans', 'segments', 'explicitAcceptance',
        'evidenceLimit', 'sha256', *_FALSE}, 'Explicit routine ASR review')
    _sealed(manifest, 'Explicit routine ASR review')
    if (any(manifest[k] is not False for k in _FALSE) or not isinstance(manifest['segments'], list)
            or any(not isinstance(s, dict) or not isinstance(s.get('ttsReceipt'), dict) for s in manifest['segments'])):
        fail('Explicit routine acceptance needs actual receipts and cannot claim listening')
    expected = build_operator_review_v6(plan=plan, classroom=classroom, audit=audit,
        tts_receipts=[s['ttsReceipt'] for s in manifest['segments']], authorization=manifest['authorization'],
        browser_qa=manifest['browserQa'], reviewer=manifest['reviewer'], reviewed_at=manifest['reviewedAt'],
        expected_source_sha256=expected_source_sha256, now_ms=now_ms,
        explicit_acceptance=manifest['explicitAcceptance'], request_plans=manifest['requestPlans'],
        expected_source_classroom_id=expected_source_classroom_id)
    if manifest != expected:
        fail('Explicit routine review differs from current raw evidence or the supplied decision')
    return {(s['sceneId'], s['actionId']): deepcopy(s) for s in expected['segments']}


def accepts_validated_routine_segment(review, item, entry):
    """Publication-only discriminator AFTER complete manifest validation."""
    return (isinstance(review, dict) and review.get('schemaVersion') == SCHEMA_V6
        and item.get('acceptanceMethod') == UNRESOLVED_METHOD
        and item.get('originalLiteralPassed') is False
        and entry.get('comparison', {}).get('passed') is False
        and item.get('auditSegmentSha256') == digest(entry)
        and item.get('explicitAcceptanceSha256') == digest(review.get('explicitAcceptance'))
        and all(item.get(k) == entry.get(k) for k in
                ('sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256')))
