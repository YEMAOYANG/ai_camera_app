"""Verify paid audio from an incomplete private preview without certifying it.

This pure preparation gate makes no dispatch, storage or publication changes.
Callers must independently validate the author's target scene ledger and persist
both source evidence and this result immutably before binding any audio.
"""
from copy import deepcopy
import hashlib
import io
import re
from urllib.parse import urlparse
import wave

from content.textbook_catalog import digest
from content.textbook_preview_audio_contract import resolve_audio_contract, tts_request_id


SCHEMA = 'mira.textbook.partial-audio-inheritance.v1'
DECLARATION_SCHEMA = 'mira.textbook.partial-audio-parent.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')


def partial_declaration(proof):
    """Freeze only parent evidence known before target preview/plan hashing."""
    fields = ('sourcePreviewKey', 'sourceClassroomSha256', 'sourcePlanSha256',
              'sourceDatabaseReceiptsSha256', 'sourceCheckpointReceiptsSha256', 'segments')
    if not isinstance(proof, dict) or proof.get('schemaVersion') != SCHEMA:
        raise ValueError('partial_audio_proof_invalid')
    return {'schemaVersion': DECLARATION_SCHEMA, **{field: deepcopy(proof[field]) for field in fields}}


def _core(room):
    result = deepcopy(room)
    result.pop('createdAt', None)
    for scene in result['scenes']:
        for action in scene.get('actions', []):
            if action.get('type') == 'speech':
                for key in ('audioId', 'audioUrl', 'audioMetadata'):
                    action.pop(key, None)
    return result


def _actions(room):
    found = {}
    for scene in room['scenes']:
        for action in scene.get('actions', []):
            if action.get('type') != 'speech':
                continue
            key = (scene['id'], action['id'])
            if key in found or not isinstance(action.get('text'), str) or not action['text'].strip():
                raise ValueError('partial_audio_invalid_action')
            found[key] = action
    return found


def _receipts(receipts):
    if not isinstance(receipts, list):
        raise ValueError('partial_audio_invalid_receipts')
    result = {}
    for item in receipts:
        if not isinstance(item, dict) or not isinstance(item.get('requestId'), str) or item['requestId'] in result:
            raise ValueError('partial_audio_duplicate_receipt')
        result[item['requestId']] = item
    return result


def _check_wav(raw, sha):
    if not isinstance(raw, bytes) or not SHA.fullmatch(str(sha)) or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('partial_audio_wav_hash_mismatch')
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            if wav.getnframes() <= 0 or wav.getframerate() <= 0 or wav.getnchannels() <= 0:
                raise ValueError('partial_audio_empty_wav')
    except (wave.Error, EOFError) as exc:
        raise ValueError('partial_audio_invalid_wav') from exc


def validate_partial_repair_chain(*, source_input, source_room, target_input, target_room, chain):
    """Bind the frozen repair summary to both original and derived stages.

    The registrar separately verifies every native event, patch operation and
    receipt before making this summary. Archive those originals as well; this
    portable check does not pretend to replay absent operation bytes.
    """
    link = target_input.get('partialRevisionSource', {})
    identity = link.get('identity', {})
    author = source_input.get('authoring', {})
    stage = author.get('stageId')
    rebuilt = deepcopy(target_room)
    rebuilt['id'] = rebuilt['stage']['id'] = stage
    for scene in rebuilt['scenes']:
        scene['stageId'] = stage
    if (not isinstance(chain, dict) or chain.get('schemaVersion') != 'mira.textbook.partial-preview-repair-chain.v1'
            or not isinstance(chain.get('patches'), list) or not chain['patches']
            or link.get('chainSha256') != digest(chain) or link.get('parentClassroomSha256') != digest(source_room)
            or identity.get('schemaVersion') != 'mira.textbook.partial-preview-identity.v1'
            or identity.get('parentPreviewKey') != source_input.get('previewKey')
            or identity.get('sourceStageId') != stage or identity.get('teachingRevision') != target_input.get('teachingRevision')
            or identity.get('candidateSha256') != target_input.get('authoringCandidate', {}).get('sha256')
            or identity.get('targetStageSha256') != digest(rebuilt)
            or chain.get('stageId') != stage or chain.get('sessionId') != author.get('sessionId')
            or chain.get('sourceCoreSha256') != digest(_core(source_room))
            or chain.get('targetSha256') != digest(rebuilt)
            or not SHA.fullmatch(str(chain.get('frozenFileSha256')))):
        raise ValueError('partial_audio_repair_chain_invalid')
    return True


