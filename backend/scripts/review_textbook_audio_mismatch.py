#!/usr/bin/env python3
"""One additional recognition of known audio with an explicit textual mismatch.

This provides separate semantic-review evidence. It never synthesizes speech,
changes the original audio audit, approves content, or publishes a classroom.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import digest
from scripts.narrate_textbook_batch import load_candidate, DEFAULT_CLASSROOM_DIRECTORY
from services.learning_media_materialization_service import asr_similarity_bps
from services.textbook_batch_audio import (
    _asr_request_id, _external_once, _known_success, _segment_requests,
    audio_language_policy_from_plan, build_audio_plan, save_json,
)

SCHEMA = 'mira.textbook.semantic-audio-recheck.v1'


def preflight(candidate, scene_id, segment_id):
    candidate = Path(candidate).resolve()
    frozen, state, room = load_candidate(candidate)
    directory = candidate / 'audio-audit'
    plan = json.loads((directory / 'plan.json').read_text())
    audit = json.loads((directory / 'audit.json').read_text())
    if plan != build_audio_plan(room, frozen['binding'], state['runtimeOrigin'],
                               audio_language_policy=audio_language_policy_from_plan(plan)):
        raise ValueError('semantic_recheck_source_changed')
    if audit['planSha256'] != digest(plan) or audit['completedSegments'] != audit['expectedSegments']:
        raise ValueError('semantic_recheck_requires_completed_audit')
    item = next(w for w in plan['workload'] if (w['sceneId'], w['id']) == (scene_id, segment_id))
    segment = next(s for s in audit['segments'] if (s['sceneId'], s['segmentId']) == (scene_id, segment_id))
    if segment.get('inheritedFrom') or segment.get('asrReconciliation'):
        raise ValueError('semantic_recheck_requires_original_unreconciled_audio')
    teacher = get_formal_subject_qwen_voice_identity(frozen['binding']['subject'])
    tts_id, identity, text_hash, tts_payload = _segment_requests(plan, item, teacher)
    tts = _known_success(directory, tts_id, tts_payload)
    asr_id = _asr_request_id(plan, tts_id, tts['audioSha256'])
    payload = {**identity, 'request_id':asr_id, 'tts_request_id':tts_id,
               'audio_sha256':tts['audioSha256']}
    asr = _known_success(directory, asr_id, payload)
    transcript = asr.get('transcript')
    if (not isinstance(transcript, str) or not transcript.strip()
            or hashlib.sha256(transcript.encode()).hexdigest() != asr.get('transcriptSha256')
            or segment['ttsRequestId'] != tts_id or segment['asrRequestId'] != asr_id
            or segment['textSha256'] != text_hash or segment['audioSha256'] != tts['audioSha256']):
        raise ValueError('semantic_recheck_receipt_changed')
    score = asr_similarity_bps(item['text'], transcript)
    # Low-score cases already have a separate, bounded reconciliation path.
    if not 8500 <= score < 10000 or score != segment['literalScoreBps']:
        raise ValueError('semantic_recheck_requires_actual_mismatch')
    audio = Path(DEFAULT_CLASSROOM_DIRECTORY) / room['id'] / 'audio' / (tts_id + '.wav')
    if hashlib.sha256(audio.read_bytes()).hexdigest() != tts['audioSha256']:
        raise ValueError('semantic_recheck_audio_changed')
    request_id = 'tbbsem_' + digest({'purpose':SCHEMA, 'originalAsrRequestId':asr_id,
                                    'audioSha256':tts['audioSha256']})
    output = candidate / 'audio-semantic-recheck'
    evidence = {'schemaVersion':SCHEMA, 'planSha256':digest(plan), 'sourceSha256':plan['sourceSha256'],
                'sceneId':scene_id, 'segmentId':segment_id, 'textSha256':text_hash,
                'audioSha256':tts['audioSha256'], 'originalTtsRequestId':tts_id,
                'originalAsrRequestId':asr_id, 'originalAsrReceiptSha256':digest(asr),
                'expectedText':item['text'], 'originalTranscript':transcript,
                'requestId':request_id, 'publicationAllowed':False,
                'semanticReviewStatus':'pending', 'humanListeningVerified':False}
    return output, evidence, {**payload, 'request_id':request_id}, state['runtimeOrigin']


def review(candidate, scene_id, segment_id, runtime):
    output, evidence, payload, origin = preflight(candidate, scene_id, segment_id)
    if runtime.base_url != origin:
        raise ValueError('semantic_recheck_runtime_mismatch')
    output.mkdir(exist_ok=True)
    with (output / (evidence['requestId'] + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = output / (evidence['requestId'] + '.source.json')
        if source.exists():
            if json.loads(source.read_text()) != evidence:
                raise ValueError('semantic_recheck_evidence_changed')
        else:
            save_json(source, evidence)
        result = _external_once(runtime, output / (evidence['requestId'] + '.json'),
                                evidence['requestId'], 'asr', payload)
        if (not isinstance(result.get('transcript'), str) or not result['transcript'].strip()
                or hashlib.sha256(result['transcript'].encode()).hexdigest() != result.get('transcriptSha256')):
            raise ValueError('semantic_recheck_transcript_invalid')
        # The fixed request/checkpoint determines the one permitted call. Changing
        # a reason, output name, timestamp, or caller cannot create another slot.
        return {**evidence, 'newTranscript':result['transcript'],
                'newReceiptSha256':digest(result), 'receiptPath':str(output / (evidence['requestId'] + '.json'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-directory', type=Path, required=True)
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--segment-id', required=True)
    args = parser.parse_args()
    # Validate local evidence before loading runtime/provider configuration.
    preflight(args.candidate_directory, args.scene_id, args.segment_id)
    from core.config import AppConfig
    from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
    config = AppConfig.from_env()
    runtime = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                       formal_audio_internal_token=config.INTERNAL_API_TOKEN)
    print(json.dumps(review(args.candidate_directory, args.scene_id, args.segment_id, runtime), ensure_ascii=False))


if __name__ == '__main__':
    main()
