"""Verify the ancestry of a private, partially narrated preview repair.

This module performs no generation, paid requests, publication, or source
mutation. A separate registrar must recheck the returned fences immediately
before reserving an independent preview; this verifier is not a release gate.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from content.textbook_catalog import digest
from content.textbook_authoring_candidate import _find_job, validate_authoring_candidate
from content.textbook_partial_audio_inheritance import partial_declaration, verify_partial_audio
from content.textbook_preview import operator_media, operator_preview_input, preview_checks
from content.textbook_preview_audio_contract import new_audio_plan, pronunciation_client_options
from core.errors import ApiError
from services.course_file_store import course_bytes
from services.textbook_preview_audio import core_content


def _fail():
    raise ApiError('textbook_partial_revision_invalid', '原作者修订链无法核实，已停止创建新预览', 409)


def _file(folder, name):
    path = folder / name
    if folder.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        _fail()
    return path.read_bytes()


def _apply(scene, ops):
    """Reproduce only the bounded operations allowed by the native operator."""
    result = deepcopy(scene)
    if not isinstance(ops, list) or not ops or len(ops) > 128:
        _fail()
    action_sets = 0
    for op in ops:
        if not isinstance(op, dict):
            _fail()
        if op.get('op') == 'str_replace' and op.get('path') == '/content/html':
            old, new = op.get('oldText'), op.get('newText')
            html = result.get('content', {}).get('html')
            if (not isinstance(old, str) or not old or not isinstance(new, str)
                    or not isinstance(html, str) or html.count(old) != 1 or op.get('replaceAll')):
                _fail()
            result['content']['html'] = html.replace(old, new, 1)
        elif op.get('op') == 'set' and op.get('path') == '/actions' and isinstance(op.get('value'), list):
            action_sets += 1
            original, replacement = result.get('actions', []), op['value']
            if action_sets > 1 or len(replacement) < len(original) or len(replacement) > 120:
                _fail()
            for index, action in enumerate(replacement):
                if not isinstance(action, dict):
                    _fail()
                if index >= len(original):
                    if (set(action) != {'id', 'type', 'text'} or action.get('type') != 'speech'
                            or not isinstance(action.get('id'), str) or not action['id'].strip()
                            or not isinstance(action.get('text'), str) or not action['text'].strip()):
                        _fail()
                elif original[index].get('type') == 'speech':
                    if (not isinstance(action.get('text'), str) or not action['text'].strip()
                            or {k: v for k, v in action.items() if k != 'text'}
                            != {k: v for k, v in original[index].items() if k != 'text'}):
                        _fail()
                elif action != original[index]:
                    _fail()
            result['actions'] = deepcopy(replacement)
        else:
            _fail()
    return result


def verify_reviewed_scene_chain(*, source_room, target_room, stage_id, session_id,
                                frozen_file_sha256, job_directory, events):
    """Bind every change to the original parent's exact scenes and native events.

    Caller must independently read the source from the preview DB, read target
    with the original owner and run ``validate_authoring_candidate``. Events
    must be the complete authenticated native SSE backlog, not request input.
    """
    if not isinstance(events, list):
        _fail()
    original = core_content(source_room)
    if original.get('id') != original.get('stage', {}).get('id'):
        _fail()
    original['id'] = original['stage']['id'] = stage_id
    for scene in original.get('scenes', []):
        scene['stageId'] = stage_id
    if (not isinstance(target_room, dict) or target_room.get('id') != stage_id
            or target_room.get('stage', {}).get('id') != stage_id
            or original.get('stage') != target_room.get('stage')
            or [s.get('id') for s in original.get('scenes', [])]
            != [s.get('id') for s in target_room.get('scenes', [])]):
        _fail()
    source_scenes = {s['id']: s for s in original['scenes']}
    target_scenes = {s['id']: s for s in target_room['scenes']}
    if len(source_scenes) != len(original['scenes']) or len(target_scenes) != len(target_room['scenes']):
        _fail()
    patches = Path(job_directory).resolve() / 'reviewed-patches'
    if patches.is_symlink() or not patches.is_dir():
        _fail()
    verified = []
    for scene_id, source in source_scenes.items():
        target = target_scenes[scene_id]
        if digest(source) == digest(target):
            continue
        current, last_seq, seen = source, 0, set()
        while digest(current) != digest(target):
            if digest(current) in seen:
                _fail()
            seen.add(digest(current))
            choices = [e for e in events if isinstance(e, dict) and e.get('type') == 'mira_textbook_reviewed_patch'
                       and type(e.get('id')) is int and e['id'] > last_seq and isinstance(e.get('data'), dict)
                       and e['data'].get('sceneId') == scene_id
                       and e['data'].get('beforeSceneSha256') == digest(current)]
            if len(choices) != 1:
                _fail()
            event = choices[0]
            d = event['data']
            op_sha = d.get('opsSha256')
            if (not isinstance(op_sha, str) or len(op_sha) != 64
                    or any(c not in '0123456789abcdef' for c in op_sha)
                    or d.get('stageId') != stage_id or d.get('sessionId') != session_id
                    or d.get('frozenFileSha256') != frozen_file_sha256):
                _fail()
            folder = patches / op_sha
            try:
                raw, receipt = _file(folder, 'ops.json'), json.loads(_file(folder, 'receipt.json'))
                before, after = json.loads(_file(folder, 'before.json')), json.loads(_file(folder, 'after.json'))
                op = json.loads(raw)
            except (OSError, ValueError, TypeError):
                _fail()
            if (hashlib.sha256(raw).hexdigest() != op_sha or receipt.get('status') != 'applied'
                    or receipt.get('eventSeq') != event['id'] or any(receipt.get(k) != v for k, v in d.items())
                    or op.get('target') != '/scenes/' + scene_id or op.get('expectedSceneSha256') != digest(current)
                    or before != current or digest(after) != d.get('afterSceneSha256')
                    or _apply(before, op.get('ops')) != after):
                _fail()
            verified.append({'eventSeq': event['id'], **d})
            current, last_seq = after, event['id']
        if current != target:
            _fail()
    normalized = deepcopy(target_room)
    normalized['scenes'] = [target_scenes[s['id']] for s in original['scenes']]
    if {k: v for k, v in original.items() if k != 'scenes'} != {k: v for k, v in normalized.items() if k != 'scenes'}:
        _fail()
    return {'schemaVersion': 'mira.textbook.partial-preview-repair-chain.v1',
            'sourceCoreSha256': digest(core_content(source_room)), 'targetSha256': digest(target_room),
            'sessionId': session_id, 'stageId': stage_id, 'frozenFileSha256': frozen_file_sha256,
            'patches': verified}


def _native_review_events(client, session_id):
    """Read the entire authenticated backlog; never trust an event list in a request."""
    from urllib.parse import quote
    events, frame, consumed = [], [], 0
    with client._open('/api/agent/sessions/' + quote(session_id, safe='') + '/events') as response:
        while True:
            line = response.readline(4 * 1024 * 1024 + 1)
            consumed += len(line)
            if not line or len(line) > 4 * 1024 * 1024 or consumed > 64 * 1024 * 1024:
                _fail()
            if line.strip():
                frame.append(line.decode('utf-8').rstrip('\r\n'))
                continue
            name = next((v[6:].strip() for v in frame if v.startswith('event:')), '')
            data = '\n'.join(v[5:].lstrip() for v in frame if v.startswith('data:'))
            frame = []
            if not data:
                continue
            obj = json.loads(data)
            if name == 'caught_up':
                if obj.get('degraded'):
                    _fail()
                return events
            if name == 'mira_textbook_reviewed_patch':
                events.append(obj)


def prepare_partial_revision(service, parent_key, new_revision, classroom_directory):
    """Read and validate everything needed for a later isolated registration.

    This step performs authenticated GETs and downloads only.  It does not
    reserve a version slot or write a classroom. The caller must independently
    revalidate the returned fences during registration.
    """
    from content.textbook_catalog import identifier
    from services.course_file_store import course_text
    if not isinstance(parent_key, str) or len(parent_key) != 64 or any(c not in '0123456789abcdef' for c in parent_key):
        _fail()
    if not identifier(new_revision):
        _fail()
    root = Path(classroom_directory).resolve()
    with service.repository.transaction() as conn:
        row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=?', (parent_key,)).fetchone()
        if row is None or row['runtime_origin'] != service.runtime.base_url:
            _fail()
        source_input = service.repository.parse(row['input_json'])
        source_room = service.repository.parse(row['classroom_json'])
        source_result = service.repository.parse(row['result_json'])
        manifest = service._manifest(conn, row['edition_id'], row['revision_id'])
        if (digest(source_room) != row['classroom_sha256'] or source_input.get('previewKey') != parent_key
                or source_input.get('teachingRevision', '1') == new_revision
                or source_result.get('audioPartial') is not True
                or source_result.get('audioStopCode') not in (None, 'textbook_preview_audio_invalid')
                or source_input.get('executionPolicy') != 'operator-authored-saved-classroom.v1'):
            _fail()
    author = source_input.get('authoring')
    if not isinstance(author, dict):
        _fail()
    stage_id, sid = author.get('stageId'), author.get('sessionId')
    source_folder = root / row['classroom_id'] / 'textbook-preview-audio'
    plan = json.loads(course_text(source_folder / 'plan.json'))
    checkpoint = json.loads(course_text(source_folder / 'receipts.json'))
    db_receipts = source_result.get('audioReceipts')
    if (not isinstance(db_receipts, list) or not db_receipts
            or any(not isinstance(r, dict) or r.get('status') != 'succeeded'
                   or not isinstance(r.get('requestId'), str) or not r['requestId'] for r in db_receipts)
            or len({r.get('requestId') for r in db_receipts}) != len(db_receipts)
            or not isinstance(checkpoint, list)):
        _fail()
    db_by_id = {r['requestId']: r for r in db_receipts}
    if any(not isinstance(r, dict) or not isinstance(r.get('requestId'), str)
           or r['requestId'] not in db_by_id
           or r.get('status') not in {'unknown', 'succeeded'} for r in checkpoint):
        _fail()
    target, protected = service._operator_adoption_classroom(stage_id, root, author, manifest, row['node_id'])
    candidate = validate_authoring_candidate(target, root, author, manifest, row['node_id'],
        output_root=service.authoring_output_root, runtime_origin=service.runtime.base_url)
    if candidate is None or protected is None or not isinstance(protected.get('lockedAssessments'), list):
        _fail()
    old_candidate = source_input.get('authoringCandidate')
    if (not isinstance(old_candidate, dict)
            or any(candidate.get(k) != old_candidate.get(k) for k in
                   ('contractSha256', 'interactionPolicySha256', 'interactionPolicyVersion'))):
        _fail()
    found = _find_job(service.authoring_output_root, row['edition_id'], row['revision_id'], row['node_id'],
                      sid, stage_id, True)
    if found is None:
        _fail()
    job, frozen, state = found
    if (frozen.get('binding', {}).get('teachingRevision') != source_input.get('teachingRevision', '1')
            or protected.get('teachingRevision') != source_input.get('teachingRevision', '1')):
        _fail()
    client = service.workbench_client_factory(frozen['origin'], job / 'owner.cookies')
    events = _native_review_events(client, sid)
    frozen_sha = hashlib.sha256(course_bytes(job / 'frozen.json')).hexdigest()
    chain = verify_reviewed_scene_chain(source_room=source_room, target_room=target, stage_id=stage_id,
        session_id=sid, frozen_file_sha256=frozen_sha, job_directory=job, events=events)
    if not chain['patches']:
        _fail()
    identity = {'schemaVersion': 'mira.textbook.partial-preview-identity.v1', 'parentPreviewKey': parent_key,
                'sourceStageId': stage_id, 'candidateSha256': candidate['sha256'],
                'targetStageSha256': digest(target), 'teachingRevision': new_revision}
    cid = 'tbpartial_' + digest(identity)[:24]
    clone = deepcopy(target)
    clone['id'] = clone['stage']['id'] = cid
    for scene in clone['scenes']:
        if scene.get('stageId') != stage_id:
            _fail()
        scene['stageId'] = cid
    media = operator_media(clone, root, author.get('imageProvenance'))
    target_input = operator_preview_input(manifest, row['node_id'], clone, media, author,
        teaching_revision=new_revision, authoring_candidate=candidate,
        verified_locked_assessments=protected['lockedAssessments'],
        verified_scene_types=[t for t in ('slide', 'interactive', 'quiz')
            if any(p.get('type') == t for p in protected['pagePlan'])])
    # The source proof is bound before the partial-audio declaration, avoiding
    # a dependency on either the new preview key or the new plan.
    target_input['partialRevisionSource'] = {'identity': identity, 'chainSha256': digest(chain),
                                            'parentClassroomSha256': row['classroom_sha256']}
    target_input['previewKey'] = digest({k: v for k, v in target_input.items()
                                         if k not in ('previewKey', 'requirement')})
    providers, wavs = {}, {}
    def get_receipt(request):
        if request not in providers:
            providers[request] = service.runtime.get_formal_audio_tts(request, **pronunciation_client_options(plan))
        return providers[request]
    def get_audio(request, sha):
        if request not in wavs:
            wavs[request] = service.runtime.download_formal_audio_tts(request, expected_sha256=sha)
        return wavs[request]
    def audio_plan(frozen_input):
        return new_audio_plan(preview_key=frozen_input['previewKey'], classroom_sha256=digest(clone),
                              core_sha256=digest(core_content(clone)), frozen_input=frozen_input)
    def verify(frozen_input, target_plan):
        return verify_partial_audio(source_input=source_input, source_room=source_room,
            source_room_sha256=row['classroom_sha256'], source_plan=plan,
            database_receipts=db_receipts, checkpoint_receipts=checkpoint,
            target_input=frozen_input, target_room=clone, target_plan=target_plan,
            get_receipt=get_receipt, get_audio=get_audio)
    initial = verify(target_input, audio_plan(target_input))
    target_input['partialAudioParent'] = partial_declaration(initial)
    target_input['previewKey'] = digest({k: v for k, v in target_input.items()
                                         if k not in ('previewKey', 'requirement')})
    target_plan = audio_plan(target_input)
    proof = verify(target_input, target_plan)
    if partial_declaration(proof) != target_input['partialAudioParent']:
        _fail()
    prompt = target_input['previewPrompt']
    checks = preview_checks(clone, prompt['expectedSceneCount'], media, prompt['expectedQuestionCount'],
                            required_scene_types=prompt.get('requiredSceneTypes'),
                            grade_code=target_input.get('gradeCode'))
    if any(x != 'speech_audio_missing' for x in checks['issues']):
        _fail()
    return {'identity': identity, 'parentKey': parent_key, 'parentClassroomSha256': row['classroom_sha256'],
            'sourceInput': source_input, 'sourceRoom': source_room, 'sourcePlan': plan,
            'databaseReceipts': db_receipts, 'checkpointReceipts': checkpoint,
            'chain': chain, 'targetInput': target_input, 'targetRoom': clone,
            'targetPlan': target_plan, 'proof': proof, 'providerReceipts': providers,
            'wavs': wavs, 'checks': checks}


def bind_inherited_audio(prepared, runtime_origin):
    """Bind only independently verified old request IDs to a new classroom."""
    room = deepcopy(prepared['targetRoom'])
    cid = room['id']
    teacher = prepared['targetPlan']['teacher']
    metadata = {'schemaVersion': 'mira.openmaic.speech-audio.v1',
                'providerId': teacher['tts']['providerId'], 'modelId': teacher['tts']['modelId'],
                'voiceId': teacher['voiceId'], 'fallbackUsed': False}
    segments = {(s['sceneId'], s['actionId']): s for s in prepared['proof']['segments']}
    receipts = {r['requestId']: r for r in prepared['databaseReceipts']}
    if len(segments) != len(prepared['proof']['segments']):
        _fail()
    found, inherited = set(), []
    for scene in room['scenes']:
        for action in scene.get('actions', []):
            identity = (scene['id'], action.get('id'))
            segment = segments.get(identity)
            if segment is None:
                continue
            request = segment['sourceRequestId']
            receipt = receipts.get(request)
            if (identity in found or action.get('type') != 'speech'
                    or hashlib.sha256(action['text'].strip().encode()).hexdigest() != segment['textSha256']
                    or not isinstance(receipt, dict) or digest(receipt) != segment['sourceReceiptSha256']
                    or hashlib.sha256(prepared['wavs'][request]).hexdigest() != segment['audioSha256']
                    or any(k in action for k in ('audioId', 'audioUrl', 'audioMetadata'))):
                _fail()
            found.add(identity)
            action.update(audioId=request,
                audioUrl=f"{runtime_origin}/api/classroom-media/{cid}/audio/{request}.wav",
                audioMetadata=deepcopy(metadata))
            inherited.append(deepcopy(receipt))
    if found != set(segments):
        _fail()
    return room, inherited


def register_partial_revision(service, parent_key, new_revision, regeneration, classroom_directory, *,
                              expected_preview_key, expected_stage_sha256, expected_parent_sha256):
    """Create one separate preview after rechecking all source and audio fences.

    No model dispatch or publication occurs here.  The parent lock, deterministic
    child identity, save-attempt marker, readback and DB slot prevent overwrite.
    """
    from core.security import now_ms
    from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
    from services.textbook_operator_revision_service import locked
    from services.textbook_partial_audio_inheritance import load_partial_audio
    from services.textbook_preview_visual_revision import immutable, json_bytes, persisted
    from services.course_file_store import course_exists
    from urllib.parse import urlparse
    if urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
        _fail()
    for value in (expected_preview_key, expected_stage_sha256, expected_parent_sha256):
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            _fail()
    root = Path(classroom_directory).resolve()
    initial = service.get(parent_key)
    parent_cid = initial['classroom_id']
    # The user-supplied token is only a lookup key: the actual source, owner,
    # revision chain and successful provider receipts are reread under lock.
    source_folder = root / parent_cid / 'textbook-preview-audio'
    with locked(source_folder / 'operator.lock'):
        p = prepare_partial_revision(service, parent_key, new_revision, root)
        if (p['targetInput']['previewKey'] != expected_preview_key
                or p['identity']['targetStageSha256'] != expected_stage_sha256
                or p['parentClassroomSha256'] != expected_parent_sha256):
            _fail()
        target_input, clean, plan, proof = p['targetInput'], p['targetRoom'], p['targetPlan'], p['proof']
        cid, key = clean['id'], target_input['previewKey']
        child = root / cid
        folder, archive = child / 'textbook-preview-audio', child / 'textbook-preview-audio' / 'partial-parent'
        if any(path.is_symlink() for path in (child, folder, archive)):
            _fail()
        folder.mkdir(parents=True, exist_ok=True)
        with locked(folder / 'operator.lock'), service.repository.transaction() as conn:
            # Match the resolver's global lock ordering: edition before any
            # preview or slot row, preventing competing registration deadlocks.
            service.reuse.repository.lock_edition(conn, initial['edition_id'])
            old = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE',
                               (parent_key,)).fetchone()
            if (old is None or old['classroom_sha256'] != p['parentClassroomSha256']
                    or service.repository.parse(old['input_json']) != p['sourceInput']
                    or service.repository.parse(old['classroom_json']) != p['sourceRoom']
                    or service.repository.parse(old['result_json']).get('audioReceipts') != p['databaseReceipts']):
                _fail()
            # Verify the author stage and native ledger again immediately before
            # the DB reservation. A changed stage requires a fresh preparation.
            manifest = service._manifest(conn, old['edition_id'], old['revision_id'])
            author = p['sourceInput']['authoring']
            current, _ = service._operator_adoption_classroom(author['stageId'], root, author, manifest, old['node_id'])
            candidate = validate_authoring_candidate(current, root, author, manifest, old['node_id'],
                output_root=service.authoring_output_root, runtime_origin=service.runtime.base_url)
            if (digest(current) != p['identity']['targetStageSha256'] or not candidate
                    or candidate['sha256'] != p['identity']['candidateSha256']):
                _fail()
            resolved = service.reuse.resolve(conn, manifest, old['node_id'],
                teaching_revision=new_revision, regeneration=regeneration)
            if resolved['source'] != 'new':
                existing = resolved.get('preview')
                if (existing is None or existing['preview_key'] != key
                        or service.repository.parse(existing['input_json']) != target_input
                        or existing['classroom_id'] != cid):
                    _fail()
                load_partial_audio(folder, plan, frozen=target_input)
                return service.summary(existing)
            archive.mkdir(parents=True, exist_ok=True)
            if (archive / 'audio').is_symlink() or (child / 'audio').is_symlink():
                _fail()
            files = {'source-input': p['sourceInput'], 'source-room': p['sourceRoom'], 'source-plan': p['sourcePlan'],
                     'database-receipts': p['databaseReceipts'], 'checkpoint-receipts': p['checkpointReceipts'],
                     'target-input': target_input, 'target-room': clean, 'provider-receipts': p['providerReceipts'],
                     'proof': proof, 'repair-chain': p['chain']}
            for name, value in files.items():
                immutable(archive / (name + '.json'), json_bytes(value))
            (archive / 'audio').mkdir(exist_ok=True)
            (child / 'audio').mkdir(exist_ok=True)
            room, receipts = bind_inherited_audio(p, service.runtime.base_url)
            for segment in proof['segments']:
                req = segment['sourceRequestId']
                immutable(archive / 'audio' / (req + '.wav'), p['wavs'][req])
                immutable(child / 'audio' / (req + '.wav'), p['wavs'][req])
            immutable(folder / 'plan.json', json_bytes(plan))
            immutable(folder / 'receipts.json', json_bytes(receipts))
            immutable(folder / 'checkpoint.json', json_bytes(room))
            load_partial_audio(folder, plan, frozen=target_input)
            try:
                saved = service.runtime.get_classroom(cid)
            except OpenMaicFullRuntimeError as exc:
                if exc.status_code != 404:
                    raise
                marker = folder / 'save-attempt.json'
                if course_exists(marker):
                    _fail()
                immutable(marker, json_bytes({'previewKey': key, 'targetSha256': digest(room)}))
                service.runtime.save_preview_classroom(room)
                saved = service.runtime.get_classroom(cid)
            if persisted(saved) != persisted(room):
                _fail()
            checks = deepcopy(p['checks'])
            checks.update(audioReceipts=receipts, audioStopCode=None, audioPartial=True,
                          audioCompleted=len(receipts), audioTotal=sum(a.get('type') == 'speech'
                              for s in clean['scenes'] for a in s.get('actions', [])))
            stamp = now_ms()
            conn.execute('INSERT INTO learning_textbook_course_previews '
                '(preview_key,edition_id,revision_id,node_id,input_json,runtime_origin,status,runtime_job_id,'
                'classroom_id,classroom_sha256,classroom_json,result_json,created_at,updated_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (key, old['edition_id'], old['revision_id'], old['node_id'], json_bytes(target_input).decode(),
                 service.runtime.base_url, 'review_required', 'partial-revision:' + digest(p['identity']),
                 cid, digest(saved), json_bytes(saved).decode(), json_bytes(checks).decode(), stamp, stamp))
            service.reuse.repository.bind_preview(conn, resolved['slot'], key, stamp)
        return service.summary(service.get(key))
