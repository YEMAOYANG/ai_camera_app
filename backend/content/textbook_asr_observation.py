"""Same-WAV ASR observations, never an exact-source or pronunciation claim.

Original formal routines retain their own source, request plan and raw records.
An outer target may compare their transcript only after proving complete WAV
byte equality as well as PCM/format equality. This lane has no provider API.
"""
import base64
from copy import deepcopy
import json

from content.textbook_catalog import digest
from content.textbook_audio_recheck import provider_body as asr_body, seal
from content.textbook_asr_source_reuse import (
    ORIGIN_SCHEMA, FAILED_RECOVERY_ORIGIN_SCHEMA, formal_request, sha,
    target_evidence, verify_origin,
)
from content.textbook_preview_audio_contract import audit_contract_identity, compare_transcript, resolve_audio_contract
from content.textbook_pinyin_pronunciation import pronunciation_identity
from core.errors import ApiError

SCHEMA = 'mira.textbook.audio-audit.v4-same-wav-observations'
OBSERVATION_SCHEMA = 'mira.textbook.asr-observation.v1'
LIMIT = ('Original routines and raw records remain original. Target references prove identical complete WAV '
         'and PCM/format, not identical original text/body/source. Cross-source, conflicting or low literal '
         'observations and historical excess remain pending explicit acceptance for this lesson. '
         'No aliases, new provider calls, human listening or phonetic/tone accuracy are established.')
FALSE = ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified')


def fail(message):
    raise ApiError('textbook_asr_observation_invalid', message, 409)


def fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names):
        fail('Observation fields are incomplete or contain unknown fields')


