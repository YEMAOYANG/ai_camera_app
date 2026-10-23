"""Optional operator I/O lane. A single managed PCM ledger spans all outputs.

No HTTP or Native changes. Import original evidence before dispatch; exclusive
durable claims count unknown outcomes. Existing jobs are recovered read-only.
"""
import base64
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path

from content.textbook_catalog import canonical, digest
from content.textbook_asr_source_reuse import (
    ORIGIN_SCHEMA, target_evidence, verify_origin, pcm_key,
    formal_request, shared_recheck_id, sha, build_audit,
    alias_exact, verify_origin_library, FAILED_RECOVERY_ORIGIN_SCHEMA,
)
from content.textbook_preview_audio_contract import asr_request_id, compare_transcript
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from core.security import now_ms


def read(path):
    return json.loads(Path(path).read_text())


def immutable(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value).encode()
    if path.exists():
        if path.read_bytes() != raw: raise RuntimeError('Immutable ASR origin evidence conflict')
        return
    with path.open('xb') as out:
        out.write(raw); out.flush(); os.fsync(out.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def inventory_attempts(native_root, probe_roots, facts):
    """Read real historical claims, including failures/unknown and overuse.

    This is an attempt budget, not acceptance. Originals are stored unchanged;
    successful reuse still requires the separate portable validator.
    """
    native_root = Path(native_root).resolve(); attempts = {}
    if not (native_root / 'jobs/asr').is_dir() or not (native_root / 'jobs/tts').is_dir():
        raise RuntimeError('Actual managed Native job history is required')
    for path in (native_root / 'jobs/asr').glob('*.json'):
        job = read(path)
        tts_id = job.get('ttsRequestId')
        if not isinstance(tts_id, str): continue
        tts_path = native_root / 'jobs/tts' / (sha(tts_id.encode()) + '.json')
        if not tts_path.is_file():
            if job.get('audioSha256') == sha(facts['audio']): raise RuntimeError('Matching historical ASR has no TTS identity')
            continue
        tts = read(tts_path)
        if tts.get('pcmSha256') != facts['receipt']['pcmSha256']: continue
        if pcm_key(tts) != facts['pcmKey']: continue
        rid = job.get('requestId')
        if not isinstance(rid, str) or not rid: raise RuntimeError('Historical ASR claim missing identity')
        attempts[rid] = {'kind': 'native-durable-job', 'job': job, 'tts': tts}
    for root in probe_roots:
        root = Path(root).resolve()
        if not root.is_dir(): raise RuntimeError('Declared probe history root is missing')
        for path in root.rglob('intent.json'):
            intent = read(path)
            if intent.get('schemaVersion') != 'mira.operator.probe-asr-intent.v1': continue
            req_path = path.parent / 'request.json'
            if not req_path.is_file(): raise RuntimeError('Original ASR intent has no immutable request')
            request = read(req_path)
            try:
                encoded = request['input']['messages'][0]['content'][0]['audio']
                if not encoded.startswith('data:audio/wav;base64,'): raise ValueError()
                audio = base64.b64decode(encoded.split(',', 1)[1], validate=True)
            except (KeyError, TypeError, IndexError, ValueError): raise RuntimeError('Invalid historical probe request')
            if len(audio) < 44 or sha(audio[44:]) != facts['receipt']['pcmSha256']: continue
            rid = intent.get('requestId')
            if not isinstance(rid, str) or not rid: raise RuntimeError('Historical probe claim missing ID')
            evidence = {'kind': 'probe-dispatch-intent', 'intent': intent, 'requestSha256': sha(req_path.read_bytes())}
            if (path.parent / 'receipt.json').is_file(): evidence['receipt'] = read(path.parent / 'receipt.json')
            if rid in attempts and attempts[rid] != evidence: raise RuntimeError('Conflicting original ASR identities')
            attempts[rid] = evidence
    return attempts


class PcmLedger:
    def __init__(self, classroom_directory, native_root, probe_roots, *, routine_cache_directory=None):
        # Deliberately not selected by output directory, action or revision.
        self.root = Path(classroom_directory).resolve() / '.textbook-asr-pcm-ledger-v1'
        self.native_root = Path(native_root).resolve()
        self.probe_roots = tuple(Path(p).resolve() for p in probe_roots)
        self.routine_cache_directory = Path(routine_cache_directory).resolve() if routine_cache_directory is not None else None

    def _recovery_history(self, facts):
        failed = facts.get('failureRecovery')
        if failed is None: return set()
        rid = failed['failedRequestId']
        job = self.native_root / 'jobs/asr' / (sha(rid.encode()) + '.json')
        cache = self.routine_cache_directory / (rid + '.json') if self.routine_cache_directory is not None else None
        if (job.is_symlink() or not job.is_file() or job.read_bytes() != failed['failedJobRaw']
                or cache is None or cache.is_symlink() or not cache.is_file()
                or cache.read_bytes() != failed['failedCacheRaw']):
            raise RuntimeError('Original failed ASR job/cache bytes changed or are not retained')
        return {rid}

    def inspect(self, *, origin, facts, recoverable_request_id=None):
        """Even zero-POST reuse must not hide a failed/unknown second attempt."""
        group = self.root / facts['pcmKey']; group.mkdir(parents=True, exist_ok=True)
        with (group / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            immutable(group / 'identity.json', {'schemaVersion':'mira.textbook.asr-pcm-identity.v1',
                'pcmKey':facts['pcmKey'],'audioSha256':sha(facts['audio']), 'text':facts['text'],'providerBody':facts['body']})
            history = inventory_attempts(self.native_root, self.probe_roots, facts)
            for path in (group/'claims').glob('*/intent.json') if (group/'claims').exists() else ():
                item=read(path);history.setdefault(item['requestId'], {'kind':'operator-claim','intent':item})
            immutable(group/'history'/(digest(history)+'.json'),history)
            retained = {x['requestId'] for x in facts['attempts']} | self._recovery_history(facts)
            remaining = set(history)-retained
            if recoverable_request_id is not None: remaining.discard(recoverable_request_id)
            consensus = facts.get('historicalExcessConsensus')
            if consensus is not None:
                if (recoverable_request_id is not None or set(history) != retained
                        or retained != set(consensus['requestIds'])
                        or any(item.get('kind') != 'native-durable-job'
                               or item.get('job', {}).get('state') != 'succeeded'
                               for item in history.values())):
                    raise RuntimeError('Historical excess consensus must exactly equal all succeeded durable PCM history')
            elif remaining or len(set(history)|retained) > 2:
                raise RuntimeError('Origin omits known failed/unknown/excess PCM history; recover all originals first')
            if facts.get('failureRecovery') is not None and recoverable_request_id in history:
                pending = history[recoverable_request_id]
                if pending.get('kind') == 'native-durable-job' and pending.get('job', {}).get('state') != 'succeeded':
                    raise RuntimeError('Existing recovery ASR unknown/failed; no redispatch or third attempt')
            # Existing source evidence is retained by its exact request ID. A
            # local durable response must agree, not merely share that ID.
            for item in facts['attempts']:
                old=history.get(item['requestId'],{})
                if old.get('kind')=='native-durable-job':
                    job=old['job']; response=item['receipt']
                    if (job.get('state')!='succeeded' or job.get('transcriptSha256')!=response.get('transcriptSha256')
                            or job.get('audioSha256')!=sha(facts['audio'])):
                        raise RuntimeError('Original success conflicts with actual durable PCM history')
                elif old.get('kind')=='probe-dispatch-intent' and old.get('receipt')!=item['receipt']:
                    raise RuntimeError('Original probe success is missing or differs from actual receipt')

    def dispatch(self, *, origin, source, plan, classroom_id, client, probe_files=None):
        own = target_evidence(source, plan)
        facts = verify_origin(origin, probe_files=probe_files)
        if facts.get('historicalExcessConsensus') is not None:
            raise RuntimeError('Historical excess consensus permanently forbids another ASR dispatch or recheck')
        if any(own[k] != facts[k] for k in ('audio', 'body', 'text', 'pcmKey')):
            raise RuntimeError('Same-PCM request/body/text conflict; cannot create another budget identity')
        failed_ids = self._recovery_history(facts)
        recovery = facts.get('failureRecovery')
        if recovery is not None and (source != origin['source'] or plan != origin['plan']
                                     or classroom_id != origin['classroomId']):
            raise RuntimeError('Failed recovery must keep the explicitly selected original target identity')
        if recovery is not None and facts['attempts']:
            raise RuntimeError('Failed routine and recovery already consume both PCM attempts; no further call')
        group = self.root / own['pcmKey']; group.mkdir(parents=True, exist_ok=True)
        with (group / 'lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            failed_ids = self._recovery_history(facts)
            identity = {'schemaVersion': 'mira.textbook.asr-pcm-identity.v1', 'pcmKey': own['pcmKey'],
                        'audioSha256': sha(own['audio']), 'text': own['text'], 'providerBody': own['body']}
            immutable(group / 'identity.json', identity)
            history = inventory_attempts(self.native_root, self.probe_roots, own)
            for old in facts['attempts']:
                history.setdefault(old['requestId'], {'kind': 'validated-origin', 'originSha256': digest(origin),
                    'receipt': old['receipt']})
            # Immutable import snapshots retain even historical third attempts.
            immutable(group / 'history' / (digest(history) + '.json'), history)
            for path in (group / 'claims').glob('*/intent.json') if (group / 'claims').exists() else ():
                item = read(path); history.setdefault(item['requestId'], {'kind': 'operator-claim', 'intent': item})
            count = len(facts['attempts'])
            if count > 1: raise RuntimeError('One routine and one recheck already retained; no further call')
            rid = (recovery['recoveryRequestId'] if recovery is not None else
                   asr_request_id(plan, source['action']['audioId'], sha(own['audio']))
                   if count == 0 else shared_recheck_id(own['pcmKey']))
            retained_ids = {x['requestId'] for x in facts['attempts']} | failed_ids
            if (len(history) > 2 or set(history) - retained_ids - {rid}
                    or recovery is not None and failed_ids - set(history)):
                raise RuntimeError('Additional historical PCM claims must be preserved/recovered; no new call')
            claim = group / 'claims' / rid; claim.mkdir(parents=True, exist_ok=True)
            request = formal_request(source, plan, classroom_id, rid)
            # Policy version selects the response validator, not an HTTP field.
            # Native derives the actual pronunciation from the original TTS job.
            prior = read(claim / 'intent.json') if (claim / 'intent.json').exists() else None
            if prior is not None and (prior['request'] != request or prior['originSha256'] != digest(origin)):
                raise RuntimeError('Prior shared claim has a different original request')
            response = None
            version = own['policy']['policyVersion']
            if (claim / 'response.json').exists():
                response = read(claim / 'response.json')
            else:
                found = None
                try: found = client.get_formal_audio_asr(rid, pronunciation_policy_version=version)
                except OpenMaicFullRuntimeError as exc:
                    if exc.status_code != 404: raise
                if found is not None:
                    if found.get('status') != 'succeeded': raise RuntimeError('Existing ASR unknown/failed; no redispatch')
                    transcript = read(self.native_root / 'transcripts' / (sha(rid.encode()) + '.json'))
                    if (transcript.get('requestId') != rid or transcript.get('audioSha256') != sha(own['audio'])
                            or transcript.get('transcriptSha256') != found.get('transcriptSha256')
                            or sha(transcript.get('transcript', '').encode()) != found.get('transcriptSha256')):
                        raise RuntimeError('Durable transcript recovery differs from original ASR')
                    response = {**found, 'transcript': transcript['transcript'], 'completionUsable': True}
                    immutable(claim / 'recovery.json', {'durableGet': found, 'transcriptArchive': transcript})
                else:
                    if prior is not None: raise RuntimeError('Unknown prior outcome consumes budget; no retry')
                    limit = 2 if recovery is not None or count else 1
                    if rid in history or len(history) >= limit:
                        raise RuntimeError('Historical PCM attempt budget occupied; recover originals instead of redispatch')
                    if set(history) != retained_ids:
                        raise RuntimeError('Unrecovered historical PCM claim; no new paid request')
                    intent = {'schemaVersion': 'mira.textbook.asr-pcm-dispatch.v1', 'pcmKey': own['pcmKey'],
                        'requestId': rid, 'request': request, 'originSha256': digest(origin),
                        'historySha256': digest(history), 'createdAt': now_ms(), 'maximumPostAttempts': 1,
                        'maximumAttemptsPerPcm': 2, 'unknownConsumesAttempt': True, 'providerHints': None}
                    immutable(claim / 'intent.json', intent)
                    response = client._request_formal_audio_json('POST', '/api/mira/formal-audio/asr', request)
                immutable(claim / 'response.json', response)
            if (claim / 'recovery.json').exists():
                recovered = read(claim / 'recovery.json')
                expected = {**recovered['durableGet'], 'transcript': recovered['transcriptArchive']['transcript'],
                            'completionUsable': True}
                if response != expected: raise RuntimeError('Recovered response no longer matches original GET/transcript')
            else:
                response = client._validate_formal_asr_response(response, request_id=rid,
                    require_ephemeral_transcript=True, pronunciation_policy_version=version)
            if response.get('status') != 'succeeded': raise RuntimeError('Unsuccessful ASR preserved; no retry')
            attempt = {'kind': 'formal', 'role': 'routine' if count == 0 else 'recheck',
                'request': formal_request(source, plan, classroom_id, rid), 'response': response,
                'source': deepcopy(source), 'plan': deepcopy(plan), 'classroomId': classroom_id}
            result = deepcopy(origin); result['attempts'].append(attempt)
            verify_origin(result, probe_files=probe_files)
            immutable(claim / 'origin.json', result)
            return result


def recover_failed_origins(*, plan, classroom, origins, ledger, client=None):
    """Explicit selected failures only; no full-audit or publication claim.

    With no client, this is the local prepare preflight. All selected histories
    are checked before the first potential POST; old routine sources elsewhere
    in the lesson are not reclassified or dispatched by this narrow operation.
    """
    if not isinstance(origins, list) or not origins:
        raise RuntimeError('Failed recovery requires a nonempty exact selection')
    seen = set()
    for origin in origins:
        facts = verify_origin(origin)
        if (origin.get('schemaVersion') != FAILED_RECOVERY_ORIGIN_SCHEMA or facts['attempts']
                or origin['plan'] != plan or origin['classroomId'] != classroom['id']
                or origin['failureRecovery']['selection']['sourceSha256'] != digest(classroom)
                or facts['pcmKey'] in seen):
            raise RuntimeError('Invalid, duplicate or changed failed-recovery selection')
        seen.add(facts['pcmKey'])
        ledger.inspect(origin=origin, facts=facts,
                       recoverable_request_id=facts['failureRecovery']['recoveryRequestId'])
    if client is None: return deepcopy(origins)
    return [ledger.dispatch(origin=origin, source=origin['source'], plan=plan,
                            classroom_id=classroom['id'], client=client) for origin in origins]


def collect(*, plan, classroom, targets, library, ledger, client, recheck_keys=(), failed_recoveries=()):
    """All targets prevalidated before any call; returns original-source audit."""
    files = verify_origin_library(library, plan)
    groups = {}
    for origin in library['origins']:
        facts = verify_origin(origin, probe_files=files)
        if facts['pcmKey'] in groups: raise RuntimeError('Merge and retain complete original history before using duplicate PCM origins')
        groups[facts['pcmKey']] = deepcopy(origin)
    own = [target_evidence(t, plan) for t in targets]
    recoveries = {}
    for origin in failed_recoveries:
        facts = verify_origin(origin, probe_files=files)
        if (origin.get('schemaVersion') != FAILED_RECOVERY_ORIGIN_SCHEMA or facts['attempts']
                or origin['failureRecovery']['selection']['sourceSha256'] != digest(classroom)
                or origin['plan'] != plan or origin['classroomId'] != classroom['id']):
            raise RuntimeError('Failed recovery must explicitly select the exact current source and plan')
        key = facts['pcmKey']
        if key in recoveries or key in groups:
            raise RuntimeError('Failed recovery PCM selection duplicates or replaces an existing origin')
        if not any(t == origin['source'] for t in targets):
            raise RuntimeError('Failed recovery selection is not an actual current target')
        recoveries[key] = origin
        groups[key] = deepcopy(origin)
    for t, facts in zip(targets, own):
        if facts['pcmKey'] in groups:
            original = verify_origin(groups[facts['pcmKey']], probe_files=files)
            if any(original[k] != facts[k] for k in ('text', 'body', 'audio')):
                raise RuntimeError('Same PCM has different source/body/WAV; no call permitted')
        else:
            groups[facts['pcmKey']] = {'schemaVersion': ORIGIN_SCHEMA, 'kind': 'formal',
                'source': deepcopy(t), 'plan': deepcopy(plan), 'classroomId': classroom['id'], 'attempts': []}
    selected = set(recheck_keys)
    if selected - {(t['sceneId'], t['action']['id']) for t in targets}: raise RuntimeError('Unknown recheck selection')
    # Freeze/check all real histories before the first potential POST, including
    # already successful groups that would otherwise never enter dispatch().
    inspected=set()
    for t,facts in zip(targets,own):
        key=facts['pcmKey']
        if key in inspected: continue
        origin=groups[key]; prior=verify_origin(origin,probe_files=files)
        selected_pcm=any((other['sceneId'],other['action']['id']) in selected
                         for other,other_facts in zip(targets,own) if other_facts['pcmKey']==key)
        failed = prior.get('failureRecovery')
        if failed is not None and selected_pcm:
            raise RuntimeError('Failed recovery already reserves both PCM attempts; independent recheck forbidden')
        if failed is not None and not prior['attempts'] and key not in recoveries:
            raise RuntimeError('Missing explicit current failed-recovery selection')
        recoverable=(failed['recoveryRequestId'] if failed is not None and not prior['attempts'] else
                     asr_request_id(plan,t['action']['audioId'],sha(facts['audio'])) if not prior['attempts']
                     else shared_recheck_id(key) if selected_pcm and len(prior['attempts'])==1 else None)
        ledger.inspect(origin=origin,facts=prior,recoverable_request_id=recoverable)
        inspected.add(key)
    seen_recheck = set()
    for t, facts in zip(targets, own):
        key = facts['pcmKey']; origin = groups[key]
        prior = verify_origin(origin, probe_files=files)
        needs = not prior['attempts']
        recheck = (t['sceneId'], t['action']['id']) in selected
        if recheck and key in seen_recheck: continue
        if recheck:
            if prior.get('historicalExcessConsensus') is not None:
                raise RuntimeError('Historical excess consensus permanently forbids another ASR dispatch or recheck')
            if (not prior['attempts'] or compare_transcript(plan, facts['text'], prior['attempts'][0]['transcript'])['similarityBps'] >= 10000):
                raise RuntimeError('Recheck requires a real original transcript discrepancy')
            if alias_exact(facts['text'], prior['attempts'][0]['transcript'], facts['policy']):
                raise RuntimeError('Fully verified exact natural alias needs no additional paid recognition')
        if needs or (recheck and len(origin['attempts']) == 1):
            dispatch_source = origin['source'] if prior.get('failureRecovery') is not None else t
            groups[key] = ledger.dispatch(origin=origin, source=dispatch_source, plan=plan, classroom_id=classroom['id'],
                client=client, probe_files=files)
        if recheck: seen_recheck.add(key)
    used = {facts['pcmKey'] for facts in own}
    return build_audit(plan=plan, classroom=classroom,
        targets=[{'target': t, 'originSha256': digest(groups[f['pcmKey']])} for t, f in zip(targets, own)],
        origins=[groups[k] for k in groups if k in used], probe_protocol=library['probeProtocol'])
