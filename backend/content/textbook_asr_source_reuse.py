"""Portable ASR provenance, never a relabelled ASR receipt or listening claim.

The optional v3 audit binds every current TTS independently. Recognition belongs
to its original request. Reuse requires equal complete WAV bytes, PCM, source
text and complete registered provider body, including voice and SSML.
"""
import base64
from copy import deepcopy
import hashlib
import json
import unicodedata

from content.textbook_catalog import canonical, digest
from content.textbook_audio_recheck import provider_body as asr_body, validate_tts_request_plan, seal
from content.textbook_pinyin_pronunciation import (
    policy_for_plan, provider_body, validate_formal_receipt, validate_receipt_wav,
    GARDEN3_V2_POLICY_VERSION,
)
from content.textbook_preview_audio_contract import (
    asr_request_id, compare_transcript, audit_contract_identity, resolve_audio_contract,
)
from core.errors import ApiError

SCHEMA = 'mira.textbook.audio-audit.v3-asr-origin'
ORIGIN_SCHEMA = 'mira.textbook.asr-origin.v1'
FAILED_RECOVERY_ORIGIN_SCHEMA = 'mira.textbook.asr-origin.v3-failed-routine-recovery'
FAILURE_RECOVERY_SCHEMA = 'mira.textbook.asr-failure-recovery.v1'
FAILED_RECOVERY_SELECTION_FIELDS = {
    'sceneId', 'actionId', 'failedRequestId', 'sourceSha256', 'planSha256',
    'audioSha256', 'failedJobSha256', 'failedCacheSha256',
}
CONSENSUS_ORIGIN_SCHEMA = 'mira.textbook.asr-origin.v2-historical-excess-consensus'
LIBRARY_SCHEMA_V1 = 'mira.textbook.asr-origin-library.v1'
LIBRARY_SCHEMA_V2 = 'mira.textbook.asr-origin-library.v2'
INVESTIGATION_SCHEMA = 'mira.textbook.asr-historical-excess-investigation.v1'
EXCESS_ACCEPTANCE = 'historical-excess-all-literal-asr'
LIMIT = 'Original ASR provenance and exact WAV/PCM/request equivalence only; no human listening, phonetic accuracy or perceptual tone verification.'


def fail(message):
    raise ApiError('textbook_asr_source_reuse_invalid', message, 409)


