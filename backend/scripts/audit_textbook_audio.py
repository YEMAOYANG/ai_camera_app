"""Audit the existing preview WAVs with ASR. Never generates content or TTS."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.textbook_catalog import canonical, digest
from core.config import AppConfig
from core.database import Database
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from repositories.textbook_repository import TextbookRepository
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_preview_audio import atomic_json
from services.learning_media_materialization_service import asr_similarity_bps, validate_formal_wav


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key', required=True)
    parser.add_argument('--classroom-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = AppConfig.from_env()
    client = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                      formal_audio_internal_token=config.INTERNAL_API_TOKEN)
    preview = TextbookPreviewService(TextbookRepository(Database(config.DATABASE_URL)), client)
    row = preview.get(args.key)
    content = json.loads(row['classroom_json'])
    plan = json.loads((args.classroom_directory / row['classroom_id'] / 'textbook-preview-audio/plan.json').read_text())
    receipts = {r['requestId']: r for r in json.loads(row['result_json'])['audioReceipts']}
    teacher = plan['teacher']
    args.output.mkdir(parents=True, exist_ok=True)
    result = {'schemaVersion': 'mira.textbook.audio-audit.v1', 'previewKey': args.key,
              'sourceSha256': row['classroom_sha256'], 'segments': []}
    for scene in content['scenes']:
        for action in scene.get('actions', []):
            if action['type'] != 'speech':
                continue
            receipt = receipts[action['audioId']]
            audio = (args.classroom_directory / row['classroom_id'] / 'audio' / (action['audioId'] + '.wav')).read_bytes()
            sha = hashlib.sha256(audio).hexdigest()
            wav = validate_formal_wav(audio, mime_type='audio/wav', runtime_sha256=receipt['audioSha256'],
                download_sha256=sha, streamed_sha256=sha)
            request_id = 'tbasr_' + digest({'tts': action['audioId'], 'audio': sha})
            path = args.output / (request_id + '.json')
            if path.exists():
                entry = json.loads(path.read_text())
                if entry['audioSha256'] != sha or entry['textSha256'] != hashlib.sha256(action['text'].strip().encode()).hexdigest():
                    raise RuntimeError('Audio audit identity changed')
            else:
                try:
                    found = client.get_formal_audio_asr(request_id)
                except OpenMaicFullRuntimeError as exc:
                    if exc.status_code != 404:
                        raise
                    found = None
                if found is not None:
                    raise RuntimeError('Existing ASR call needs receipt recovery; will not dispatch again')
                # The durable transport records the claim before contacting ASR.
                response = client.start_formal_audio_asr(request_id=request_id, tts_request_id=action['audioId'],
                    classroom_id=row['classroom_id'], classroom_content_sha256=plan['classroomSha256'],
                    subject='chinese', teacher_profile_id=teacher['teacherProfile']['id'],
                    teacher_profile_version=teacher['teacherProfile']['version'], teacher_profile_sha256=teacher['teacherProfile']['contentHash'],
                    teacher_gender=teacher['teacherGender'], scene_id=scene['id'], scene_order=scene['order'],
                    action_id=action['id'], narration_segment_id=action['id'], audio_sha256=sha)
                transcript = response.get('transcript', '')
                entry = {'sceneId': scene['id'], 'actionId': action['id'], 'ttsRequestId': action['audioId'],
                    'audioSha256': sha, 'textSha256': hashlib.sha256(action['text'].strip().encode()).hexdigest(),
                    'text': action['text'].strip(), 'transcript': transcript, 'durationMs': wav.duration_ms,
                    'similarityBps': asr_similarity_bps(action['text'], transcript), 'asr': response}
                atomic_json(path, entry)
            result['segments'].append(entry)
            print(json.dumps({'completed': len(result['segments']), 'similarityBps': entry['similarityBps'],
                              'status': entry['asr']['status']}, ensure_ascii=False), flush=True)
            if entry['asr']['status'] != 'succeeded':
                raise RuntimeError('ASR outcome is not succeeded; no retry')
    result['passed'] = all(s['similarityBps'] >= 8500 for s in result['segments'])
    result['sha256'] = digest(result)
    atomic_json(args.output / 'audit.json', result)
    print(json.dumps({'passed': result['passed'], 'segments': len(result['segments']), 'auditSha256': result['sha256']}))


if __name__ == '__main__':
    main()
