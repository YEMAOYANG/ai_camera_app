"""Immutable local preparation and separate registration of published revisions.

No provider dispatch. Preparation reads the parent and archives literal evidence;
registration reserves only the new teaching version and new classroom namespace.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import io
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from content.textbook_catalog import canonical, digest
from content.textbook_complete_scene_revision import PATCH_SCHEMA as COMPLETE_PATCH_SCHEMA, PREVIEW_PATCH_SCHEMA
from content.textbook_legacy_complete_scene_revision import PATCH_SCHEMA as LEGACY_COMPLETE_PATCH_SCHEMA
from content.textbook_operator_revision import (
    QUIZ_PATCH_SCHEMA, VISUAL_PATCH_SCHEMA, fail, inheritance_provenance, parse, quiz_crop_definitions,
    revision_candidate, validate_parent, verify_inherited_segment, speech_index,
)
from content.textbook_pinyin_pronunciation import PLAN_SCHEMA as PINYIN_SCHEMA, validate_receipt_wav
from content.textbook_preview import THREE_MODULE_PATH, preview_checks, self_contained_classroom
from content.textbook_preview_audio_contract import compare_transcript, new_audio_plan, resolve_audio_contract
from content.textbook_release import MEDIA, validate_release
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.textbook_preview_audio import core_content
from services.textbook_preview_visual_revision import immutable, json_bytes, persisted, sha_bytes
from services.course_file_store import course_bytes, course_exists, course_is_dir, course_text

SCHEMA = 'mira.textbook.operator-revision-prepared.v1'
ARCHIVE = 'operator-parent'
COMPLETE_SCHEMAS = {COMPLETE_PATCH_SCHEMA, PREVIEW_PATCH_SCHEMA, LEGACY_COMPLETE_PATCH_SCHEMA}


@contextmanager
def locked(path):
    # Source evidence may be remote; the serialization lock remains local.
    if course_is_dir(path.parent):
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('已有制作或修订任务持有本课操作锁')
        yield


def media_path(root, reference):
    match = MEDIA.fullmatch(reference)
    if not match:
        fail('来源素材路径无效')
    path = (root / match[1] / match[2]).resolve()
    if root not in path.parents or not course_exists(path):
        fail('原始素材文件不存在')
    return path


def checked_bytes(path, sha):
    raw = course_bytes(path)
    if sha_bytes(raw) != sha:
        fail('来源文件摘要变化：' + path.name)
    return raw


def target_input(parent, candidate):
    frozen = deepcopy(parse(parent['preview']['input_json']))
    request = frozen.get('authoring', {}).get('request') or frozen.get('requirement')
    for field in ('previewKey', 'requirement'):
        frozen.pop(field, None)
    frozen.update(executionPolicy='operator-published-revision.v1',
        teachingRevision=candidate['patch']['teachingRevision'], sourceSha256=digest(candidate['classroom']),
        operatorRevision={'revisionId': candidate['revisionId'], 'candidateSha256': digest(candidate),
                          'sourceEvidenceSha256': digest(parent)})
    if candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA:
        frozen.update(candidate['parent']['binding'])
    if candidate['patch']['schemaVersion'] == QUIZ_PATCH_SCHEMA:
        frozen.update(candidate['parent']['binding'])
        frozen['derivedMedia'] = deepcopy(candidate['derivedImages'])
        frozen['assessmentEvidence'] = candidate['assessmentEvidence']
        frozen['originalMedia'] = deepcopy(candidate['parent']['originalMedia'])
        frozen['originalMedia']['assets'].extend({'id': a['sha256'], 'file': a['sha256'] + '.png',
            'sha256': a['sha256'], 'mediaPath': a['mediaPath'], 'derivation': deepcopy(a['definition'])}
            for a in candidate['derivedImages'])
    if candidate['patch']['schemaVersion'] in COMPLETE_SCHEMAS:
        evidence = candidate['completeSceneEvidence']
        frozen.update(candidate['parent']['binding'])
        frozen['originalMedia'] = deepcopy(evidence['media'])
        frozen['authoring'] = deepcopy(evidence['authoring'])
        frozen['authoringCandidate'] = deepcopy(evidence['summary'])
    if candidate['patch']['schemaVersion'] in COMPLETE_SCHEMAS | {VISUAL_PATCH_SCHEMA}:
        # The native ledger is unchanged. Rebind its original review follow-up
        # to this separately recorded adoption or exact HTML-only descendant.
        # Publication independently rediscovers the immutable native evidence.
        followup = frozen.get('authoringCandidate', {}).get('completeSceneReviewFollowup')
        if followup:
            followup['candidateSourceSha256'] = frozen['sourceSha256']
            followup['sha256'] = digest({k: v for k, v in followup.items() if k != 'sha256'})
    return {**frozen, 'previewKey': digest(frozen), 'requirement': request}


def derive_quiz_assets(parent, patch, read_source):
    """Deterministic local crop only; no image model, network or source writes."""
    if patch.get('schemaVersion') != QUIZ_PATCH_SCHEMA:
        return None, {}
    from PIL import Image
    origin = validate_parent(parent, allow_saved_preview=True)
    revision_id = digest({'parentReleaseSha256': origin['releaseSha256'], 'patch': patch, 'visualPatch': None})
    cid = 'tbrev_' + revision_id[:24]
    assets, files = [], {}
    for definition in quiz_crop_definitions(parent, patch):
        raw = read_source(definition)
        if sha_bytes(raw) != definition['sourceSha256']:
            fail('裁切原图摘要已变化')
        with Image.open(io.BytesIO(raw)) as image:
            if list(image.size) != definition['sourceSize'] or image.format not in {'PNG', 'JPEG', 'WEBP'}:
                fail('裁切原图尺寸或格式不匹配')
            x, y, width, height = definition['rect']
            cropped = image.convert('RGB').crop((x, y, x + width, y + height))
            output = io.BytesIO()
            cropped.save(output, format='PNG', optimize=False, compress_level=9)
            encoded = output.getvalue()
        sha = sha_bytes(encoded)
        assets.append({'definition': deepcopy(definition), 'sha256': sha, 'byteSize': len(encoded),
                       'mediaPath': f'/api/classroom-media/{cid}/media/{sha}.png'})
        files['derived/' + sha + '.png'] = encoded
    return assets, files


def normalized_parent_cache(parent, entry):
    """An inherited ASR cache stays literal; rebuild each audited ancestry hop."""
    identity = (entry.get('sceneId'), entry.get('actionId'))
    ancestry = parent.get('sourceInheritance')
    if ancestry and parent.get('sourceAudioRestorations'):
        from content.textbook_parent_audio_restoration import validate_restoration_evidence, restored_entry
        context = validate_restoration_evidence(ancestry, parent['plan'], parent['sourceAudioRestorations'])
        if identity in context['restoredSegments']:
            prior = normalized_parent_cache(ancestry['parent'], entry)
            expected = next(e for e in ancestry['parent']['audit']['segments']
                            if (e['sceneId'], e['actionId']) == identity)
            if prior != expected:
                fail('恢复 ASR 缓存不能追溯到原始审核')
            scene, action = speech_index(parse(parent['preview']['classroom_json']))[identity]
            receipt = next(r for r in parent['receipts'] if r['requestId'] == action['audioId'])
            return restored_entry(context, parent['plan'], scene, action, receipt)
    if ancestry and any((s['sceneId'], s['actionId']) == identity for s in ancestry['candidate']['inheritedSegments']):
        prior = normalized_parent_cache(ancestry['parent'], entry)
        expected = next(e for e in ancestry['parent']['audit']['segments']
                        if (e['sceneId'], e['actionId']) == identity)
        if prior != expected:
            fail('继承 ASR 缓存不能追溯到原始审核')
        comparison = compare_transcript(parent['plan'], entry['text'], entry['transcript'])
        return {**prior, 'comparison': comparison, 'similarityBps': comparison['similarityBps'],
                'operatorParent': {'provenanceSha256': ancestry['provenance']['sha256'],
                                   'sourceEntrySha256': digest(expected)}}
    if not resolve_audio_contract(parent['plan'])['legacy']:
        comparison = compare_transcript(parent['plan'], entry['text'], entry['transcript'])
        return {**entry, 'comparison': comparison, 'similarityBps': comparison['similarityBps']}
    return entry


def read_parent(service, content_key, audit_path, root, conn, *, allow_saved_preview=False, allow_visual_ancestry=False, allow_complete_scene=False):
    build = service.repository.get_build(conn, content_key)
    if build is None:
        fail('父发布不存在')
    frozen = parse(build['input_json'])
    from content.textbook_complete_scene_revision import PROVENANCE_SCHEMA as COMPLETE_PROVENANCE_SCHEMA
    complete_ancestry = allow_visual_ancestry and frozen.get('operatorParent', {}).get('schemaVersion') == COMPLETE_PROVENANCE_SCHEMA
    preview = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=?',
                           (frozen.get('previewKey'),)).fetchone()
    directory = service.repository.get_revision(conn, build['edition_id'], build['revision_id'])
    course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                          (build['course_id'], build['course_version'])).fetchone()
    if preview is None or directory is None or course is None:
        fail('父课件的原始预览、目录或课程不存在')
    manifest = service.repository.manifest(directory)
    if digest(manifest) != directory['manifest_sha256']:
        fail('父目录摘要变化')
    validate_release(build, manifest, course)
    cid = preview['classroom_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', cid or '') or preview['runtime_origin'] != service.runtime.base_url:
        fail('父来源不属于当前本机运行环境')
    folder = root / cid / 'textbook-preview-audio'
    raw = {'source.json': course_bytes(root / (cid + '.json')),
           'source-plan.json': course_bytes(folder / 'plan.json'),
           'source-receipts.json': course_bytes(folder / 'receipts.json'),
           'source-audit.json': course_bytes(Path(audit_path))}
    parent = {'build': build, 'manifest': manifest, 'preview': preview,
              'plan': json.loads(raw['source-plan.json']), 'receipts': json.loads(raw['source-receipts.json']),
              'audit': json.loads(raw['source-audit.json'])}
    if ((allow_complete_scene or complete_ancestry or allow_visual_ancestry and resolve_audio_contract(parent['plan'])['legacy'])
            and parse(preview['result_json']).get('narrationRevisions')):
        from content.textbook_legacy_narration_evidence import EVIDENCE_FILES
        parent['sourceNarrationRevisions'] = []
        for amendment in parse(preview['result_json'])['narrationRevisions']:
            revision = amendment.get('revisionId')
            if not re.fullmatch(r'[a-f0-9]{64}', str(revision)):
                fail('原旁白修订编号无效')
            files = {}
            for name in sorted(EVIDENCE_FILES):
                archived = 'source-narration-revisions/' + revision + '/' + name
                raw[archived] = course_bytes(folder / 'narration-revisions' / revision / name)
                files[name] = raw[archived].decode('utf-8')
            parent['sourceNarrationRevisions'].append({'revisionId': revision, 'files': files})
    source_input = parse(preview['input_json'])
    if allow_saved_preview and source_input.get('executionPolicy') == 'persist-content-before-segment-audio.v2':
        source_directory = service.repository.get_revision(conn, preview['edition_id'], preview['revision_id'])
        if source_directory is None:
            fail('旧预览的原教材目录缺失')
        parent['sourceManifest'] = service.repository.manifest(source_directory)
        if digest(parent['sourceManifest']) != source_directory['manifest_sha256']:
            fail('旧预览的原教材目录摘要变化')
    release = parse(build['review_json'])['release']
    if (allow_visual_ancestry and parent['plan'].get('schemaVersion') == PINYIN_SCHEMA
            and 'pronunciationReview' not in release['audioAudit'] and 'operatorParent' not in frozen):
        source = parse(preview['classroom_json'])
        used = {a.get('audioId') for s in source['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech'}
        revisions = sorted({r['narrationRevisionId'] for r in parent['receipts']
                            if r.get('narrationRevisionId') and r.get('requestId') in used})
        if any(not re.fullmatch(r'[a-f0-9]{64}', revision) for revision in revisions):
            fail('原拼音旁白修订编号无效')
        if revisions:
            parent['sourceRequestPlans'] = [json.loads(course_text(folder / 'narration-revisions' / revision / 'plan.json'))
                                            for revision in revisions]
    if json.loads(raw['source.json']) != parse(preview['classroom_json']):
        fail('父本机文件与冻结预览不同')
    if allow_visual_ancestry and 'operatorParent' in frozen:
        context = load_inheritance(folder, parent['plan'], frozen=source_input)
        if context is None:
            fail('父继承发布缺少原归档')
        parent['sourceInheritance'] = {k: context[k] for k in ('parent', 'candidate', 'provenance')}
        parent['sourceInheritance']['input'] = source_input
        ancestor_intent = json.loads(course_text(context['archive'] / 'prepared.json'))
        for name in (*ancestor_intent['files'], 'prepared.json', 'provenance.json'):
            raw['source-inheritance/' + name] = course_bytes(context['archive'] / name)
        if context.get('restorations'):
            from content.textbook_parent_audio_restoration import EVIDENCE_FILES
            parent['sourceAudioRestorations'] = []
            for receipt in context['restorations']:
                revision, docs = receipt['revisionId'], {}
                for name in sorted(EVIDENCE_FILES):
                    archived = 'source-audio-restorations/' + revision + '/' + name
                    raw[archived] = course_bytes(folder / 'parent-audio-restorations' / revision / name)
                    docs[name] = json.loads(raw[archived])
                parent['sourceAudioRestorations'].append({'revisionId': revision, 'documents': docs})
    origin = validate_parent(parent, allow_saved_preview=allow_saved_preview, allow_visual_ancestry=allow_visual_ancestry,
                             allow_complete_scene=allow_complete_scene)
    for alias in origin.get('audioAliases', []):
        name = alias['sourcePath'].rsplit('/', 1)[-1]
        raw['audio-aliases/' + name] = checked_bytes(media_path(root, alias['sourcePath']), alias['audioSha256'])
    release = parse(build['review_json'])['release']
    if parent['plan'].get('schemaVersion') == PINYIN_SCHEMA:
        for request_plan in parent.get('sourceRequestPlans', release['audioAudit'].get('pronunciationReview', {}).get('requestPlans', [])):
            name = 'narration-revisions/' + request_plan['revisionId'] + '/plan.json'
            raw['source-request-plans/' + request_plan['revisionId'] + '.json'] = course_bytes(folder / name)
            if json.loads(raw['source-request-plans/' + request_plan['revisionId'] + '.json']) != request_plan:
                fail('拼音原旁白请求计划与发布审核不同')
    for segment in origin['segments']:
        request = segment['ttsRequestId']
        raw['audio/' + request + '.wav'] = checked_bytes(root / cid / 'audio' / (request + '.wav'), segment['audioSha256'])
        if parent['plan'].get('schemaVersion') == PINYIN_SCHEMA:
            receipt = next(r for r in parent['receipts'] if r['requestId'] == request)
            validate_receipt_wav(receipt, raw['audio/' + request + '.wav'])
        name = segment['asrRequestId'] + '.json'
        cache = Path(audit_path).parent / name
        if not course_exists(cache) and 'sourceInheritance' in parent:
            cache = folder / ARCHIVE / 'asr' / name
        raw['asr/' + name] = course_bytes(cache)
        entry = json.loads(raw['asr/' + name])
        saved = next(e for e in parent['audit']['segments'] if e['ttsRequestId'] == request)
        entry = normalized_parent_cache(parent, entry)
        if entry != saved:
            fail('父 ASR 缓存与已发布聚合审核不一致')
    for asset in origin['originalMedia']['assets']:
        path = media_path(root, asset['mediaPath'])
        raw['images/' + asset['sha256'] + path.suffix] = checked_bytes(path, asset['sha256'])
    release = parse(build['review_json'])['release']
    for asset in release['media']:
        checked_bytes(media_path(root, asset['path']), asset['sha256'])
    return parent, raw


def read_preview_parent(service, preview_key, audit_path, root, conn):
    """Archive the original DB preview, not the independently revised author stage."""
    from content.textbook_unpublished_preview_origin import validate_preview_parent
    preview = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=?', (preview_key,)).fetchone()
    if preview is None or preview['runtime_origin'] != service.runtime.base_url:
        fail('原预览不存在或不属于当前运行环境')
    directory = service.repository.get_revision(conn, preview['edition_id'], preview['revision_id'])
    if directory is None:
        fail('原预览目录不存在')
    manifest = service.repository.manifest(directory)
    if digest(manifest) != directory['manifest_sha256']:
        fail('原预览目录摘要变化')
    cid = preview['classroom_id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', cid or ''):
        fail('原预览课堂身份无效')
    folder = root / cid / 'textbook-preview-audio'
    raw = {'source.json': json_bytes(parse(preview['classroom_json'])),
           'source-plan.json': course_bytes(folder / 'plan.json'),
           'source-receipts.json': course_bytes(folder / 'receipts.json'),
           'source-audit.json': course_bytes(Path(audit_path))}
    parent = {'manifest': manifest, 'preview': preview, 'plan': json.loads(raw['source-plan.json']),
              'receipts': json.loads(raw['source-receipts.json']), 'audit': json.loads(raw['source-audit.json'])}
    origin = validate_preview_parent(parent)
    # Verify even rejected original entries against the literal source files;
    # they remain in the complete audit but cannot enter inherited segments.
    for entry in parent['audit']['segments']:
        request = entry['ttsRequestId']
        wav = checked_bytes(root / cid / 'audio' / (request + '.wav'), entry['audioSha256'])
        name = entry['asr']['requestId'] + '.json'
        cache = course_bytes(Path(audit_path).parent / name)
        if normalized_parent_cache(parent, json.loads(cache)) != entry:
            fail('原预览 ASR 缓存与完整审核不同')
        raw['audio/' + request + '.wav'] = wav
        raw['asr/' + name] = cache
    for asset in origin['originalMedia']['assets']:
        path = media_path(root, asset['mediaPath'])
        raw['images/' + asset['sha256'] + path.suffix] = checked_bytes(path, asset['sha256'])
    return parent, raw


def load_prepared(directory, *, verify_assets=False):
    directory = Path(directory)
    intent = json.loads(course_text(directory / 'prepared.json'))
    if (intent.get('schemaVersion') != SCHEMA or intent.get('sha256') != digest({
            k: v for k, v in intent.items() if k != 'sha256'})):
        fail('修订准备记录无效')
    files = intent['files']
    required = {'parent.json', 'candidate.json', 'input.json', 'source.json', 'source-plan.json',
                'source-receipts.json', 'source-audit.json'}
    if not required <= set(files):
        fail('修订准备记录缺少原始证据')
    for name, sha in files.items():
        path = (directory / name).resolve()
        if directory.resolve() not in path.parents:
            fail('修订归档路径无效')
        if verify_assets or not name.startswith(('audio/', 'images/')):
            checked_bytes(path, sha)
    parent = json.loads(course_text(directory / 'parent.json'))
    candidate = json.loads(course_text(directory / 'candidate.json'))
    frozen = json.loads(course_text(directory / 'input.json'))
    derived, derivative_files = derive_quiz_assets(parent, candidate['patch'], lambda d:
        checked_bytes(directory / 'images' / (d['sourceSha256'] + Path(urlparse(d['sourcePath']).path).suffix), d['sourceSha256']))
    evidence = candidate.get('completeSceneEvidence')
    rebuilt = revision_candidate(parent, candidate['patch'], candidate.get('visualPatch'), derived_assets=derived,
                                 complete_scene_evidence=evidence)
    if (candidate != rebuilt or frozen != target_input(parent, candidate)
            or json.loads(course_text(directory / 'source.json')) != parse(parent['preview']['classroom_json'])
            or json.loads(course_text(directory / 'source-plan.json')) != parent['plan']
            or json.loads(course_text(directory / 'source-receipts.json')) != parent['receipts']
            or json.loads(course_text(directory / 'source-audit.json')) != parent['audit']
            or intent['revisionId'] != candidate['revisionId'] or intent['previewKey'] != frozen['previewKey']):
        fail('归档与父来源或修订白名单不一致')
    expected = required | {'audio/' + s['ttsRequestId'] + '.wav' for s in candidate['parent']['segments']} | {
        'asr/' + s['asrRequestId'] + '.json' for s in candidate['parent']['segments']} | {
        'images/' + a['sha256'] + Path(urlparse(a['mediaPath']).path).suffix for a in candidate['parent']['originalMedia']['assets']}
    if candidate['parent'].get('sourceKind') == 'audited-unpublished-preview':
        # Rejected source clips are immutable evidence, never usable media in
        # the target. Keep the complete failed audit reproducible as well.
        expected |= {'audio/' + e['ttsRequestId'] + '.wav' for e in parent['audit']['segments']}
        expected |= {'asr/' + e['asr']['requestId'] + '.json' for e in parent['audit']['segments']}
    expected |= set(derivative_files)
    if evidence is not None:
        expected.add('complete-scene-evidence.json')
        if json.loads(course_text(directory / 'complete-scene-evidence.json')) != evidence:
            fail('完整场景原始证据与候选不同')
        expected |= {'complete-scene-media/' + a['sha256'] + Path(urlparse(a['mediaPath']).path).suffix
                     for a in evidence['media']['assets']}
    expected |= {'audio-aliases/' + a['sourcePath'].rsplit('/', 1)[-1] for a in candidate['parent'].get('audioAliases', [])}
    for alias in candidate['parent'].get('audioAliases', []):
        checked_bytes(directory / 'audio-aliases' / alias['sourcePath'].rsplit('/', 1)[-1], alias['audioSha256'])
    for evidence in parent.get('sourceNarrationRevisions', []):
        for name, raw in evidence['files'].items():
            archived = 'source-narration-revisions/' + evidence['revisionId'] + '/' + name
            expected.add(archived)
            if course_text(directory / archived) != raw:
                fail('普通旧旁白归档字节与父证据不一致')
    for evidence in parent.get('sourceAudioRestorations', []):
        for name, document in evidence['documents'].items():
            archived = 'source-audio-restorations/' + evidence['revisionId'] + '/' + name
            expected.add(archived)
            if json.loads(course_text(directory / archived)) != document:
                fail('原音频恢复归档与父证据不一致')
    release = parse(parent['build']['review_json'])['release'] if 'build' in parent else {}
    for request_plan in parent.get('sourceRequestPlans', release.get('audioAudit', {}).get('pronunciationReview', {}).get('requestPlans', [])):
        name = 'source-request-plans/' + request_plan['revisionId'] + '.json'
        expected.add(name)
        if json.loads(course_text(directory / name)) != request_plan:
            fail('归档拼音请求计划与已批准记录不同')
    if 'sourceInheritance' in parent:
        ancestor = directory / 'source-inheritance'
        prior_parent, prior_candidate, prior_input, prior_intent = load_prepared(ancestor, verify_assets=verify_assets)
        prior_proof = json.loads(course_text(ancestor / 'provenance.json'))
        if parent['sourceInheritance'] != {'parent': prior_parent, 'candidate': prior_candidate,
                                         'input': prior_input, 'provenance': prior_proof}:
            fail('继承链原始文件与父证据不一致')
        expected |= {'source-inheritance/' + name for name in (*prior_intent['files'], 'prepared.json', 'provenance.json')}
    if set(files) != expected:
        fail('原始收据或媒体归档清单不完整')
    for name, expected_bytes in derivative_files.items():
        if course_bytes(directory / name) != expected_bytes:
            fail('派生图片不是冻结原图的准确裁切')
    source_entries = {e['asr']['requestId']: e for e in parent['audit']['segments']}
    for request, saved in source_entries.items():
        entry = json.loads(course_text(directory / 'asr' / (request + '.json')))
        entry = normalized_parent_cache(parent, entry)
        if entry != saved:
            fail('原始 ASR 缓存与冻结父证据不一致')
    return parent, candidate, frozen, intent


def prepare_revision(service, content_key, classroom_directory, patch, source_audit, output, *, visual_patch=None, parent_preview_key=None):
    """Read-only DB operation; write only a new immutable local candidate."""
    root, output = Path(classroom_directory).resolve(), Path(output).resolve()
    if urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'} or root == output or root in output.parents:
        fail('准备目录必须独立于本机课件存储')
    with service.repository.transaction() as conn:
        if parent_preview_key is not None:
            if content_key is not None or patch.get('schemaVersion') != PREVIEW_PATCH_SCHEMA or patch.get('parentPreviewKey') != parent_preview_key:
                fail('未发布预览入口必须显式使用独立 v4 合同')
            key = parent_preview_key
        else:
            if patch.get('schemaVersion') == PREVIEW_PATCH_SCHEMA:
                fail('未发布来源不能冒充已发布父课程')
            build = service.repository.get_build(conn, content_key)
            if build is None:
                fail('父发布不存在')
            key = parse(build['input_json']).get('previewKey')
        preview = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=?', (key,)).fetchone()
    if preview is None:
        fail('父预览不存在')
    folder = root / preview['classroom_id'] / 'textbook-preview-audio'
    with locked(folder / 'operator.lock'):
        with service.repository.transaction() as conn:
            if parent_preview_key is not None:
                parent, files = read_preview_parent(service, parent_preview_key, source_audit, root, conn)
            else:
                parent, files = read_parent(service, content_key, source_audit, root, conn,
                                       allow_saved_preview=patch.get('schemaVersion') in {QUIZ_PATCH_SCHEMA, VISUAL_PATCH_SCHEMA},
                                       allow_visual_ancestry=patch.get('schemaVersion') == VISUAL_PATCH_SCHEMA,
                                       allow_complete_scene=patch.get('schemaVersion') in COMPLETE_SCHEMAS)
        derived, derivative_files = derive_quiz_assets(parent, patch, lambda d:
            files['images/' + d['sourceSha256'] + Path(urlparse(d['sourcePath']).path).suffix])
        complete_evidence = None
        if patch.get('schemaVersion') in COMPLETE_SCHEMAS:
            if patch['schemaVersion'] == LEGACY_COMPLETE_PATCH_SCHEMA:
                from services.textbook_legacy_complete_scene_revision import read_legacy_complete_scene_evidence
                complete_evidence, native_files = read_legacy_complete_scene_evidence(parent, root, patch['sourceBundlePath'])
            else:
                from services.textbook_complete_scene_revision import read_complete_scene_evidence
                authoring = deepcopy(parse(parent['preview']['input_json'])['authoring'])
                authoring.update(sessionId=patch['nativeSessionId'], stageId=patch['nativeStageId'])
                complete_evidence, native_files = read_complete_scene_evidence(parent, root, authoring,
                    service.authoring_output_root, service.runtime.base_url)
            if patch.get('evidenceSha256', digest(complete_evidence)) != digest(complete_evidence):
                fail('预期完整场景证据摘要已变化')
            patch = {**patch, 'evidenceSha256': digest(complete_evidence)}
            files.update(native_files)
            files['complete-scene-evidence.json'] = json_bytes(complete_evidence)
        candidate = revision_candidate(parent, patch, visual_patch, derived_assets=derived,
                                       complete_scene_evidence=complete_evidence)
        files.update(derivative_files)
        frozen = target_input(parent, candidate)
        contained = self_contained_classroom(candidate['classroom'],
            lambda: (root.parents[1] / THREE_MODULE_PATH).read_bytes())
        if contained != candidate['classroom']:
            fail('候选必须自包含，不能引入未审核的资源转换')
        prompt = frozen['previewPrompt']
        # revision_candidate has verified exact before hashes and the complete
        # immutable visual diff. Unchanged historical HTML keeps its old host
        # contract; only actually revised v3 pages opt into responsive layout.
        responsive_ids = ({c['sceneId'] for c in candidate['visualPatch']['changes']}
                          if candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA else None)
        checks = preview_checks(candidate['classroom'], prompt['expectedSceneCount'], frozen['originalMedia'], prompt.get('expectedQuestionCount', 6),
                                grade_code=frozen.get('gradeCode'), responsive_scene_ids=responsive_ids)
        if any(i != 'speech_audio_missing' for i in checks['issues']):
            fail('候选结构或图片检查未通过')
        files.update({'parent.json': json_bytes(parent), 'candidate.json': json_bytes(candidate), 'input.json': json_bytes(frozen)})
        intent = {'schemaVersion': SCHEMA, 'revisionId': candidate['revisionId'], 'previewKey': frozen['previewKey'],
                  'files': {name: sha_bytes(raw) for name, raw in files.items()}}
        intent['sha256'] = digest(intent)
        output.mkdir(parents=True, exist_ok=True)
        with locked(output / 'prepare.lock'):
            if course_exists(output / 'prepared.json') and json.loads(course_text(output / 'prepared.json')) != intent:
                fail('候选目录已用于其他修订，不能覆盖')
            for name, raw in files.items():
                path = output / name
                path.parent.mkdir(parents=True, exist_ok=True)
                immutable(path, raw)
            immutable(output / 'prepared.json', json_bytes(intent))
    return {**intent, 'classroomId': candidate['classroom']['id'], 'teachingRevision': patch['teachingRevision'],
            'changedSpeechCount': len(candidate['changedSegments']), 'inheritedSpeechCount': len(candidate['inheritedSegments'])}


def _same_parent(service, parent, conn):
    current = service.repository.get_build(conn, parent['build']['content_key']) if 'build' in parent else None
    preview = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=?',
                           (parent['preview']['preview_key'],)).fetchone()
    if current != parent.get('build') or preview != parent['preview']:
        fail('准备后父发布或父预览发生变化，不能登记')


def register_revision(service, prepared_directory, classroom_directory, *, budget_reference):
    root, directory = Path(classroom_directory).resolve(), Path(prepared_directory).resolve()
    if urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
        fail('只能登记本机课件')
    with locked(directory / 'prepare.lock'):
        parent, candidate, frozen, intent = load_prepared(directory, verify_assets=True)
        if service.runtime.base_url != parent['preview']['runtime_origin']:
            fail('登记环境必须与已核验的父来源相同')
        cid, key = candidate['classroom']['id'], frozen['previewKey']
        folder = root / cid / 'textbook-preview-audio'
        folder.mkdir(parents=True, exist_ok=True)
        source_folder = root / parent['preview']['classroom_id'] / 'textbook-preview-audio'
        with locked(source_folder / 'operator.lock'), locked(folder / 'operator.lock'), service.repository.transaction() as conn:
            resolved = service.reuse.resolve(conn, parent['manifest'], parent['preview']['node_id'],
                teaching_revision=candidate['patch']['teachingRevision'],
                regeneration={'reason': candidate['patch']['basis'], 'budgetReference': budget_reference})
            _same_parent(service, parent, conn)
            for name, archived in [('plan.json', 'source-plan.json'), ('receipts.json', 'source-receipts.json')]:
                if course_bytes(source_folder / name) != course_bytes(directory / archived):
                    fail('准备后父配音计划或收据发生变化')
            if 'build' in parent and course_bytes(root / (parent['preview']['classroom_id'] + '.json')) != course_bytes(directory / 'source.json'):
                fail('准备后父课件文件发生变化')
            for name, sha in intent['files'].items():
                if name.startswith('source-narration-revisions/'):
                    checked_bytes(source_folder / 'narration-revisions' / name[len('source-narration-revisions/'):], sha)
                if name.startswith('source-request-plans/'):
                    revision = Path(name).stem
                    checked_bytes(source_folder / 'narration-revisions' / revision / 'plan.json', sha)
                if name.startswith('source-inheritance/'):
                    checked_bytes(source_folder / ARCHIVE / name[len('source-inheritance/'):], sha)
            for asset in candidate['parent']['originalMedia']['assets']:
                checked_bytes(media_path(root, asset['mediaPath']), asset['sha256'])
            for asset in candidate.get('completeSceneEvidence', {}).get('media', {}).get('assets', []):
                if candidate['patch']['schemaVersion'] == LEGACY_COMPLETE_PATCH_SCHEMA:
                    expected_owner = 'legacy-review-' + candidate['patch']['expectedSourceBundleSha256'][:24]
                    match = MEDIA.fullmatch(asset['mediaPath'])
                    if not match or match[1] != expected_owner:
                        fail('旧版新素材只能登记到独立的原始证据命名空间')
                    target = root / match[1] / match[2]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    immutable(target, checked_bytes(directory / 'complete-scene-media' / (asset['sha256'] + target.suffix), asset['sha256']))
                checked_bytes(media_path(root, asset['mediaPath']), asset['sha256'])
            for alias in candidate['parent'].get('audioAliases', []):
                checked_bytes(media_path(root, alias['sourcePath']), alias['audioSha256'])
            if resolved['source'] != 'new':
                existing = resolved.get('preview')
                if (existing is None or existing['preview_key'] != key or parse(existing['input_json']) != frozen
                        or existing['classroom_id'] != cid):
                    fail('新教学版本已被其他任务占用')
                load_inheritance(folder, json.loads(course_text(folder / 'plan.json')), frozen=frozen)
                return service.summary(existing)
            archive = folder / ARCHIVE
            archive.mkdir(exist_ok=True)
            for name in (*intent['files'], 'prepared.json'):
                target = archive / name
                target.parent.mkdir(parents=True, exist_ok=True)
                immutable(target, course_bytes(directory / name))
            for asset in candidate.get('derivedImages', []):
                target = root / cid / 'media' / (asset['sha256'] + '.png')
                target.parent.mkdir(exist_ok=True)
                immutable(target, checked_bytes(archive / 'derived' / target.name, asset['sha256']))
            try:
                saved = service.runtime.get_classroom(cid)
            except OpenMaicFullRuntimeError as exc:
                if exc.status_code != 404:
                    raise
                marker = directory / 'save-attempt.json'
                if course_exists(marker):
                    fail('上次保存结果不明且未发现候选，不能重发')
                immutable(marker, json_bytes({'previewKey': key, 'candidateSha256': digest(candidate)}))
                service.runtime.save_preview_classroom(candidate['classroom'])
                saved = service.runtime.get_classroom(cid)
            if persisted(saved) != persisted(candidate['classroom']):
                fail('新课堂编号已存在不同内容，不能覆盖')
            if json.loads(course_text(root / (cid + '.json'))) != saved:
                fail('保存的本机课堂与运行快照不一致')
            if candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA and parent['plan'].get('schemaVersion') == PINYIN_SCHEMA:
                plan = {**deepcopy(parent['plan']), 'previewKey': key, 'classroomSha256': digest(saved),
                        'coreSha256': digest(core_content(saved)), 'revisionId': candidate['revisionId'],
                        'parentPlanSha256': digest(parent['plan'])}
                resolve_audio_contract(plan, frozen)
            else:
                plan = new_audio_plan(preview_key=key, classroom_sha256=digest(saved),
                    core_sha256=digest(core_content(saved)), frozen_input=frozen)
            provenance = inheritance_provenance(candidate, plan)
            immutable(folder / 'plan.json', json_bytes(plan))
            immutable(archive / 'provenance.json', json_bytes(provenance))
            used = {s['ttsRequestId'] for s in candidate['inheritedSegments']}
            receipts = [r for r in parent['receipts'] if r['requestId'] in used]
            (root / cid / 'audio').mkdir(exist_ok=True)
            for segment in candidate['inheritedSegments']:
                name = segment['ttsRequestId'] + '.wav'
                immutable(root / cid / 'audio' / name, checked_bytes(archive / 'audio' / name, segment['audioSha256']))
            for alias in candidate['parent'].get('audioAliases', []):
                name = alias['sourcePath'].rsplit('/', 1)[-1]
                immutable(root / cid / 'audio' / name, checked_bytes(archive / 'audio-aliases' / name, alias['audioSha256']))
            immutable(folder / 'receipts.json', json_bytes(receipts))
            prompt = frozen['previewPrompt']
            responsive_ids = ({c['sceneId'] for c in candidate['visualPatch']['changes']}
                              if candidate['patch']['schemaVersion'] == VISUAL_PATCH_SCHEMA else None)
            checks = preview_checks(saved, prompt['expectedSceneCount'], frozen['originalMedia'], prompt.get('expectedQuestionCount', 6),
                                    grade_code=frozen.get('gradeCode'), responsive_scene_ids=responsive_ids)
            checks.update(audioReceipts=receipts, audioStopCode=None, operatorParentProvenanceSha256=provenance['sha256'])
            timestamp = now_ms()
            conn.execute('INSERT INTO learning_textbook_course_previews '
                '(preview_key,edition_id,revision_id,node_id,input_json,runtime_origin,status,runtime_job_id,'
                'classroom_id,classroom_sha256,classroom_json,result_json,created_at,updated_at) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (key, frozen['editionId'], frozen['alignmentRevisionId'],
                frozen['nodeId'], canonical(frozen), service.runtime.base_url, 'review_required',
                'operator-revision:' + candidate['revisionId'], cid, digest(saved), canonical(saved), canonical(checks), timestamp, timestamp))
            service.reuse.repository.bind_preview(conn, resolved['slot'], key, timestamp)
        return service.summary(service.get(key))


def load_inheritance(folder, plan, *, frozen=None):
    """Missing provenance for an explicitly inherited preview fails closed."""
    archive = Path(folder) / ARCHIVE
    if not course_is_dir(archive):
        if frozen and frozen.get('operatorRevision'):
            fail('修订预览缺少父来源归档')
        return None
    parent, candidate, saved_input, _ = load_prepared(archive)
    provenance = json.loads(course_text(archive / 'provenance.json'))
    if ((frozen is not None and frozen != saved_input) or plan['previewKey'] != saved_input['previewKey']
            or inheritance_provenance(candidate, plan) != provenance):
        fail('父来源归档未绑定新预览与新配音合同')
    context = {'parent': parent, 'candidate': candidate, 'provenance': provenance, 'archive': archive,
               'segments': {(s['sceneId'], s['actionId']): s for s in candidate['inheritedSegments']}}
    from services.textbook_parent_audio_restoration import load_restorations
    return load_restorations(folder, context, plan)


def inherited_evidence(context, plan, scene, action, receipt):
    if context is not None and (scene['id'], action['id']) in context.get('restoredSegments', {}):
        from content.textbook_parent_audio_restoration import restored_entry
        segment = context['restoredSegments'][(scene['id'], action['id'])][0]
        checked_bytes(context['archive'] / 'audio' / (segment['ttsRequestId'] + '.wav'), segment['audioSha256'])
        return restored_entry(context, plan, scene, action, receipt)
    if context is None or (scene['id'], action['id']) not in context['segments']:
        return None
    proof = verify_inherited_segment(context['parent'], context['candidate'], plan, context['provenance'], scene, action, receipt)
    saved = context['segments'][(scene['id'], action['id'])]
    checked_bytes(context['archive'] / 'audio' / (saved['ttsRequestId'] + '.wav'), saved['audioSha256'])
    entry = proof['sourceEntry']
    return {**entry, 'comparison': proof['comparison'], 'similarityBps': proof['comparison']['similarityBps'],
            'operatorParent': {'provenanceSha256': context['provenance']['sha256'],
                               'sourceEntrySha256': saved['asrEntrySha256']}}
