"""Read-only packaging and authoritative checks for same-WAV observations.

No provider client or dispatch method exists here. The original collector owns
paid attempts. This helper only consumes their actual saved raw files.
"""
import base64
from copy import deepcopy
import json
from pathlib import Path

from content.textbook_catalog import digest
from content.textbook_asr_observation import (
    OBSERVATION_SCHEMA, build_observation_audit, validate_observation_audit, verify_observation, fail,
)
from content.textbook_asr_source_reuse import ORIGIN_SCHEMA, formal_request, pcm_key, sha, verify_origin
from services.textbook_preview_audio import verify_segment_receipt, segment_request_plan
from services.course_file_store import course_bytes, course_exists, course_glob, course_is_dir


def checked_bytes(path):
    path = Path(path)
    if path.is_symlink() or not course_exists(path): fail('Original observation file is missing or symlinked')
    return course_bytes(path)


def package_observation(*, origin, native_audio_directory, receipt_path, receipt_container):
    """Archive a supplied actual origin and its raw Native/cache records."""
    facts = verify_origin(origin)
    if len(facts['attempts']) != 1: fail('Package one original successful routine at a time')
    rid = facts['attempts'][0]['requestId']; root = Path(native_audio_directory)
    enc = lambda raw: base64.b64encode(raw).decode('ascii')
    result = {'schemaVersion': OBSERVATION_SCHEMA, 'origin': deepcopy(origin), 'rawEvidence': {
        'jobBase64': enc(checked_bytes(root / 'jobs/asr' / (sha(rid.encode()) + '.json'))),
        'ttsJobBase64': enc(checked_bytes(root / 'jobs/tts' / (sha(origin['source']['action']['audioId'].encode()) + '.json'))),
        'transcriptBase64': enc(checked_bytes(root / 'transcripts' / (sha(rid.encode()) + '.json'))),
        'receiptBase64': enc(checked_bytes(receipt_path)), 'receiptContainer': receipt_container}}
    verify_observation(result)
    return result


def target_evidence_from_files(*, plan, classroom, audio_directory):
    root = Path(audio_directory); folder = root / 'textbook-preview-audio'
    receipts = json.loads(checked_bytes(folder / 'receipts.json'))
    by_id = {r['requestId']: r for r in receipts}
    if len(by_id) != len(receipts): fail('Duplicate actual TTS receipt')
    targets = []
    for scene in classroom['scenes']:
        for action in scene.get('actions', []):
            if action.get('type') != 'speech': continue
            receipt = by_id.get(action.get('audioId'))
            if receipt is None: fail('Current speech lacks its actual TTS receipt')
            verify_segment_receipt(plan, receipt, scene, action, folder)
            effective = segment_request_plan(plan, receipt, folder, text=action['text'])
            targets.append({'sceneId': scene['id'], 'sceneOrder': scene.get('order', 0),
                'action': deepcopy(action), 'ttsReceipt': deepcopy(receipt),
                'requestPlan': None if effective == plan else effective,
                'audioBase64': base64.b64encode(checked_bytes(root / 'audio' / (action['audioId'] + '.wav'))).decode('ascii')})
    return targets


def assemble_observation_audit(*, plan, classroom, audio_directory, observations):
    """Pure collection from complete actual TTS/WAV files; no ASR operation."""
    targets = target_evidence_from_files(plan=plan, classroom=classroom, audio_directory=audio_directory)
    audit = build_observation_audit(plan=plan, classroom=classroom, targets=targets, observations=observations)
    validate_observation_audit(audit, plan=plan, classroom=classroom, expected_source_sha256=digest(classroom))
    return audit


