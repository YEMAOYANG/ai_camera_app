"""Prepare an explicitly authorized revision without rewriting its terminal parent.

Only the exact predecessor operator/authoring record is exempted. Source bytes
and owner/session identity stay fixed; other duplicate fences and the normal
single-POST dispatch marker remain authoritative. No provider is called here.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re

from content.textbook_catalog import digest, identifier
from content.textbook_official_resource_review import BINDING_FIELDS
from integrations.openmaic_workbench_client import private_write
from integrations.openmaic_workbench_client import WorkbenchError
from services.course_file_store import course_bytes, course_exists, course_glob, course_text


SCHEMA = 'mira.operator.terminal-predecessor-reuse.v1'
RECEIPT = 'terminal-predecessor.json'
ARCHIVE = 'terminal-predecessor'
MAX_MEDIA_FILES = 256
MAX_MEDIA_BYTES = 512 * 1024 * 1024
_MEDIA_STEM = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,195}\Z')


def _helpers():
    # Lazy: the workbench service delegates here after its module is loaded.
    from services.textbook_workbench_authoring import fail, immutable_write, json_bytes, sha
    return fail, immutable_write, json_bytes, sha


def _check(condition, message='原制作修订证据无效；保留原件并核查'):
    if not condition:
        _helpers()[0]('terminal_predecessor_invalid', message)


def _json(path):
    try:
        value = json.loads(course_text(path))
        _check(isinstance(value, dict))
        return value
    except (OSError, ValueError, UnicodeError):
        _helpers()[0]('terminal_predecessor_invalid', '父任务或修订证据不可读，禁止新派发')


def _authorization(draft):
    record = draft.get('scopeReview', {}).get('authoringRevisionAuthorization')
    _check(isinstance(record, dict) and record.get('authorizedBy') == 'user'
           and all(isinstance(record.get(key), str) and record[key].strip()
                   for key in ('authorizedAt', 'userInstruction', 'reason')),
           '新修订须记录本课用户原话、授权时间和修订原因')
    _check(isinstance(record.get('binding'), dict)
           and all(record['binding'].get(key) == draft['binding'].get(key) for key in BINDING_FIELDS),
           '新修订授权与本稿教材身份不符')
    try:
        value = datetime.fromisoformat(record['authorizedAt'].replace('Z', '+00:00'))
        _check(value.tzinfo is not None)
    except ValueError:
        _helpers()[0]('terminal_predecessor_invalid', '修订授权时间须为带时区 ISO 时间')
    return record


def _same_scope(source, target):
    _check(all(source['binding'].get(key) == target['binding'].get(key) for key in
               (*BINDING_FIELDS, 'unitId', 'unitTitle', 'lessonTitle')),
           '修订必须保持精确教材、课次与学制')
    _check(source['teacherContract'] == target['teacherContract'] and source['skillIds'] == target['skillIds'],
           '修订不能改变冻结教师或技能身份')
    locks = lambda draft: [{key: value for key, value in lock.items() if key != 'page'}
                           for lock in draft.get('lockedAssessments', [])]
    _check(locks(source) == locks(target), '原锁题身份、顺序与全部内容必须保持；只允许显式移动页码')


def _media(root, stage_id):
    _, _, _, sha = _helpers()
    root = Path(root).resolve()
    folder = root / stage_id / 'media'
    _check(not folder.is_symlink() and folder.resolve().is_relative_to(root))
    files = sorted(course_glob(folder, '*')) if folder.exists() else []
    _check(len(files) <= MAX_MEDIA_FILES, '父素材数量超过修订归档上限')
    result, total = [], 0
    for path in files:
        _check(path.parent == folder and not path.is_symlink() and path.is_file()
               and len(path.name) <= 200 and _MEDIA_STEM.fullmatch(path.stem)
               and path.suffix.lower() in
               {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.mp3', '.wav', '.mp4', '.json'},
               '父素材必须是受支持的普通媒体文件')
        body = course_bytes(path)
        total += len(body)
        _check(0 < len(body) <= 64 * 1024 * 1024 and total <= MAX_MEDIA_BYTES,
               '父素材总字节超过修订归档上限')
        result.append({'name': path.name, 'sourcePath': str(path), 'sha256': sha(body), 'byteSize': len(body)})
    return result


def inspect_terminal_source(service, source, classroom_directory):
    """GET and byte reads only; no stop/resume, uploads, provider or DB mutation."""
    _, _, _, sha = _helpers()
    frozen, draft, state = service._load(source)
    _check(course_exists(source / 'dispatch.json') and identifier(state.get('sessionId')),
           '父任务须有原派发栅栏及会话身份')
    # Authentication stays strictly local, outside CourseFileStore/MinIO.
    owner_path = source / 'owner.cookies'
    _check(not owner_path.is_symlink() and owner_path.is_file(), '必须保留父任务原 owner 身份')
    client = service.client_factory(service.origin, source / 'owner.cookies')
    _, identity = service._material_payload(source, frozen, draft)
    marker = _json(source / 'dispatch.json')
    owner = client.owner_fingerprint()
    _check(marker.get('requestSha256') == identity['requestSha256']
           and marker.get('payloadSha256') == identity['payloadSha256']
           and marker.get('materialsSha256') == identity.get('materialsSha256')
           and marker.get('ownerFingerprint') == owner, '父派发栅栏或 owner 与原请求不符')
    session = client.session(state['sessionId'])
    _check(isinstance(session, dict) and service._match(session, identity)
           and session.get('id') == state['sessionId'], '父会话必须与完整原请求及技能精确匹配')
    _check(session.get('status') in {'succeeded', 'failed', 'cancelled'},
           '父会话尚未终止，不能创建有意修订')
    # Native meta.stageId may remain the empty opening placeholder. The finite
    # durable creation events identify the classroom actually saved by the run.
    events = client.stage_events(session['id'])
    _check(isinstance(events, list), '父会话课堂事件不可读')
    stage_ids = {event.get('data', {}).get('stageId') for event in events
                 if isinstance(event, dict) and event.get('type') == 'library_changed'
                 and isinstance(event.get('data'), dict) and event['data'].get('change') == 'stage_created'}
    if session.get('stageId') is not None:
        stage_ids.add(session['stageId'])
    _check(bool(stage_ids) and all(identifier(item) for item in stage_ids), '必须明确父会话已保存课堂身份')
    saved = []
    for candidate_id in sorted(stage_ids):
        try:
            candidate_document = client.stage(candidate_id)
        except WorkbenchError as exc:
            if exc.http_status == 404:
                continue  # A never-saved opening placeholder is not authored work.
            raise
        _check(isinstance(candidate_document, dict) and isinstance(candidate_document.get('stage'), dict)
               and candidate_document['stage'].get('id') == candidate_id
               and isinstance(candidate_document.get('scenes'), list), '父课堂响应身份不符')
        if not candidate_document['scenes']:
            continue
        _check(isinstance(candidate_document.get('outline'), dict)
               and candidate_document['outline'].get('producerRef') == session['id'],
               '父课堂与原会话制作归属不一致')
        saved.append((candidate_id, candidate_document))
    _check(len(saved) == 1, '父会话必须恰有一个已保存课堂；多候选或无成果不能自动修订')
    stage_id, document = saved[0]
    candidate_path = Path(classroom_directory).resolve() / stage_id / 'textbook-authoring-candidate.json'
    candidate = _json(candidate_path)
    candidate_body = {key: value for key, value in candidate.items() if key != 'sha256'}
    # Native v4 authors receive and bind their ledger to the compact author
    # projection.  The complete scene contract remains frozen beside it and
    # is revalidated by ``service._load`` / ``_base_dispatch_payload``.  v3
    # and older contract jobs never had that projection, so their ledger must
    # continue to bind the complete scene contract exactly as before.
    expected_candidate_contract = (frozen.get('authorDispatchContract')
                                   if frozen.get('schemaVersion') == 'mira.operator.workbench-authoring.v4'
                                   else frozen.get('sceneContract'))
    _check(candidate.get('schemaVersion') == 'mira.textbook.authoring-candidate.v1'
           and candidate.get('sha256') == digest(candidate_body)
           and candidate.get('status') == 'author_candidate'
           and candidate.get('verification') == 'static_contract_only_not_play_or_semantic_review'
           and candidate.get('sessionId') == session['id'] and candidate.get('stageId') == stage_id
           and candidate.get('frozenContract') == expected_candidate_contract
           and isinstance(candidate.get('scenes'), list)
           and len(candidate['scenes']) == len(document['scenes']), '父候选台账与冻结合同/保存课堂不符')
    for scene in document['scenes']:
        entries = [entry for entry in candidate['scenes'] if entry.get('sceneId') == scene.get('id')]
        _check(len(entries) == 1 and isinstance(entries[0].get('canonicalJson'), str)
               and entries[0].get('order') == scene.get('order')
               and sha(entries[0]['canonicalJson'].encode()) == entries[0].get('sha256'),
               '父保存页面缺少精确候选证据')
        try:
            _check(json.loads(entries[0]['canonicalJson']) == scene)
        except (ValueError, TypeError):
            _check(False)
    materials = client.session_materials(session['id'])
    media = _media(classroom_directory, stage_id)
    authoring = source.parent / 'authoring.json'
    source_files = {name: sha(course_bytes(source / name)) for name in ('draft.json', 'frozen.json', 'dispatch.json')}
    if course_exists(authoring):
        record = _json(authoring)
        _check(record.get('sessionId') == session['id']
               and record.get('stageId', record.get('classroomId')) == stage_id,
               '父 authoring 记录不能归属于别的任务')
        source_files['../authoring.json'] = sha(course_bytes(authoring))
    summary = {'sourceFiles': source_files, 'sessionId': session['id'], 'stageId': stage_id,
               'sessionMetaStageId': session.get('stageId'), 'sourceStageId': stage_id,
               'ownerFingerprint': owner, 'terminalStatus': session['status'],
               'sessionIdentitySha256': digest({key: session.get(key) for key in ('id', 'prompt', 'skillId', 'stageId', 'status')}),
               'documentSha256': digest(document), 'candidateFileSha256': sha(course_bytes(candidate_path)),
               'eventsSha256': digest(events), 'materialsSha256': digest(materials), 'media': media}
    return summary, {'session.json': session, 'stage.json': document, 'events.json': {'events': events},
                     'materials.json': {'materials': materials}}, candidate_path


def _validated_operator_lineage(service, source, *, live):
    """Return the exact, receipt-proven operator ancestry for one lesson.

    A terminal successor may itself have been created from a permanently held
    prepared predecessor (or another explicit successor).  Those immutable,
    validated ancestors are not unrelated duplicates, but every other sibling
    operator job must continue to block a new revision.
    """
    source = Path(source).resolve()
    lesson = source.parent.parent
    root = Path(service.output_root).resolve()
    _check(source.name == 'authoring-job' and source.is_relative_to(root)
           and len(source.relative_to(root).parts) == 4)
    lineage, seen, cursor = [], set(), source
    for _ in range(64):
        key = str(cursor)
        _check(key not in seen, '父修订链出现循环，禁止继续')
        seen.add(key)
        lineage.append(key)
        receipts = [record for record in (
            service._terminal_predecessor_receipt(cursor, live=live),
            service._prepared_predecessor_receipt(cursor, live=live),
            service._widget_successor_receipt(cursor, live=live),
        ) if record is not None]
        _check(len(receipts) <= 1, '父任务同时存在多种继任回执，禁止自动放宽重复栅栏')
        if not receipts:
            return lineage
        parent = Path(receipts[0].get('sourceJob', '')).resolve()
        _check(parent != cursor and parent.name == 'authoring-job'
               and parent.is_relative_to(root) and parent.parent.parent == lesson,
               '继任回执只能追踪同一教材课次的精确父任务')
        cursor = parent
    _check(False, '父修订链超过安全上限，禁止继续')


def validate_terminal_predecessor(service, job, *, live=False):
    path = job / RECEIPT
    if not course_exists(path):
        return None
    _, _, _, sha = _helpers()
    sealed = _json(path)
    body = {key: value for key, value in sealed.items() if key != 'sha256'}
    _check(sealed.get('schemaVersion') == SCHEMA and sealed.get('sha256') == digest(body)
           and sealed.get('targetJob') == str(job))
    source = Path(sealed.get('sourceJob', '')).resolve()
    _check(source != job and source.name == 'authoring-job' and source.is_relative_to(service.output_root)
           and source.parent.parent == job.parent.parent, '父修订必须属于同一教材课次且保留原目录')
    frozen, target = _json(job / 'frozen.json'), _json(job / 'draft.json')
    _check(frozen.get('draftSha256') == sealed.get('targetDraftSha256')
           and sha(course_bytes(job / 'draft.json')) == sealed.get('targetDraftSha256')
           and digest(_authorization(target)) == sealed.get('authorizationSha256'))
    old = _json(source / 'draft.json')
    _same_scope(old, target)
    if 'sourceOperatorLineageJobs' in sealed:
        _check(sealed['sourceOperatorLineageJobs']
               == _validated_operator_lineage(service, source, live=live),
               '终止父任务的已审核继任链发生变化')
    _check(sealed.get('classroomDirectory') == str(Path(sealed['classroomDirectory']).resolve()))
    archive = job / ARCHIVE
    for name, checksum in sealed.get('archiveFiles', {}).items():
        item = archive / name
        _check(not Path(name).is_absolute() and '..' not in Path(name).parts
               and not item.is_symlink() and sha(course_bytes(item)) == checksum,
               '父修订归档发生变化，禁止派发')
    _check(bool(sealed.get('archiveFiles')))
    for name, checksum in sealed['source']['sourceFiles'].items():
        _check(name in {'draft.json', 'frozen.json', 'dispatch.json', '../authoring.json'}
               and sha(course_bytes(source / name)) == checksum, '父原请求或派发记录变化，禁止修订派发')
    if live:
        fresh, _, _ = inspect_terminal_source(service, source, sealed['classroomDirectory'])
        _check(fresh == sealed['source'], '父会话、课堂、素材或事件变化，须重新核对修订')
    return sealed


def revise_terminal(service, source_job, draft_path, *, teaching_revision, expected_source_draft_sha256,
                    reviewer, basis, classroom_directory):
    fail, immutable_write, json_bytes, sha = _helpers()
    _check(isinstance(reviewer, str) and reviewer.strip() and isinstance(basis, str) and basis.strip())
    source = Path(source_job).resolve()
    target_draft = _json(Path(draft_path))
    _authorization(target_draft)
    target = service._path(target_draft['binding'], teaching_revision)
    _check(source != target and source.name == 'authoring-job'
           and source.is_relative_to(service.output_root)
           and len(source.relative_to(service.output_root).parts) == 4
           and source.parent.parent == target.parent.parent)
    # Normal prepare freezes the new contract and leaves duplicate fences in
    # reuse_review_required. No client or provider is created by prepare.
    service.prepare(draft_path, teaching_revision=teaching_revision)
    with service._locked(target) as job:
        frozen, draft, state = service._load(job)
        _check(not course_exists(job / 'dispatch.json') and not state.get('sessionId'),
               '已派发修订不能重新准备或替换其父记录')
        _check(frozen['draftSha256'] == sha(course_bytes(Path(draft_path))))
        source_frozen, source_draft, _ = service._load(source)
        _check(source_frozen['draftSha256'] == expected_source_draft_sha256,
               '父草稿摘要与明确审核身份不符')
        _same_scope(source_draft, draft)
        check = service.guard.inspect(draft['binding'])
        _check(not check['existingArtifacts'] and all(check[key] == frozen['catalogCheck'][key]
               == source_frozen['catalogCheck'][key] for key in ('manifestSha256', 'lessonScopeSha256')),
               '存在数据库课程成果或教材变化，不能自动豁免修订栅栏')
        existing = validate_terminal_predecessor(service, job, live=True)
        if existing:
            _check(existing['sourceJob'] == str(source) and existing['reviewer'] == reviewer
                   and existing['basis'] == basis)
        else:
            summary, snapshots, candidate = inspect_terminal_source(service, source, classroom_directory)
            lineage = _validated_operator_lineage(service, source, live=True)
            allowed = set(lineage)
            authoring_path = str(source.parent / 'authoring.json')
            _check(all((record.get('kind') == 'operator_job' and record.get('path') in allowed)
                       or (record.get('kind') == 'authoring' and record.get('path') == authoring_path
                           and '../authoring.json' in summary['sourceFiles'])
                       for record in service._other_artifacts(job)),
                   '存在准确父任务以外的同课记录，保留其他重复生成栅栏')
            archive = job / ARCHIVE
            paths = {}
            def save(name, raw):
                immutable_write(archive / name, raw)
                paths[name] = sha(raw)
            required = sum(entry['byteSize'] for entry in summary['media'])
            disk = os.statvfs(job)
            _check(disk.f_bavail * disk.f_frsize >= required + 64 * 1024 * 1024,
                   '可用空间不足以保留父素材原字节')
            archive.mkdir(mode=0o700, parents=True, exist_ok=True)
            (archive / 'media').mkdir(mode=0o700, exist_ok=True)
            for name in ('draft.json', 'frozen.json', 'dispatch.json'):
                save(name, course_bytes(source / name))
            if '../authoring.json' in summary['sourceFiles']:
                save('authoring.json', course_bytes(source.parent / 'authoring.json'))
            save('candidate.json', course_bytes(candidate))
            for name, value in snapshots.items():
                save(name, json_bytes(value))
            for entry in summary['media']:
                raw = course_bytes(Path(entry['sourcePath']))
                _check(sha(raw) == entry['sha256'])
                save('media/' + entry['name'], raw)
            body = {'schemaVersion': SCHEMA, 'sourceJob': str(source), 'targetJob': str(job),
                    'targetDraftSha256': frozen['draftSha256'], 'sourceDraftSha256': expected_source_draft_sha256,
                    'classroomDirectory': str(Path(classroom_directory).resolve()), 'source': summary,
                    'reviewer': reviewer, 'basis': basis, 'authorization': _authorization(draft),
                    'authorizationSha256': digest(_authorization(draft)), 'archiveFiles': paths,
                    'lockedAssessmentChange': 'page_only; ids/order/all_other_fields_unchanged',
                    'reuseDecision': 'preserve original stage and all media; new contract/stage; reviewed media may be attached by exact bytes',
                    'sourceOperatorLineageJobs': lineage,
                    'providerCalls': 0}
            immutable_write(job / RECEIPT, json_bytes({**body, 'sha256': digest(body)}))
            validate_terminal_predecessor(service, job, live=True)
        _check(not service._other_artifacts(job), '其他同课记录仍需要核查，不能派发')
        # Reuse the same private owner so existing owner-library uploads can be
        # attached without exposing a credential in the receipt or prompt.
        owner_path = job / 'owner.cookies'
        if owner_path.exists():
            _check(not owner_path.is_symlink()
                   and service.client_factory(service.origin, owner_path).owner_fingerprint()
                   == (existing or _json(job / RECEIPT))['source']['ownerFingerprint'],
                   '修订已有不同 owner，停止素材复用')
        else:
            private_write(owner_path, (source / 'owner.cookies').read_bytes())
        state.update(status='prepared', existingArtifacts=[],
                     message='终止父任务和全部原素材已归档；仅明确授权的新修订尚未派发')
        service._save_state(job, state)
        return service._summary(job, frozen, state)