def verify_partial_audio(*, source_input, source_room, source_room_sha256, source_plan,
                         database_receipts, checkpoint_receipts, target_input, target_room,
                         target_plan, get_receipt, get_audio, _media_hashes=None):
    """Return verified unchanged clips; audio approval and ASR remain outstanding.

    ``get_receipt`` and ``get_audio`` must perform read-only retrieval of the
    exact original request and WAV. The output binds their verified data to both
    immutable plans, not to any fabricated target request or transcript.
    """
    if (digest(source_room) != source_room_sha256
            or source_input.get('previewKey') != source_plan.get('previewKey')
            or digest({k: v for k, v in source_input.items() if k not in ('previewKey', 'requirement')}) != source_input.get('previewKey')
            or source_input.get('sourceSha256') != source_plan.get('classroomSha256')
            or digest(_core(source_room)) != source_plan.get('coreSha256')):
        raise ValueError('partial_audio_source_changed')
    author = source_input.get('authoring', {})
    candidate = source_input.get('authoringCandidate', {})
    version = source_input.get('teachingRevision', '1')
    expected_id = 'tbadopt_' + digest({'schemaVersion': 'mira.textbook.operator-adoption-materialization.v1',
        'sourceStageId': author.get('stageId'), 'candidateSha256': candidate.get('sha256'),
        'teachingRevision': version})[:24]
    if (not SHA.fullmatch(str(candidate.get('sha256'))) or source_room.get('id') != expected_id
            or source_room.get('stage', {}).get('id') != expected_id):
        raise ValueError('partial_audio_source_materialization_invalid')
    source_contract = resolve_audio_contract(source_plan, source_input)
    target_contract = resolve_audio_contract(target_plan, target_input)
    if (source_contract['legacy'] or target_contract['legacy']
            or source_plan.get('previewKey') == target_plan.get('previewKey')
            or source_room.get('id') == target_room.get('id')
            or target_room.get('stage', {}).get('id') != target_room.get('id')
            or target_input.get('previewKey') != target_plan.get('previewKey')
            or digest({k: v for k, v in target_input.items() if k not in ('previewKey', 'requirement')}) != target_input.get('previewKey')
            or target_input.get('sourceSha256') != target_plan.get('classroomSha256')
            or target_input.get('sourceSha256') != digest(target_room)
            or digest(_core(target_room)) != target_plan.get('coreSha256')
            or source_plan.get('binding') != target_plan.get('binding')
            or source_plan.get('teacher') != target_plan.get('teacher')
            or source_plan.get('providerLanguagePolicy') != target_plan.get('providerLanguagePolicy')
            or source_plan.get('comparisonPolicy') != target_plan.get('comparisonPolicy')):
        raise ValueError('partial_audio_target_contract_changed')
    old, new = _actions(source_room), _actions(target_room)
    old_orders = {scene['id']: scene.get('order') for scene in source_room['scenes']}
    new_orders = {scene['id']: scene.get('order') for scene in target_room['scenes']}
    database, checkpoint = _receipts(database_receipts), _receipts(checkpoint_receipts)
    inherited = []
    for key, old_action in old.items():
        action = new.get(key)
        if action is None or action['text'] != old_action['text'] or old_orders.get(key[0]) != new_orders.get(key[0]):
            continue
        request = tts_request_id(source_plan, key[0], key[1], old_action['text'])
        receipt = database.get(request)
        if receipt is None:
            continue
        if receipt.get('status') != 'succeeded':
            raise ValueError('partial_audio_source_outcome_unresolved')
        if receipt.get('previewAudioIdentity') != {'planSha256': digest(source_plan), 'attempt': 1}:
            raise ValueError('partial_audio_source_request_changed')
        if old_action.get('audioId') not in (None, request):
            raise ValueError('partial_audio_source_binding_changed')
        if action.get('audioId') not in (None, request):
            raise ValueError('partial_audio_target_binding_changed')
        if old_action.get('audioId'):
            teacher = source_contract['teacher']
            metadata = {'providerId': teacher['tts']['providerId'], 'modelId': teacher['tts']['modelId'],
                        'voiceId': teacher['voiceId'], 'fallbackUsed': False}
            if (old_action.get('audioMetadata') != {'schemaVersion': 'mira.openmaic.speech-audio.v1', **metadata}
                    or urlparse(old_action.get('audioUrl', '')).path !=
                        f"/api/classroom-media/{source_room['id']}/audio/{request}.wav"):
                raise ValueError('partial_audio_source_binding_changed')
        provider = get_receipt(request)
        if (not isinstance(provider, dict) or provider.get('requestId') != request
                or provider.get('status') != 'succeeded' or provider.get('audioSha256') != receipt.get('audioSha256')
                or provider.get('mimeType') != 'audio/wav'):
            raise ValueError('partial_audio_provider_evidence_changed')
        cp = checkpoint.get(request)
        if cp is not None and cp != receipt:
            common = set(cp) & set(receipt)
            if (cp.get('status') != 'unknown' or any(cp[k] != receipt[k] for k in common
                    if k not in ('status', 'audioSha256')) or cp.get('audioSha256') not in (None, receipt['audioSha256'])):
                raise ValueError('partial_audio_checkpoint_conflict')
        if _media_hashes is not None:
            # This checks a release's declared reviewed-source hash only. The
            # release/remote object reader must independently verify bytes.
            if _media_hashes.get(key) != receipt['audioSha256']:
                raise ValueError('partial_audio_release_media_changed')
        else:
            raw = get_audio(request, receipt['audioSha256'])
            _check_wav(raw, receipt['audioSha256'])
        inherited.append({'sceneId': key[0], 'actionId': key[1],
            'textSha256': hashlib.sha256(old_action['text'].strip().encode('utf-8')).hexdigest(),
            'sourceRequestId': request, 'audioSha256': receipt['audioSha256'],
            'sourceReceiptSha256': digest(receipt), 'providerReceiptSha256': digest(provider)})
    body = {'schemaVersion': SCHEMA, 'sourcePreviewKey': source_plan['previewKey'],
        'sourceClassroomSha256': source_room_sha256, 'sourcePlanSha256': digest(source_plan),
        'sourceDatabaseReceiptsSha256': digest(database_receipts),
        'sourceCheckpointReceiptsSha256': digest(checkpoint_receipts),
        'targetPreviewKey': target_plan['previewKey'], 'targetCoreSha256': target_plan['coreSha256'],
        'targetPlanSha256': digest(target_plan), 'segments': inherited,
        'asrStatus': 'not_performed', 'publicationAllowed': False}
    return {**body, 'sha256': digest(body)}