def package_cached_routines(*, plan, classroom, audio_directory, routine_cache_directory,
                            native_audio_directory):
    """Import each actual old routine separately; return failures explicitly.

    This does not repair or rewrite a cache. A failed ID must be represented by
    its separate bounded-recovery origin before authoritative history can pass.
    """
    targets = target_evidence_from_files(plan=plan, classroom=classroom, audio_directory=audio_directory)
    by_key = {(t['sceneId'], t['action']['id']): t for t in targets}
    observations, unsuccessful = [], []
    for path in sorted(course_glob(Path(routine_cache_directory), 'tbpasr1_*.json')):
        entry = json.loads(checked_bytes(path)); source = by_key.get((entry.get('sceneId'), entry.get('actionId')))
        if source is None: fail('Original routine cache does not belong to this current lesson')
        response = entry.get('asr', {}); rid = response.get('requestId')
        if not isinstance(rid, str) or path.name != rid+'.json': fail('Original cache request identity changed')
        if response.get('status') != 'succeeded':
            unsuccessful.append({'sceneId': source['sceneId'], 'actionId': source['action']['id'],
                'requestId': rid, 'status': response.get('status'), 'rawCacheSha256': sha(checked_bytes(path))})
            continue
        origin = {'schemaVersion': ORIGIN_SCHEMA, 'kind': 'formal', 'source': deepcopy(source),
            'plan': deepcopy(plan), 'classroomId': classroom['id'], 'attempts': [{
                'kind': 'formal', 'role': 'routine', 'source': deepcopy(source), 'plan': deepcopy(plan),
                'classroomId': classroom['id'], 'request': formal_request(source, plan, classroom['id'], rid),
                'response': deepcopy(response)}]}
        observations.append(package_observation(origin=origin, native_audio_directory=native_audio_directory,
            receipt_path=path, receipt_container='routine-cache'))
    return {'observations': observations, 'unsuccessfulRoutines': unsuccessful}


def package_collected_origins(*, origins, classroom_directory, native_audio_directory):
    """Consume actual completed collector claims, including bounded recovery."""
    observations = []
    for origin in origins:
        facts = verify_origin(origin)
        if len(facts['attempts']) != 1: fail('One successful original routine is required per collector origin')
        rid = facts['attempts'][0]['requestId']
        path = Path(classroom_directory) / '.textbook-asr-pcm-ledger-v1' / facts['pcmKey'] / 'claims' / rid / 'response.json'
        original = json.loads(checked_bytes(path))
        observations.append(package_observation(origin=origin, native_audio_directory=native_audio_directory,
            receipt_path=path, receipt_container='native-response' if 'success' in original else 'transport-response'))
    return observations


