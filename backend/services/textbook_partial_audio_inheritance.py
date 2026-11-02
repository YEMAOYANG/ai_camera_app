"""Read and revalidate an immutable, unaudited partial-TTS parent archive."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from content.textbook_catalog import digest
from content.textbook_partial_audio_inheritance import (partial_declaration, validate_partial_repair_chain,
                                                        verify_partial_audio)
from core.errors import ApiError
from services.course_file_store import course_bytes, course_exists, course_text


def _fail():
    raise ApiError('textbook_partial_audio_invalid', '部分配音来源或音频摘要不一致，已停止', 409)


def load_partial_audio(folder, plan, *, frozen=None):
    """Load only an explicitly frozen parent. Never treat TTS as ASR approval."""
    archive = Path(folder) / 'partial-parent'
    intent = archive / 'target-input.json'
    if not course_exists(intent):
        if frozen and frozen.get('partialAudioParent') is not None:
            _fail()
        return None
    try:
        def read(name):
            return json.loads(course_text(archive / (name + '.json')))
        target_input, target_room = read('target-input'), read('target-room')
        source_input, source_room, source_plan = read('source-input'), read('source-room'), read('source-plan')
        db, checkpoint, providers, proof, chain = (read('database-receipts'), read('checkpoint-receipts'),
                                            read('provider-receipts'), read('proof'), read('repair-chain'))
        if frozen is not None and frozen != target_input:
            _fail()
        if not isinstance(providers, dict):
            _fail()
        validate_partial_repair_chain(source_input=source_input, source_room=source_room,
            target_input=target_input, target_room=target_room, chain=chain)
        calculated = verify_partial_audio(source_input=source_input, source_room=source_room,
            source_room_sha256=proof['sourceClassroomSha256'], source_plan=source_plan,
            database_receipts=db, checkpoint_receipts=checkpoint, target_input=target_input,
            target_room=target_room, target_plan=plan, get_receipt=lambda req: providers[req],
            get_audio=lambda req, _sha: course_bytes(archive / 'audio' / (req + '.wav')))
        if (calculated != proof or target_input.get('partialAudioParent') != partial_declaration(proof)
                or set(providers) != {s['sourceRequestId'] for s in proof['segments']}):
            _fail()
        evidence = {'sourceInput': source_input, 'sourceRoom': source_room, 'sourcePlan': source_plan,
                    'databaseReceipts': db, 'checkpointReceipts': checkpoint, 'targetInput': target_input,
                    'targetRoom': target_room, 'providerReceipts': providers, 'proof': proof, 'repairChain': chain}
        return {'sourceInput': source_input, 'sourceRoom': source_room, 'sourcePlan': source_plan,
                'targetInput': target_input, 'proof': proof,
                'evidence': evidence,
                'segments': {(s['sceneId'], s['actionId']): s for s in proof['segments']},
                'sourceReceipts': {r['requestId']: r for r in db}}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        _fail()


def verify_partial_segment(context, scene, action, receipt, folder):
    """Verify source TTS and target bytes, returning its true source ASR identity."""
    if context is None:
        return None
    segment = context['segments'].get((scene.get('id'), action.get('id')))
    if segment is None:
        return None
    source_scene = next((s for s in context['sourceRoom']['scenes'] if s['id'] == scene['id']), None)
    source_action = next((a for a in source_scene.get('actions', []) if a.get('id') == action['id']), None) if source_scene else None
    request = segment['sourceRequestId']
    teacher = context['sourcePlan']['teacher']
    metadata = {'schemaVersion': 'mira.openmaic.speech-audio.v1', 'providerId': teacher['tts']['providerId'],
                'modelId': teacher['tts']['modelId'], 'voiceId': teacher['voiceId'], 'fallbackUsed': False}
    try:
        if (source_action is None or source_action.get('text') != action.get('text')
                or source_scene.get('order') != scene.get('order') or action.get('audioId') != request
                or digest(receipt) != segment['sourceReceiptSha256']
                or receipt != context['sourceReceipts'].get(request)
                or receipt.get('audioSha256') != segment['audioSha256'] or action.get('audioMetadata') != metadata
                or urlparse(action.get('audioUrl', '')).path !=
                    f"/api/classroom-media/{Path(folder).parent.name}/audio/{request}.wav"
                or hashlib.sha256(course_bytes(Path(folder).parent / 'audio' / (request + '.wav'))).hexdigest()
                    != segment['audioSha256']):
            _fail()
    except (OSError, ValueError, TypeError):
        _fail()
    return {'sourceClassroomId': context['sourceRoom']['id'],
            'sourceClassroomSha256': context['sourcePlan']['classroomSha256'],
            'sourcePlan': context['sourcePlan'], 'sourceSceneOrder': source_scene['order'],
            'sourcePreviewKey': context['sourcePlan']['previewKey'],
            'sourceReceiptSha256': segment['sourceReceiptSha256'],
            'parentDeclarationSha256': digest(context['targetInput']['partialAudioParent'])}