def verify_partial_audio_metadata(*, media_hashes, **kwargs):
    """Validate portable parent metadata against a release media manifest.

    This never claims to have read media bytes; publication and archive readers
    must separately validate each actual object against its declared SHA.
    """
    return verify_partial_audio(**kwargs, get_audio=None, _media_hashes=media_hashes)


def validate_partial_release(*, frozen, release):
    """Validate portable source metadata and real target ASR evidence.

    The release media manifest binds each reviewed source SHA; its actual bytes
    must still be checked by the media/remote-object reader independently.
    """
    audit = release.get('audioAudit', {})
    evidence, raw = audit.get('partialAudioEvidence'), audit.get('literalAudit')
    from content.textbook_user_audio_reconciliation import METHOD as USER_CONFIRMATION, validate_reconciliation
    user_confirmed = audit.get('acceptanceMethod') == USER_CONFIRMATION
    fields = {'sourceInput', 'sourceRoom', 'sourcePlan', 'databaseReceipts', 'checkpointReceipts',
              'targetInput', 'targetRoom', 'providerReceipts', 'proof', 'repairChain'}
    if (not isinstance(evidence, dict) or set(evidence) != fields or not isinstance(raw, dict)
            or frozen.get('partialAudioEvidenceSha256') != digest(evidence)
            or audit.get('acceptanceMethod') not in ('partial-parent-literal-asr', USER_CONFIRMATION)
            or frozen.get('audioAuditSha256') != raw.get('sha256')
            or audit.get('sha256') != raw.get('sha256')
            or raw.get('sha256') != digest({k: v for k, v in raw.items() if k != 'sha256'})
            or raw.get('passed') is not (not user_confirmed) or raw.get('sourceSha256') != frozen.get('sourceSha256')
            or raw.get('previewKey') != frozen.get('previewKey')
            or raw.get('partialAudioParentSha256') != digest(frozen.get('partialAudioParent'))
            or evidence['targetInput'].get('partialAudioParent') != frozen.get('partialAudioParent')):
        raise ValueError('partial_audio_release_evidence_invalid')
    providers, proof, plan = evidence['providerReceipts'], evidence['proof'], frozen['audioContract']
    confirmed = {}
    if user_confirmed:
        from core.security import now_ms
        reconciliation = audit.get('reconciliation', {})
        if (audit.get('literalPassed') is not False
                or frozen.get('sourceClassroomId') != evidence['targetRoom'].get('id')
                or frozen.get('audioAcceptance') != {'method': USER_CONFIRMATION,
                    'literalAuditSha256': raw['sha256'],
                    'reconciliationSha256': reconciliation.get('sha256')}):
            raise ValueError('partial_audio_user_confirmation_unbound')
        confirmed = validate_reconciliation(reconciliation, plan=plan,
            classroom=release['classroom'], audit=raw,
            expected_source_sha256=frozen['sourceSha256'], now_ms=now_ms(),
            expected_source_classroom_id=frozen['sourceClassroomId'])
    validate_partial_repair_chain(source_input=evidence['sourceInput'], source_room=evidence['sourceRoom'],
        target_input=evidence['targetInput'], target_room=evidence['targetRoom'], chain=evidence['repairChain'])
    if not isinstance(providers, dict) or set(providers) != {s['sourceRequestId'] for s in proof['segments']}:
        raise ValueError('partial_audio_release_provider_invalid')
    media = {item.get('path'): item for item in release.get('media', [])}
    scenes = {scene['id']: scene for scene in release['classroom']['scenes']}
    audits = {(entry['sceneId'], entry['actionId']): entry for entry in raw.get('segments', [])}
    media_hashes = {}
    from content.textbook_preview_audio_contract import audit_contract_identity, validate_v2_audit_segment
    all_speech = {(s['id'], a['id']): a for s in release['classroom']['scenes']
                  for a in s.get('actions', []) if a.get('type') == 'speech'}
    if (raw.get('schemaVersion') != 'mira.textbook.audio-audit.v2'
            or raw.get('contract') != audit_contract_identity(plan)
            or len(audits) != len(raw.get('segments', [])) or set(audits) != set(all_speech)
            or any(not validate_v2_audit_segment(plan, action, audits[key], scene_id=key[0]) and key not in confirmed
                   for key, action in all_speech.items())):
        raise ValueError('partial_audio_release_audit_incomplete')
    for segment in proof['segments']:
        key = segment['sceneId'], segment['actionId']
        scene = scenes.get(key[0], {})
        matches = [a for a in scene.get('actions', []) if a.get('id') == key[1] and a.get('type') == 'speech']
        if len(matches) != 1:
            raise ValueError('partial_audio_release_action_missing')
        action = matches[0]
        asset = media.get(action.get('audioUrl'), {})
        media_hashes[key] = asset.get('sourceSha256', asset.get('sha256'))
        source_scene = next(s for s in evidence['sourceRoom']['scenes'] if s['id'] == key[0])
        identity = {'sourceClassroomId': evidence['sourceRoom']['id'],
                    'sourceClassroomSha256': evidence['sourcePlan']['classroomSha256'],
                    'sourceSceneOrder': source_scene['order'], 'sourcePreviewKey': evidence['sourcePlan']['previewKey'],
                    'sourceReceiptSha256': segment['sourceReceiptSha256'],
                    'parentDeclarationSha256': digest(frozen['partialAudioParent'])}
        entry = audits.get(key, {})
        if (action.get('audioId') != segment['sourceRequestId'] or entry.get('partialAudioParent') != identity
                or entry.get('audioSha256') != segment['audioSha256']
                or (not validate_v2_audit_segment(plan, action, entry, scene_id=key[0]) and key not in confirmed)):
            raise ValueError('partial_audio_release_asr_invalid')
    inherited_keys = {(s['sceneId'], s['actionId']) for s in proof['segments']}
    if any(entry.get('partialAudioParent') is not None for key, entry in audits.items() if key not in inherited_keys):
        raise ValueError('partial_audio_release_unexpected_parent')
    calculated = verify_partial_audio_metadata(media_hashes=media_hashes,
        source_input=evidence['sourceInput'], source_room=evidence['sourceRoom'],
        source_room_sha256=proof['sourceClassroomSha256'], source_plan=evidence['sourcePlan'],
        database_receipts=evidence['databaseReceipts'], checkpoint_receipts=evidence['checkpointReceipts'],
        target_input=evidence['targetInput'], target_room=evidence['targetRoom'], target_plan=plan,
        get_receipt=lambda request: providers[request])
    if calculated != proof or frozen.get('partialAudioParent') != partial_declaration(proof):
        raise ValueError('partial_audio_release_parent_changed')
    return {'segmentCount': len(proof['segments']), 'sourcePreviewKey': proof['sourcePreviewKey']}