def verify_live_observation_audit(audit, *, plan, classroom, expected_source_sha256,
                                native_audio_directory, probe_history_roots=()):
    """Compare every raw record and complete current PCM history before release.

Portable reads later revalidate the archived original evidence and frozen
release identity; they never need the live Native or make network calls.
"""
    validate_observation_audit(audit, plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256)
    root = Path(native_audio_directory)
    if not course_is_dir(root / 'jobs/asr') or not course_is_dir(root / 'jobs/tts'):
        fail('Managed Native ASR/TTS history is required')
    facts = [verify_observation(o) for o in audit['observations']]
    pcm_shas = {f['receipt']['pcmSha256'] for f in facts}
    audio_shas = {sha(f['audio']) for f in facts}
    expected = {h['pcmKey']: set(h['requestIds']) for h in audit['pcmHistory']}
    current = {key: set() for key in expected}; tts_cache = {}
    for fact in facts:
        rid = fact['requestId']
        if (checked_bytes(root / 'jobs/asr' / (sha(rid.encode()) + '.json')) != fact['jobRaw']
                or checked_bytes(root / 'jobs/tts' / (sha(fact['origin']['source']['action']['audioId'].encode()) + '.json')) != fact['ttsJobRaw']
                or checked_bytes(root / 'transcripts' / (sha(rid.encode()) + '.json')) != fact['transcriptRaw']):
            fail('Original Native observation bytes changed')
        recovery = fact.get('failureRecovery')
        if recovery is not None and checked_bytes(root / 'jobs/asr' / (sha(recovery['failedRequestId'].encode()) + '.json')) != recovery['failedJobRaw']:
            fail('Original failed routine bytes changed')
    for path in course_glob(root / 'jobs/asr', '*.json'):
        job = json.loads(checked_bytes(path)); tts_id = job.get('ttsRequestId')
        if not isinstance(tts_id, str): continue
        if tts_id not in tts_cache:
            tts_path = root / 'jobs/tts' / (sha(tts_id.encode()) + '.json')
            tts_cache[tts_id] = json.loads(checked_bytes(tts_path)) if course_exists(tts_path) else None
        tts = tts_cache[tts_id]
        if tts is None:
            if job.get('audioSha256') in audio_shas:
                fail('Matching historical ASR lacks its original TTS identity')
            continue
        if tts.get('pcmSha256') not in pcm_shas: continue
        key = pcm_key(tts)
        if key in current:
            rid = job.get('requestId')
            if not isinstance(rid, str) or not rid: fail('Historical ASR request identity is missing')
            current[key].add(rid)
    # A durable operator claim with no Native job is still an unknown paid
    # outcome. It must never disappear merely because only job files were read.
    claims_root = root.parent / 'classrooms/.textbook-asr-pcm-ledger-v1'
    known_requests = {f['requestId']: f['origin']['attempts'][0]['request'] for f in facts}
    known_origins = {f['requestId']: digest({**f['origin'], 'attempts': []}) for f in facts}
    for f in facts:
        recovery = f.get('failureRecovery')
        if recovery is not None:
            known_requests[recovery['failedRequestId']] = formal_request(f['origin']['source'],
                f['origin']['plan'], f['origin']['classroomId'], recovery['failedRequestId'])
    for key in current:
        for path in course_glob(claims_root / key / 'claims', '*/intent.json'):
            claim = json.loads(checked_bytes(path)); rid = claim.get('requestId')
            claim_fields = {'schemaVersion', 'pcmKey', 'requestId', 'request', 'originSha256',
                'historySha256', 'createdAt', 'maximumPostAttempts', 'maximumAttemptsPerPcm',
                'unknownConsumesAttempt', 'providerHints'}
            if (set(claim) != claim_fields or claim.get('schemaVersion') != 'mira.textbook.asr-pcm-dispatch.v1'
                    or claim.get('pcmKey') != key or not isinstance(rid, str) or not rid
                    or path.parent.name != rid or type(claim.get('maximumPostAttempts')) is not int
                    or claim.get('maximumPostAttempts') != 1 or type(claim.get('maximumAttemptsPerPcm')) is not int
                    or claim.get('maximumAttemptsPerPcm') != 2 or claim.get('unknownConsumesAttempt') is not True
                    or claim.get('providerHints') is not None or type(claim.get('createdAt')) is not int
                    or claim.get('createdAt', 0) <= 0
                    or any(not isinstance(claim.get(k), str) or len(claim[k]) != 64
                        or any(c not in '0123456789abcdef' for c in claim[k]) for k in ('originSha256', 'historySha256'))):
                fail('Original shared PCM dispatch claim is invalid')
            current[key].add(rid)
            if rid in known_requests and claim.get('request') != known_requests[rid]:
                fail('Original shared claim conflicts with the actual source request')
            if rid in known_origins and claim['originSha256'] != known_origins[rid]:
                fail('Original shared claim differs from its original pre-dispatch source')
    # Manual probe claims also consume history; no expected-text/body alias can hide one.
    for probe_root in probe_history_roots:
        probe_root = Path(probe_root)
        if not course_is_dir(probe_root): fail('Declared probe history root is missing')
        for path in course_glob(probe_root, 'intent.json', recursive=True):
            intent = json.loads(checked_bytes(path))
            if intent.get('schemaVersion') != 'mira.operator.probe-asr-intent.v1': continue
            request = json.loads(checked_bytes(path.parent / 'request.json'))
            try:
                encoded = request['input']['messages'][0]['content'][0]['audio']
                if not encoded.startswith('data:audio/wav;base64,'): raise ValueError()
                audio = base64.b64decode(encoded.split(',', 1)[1], validate=True)
            except (KeyError, TypeError, IndexError, ValueError): fail('Invalid original probe ASR input')
            for f in facts:
                if len(audio) >= 44 and sha(audio[44:]) == f['receipt']['pcmSha256']:
                    rid = intent.get('requestId')
                    if not isinstance(rid, str) or not rid: fail('Probe ASR claim has no original request ID')
                    current[f['pcmKey']].add(rid)
    if current != expected:
        fail('Observation archive omits known failed, unknown, excess or other original PCM attempts')
    return {'pcmGroups': len(current), 'historicalAttempts': sum(map(len, current.values())),
        'noFurtherProviderCalls': True, 'historySha256': digest({k: sorted(v) for k, v in current.items()})}
