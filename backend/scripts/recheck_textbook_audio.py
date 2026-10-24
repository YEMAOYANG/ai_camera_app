#!/usr/bin/env python3
"""Bounded independent ASR of the same formal WAV; no TTS or raw-audit edits.

Prepare validates all inputs and writes a sealed selection. Run creates each
immutable dispatch intent before its sole POST. An unknown response stops; it
never retries. Existing successful native jobs can be recovered read-only from
their private transcript archive with --native-audio-directory.
"""
import argparse
import base64
import fcntl
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from content.textbook_audio_recheck import (SCHEMA, SCHEMA_ALIAS, INTENT_SCHEMA_ALIAS, build_intent, logical_request,
    provider_body, raw_entries, seal, validate_asr_recheck, validate_tts_request_plan)
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_pronunciation import policy_for_plan, validate_formal_receipt, validate_receipt_wav
from content.textbook_preview_audio_contract import compare_transcript
from core.config import AppConfig
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.course_file_store import course_bytes, course_exists, course_text
from services.textbook_preview_audio import verify_segment_receipt


def read(path):
    return json.loads(course_text(path))


def immutable(path, value):
    path = Path(path)
    data = canonical(value).encode()
    if course_exists(path):
        if course_bytes(path) != data: raise RuntimeError('Immutable recheck evidence conflict: ' + path.name)
        return
    with path.open('xb') as out:
        out.write(data); out.flush()
        import os
        os.fsync(out.fileno())


def preflight(*, classroom_path, audit_path, audio_directory, selection, expected_source_sha256):
    classroom, audit = read(classroom_path), read(audit_path)
    if digest(classroom) != expected_source_sha256: raise RuntimeError('Current classroom source changed')
    folder = Path(audio_directory)
    plan, receipts = read(folder / 'textbook-preview-audio/plan.json'), read(folder / 'textbook-preview-audio/receipts.json')
    if not isinstance(receipts, list): raise RuntimeError('Formal receipts must be a list')
    by_id = {r['requestId']: r for r in receipts}
    if len(by_id) != len(receipts): raise RuntimeError('Duplicate formal receipts')
    scenes, actions, raw = raw_entries(plan=plan, classroom=classroom, audit=audit, expected_source_sha256=expected_source_sha256)
    entries = []
    for selected in selection:
        key = (selected['sceneId'], selected['actionId']); action = actions[key]; original = raw[key]
        receipt = by_id[action['audioId']]
        if receipt.get('status') != 'succeeded' or receipt.get('completionUsable') is False:
            raise RuntimeError('Original TTS request plan identity invalid')
        verify_segment_receipt(plan, receipt, scenes[key[0]], action, folder / 'textbook-preview-audio')
        request_plan = None
        if receipt.get('narrationRevisionId') is not None:
            # verify_segment_receipt has validated the revision ID and actual
            # immutable child plan before it is copied into evidence.
            request_plan = read(folder / 'textbook-preview-audio/narration-revisions' / receipt['narrationRevisionId'] / 'plan.json')
        effective = validate_tts_request_plan(plan, scenes[key[0]], action, receipt, request_plan)
        policy = policy_for_plan(effective)
        audio = course_bytes(folder / 'audio' / (action['audioId'] + '.wav'))
        validate_formal_receipt(receipt, action['text'].strip(), policy_version=policy['policyVersion'])
        validate_receipt_wav(receipt, audio)
        if receipt.get('audioSha256') != original['audioSha256']: raise RuntimeError('Original audit audio changed')
        body_sha = hashlib.sha256(provider_body(audio)).hexdigest()
        if body_sha != original['asr']['providerAsrBodySha256']: raise RuntimeError('Original ASR body was not the exact same no-hint audio request')
        payload = logical_request(plan, classroom, scenes[key[0]], action, receipt, original)
        # Validate the unchanged public client contract under its original ID.
        normal = {**payload, 'requestId': original['asr']['requestId']}
        identity = OpenMaicFullRuntimeClient._formal_audio_identity_payload(
            request_id=normal['requestId'], classroom_id=normal['classroomId'],
            classroom_content_sha256=normal['classroomContentSha256'], subject=normal['subject'],
            teacher_profile_id=normal['teacherProfileId'], teacher_profile_version=normal['teacherProfileVersion'],
            teacher_profile_sha256=normal['teacherProfileSha256'], teacher_gender=normal['teacherGender'],
            scene_id=normal['sceneId'], scene_order=normal['sceneOrder'], action_id=normal['actionId'],
            narration_segment_id=normal['narrationSegmentId'])
        if normal != {**identity, 'ttsRequestId': normal['ttsRequestId'], 'audioSha256': normal['audioSha256']}:
            raise RuntimeError('Unexpected logical request fields')
        OpenMaicFullRuntimeClient._validate_textbook_audio_namespace(normal, 'asr', pronunciation_policy_version=policy['policyVersion'])
        entry = {'sceneId': key[0], 'actionId': key[1], 'originalSegmentSha256': digest(original),
            'request': payload, 'requestSha256': digest(payload), 'ttsReceipt': receipt,
            'ttsReceiptSha256': digest(receipt), 'audioBase64': base64.b64encode(audio).decode('ascii')}
        if request_plan is not None: entry['requestPlan'] = request_plan
        entries.append(entry)
    return plan, classroom, audit, entries


