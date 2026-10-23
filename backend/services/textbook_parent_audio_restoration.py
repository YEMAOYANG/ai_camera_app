"""Archive and apply one exact parent-audio restoration without providers."""
import json
from pathlib import Path
from urllib.parse import urlparse

from content.textbook_catalog import canonical, digest
from content.textbook_parent_audio_restoration import restoration_candidate, restoration_receipt
from content.textbook_operator_revision import fail, parse, speech_index
from core.security import now_ms
from services.textbook_preview_audio import atomic_json
from services.textbook_preview_visual_revision import immutable, json_bytes, persisted, verify_audio
from services.course_file_store import course_exists, course_glob, course_is_dir, course_text


def load_restorations(folder, context, plan):
    base = Path(folder) / 'parent-audio-restorations'
    if not course_is_dir(base):
        return context
    from content.textbook_parent_audio_restoration import EVIDENCE_FILES, validate_restoration_evidence
    items = []
    for archive in sorted(course_glob(base)):
        if not course_is_dir(archive) or not course_exists(archive / 'amendment.json'):
            continue
        items.append({'revisionId': archive.name, 'documents': {
            name: json.loads(course_text(archive / name)) for name in EVIDENCE_FILES}})
    return validate_restoration_evidence(context, plan, items)


def restore_parent_audio(service, key, classroom_directory, patch):
    from services.textbook_operator_revision_service import checked_bytes, load_inheritance, locked, _same_parent
    row = service.get(key)
    root = Path(classroom_directory).resolve()
    cid = row['classroom_id']
    if (urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}
            or not cid.startswith('tbrev_')):
        fail('只能恢复本机独立修订预览的原父录音')
    folder = root / cid / 'textbook-preview-audio'
    plan = json.loads(course_text(folder / 'plan.json'))
    revision = digest({'previewKey': key, 'patch': patch})
    archive = folder / 'parent-audio-restorations' / revision
    with locked(folder / 'operator.lock'), service.repository.transaction() as conn:
        row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (key,)).fetchone()
        if row['status'] != 'preview_ready' or row['runtime_origin'] != service.runtime.base_url:
            fail('需要完成原始配音的同环境预览')
        published = conn.execute("SELECT input_json FROM learning_textbook_course_builds WHERE edition_id=? AND node_id=? AND status='published'",
                                 (row['edition_id'], row['node_id'])).fetchall()
        if any(parse(b['input_json']).get('previewKey') == key for b in published):
            fail('不能恢复或替换已发布目标课件')
        frozen, result = parse(row['input_json']), parse(row['result_json'])
        context = load_inheritance(folder, plan, frozen=frozen)
        _same_parent(service, context['parent'], conn)
        committed = result.get('parentAudioRestorations', [])
        if committed:
            if (len(committed) != 1 or committed[0]['revisionId'] != revision
                    or context.get('restorations') != committed
                    or row['classroom_sha256'] != committed[0]['targetSha256']
                    or digest(service.runtime.get_classroom(cid)) != row['classroom_sha256']):
                fail('已有恢复记录与当前课件不同')
            return committed[0]
        if context.get('restorations'):
            if len(context['restorations']) != 1 or context['restorations'][0]['revisionId'] != revision:
                fail('已有恢复归档没有对应数据库记录')
            # Reconcile a crash after saving the exact target but before the DB
            # commit. The sealed source/patch below still reconstruct it.
            context = {**context, 'restorations': [], 'restoredSegments': {}}
        source = parse(row['classroom_json'])
        if digest(source) != patch.get('expectedSourceSha256') or digest(source) != row['classroom_sha256']:
            fail('恢复来源摘要已变化')
        current = service.runtime.get_classroom(cid)
        if digest(json.loads(course_text(root / (cid + '.json')))) != digest(current):
            fail('本机课件与实际运行快照不同')
        target, segments = restoration_candidate(context, source, patch, plan)
        if digest(current) != digest(source) and persisted(current) != persisted(target):
            fail('运行快照不属于原始或准确恢复目标')
        if digest(current) == digest(source):
            verify_audio(source, result, root, cid)
        archive.mkdir(parents=True, exist_ok=True)
        for name, value in [('source.json', source), ('source-row.json', row), ('patch.json', patch),
                            ('target.json', target), ('plan.json', plan), ('original-receipts.json', result['audioReceipts'])]:
            immutable(archive / name, json_bytes(value))
        parent_receipts = {r['requestId']: r for r in context['parent']['receipts']}
        receipts = list(result['audioReceipts'])
        for segment in segments:
            request = segment['ttsRequestId']
            raw = checked_bytes(context['archive'] / 'audio' / (request + '.wav'), segment['audioSha256'])
            immutable(root / cid / 'audio' / (request + '.wav'), raw)
            cached = checked_bytes(context['archive'] / 'asr' / (segment['asrRequestId'] + '.json'),
                json.loads(course_text(context['archive'] / 'prepared.json'))['files']['asr/' + segment['asrRequestId'] + '.json'])
            immutable(archive / (segment['asrRequestId'] + '.json'), cached)
            original = parent_receipts[request]
            if digest(original) != segment['ttsReceiptSha256']:
                fail('恢复的正式 TTS 回执与父凭证不同')
            existing = next((r for r in receipts if r['requestId'] == request), None)
            if existing is not None and existing != original:
                fail('恢复音频的原始收据编号发生冲突')
            if existing is None:
                receipts.append(original)
        if digest(current) == digest(source):
            if course_exists(archive / 'save-attempt.json'):
                fail('上次恢复保存结果不明，不能重复发送')
            immutable(archive / 'save-attempt.json', json_bytes({'revisionId': revision, 'attemptedAt': now_ms()}))
            service.runtime.save_preview_classroom(target)
            current = service.runtime.get_classroom(cid)
        if persisted(current) != persisted(target) or digest(json.loads(course_text(root / (cid + '.json')))) != digest(current):
            fail('原音频恢复保存未确认')
        immutable(archive / 'saved.json', json_bytes(current))
        receipt = restoration_receipt(context, source, current, patch, plan, segments)
        immutable(archive / 'amendment.json', json_bytes(receipt))
        atomic_json(folder / 'receipts.json', receipts)
        updated = {**result, 'audioReceipts': receipts, 'parentAudioRestorations': [receipt]}
        updated.pop('frozenPreview', None)
        changed = conn.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=?,result_json=?,updated_at=? '
            'WHERE preview_key=? AND classroom_sha256=? AND status=?',
            (canonical(current), digest(current), canonical(updated), now_ms(), key, digest(source), 'preview_ready')).rowcount
        if changed != 1:
            fail('原音频恢复数据库快照发生变化')
        return receipt
