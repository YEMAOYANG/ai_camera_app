"""Trace a corrected review-evidence draft to an undispatched prepared parent.

This is deliberately narrower than a terminal revision.  The parent must be
permanently review-held, have a complete ready material bundle, and have no
dispatch/session/output evidence.  Only review evidence and its derived
metadata may change; the teaching design remains byte-equivalent after the
explicit evidence fields are projected away.

The parent is never rewritten.  All non-secret parent evidence is archived in
the successor and revalidated before material upload and the first POST.  The
owner cookie is copied only as a local authentication control and is never put
in the receipt or archive.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

from content.textbook_catalog import digest
from integrations.openmaic_workbench_client import private_write
from services.course_file_store import course_bytes, course_exists, course_glob, course_is_dir, course_text


SCHEMA = 'mira.operator.prepared-predecessor-revision.v1'
RECEIPT = 'prepared-predecessor.json'
ARCHIVE = 'prepared-predecessor'
LINEAGE_SCHEMA = 'mira.operator.review-evidence-correction-lineage.v1'
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _helpers():
    # Lazy import avoids a module cycle: the workbench service delegates here.
    from services.textbook_workbench_authoring import fail, immutable_write, json_bytes, sha
    return fail, immutable_write, json_bytes, sha


def _check(condition, message='已准备父稿的修正版证据无效；保留原件并核查'):
    if not condition:
        _helpers()[0]('prepared_predecessor_invalid', message)


def _json(path):
    try:
        value = json.loads(course_text(path))
        _check(isinstance(value, dict))
        return value
    except (OSError, ValueError, UnicodeError):
        _helpers()[0]('prepared_predecessor_invalid', '父稿、修正版或继任回执不可读，禁止继续')


def _relative_job(value):
    _check(isinstance(value, str) and value.strip() == value and value)
    path = Path(value)
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def _revision_number(job):
    match = re.fullmatch(r'teaching-([1-9][0-9]*)', job.parent.name)
    _check(match is not None, '证据修正版只接受连续数字教学修订')
    return int(match.group(1))


def _lineage(source, target, target_draft):
    scope = target_draft.get('scopeReview')
    record = scope.get('correctionLineage') if isinstance(scope, dict) else None
    _check(isinstance(record, dict) and record.get('schemaVersion') == LINEAGE_SCHEMA,
           '修正版须有结构化审阅证据纠错沿袭')
    source_draft = _json(source / 'draft.json')
    source_frozen = _json(source / 'frozen.json')
    source_revision, target_revision = _revision_number(source), _revision_number(target)
    _check(target_revision == source_revision + 1
           and str(record.get('predecessorTeachingRevision')) == str(source_revision)
           and record.get('predecessorDraftSha256') == source_frozen.get('draftSha256')
           and record.get('predecessorDispatchStatus') == 'never_started'
           and _relative_job(record.get('predecessorJob')) == source,
           '纠错沿袭必须精确指向相邻、从未派发的父稿')
    for key in ('correctedAt', 'correctionReason', 'authorizationBoundary'):
        _check(isinstance(record.get(key), str) and record[key].strip() == record[key] and record[key])
    _check('不伪造' in record['authorizationBoundary'] and '派发' in record['authorizationBoundary'],
           '纠错沿袭必须明确不是伪造授权且本身不能派发')
    _check('authoringRevisionAuthorization' not in scope,
           '本路径不是用户授权的终止任务重做，不能混入修订授权记录')
    correction = scope.get('officialResourceReview', {}).get('reviewCorrection')
    _check(isinstance(correction, dict)
           and correction.get('predecessorDraftSha256') == source_frozen.get('draftSha256')
           and correction.get('predecessorDispatchStatus') == 'never_started'
           and _relative_job(correction.get('predecessorJob')) == source,
           '官方资源纠错记录必须与父稿沿袭一致')
    return record, source_draft


def _single_evidence_insertion(source, target, *, source_revision, target_revision,
                               video_waiver=False):
    _check(isinstance(source, str) and isinstance(target, str) and source != target)
    prefix = 0
    limit = min(len(source), len(target))
    while prefix < limit and source[prefix] == target[prefix]:
        prefix += 1
    suffix = 0
    while (suffix < len(source) - prefix and suffix < len(target) - prefix
           and source[len(source) - suffix - 1] == target[len(target) - suffix - 1]):
        suffix += 1
    insertion = target[prefix:len(target) - suffix if suffix else len(target)]
    _check(source == target[:prefix] + target[len(target) - suffix if suffix else len(target):]
           and 0 < len(insertion) <= 1200 and '\n' not in insertion,
           '请求只允许插入一段有界审阅证据说明，不能删除或改写教学请求')
    required = ((f'teaching-{source_revision}', f'teaching-{target_revision}', '从未派发',
                 '用户授权', 'waived_unavailable', 'DRM') if video_waiver else
                (f'teaching-{source_revision}', f'teaching-{target_revision}', '从未派发', '1x', '连续'))
    _check(all(token in insertion for token in required)
           and not any(token in insertion for token in ('新增页面', '删除页面', '更换教师', '更换技能', '改变答案')),
           '新增请求文字必须只说明父稿未派发和本次连续视频复核')
    return insertion


def _video_exception_map(review):
    result = {}
    records = review.get('reviewExceptions', []) if isinstance(review, dict) else None
    _check(isinstance(records, list))
    for record in records:
        if not isinstance(record, dict) or record.get('resourceType') != 'video':
            continue
        hours = record.get('classHourIds')
        _check(isinstance(hours, list) and hours)
        for hour_id in hours:
            _check(isinstance(hour_id, str) and hour_id not in result)
            result[hour_id] = record
    return result


def _video_waiver_change_hours(source, target):
    source_hours = {hour.get('classHourId'): hour for hour in source.get('classHours', [])
                    if isinstance(hour, dict)}
    target_hours = {hour.get('classHourId'): hour for hour in target.get('classHours', [])
                    if isinstance(hour, dict)}
    _check(source_hours and source_hours.keys() == target_hours.keys())
    changed = set()
    for hour_id in source_hours:
        source_video = source_hours[hour_id].get('resources', {}).get('video')
        target_video = target_hours[hour_id].get('resources', {}).get('video')
        _check(isinstance(source_video, dict) and isinstance(target_video, dict))
        if source_video.get('status') == target_video.get('status'):
            continue
        _check(source_video.get('status') == 'reviewed'
               and target_video.get('status') == 'waived_unavailable'
               and 'videoModalityReview' not in target_video,
               '视频状态只能按本课用户授权从reviewed改为waived_unavailable')
        changed.add(hour_id)
    source_exceptions, target_exceptions = _video_exception_map(source), _video_exception_map(target)
    for hour_id in source_hours:
        if hour_id in changed:
            _check(hour_id not in source_exceptions and hour_id in target_exceptions
                   and set(target_exceptions[hour_id].get('classHourIds', [])) <= changed,
                   '新增视频豁免必须只覆盖本次变更的精确课时')
        else:
            _check(source_exceptions.get(hour_id) == target_exceptions.get(hour_id),
                   '未变更课时的视频豁免记录必须保持原样')
    return changed


def _normalized_official_review(review, *, video_waiver_hours=frozenset()):
    value = deepcopy(review)
    for key in ('reviewedAt', 'reviewedBy', 'reviewCorrection'):
        value.pop(key, None)
    hours = value.get('classHours')
    _check(isinstance(hours, list) and hours)
    for hour in hours:
        resources = hour.get('resources') if isinstance(hour, dict) else None
        video = resources.get('video') if isinstance(resources, dict) else None
        _check(isinstance(video, dict))
        video.pop('locations', None)
        video.pop('method', None)
        video.pop('videoModalityReview', None)
        if hour.get('classHourId') in video_waiver_hours:
            video.pop('status', None)
            video.pop('findings', None)
    records = value.get('reviewExceptions', [])
    _check(isinstance(records, list))
    value['reviewExceptions'] = [record for record in records
                                 if not (isinstance(record, dict)
                                         and record.get('resourceType') == 'video'
                                         and set(record.get('classHourIds', [])) <= video_waiver_hours)]
    return value


def _normalized_post_class(record):
    value = deepcopy(record)
    for key in ('officialResourceReviewFile', 'officialResourceReviewSha256', 'sourceContract',
                'sourcePath', 'sourceSha256'):
        value.pop(key, None)
    return value


def _normalized_asset_plan(plan):
    value = deepcopy(plan)
    value.pop('status', None)
    attachments = value.get('sourceAttachments')
    if attachments is not None:
        _check(isinstance(attachments, list) and attachments)
        value['sourceAttachments'] = [
            {'assetKey': item.get('assetKey'), 'mimeType': item.get('mimeType')}
            for item in attachments if isinstance(item, dict)
        ]
        _check(len(value['sourceAttachments']) == len(attachments)
               and all(item['assetKey'] and item['mimeType'] for item in value['sourceAttachments']))
    return value


def _same_course_content(source_job, target_job, source, target):
    source_revision, target_revision = _revision_number(source_job), _revision_number(target_job)
    _check(target_revision == source_revision + 1)
    for field in ('teacherContract', 'skillIds', 'pagePlan', 'lockedAssessments', 'coverContract',
                  'generationReady', 'readinessBoundary', 'mode', 'schemaVersion'):
        _check(source.get(field) == target.get(field), f'证据修正版不能改变 {field}')
    source_binding, target_binding = deepcopy(source.get('binding')), deepcopy(target.get('binding'))
    _check(isinstance(source_binding, dict) and isinstance(target_binding, dict))
    source_binding.pop('teachingRevision', None)
    target_binding.pop('teachingRevision', None)
    _check(source_binding == target_binding
           and str(source.get('binding', {}).get('teachingRevision', source_revision)) == str(source_revision)
           and str(target.get('binding', {}).get('teachingRevision', target_revision)) == str(target_revision),
           '修正版必须保持精确教材和课次身份，只能递增教学修订')
    _check(_normalized_asset_plan(source.get('assetPlan', {}))
           == _normalized_asset_plan(target.get('assetPlan', {})),
           '修正版素材计划只能更新同一组来源附件的证据字节')
    source_rules, target_rules = source.get('qualityRules'), target.get('qualityRules')
    _check(isinstance(source_rules, list) and isinstance(target_rules, list)
           and len(target_rules) == len(source_rules) + 1 and target_rules[1:] == source_rules)
    evidence_rule = target_rules[0]
    _check(isinstance(evidence_rule, str)
           and f'teaching-{source_revision}' in evidence_rule
           and f'teaching-{target_revision}' in evidence_rule
           and '视频' in evidence_rule and '不得据此' in evidence_rule,
           '新增质量规则只能声明审阅证据修正边界')
    left, right = deepcopy(source), deepcopy(target)
    for value in (left, right):
        for key in ('preparedAt', 'reviewedAt', 'status', 'request', 'qualityRules', 'assetPlan'):
            value.pop(key, None)
    left_scope, right_scope = left.get('scopeReview'), right.get('scopeReview')
    _check(isinstance(left_scope, dict) and isinstance(right_scope, dict))
    right_scope.pop('correctionLineage', None)
    left_review = left_scope.get('officialResourceReview')
    right_review = right_scope.get('officialResourceReview')
    video_waiver_hours = _video_waiver_change_hours(left_review, right_review)
    _single_evidence_insertion(source.get('request'), target.get('request'),
                               source_revision=source_revision, target_revision=target_revision,
                               video_waiver=bool(video_waiver_hours))
    _check(_normalized_official_review(left_review, video_waiver_hours=video_waiver_hours)
           == _normalized_official_review(right_review, video_waiver_hours=video_waiver_hours),
           '官方审阅修正只能更新视频观看证据和纠错元数据，不能改变五类资源范围')
    _check(_normalized_post_class(left_scope.get('postClassPractice'))
           == _normalized_post_class(right_scope.get('postClassPractice')),
           '课后练习目标和原创课内映射必须保持')
    left_scope['officialResourceReview'] = '<review-evidence>'
    right_scope['officialResourceReview'] = '<review-evidence>'
    left_scope['postClassPractice'] = '<derived-source-evidence>'
    right_scope['postClassPractice'] = '<derived-source-evidence>'
    left['binding'].pop('teachingRevision', None)
    right['binding'].pop('teachingRevision', None)
    _check(left == right, '证据修正版含有审阅证据之外的课程变化')


def _material_files(source, manifest):
    folder = source / 'material-attachments'
    _check(folder.is_dir() and not folder.is_symlink())
    expected = {'manifest.json', 'owner.json', 'ready.json'}
    for asset in manifest['assets']:
        expected.update({asset['file'], asset['assetKey'] + '-intent.json',
                         asset['assetKey'] + '-receipt.json'})
    actual = {path.name for path in folder.iterdir() if path.is_file() and not path.is_symlink()}
    _check(actual == expected and all(not path.is_symlink() and path.is_file() for path in folder.iterdir()),
           '父稿附件目录必须完整且不能含未归档文件或符号链接')
    return ['material-attachments/' + name for name in sorted(expected)]


def _source_snapshot(service, source):
    _, _, _, sha = _helpers()
    frozen, draft, state = service._load(source)
    _check(state.get('status') == 'prepared' and state.get('materialsStatus') == 'ready'
           and state.get('existingArtifacts') in (None, [])
           and not any(state.get(key) for key in ('sessionId', 'sessionStatus', 'savedStages',
                                                  'stageId', 'classroomId', 'runtimeJobId', 'error')),
           '父稿必须是附件完整且从未派发、无会话、无保存成果的 prepared 状态')
    _check(not course_exists(source / 'dispatch.json')
           and not course_exists(source.parent / 'authoring.json')
           and not any(course_glob(source, 'saved-*.json')),
           '父稿已有派发、课堂或保存成果，不能走 prepared 证据修正')
    hold = service._review_hold(source, frozen, state)
    _check(hold is not None, '证据不足的父稿必须先建立不可解除的审查挂起')
    payload, identity = service._material_payload(source, frozen, draft)
    manifest = service._read_material_manifest(source, frozen)
    _check(manifest is not None and state.get('materialCount') == len(manifest['assets'])
           and identity.get('materialsSha256') and identity.get('materialsOwnerFingerprint'),
           '父稿必须有完整、可核验的首轮附件派发合同')
    allowed_top = {'draft.json', 'frozen.json', 'state.json', 'review-hold.json',
                   'owner.cookies', 'material-attachments'}
    _check({path.name for path in source.iterdir()} == allowed_top
           and (source / 'owner.cookies').is_file() and not (source / 'owner.cookies').is_symlink(),
           '父稿只能包含冻结请求、完整附件、私有 owner 与审查挂起证据')
    names = ['draft.json', 'frozen.json', 'state.json', 'review-hold.json', *_material_files(source, manifest)]
    files = {name: sha(course_bytes(source / name)) for name in names}
    return frozen, draft, state, {
        'sourceFiles': files,
        'sourceDraftSha256': frozen['draftSha256'],
        'sourceFrozenSha256': files['frozen.json'],
        'sourceStateSha256': files['state.json'],
        'sourceReviewHoldSha256': files['review-hold.json'],
        'sourceRequestSha256': identity['requestSha256'],
        'sourcePayloadSha256': identity['payloadSha256'],
        'sourceMaterialsSha256': identity['materialsSha256'],
        'sourceMaterialManifestSha256': manifest['sha256'],
        'sourceOwnerFingerprint': identity['materialsOwnerFingerprint'],
        'sourceStatus': state['status'],
        'sourceMaterialsStatus': state['materialsStatus'],
        'sourceMaterialCount': len(manifest['assets']),
    }


def _owner_client(service, source, target, expected_fingerprint, *, allow_copy=False):
    source_owner, target_owner = source / 'owner.cookies', target / 'owner.cookies'
    _check(source_owner.is_file() and not source_owner.is_symlink())
    if target_owner.exists() or target_owner.is_symlink():
        _check(target_owner.is_file() and not target_owner.is_symlink())
    else:
        _check(allow_copy, '修正版私有 owner 缺失；验证路径不能自动重建身份')
        # Read the credential directly: it is intentionally excluded from the
        # course-file registry, receipt and evidence archive.
        private_write(target_owner, source_owner.read_bytes())
    client = service.client_factory(service.origin, target_owner)
    _check(client.owner_fingerprint() == expected_fingerprint,
           '修正版 owner 与父附件 owner 不一致，禁止复用或上传')
    return client


def _live_checks(service, source, target, source_summary, client):
    source_frozen, source_draft, _, fresh = _source_snapshot(service, source)
    _check(fresh == source_summary, '父稿冻结字节、附件或审查挂起发生变化')
    target_frozen, target_draft = _json(target / 'frozen.json'), _json(target / 'draft.json')
    checks = service.guard.inspect(target_draft['binding'])
    _check(not checks['existingArtifacts']
           and all(checks[key] == target_frozen['catalogCheck'][key]
                   == source_frozen['catalogCheck'][key]
                   for key in ('manifestSha256', 'lessonScopeSha256')),
           '教材目录或数据库课程成果发生变化，不能豁免父稿重复栅栏')
    _, identity = service._material_payload(source, source_frozen, source_draft)
    matches = [session for session in client.sessions() if service._match(session, identity)]
    _check(not matches, '父稿完整请求已存在会话，不能声明从未派发')
    return 0


def _archive_files(job):
    archive = job / ARCHIVE
    if not archive.exists():
        return {}
    _check(archive.is_dir() and not archive.is_symlink())
    result = {}
    for path in sorted(archive.rglob('*')):
        _check(not path.is_symlink())
        if path.is_file():
            result[path.relative_to(archive).as_posix()] = _helpers()[3](course_bytes(path))
        else:
            _check(path.is_dir())
    return result


def validate_prepared_predecessor(service, job, *, live=False):
    path = job / RECEIPT
    if not course_exists(path):
        return None
    _, _, _, sha = _helpers()
    sealed = _json(path)
    body = {key: value for key, value in sealed.items() if key != 'sha256'}
    _check(sealed.get('schemaVersion') == SCHEMA and sealed.get('sha256') == digest(body)
           and sealed.get('targetJob') == str(job) and sealed.get('providerCalls') == 0
           and sealed.get('sourceSessionMatchCount') == 0)
    source = Path(sealed.get('sourceJob', '')).resolve()
    _check(source != job and source.is_relative_to(service.output_root)
           and source.name == 'authoring-job' and source.parent.parent == job.parent.parent
           and _revision_number(job) == _revision_number(source) + 1,
           'prepared 父稿必须是同一课的相邻教学修订')
    target_frozen, target_draft = _json(job / 'frozen.json'), _json(job / 'draft.json')
    _check(target_frozen.get('draftSha256') == sealed.get('targetDraftSha256')
           and sha(course_bytes(job / 'draft.json')) == sealed.get('targetDraftSha256'))
    lineage, source_draft = _lineage(source, job, target_draft)
    _check(digest(lineage) == sealed.get('correctionLineageSha256'))
    _same_course_content(source, job, source_draft, target_draft)
    _, _, _, fresh = _source_snapshot(service, source)
    _check(fresh == sealed.get('source'), '父稿请求、状态、挂起或附件已变化')
    archive = _archive_files(job)
    _check(archive == sealed.get('archiveFiles') == fresh['sourceFiles'] and bool(archive),
           '父稿非密钥证据归档不完整或发生变化')
    client = _owner_client(service, source, job, fresh['sourceOwnerFingerprint'])
    if live:
        count = _live_checks(service, source, job, fresh, client)
        _check(count == sealed.get('sourceSessionMatchCount'))
    return sealed


def revise_prepared(service, source_job, draft_path, *, teaching_revision,
                    expected_source_draft_sha256, reviewer, basis):
    fail, immutable_write, json_bytes, sha = _helpers()
    _check(isinstance(reviewer, str) and reviewer.strip() == reviewer and reviewer
           and isinstance(basis, str) and basis.strip() == basis and basis,
           '证据修正版须记录审核人和具体复核依据')
    source = Path(source_job).resolve()
    target_draft = _json(Path(draft_path))
    target = service._path(target_draft['binding'], teaching_revision)
    _check(source != target and source.is_relative_to(service.output_root)
           and source.name == 'authoring-job' and len(source.relative_to(service.output_root).parts) == 4
           and source.parent.parent == target.parent.parent)
    lineage, source_draft = _lineage(source, target, target_draft)
    _same_course_content(source, target, source_draft, target_draft)

    # The ordinary prepare path freezes and validates the complete current
    # policy/official-review/scene contracts.  It intentionally leaves the
    # exact parent as a duplicate fence until this receipt is complete.
    service.prepare(draft_path, teaching_revision=teaching_revision)
    with service._locked(target) as job:
        frozen, draft, state = service._load(job)
        existing = validate_prepared_predecessor(service, job, live=True)
        if existing is not None:
            _check(existing.get('sourceJob') == str(source)
                   and existing.get('reviewer') == reviewer and existing.get('basis') == basis,
                   '既有 prepared 继任回执与本次审核身份不一致')
            return service._summary(job, frozen, state)
        _check(frozen['draftSha256'] == sha(course_bytes(Path(draft_path)))
               and state.get('status') == 'reuse_review_required'
               and not course_exists(job / 'dispatch.json') and not state.get('sessionId')
               and not course_is_dir(job / 'material-attachments')
               and not course_exists(job.parent / 'authoring.json')
               and not any(course_glob(job, 'saved-*.json')),
               '修正版必须是只冻结、未绑定附件、未派发的重复审核状态')
        source_frozen, _, _, summary = _source_snapshot(service, source)
        _check(source_frozen['draftSha256'] == expected_source_draft_sha256,
               '父稿摘要与明确复核身份不符')
        allowed = [{'kind': 'operator_job', 'path': str(source), 'status': 'review_for_reuse'}]
        _check(service._other_artifacts(job) == allowed,
               '存在精确父稿以外的同课任务或成果，不能豁免重复生成栅栏')
        client = _owner_client(service, source, job, summary['sourceOwnerFingerprint'], allow_copy=True)
        source_match_count = _live_checks(service, source, job, summary, client)
        _check(source_match_count == 0)

        archive = job / ARCHIVE
        archive.mkdir(mode=0o700, parents=True, exist_ok=True)
        archive_hashes = {}
        for name, expected in summary['sourceFiles'].items():
            raw = course_bytes(source / name)
            _check(sha(raw) == expected)
            destination = archive / name
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            immutable_write(destination, raw)
            archive_hashes[name] = sha(raw)
        body = {
            'schemaVersion': SCHEMA,
            'sourceJob': str(source),
            'targetJob': str(job),
            'sourceDraftSha256': expected_source_draft_sha256,
            'targetDraftSha256': frozen['draftSha256'],
            'source': summary,
            'sourceSessionMatchCount': source_match_count,
            'correctionLineageSha256': digest(lineage),
            'reviewer': reviewer,
            'basis': basis,
            'archiveFiles': archive_hashes,
            'reuseDecision': ('preserve review-held parent and all non-secret attachment evidence; '
                              'only exact parent duplicate is exempt; target uses its own reviewed attachments'),
            'workbenchReads': 1,
            'providerCalls': 0,
        }
        immutable_write(job / RECEIPT, json_bytes({**body, 'sha256': digest(body)}))
        validate_prepared_predecessor(service, job, live=False)
        _check(not service._other_artifacts(job), 'prepared 父稿回执未能唯一豁免精确父任务')
        state.update(status='prepared', existingArtifacts=[],
                     message='旧审阅证据父稿已永久挂起并完整归档；当前修正版尚未派发')
        service._save_state(job, state)
        return service._summary(job, frozen, state)
