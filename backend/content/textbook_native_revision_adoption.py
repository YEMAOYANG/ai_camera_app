"""Verify the native revision chain before binding an unpublished preview.

The proof is artifact integrity only: it is neither play, audio nor quality review.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import urlparse

from content.textbook_catalog import digest
from content.textbook_review_followup import _read, _revision_entry, _scene_record_matches
from content.textbook_scene_contract import scene_digest
from services.course_file_store import course_bytes


def verify_native_stage_quiescent(session, stage, owner_fingerprint):
    """Read native ownership and leases; unavailable or ambiguous means unsafe."""
    import psycopg

    url = os.environ.get('MIRA_OPENMAIC_AGENT_DATABASE_URL', '')
    parsed = urlparse(url)
    if parsed.scheme not in ('postgres', 'postgresql') or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('native stage status is unavailable')
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            row = conn.execute('SELECT owner_id,status,deleted_at,lease_worker_id FROM agent_sessions WHERE id=%s',
                               (session,)).fetchone()
            meta = conn.execute('SELECT owner_id,deleted_at FROM stage_meta WHERE stage_id=%s',
                                (stage,)).fetchone()
            active = conn.execute("SELECT 1 FROM agent_sessions WHERE (stage_id=%s OR active_stage_id=%s) "
                                  "AND deleted_at IS NULL AND (status IN ('queued','running') OR lease_worker_id IS NOT NULL) LIMIT 1",
                                  (stage, stage)).fetchone()
        if (not row or not meta or not isinstance(row[0], str) or not row[0].startswith('anon:')
                or hashlib.sha256(row[0][5:].encode()).hexdigest() != owner_fingerprint
                or meta[0] != row[0] or row[1] != 'succeeded' or row[2] is not None
                or row[3] is not None or meta[1] is not None or active is not None):
            raise ValueError('native stage is not an idle owned successful session')
    except (psycopg.Error, OSError):
        raise ValueError('native stage status is unavailable') from None


def validate_native_source_proof(proof, followup):
    fields = {'schemaVersion', 'sessionId', 'stageId', 'ownerFingerprint',
              'authoringSourceSha256', 'nativeDocumentSha256', 'savedStageFileSha256',
              'revisionIds', 'revisionReceiptSha256s', 'candidateSha256',
              'candidateFileSha256', 'followupSha256', 'cloneCoreSha256', 'previewSourceSha256'}
    sha_fields = ('ownerFingerprint', 'authoringSourceSha256', 'nativeDocumentSha256',
                  'savedStageFileSha256', 'candidateSha256', 'candidateFileSha256',
                  'followupSha256', 'cloneCoreSha256', 'previewSourceSha256')
    if (not isinstance(proof, dict) or set(proof) != fields
            or proof.get('schemaVersion') != 'mira.textbook.native-preview-source.v1'
            or not isinstance(followup, dict)
            or any(re.fullmatch(r'[0-9a-f]{64}', str(proof.get(key))) is None for key in sha_fields)
            or any(proof.get(key) != followup.get(key) for key in
                   ('sessionId', 'stageId', 'revisionIds', 'revisionReceiptSha256s',
                    'candidateSha256', 'candidateFileSha256'))
            or proof['authoringSourceSha256'] != followup.get('candidateSourceSha256')
            or proof['followupSha256'] != followup.get('sha256')):
        raise ValueError('native source proof differs from the sealed revision followup')


def verify_native_revision_chain(document, classroom, directory, job, followup, owner_fingerprint):
    """Verify both complete document ancestry and the existing sealed candidate chain."""
    directory, job = Path(directory).resolve(), Path(job).resolve()
    session, stage = followup['sessionId'], followup['stageId']
    if (document.get('stage', {}).get('id') != stage
            or document.get('outline', {}).get('producerRef') != session
            or classroom != {'id': stage, 'stage': document['stage'], 'scenes': document['scenes']}
            or digest(classroom) != followup['candidateSourceSha256']):
        raise ValueError('native classroom differs from its revision followup')
    root = directory.parent / 'textbook-current-review-revisions' / hashlib.sha256(session.encode()).hexdigest() / stage
    candidate_path = directory / stage / 'textbook-authoring-candidate.json'
    current_candidate, current_bytes = _read(candidate_path, directory)
    if (current_candidate.get('sha256') != followup.get('candidateSha256')
            or hashlib.sha256(current_bytes).hexdigest() != followup.get('candidateFileSha256')):
        raise ValueError('current native candidate changed')
    frozen_contract = current_candidate['frozenContract']
    entries = []
    for index, revision_id in enumerate(followup['revisionIds']):
        entry = _revision_entry(root / revision_id, root, session, stage,
                                frozen_contract['sha256'])
        plan = entry['plan']
        if (plan['ownerFingerprint'] != owner_fingerprint
                or entry['receipt']['sha256'] != followup['revisionReceiptSha256s'][index]
                or plan['input'].get('expectedDocumentSha256') != plan['beforeDocumentSha256']
                or Path(plan['input'].get('jobDir', '')).resolve() != job
                or Path(plan.get('dataDir', '')).resolve() != directory.parent):
            raise ValueError('revision owner changed')
        original, _ = _read(root / revision_id / 'original-document.json', root)
        if digest(original) != plan['beforeDocumentSha256']:
            raise ValueError('revision original document changed')
        candidate, _ = _read(root / revision_id / 'original-candidate.json', root)
        records = candidate.get('scenes', [])
        if (candidate.get('frozenContract') != frozen_contract
                or candidate.get('status') != 'author_candidate'
                or candidate.get('verification') != 'static_contract_only_not_play_or_semantic_review'
                or len(records) != len(original.get('scenes', []))
                or any(not isinstance(record, dict)
                       or record.get('contractSha256') != frozen_contract['sha256']
                       or not _scene_record_matches(record, scene)
                       for record, scene in zip(records, original['scenes']))):
            raise ValueError('original candidate differs from its document')
        from content.textbook_authoring_candidate import _assets
        _assets(candidate, directory, stage)
        entries.append((entry, original))
    if not entries:
        raise ValueError('revision chain is empty')
    saved_path = job / ('saved-' + stage + '.json')
    saved, saved_bytes = _read(saved_path, job)
    state, _ = _read(job / 'state.json', job)
    saved_records = [item for item in state.get('savedStages', []) if isinstance(item, dict) and item.get('stageId') == stage]
    if (len(saved_records) != 1 or saved_records[0].get('sha256') != digest(saved)
            or Path(saved_records[0].get('path', '')).resolve() != saved_path.resolve()
            or saved != entries[0][1]):
        raise ValueError('revision chain is not anchored to the saved author stage')
    for i, (entry, before) in enumerate(entries):
        plan = entry['plan']
        after = entries[i + 1][1] if i + 1 < len(entries) else document
        if digest(after) != plan['afterDocumentSha256']:
            raise ValueError('revision documents do not join')
        if i and entries[i-1][0]['plan']['afterCandidateSha256'] != plan['beforeCandidateSha256']:
            raise ValueError('revision candidates do not join')
        after_by_id = {s['id']: s for s in after['scenes']}
        if (len(after_by_id) != len(after['scenes'])
                or [s['id'] for s in before['scenes']] != [s['id'] for s in after['scenes']]):
            raise ValueError('revision scene count differs')
        revised = {r['sceneId']: r for r in plan['revisions']}
        if len(revised) != len(plan['revisions']):
            raise ValueError('duplicate revised scene')
        for old in before['scenes']:
            new = after_by_id.get(old['id'])
            if new is None:
                raise ValueError('revision scene missing')
            change = revised.get(old['id'])
            if change is None:
                if old != new:
                    raise ValueError('unrecorded scene changed')
            elif scene_digest(old) != change['beforeSceneSha256'] or scene_digest(new) != change['afterSceneSha256']:
                raise ValueError('revision scene digest changed')
        before_header = {k: v for k, v in before.items() if k != 'scenes'}
        after_header = {k: v for k, v in after.items() if k != 'scenes'}
        if before_header != after_header:
            raise ValueError('unrecorded document metadata changed')
    if course_bytes(candidate_path) != current_bytes or course_bytes(saved_path) != saved_bytes:
        raise ValueError('native candidate or saved source changed while checking revision ancestry')
    return {'schemaVersion': 'mira.textbook.native-preview-source.v1',
            'sessionId': session, 'stageId': stage,
            'ownerFingerprint': owner_fingerprint,
            'authoringSourceSha256': digest(classroom),
            'nativeDocumentSha256': digest(document),
            'savedStageFileSha256': hashlib.sha256(saved_bytes).hexdigest(),
            'revisionIds': list(followup['revisionIds']),
            'revisionReceiptSha256s': list(followup['revisionReceiptSha256s']),
            'candidateSha256': followup['candidateSha256'],
            'candidateFileSha256': followup['candidateFileSha256'],
            'followupSha256': followup['sha256']}


def verify_preview_clone(classroom, native_stage, native_source_sha256):
    """Reverse identity translation and the storage-owned creation timestamp.

    Native documents project only id/stage/scenes; saveClassroom appends its
    own createdAt. The full preview digest still binds that timestamp, while
    this comparison checks all authored content against the native source.
    """
    clone = deepcopy(classroom)
    if 'createdAt' in clone:
        created_at = clone.pop('createdAt')
        try:
            if not isinstance(created_at, str) or datetime.fromisoformat(created_at.replace('Z', '+00:00')).tzinfo is None:
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError('preview storage timestamp is invalid') from None
    clone_id = clone.get('id')
    if not isinstance(clone_id, str) or clone.get('stage', {}).get('id') != clone_id:
        raise ValueError('preview identity is invalid')
    clone['id'] = native_stage
    clone['stage']['id'] = native_stage
    for scene in clone['scenes']:
        if scene.get('stageId') != clone_id:
            raise ValueError('preview scene identity differs')
        scene['stageId'] = native_stage
    if digest(clone) != native_source_sha256:
        raise ValueError('preview clone differs from native source')


def normalized_preview_core(classroom):
    """Remove generated audio only; reject a modified helper."""
    from content.textbook_interactive_narration import without_audio_helper
    from services.textbook_preview_audio import core_content

    core = core_content(classroom)
    for scene in core['scenes']:
        if scene.get('type') == 'interactive':
            scene['content']['html'] = without_audio_helper(scene['content']['html'])
    return core


def verify_narrated_preview(classroom, proof, plan):
    """Compare authored content after removing only the exact formal audio additions."""
    from urllib.parse import urlparse
    from content.textbook_interactive_narration import bind_interactive_audio
    from content.textbook_preview import cue_speech

    if (any(scene.get('type') == 'quiz' for scene in classroom['scenes'])
            or plan.get('classroomSha256') != proof.get('previewSourceSha256')
            or plan.get('coreSha256') != proof.get('cloneCoreSha256')):
        raise ValueError('preview audio identity differs')
    for original in classroom['scenes']:
        if original.get('type') == 'interactive':
            html = original['content']['html']
            clips = {cue: urlparse(action['audioUrl']).path
                     for cue, action in cue_speech(original).items()}
            if bind_interactive_audio(html, clips, classroom['id']) != html:
                raise ValueError('interactive cue audio does not match its formal action')
    if digest(normalized_preview_core(classroom)) != proof['cloneCoreSha256']:
        raise ValueError('narrated preview content changed')


def verify_narration_amendments(classroom, proof, plan, *, folder, revisions):
    """Rebuild each narrow narration patch from its immutable, audited source.

    The original native content identity remains unchanged. This separate chain
    proves why the currently audited speech differs from that original.
    """
    import json
    from pathlib import Path
    from services.course_file_store import course_text
    from services.textbook_preview_narration_revision import _check_archive, text_candidate
    if not revisions:
        verify_narrated_preview(classroom, proof, plan)
        return None
    if not isinstance(revisions, list) or not 1 <= len(revisions) <= 16:
        raise ValueError('invalid narration amendment chain')
    current, chain = classroom, []
    for receipt in reversed(revisions):
        rid = receipt.get('revisionId', '')
        if not re.fullmatch(r'[a-f0-9]{64}', rid):
            raise ValueError('invalid narration amendment id')
        archive = Path(folder) / 'narration-revisions' / rid
        read = lambda name: json.loads(course_text(archive / name))
        intent = read('intent.json')
        _check_archive(archive, intent)
        if (read('amendment.json') != receipt
                or receipt.get('sha256') != digest({k:v for k,v in receipt.items() if k != 'sha256'})
                or receipt.get('intentSha256') != intent.get('sha256')
                or receipt.get('previewKey') != plan.get('previewKey')
                or receipt.get('classroomId') != classroom['id']
                or receipt.get('targetSha256') != digest(current)
                or read('saved.json') != current):
            raise ValueError('narration amendment identity differs')
        original = read('source.json')
        original_plan = read('original-plan.json')
        if digest(original) != receipt['sourceSha256'] or original_plan != plan:
            raise ValueError('narration amendment original differs')
        rebuilt = text_candidate(original, intent['patch'], read('failed-audit.json'), original_plan)
        if (read('target-text.json') != rebuilt
                or normalized_preview_core(rebuilt) != normalized_preview_core(current)):
            raise ValueError('narration amendment exceeds reviewed text changes')
        # Also verify that every helper still plays its corresponding action.
        from urllib.parse import urlparse
        from content.textbook_interactive_narration import bind_interactive_audio
        from content.textbook_preview import cue_speech
        for scene in current['scenes']:
            if scene.get('type') == 'interactive':
                html = scene['content']['html']
                clips = {cue:urlparse(a['audioUrl']).path for cue,a in cue_speech(scene).items()}
                if bind_interactive_audio(html, clips, classroom['id']) != html:
                    raise ValueError('amended cue helper differs')
        chain.append(deepcopy(receipt))
        current = original
    verify_narrated_preview(current, proof, plan)
    body = {'schemaVersion':'mira.textbook.native-narration-chain.v1',
            'originalSourceSha256':digest(current), 'targetSourceSha256':digest(classroom),
            'nativeSourceSha256':digest(proof), 'amendments':list(reversed(chain))}
    return {**body, 'sha256':digest(body)}


def validate_narration_chain(chain, native_source, target_sha):
    if (not isinstance(chain, dict) or set(chain) != {'schemaVersion','originalSourceSha256',
            'targetSourceSha256','nativeSourceSha256','amendments','sha256'}
            or chain.get('schemaVersion') != 'mira.textbook.native-narration-chain.v1'
            or chain.get('sha256') != digest({k:v for k,v in chain.items() if k != 'sha256'})
            or chain.get('nativeSourceSha256') != digest(native_source)
            or chain.get('targetSourceSha256') != target_sha
            or not isinstance(chain.get('amendments'), list) or not 1 <= len(chain['amendments']) <= 16):
        raise ValueError('native narration chain differs')
    previous = chain['originalSourceSha256']
    for item in chain['amendments']:
        if (item.get('sha256') != digest({k:v for k,v in item.items() if k != 'sha256'})
                or item.get('sourceSha256') != previous):
            raise ValueError('native narration chain is discontinuous')
        previous = item['targetSha256']
    if previous != target_sha:
        raise ValueError('native narration chain has another target')


def verify_native_visual_amendments(row, proof, classroom_directory):
    """Unwrap only archived, replayable visual changes before native verification."""
    import json
    from services.textbook_preview_visual_revision import verify_visual_revisions
    original = verify_visual_revisions(row, classroom_directory)
    amendments = json.loads(row['result_json']).get('visualRevisions', [])
    if not amendments:
        return original, None
    body = {'schemaVersion': 'mira.textbook.native-visual-chain.v1',
            'originalSourceSha256': digest(original), 'targetSourceSha256': row['classroom_sha256'],
            'nativeSourceSha256': digest(proof), 'amendments': deepcopy(amendments)}
    chain = {**body, 'sha256': digest(body)}
    validate_visual_chain(chain, proof, row['classroom_sha256'])
    return original, chain


def validate_visual_chain(chain, native_source, target_sha):
    fields = {'schemaVersion', 'originalSourceSha256', 'targetSourceSha256',
              'nativeSourceSha256', 'amendments', 'sha256'}
    if (not isinstance(chain, dict) or set(chain) != fields
            or chain.get('schemaVersion') != 'mira.textbook.native-visual-chain.v1'
            or not isinstance(native_source, dict)
            or chain.get('sha256') != digest({k: v for k, v in chain.items() if k != 'sha256'})
            or chain.get('nativeSourceSha256') != digest(native_source)
            or chain.get('targetSourceSha256') != target_sha
            or any(re.fullmatch(r'[a-f0-9]{64}', str(chain.get(k))) is None for k in
                   ('originalSourceSha256', 'targetSourceSha256', 'nativeSourceSha256'))
            or not isinstance(chain.get('amendments'), list) or not 1 <= len(chain['amendments']) <= 16):
        raise ValueError('native visual chain differs')
    previous = chain['originalSourceSha256']
    identity = None
    for item in chain['amendments']:
        if (not isinstance(item, dict) or item.get('schemaVersion') != 'mira.textbook.preview-visual-amendment.v1'
                or item.get('sha256') != digest({k: v for k, v in item.items() if k != 'sha256'})
                or item.get('sourceSha256') != previous
                or any(item.get(k) is not False for k in ('generationDispatched', 'ttsDispatched', 'asrDispatched', 'publicationAllowed'))
                or item.get('audioIdentityClassroomSha256') != native_source.get('previewSourceSha256')
                or any(re.fullmatch(r'[a-f0-9]{64}', str(item.get(k))) is None for k in
                       ('revisionId', 'intentSha256', 'targetSha256', 'audioPlanSha256', 'audioReceiptsSha256'))):
            raise ValueError('native visual amendment differs')
        current_identity = tuple(item.get(k) for k in ('previewKey', 'classroomId', 'audioPlanSha256', 'audioReceiptsSha256'))
        if identity is not None and identity != current_identity:
            raise ValueError('native visual audio identity differs')
        identity = current_identity
        previous = item['targetSha256']
    if previous != target_sha:
        raise ValueError('native visual chain has another target')
