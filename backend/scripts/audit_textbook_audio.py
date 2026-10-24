"""Audit the existing preview WAVs with ASR. Never generates content or TTS."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import (asr_request_id, audit_contract_identity,
    check_receipt_language_policy, compare_transcript, pronunciation_client_options,
    resolve_audio_contract, validate_v2_audit_segment)
from content.textbook_pinyin_pronunciation import PLAN_SCHEMA as PINYIN_SCHEMA, validate_listening_review, validate_receipt_wav
from core.config import AppConfig
from core.database import Database
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from repositories.textbook_repository import TextbookRepository
from services.course_file_store import course_bytes, course_exists, course_text
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_preview_audio import atomic_json, verify_segment_receipt, segment_request_plan
from services.learning_media_materialization_service import asr_similarity_bps, validate_formal_wav
from services.textbook_operator_revision_service import load_inheritance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', required=True)
    parser.add_argument('--classroom-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--listening-review', type=Path, help='Required for the formal pinyin profile; exact current audio listening manifest')
    parser.add_argument('--collect-only', action='store_true',
                        help='Collect/cache raw ASR before pronunciation acceptance; does not create listening evidence or authorize publication')
    parser.add_argument('--strict-segment-gate', action='store_true',
                        help='Stop before the next ASR request when the current transcript comparison does not pass')
    parser.add_argument('--asr-reconciliation', type=Path,
                        help='Exact registered segment reconciliation used only by --strict-segment-gate')
    parser.add_argument('--preflight-existing', action='store_true',
                        help='Validate cached receipts and stop before the first missing ASR request')
    parser.add_argument('--recover-failed-asr',
                        help='One original failed ASR request ID; records one new request, retaining the raw failure')
    args = parser.parse_args()
    if args.collect_only and args.listening_review is not None:
        parser.error('--collect-only cannot be combined with --listening-review')
    if args.asr_reconciliation is not None and not args.strict_segment_gate:
        parser.error('--asr-reconciliation requires --strict-segment-gate')
    config = AppConfig.from_env()
    client = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                      formal_audio_internal_token=config.INTERNAL_API_TOKEN)
    preview = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)), client)
    row = preview.get(args.key)
    content = json.loads(row['classroom_json'])
    plan = json.loads(course_text(args.classroom_directory / row['classroom_id'] / 'textbook-preview-audio/plan.json'))
    contract = resolve_audio_contract(plan, json.loads(row['input_json']))
    inheritance = load_inheritance(args.classroom_directory / row['classroom_id'] / 'textbook-preview-audio',
                                   plan, frozen=json.loads(row['input_json']))
    if plan['previewKey'] != args.key:
        raise RuntimeError('Audio plan belongs to a different preview')
    receipts = {r['requestId']: r for r in json.loads(row['result_json'])['audioReceipts']}
    teacher = plan['teacher']
    listening = None
    if plan.get('schemaVersion') == PINYIN_SCHEMA:
        if args.listening_review is None and not args.collect_only:
            raise RuntimeError('Formal pinyin requires human listening evidence; ASR cannot approve pronunciation')
        if args.listening_review is not None:
            listening = json.loads(course_text(args.listening_review))
            heard = validate_listening_review(plan, content, listening, now_ms=now_ms())
            if any(item['audioSha256'] != receipts.get(item['ttsRequestId'], {}).get('audioSha256') for item in heard.values()):
                raise RuntimeError('Listening evidence does not match the current formal audio bytes')
    elif args.listening_review is not None:
        raise RuntimeError('Listening manifest is reserved for the versioned pinyin profile')
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'schemaVersion': 'mira.textbook.audio-audit.v1', 'previewKey': args.key,
              'sourceSha256': row['classroom_sha256'], 'segments': []}
    if not contract['legacy']:
        result.update(schemaVersion='mira.textbook.audio-audit.v2', contract=audit_contract_identity(plan))
    if listening is not None:
        result['listeningReview'] = listening
    if inheritance:
        result['operatorParentProvenanceSha256'] = inheritance['provenance']['sha256']
    reconciliation = (json.loads(course_text(args.asr_reconciliation))
                      if args.asr_reconciliation is not None else None)
    if args.recover_failed_asr:
        import re
        selected_path = args.output / (args.recover_failed_asr + '.json')
        if (contract['legacy'] or plan.get('schemaVersion') == PINYIN_SCHEMA
                or not re.fullmatch(r'[A-Za-z0-9_]+', args.recover_failed_asr)
                or not course_exists(selected_path)
                or json.loads(course_text(selected_path)).get('asr', {}).get('status') != 'failed'):
            raise RuntimeError('Recovery requires one cached terminal ASR rejection; no dispatch')
    reconciled = set()
    for scene in content['scenes']:
        for action in scene.get('actions', []):
            if action['type'] != 'speech':
                continue
            receipt = receipts[action['audioId']]
            if receipt['status'] != 'succeeded':
                raise RuntimeError('Current TTS receipt is not succeeded')
            inherited = verify_segment_receipt(plan, receipt, scene, action,
                args.classroom_directory / row['classroom_id'] / 'textbook-preview-audio', inheritance=inheritance)
            # Inherited segments already validate their original request plans
            # in the immutable ancestor archive. They perform no ASR request
            # and must not look for a fabricated target narration revision.
            request_plan = plan if inherited is not None else segment_request_plan(
                plan, receipt, args.classroom_directory / row['classroom_id'] / 'textbook-preview-audio', text=action['text'])
            client_options = pronunciation_client_options(request_plan)
            audio = course_bytes(args.classroom_directory / row['classroom_id'] / 'audio' / (action['audioId'] + '.wav'))
            if plan.get('schemaVersion') == PINYIN_SCHEMA:
                validate_receipt_wav(receipt, audio)
            sha = hashlib.sha256(audio).hexdigest()
            wav = validate_formal_wav(audio, mime_type='audio/wav', runtime_sha256=receipt['audioSha256'],
                download_sha256=sha, streamed_sha256=sha)
            request_id = asr_request_id(plan, action['audioId'], sha)
            path = args.output / (request_id + '.json')
            if inherited is not None:
                # Original raw ASR remains in the immutable parent archive.
                # Only this new aggregate gains target-policy evidence.
                entry = inherited
            elif course_exists(path):
                entry = json.loads(course_text(path))
                if entry['audioSha256'] != sha or entry['textSha256'] != hashlib.sha256(action['text'].strip().encode()).hexdigest():
                    raise RuntimeError('Audio audit identity changed')
            else:
                if args.preflight_existing:
                    print(json.dumps({'preflightExisting': True,
                        'completed': len(result['segments']), 'nextSceneId': scene['id'],
                        'nextActionId': action['id'], 'nextRequestId': request_id,
                        'reconciledSegments': len(reconciled), 'providerCalls': 0,
                        'publicationAllowed': False}, ensure_ascii=False))
                    return
                try:
                    found = client.get_formal_audio_asr(request_id, **client_options)
                except OpenMaicFullRuntimeError as exc:
                    if exc.status_code != 404:
                        raise
                    found = None
                if found is not None:
                    raise RuntimeError('Existing ASR call needs receipt recovery; will not dispatch again')
                # The durable transport records the claim before contacting ASR.
                response = client.start_formal_audio_asr(request_id=request_id, tts_request_id=action['audioId'],
                    classroom_id=row['classroom_id'], classroom_content_sha256=receipt.get('classroomContentSha256', plan['classroomSha256']),
                    subject=contract['subject'], teacher_profile_id=teacher['teacherProfile']['id'],
                    teacher_profile_version=teacher['teacherProfile']['version'], teacher_profile_sha256=teacher['teacherProfile']['contentHash'],
                    teacher_gender=teacher['teacherGender'], scene_id=scene['id'], scene_order=scene['order'],
                    action_id=action['id'], narration_segment_id=action['id'], audio_sha256=sha, **client_options)
                transcript = response.get('transcript', '')
                entry = {'sceneId': scene['id'], 'actionId': action['id'], 'ttsRequestId': action['audioId'],
                    'audioSha256': sha, 'textSha256': hashlib.sha256(action['text'].strip().encode()).hexdigest(),
                    'text': action['text'].strip(), 'transcript': transcript, 'durationMs': wav.duration_ms,
                    'similarityBps': asr_similarity_bps(action['text'], transcript), 'asr': response}
                atomic_json(path, entry)
            if inherited is None and entry.get('asr', {}).get('status') == 'failed':
                from content.textbook_asr_terminal_recovery import evidence, request_id as recovery_id
                recovery_path = args.output / (recovery_id(request_id) + '.json')
                if course_exists(recovery_path) or args.recover_failed_asr == request_id:
                    proof = evidence(entry, plan_sha256=digest(plan), action=action,
                        scene_id=scene['id'], expected_request_id=request_id, audio_sha256=sha)
                    if course_exists(recovery_path):
                        entry = json.loads(course_text(recovery_path))
                    else:
                        if args.preflight_existing:
                            raise RuntimeError('ASR recovery is missing; preflight performs no dispatch')
                        original = client.get_formal_audio_asr(request_id, **client_options)
                        if original.get('status') != 'failed':
                            raise RuntimeError('Authoritative original ASR is not terminal failed; no dispatch')
                        recovery_request = proof['requestId']
                        try:
                            found = client.get_formal_audio_asr(recovery_request, **client_options)
                        except OpenMaicFullRuntimeError as exc:
                            if exc.status_code != 404:
                                raise
                            found = None
                        intent_path = args.output / (recovery_request + '.intent.json')
                        if found is not None or course_exists(intent_path):
                            raise RuntimeError('Existing ASR recovery needs receipt recovery; will not dispatch again')
                        with intent_path.open('x') as stream:
                            stream.write(canonical(proof))
                            stream.flush()
                            import os
                            os.fsync(stream.fileno())
                        response = client.start_formal_audio_asr(request_id=recovery_request,
                            tts_request_id=action['audioId'], classroom_id=row['classroom_id'],
                            classroom_content_sha256=receipt.get('classroomContentSha256', plan['classroomSha256']),
                            subject=contract['subject'], teacher_profile_id=teacher['teacherProfile']['id'],
                            teacher_profile_version=teacher['teacherProfile']['version'],
                            teacher_profile_sha256=teacher['teacherProfile']['contentHash'],
                            teacher_gender=teacher['teacherGender'], scene_id=scene['id'], scene_order=scene['order'],
                            action_id=action['id'], narration_segment_id=action['id'], audio_sha256=sha, **client_options)
                        transcript = response.get('transcript', '')
                        entry = {**entry, 'transcript': transcript,
                            'similarityBps': asr_similarity_bps(action['text'], transcript),
                            'asr': response, 'asrTerminalRecovery': proof}
                        atomic_json(recovery_path, entry)
            if not contract['legacy']:
                # Recompute locally without overwriting the raw ASR cache or
                # dispatching another call when only comparison policy differs.
                comparison = compare_transcript(plan, action['text'], entry.get('transcript'))
                entry = {**entry, 'comparison': comparison, 'similarityBps': comparison['similarityBps']}
                if request_plan.get('pronunciationPolicySha256') != plan.get('pronunciationPolicySha256'):
                    entry = {**entry, 'requestPlan': request_plan, 'ttsAttempt': receipt['previewAudioIdentity']['attempt']}
                if inherited is None:
                    validate_v2_audit_segment(plan, action, entry, scene_id=scene['id'])
                # Otherwise verify_segment_receipt already rebuilt the full
                # published ancestor proof; its child plan belongs to that
                # original parent, never to this visual-only target plan.
            result['segments'].append(entry)
            comparison_passed = (entry['similarityBps'] >= 8500 if contract['legacy']
                                 else entry['comparison']['passed'])
            acceptance_method = None
            if not comparison_passed and reconciliation is not None:
                from content.textbook_english_asr_reconciliation import validate_segment_evidence
                accepted = validate_segment_evidence(reconciliation, plan=plan, classroom=content,
                    audit_entry=entry, expected_source_sha256=row['classroom_sha256'], now_ms=now_ms())
                key = (scene['id'], action['id'])
                if key in accepted:
                    reconciled.add(key)
                    acceptance_method = accepted[key]['acceptanceMethod']
            print(json.dumps({'completed': len(result['segments']), 'similarityBps': entry['similarityBps'],
                              'comparisonPassed': comparison_passed, 'acceptedBy': acceptance_method,
                              'status': entry['asr']['status']}, ensure_ascii=False), flush=True)
            if entry['asr']['status'] != 'succeeded':
                raise RuntimeError('ASR outcome is not succeeded; no retry')
            if args.strict_segment_gate and not comparison_passed and acceptance_method is None:
                raise RuntimeError('ASR comparison did not pass; no further dispatch')
    result['passed'] = bool(result['segments']) and all(
        s['similarityBps'] >= 8500 if contract['legacy'] else s['comparison']['passed'] for s in result['segments'])
    result['sha256'] = digest(result)
    aggregate = args.output / 'audit.json'
    # Reuse identical archived evidence. If it differs, read its version before
    # atomic_json applies the existing guarded writer; never create a shadow.
    if not course_exists(aggregate) or course_bytes(aggregate) != canonical(result).encode('utf-8'):
        atomic_json(aggregate, result)
    print(json.dumps({'passed': result['passed'], 'segments': len(result['segments']), 'auditSha256': result['sha256'],
                      'collectionOnly': args.collect_only, 'pronunciationAcceptancePending': args.collect_only,
                      'reconciledSegments': len(reconciled), 'publicationAllowed': False}))


if __name__ == '__main__':
    main()