def verify_alias_sources(evidence, *, plan, classroom, audit, audio_directory, expected_source_sha256, latest):
    """No text-only skip: revalidate the exact proof AND authoritative bytes."""
    from content.textbook_pinyin_alias_alignment import validate_evidence
    aligned = validate_evidence(evidence, plan=plan, classroom=classroom, audit=audit,
        expected_source_sha256=expected_source_sha256, now_ms=latest)
    folder = Path(audio_directory)
    receipts = read(folder / 'textbook-preview-audio/receipts.json')
    if not isinstance(receipts, list): raise RuntimeError('Formal receipts must be a list')
    by_id = {r['requestId']: r for r in receipts}
    if len(by_id) != len(receipts): raise RuntimeError('Duplicate formal receipts')
    scenes, actions, _ = raw_entries(plan=plan, classroom=classroom, audit=audit,
                                     expected_source_sha256=expected_source_sha256)
    for key, entry in aligned.items():
        receipt, action = entry['ttsReceipt'], actions[key]
        if by_id.get(action['audioId']) != receipt:
            raise RuntimeError('Alias proof is not the authoritative formal receipt')
        verify_segment_receipt(plan, receipt, scenes[key[0]], action, folder / 'textbook-preview-audio')
        if receipt.get('narrationRevisionId') is not None:
            actual = read(folder / 'textbook-preview-audio/narration-revisions' / receipt['narrationRevisionId'] / 'plan.json')
            if entry.get('requestPlan') != actual: raise RuntimeError('Alias child plan differs from its archive')
        audio = course_bytes(folder / 'audio' / (action['audioId'] + '.wav'))
        if base64.b64encode(audio).decode('ascii') != entry['audioBase64']:
            raise RuntimeError('Alias WAV differs from the actual formal audio')
        validate_receipt_wav(receipt, audio)
    return aligned