def fields(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        fail('Missing or unknown source evidence fields')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decoded(value):
    try:
        if not isinstance(value, str) or len(value) > 16_000_000: raise ValueError()
        raw = base64.b64decode(value, validate=True)
        if base64.b64encode(raw).decode() != value: raise ValueError()
        return raw
    except (ValueError, TypeError):
        fail('Invalid original byte encoding')


def parsed(value):
    try:
        raw = decoded(value)
        result = json.loads(raw)
        if not isinstance(result, dict): raise ValueError()
        return raw, result
    except (ValueError, TypeError, UnicodeError):
        fail('Invalid original JSON bytes')


def pcm_key(receipt):
    n = receipt['audioNormalization']
    return digest({'pcmSha256': receipt['pcmSha256'], **{k: n[k] for k in
        ('sampleRate', 'channels', 'bitsPerSample', 'pcmByteLength')}})


def target_evidence(source, plan):
    """One independently verified target, including its real amendment plan."""
    required = {'sceneId', 'sceneOrder', 'action', 'ttsReceipt', 'audioBase64', 'requestPlan'}
    fields(source, required)
    action, receipt = source['action'], source['ttsReceipt']
    if (not isinstance(action, dict) or action.get('type') != 'speech'
            or not isinstance(action.get('text'), str) or not action['text'].strip()
            or not isinstance(source['sceneId'], str) or not source['sceneId']
            or type(source['sceneOrder']) is not int or not isinstance(receipt, dict)
            or receipt.get('status') != 'succeeded' or receipt.get('completionUsable') is False):
        fail('Invalid actual formal speech/TTS identity')
    effective = validate_tts_request_plan(plan, {'id': source['sceneId']}, action, receipt, source['requestPlan'])
    policy = policy_for_plan(effective)
    text = action['text'].strip()
    validate_formal_receipt(receipt, text, policy_version=policy['policyVersion'])
    audio = decoded(source['audioBase64'])
    validate_receipt_wav(receipt, audio)
    metadata = action.get('audioMetadata', {})
    if (any(metadata.get(k) != policy[k] for k in ('providerId', 'modelId', 'voiceId'))
            or metadata.get('fallbackUsed') is not False):
        fail('Actual classroom voice metadata differs from its TTS')
    body = provider_body(text, policy_version=policy['policyVersion'])
    return {'text': text, 'body': body, 'audio': audio, 'receipt': receipt,
            'policy': policy, 'effectivePlan': effective, 'pcmKey': pcm_key(receipt)}


def formal_request(source, plan, classroom_id, request_id):
    profile = plan['teacher']['teacherProfile']
    return {'requestId': request_id, 'classroomId': classroom_id,
        'classroomContentSha256': source['ttsReceipt'].get('classroomContentSha256', plan['classroomSha256']),
        'subject': 'chinese', 'teacherProfileId': profile['id'], 'teacherProfileVersion': profile['version'],
        'teacherProfileSha256': profile['contentHash'], 'teacherGender': plan['teacher']['teacherGender'],
        'sceneId': source['sceneId'], 'sceneOrder': source['sceneOrder'], 'actionId': source['action']['id'],
        'narrationSegmentId': source['action']['id'], 'ttsRequestId': source['action']['audioId'],
        'audioSha256': source['ttsReceipt']['audioSha256']}


def shared_recheck_id(key):
    return 'tbpasr1_' + digest({'purpose': 'mira.textbook.shared-pcm-recheck.v1', 'pcmKey': key})


def failed_recovery_id(failed_request_id, key):
    return 'tbpasr1_' + digest({'purpose': FAILURE_RECOVERY_SCHEMA,
        'failedRequestId': failed_request_id, 'pcmKey': key})


def verify_failure_recovery(envelope, *, source, plan, classroom_id):
    """A failed routine remains original bytes, never a successful attempt."""
    fields(envelope, {'schemaVersion', 'selection', 'classroomBase64', 'failedJobBase64', 'failedCacheBase64', 'recoveryRequestId'})
    selected = envelope['selection']; fields(selected, FAILED_RECOVERY_SELECTION_FIELDS)
    facts = target_evidence(source, plan)
    def record(encoded):
        raw = decoded(encoded)
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result: fail('Duplicate failed-recovery JSON field')
                result[key] = value
            return result
        try:
            value = json.loads(raw, object_pairs_hook=pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict): raise ValueError()
        except (ValueError, UnicodeError): fail('Invalid failed-recovery original JSON bytes')
        return raw, value
    job_raw, job = record(envelope['failedJobBase64'])
    cache_raw, cache = record(envelope['failedCacheBase64'])
    _, classroom = record(envelope['classroomBase64'])
    matching = [(scene, action) for scene in classroom.get('scenes', []) if isinstance(scene, dict)
                for action in scene.get('actions', []) if isinstance(action, dict)
                and scene.get('id') == source['sceneId'] and action.get('id') == source['action']['id']]
    original_id = asr_request_id(plan, source['action']['audioId'], sha(facts['audio']))
    request = formal_request(source, plan, classroom_id, original_id)
    sha_fields = ('sourceSha256', 'planSha256', 'audioSha256', 'failedJobSha256', 'failedCacheSha256')
    if (envelope['schemaVersion'] != FAILURE_RECOVERY_SCHEMA
            or any(not isinstance(selected[k], str) or len(selected[k]) != 64
                   or any(c not in '0123456789abcdef' for c in selected[k]) for k in sha_fields)
            or selected['sceneId'] != source['sceneId'] or selected['actionId'] != source['action']['id']
            or selected['sourceSha256'] != digest(classroom) or classroom.get('id') != classroom_id
            or len(matching) != 1 or matching[0][0].get('order') != source['sceneOrder']
            or matching[0][1] != source['action']
            or selected['failedRequestId'] != original_id or selected['planSha256'] != digest(plan)
            or selected['audioSha256'] != sha(facts['audio'])
            or selected['failedJobSha256'] != sha(job_raw) or selected['failedCacheSha256'] != sha(cache_raw)
            or envelope['recoveryRequestId'] != failed_recovery_id(original_id, facts['pcmKey'])):
        fail('Failed ASR recovery selection or immutable byte fences differ')
    required_job = {'schemaVersion', 'kind', 'requestId', 'requestSha256', 'classroomId',
        'classroomContentSha256', 'subject', 'teacherProfileId', 'teacherProfileVersion',
        'teacherProfileSha256', 'teacherGender', 'sceneId', 'sceneOrder', 'actionId',
        'narrationSegmentId', 'ttsRequestId', 'audioSha256', 'languageCode', 'state',
        'providerId', 'modelId', 'fallbackUsed', 'providerAttemptedAt', 'createdAt', 'updatedAt',
        'providerPronunciation', 'providerAsrBodySha256', 'safeErrorCode', 'completedAt'}
    fields(job, required_job)
    if (job['schemaVersion'] != 'mira.openmaic.formal-audio-job.v1' or job['kind'] != 'asr'
            or any(job[k] != v for k, v in request.items())
            or job['state'] != 'failed' or job['safeErrorCode'] != 'provider_rejected'
            or job['providerId'] != 'qwen-asr' or job['modelId'] != 'qwen3-asr-flash'
            or job['fallbackUsed'] is not False or job['languageCode'] != 'zh-CN'
            or job['providerPronunciation'] != facts['receipt']['providerPronunciation']
            or job['providerAsrBodySha256'] != sha(asr_body(facts['audio']))
            or job['requestSha256'] != digest({'logicalRequest': request,
                'providerPronunciation': job['providerPronunciation']})
            or any(not isinstance(job[k], str) or not job[k] for k in
                   ('providerAttemptedAt', 'createdAt', 'updatedAt', 'completedAt'))):
        fail('Recovery requires the exact terminal provider-rejected original ASR job')
    fields(cache, {'sceneId', 'actionId', 'ttsRequestId', 'audioSha256', 'textSha256',
        'text', 'transcript', 'durationMs', 'similarityBps', 'asr'})
    normalization = facts['receipt']['audioNormalization']
    duration_ms = normalization['pcmByteLength'] * 1000 // (
        normalization['sampleRate'] * normalization['channels'] * normalization['bitsPerSample'] // 8)
    expected_response = {'requestId': original_id, 'status': 'failed', 'transcript': None,
        'transcriptSha256': None, 'completionUsable': False}
    if (cache['sceneId'] != source['sceneId'] or cache['actionId'] != source['action']['id']
            or cache['ttsRequestId'] != source['action']['audioId'] or cache['audioSha256'] != sha(facts['audio'])
            or cache['text'] != facts['text'] or cache['textSha256'] != sha(facts['text'].encode())
            or cache['transcript'] is not None or cache['similarityBps'] != 0
            or type(cache['durationMs']) is not int or cache['durationMs'] != duration_ms
            or cache['asr'] != expected_response):
        fail('Original failed ASR cache is not an unchanged unusable result')
    return {'failedRequestId': original_id, 'failedJob': job, 'failedJobRaw': job_raw,
        'failedCacheRaw': cache_raw, 'recoveryRequestId': envelope['recoveryRequestId']}


def build_failed_recovery_origin(*, source, plan, classroom, selection, failed_job_raw, failed_cache_raw):
    fields(selection, FAILED_RECOVERY_SELECTION_FIELDS)
    if selection['sourceSha256'] != digest(classroom): fail('Failed recovery source fence differs')
    result = {'schemaVersion': FAILED_RECOVERY_ORIGIN_SCHEMA, 'kind': 'formal',
        'source': deepcopy(source), 'plan': deepcopy(plan), 'classroomId': classroom['id'], 'attempts': [],
        'failureRecovery': {'schemaVersion': FAILURE_RECOVERY_SCHEMA, 'selection': deepcopy(selection),
            'classroomBase64': base64.b64encode(canonical(classroom).encode()).decode(),
            'failedJobBase64': base64.b64encode(failed_job_raw).decode(),
            'failedCacheBase64': base64.b64encode(failed_cache_raw).decode(),
            'recoveryRequestId': failed_recovery_id(selection['failedRequestId'], target_evidence(source, plan)['pcmKey'])}}
    verify_origin(result)
    return result


def verify_probe_protocol(package, plan):
    """Reuse the existing composition verifier with its ORIGINAL unbound record.

    This is a protocol-only function. No preview/core/review pass is invented.
    The original unbound record is kept as bytes, not converted into an approval.
    """
    from services.textbook_pronunciation_probe_composite import verify_files, evidence_names, parse
    fields(package, {'files'})
    if set(package['files']) != evidence_names(): fail('Incomplete original composition archive')
    files = {name: decoded(raw) for name, raw in package['files'].items()}
    protocol = parse(files['evidence/operator-probe-review.json'])
    if (protocol.get('previewBound') is not False or protocol.get('formalUseAllowed') is not False
            or protocol.get('humanListeningVerified') is not False
            or protocol.get('perceptualToneVerified') is not False):
        fail('Expected the original unbound protocol evidence, not a fabricated initialization review')
    verify_files(files, protocol, plan['binding'], policy_for_plan(plan))
    return files


def probe_source(origin, files):
    from services.textbook_pronunciation_probe_composite import SLOTS, parse
    label = origin['label']
    if label not in SLOTS: fail('Unregistered original probe label')
    old, old_label, text, _ = SLOTS[label]
    base = f'evidence/origins/{old}/{old_label}/'
    receipt = parse(files[base + 'receipt.json'])
    body = parse(files[base + 'request.json'])
    return {'text': text, 'body': body, 'audio': files[base + 'playback.wav'], 'receipt': receipt,
            'pcmKey': pcm_key(receipt), 'originPlanSha256': sha(files[f'evidence/origins/{old}/plan.json']),
            'receiptFileSha256': sha(files[base + 'receipt.json']), 'label': old_label}


def verify_probe_asr(attempt, facts):
    from services.learning_media_materialization_service import asr_similarity_bps
    from services.textbook_pronunciation_probe_composite import SLOTS, timestamp
    fields(attempt, {'kind', 'role', 'files'})
    if attempt['kind'] != 'probe' or set(attempt['files']) != {'request.json', 'intent.json', 'receipt.json', 'provider-response.json'}:
        fail('Incomplete original probe ASR archive')
    records = {n: parsed(b) for n, b in attempt['files'].items()}
    req_raw, req = records['request.json']; _, intent = records['intent.json']
    _, receipt = records['receipt.json']; response_raw, response = records['provider-response.json']
    try:
        transcript = response['output']['choices'][0]['message']['content'][0]['text']
    except (KeyError, TypeError, IndexError): fail('Original provider response has no complete transcript')
    if not isinstance(transcript, str) or not transcript.strip(): fail('Original transcript is empty or invalid')
    expected_body = json.loads(asr_body(facts['audio']))
    score = asr_similarity_bps(facts['text'], transcript)
    slot = SLOTS.get(facts['label'])
    # The registered pre-registration alias archive predates this duplicated
    # ASR receipt field. Its verified composition still binds the exact original
    # plan, complete provider body and TTS receipt bytes. Never synthesize a field
    # in that original receipt, or extend this exception to the six v1 probes.
    legacy_alias_ssml = (
        'ssmlSha256' not in receipt
        and slot is not None and slot[0] == 'garden3-alias-preregistration'
        and slot[1] == facts['label'] == 'ca-boli-natural-alias'
        and slot[2] == facts['text'] and slot[3] is None
        and facts['receipt'].get('registeredPolicyMatch') is False
        and all(key not in item for item in (facts['receipt'], receipt, intent)
                for key in ('policyVersion', 'policyCanonicalSha256'))
        and facts['body'] == provider_body(facts['text'], policy_version=GARDEN3_V2_POLICY_VERSION)
    )
    if (req != expected_body or not isinstance(transcript, str) or not transcript.strip()
            or intent.get('schemaVersion') != 'mira.operator.probe-asr-intent.v1'
            or receipt.get('schemaVersion') != 'mira.operator.probe-asr-receipt.v1'
            or receipt.get('status') != 'succeeded' or receipt.get('postAttempts') != 1
            or receipt.get('transcript') != transcript or receipt.get('transcriptSha256') != sha(transcript.encode())
            or receipt.get('providerResponseSha256') != sha(response_raw)
            or receipt.get('providerRequestId') != response.get('request_id')
            or receipt.get('usage') != response.get('usage') or receipt.get('requestBytes') != len(req_raw)
            or receipt.get('text') != facts['text'] or receipt.get('textSha256') != sha(facts['text'].encode())
            or receipt.get('ttsReceiptSha256') != facts['receiptFileSha256']
            or (not legacy_alias_ssml
                and receipt.get('ssmlSha256') != sha(facts['body']['input']['text'].encode()))
            or receipt.get('pcmSha256') != facts['receipt']['pcmSha256']
            or receipt.get('comparison') != {'method': 'original-text-literal-levenshtein',
                'passed': score >= 8500, 'similarityBps': score, 'thresholdBps': 8500}
            or response['output']['choices'][0].get('finish_reason') != 'stop'
            or timestamp(intent.get('createdAt')) > timestamp(receipt.get('completedAt'))):
        fail('Original probe ASR body, response, transcript or TTS bytes differ')
    for item in (receipt, intent):
        if (item.get('requestSha256') != sha(req_raw) or item.get('audioSha256') != sha(facts['audio'])
                or item.get('planSha256') != facts['originPlanSha256'] or item.get('label') != facts['label']
                or item.get('provider') != 'qwen-asr' or item.get('model') != 'qwen3-asr-flash'
                or item.get('formalUseAllowed') is not False or item.get('humanListeningVerified') is not False
                or item.get('perceptualToneVerified') is not False or item.get('expectedTextSentToProvider') is not False):
            fail('Original probe request/receipt identity cannot be relabelled')
    if (intent.get('requestId') != receipt.get('requestId') or not receipt.get('requestId')
            or intent.get('maxPostAttempts') != 1
            or intent.get('asrPlanSha256') != receipt.get('asrPlanSha256')):
        fail('Original probe dispatch identity differs')
    old = facts['receipt']
    if 'policyVersion' in old:
        if any(receipt.get(k) != old[k] for k in ('policyVersion', 'policyCanonicalSha256')):
            fail('Historical probe policy must remain historical')
    elif 'policyVersion' in receipt:
        fail('Pre-registration alias must not acquire a policy version')
    return {'requestId': receipt['requestId'], 'transcript': transcript,
            'receipt': receipt, 'receiptSha256': sha(records['receipt.json'][0]), 'status': 'succeeded'}


def _verify_origin_v1(origin, *, probe_files=None):
    common = {'schemaVersion', 'kind', 'attempts'}
    recovery = isinstance(origin, dict) and origin.get('schemaVersion') == FAILED_RECOVERY_ORIGIN_SCHEMA
    if recovery: common.add('failureRecovery')
    fields(origin, common | ({'label'} if origin.get('kind') == 'probe-composition' else {'source', 'plan', 'classroomId'}))
    if (origin['schemaVersion'] not in (ORIGIN_SCHEMA, FAILED_RECOVERY_ORIGIN_SCHEMA)
            or not isinstance(origin['attempts'], list)
            or recovery and (origin['kind'] != 'formal' or len(origin['attempts']) > 1)):
        fail('Invalid ASR origin schema or failed-recovery attempt budget')
    if origin['kind'] == 'probe-composition':
        if probe_files is None: fail('Original probe composition required')
        facts = probe_source(origin, probe_files)
    elif origin['kind'] == 'formal':
        if not isinstance(origin['classroomId'], str) or not origin['classroomId']: fail('Missing original classroom identity')
        facts = target_evidence(origin['source'], origin['plan'])
    else: fail('Unknown origin kind')
    failed = verify_failure_recovery(origin['failureRecovery'], source=origin['source'],
        plan=origin['plan'], classroom_id=origin['classroomId']) if recovery else None
    results, seen = [], set()
    for index, attempt in enumerate(origin['attempts']):
        if not isinstance(attempt, dict) or attempt.get('role') != ('routine' if index == 0 else 'recheck' if index == 1 else 'historical-extra'):
            fail('All attempts, including historical excess, must retain chronological roles')
        if attempt.get('kind') == 'probe':
            if origin['kind'] != 'probe-composition': fail('Probe response cannot impersonate formal ASR')
            result = verify_probe_asr(attempt, facts)
        else:
            fields(attempt, {'kind', 'role', 'request', 'response', 'source', 'plan', 'classroomId'})
            if attempt['kind'] != 'formal': fail('Unknown ASR attempt')
            if index == 0 and (origin['kind'] != 'formal' or any(
                    attempt[k] != origin[k] for k in ('source', 'plan', 'classroomId'))):
                fail('First formal recognition must retain its original complete source identity')
            own = target_evidence(attempt['source'], attempt['plan'])
            if any(own[k] != facts[k] for k in ('text', 'body', 'audio', 'pcmKey')):
                fail('Formal ASR source does not equal the original text/body/WAV/PCM')
            response = attempt['response']; request = attempt['request']
            first_id = asr_request_id(attempt['plan'], attempt['source']['action']['audioId'], sha(own['audio']))
            if failed is not None: first_id = failed['recoveryRequestId']
            allowed = {first_id} if index == 0 else {shared_recheck_id(facts['pcmKey'])}
            if index == 1 and results:
                from content.textbook_audio_recheck import request_id
                allowed.add(request_id(results[0]['requestId'], sha(own['audio'])))
            if (not isinstance(response, dict) or not isinstance(request, dict)
                    or request.get('requestId') not in allowed
                    or request != formal_request(attempt['source'], attempt['plan'], attempt['classroomId'], request['requestId'])):
                fail('ASR request is not the original routine or bounded recheck')
            validate_formal_receipt(response, own['text'], policy_version=own['policy']['policyVersion'])
            transcript = response.get('transcript')
            if (response.get('requestId') != request['requestId'] or response.get('status') != 'succeeded'
                    or response.get('completionUsable') is not True or not isinstance(transcript, str)
                    or not transcript.strip() or len(transcript) > 8000
                    or response.get('transcriptSha256') != sha(transcript.encode())
                    or response.get('providerAsrBodySha256') != sha(asr_body(own['audio']))):
                fail('Original formal ASR response is incomplete or not this no-hint WAV')
            result = {'requestId': response['requestId'], 'transcript': transcript, 'receipt': response,
                      'receiptSha256': digest(response), 'status': 'succeeded'}
        if result['requestId'] in seen: fail('Duplicate request cannot count as independent recognition')
        seen.add(result['requestId']); results.append(result)
    return {**facts, 'attempts': results, **({'failureRecovery': failed} if failed is not None else {})}


def historical_excess_investigation(origins, *, probe_files=None):
    """Seal an explicit zero-call consensus over complete original routines.

    Each child remains an independently valid v1 formal origin.  The outer
    consensus never relabels a historical routine as a recheck and never makes
    a new provider request identity.
    """
    if not isinstance(origins, list) or len(origins) < 3:
        fail('Historical excess consensus requires at least three complete original routines')
    verified = []
    for origin in origins:
        if (not isinstance(origin, dict) or origin.get('schemaVersion') != ORIGIN_SCHEMA
                or origin.get('kind') != 'formal'):
            fail('Historical excess children must be complete formal v1 origins')
        facts = _verify_origin_v1(origin, probe_files=probe_files)
        if (len(facts['attempts']) != 1 or len(origin.get('attempts', [])) != 1
                or origin['attempts'][0].get('kind') != 'formal'
                or origin['attempts'][0].get('role') != 'routine'):
            fail('Historical excess children must retain one original routine each')
        verified.append(facts)
    first = verified[0]
    for facts in verified[1:]:
        if any(facts[key] != first[key] for key in ('text', 'body', 'audio', 'pcmKey')):
            fail('Historical excess routines must have identical text, provider body, WAV and PCM')
    request_ids = [facts['attempts'][0]['requestId'] for facts in verified]
    if len(set(request_ids)) != len(request_ids):
        fail('Historical excess routines must retain distinct request identities')
    for origin, facts in zip(origins, verified):
        transcript = facts['attempts'][0]['transcript']
        comparison = compare_transcript(origin['plan'], facts['text'], transcript)
        if (transcript != facts['text'] or comparison['passed'] is not True
                or comparison['similarityBps'] != 10000
                or facts['attempts'][0]['status'] != 'succeeded'):
            fail('Historical excess consensus requires every original transcript to be literal exact')
    base = {'schemaVersion': INVESTIGATION_SCHEMA, 'disposition': EXCESS_ACCEPTANCE,
        'requestIds': request_ids, 'originSha256s': [digest(origin) for origin in origins],
        'attemptCount': len(origins), 'textSha256': sha(first['text'].encode()),
        'providerBodySha256': digest(first['body']), 'audioSha256': sha(first['audio']),
        'pcmSha256': first['receipt']['pcmSha256'], 'pcmKey': first['pcmKey'],
        'transcriptSha256': sha(first['text'].encode()), 'providerCallsAllowed': False}
    return {**base, 'sha256': digest(base)}


def build_historical_excess_consensus(origins, *, probe_files=None):
    result = {'schemaVersion': CONSENSUS_ORIGIN_SCHEMA, 'kind': 'formal-excess-consensus',
        'origins': deepcopy(origins),
        'investigation': historical_excess_investigation(origins, probe_files=probe_files)}
    verify_origin(result, probe_files=probe_files)
    return result


def _verify_historical_excess_consensus(origin, *, probe_files=None):
    fields(origin, {'schemaVersion', 'kind', 'origins', 'investigation'})
    if (origin['schemaVersion'] != CONSENSUS_ORIGIN_SCHEMA
            or origin['kind'] != 'formal-excess-consensus'):
        fail('Invalid historical excess consensus origin')
    expected = historical_excess_investigation(origin['origins'], probe_files=probe_files)
    if origin['investigation'] != expected:
        fail('Historical excess investigation is missing, changed or unsealed')
    verified = [_verify_origin_v1(item, probe_files=probe_files) for item in origin['origins']]
    return {**verified[0], 'attempts': [item['attempts'][0] for item in verified],
        'historicalExcessConsensus': deepcopy(expected)}


def verify_origin(origin, *, probe_files=None):
    if isinstance(origin, dict) and origin.get('schemaVersion') == CONSENSUS_ORIGIN_SCHEMA:
        return _verify_historical_excess_consensus(origin, probe_files=probe_files)
    return _verify_origin_v1(origin, probe_files=probe_files)


def verify_origin_library(library, plan):
    fields(library, {'schemaVersion', 'origins', 'probeProtocol'})
    version = library['schemaVersion']
    if version not in (LIBRARY_SCHEMA_V1, LIBRARY_SCHEMA_V2) or not isinstance(library['origins'], list):
        fail('Invalid explicit original ASR library')
    files = verify_probe_protocol(library['probeProtocol'], plan) if library['probeProtocol'] else None
    for origin in library['origins']:
        if (version == LIBRARY_SCHEMA_V1 and isinstance(origin, dict)
                and origin.get('schemaVersion') in (CONSENSUS_ORIGIN_SCHEMA, FAILED_RECOVERY_ORIGIN_SCHEMA)):
            fail('Historical excess consensus or failed recovery requires the v2 library contract')
        verify_origin(origin, probe_files=files)
    return files


def alias_exact(text, transcript, policy):
    from content.textbook_pinyin_alias_alignment import TEXT, ALIAS, SSML
    if (policy['policyVersion'] != GARDEN3_V2_POLICY_VERSION or text != TEXT
            or provider_body(text, policy_version=policy['policyVersion'])['input']['text'] != SSML): return False
    if (any(c not in ALIAS and not c.isspace() and not unicodedata.category(c).startswith('P') for c in transcript)
            or any(unicodedata.category(c).startswith('C') and c not in '\t\n\r' for c in transcript)): return False
    return ''.join(c for c in transcript if not c.isspace() and not unicodedata.category(c).startswith('P')) == ALIAS


def acceptance(entry, facts, plan, policy):
    """Provenance alone never waives low score. No new pronunciation assertion."""
    attempts = facts['attempts']
    first = compare_transcript(plan, entry['text'], attempts[0]['transcript'])
    consensus = facts.get('historicalExcessConsensus')
    if consensus is not None:
        if (consensus.get('disposition') != EXCESS_ACCEPTANCE
                or consensus.get('requestIds') != [item['requestId'] for item in attempts]
                or any(item['transcript'] != entry['text'] for item in attempts)):
            fail('Historical excess acceptance differs from its sealed literal consensus')
        return EXCESS_ACCEPTANCE
    if len(attempts) > 2: fail('Historical excess retained; this group needs explicit investigation')
    if alias_exact(entry['text'], attempts[0]['transcript'], policy):
        if any(not alias_exact(entry['text'], x['transcript'], policy) for x in attempts):
            fail('A conflicting alias recheck cannot be discarded')
        return 'exact-natural-alias-content'
    if len(attempts) == 1:
        if first['passed']: return 'literal-asr'
        fail('Literal failure requires an independent same-PCM recheck')
    second = compare_transcript(plan, entry['text'], attempts[1]['transcript'])
    if second['passed']: return 'independent-asr-recheck'
    if first['passed']: fail('A failed concern recheck cannot be discarded for the earlier score')
    from content.textbook_pinyin_carrier_equivalence import exact_representation
    exact_representation(entry['text'], attempts[0]['transcript'], policy)
    exact_representation(entry['text'], attempts[1]['transcript'], policy)
    return 'exact-carrier-orthography-both-asr'


def build_audit(*, plan, classroom, targets, origins, probe_protocol=None):
    result = {'schemaVersion': SCHEMA, 'previewKey': plan['previewKey'], 'sourceClassroomId': classroom['id'],
        'sourceSha256': digest(classroom), 'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'contract': audit_contract_identity(plan), 'probeProtocol': deepcopy(probe_protocol),
        'origins': deepcopy(origins), 'segments': [], 'evidenceLimit': LIMIT,
        'humanListeningVerified': False, 'phoneticAccuracyVerified': False, 'perceptualToneVerified': False}
    files = verify_probe_protocol(probe_protocol, plan) if probe_protocol is not None else None
    verified = {digest(o): verify_origin(o, probe_files=files) for o in origins}
    for item in targets:
        fields(item, {'target', 'originSha256'})
        source = item['target']; own = target_evidence(source, plan); origin = verified.get(item['originSha256'])
        if origin is None or not origin['attempts']: fail('Missing succeeded original recognition')
        if any(own[k] != origin[k] for k in ('text', 'body', 'audio', 'pcmKey')):
            fail('Reused origin must have exact text, complete provider body, WAV and PCM')
        first = origin['attempts'][0]; comparison = compare_transcript(plan, own['text'], first['transcript'])
        result['segments'].append({'sceneId': source['sceneId'], 'actionId': source['action']['id'],
            'text': own['text'], 'textSha256': sha(own['text'].encode()), 'ttsRequestId': source['action']['audioId'],
            'audioSha256': sha(own['audio']), 'pcmSha256': own['receipt']['pcmSha256'],
            'transcript': first['transcript'], 'asr': deepcopy(first['receipt']),
            'comparison': comparison, 'similarityBps': comparison['similarityBps'],
            'originSha256': item['originSha256'], 'target': deepcopy(source)})
    result['passed'] = bool(result['segments']) and all(e['comparison']['passed'] for e in result['segments'])
    return seal(result)


def validate_audit(audit, *, plan, classroom, expected_source_sha256, expected_source_classroom_id=None):
    contract = resolve_audio_contract(plan)
    if contract['comparisonPolicy'].get('minimumSimilarityBps') != 8500 or contract['comparisonPolicy'].get('version') != 'literal-v1':
        fail('Original literal comparison contract must remain unchanged')
    if expected_source_classroom_id is None:
        if digest(classroom) != expected_source_sha256: fail('Full current source bytes changed')
        expected_source_classroom_id = classroom['id']
    if not isinstance(audit, dict) or audit.get('schemaVersion') != SCHEMA: fail('Wrong origin audit schema')
    original = {**classroom, 'id': expected_source_classroom_id}
    scenes = {s['id']: s for s in original['scenes']}
    actions = {(s['id'], a['id']): a for s in original['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech'}
    if len(scenes) != len(original['scenes']) or len(actions) != sum(a.get('type') == 'speech' for s in original['scenes'] for a in s.get('actions', [])):
        fail('Duplicate current source identity')
    targets, seen = [], set()
    for entry in audit.get('segments', []):
        if not isinstance(entry, dict): fail('Invalid origin audit segment')
        key = entry.get('sceneId'), entry.get('actionId'); target = entry.get('target', {})
        if key not in actions or key in seen: fail('Origin audit target missing, extra or duplicate')
        # Audio URLs are relocated by publication. All identity/text/metadata and
        # every independently validated TTS/WAV remain exact.
        a, b = deepcopy(target.get('action', {})), deepcopy(actions[key])
        a.pop('audioUrl', None); b.pop('audioUrl', None)
        if a != b or target.get('sceneOrder') != scenes[key[0]].get('order', 0): fail('Target speech differs from actual current classroom')
        seen.add(key); targets.append({'target': target, 'originSha256': entry.get('originSha256')})
    if not seen or seen != set(actions): fail('Every actual current speech requires independent target evidence')
    expected = build_audit(plan=plan, classroom=original, targets=targets, origins=audit.get('origins', []), probe_protocol=audit.get('probeProtocol'))
    expected['sourceSha256'] = expected_source_sha256; seal(expected)
    if audit != expected: fail('Origin audit, raw scores or identities changed')
    origin_ids = [digest(o) for o in audit['origins']]
    if len(set(origin_ids)) != len(origin_ids) or set(origin_ids) != {e['originSha256'] for e in audit['segments']}:
        fail('Missing, duplicate or unused ASR origin')
    files = verify_probe_protocol(audit['probeProtocol'], plan) if audit['probeProtocol'] is not None else None
    origins = {digest(o): verify_origin(o, probe_files=files) for o in audit['origins']}
    # Same PCM may not be split across origins to evade the two-attempt budget.
    pcm = [o['pcmKey'] for o in origins.values()]
    if len(set(pcm)) != len(pcm): fail('One real PCM must have one complete origin history')
    return {(e['sceneId'], e['actionId']): (deepcopy(e), origins[e['originSha256']]) for e in audit['segments']}
