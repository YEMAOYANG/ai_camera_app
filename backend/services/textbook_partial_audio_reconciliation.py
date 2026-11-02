"""Reconcile verified partial narration after a storage-registry cutover.

No TTS POST is made by this module. The explicit execute path only uses the
existing immutable-object/CAS file writer for receipts and checkpoint.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlparse
import wave

from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import pronunciation_client_options, resolve_audio_contract, tts_request_id
from core.errors import ApiError
from services.course_file_store import CourseFileStore, course_bytes
from services.textbook_preview_audio import core_content, verify_segment_receipt
from services.textbook_preview_visual_revision import persisted


def _fail():
    raise ApiError('textbook_audio_reconciliation_conflict', '配音回执或检查点不一致，已停止恢复', 409)


def _receipt_prefix(old, new):
    """Only preserve order or upgrade an unresolved claim to the same success."""
    if not isinstance(old, list) or not isinstance(new, list) or len(old) > len(new):
        _fail()
    if len({r.get('requestId') for r in new if isinstance(r, dict)}) != len(new):
        _fail()
    for before, after in zip(old, new):
        if not isinstance(before, dict) or not isinstance(after, dict) or before.get('requestId') != after.get('requestId'):
            _fail()
        if before == after:
            continue
        if (before.get('status') not in {'unknown', 'running', 'ambiguous'} or after.get('status') != 'succeeded'
                or any(before[k] != after.get(k) for k in before if k not in {'status', 'audioSha256', 'mimeType'})
                or before.get('audioSha256') not in (None, after.get('audioSha256'))
                or before.get('mimeType') not in (None, after.get('mimeType'))):
            _fail()


def _checkpoint_prefix(old, new):
    """The newer checkpoint may add audio bindings but cannot change the core."""
    if core_content(old) != core_content(new):
        _fail()
    old_actions = {(s['id'], a['id']): a for s in old['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech'}
    new_actions = {(s['id'], a['id']): a for s in new['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech'}
    if old_actions.keys() != new_actions.keys():
        _fail()
    for key, before in old_actions.items():
        if before.get('audioId') and any(before.get(field) != new_actions[key].get(field)
                                         for field in ('audioId', 'audioUrl', 'audioMetadata')):
            _fail()


def _valid_wav(raw, sha):
    if hashlib.sha256(raw).hexdigest() != sha:
        _fail()
    try:
        with wave.open(io.BytesIO(raw), 'rb') as wav:
            if wav.getnframes() <= 0 or wav.getframerate() <= 0 or wav.getnchannels() <= 0:
                _fail()
    except (wave.Error, EOFError):
        _fail()


def prepare_reconciliation(service, key, classroom_directory):
    """Read both heads and verify all provider successes; no files are changed."""
    from services.textbook_partial_audio_inheritance import load_partial_audio
    from services.textbook_operator_revision_service import load_inheritance
    from repositories.course_storage_repository import storage_id_for
    if urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
        _fail()
    root = Path(classroom_directory).resolve()
    row = service.get(key)
    cid = row['classroom_id']
    folder = root / cid / 'textbook-preview-audio'
    if not cid or any(p.is_symlink() for p in (root / cid, folder, folder / 'plan.json',
                                                folder / 'receipts.json', folder / 'checkpoint.json')):
        _fail()
    frozen, room, result = [service.repository.parse(row[field]) for field in ('input_json', 'classroom_json', 'result_json')]
    if (row['status'] != 'review_required' or result.get('audioPartial') is not True
            or result.get('audioStopCode') != 'textbook_preview_audio_invalid'
            or digest(room) != row['classroom_sha256'] or frozen.get('previewKey') != key
            or digest(service.runtime.get_classroom(cid)) != row['classroom_sha256']):
        _fail()
    plan_path, receipts_path, checkpoint_path = [folder / name for name in ('plan.json', 'receipts.json', 'checkpoint.json')]
    plan_raw = course_bytes(plan_path)
    if not plan_path.is_file() or plan_path.read_bytes() != plan_raw:
        _fail()
    plan = json.loads(plan_raw)
    resolve_audio_contract(plan, frozen)
    if plan.get('previewKey') != key or plan.get('coreSha256') != digest(core_content(room)):
        _fail()
    old_receipts_raw, old_checkpoint_raw = course_bytes(receipts_path), course_bytes(checkpoint_path)
    old_receipts, old_checkpoint = json.loads(old_receipts_raw), json.loads(old_checkpoint_raw)
    local_receipts, local_checkpoint = json.loads(receipts_path.read_bytes()), json.loads(checkpoint_path.read_bytes())
    db_receipts = result.get('audioReceipts')
    _receipt_prefix(old_receipts, db_receipts)
    _receipt_prefix(local_receipts, db_receipts)
    _checkpoint_prefix(old_checkpoint, room)
    _checkpoint_prefix(local_checkpoint, room)
    if persisted(local_checkpoint) != persisted(room):
        _fail()
    partial = load_partial_audio(folder, plan, frozen=frozen)
    inherited = load_inheritance(folder, plan, frozen=frozen)
    if not partial:
        _fail()
    actions = [(s, a) for s in room['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
    by_id = {r.get('requestId'): r for r in db_receipts if isinstance(r, dict)}
    if len(by_id) != len(db_receipts) or any(r.get('status') != 'succeeded' for r in db_receipts):
        _fail()
    known = set()
    for scene, action in actions:
        request = action.get('audioId')
        if not request:
            request = tts_request_id(plan, scene['id'], action['id'], action['text'].strip())
            if request not in by_id:
                continue
        receipt = by_id.get(request)
        if not receipt or request in known:
            _fail()
        known.add(request)
        if action.get('audioId'):
            verify_segment_receipt(plan, receipt, scene, action, folder,
                                   inheritance=inherited, partial_inheritance=partial)
        elif receipt.get('previewAudioIdentity') != {'planSha256': digest(plan), 'attempt': 1}:
            _fail()
        actual = service.runtime.get_formal_audio_tts(request, **pronunciation_client_options(plan))
        sha = receipt.get('audioSha256')
        if (actual.get('requestId') != request or actual.get('status') != 'succeeded'
                or actual.get('audioSha256') != sha or actual.get('mimeType') != 'audio/wav'):
            _fail()
        _valid_wav(service.runtime.download_formal_audio_tts(request, expected_sha256=sha), sha)
    if known != set(by_id):
        _fail()
    store = CourseFileStore()
    storage = storage_id_for(store.config.endpoint, store.config.bucket, store.config.region)
    paths = [receipts_path, checkpoint_path]
    entries = [store.resolve(path) for path in paths]
    if not all(entries):
        _fail()
    scopes = [store.repository.head_scope(path.relative_to(store.project_root).as_posix(), storage) for path in paths]
    if not all(scopes):
        _fail()
    return {'previewKey': key, 'classroomId': cid, 'classroomSha256': row['classroom_sha256'],
            'planSha256': hashlib.sha256(plan_raw).hexdigest(), 'dbReceiptsSha256': digest(db_receipts),
            'receiptsPath': str(receipts_path), 'receiptsOldSha256': entries[0]['sha256'],
            'checkpointPath': str(checkpoint_path), 'checkpointOldSha256': entries[1]['sha256'],
            'receiptsNew': db_receipts, 'checkpointNew': local_checkpoint,
            'receiptCount': len(db_receipts), 'boundCount': sum(bool(a.get('audioId')) for _, a in actions),
            'oldReceipts': old_receipts, 'oldCheckpoint': old_checkpoint,
            'scopes': scopes}


def reconcile_partial_audio(service, key, classroom_directory, *, expected_fences=None, execute=False):
    """Dry-run writer policies or CAS both exact heads, stopping on conflict."""
    from services.textbook_operator_revision_service import locked
    from services.course_file_writer import CourseFileWriter
    from repositories.course_storage_repository import storage_id_for
    row = service.get(key)
    folder = Path(classroom_directory).resolve() / row['classroom_id'] / 'textbook-preview-audio'
    with locked(folder / 'operator.lock'):
        p = prepare_reconciliation(service, key, classroom_directory)
        fence_keys = ('previewKey', 'classroomSha256', 'planSha256', 'dbReceiptsSha256',
                      'receiptsOldSha256', 'checkpointOldSha256')
        fences = {k: p[k] for k in fence_keys}
        if execute and expected_fences != fences:
            _fail()
        writer = CourseFileWriter()
        root = writer.root
        raw = [canonical(p['receiptsNew']).encode(), canonical(p['checkpointNew']).encode()]
        paths = [Path(p['receiptsPath']), Path(p['checkpointPath'])]
        old = [p['oldReceipts'], p['oldCheckpoint']]
        checks = []
        if not execute:
            # _policy performs reads / row locks but no upload or mutation.
            # Explicit rollback prevents a dry run from changing any state.
            class Rollback(Exception): pass
            try:
                with service.repository.transaction() as conn:
                    for index, path in enumerate(paths):
                        rel = path.relative_to(root).as_posix()
                        checks.append(writer._policy(rel, course_bytes(path), raw[index], old[index],
                                                     json.loads(raw[index]), p['scopes'][index]['metadata'], conn))
                    raise Rollback()
            except Rollback:
                pass
            return {'status': 'validated_not_applied', 'fences': fences, 'policies': checks,
                    'receiptCount': p['receiptCount'], 'boundCount': p['boundCount']}
        for index, path in enumerate(paths):
            expected = fences['receiptsOldSha256' if index == 0 else 'checkpointOldSha256']
            result = writer.write_bytes(path, raw[index], expected_sha256=expected)
            if result.get('sha256') != hashlib.sha256(raw[index]).hexdigest() or course_bytes(path) != raw[index]:
                _fail()
            checks.append(result['sha256'])
        return {'status': 'reconciled', 'fences': fences, 'newSha256': checks,
                'receiptCount': p['receiptCount'], 'boundCount': p['boundCount']}