def raw_json(value):
    try:
        raw = base64.b64decode(value, validate=True)
        def pairs(items):
            result = {}
            for key, item in items:
                if key in result: raise ValueError('duplicate key')
                result[key] = item
            return result
        record = json.loads(raw, object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(record, dict): raise ValueError('object required')
        return raw, record
    except (ValueError, TypeError, UnicodeError):
        fail('Original observation JSON bytes are invalid')


def verify_observation(observation):
    fields(observation, {'schemaVersion', 'origin', 'rawEvidence'})
    if observation['schemaVersion'] != OBSERVATION_SCHEMA:
        fail('Unknown observation schema')
    origin = observation['origin']
    if (not isinstance(origin, dict) or origin.get('schemaVersion') not in
            (ORIGIN_SCHEMA, FAILED_RECOVERY_ORIGIN_SCHEMA) or origin.get('kind') != 'formal'
            or not isinstance(origin.get('attempts'), list) or len(origin['attempts']) != 1):
        fail('Each observation must retain one original successful formal routine')
    facts = verify_origin(origin)
    attempt = origin['attempts'][0]
    if attempt.get('kind') != 'formal' or attempt.get('role') != 'routine':
        fail('An original routine may not be relabelled a recheck or consensus')
    evidence = observation['rawEvidence']
    fields(evidence, {'jobBase64', 'ttsJobBase64', 'transcriptBase64', 'receiptBase64', 'receiptContainer'})
    job_raw, job = raw_json(evidence['jobBase64'])
    tts_raw, tts_job = raw_json(evidence['ttsJobBase64'])
    transcript_raw, transcript = raw_json(evidence['transcriptBase64'])
    receipt_raw, container = raw_json(evidence['receiptBase64'])
    response = attempt['response']; request = attempt['request']
    receipt = facts['receipt']; source = origin['source']
    teacher = facts['effectivePlan']['teacher']; profile = teacher['teacherProfile']
    tts_request = {'requestId': source['action']['audioId'], 'classroomId': origin['classroomId'],
        'classroomContentSha256': receipt.get('classroomContentSha256', origin['plan']['classroomSha256']),
        'subject': facts['effectivePlan']['subject'], 'teacherProfileId': profile['id'],
        'teacherProfileVersion': profile['version'], 'teacherProfileSha256': profile['contentHash'],
        'teacherGender': teacher['teacherGender'], 'sceneId': source['sceneId'],
        'sceneOrder': source['sceneOrder'], 'actionId': source['action']['id'],
        'narrationSegmentId': source['action']['id'], 'text': facts['text'], 'textSha256': sha(facts['text'].encode())}
    tts_request['pronunciationProfile'] = pronunciation_identity(facts['text'], policy_version=facts['policy']['policyVersion'])
    native_receipt_fields = ('requestId', 'providerId', 'modelId', 'voiceId', 'providerPronunciation',
        'audioSha256', 'pcmSha256', 'providerAudioSha256', 'audioNormalization', 'mimeType',
        'providerRequestId', 'providerUsage', 'budgetMeasurement')
    if (tts_job.get('schemaVersion') != 'mira.openmaic.formal-audio-job.v1'
            or tts_job.get('kind') != 'tts' or tts_job.get('state') != 'succeeded'
            or any(k not in tts_job or tts_job[k] != receipt.get(k) for k in native_receipt_fields)
            or any(k not in tts_job or tts_job[k] != v for k, v in tts_request.items() if k not in ('text', 'pronunciationProfile'))
            or type(tts_job.get('teacherProfileVersion')) is not int or type(tts_job.get('sceneOrder')) is not int
            or tts_job.get('requestSha256') != digest({'logicalRequest': tts_request,
                'providerPronunciation': receipt['providerPronunciation']})
            or tts_job.get('voiceGender') != teacher['voiceGender']
            or tts_job.get('languageCode') != 'zh-CN'
            or tts_job.get('classroomId') != origin['classroomId']
            or tts_job.get('classroomContentSha256') != receipt.get('classroomContentSha256', origin['plan']['classroomSha256'])
            or tts_job.get('sceneId') != source['sceneId'] or tts_job.get('sceneOrder') != source['sceneOrder']
            or tts_job.get('actionId') != source['action']['id']
            or tts_job.get('narrationSegmentId') != source['action']['id']
            or tts_job.get('textSha256') != sha(facts['text'].encode())
            or tts_job.get('fallbackUsed') is not False):
        fail('Original TTS receipt, source or SSML identity differs from its own Native job')
    normalization = facts['receipt']['audioNormalization']
    duration = normalization['pcmByteLength'] * 1000 // (
        normalization['sampleRate'] * normalization['channels'] * normalization['bitsPerSample'] // 8)
    if evidence['receiptContainer'] == 'routine-cache':
        from services.learning_media_materialization_service import asr_similarity_bps
        fields(container, {'sceneId', 'actionId', 'ttsRequestId', 'audioSha256', 'textSha256',
            'text', 'transcript', 'durationMs', 'similarityBps', 'asr'})
        expected = {'sceneId': origin['source']['sceneId'], 'actionId': origin['source']['action']['id'],
            'ttsRequestId': origin['source']['action']['audioId'], 'audioSha256': sha(facts['audio']),
            'textSha256': sha(facts['text'].encode()), 'text': facts['text'],
            'transcript': response['transcript'], 'durationMs': duration,
            'similarityBps': asr_similarity_bps(facts['text'], response['transcript']),
            'asr': response}
        if (container != expected or type(container['durationMs']) is not int
                or type(container['similarityBps']) is not int):
            fail('Original routine cache differs from its own source or response')
    elif evidence['receiptContainer'] == 'transport-response':
        if container != response: fail('Original transport response differs from the observation')
    elif evidence['receiptContainer'] == 'native-response':
        # The collector stores the real Native HTTP object before its existing
        # client adapter returns a smaller receipt. Preserve that object intact.
        fields(container, set(job) | {'success', 'done', 'transcript'})
        if (container.get('success') is not True or container.get('done') is not True
                or container != {**job, 'success': True, 'done': True, 'transcript': response['transcript']}):
            fail('Original Native HTTP response differs from its durable job or transcript')
    else:
        fail('Unknown original response container')
    required_job = {'schemaVersion', 'kind', 'requestId', 'requestSha256', 'classroomId',
        'classroomContentSha256', 'subject', 'teacherProfileId', 'teacherProfileVersion',
        'teacherProfileSha256', 'teacherGender', 'sceneId', 'sceneOrder', 'actionId',
        'narrationSegmentId', 'ttsRequestId', 'audioSha256', 'languageCode', 'state',
        'providerId', 'modelId', 'fallbackUsed', 'providerAttemptedAt', 'createdAt', 'updatedAt',
        'providerPronunciation', 'providerAsrBodySha256', 'providerCompletedAt', 'transcriptSha256', 'completedAt'}
    fields(job, required_job)
    if (job['schemaVersion'] != 'mira.openmaic.formal-audio-job.v1' or job['kind'] != 'asr'
            or type(job['sceneOrder']) is not int or type(job['teacherProfileVersion']) is not int
            or any(job[k] != v for k, v in request.items()) or job['state'] != 'succeeded'
            or job['providerId'] != 'qwen-asr' or job['modelId'] != 'qwen3-asr-flash'
            or job['fallbackUsed'] is not False or job['languageCode'] != 'zh-CN'
            or job['providerPronunciation'] != facts['receipt']['providerPronunciation']
            or job['providerAsrBodySha256'] != sha(asr_body(facts['audio']))
            or job['providerAsrBodySha256'] != response['providerAsrBodySha256']
            or job['transcriptSha256'] != response['transcriptSha256']
            or job['requestSha256'] != digest({'logicalRequest': request,
                'providerPronunciation': job['providerPronunciation']})
            or any(not isinstance(job[k], str) or not job[k] for k in
                ('providerAttemptedAt', 'createdAt', 'updatedAt', 'providerCompletedAt', 'completedAt'))):
        fail('Observation does not match its original succeeded no-hint ASR job')
    fields(transcript, {'requestId', 'audioSha256', 'transcript', 'transcriptSha256'})
    if transcript != {k: response[k] for k in ('requestId', 'transcript', 'transcriptSha256')} | {
            'audioSha256': sha(facts['audio'])}:
        fail('Original durable transcript differs from its succeeded observation')
    return {**facts, 'job': job, 'jobRaw': job_raw, 'ttsJobRaw': tts_raw, 'transcriptRaw': transcript_raw,
        'receiptRaw': receipt_raw, 'origin': origin, 'requestId': response['requestId'],
        'response': response, 'createdAt': job['createdAt']}


def _history(verified):
    groups = {}
    for oid, facts in verified.items():
        group = groups.setdefault(facts['pcmKey'], {'requestIds': set(), 'observations': []})
        if facts['requestId'] in group['requestIds']: fail('Duplicate original ASR request')
        group['requestIds'].add(facts['requestId']); group['observations'].append(oid)
        recovery = facts.get('failureRecovery')
        if recovery is not None:
            if recovery['failedRequestId'] in group['requestIds']: fail('Duplicate original failed routine')
            group['requestIds'].add(recovery['failedRequestId'])
    result = []
    for key, group in sorted(groups.items()):
        result.append({'pcmKey': key, 'requestIds': sorted(group['requestIds']),
            'observationSha256s': sorted(group['observations']), 'attemptCount': len(group['requestIds']),
            'historicalExcess': len(group['requestIds']) > 2, 'noFurtherProviderCalls': True})
    return result


def build_observation_audit(*, plan, classroom, targets, observations):
    contract = resolve_audio_contract(plan)
    if (contract['comparisonPolicy']['version'] != 'literal-v1'
            or contract['comparisonPolicy']['minimumSimilarityBps'] != 8500):
        fail('The original literal comparison contract must remain unchanged')
    if not isinstance(observations, list) or not observations: fail('Succeeded original observations required')
    verified = {digest(o): verify_observation(o) for o in observations}
    if len(verified) != len(observations): fail('Duplicate observation')
    histories = _history(verified); history = {h['pcmKey']: h for h in histories}
    segments, used, seen = [], set(), set()
    for source in targets:
        own = target_evidence(source, plan); key = source['sceneId'], source['action']['id']
        if key in seen: fail('Duplicate target')
        seen.add(key)
        matches = sorted(((oid, f) for oid, f in verified.items()
            if f['audio'] == own['audio'] and f['pcmKey'] == own['pcmKey']),
            key=lambda item: (item[1]['createdAt'], item[1]['requestId']))
        if not matches: fail('Every target needs a succeeded identical complete WAV and PCM/format observation')
        reasons, comparisons = set(), []
        for oid, facts in matches:
            used.add(oid); origin = facts['origin']; original = origin['source']
            same = (origin['classroomId'] == classroom['id'] and original == source
                and origin['plan'] == plan)
            text_body = own['text'] == facts['text'] and own['body'] == facts['body']
            comparison = compare_transcript(plan, own['text'], facts['response']['transcript'])
            if not same: reasons.add('cross-source-observation')
            if not text_body: reasons.add('different-original-text-or-tts-body')
            if not comparison['passed']: reasons.add('literal-comparison-unresolved')
            comparisons.append({'observationSha256': oid, 'originalRequestId': facts['requestId'],
                'relationship': 'same-complete-wav-observation', 'sameOriginalSource': same,
                'textAndBodyMatch': text_body, 'comparison': comparison})
        if history[own['pcmKey']]['historicalExcess']: reasons.add('historical-excess-routines-retained')
        primary_id, primary = matches[0]; comparison = comparisons[0]['comparison']
        # Audio bytes are shared by cryptographic identity; target remains an independent exact TTS proof.
        compact = {k: deepcopy(v) for k, v in source.items() if k != 'audioBase64'}
        segments.append({'sceneId': key[0], 'actionId': key[1], 'text': own['text'],
            'textSha256': sha(own['text'].encode()), 'ttsRequestId': source['action']['audioId'],
            'audioSha256': sha(own['audio']), 'pcmSha256': own['receipt']['pcmSha256'], 'pcmKey': own['pcmKey'],
            'target': compact, 'primaryObservationSha256': primary_id, 'observations': comparisons,
            'transcript': primary['response']['transcript'], 'asr': deepcopy(primary['response']),
            'comparison': comparison, 'similarityBps': comparison['similarityBps'],
            'pendingReasons': sorted(reasons), 'acceptancePending': bool(reasons)})
    if used != set(verified): fail('Missing or unused original observation')
    result = {'schemaVersion': SCHEMA, 'previewKey': plan['previewKey'], 'sourceClassroomId': classroom['id'],
        'sourceSha256': digest(classroom), 'coreSha256': plan['coreSha256'], 'planSha256': digest(plan),
        'contract': audit_contract_identity(plan), 'observations': deepcopy(observations), 'pcmHistory': histories,
        'segments': segments, 'passed': bool(segments) and all(s['comparison']['passed'] for s in segments),
        'pendingCount': sum(s['acceptancePending'] for s in segments), 'noFurtherProviderCalls': True,
        'evidenceLimit': LIMIT, **{k: False for k in FALSE}}
    return seal(result)


def validate_observation_audit(audit, *, plan, classroom, expected_source_sha256,
                             expected_source_classroom_id=None):
    if not isinstance(audit, dict) or audit.get('schemaVersion') != SCHEMA:
        fail('Wrong observation-audit schema')
    if (type(audit.get('passed')) is not bool or type(audit.get('pendingCount')) is not int
            or audit.get('noFurtherProviderCalls') is not True
            or any(audit.get(k) is not False for k in FALSE)
            or not isinstance(audit.get('segments'), list)
            or not isinstance(audit.get('observations'), list)
            or not isinstance(audit.get('pcmHistory'), list)):
        fail('Observation coverage, pending state and capability claims require exact types')
    for h in audit['pcmHistory']:
        if (not isinstance(h, dict) or type(h.get('attemptCount')) is not int
                or type(h.get('historicalExcess')) is not bool or h.get('noFurtherProviderCalls') is not True):
            fail('Original PCM history types or no-further-call boundary changed')
    if expected_source_classroom_id is None:
        if digest(classroom) != expected_source_sha256: fail('Current complete source changed')
        expected_source_classroom_id = classroom['id']
    original = {**classroom, 'id': expected_source_classroom_id}
    actions = {(s['id'], a['id']): (s, a) for s in original['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech'}
    if len(actions) != sum(a.get('type') == 'speech' for s in original['scenes'] for a in s.get('actions', [])):
        fail('Duplicate current action identity')
    verified = {digest(o): verify_observation(o) for o in audit.get('observations', [])}
    targets, seen = [], set()
    for entry in audit.get('segments', []):
        if (not isinstance(entry, dict) or type(entry.get('acceptancePending')) is not bool
                or type(entry.get('similarityBps')) is not int
                or not isinstance(entry.get('comparison'), dict)
                or type(entry['comparison'].get('passed')) is not bool
                or not isinstance(entry.get('observations'), list)):
            fail('Target observation comparison types changed')
        for observed in entry['observations']:
            if (not isinstance(observed, dict) or type(observed.get('sameOriginalSource')) is not bool
                    or type(observed.get('textAndBodyMatch')) is not bool
                    or not isinstance(observed.get('comparison'), dict)
                    or type(observed['comparison'].get('passed')) is not bool):
                fail('Original observation relationship or comparison types changed')
        key = entry.get('sceneId'), entry.get('actionId')
        if key not in actions or key in seen: fail('Missing, extra or duplicate current target')
        seen.add(key); scene, action = actions[key]; target = deepcopy(entry.get('target', {}))
        original_action = deepcopy(target.get('action', {})); actual = deepcopy(action)
        original_action.pop('audioUrl', None); actual.pop('audioUrl', None)
        if original_action != actual or target.get('sceneOrder') != scene.get('order', 0):
            fail('Target differs from current speech')
        primary = verified.get(entry.get('primaryObservationSha256'))
        if primary is None: fail('Missing primary observation')
        target['audioBase64'] = base64.b64encode(primary['audio']).decode('ascii')
        targets.append(target)
    if not seen or seen != set(actions): fail('Complete current speech coverage is required')
    expected = build_observation_audit(plan=plan, classroom=original, targets=targets,
        observations=audit.get('observations'))
    expected['sourceSha256'] = expected_source_sha256; seal(expected)
    if audit != expected: fail('Original evidence, target comparison or pending state changed')
    return {(e['sceneId'], e['actionId']): deepcopy(e) for e in expected['segments']}