def dispatch_once(client, *, entry, directory, policy_version, native_audio_directory=None, paid_budget=None):
    """At most one POST, even after unknown outcome or another output directory."""
    directory = Path(directory); directory.mkdir(exist_ok=True)
    request = entry['request']; rid = request['requestId']
    response_path = directory / 'response.json'
    intent_path = directory / 'dispatch-intent.json'
    if course_exists(response_path):
        raw = read(response_path)
        response = client._validate_formal_asr_response(raw, request_id=rid,
            require_ephemeral_transcript=True, pronunciation_policy_version=policy_version)
        if response['status'] != 'succeeded': raise RuntimeError('Prior ASR outcome not succeeded; no retry')
        return response
    found = None
    try:
        found = client.get_formal_audio_asr(rid, pronunciation_policy_version=policy_version)
    except OpenMaicFullRuntimeError as exc:
        if exc.status_code != 404: raise
    if found is not None:
        if found['status'] != 'succeeded' or native_audio_directory is None:
            raise RuntimeError('Existing ASR needs read-only recovery; will not redispatch')
        transcript = read(Path(native_audio_directory) / 'transcripts' / (hashlib.sha256(rid.encode()).hexdigest() + '.json'))
        if (set(transcript) != {'requestId', 'audioSha256', 'transcript', 'transcriptSha256'}
                or transcript['requestId'] != rid or transcript['audioSha256'] != request['audioSha256']
                or transcript['transcriptSha256'] != found.get('transcriptSha256')
                or hashlib.sha256(transcript['transcript'].encode()).hexdigest() != transcript['transcriptSha256']):
            raise RuntimeError('Native transcript does not match durable ASR receipt')
        response = {**found, 'transcript': transcript['transcript'], 'completionUsable': True}
        immutable(directory / 'recovered-response.json', {'durableGet': found, 'transcriptArchive': transcript})
        return response
    if course_exists(intent_path):
        raise RuntimeError('Prior dispatch intent has unknown outcome; no retry even if GET is missing')
    immutable(directory / 'request.json', request)
    immutable(intent_path, {'schemaVersion': 'mira.textbook.audio-asr-dispatch.v1', 'requestId': rid,
        'requestSha256': digest(request), 'sourceEvidenceSha256': digest(entry), 'createdAt': now_ms(),
        'maximumPostAttempts': 1, 'paidBudget': paid_budget, 'providerHints': None})
    # Only this isolated operator path uses the domain-separated ID. The public
    # start_formal_audio_asr method and its strict original-ID formula stay intact.
    raw = client._request_formal_audio_json('POST', '/api/mira/formal-audio/asr', request, paid_budget=paid_budget)
    immutable(response_path, raw)
    response = client._validate_formal_asr_response(raw, request_id=rid,
        require_ephemeral_transcript=True, pronunciation_policy_version=policy_version)
    if response['status'] != 'succeeded': raise RuntimeError('ASR outcome not succeeded; no retry')
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'run'])
    parser.add_argument('--classroom', type=Path, required=True)
    parser.add_argument('--audio-directory', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True, help='JSON list of sceneId/actionId/reason; frozen before any call')
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-audio-directory', type=Path)
    parser.add_argument('--paid-budget', type=Path)
    parser.add_argument('--exact-alias-evidence', type=Path,
                        help='Optional complete registered natural-alias proof; never a text-only exemption')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / 'operator.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        selection = read(args.selection)
        # Resolve and freeze the entire scope before any provider action.
        plan, classroom, audit, entries = preflight(classroom_path=args.classroom, audit_path=args.audit,
            audio_directory=args.audio_directory, selection=selection, expected_source_sha256=args.source_sha256)
        intent_path = args.output / 'intent.json'
        created = read(intent_path)['createdAt'] if course_exists(intent_path) else now_ms()
        alias = read(args.exact_alias_evidence) if args.exact_alias_evidence else None
        if alias is not None:
            verify_alias_sources(alias, plan=plan, classroom=classroom, audit=audit,
                audio_directory=args.audio_directory, expected_source_sha256=args.source_sha256, latest=created)
        intent = build_intent(plan=plan, classroom=classroom, audit=audit, expected_source_sha256=args.source_sha256,
            selections=selection, created_at=created, exact_alias_evidence=alias)
        immutable(intent_path, intent)
        immutable(args.output / 'original-audit.json', audit)
        immutable(args.output / 'plan.json', plan)
        for entry in entries:
            folder = args.output / entry['request']['requestId']; folder.mkdir(exist_ok=True)
            immutable(folder / 'source.json', entry)
        if args.mode == 'prepare':
            print(json.dumps({'prepared': len(entries), 'intentSha256': intent['sha256'], 'providerCalls': 0})); return
        if not entries:
            # A verified alias alone needs no second recognition. Do not create
            # an empty "passed" recheck or even initialize a provider client.
            print(json.dumps({'completed': 0, 'providerCalls': 0, 'independentAsrPerformed': False,
                              'exactAliasEvidenceSha256': alias['sha256']})); return
        config = AppConfig.from_env()
        client = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, formal_audio_internal_token=config.INTERNAL_API_TOKEN)
        results = []
        for entry in entries:
            policy_version = policy_for_plan(entry.get('requestPlan') or plan)['policyVersion']
            folder = args.output / entry['request']['requestId']
            if course_exists(folder / 'result.json'):
                result = read(folder / 'result.json')
            else:
                response = dispatch_once(client, entry=entry, directory=folder, policy_version=policy_version,
                    native_audio_directory=args.native_audio_directory,
                    paid_budget=read(args.paid_budget) if args.paid_budget else None)
                original = next(e for e in audit['segments'] if (e['sceneId'], e['actionId']) == (entry['sceneId'], entry['actionId']))
                result = {**entry, 'asr': response, 'asrSha256': digest(response), 'observedAt': now_ms(),
                    'comparison': compare_transcript(plan, original['text'], response['transcript'])}
                immutable(folder / 'result.json', result)
            results.append(result)
            print(json.dumps({'completed': len(results), 'actionId': entry['actionId'],
                'transcript': result['asr']['transcript'], 'similarityBps': result['comparison']['similarityBps'],
                'passed': result['comparison']['passed']}, ensure_ascii=False), flush=True)
        manifest_path = args.output / 'recheck.json'
        completed_at = read(manifest_path)['createdAt'] if course_exists(manifest_path) else now_ms()
        manifest = seal({'schemaVersion': SCHEMA_ALIAS if intent['schemaVersion'] == INTENT_SCHEMA_ALIAS else SCHEMA,
                         'intent': intent, 'segments': results, 'createdAt': completed_at})
        validate_asr_recheck(manifest, plan=plan, classroom=classroom, audit=audit,
            expected_source_sha256=args.source_sha256, now_ms=now_ms())
        # Re-read source/plan/original audit after calls; concurrent edits never
        # turn previously collected evidence into acceptance of a new classroom.
        if digest(read(args.classroom)) != args.source_sha256 or read(args.audit) != audit or read(args.audio_directory / 'textbook-preview-audio/plan.json') != plan:
            raise RuntimeError('Source changed during ASR recheck; original evidence retained')
        immutable(manifest_path, manifest)
        print(json.dumps({'completed': len(results), 'passed': all(e['comparison']['passed'] for e in results),
            'sha256': manifest['sha256'], 'humanListeningVerified': False, 'perceptualToneVerified': False,
            'billingAmountKnown': False, 'budgetLedgerRequested': args.paid_budget is not None}))


if __name__ == '__main__':
    main()
