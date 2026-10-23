"""Freeze and dispatch one reviewed textbook draft through Pro, without TTS.

The dispatch marker is a permanent fence, not a lease. An unknown POST outcome
can only be reconciled by owner and the complete prompt hash, never by title.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re

from PIL import Image

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import canonical, digest, identifier, lesson_by_id
from content.textbook_interaction_policy import freeze_interaction_policy, interaction_policy_prompt
from content.textbook_scene_contract import (PROMPT_END, PROMPT_START, SNAPSHOT_SCHEMA, freeze_scene_contract,
                                             render_scene_contract, validate_scene_contract)
from integrations.openmaic_workbench_client import (OpenMaicWorkbenchClient, WorkbenchError,
                                                   local_origin, private_write)
from services.course_reuse_resolver import lesson_scope
from services.course_file_store import course_bytes, course_exists, course_glob, course_is_dir, course_text


# The workbench generate_scene API accepts these five values. DSL-only widget
# kinds do not establish that this authoring route can generate them.
NATIVE_AUTHORING_WIDGET_TYPES = frozenset({'simulation', 'game', 'visualization3d', 'diagram', 'code'})


def validate_native_widget_types(draft):
    """Check new dispatches without making old frozen sessions unreadable."""
    plan = draft.get('pagePlan')
    if not isinstance(plan, list):
        return  # The complete scene-contract validator reports malformed plans.
    for page in plan:
        if (isinstance(page, dict) and page.get('type') == 'interactive'
                and 'widgetType' in page and (not isinstance(page['widgetType'], str)
                                             or page['widgetType'] not in NATIVE_AUTHORING_WIDGET_TYPES)):
            fail('unsupported_widget_type', '互动页 widgetType 不受原生生成 API 支持；请在冻结前修正')


def widget_successor_diff(old, new):
    """Exactly one unsupported renderer label; no semantic contract changes."""
    validate_draft(new)
    validate_native_widget_types(new)
    before, after = old.get('pagePlan'), new.get('pagePlan')
    if not isinstance(before, list) or not isinstance(after, list) or len(before) != len(after):
        fail('successor_scope_changed', '继任只允许修正一处不支持的渲染枚举')
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    if len(changed) != 1:
        fail('successor_scope_changed', '继任只允许修正一处不支持的渲染枚举')
    i = changed[0]
    a, b = before[i], after[i]
    if (a.get('type') != 'interactive' or not isinstance(a.get('widgetType'), str)
            or a['widgetType'] in NATIVE_AUTHORING_WIDGET_TYPES
            or b != {**a, 'widgetType': b.get('widgetType')}
            or b.get('widgetType') not in NATIVE_AUTHORING_WIDGET_TYPES):
        fail('successor_scope_changed', '继任不能更改活动、教材、教师或测评范围')
    # Derive the only permitted request edit from the structured changed page.
    # It must occur exactly once; no global replace or unrelated prose edits.
    old_token = json.dumps('widgetType') + ': ' + json.dumps(a['widgetType'], ensure_ascii=False)
    new_token = json.dumps('widgetType') + ': ' + json.dumps(b['widgetType'], ensure_ascii=False)
    if old['request'].count(old_token) != 1:
        fail('successor_scope_changed', '请求中的待修枚举必须唯一且与结构化页面一致')
    offset = old['request'].index(old_token)
    expected = deepcopy(old)
    expected['pagePlan'][i]['widgetType'] = b['widgetType']
    expected['request'] = old['request'][:offset] + new_token + old['request'][offset + len(old_token):]
    if expected != new:
        fail('successor_scope_changed', '继任请求包含渲染标签以外的改动')
    return {'page': i + 1, 'from': a['widgetType'], 'to': b['widgetType']}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    private_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def png_dimensions(raw):
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG':
                raise ValueError()
            size = image.size
            image.verify()
        return size
    except Exception:
        fail('material_png_invalid', '附件必须是可核验的 PNG 原字节')


def material_json(path):
    try:
        if path.is_symlink():
            raise ValueError()
        result = json.loads(course_text(path))
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (OSError, ValueError, UnicodeError):
        fail('material_integrity_error', '附件记录缺失或摘要不一致，禁止上传或派发')


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def immutable_write(path, raw):
    if path.is_symlink():
        fail('amendment_integrity_error', '修订归档不能是符号链接')
    if course_exists(path):
        if course_bytes(path) != raw:
            fail('amendment_integrity_error', '既有修订归档发生变化，禁止覆盖')
    else:
        private_write(path, raw)


def amendment_draft(old, new):
    """Only authoring guidance changes; structured scope and embedded JSON stay frozen."""
    validate_draft(new)
    mutable = {'request', 'qualityRules'}
    if ({k: v for k, v in old.items() if k not in mutable}
            != {k: v for k, v in new.items() if k not in mutable}):
        fail('amendment_scope_changed', '只能修订 request/qualityRules；教材、教师、技能、测评、页面和素材范围必须保持')
    if 'qualityRules' in new and (not isinstance(new['qualityRules'], list) or not new['qualityRules']
            or not all(isinstance(rule, str) and rule.strip() for rule in new['qualityRules'])):
        fail('amendment_scope_changed', 'qualityRules 必须是非空文字规则列表')
    # Preserve exact embedded binding/assessment JSON, including its formatting.
    # Free-form prose still needs the named reviewer's complete-prompt review.
    decoder = json.JSONDecoder()
    text = old['request']
    for index, char in enumerate(text):
        if char not in '{[':
            continue
        try:
            value, end = decoder.raw_decode(text, index)
        except ValueError:
            continue
        if value and isinstance(value, (dict, list)):
            chunk = text[index:end]
            if new['request'].count(chunk) < text.count(chunk):
                fail('amendment_scope_changed', '请求内已有教材/测评等 JSON 原文必须完整保留')
    if old == new:
        fail('amendment_unchanged', '草稿没有实际修订')


def fail(code, message):
    raise WorkbenchError(code, message)


def validate_draft(draft, *, check_current_teacher=True):
    if not isinstance(draft, dict):
        fail('draft_invalid', '需要已审核的 JSON 草案对象')
    binding, request, skills = draft.get('binding'), draft.get('request'), draft.get('skillIds')
    if not isinstance(binding, dict) or not all(identifier(binding.get(k)) for k in ('editionId', 'revisionId', 'nodeId')):
        fail('binding_invalid', '草案须绑定准确 editionId、revisionId 与 nodeId')
    if (not isinstance(request, str) or not request or request != request.strip()
            or len(request.encode('utf-16-le')) // 2 > 100_000):
        fail('request_invalid', '请求须为非空原文、无首尾空白且不超过工作台限制')
    if (not isinstance(skills, list) or not skills
            or not all(identifier(skill) and skill in request for skill in skills)
            or len(set(skills)) != len(skills)):
        fail('skills_invalid', '每个 skillId 须明确写入冻结请求；首个作为 API 主技能')
    teacher = draft.get('teacherContract')
    if not isinstance(teacher, dict):
        fail('teacher_invalid', '草案缺少冻结教师契约')
    if not check_current_teacher:
        return binding  # Recovery keeps the original contract across registry upgrades.
    try:
        voice = get_formal_subject_qwen_voice_identity(binding.get('subject'))
    except KeyError:
        fail('teacher_invalid', '教材学科缺少已批准教师身份')
    expected = {'subject': voice.subject, 'teacherProfileId': voice.teacher_profile_id,
                'teacherProfileVersion': voice.teacher_profile_version, 'teacherProfileHash': voice.teacher_profile_hash,
                'teacherName': voice.teacher_name, 'voiceId': voice.voice_id, 'languageCode': voice.language_code}
    if any(teacher.get(k) != v for k, v in expected.items()):
        fail('teacher_invalid', '草案教师与当前学科教师契约不一致；不会自动替换')
    return binding


class WorkbenchCatalogGuard:
    """Narrow SELECTs only; no reuse reservation, migration or catalog import."""
    def __init__(self, repository):
        self.repository = repository

    def inspect(self, binding):
        repository = self.repository
        with repository.transaction() as conn:
            revision = repository.get_revision(conn, binding['editionId'], binding['revisionId'])
            if revision is None:
                fail('textbook_revision_missing', '请先核对并导入已绑定的教材目录版本')
            manifest = repository.manifest(revision)
            if digest(manifest) != revision['manifest_sha256']:
                fail('textbook_integrity_error', '教材目录摘要不一致，停止生成')
            unit, lesson = lesson_by_id(manifest, binding['nodeId'])
            expected = {k: manifest[k] for k in ('editionId', 'revisionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')}
            expected.update(unitId=unit['unitId'], unitTitle=unit['title'], lessonTitle=lesson['title'])
            if any(binding.get(k) != v for k, v in expected.items()):
                fail('binding_mismatch', '教材、单元、课次或学制与草案绑定不一致')
            scope = lesson_scope(manifest, binding['nodeId'])
            records = []
            queries = (
                ('build', 'SELECT content_key,revision_id,node_id,status,teaching_revision,course_id,course_version '
                 'FROM learning_textbook_course_builds WHERE edition_id=? AND node_id=?'),
                ('preview', 'SELECT preview_key,revision_id,node_id,status,classroom_id,runtime_job_id '
                 'FROM learning_textbook_course_previews WHERE edition_id=? AND node_id=?'),
            )
            for kind, query in queries:
                for row in conn.execute(query, (binding['editionId'], binding['nodeId'])).fetchall():
                    source = repository.get_revision(conn, binding['editionId'], row['revision_id'])
                    source_manifest = repository.manifest(source) if source else None
                    same = bool(source_manifest and digest(source_manifest) == source['manifest_sha256']
                                and lesson_scope(source_manifest, binding['nodeId']) == scope)
                    records.append({'kind': kind, 'key': row['content_key' if kind == 'build' else 'preview_key'],
                                    'revisionId': row['revision_id'], 'status': row['status'], 'sameScope': same,
                                    **{k: row[k] for k in ('classroom_id', 'runtime_job_id', 'course_id', 'course_version')
                                       if row.get(k)}})
            # Any known node artifact fences dispatch, including legacy releases,
            # retired builds and failed/ambiguous previews. Review decides reuse.
            return {'manifestSha256': digest(manifest), 'lessonScopeSha256': scope,
                    'checkedAt': timestamp(), 'existingArtifacts': records}


class TextbookWorkbenchAuthoring:
    def __init__(self, guard, output_root, *, origin, client_factory=OpenMaicWorkbenchClient):
        self.guard = guard
        self.output_root = Path(output_root).resolve()
        self.origin = local_origin(origin)
        self.client_factory = client_factory

    def _path(self, binding, teaching_revision):
        if not identifier(str(teaching_revision)):
            fail('teaching_revision_invalid', '教学版本无效')
        return self.output_root / binding['editionId'] / binding['nodeId'] / ('teaching-' + str(teaching_revision)) / 'authoring-job'

    @contextmanager
    def _locked(self, job):
        job = Path(job).resolve()
        if not job.is_relative_to(self.output_root) or job.name != 'authoring-job' or len(job.relative_to(self.output_root).parts) != 4:
            fail('job_path_invalid', '工作目录须在既有教材 operator 输出树中')
        job.parent.parent.mkdir(parents=True, exist_ok=True)
        lock = job.parent.parent / '.workbench-authoring.lock'
        fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield job
        finally:
            os.close(fd)

    @staticmethod
    def _summary(job, frozen, state):
        return {'jobDirectory': str(job), 'status': state['status'], 'requestSha256': frozen['requestSha256'],
                'draftSha256': frozen['draftSha256'], 'binding': frozen['binding'],
                'teachingRevision': frozen['teachingRevision'], 'teacherContract': frozen['teacherContract'],
                'skillIds': frozen['skillIds'], 'primarySkillId': frozen['skillIds'][0],
                **({'interactionPolicy': {'policyId': frozen['interactionPolicy']['policy']['policyId'],
                                         'sha256': frozen['interactionPolicy']['sha256'],
                                         'verification': 'frozen_prompt_requirement_only'}}
                   if 'interactionPolicy' in frozen else {}),
                **({'sceneContract': {'sha256': frozen['sceneContract']['sha256'],
                                      'verification': 'frozen_constraints_not_candidate_acceptance'}}
                   if 'sceneContract' in frozen else {}),
                **{k: state[k] for k in ('sessionId', 'sessionStatus', 'savedStages', 'error', 'httpStatus',
                                        'existingArtifacts', 'message', 'materialsStatus', 'materialCount') if k in state}}

    def _other_artifacts(self, job):
        records = []
        for directory in course_glob(job.parent.parent, 'teaching-*'):
            authoring = directory / 'authoring.json'
            if course_exists(authoring):
                try:
                    data = json.loads(course_text(authoring))
                except (ValueError, OSError):
                    fail('existing_authoring_unreadable', '已有制作记录无法读取，须核对后复用')
                if any(data.get(k) for k in ('sessionId', 'stageId', 'classroomId')):
                    records.append({'kind': 'authoring', 'path': str(authoring), 'status': 'review_for_reuse'})
            other = directory / 'authoring-job'
            if other != job and course_exists(other / 'frozen.json'):
                records.append({'kind': 'operator_job', 'path': str(other), 'status': 'review_for_reuse'})
        receipt = self._widget_successor_receipt(job)
        if receipt:
            parent = receipt['sourceJob']
            records = [record for record in records if not (
                record.get('kind') == 'operator_job' and record.get('path') == parent)]
        return records

    def _empty_terminal_source(self, source, frozen, draft, state, classroom_directory):
        """Read-only, fail-closed proof for the no-assets successor route."""
        marker = source / 'dispatch.json'
        if not course_exists(marker) or not state.get('sessionId'):
            fail('successor_parent_invalid', '父任务必须有可核验的原始派发与会话')
        if (source / 'material-attachments').exists() or course_is_dir(source / 'material-attachments'):
            fail('successor_parent_has_artifacts', '父任务已有操作员附件，不能丢弃后走无素材继任')
        client = self.client_factory(self.origin, source / 'owner.cookies')
        payload, identity = self._material_payload(source, frozen, draft)
        dispatch = json.loads(course_text(marker))
        session = client.session(state['sessionId'])
        if (dispatch.get('requestSha256') != identity['requestSha256']
                or dispatch.get('payloadSha256') != identity['payloadSha256']
                or dispatch.get('ownerFingerprint') != client.owner_fingerprint()
                or session.get('id') != state['sessionId'] or not self._match(session, identity)):
            fail('successor_parent_invalid', '父任务的派发、会话与原冻结请求不匹配')
        if session.get('status') not in {'succeeded', 'failed', 'cancelled'}:
            fail('successor_parent_active', '父任务尚未正常终止，不能创建继任')
        events = client.stage_events(session['id'])
        if any(event.get('type') in {'stage_link', 'course_link', 'library_changed'} for event in events):
            fail('successor_parent_has_artifacts', '父任务已有课程或素材事件，须先审核复用，不能走无素材继任')
        materials = client.session_materials(session['id'])
        if any(material.get('kind') not in {'web', 'text'} for material in materials):
            fail('successor_parent_has_artifacts', '父任务已有非文字素材，须走素材继承审核')
        root = Path(classroom_directory).resolve()
        if not course_is_dir(root):
            fail('successor_parent_invalid', '需要真实本机课堂媒体目录以核验原素材')
        stage_id = session.get('stageId')
        if not identifier(stage_id):
            fail('successor_parent_invalid', '父会话缺少可核验的原 stage 身份')
        try:
            document = client.stage(stage_id)
        except WorkbenchError as error:
            if error.http_status != 404:
                raise
            document = None
        # A saved stage, even empty, may contain assets or a candidate receipt.
        # This narrow route never silently discards one.
        folder, exported = root / stage_id, root / (stage_id + '.json')
        if (document is not None or course_exists(exported) or exported.is_symlink()
                or folder.is_symlink()
                or (folder.exists() and not folder.is_dir())
                or any(course_glob(folder, '*', recursive=True))):
            fail('successor_parent_has_artifacts', '父任务已有 stage、候选或媒体文件，不能走无素材继任')
        if state.get('savedStages') or list(course_glob(source, 'saved-*.json')):
            fail('successor_parent_has_artifacts', '父任务已有保存成果，不能走无素材继任')
        return {'session': session, 'materials': materials, 'events': events,
                'classroomDirectory': str(root), 'stageId': stage_id,
                'savedStageAbsent': True, 'candidateAbsent': True, 'mediaAbsent': True}

    def _widget_successor_receipt(self, job, *, live=False):
        path = job / 'widget-successor.json'
        if not course_exists(path):
            return None
        try:
            if path.is_symlink():
                raise ValueError()
            receipt = json.loads(course_text(path))
            body = {k: v for k, v in receipt.items() if k != 'sha256'}
            source = Path(receipt['sourceJob']).resolve()
            if (receipt.get('schemaVersion') != 'mira.operator.empty-widget-successor.v1'
                    or receipt.get('sha256') != digest(body)
                    or source.parent.parent != job.parent.parent or source == job
                    or source.name != 'authoring-job'
                    or not source.is_relative_to(self.output_root)
                    or course_exists(source / 'widget-successor.json')
                    or set(receipt['sourceFileSha256']) != {'draft.json', 'frozen.json', 'dispatch.json'}):
                raise ValueError()
            for name, expected in receipt['sourceFileSha256'].items():
                if name not in {'draft.json', 'frozen.json', 'dispatch.json'}:
                    raise ValueError()
                original, archived = source / name, job / 'predecessor' / name
                if (original.is_symlink() or archived.is_symlink() or sha(course_bytes(original)) != expected
                        or course_bytes(archived) != course_bytes(original)):
                    raise ValueError()
            source_frozen, source_draft, source_state = self._load(source)
            target = json.loads(course_text(job / 'draft.json'))
            if (sha(course_bytes(job / 'draft.json')) != receipt['targetDraftSha256']
                    or sha(course_bytes(job / 'frozen.json')) != receipt['targetFrozenSha256']
                    or widget_successor_diff(source_draft, target) != receipt['change']):
                raise ValueError()
            pointer = json.loads(course_text(source / 'widget-successor-intent.json'))
            if pointer != receipt['intent'] or pointer['targetJob'] != str(job):
                raise ValueError()
            evidence_raw = course_bytes(job / 'predecessor/terminal-empty-source.json')
            if sha(evidence_raw) != receipt['sourceEvidenceSha256']:
                raise ValueError()
            evidence = json.loads(evidence_raw)
        except (KeyError, OSError, TypeError, ValueError, UnicodeError):
            fail('successor_integrity_error', '继任或父任务审核记录发生变化，禁止派发')
        if live:
            fresh = self._empty_terminal_source(source, source_frozen, source_draft, source_state,
                                                evidence['classroomDirectory'])
            if digest(fresh) != digest(evidence):
                fail('successor_parent_changed', '父会话或素材在审核后改变，停止继任派发')
        return receipt

    def supersede_unsupported_widget(self, source_job, draft_path, *, teaching_revision,
                                     expected_source_draft_sha256, reviewer, basis, classroom_directory):
        """Explicit reviewed successor; never revise the original frozen job."""
        if not reviewer.strip() or not basis.strip():
            fail('successor_review_required', '继任需要明确审核者与原因')
        source = Path(source_job).resolve()
        with self._locked(source):
            frozen, original, state = self._load(source)
            if (frozen['schemaVersion'] != 'mira.operator.workbench-authoring.v3'
                    or frozen['draftSha256'] != expected_source_draft_sha256
                    or course_exists(source / 'widget-successor.json')):
                fail('successor_parent_invalid', '只允许原始 v3 父任务及准确草稿摘要')
            raw = course_bytes(Path(draft_path))
            corrected = json.loads(raw)
            change = widget_successor_diff(original, corrected)
            job = self._path(corrected['binding'], teaching_revision)
            if job == source:
                fail('successor_parent_invalid', '继任必须使用新的教学版本，不得覆盖父任务')
            check = self.guard.inspect(corrected['binding'])
            if check['existingArtifacts'] or any(check[k] != frozen['catalogCheck'][k]
                                                for k in ('manifestSha256', 'lessonScopeSha256')):
                fail('successor_parent_has_artifacts', '已有预览/发布成果或教材变化，不能走无素材继任')
            evidence = self._empty_terminal_source(source, frozen, original, state, classroom_directory)
            intent = {'sourceJob': str(source), 'targetJob': str(job),
                      'sourceDraftSha256': expected_source_draft_sha256,
                      'sourceFileSha256': {name: sha(course_bytes(source / name))
                                          for name in ('draft.json', 'frozen.json', 'dispatch.json')},
                      'targetDraftSha256': sha(raw), 'reviewer': reviewer, 'basis': basis, 'change': change}
            immutable_write(source / 'widget-successor-intent.json', json_bytes(intent))
        # prepare takes the same per-node lock. Do not nest it under source lock.
        self.prepare(draft_path, teaching_revision=teaching_revision)
        with self._locked(job):
            records = self._other_artifacts(job)
            if any(not (record.get('kind') == 'operator_job' and record.get('path') == str(source))
                   for record in records):
                fail('successor_other_artifacts', '存在其他同课任务，不能豁免重复生成栅栏')
            archive = job / 'predecessor'
            archive.mkdir(mode=0o700, exist_ok=True)
            source_hashes = {}
            for name in ('draft.json', 'frozen.json', 'dispatch.json'):
                data = course_bytes(source / name)
                if sha(data) != intent['sourceFileSha256'][name]:
                    fail('successor_parent_changed', '父冻结文件在审核后改变，停止继任准备')
                immutable_write(archive / name, data)
                source_hashes[name] = sha(data)
            evidence_bytes = json_bytes(evidence)
            immutable_write(archive / 'terminal-empty-source.json', evidence_bytes)
            body = {'schemaVersion': 'mira.operator.empty-widget-successor.v1', **intent,
                    'sourceFileSha256': source_hashes, 'sourceEvidenceSha256': sha(evidence_bytes),
                    'targetFrozenSha256': sha(course_bytes(job / 'frozen.json')),
                    'intent': intent}
            immutable_write(job / 'widget-successor.json', json_bytes({**body, 'sha256': digest(body)}))
            self._widget_successor_receipt(job, live=True)
            target_frozen, _, target_state = self._load(job)
            if course_exists(job / 'dispatch.json'):
                return self._summary(job, target_frozen, target_state)
            target_state.update(status='prepared', existingArtifacts=[],
                                message='无素材父任务已终止并归档；仅修正一处渲染枚举，继任尚未派发')
            self._save_state(job, target_state)
            return self._summary(job, target_frozen, target_state)

    def prepare(self, draft_path, *, teaching_revision='1'):
        raw = course_bytes(Path(draft_path))
        try:
            draft = json.loads(raw)
        except (ValueError, UnicodeError):
            fail('draft_invalid', '草案 JSON 不可读')
        binding = validate_draft(draft)
        validate_native_widget_types(draft)
        if binding.get('teachingRevision', str(teaching_revision)) != str(teaching_revision):
            fail('teaching_revision_mismatch', '草案与指定教学版本不一致')
        with self._locked(self._path(binding, teaching_revision)) as job:
            if course_exists(job / 'frozen.json'):
                frozen, _, state = self._load(job)
                if frozen['draftSha256'] != sha(raw) or frozen['origin'] != self.origin:
                    fail('draft_already_frozen', '本教学版本已有不同的冻结请求；禁止覆盖或另派发')
                return self._summary(job, frozen, state)
            if job.exists() and any(job.iterdir()):
                fail('incomplete_job', '已有不完整冻结记录，保留并核查，不能覆盖')
            check = self.guard.inspect(binding)
            artifacts = check['existingArtifacts'] + self._other_artifacts(job)
            frozen = {'schemaVersion': 'mira.operator.workbench-authoring.v3', 'createdAt': timestamp(),
                      'draftSha256': sha(raw), 'draftCanonicalSha256': digest(draft),
                      'requestSha256': sha(draft['request'].encode()), 'binding': binding,
                      'teacherContract': draft['teacherContract'], 'skillIds': draft['skillIds'],
                      'teachingRevision': str(teaching_revision), 'origin': self.origin, 'catalogCheck': check,
                      'payloadSha256': digest({'prompt': draft['request'], 'skill': draft['skillIds'][0]})}
            try:
                frozen['interactionPolicy'] = freeze_interaction_policy()
            except (OSError, ValueError):
                fail('interaction_policy_integrity_error', '互动规则无法完整冻结，停止准备新课')
            try:
                frozen['sceneContract'] = freeze_scene_contract(draft, check, frozen['interactionPolicy'])
            except ValueError:
                fail('scene_contract_invalid', '新课须包含准确教材范围、完整逐页计划、互动规则和锁定测评')
            self._base_dispatch_payload(frozen, draft)
            state = {'status': 'reuse_review_required' if artifacts else 'prepared', 'existingArtifacts': artifacts,
                     'updatedAt': timestamp(), 'message': '已有记录须核查复用，未判断达到 Claude 标准' if artifacts else '冻结完成，尚未派发'}
            job.mkdir(parents=True, mode=0o700, exist_ok=True)
            os.chmod(job, 0o700)
            private_write(job / 'draft.json', raw)
            write_json(job / 'frozen.json', frozen)
            write_json(job / 'state.json', state)
            return self._summary(job, frozen, state)

    def _amendment_records(self, job, *, ignore=None):
        """Any incomplete archive is a dispatch fence, even before live writes."""
        folder = job / 'amendments'
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            fail('amendment_integrity_error', '修订归档目录不能是符号链接')
        records = {}
        if not course_is_dir(folder):
            return records
        for archive in course_glob(folder):
            if archive.name == ignore:
                continue
            if archive.is_symlink() or not course_is_dir(archive) or not re.fullmatch('[0-9a-f]{64}', archive.name):
                fail('amendment_integrity_error', '修订归档目录无效')
            intent = self._amendment_intent(archive)
            if intent['sourceEvidence'] != self._source_evidence(job,
                    draft=json.loads(intent['files']['source-draft.json']),
                    frozen=json.loads(intent['files']['source-frozen.json'])):
                fail('amendment_integrity_error', '修订保留的官方来源材料发生变化，禁止派发')
            if not course_exists(archive / 'receipt.json'):
                fail('amendment_pending', '草稿修订未完成；只能用同一 amend 请求恢复，禁止派发')
            try:
                receipt = json.loads(course_text(archive / 'receipt.json'))
                if (archive.joinpath('receipt.json').is_symlink()
                        or receipt != self._amendment_receipt(intent, receipt['completedAt'])):
                    raise ValueError()
                for name, raw in intent['files'].items():
                    file = archive / name
                    if file.is_symlink() or course_bytes(file) != raw.encode():
                        raise ValueError()
            except (OSError, ValueError, KeyError, TypeError):
                fail('amendment_integrity_error', '修订归档或完成收据不一致，禁止派发')
            records[archive.name] = intent
        return records

    @staticmethod
    def _amendment_intent(archive):
        try:
            path = archive / 'intent.json'
            if not course_exists(path):
                fail('amendment_pending', '草稿修订尚未完成，禁止派发')
            intent = json.loads(course_text(path))
            identity = intent['identity']
            if (path.is_symlink() or digest(identity) != archive.name
                    or intent['sha256'] != digest({k: v for k, v in intent.items() if k != 'sha256'})
                    or set(intent['files']) != {f'{side}-{name}.json' for side in ('source', 'target')
                                               for name in ('draft', 'frozen', 'state')}
                    or any(not isinstance(raw, str) for raw in intent['files'].values())):
                raise ValueError()
            for side in ('source', 'target'):
                raw = intent['files'][f'{side}-draft.json'].encode()
                frozen = json.loads(intent['files'][f'{side}-frozen.json'])
                if sha(raw) != identity[f'{side}DraftSha256'] or frozen['draftSha256'] != sha(raw):
                    raise ValueError()
            if json.loads(intent['files']['target-frozen.json'])['draftAmendmentId'] != archive.name:
                raise ValueError()
            if not isinstance(intent['sourceEvidence'], list):
                raise ValueError()
            return intent
        except (OSError, ValueError, KeyError, TypeError):
            fail('amendment_integrity_error', '修订意图或摘要不一致，禁止恢复')

    @staticmethod
    def _amendment_receipt(intent, completed_at):
        return {'schemaVersion': 'mira.operator.workbench-draft-amendment.v1',
                'revisionId': digest(intent['identity']), 'intentSha256': intent['sha256'],
                **intent['identity'], 'completedAt': completed_at,
                'targetFrozenSha256': sha(intent['files']['target-frozen.json'].encode()),
                'generationDispatched': False}

    def _load(self, job, *, ignore_amendment=None):
        amendments = self._amendment_records(job, ignore=ignore_amendment)
        try:
            frozen = json.loads(course_text(job / 'frozen.json'))
            raw = course_bytes(job / 'draft.json')
            draft = json.loads(raw)
            state = json.loads(course_text(job / 'state.json')) if course_exists(job / 'state.json') else {'status': 'dispatch_unknown'}
        except (OSError, ValueError, UnicodeError):
            fail('job_invalid', '冻结记录不可读，禁止重新派发')
        schema = frozen.get('schemaVersion')
        if schema not in ('mira.operator.workbench-authoring.v1', 'mira.operator.workbench-authoring.v2',
                          'mira.operator.workbench-authoring.v3'):
            fail('frozen_integrity_error', '冻结记录版本未知，禁止派发')
        if (schema != 'mira.operator.workbench-authoring.v1') != ('interactionPolicy' in frozen):
            fail('interaction_policy_integrity_error', '冻结记录版本与互动规则快照不匹配，禁止派发')
        if (schema == 'mira.operator.workbench-authoring.v3') != ('sceneContract' in frozen):
            fail('scene_contract_integrity_error', '冻结记录版本与逐页生成合同不匹配，禁止派发')
        binding = validate_draft(draft, check_current_teacher=False)
        payload = {'prompt': draft['request'], 'skill': draft['skillIds'][0]}
        if (frozen['draftSha256'] != sha(raw) or frozen['draftCanonicalSha256'] != digest(draft)
                or frozen['requestSha256'] != sha(draft['request'].encode()) or frozen['payloadSha256'] != digest(payload)
                or frozen['binding'] != binding or frozen['teacherContract'] != draft['teacherContract']
                or frozen['skillIds'] != draft['skillIds'] or frozen['origin'] != self.origin
                or self._path(binding, frozen['teachingRevision']) != job):
            fail('frozen_integrity_error', '冻结请求、路径、教师或工作台地址发生变化，停止派发')
        self._base_dispatch_payload(frozen, draft)
        parents = {json.loads(i['files']['source-frozen.json']).get('draftAmendmentId') for i in amendments.values()}
        heads = set(amendments) - parents
        if amendments:
            head = frozen.get('draftAmendmentId')
            if heads != {head} or amendments[head]['files']['target-frozen.json'].encode() != course_bytes(job / 'frozen.json'):
                fail('amendment_integrity_error', '当前冻结草稿不是修订链的最后版本')
            for intent in amendments.values():
                parent = json.loads(intent['files']['source-frozen.json']).get('draftAmendmentId')
                if parent and (parent not in amendments or any(
                        intent['files'][f'source-{name}.json'] != amendments[parent]['files'][f'target-{name}.json']
                        for name in ('draft', 'frozen'))):
                    fail('amendment_integrity_error', '修订归档的前序草稿不一致')
        elif frozen.get('draftAmendmentId') and frozen['draftAmendmentId'] != ignore_amendment:
            fail('amendment_integrity_error', '冻结草稿缺少原修订归档')
        self._widget_successor_receipt(job)
        return frozen, draft, state

    def _initial_draft_sha(self, job, frozen):
        cursor, seen = frozen, set()
        while cursor.get('draftAmendmentId'):
            revision = cursor['draftAmendmentId']
            if (not isinstance(revision, str) or not re.fullmatch('[0-9a-f]{64}', revision)
                    or revision in seen or len(seen) >= 64):
                fail('amendment_integrity_error', '原稿修订来源链无效')
            seen.add(revision)
            intent = self._amendment_intent(job / 'amendments' / revision)
            if json.loads(intent['files']['target-frozen.json']) != cursor:
                fail('amendment_integrity_error', '原稿修订来源链未绑定当前冻结版本')
            cursor = json.loads(intent['files']['source-frozen.json'])
        return cursor['draftSha256']

    def _lesson_source_evidence(self, job, draft, frozen):
        """Only exact bound source review and the original draft may be siblings."""
        records, allowed = [], set()
        sources = job.parent / 'sources'
        if sources.exists() or course_is_dir(sources) or sources.is_symlink():
            reference = draft.get('sourceReview')
            if not isinstance(reference, str) or not reference or '..' in Path(reference).parts:
                fail('amendment_existing_artifact', '同课来源须由原冻结草稿精确绑定')
            source = Path(reference)
            if not source.is_absolute():
                source = Path(__file__).resolve().parents[2] / source
            if (sources.is_symlink() or not course_is_dir(sources) or source.is_symlink()
                    or source.parent != sources or not course_exists(source) or source.suffix != '.json'
                    or source.name.startswith('.') or re.search(
                        r'(dispatch|owner|cookie|session|stage|classroom|receipt|audio|generated)', source.name, re.I)
                    or any(path != source or path.is_symlink() for path in course_glob(sources))):
                fail('amendment_existing_artifact', '同课来源目录只能包含绑定的普通审查文件')
            raw = course_bytes(source)
            try:
                review = json.loads(raw)
            except (ValueError, UnicodeError):
                fail('amendment_existing_artifact', '同课来源审查文件无效')
            if (not isinstance(review, dict) or review.get('schemaVersion') != 'mira.operator.lesson-source-review.v1'
                    or review.get('binding') != frozen['binding']):
                fail('amendment_existing_artifact', '同课来源审查与冻结教材身份不同')
            allowed.add(sources)
            records.append({'path': '../sources/' + source.name, 'sha256': sha(raw), 'bytes': len(raw)})
        original = job.parent / 'preauthoring-candidate.json'
        if course_exists(original) or original.is_symlink():
            if original.is_symlink() or not course_exists(original):
                fail('amendment_existing_artifact', '原始草稿副本必须是普通文件')
            raw = course_bytes(original)
            if sha(raw) != self._initial_draft_sha(job, frozen):
                fail('amendment_existing_artifact', '同课原始草稿不是冻结链中的原字节')
            allowed.add(original)
            records.append({'path': '../preauthoring-candidate.json', 'sha256': sha(raw), 'bytes': len(raw)})
        return records, allowed

    def _source_evidence(self, job, *, draft=None, frozen=None):
        """Preserve read-only source inputs, never accept runtime outputs here."""
        folder = job / 'source-evidence'
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            fail('amendment_existing_artifact', '来源材料目录必须是本地普通目录')
        records = []
        for path in sorted(course_glob(folder, '*', recursive=True)) if course_is_dir(folder) else []:
            if (path.is_symlink() or path.name.startswith('.') or re.search(
                    r'(dispatch|owner|cookie|session|stage|classroom|receipt|audio|generated)', path.name, re.I)):
                fail('amendment_existing_artifact', '来源材料不能包含链接、运行身份、派发记录或生成成果')
            if course_is_dir(path):
                continue
            if not course_exists(path) or path.suffix.lower() not in {'.json', '.txt', '.html', '.pdf', '.png', '.jpg', '.jpeg', '.webp'}:
                fail('amendment_existing_artifact', '来源材料包含未知文件类型')
            raw = course_bytes(path)
            records.append({'path': path.relative_to(job).as_posix(), 'sha256': sha(raw), 'bytes': len(raw)})
        if draft is not None and frozen is not None:
            sibling_records, _ = self._lesson_source_evidence(job, draft, frozen)
            records.extend(sibling_records)
        return records

    def _amendment_eligible(self, job, state, candidate_path, *, draft, frozen):
        if (state.get('status') != 'prepared' or state.get('error')
                or any(state.get(k) for k in ('sessionId', 'sessionStatus', 'savedStages', 'existingArtifacts',
                                              'stageId', 'classroomId', 'runtimeJobId'))):
            fail('amendment_not_prepared', '只能修订尚未派发、没有会话或成果的 prepared 草稿')
        allowed = {'draft.json', 'frozen.json', 'state.json', 'amendments', 'source-evidence'}
        # The reviewed input may live beside the frozen draft, but never masks a
        # dispatch fence, owner identity or output artifact.
        if (candidate_path.parent == job and candidate_path.name not in allowed
                and not re.search(r'(dispatch|owner|cookie|session|stage|classroom|receipt|audio|generated)',
                                  candidate_path.name, re.I)):
            allowed.add(candidate_path.name)
        _, sibling_sources = self._lesson_source_evidence(job, draft, frozen)
        if (any(path.name not in allowed or path.is_symlink() for path in course_glob(job))
                or any(path not in {job, *sibling_sources} for path in course_glob(job.parent))):
            fail('amendment_existing_artifact', '已有派发/owner/保存成果或未知工作文件，禁止修订冻结草稿')
        return self._source_evidence(job, draft=draft, frozen=frozen)

    def amend(self, job_path, draft_path, *, expected_draft_sha256, reviewer, basis):
        """Amend an undispatched draft; replay the same intent after interruption."""
        if (not isinstance(expected_draft_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_draft_sha256)
                or any(not isinstance(v, str) or not v.strip() for v in (reviewer, basis))):
            fail('amendment_invalid', '需要原草稿 SHA256、审核人和具体修订依据')
        candidate_path = Path(draft_path).resolve()
        raw = course_bytes(candidate_path)
        try:
            new = json.loads(raw)
        except (ValueError, UnicodeError):
            fail('draft_invalid', '新草案 JSON 不可读')
        validate_draft(new)
        with self._locked(job_path) as job:
            if candidate_path in {job / f'{name}.json' for name in ('draft', 'frozen', 'state')}:
                fail('amendment_invalid', '候选必须与冻结草稿文件分开保存')
            identity = {'jobDirectory': str(job), 'sourceDraftSha256': expected_draft_sha256,
                        'targetDraftSha256': sha(raw), 'reviewer': reviewer, 'basis': basis}
            revision = digest(identity)
            archive = job / 'amendments' / revision
            if archive.is_symlink() or (job / 'amendments').is_symlink():
                fail('amendment_integrity_error', '修订归档目录不能是符号链接')
            if course_exists(archive / 'intent.json'):
                intent = self._amendment_intent(archive)
                if intent['identity'] != identity or intent['files']['target-draft.json'].encode() != raw:
                    fail('amendment_conflict', '修订恢复参数与原意图不同')
                frozen = json.loads(intent['files']['source-frozen.json'])
                old = json.loads(intent['files']['source-draft.json'])
                state = json.loads(course_text(job / 'state.json'))
                self._amendment_records(job, ignore=revision)
                for name in ('draft', 'frozen', 'state'):
                    current = course_bytes(job / f'{name}.json')
                    if current not in {intent['files'][f'{side}-{name}.json'].encode() for side in ('source', 'target')}:
                        fail('amendment_conflict', '当前文件已偏离归档中的原稿/新稿，禁止覆盖')
            else:
                if archive.exists() and any(not p.name.startswith('.authoring-') or p.is_symlink() for p in archive.iterdir()):
                    fail('amendment_integrity_error', '未完成归档缺少有效意图，停止覆盖')
                frozen, old, state = self._load(job, ignore_amendment=revision)
                if frozen['draftSha256'] != expected_draft_sha256:
                    fail('amendment_source_changed', '原草稿 SHA256 已改变，禁止修订')
                intent = None
            source_evidence = self._amendment_eligible(job, state, candidate_path, draft=old, frozen=frozen)
            if intent is not None and intent['sourceEvidence'] != source_evidence:
                fail('amendment_conflict', '来源材料与修订意图摘要不一致，禁止恢复')
            amendment_draft(old, new)
            check = self.guard.inspect(frozen['binding'])
            if any(check[k] != frozen['catalogCheck'][k] for k in ('manifestSha256', 'lessonScopeSha256')):
                fail('catalog_changed', '教材目录或课次范围已改变，禁止修订')
            if check['existingArtifacts'] or self._other_artifacts(job):
                fail('amendment_existing_artifact', '已有课件/制作记录，先核对复用，禁止修订')
            if intent is None:
                revised = {**deepcopy(frozen), 'draftAmendmentId': revision, 'draftSha256': sha(raw),
                           'draftCanonicalSha256': digest(new), 'requestSha256': sha(new['request'].encode()),
                           'payloadSha256': digest({'prompt': new['request'], 'skill': new['skillIds'][0]})}
                if 'sceneContract' in revised:
                    try:
                        revised['sceneContract'] = freeze_scene_contract(new, revised['catalogCheck'],
                                                                         revised['interactionPolicy'])
                    except ValueError:
                        fail('scene_contract_invalid', '修订后的逐页生成合同无效，原冻结记录保持不变')
                self._base_dispatch_payload(revised, new)
                revised_state = {**state, 'draftAmendmentId': revision, 'updatedAt': timestamp(),
                                 'message': '冻结草稿修订完成，尚未派发'}
                files = {f'source-{name}.json': course_bytes(job / f'{name}.json').decode()
                         for name in ('draft', 'frozen', 'state')}
                files.update({'target-draft.json': raw.decode(), 'target-frozen.json': json_bytes(revised).decode(),
                              'target-state.json': json_bytes(revised_state).decode()})
                intent = {'schemaVersion': 'mira.operator.workbench-draft-amendment-intent.v1',
                          'createdAt': timestamp(), 'identity': identity, 'catalogCheck': check,
                          'sourceEvidence': source_evidence, 'files': files}
                intent['sha256'] = digest(intent)
                archive.mkdir(parents=True, mode=0o700, exist_ok=True)
                for directory in (archive.parent, job):
                    fd = os.open(directory, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                immutable_write(archive / 'intent.json', json_bytes(intent))
            for name, content in intent['files'].items():
                immutable_write(archive / name, content.encode())
            if course_exists(archive / 'receipt.json'):
                current_frozen, _, current_state = self._load(job)
                return {**self._summary(job, current_frozen, current_state),
                        'amendment': json.loads(course_text(archive / 'receipt.json'))}
            for name in ('draft', 'frozen', 'state'):
                private_write(job / f'{name}.json', intent['files'][f'target-{name}.json'].encode())
            receipt = self._amendment_receipt(intent, timestamp())
            immutable_write(archive / 'receipt.json', json_bytes(receipt))
            current_frozen, _, current_state = self._load(job)
            return {**self._summary(job, current_frozen, current_state), 'amendment': receipt}

    @staticmethod
    def _material_manifest(path, frozen):
        path = Path(path).resolve()
        raw = course_bytes(path)
        data = material_json(path)
        assets = data.get('assets')
        if (data.get('schemaVersion') != 'mira.operator.material-attachments.v1'
                or not isinstance(assets, list) or not 1 <= len(assets) <= 20):
            fail('material_manifest_invalid', '附件清单须有 1–20 个已审核的 PNG 或 UTF-8 纯文本')
        records = []
        seen = set()
        for asset in assets:
            if not isinstance(asset, dict):
                fail('material_manifest_invalid', '附件记录无效')
            key = asset.get('assetKey')
            mime = asset.get('mimeType', 'image/png')
            if (not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', key)
                    or key in seen or not isinstance(asset.get('path'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', str(asset.get('sha256', '')))
                    or mime not in ('image/png', 'text/plain')
                    or (mime == 'image/png' and any(type(asset.get(k)) is not int or asset[k] <= 0
                                                    for k in ('width', 'height')))):
                fail('material_manifest_invalid', '附件需要唯一 assetKey、路径、SHA256、合法 MIME；PNG 需要真实尺寸')
            seen.add(key)
            source = path.parent / asset['path']
            if source.is_symlink() or not course_exists(source):
                fail('material_source_invalid', '附件来源必须是本地普通文件')
            source = source.resolve()
            body = course_bytes(source)
            if (not body or len(body) > 50 * 1024 * 1024 or sha(body) != asset['sha256']
                    or ('byteSize' in asset and (type(asset['byteSize']) is not int or asset['byteSize'] != len(body)))):
                fail('material_source_changed', '附件原字节、摘要或长度与审核清单不符')
            dimensions = {}
            extension = '.txt'
            if mime == 'image/png':
                if png_dimensions(body) != (asset['width'], asset['height']):
                    fail('material_source_changed', 'PNG 尺寸与审核清单不符')
                dimensions = {'width': asset['width'], 'height': asset['height']}
                extension = '.png'
            else:
                try:
                    text = body.decode('utf-8')
                except UnicodeError:
                    fail('material_text_invalid', '纯文本附件必须为完整 UTF-8 原字节')
                if not text.strip() or any(ord(c) < 32 and c not in '\t\r\n' for c in text):
                    fail('material_text_invalid', '纯文本附件不能为空或含二进制控制字符')
            records.append({'assetKey': key, 'sourcePath': str(source), 'file': key + extension,
                            'mimeType': mime, 'sha256': asset['sha256'], 'bytes': len(body), **dimensions,
                            'originalName': key + '-' + asset['sha256'][:16] + extension})
        result = {'schemaVersion': 'mira.operator.frozen-material-attachments.v1',
                  'baseDraftSha256': frozen['draftSha256'], 'basePayloadSha256': frozen['payloadSha256'],
                  'inputSha256': sha(raw), 'input': data, 'assets': records}
        result['sha256'] = digest(result)
        return result

    @staticmethod
    def _read_material_manifest(job, frozen):
        folder = job / 'material-attachments'
        if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
            fail('material_integrity_error', '附件归档目录无效')
        if not course_is_dir(folder):
            return None
        manifest = material_json(folder / 'manifest.json')
        if (manifest.get('sha256') != digest({k: v for k, v in manifest.items() if k != 'sha256'})
                or manifest.get('baseDraftSha256') != frozen['draftSha256']
                or manifest.get('basePayloadSha256') != frozen['payloadSha256']
                or not isinstance(manifest.get('assets'), list) or not 1 <= len(manifest['assets']) <= 20):
            fail('material_integrity_error', '附件不属于当前冻结草稿，禁止派发')
        return manifest

    @staticmethod
    def _base_dispatch_payload(frozen, draft):
        """Historical jobs keep their exact bytes; v3 also binds each page generator."""
        prompt = draft['request']
        if 'interactionPolicy' in frozen:
            try:
                prompt = interaction_policy_prompt(frozen['interactionPolicy']) + prompt
            except ValueError:
                fail('interaction_policy_integrity_error', '冻结互动规则的结构或摘要不一致，禁止派发')
        if 'sceneContract' in frozen:
            try:
                validate_scene_contract(frozen['sceneContract'], draft=draft,
                                        catalog_check=frozen['catalogCheck'],
                                        interaction_policy=frozen['interactionPolicy'])
                # The native create route trims the whole opening prompt. Keep
                # the newline-delimited contract marker internal so dispatch
                # identity survives that route unchanged.
                prompt = '【已冻结的逐页生成合同】' + render_scene_contract(frozen['sceneContract']) + prompt
                if prompt.count(PROMPT_START) != 1 or prompt.count(PROMPT_END) != 1:
                    raise ValueError('Ambiguous embedded scene contract')
            except (KeyError, ValueError):
                fail('scene_contract_integrity_error', '冻结逐页生成合同与教材、草稿或规则不一致，禁止派发')
        if len(prompt.encode('utf-16-le')) // 2 > 100_000:
            fail('dispatch_request_too_long', '合并冻结互动规则后的完整请求超过工作台限制，禁止派发')
        return {'prompt': prompt, 'skill': draft['skillIds'][0]}

    @staticmethod
    def _require_scene_contract_runtime(client, frozen):
        # Populated by the existing owner-scoped GET, before any new POST.
        # Recovery is deliberately independent of today's runtime capability.
        if ('sceneContract' in frozen
                and getattr(client, 'scene_contract_schema', None) != SNAPSHOT_SCHEMA):
            fail('scene_contract_runtime_unavailable', '当前原生运行服务未加载逐页合同校验；保留新课草稿，禁止派发')

    def _material_payload(self, job, frozen, draft):
        """Derive a separate dispatch contract without rewriting historical frozen.json."""
        payload = self._base_dispatch_payload(frozen, draft)
        dispatch_frozen = {**frozen, 'requestSha256': sha(payload['prompt'].encode()),
                           'payloadSha256': digest(payload)}
        manifest = self._read_material_manifest(job, frozen)
        if manifest is None:
            return payload, dispatch_frozen
        folder = job / 'material-attachments'
        if not course_exists(folder / 'ready.json'):
            fail('material_attachments_not_ready', '首轮附件尚未全部上传并核验，禁止派发')
        ready = material_json(folder / 'ready.json')
        owner = material_json(folder / 'owner.json')
        if owner.get('manifestSha256') != manifest['sha256']:
            fail('material_integrity_error', '附件 owner 记录不匹配')
        receipts, material_ids, titles, bindings = {}, [], {}, []
        for asset in manifest['assets']:
            snapshot = folder / asset['file']
            if snapshot.is_symlink() or not course_exists(snapshot) or sha(course_bytes(snapshot)) != asset['sha256']:
                fail('material_source_changed', '冻结附件字节已改变，禁止派发')
            intent = material_json(folder / (asset['assetKey'] + '-intent.json'))
            receipt = material_json(folder / (asset['assetKey'] + '-receipt.json'))
            expected = self._upload_intent(manifest, owner, asset)
            material = receipt.get('response', {}).get('material', {})
            if (intent != expected or receipt.get('intentSha256') != digest(intent)
                    or not self._valid_upload(receipt.get('response'), asset, intent['requestId'])):
                fail('material_integrity_error', '附件上传回执不匹配')
            material_ids.append(material['materialId'])
            titles[material['materialId']] = asset['originalName']
            bindings.append({key: material[key] for key in ('materialId', 'originalName', 'mime', 'bytes')})
            receipts[asset['assetKey']] = digest(receipt)
        if len(set(material_ids)) != len(material_ids):
            fail('material_integrity_error', '不同附件意外绑定同一素材 ID')
        payload['materialIds'] = material_ids
        expected_ready = {'schemaVersion': 'mira.operator.material-dispatch.v1',
                          'manifestSha256': manifest['sha256'], 'ownerFingerprint': owner['ownerFingerprint'],
                          'uploadReceiptSha256': receipts, 'payload': payload, 'payloadSha256': digest(payload)}
        if ready != expected_ready:
            fail('material_integrity_error', '附件派发合同不完整或已改变')
        return payload, {**dispatch_frozen, 'payloadSha256': digest(payload), 'materialsSha256': digest(ready),
                         'materialsOwnerFingerprint': owner['ownerFingerprint'], 'materialTitles': titles,
                         'materialBindings': bindings}

    @staticmethod
    def _upload_intent(manifest, owner, asset):
        identity = {'manifestSha256': manifest['sha256'], 'ownerFingerprint': owner['ownerFingerprint'],
                    'assetKey': asset['assetKey'], 'sha256': asset['sha256'], 'bytes': asset['bytes'],
                    'mimeType': asset['mimeType'], 'originalName': asset['originalName'],
                    **{key: asset[key] for key in ('width', 'height') if key in asset}}
        return {**identity, 'requestId': 'material-' + digest(identity)}

    @staticmethod
    def _valid_upload(response, asset, request_id):
        if not isinstance(response, dict) or not isinstance(response.get('material'), dict):
            return False
        material = response['material']
        return (response.get('httpStatus') == 201 and response.get('requestId') == request_id
                and identifier(material.get('materialId')) and material.get('mime') == asset['mimeType']
                and material.get('bytes') == asset['bytes'] and material.get('originalName') == asset['originalName'])

    def attach_materials(self, job_path, manifest_path):
        """Freeze/upload once per PNG or text. Unknown uploads remain fenced, never retried."""
        with self._locked(job_path) as job:
            frozen, draft, state = self._load(job)
            payload = self._base_dispatch_payload(frozen, draft)
            dispatch_frozen = {**frozen, 'requestSha256': sha(payload['prompt'].encode()),
                               'payloadSha256': digest(payload)}
            if (course_exists(job / 'dispatch.json') or state.get('sessionId')
                    or state.get('status') != 'prepared' or state.get('existingArtifacts')):
                fail('materials_not_prepared', '只有尚未派发的 prepared 草稿可绑定首轮附件')
            proposed = self._material_manifest(manifest_path, frozen)
            planned = draft.get('assetPlan', {}).get('assetKeys')
            # Plain text carries shared vector/source data and does not add an image.
            if planned is not None and any(a['mimeType'] == 'image/png' and a['assetKey'] not in planned
                                           for a in proposed['assets']):
                fail('material_scope_changed', '附件 assetKey 不在冻结素材计划中')
            check = self.guard.inspect(frozen['binding'])
            if (any(check[k] != frozen['catalogCheck'][k] for k in ('manifestSha256', 'lessonScopeSha256'))
                    or check['existingArtifacts'] or self._other_artifacts(job)):
                fail('materials_not_prepared', '教材或已有制作成果发生变化，停止附件上传')
            folder = job / 'material-attachments'
            if folder.is_symlink():
                fail('material_integrity_error', '附件归档不能是符号链接')
            folder.mkdir(mode=0o700, exist_ok=True)
            immutable_write(folder / 'manifest.json', json_bytes(proposed))
            for asset in proposed['assets']:
                immutable_write(folder / asset['file'], course_bytes(Path(asset['sourcePath'])))
                if sha(course_bytes(folder / asset['file'])) != asset['sha256']:
                    fail('material_source_changed', '复制时附件来源改变，停止上传')
            owner_path = folder / 'owner.json'
            client = self.client_factory(self.origin, job / 'owner.cookies')
            if owner_path.exists():
                owner = material_json(owner_path)
                if (owner.get('manifestSha256') != proposed['sha256']
                        or owner.get('ownerFingerprint') != client.owner_fingerprint()):
                    fail('material_owner_changed', '附件原 owner 不匹配，禁止继续')
            if self._recover_before_dispatch(job, client, frozen, dispatch_frozen, state, draft=draft):
                fail('materials_existing_session', '已存在同请求会话，不能另绑定或派发')
            self._require_scene_contract_runtime(client, frozen)
            if not owner_path.exists():
                owner = {'manifestSha256': proposed['sha256'], 'ownerFingerprint': client.owner_fingerprint()}
                immutable_write(owner_path, json_bytes(owner))
            state.update(materialsStatus='uploading', materialCount=len(proposed['assets']),
                         message='首轮附件已冻结；成功回执复用，未知上传不重发')
            self._save_state(job, state)
            for asset in proposed['assets']:
                intent = self._upload_intent(proposed, owner, asset)
                intent_path = folder / (asset['assetKey'] + '-intent.json')
                receipt_path = folder / (asset['assetKey'] + '-receipt.json')
                if course_exists(receipt_path):
                    receipt = material_json(receipt_path)
                    if (material_json(intent_path) != intent or receipt.get('intentSha256') != digest(intent)
                            or not self._valid_upload(receipt.get('response'), asset, intent['requestId'])):
                        fail('material_integrity_error', '已有附件回执不一致，禁止重传')
                    continue
                if course_exists(intent_path):
                    state.update(materialsStatus='upload_unknown', message='存在无回执的上传意图，禁止重复上传或派发')
                    self._save_state(job, state)
                    fail('material_upload_unknown', '素材上传结果未知；服务端暂无 owner 素材摘要查询，保留意图，禁止重传')
                raw = course_bytes(folder / asset['file'])
                if len(raw) != asset['bytes'] or sha(raw) != asset['sha256']:
                    fail('material_source_changed', '上传前冻结附件字节已改变，停止上传')
                immutable_write(intent_path, json_bytes(intent))
                try:
                    response = client.upload_material(raw, asset['originalName'],
                                                      intent['requestId'], asset['mimeType'])
                    if not self._valid_upload(response, asset, intent['requestId']):
                        fail('material_upload_response_unknown', '素材上传回执无法核验，禁止重传')
                    immutable_write(receipt_path, json_bytes({'intentSha256': digest(intent), 'response': response}))
                except (WorkbenchError, OSError):
                    state.update(materialsStatus='upload_unknown', message='上传或回执写入未确认，保留意图，禁止重发')
                    self._save_state(job, state)
                    raise
            receipts = {a['assetKey']: material_json(folder / (a['assetKey'] + '-receipt.json')) for a in proposed['assets']}
            payload['materialIds'] = [receipts[a['assetKey']]['response']['material']['materialId'] for a in proposed['assets']]
            ready = {'schemaVersion': 'mira.operator.material-dispatch.v1', 'manifestSha256': proposed['sha256'],
                     'ownerFingerprint': owner['ownerFingerprint'],
                     'uploadReceiptSha256': {k: digest(v) for k, v in receipts.items()},
                     'payload': payload, 'payloadSha256': digest(payload)}
            immutable_write(folder / 'ready.json', json_bytes(ready))
            self._material_payload(job, frozen, draft)
            state.update(materialsStatus='ready', materialCount=len(proposed['assets']),
                         message='首轮附件已冻结和上传；尚未派发，start 将一次绑定全部素材')
            self._save_state(job, state)
            return self._summary(job, frozen, state)

    @staticmethod
    def _verify_session_materials(client, session_id, frozen):
        expected = frozen.get('materialTitles')
        if expected is None:
            return
        # The current list also contains later extraction derivatives and uploads.
        # Only the durable opening user_message proves the original create payload.
        opening = next((event.get('data') for event in client.stage_events(session_id)
                        if isinstance(event, dict) and event.get('type') == 'user_message'), None)
        if (not isinstance(opening, dict) or not isinstance(opening.get('text'), str)
                or sha(opening['text'].encode()) != frozen['requestSha256']
                or opening.get('materials') != frozen['materialBindings']
                or opening.get('courseRefs') or opening.get('elementRefs')):
            fail('session_materials_mismatch', '已有会话的首条用户输入或完整附件不匹配；禁止复用或另建')
        records = client.session_materials(session_id)
        actual = {item.get('materialId'): item.get('title') for item in records if isinstance(item, dict)}
        if any(actual.get(key) != title for key, title in expected.items()):
            fail('session_materials_mismatch', '已有会话的首轮素材不匹配；保留派发栅栏，禁止另建')

    @staticmethod
    def _match(session, frozen):
        return (isinstance(session, dict) and isinstance(session.get('prompt'), str)
                and sha(session['prompt'].encode()) == frozen['requestSha256']
                and session.get('skillId') == frozen['skillIds'][0] and identifier(session.get('id')))

    @staticmethod
    def _save_state(job, state):
        state['updatedAt'] = timestamp()
        write_json(job / 'state.json', state)

    def _recover(self, client, frozen, state, *, sessions=None):
        if state.get('sessionId'):
            session = client.session(state['sessionId'])
            if not self._match(session, frozen) or session['id'] != state['sessionId']:
                fail('session_identity_mismatch', '原会话与完整请求摘要或技能不一致，停止恢复')
            self._verify_session_materials(client, session['id'], frozen)
            return session
        matches = [s for s in (client.sessions() if sessions is None else sessions) if self._match(s, frozen)]
        if len(matches) > 1:
            fail('session_match_ambiguous', '同一身份存在多个完整请求匹配；须人工核对会话')
        if matches:
            self._verify_session_materials(client, matches[0]['id'], frozen)
        return matches[0] if matches else None

    def _recover_before_dispatch(self, job, client, frozen, dispatch_frozen, state, *, draft):
        """A new policy cannot turn a known original-prompt session into a new lesson."""
        sessions = client.sessions()
        current = self._recover(client, dispatch_frozen, {}, sessions=sessions)
        if current is not None or 'interactionPolicy' not in frozen:
            return current
        historical = [frozen]
        if 'sceneContract' in frozen:
            v2_prompt = interaction_policy_prompt(frozen['interactionPolicy']) + draft['request']
            historical.append({**frozen, 'requestSha256': sha(v2_prompt.encode())})
        legacy = [(session, identity) for session in sessions
                  for identity in historical if self._match(session, identity)]
        if legacy:
            message = '已有完整原请求的旧规则会话；须核查复用，不能因新增互动规则另行生成'
            state.update(status='reuse_review_required', error='legacy_session_requires_review', message=message,
                         existingArtifacts=[{'kind': 'legacy_session', 'sessionId': session['id'],
                                             'requestSha256': identity['requestSha256'], 'status': 'review_for_reuse'}
                                            for session, identity in legacy])
            self._save_state(job, state)
            fail('legacy_session_requires_review', message)
        return None

    def _poll(self, job, client, frozen, state):
        session = self._recover(client, frozen, state)
        if session is None:
            state.update(status='dispatch_unknown', message='未找到完整请求匹配，保留派发栅栏；不会重新 POST')
            return
        state.update(sessionId=session['id'], sessionStatus=session.get('status'), status='session_found')
        self._save_state(job, state)  # Keep recovered identity even if event/stage reads fail.
        events = client.stage_events(session['id'])
        candidates = {event.get('data', {}).get('stageId'): 'session_stage_created' for event in events
                      if event.get('type') == 'library_changed' and event.get('data', {}).get('change') == 'stage_created'}
        if not candidates and session.get('stageId'):
            candidates[session['stageId']] = 'session_stage_id'
        stages = []
        for stage_id, provenance in candidates.items():
            if not identifier(stage_id):
                continue
            try:
                document = client.stage(stage_id)
            except WorkbenchError as exc:
                if exc.http_status == 404:
                    continue
                raise
            if (not isinstance(document, dict) or not isinstance(document.get('stage'), dict)
                    or document['stage'].get('id') != stage_id or not isinstance(document.get('scenes'), list)):
                fail('stage_invalid', '已保存 stage 响应不匹配，未标记可复用')
            if not document['scenes']:
                continue  # A session's empty placeholder is not an authored lesson.
            path = job / ('saved-' + stage_id + '.json')
            if course_exists(path):
                # Capture the CAS version before a running session advances.
                # Published/terminal snapshots are protected by the writer.
                if json.loads(course_text(path)) != document:
                    write_json(path, document)
            else:
                write_json(path, document)
            stages.append({'stageId': stage_id, 'sceneCount': len(document['scenes']), 'sha256': digest(document),
                           'path': str(path), 'provenance': provenance, 'url': self.origin + '/classroom/' + stage_id})
        state['savedStages'] = stages
        state['status'] = ('saved_stage_available' if stages and session.get('status') == 'succeeded'
                           else 'session_' + str(session.get('status', 'unknown')))
        state['message'] = '仅记录已保存成果；尚未导出、逐页验收、配音或发布'

    def run(self, job_path, *, start=False):
        with self._locked(job_path) as job:
            frozen, draft, state = self._load(job)
            marker_path = job / 'dispatch.json'
            if state['status'] == 'reuse_review_required' and not course_exists(marker_path):
                return self._summary(job, frozen, state)
            if not start and not course_exists(marker_path) and not state.get('sessionId'):
                return self._summary(job, frozen, state)
            payload, dispatch_frozen = self._material_payload(job, frozen, draft)
            client = self.client_factory(self.origin, job / 'owner.cookies')
            try:
                state.pop('error', None)
                state.pop('httpStatus', None)
                if (dispatch_frozen.get('materialsOwnerFingerprint') is not None
                        and dispatch_frozen['materialsOwnerFingerprint'] != client.owner_fingerprint()):
                    fail('material_owner_changed', '附件原 owner 不匹配，禁止派发或恢复')
                if course_exists(marker_path):
                    marker = json.loads(course_text(marker_path))
                    if (marker.get('requestSha256') != dispatch_frozen['requestSha256']
                            or marker.get('ownerFingerprint') != client.owner_fingerprint()
                            or marker.get('payloadSha256') != dispatch_frozen['payloadSha256']
                            or marker.get('materialsSha256') != dispatch_frozen.get('materialsSha256')):
                        fail('dispatch_identity_mismatch', '派发记录或原 owner 身份不一致，禁止再次 POST')
                    self._poll(job, client, dispatch_frozen, state)
                elif state.get('sessionId'):
                    self._poll(job, client, dispatch_frozen, state)
                elif start:
                    self._widget_successor_receipt(job, live=True)
                    validate_draft(draft)  # Recheck teacher before the first POST, never rewrite it.
                    if frozen['schemaVersion'] == 'mira.operator.workbench-authoring.v3':
                        validate_native_widget_types(draft)
                    check = self.guard.inspect(frozen['binding'])
                    artifacts = check['existingArtifacts'] + self._other_artifacts(job)
                    if check['manifestSha256'] != frozen['catalogCheck']['manifestSha256']:
                        fail('catalog_changed', '冻结后教材内容改变，禁止派发')
                    if artifacts:
                        state.update(status='reuse_review_required', existingArtifacts=artifacts)
                    else:
                        # GET establishes the private owner before any dispatch.
                        existing = self._recover_before_dispatch(job, client, frozen, dispatch_frozen, state, draft=draft)
                        if not existing:
                            self._require_scene_contract_runtime(client, frozen)
                        owner = client.owner_fingerprint()
                        marker = {'createdAt': timestamp(), 'requestSha256': dispatch_frozen['requestSha256'],
                                  'payloadSha256': dispatch_frozen['payloadSha256'], 'ownerFingerprint': owner,
                                  'action': 'reuse_existing_session' if existing else 'single_post_intent'}
                        if dispatch_frozen.get('materialsSha256') is not None:
                            marker['materialsSha256'] = dispatch_frozen['materialsSha256']
                        write_json(marker_path, marker)
                        state.update(status='dispatch_unknown')
                        self._save_state(job, state)
                        if existing:
                            state['sessionId'] = existing['id']
                            self._poll(job, client, dispatch_frozen, state)
                        else:
                            session = client.create_session(payload)
                            if not self._match(session, dispatch_frozen):
                                fail('dispatch_response_unknown', '派发响应无法完整匹配，请使用 status 只读恢复')
                            state.update(sessionId=session['id'], sessionStatus=session.get('status'),
                                         status='session_' + str(session.get('status', 'unknown')),
                                         message='会话已派发；后续使用 status 查询，不再次生成')
                            self._save_state(job, state)
                            self._verify_session_materials(client, session['id'], dispatch_frozen)
            except WorkbenchError as exc:
                state.update(error=exc.code, message=str(exc))
                if exc.http_status is not None:
                    state['httpStatus'] = exc.http_status
                if course_exists(marker_path) and not state.get('sessionId'):
                    state['status'] = 'dispatch_unknown'
            self._save_state(job, state)
            return self._summary(job, frozen, state)
