"""Operator-only preview generation with a durable, single-dispatch reservation.

The native preview API has no idempotency key. Commit the claim before POST;
timeouts/crashes therefore stop for reconciliation instead of creating another
paid job. Polling and opening a saved classroom never POST a new generation.
"""
from content.textbook_catalog import canonical, digest, identifier
from copy import deepcopy
from pathlib import Path
from content.textbook_preview import (THREE_MODULE_PATH, cue_speech, operator_media, operator_preview_input,
    preview_checks, preview_input, self_contained_classroom, unique_speech_ids)
from content.textbook_authoring_candidate import (CANDIDATE_FILE, DEFAULT_AUTHORING_ROOT, SHA,
    _find_job, _read_json, _safe_child, _saved_stages, validate_authoring_candidate)
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from integrations.openmaic_workbench_client import OpenMaicWorkbenchClient, WorkbenchError
from services.course_file_store import course_exists
from services.course_reuse_resolver import CourseReuseResolver


class TextbookPreviewService:
    def __init__(self, repository, runtime, *, authoring_output_root=DEFAULT_AUTHORING_ROOT,
                 workbench_client_factory=OpenMaicWorkbenchClient):
        self.authoring_output_root = Path(authoring_output_root)
        self.repository = repository
        self.runtime = runtime
        self.workbench_client_factory = workbench_client_factory
        self.reuse = CourseReuseResolver(repository)

    def _native_revision_source(self, classroom, classroom_directory, authoring, manifest, node, candidate):
        """Recheck the exact owner, opening request and entire saved revision ancestry."""
        from content.textbook_native_revision_adoption import verify_native_revision_chain, verify_native_stage_quiescent
        from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring

        directory = Path(classroom_directory).resolve()
        stage, session = authoring['stageId'], authoring['sessionId']
        found = _find_job(self.authoring_output_root, manifest['editionId'], manifest['revisionId'],
                          node, session, stage, True)
        if found is None:
            raise ApiError('textbook_preview_candidate_invalid', '修订缺少原作者任务', 409)
        job, _, _ = found
        service = TextbookWorkbenchAuthoring(None, self.authoring_output_root,
                                             origin=self.runtime.base_url,
                                             client_factory=self.workbench_client_factory)
        frozen, draft, state = service._load(job)
        _, dispatch_frozen = service._material_payload(job, frozen, draft)
        dispatch = _read_json(job / 'dispatch.json')
        client = self.workbench_client_factory(frozen['origin'], job / 'owner.cookies')
        owner = client.owner_fingerprint()
        if (dispatch.get('ownerFingerprint') != owner
                or dispatch.get('requestSha256') != dispatch_frozen['requestSha256']
                or dispatch.get('payloadSha256') != dispatch_frozen['payloadSha256']
                or dispatch.get('materialsSha256') != dispatch_frozen.get('materialsSha256')
                or dispatch_frozen.get('materialsOwnerFingerprint', owner) != owner
                or state.get('sessionId') != session):
            raise ApiError('textbook_preview_candidate_invalid', '修订作者身份或原派发记录不一致', 409)
        live = client.session(session)
        if (not service._match(live, dispatch_frozen) or live.get('id') != session
                or live.get('status') != 'succeeded' or live.get('lease') is not None):
            raise ApiError('textbook_preview_candidate_invalid', '原作者会话与冻结请求或课堂不一致', 409)
        service._verify_session_materials(client, session, dispatch_frozen)
        document = client.stage(stage)
        try:
            verify_native_stage_quiescent(session, stage, owner)
            return verify_native_revision_chain(document, classroom, directory, job,
                                                candidate['completeSceneReviewFollowup'], owner)
        except (ValueError, KeyError, TypeError, OSError):
            raise ApiError('textbook_preview_candidate_invalid', '原生课堂修订链或双来源证据不一致', 409) from None

    def _reuse_native_revision(self, manifest, node, authoring, candidate, proof, teaching_revision,
                               official_followup=None):
        """Reuse an exact recorded preview, including one already narrated."""
        from content.textbook_native_revision_adoption import (normalized_preview_core,
                                                               validate_native_source_proof)
        runtime_job_id = self._operator_runtime_job_id(authoring, authoring['stageId'], teaching_revision)
        with self.repository.transaction() as conn:
            rows = conn.execute('SELECT * FROM learning_textbook_course_previews '
                                'WHERE runtime_origin=? AND runtime_job_id=?',
                                (self.runtime.base_url, runtime_job_id)).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise ApiError('textbook_preview_conflict', '原生作者会话对应多个预览', 409)
        row = rows[0]
        frozen = self.repository.parse(row['input_json'])
        prior_proof = frozen.get('nativeRevisionSource')
        try:
            validate_native_source_proof(prior_proof, candidate['completeSceneReviewFollowup'])
            if ({k: v for k, v in prior_proof.items() if k not in ('cloneCoreSha256', 'previewSourceSha256')} != proof
                    or frozen.get('authoring') != authoring or frozen.get('authoringCandidate') != candidate
                    or frozen.get('requirement') != authoring.get('request')
                    or frozen.get('officialReviewFollowup') != official_followup
                    or frozen.get('authoringSourceSha256') != proof['authoringSourceSha256']
                    or frozen.get('sourceSha256') != prior_proof['previewSourceSha256']
                    or frozen.get('manifestSha256') != digest(manifest) or frozen.get('nodeId') != node
                    or frozen.get('previewKey') != row['preview_key']
                    or digest({k: v for k, v in frozen.items() if k not in ('previewKey', 'requirement')}) != row['preview_key']
                    or row['classroom_id'] != self._materialized_adoption_id(authoring['stageId'], candidate['sha256'], teaching_revision)):
                raise ValueError('existing preview identity differs')
            current = self.runtime.get_classroom(row['classroom_id'])
            if (digest(current) != row['classroom_sha256']
                    or current != self.repository.parse(row['classroom_json'])
                    or digest(normalized_preview_core(current)) != prior_proof['cloneCoreSha256']):
                raise ValueError('existing preview content differs')
        except (ValueError, TypeError, KeyError):
            raise ApiError('textbook_preview_conflict', '已有预览与本次原生修订不一致', 409) from None
        with self.repository.transaction() as conn:
            resolved = self.reuse.resolve(conn, manifest, node, teaching_revision=teaching_revision,
                                          preferred_key=row['preview_key'])
            if 'publication' in resolved:
                published = self.repository.parse(resolved['publication']['input_json'])
                if published.get('previewKey') != row['preview_key']:
                    raise ApiError('textbook_preview_conflict', '已发布版本与原生预览不一致', 409)
            elif resolved.get('preview', {}).get('preview_key') != row['preview_key']:
                raise ApiError('textbook_preview_conflict', '复用预览与原生修订不一致', 409)
            elif (resolved['preview']['classroom_sha256'] != row['classroom_sha256']
                  or resolved['preview']['input_json'] != row['input_json']):
                raise ApiError('textbook_preview_conflict', '复用期间预览已改变，请重新核对', 409)
            return self._resolved_summary(resolved)

    def _operator_adoption_classroom(self, classroom_id, classroom_directory, authoring,
                                     manifest, node):
        """Read a protected author candidate from its owner-scoped stage API.

        ``/api/classroom`` remains the public/published reader. A v3/v4 native
        candidate, however, belongs to the private workbench owner that created
        it and its authoritative mutable document lives at ``/api/stages/:id``.
        Genuine legacy adoptions keep their existing classroom read path.
        """
        directory = Path(classroom_directory).resolve()
        ledger = _safe_child(directory, directory / classroom_id / CANDIDATE_FILE)
        session_id = authoring.get('sessionId') if isinstance(authoring, dict) else None
        found = _find_job(
            self.authoring_output_root, manifest['editionId'], manifest['revisionId'], node,
            session_id, classroom_id, course_exists(ledger) or ledger.is_symlink())
        if found is None:
            return self.runtime.get_classroom(classroom_id), None

        job, frozen, state = found
        if (not isinstance(authoring, dict) or authoring.get('stageId') != classroom_id
                or frozen.get('origin') != self.runtime.base_url
                or classroom_id not in _saved_stages(state)):
            raise ApiError('textbook_preview_candidate_invalid',
                           '原生课堂、作者会话和真实保存记录不一致', 409)

        root = self.authoring_output_root.resolve()
        cookie_path = _safe_child(root, job / 'owner.cookies')
        if cookie_path.is_symlink() or not cookie_path.is_file():
            raise ApiError('textbook_preview_candidate_invalid',
                           '缺少原作者会话的私有身份；不能用新身份读取候选课堂', 409)
        dispatch = _read_json(job / 'dispatch.json')
        try:
            client = self.workbench_client_factory(frozen['origin'], cookie_path)
            dispatch_fields = {'createdAt', 'requestSha256', 'payloadSha256',
                               'ownerFingerprint', 'action'}
            if (not dispatch_fields.issubset(dispatch)
                    or set(dispatch) - dispatch_fields - {'materialsSha256'}
                    or not isinstance(dispatch.get('createdAt'), str)
                    or not dispatch['createdAt'].strip()
                    or dispatch.get('action') not in {'single_post_intent', 'reuse_existing_session'}
                    or any(not isinstance(dispatch.get(key), str)
                           or not SHA.fullmatch(dispatch[key]) for key in
                           ('requestSha256', 'payloadSha256', 'ownerFingerprint'))
                    or ('materialsSha256' in dispatch
                        and (not isinstance(dispatch['materialsSha256'], str)
                             or not SHA.fullmatch(dispatch['materialsSha256'])))
                    or dispatch['ownerFingerprint'] != client.owner_fingerprint()):
                raise ApiError('textbook_preview_candidate_invalid',
                               '原作者身份或派发记录无效', 409)
            document = client.stage(classroom_id)
        except ApiError:
            raise
        except WorkbenchError as error:
            raise OpenMaicFullRuntimeError(
                'preview_authoring_stage_unavailable',
                '无法以原作者身份读取权威候选课堂；已停止接收且未改动发布课堂',
                status_code=error.http_status or 502) from None
        if (not isinstance(document, dict)
                or document.get('id') not in (None, classroom_id)
                or not isinstance(document.get('stage'), dict)
                or document['stage'].get('id') != classroom_id
                or not isinstance(document.get('scenes'), list)
                or not isinstance(document.get('outline'), dict)
                or document['outline'].get('producerRef') != session_id):
            raise ApiError('textbook_preview_candidate_invalid',
                           '权威候选课堂与原作者会话或课堂编号不一致', 409)
        # The stage endpoint also returns editor-only outline/DSL metadata. The
        # durable classroom contract is exactly id + stage + scenes, matching
        # what save_preview_classroom persists and later readers consume.
        frozen_revision = frozen.get('binding', {}).get('teachingRevision')
        if frozen_revision is not None and not identifier(frozen_revision):
            raise ApiError('textbook_preview_candidate_invalid',
                           '冻结任务的教学修订身份无效', 409)
        scene_contract = frozen.get('sceneContract', {}).get('contract', {})
        return ({'id': classroom_id, 'stage': deepcopy(document['stage']),
                 'scenes': deepcopy(document['scenes'])},
                {'teachingRevision': frozen_revision,
                 'jobSchema': frozen.get('schemaVersion'),
                 'pagePlan': deepcopy(scene_contract.get('pagePlan')),
                 'lockedAssessments': deepcopy(scene_contract.get('lockedAssessments'))})

    @staticmethod
    def _validate_adoption_quizzes(classroom, locked_assessments=None):
        """Keep legacy quiz limits unless a protected contract freezes zero.

        A verified v3/v4 authoring candidate already binds every quiz and
        question to its frozen scene contract.  An explicit empty lock list is
        therefore a prohibition on inventing a quiz, not a missing default.
        ``None`` retains the historical adoption rule for legacy classrooms
        that have no protected scene contract.
        """
        quizzes = [scene for scene in classroom.get('scenes', [])
                   if scene.get('type') == 'quiz']
        question_ids = [question.get('id') for scene in quizzes
                        for question in scene.get('content', {}).get('questions', [])]
        if locked_assessments == []:
            if quizzes:
                raise ApiError(
                    'textbook_preview_adoption_rejected',
                    '冻结测评为空；不能为发布流程凭空新增随堂测验', 409)
            return
        if (not 1 <= len(quizzes) <= 4
                or len(set(question_ids)) != len(question_ids)
                or not all(scene.get('content', {}).get('questions') for scene in quizzes)):
            raise ApiError(
                'textbook_preview_adoption_rejected',
                '发布课件要有一到四个随堂小测页，每页有题，且全课题号不能重复', 409)

    @staticmethod
    def _materialized_adoption_id(source_stage_id, candidate_sha256, teaching_revision):
        return 'tbadopt_' + digest({
            'schemaVersion': 'mira.textbook.operator-adoption-materialization.v1',
            'sourceStageId': source_stage_id,
            'candidateSha256': candidate_sha256,
            'teachingRevision': teaching_revision,
        })[:24]

    def _materialize_operator_candidate(self, classroom, candidate, teaching_revision):
        """Create or reuse an immutable preview clone; never edit its source stage."""
        source_stage_id = classroom['id']
        materialized_id = self._materialized_adoption_id(
            source_stage_id, candidate['sha256'], teaching_revision)
        clone = deepcopy(classroom)
        clone['id'] = materialized_id
        clone['stage']['id'] = materialized_id
        for scene in clone['scenes']:
            if scene.get('stageId') != source_stage_id:
                raise ApiError('textbook_preview_candidate_invalid',
                               '候选页不属于原作者课堂，不能建立发布预览', 409)
            scene['stageId'] = materialized_id

        try:
            existing = self.runtime.get_classroom(materialized_id)
        except OpenMaicFullRuntimeError as error:
            if error.status_code != 404:
                raise
            existing = None
        if existing is not None:
            if (existing.get('id') != materialized_id
                    or existing.get('stage') != clone['stage']
                    or existing.get('scenes') != clone['scenes']):
                raise ApiError('textbook_preview_snapshot_conflict',
                               '确定性预览编号已存在不同内容，已拒绝覆盖', 409)
            return existing

        self.runtime.save_preview_classroom(clone)
        materialized = self.runtime.get_classroom(materialized_id)
        if (materialized.get('id') != materialized_id
                or materialized.get('stage') != clone['stage']
                or materialized.get('scenes') != clone['scenes']):
            raise ApiError('textbook_preview_snapshot_conflict',
                           '候选课件克隆落盘后的内容不一致，已停止接收', 409)
        return materialized

    def get(self, key):
        with self.repository.transaction() as conn:
            row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=?", (key,)).fetchone()
        if row is None:
            raise ApiError("textbook_preview_not_found", "没有找到课程预览", 404)
        if row["runtime_origin"] != self.runtime.base_url:
            raise ApiError("textbook_preview_runtime_changed", "预览所属的 OpenMAIC 地址已变化，请核对原任务", 409)
        return row

    def _manifest(self, conn, edition, revision):
        source = self.repository.get_revision(conn, edition, revision)
        if source is None:
            raise ApiError("textbook_revision_not_found", "请先导入已核对的教材修订", 404)
        manifest = self.repository.manifest(source)
        if digest(manifest) != source["manifest_sha256"]:
            raise ApiError("textbook_integrity_error", "教材资料摘要不一致，请先核对", 409)
        return manifest

    def _resolved_summary(self, resolved):
        if 'publication' not in resolved:
            row = resolved['preview']
            if row['runtime_origin'] != self.runtime.base_url:
                raise ApiError('textbook_preview_runtime_changed', '已有课件属于其他运行地址，请核对原任务', 409)
            return self.summary(row)
        build, release = resolved['publication'], resolved['release']
        frozen = self.repository.parse(build['input_json'])
        return {'status': 'published', 'reused': True, 'reuseSource': 'published',
                'contentKey': build['content_key'], 'courseId': build['course_id'],
                'courseVersion': build['course_version'], 'previewKey': frozen.get('previewKey'),
                'classroomId': release['classroomId'], 'classroomSha256': release['classroomSha256'],
                'sourceEditionId': build['edition_id'], 'sourceRevisionId': build['revision_id'],
                'publicationAllowed': False, 'providerDispatched': False}

    @staticmethod
    def _operator_runtime_job_id(authoring, classroom_id, teaching_revision):
        """Keep v1 identities stable while allowing an explicit later revision.

        ``runtime_job_id`` is unique per runtime origin.  A later teaching
        revision may deliberately adopt a repaired snapshot from the same
        terminal Agent session and stage, so its durable identity must include
        that revision without depending on a column-length-sensitive stage
        suffix.
        """
        legacy = f"agent-session:{authoring['sessionId']}:{classroom_id}"
        if teaching_revision == '1':
            return legacy
        return 'operator-adopt:' + digest({
            'schemaVersion': 'mira.operator-adoption-job.v1',
            'sessionId': authoring['sessionId'],
            'stageId': classroom_id,
            'teachingRevision': teaching_revision,
        })

    def prepare(self, edition, revision, node, *, teaching_revision=None, regeneration=None):
        with self.repository.transaction() as conn:
            manifest = self._manifest(conn, edition, revision)
            resolved = self.reuse.resolve(conn, manifest, node, teaching_revision=teaching_revision,
                                         regeneration=regeneration)
            if resolved['source'] != 'new':
                return self._resolved_summary(resolved)
            frozen = preview_input(manifest, node, teaching_revision=resolved['slot']['teaching_revision'])
            now = now_ms()
            conn.execute("INSERT INTO learning_textbook_course_previews "
                         "(preview_key,edition_id,revision_id,node_id,input_json,runtime_origin,status,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                         (frozen["previewKey"], edition, revision, node, canonical(frozen), self.runtime.base_url, "queued", now, now))
            row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE", (frozen["previewKey"],)).fetchone()
            if self.repository.parse(row["input_json"]) != frozen or row["runtime_origin"] != self.runtime.base_url:
                raise ApiError("textbook_preview_conflict", "同一预览任务存在输入或运行地址冲突", 409)
            self.reuse.repository.bind_preview(conn, resolved['slot'], row['preview_key'], now)
        return self.summary(row)

    def adopt(self, edition, revision, node, classroom_id, classroom_directory, authoring, *,
              teaching_revision=None, regeneration=None, official_followup_selection=None):
        """Reserve a lesson for an operator-authored saved classroom; never dispatches.

        The classroom still needs formal narration, an audio audit and a review
        before it can be published. Its Agent session and saved classroom stand
        in for the job, so a reworked export of one session is a separate job.
        """
        with self.repository.transaction() as conn:
            adoption_manifest = self._manifest(conn, edition, revision)
        source_classroom_id = classroom_id
        classroom, protected_source = self._operator_adoption_classroom(
            classroom_id, classroom_directory, authoring, adoption_manifest, node)
        if classroom.get("id") != classroom_id or classroom.get("stage", {}).get("id") != classroom_id:
            raise OpenMaicFullRuntimeError("preview_classroom_mismatch", "预览结果课堂编号不一致")
        if any(q.get("questionAudioUrl") for s in classroom.get("scenes", []) if s.get("type") == "quiz"
               for q in s.get("content", {}).get("questions", [])):
            raise ApiError("textbook_preview_adoption_rejected", "题目不能带入未经审核的读题音频", 409)
        # Validate protected candidate evidence before normalization or
        # materialization can write to the public classroom source, and before
        # reuse.resolve can reserve a database slot.
        candidate = validate_authoring_candidate(classroom, classroom_directory, authoring,
            adoption_manifest, node, output_root=self.authoring_output_root,
            runtime_origin=self.runtime.base_url)
        effective_teaching_revision = teaching_revision
        native_revision_source = None
        verified_official_followup = None
        if candidate is not None:
            if protected_source is None:
                raise ApiError('textbook_preview_candidate_invalid',
                               '候选缺少原作者课堂的私有来源', 409)
            requested_revision = self.reuse._version(teaching_revision)
            frozen_revision = protected_source.get('teachingRevision')
            if (requested_revision is not None and frozen_revision is not None
                    and requested_revision != frozen_revision):
                raise ApiError('textbook_preview_candidate_invalid',
                               '请求的教学修订与原作者冻结任务不一致', 409)
            effective_teaching_revision = requested_revision or frozen_revision or '1'
            if candidate.get('completeSceneReviewFollowup') is not None:
                if protected_source.get('jobSchema') != 'mira.operator.workbench-authoring.v4':
                    raise ApiError('textbook_preview_candidate_revision_required',
                                   '历史候选须继续使用原有完整场景修订流程', 409)
                native_revision_source = self._native_revision_source(
                    classroom, classroom_directory, authoring, adoption_manifest, node, candidate)
                from content.textbook_official_followup import requires_official_followup, validate_followup
                found = _find_job(self.authoring_output_root, edition, revision, node,
                                  authoring['sessionId'], classroom_id, True)
                job, source_frozen, _ = found
                source_draft = _read_json(job / 'draft.json')
                if requires_official_followup(source_draft):
                    selection = official_followup_selection
                    if not isinstance(selection, dict) or set(selection) != {'path', 'expectedSha256', 'operatorAttestation'}:
                        raise ApiError('textbook_preview_official_followup_required',
                                       '视频例外须由操作员核对真实对话并显式选择准确追溯记录', 409)
                    try:
                        verified_official_followup = validate_followup(
                            selection['path'], selection['expectedSha256'], selection['operatorAttestation'],
                            job=job, frozen=source_frozen, draft=source_draft,
                            dispatch=_read_json(job/'dispatch.json'), native_proof=native_revision_source,
                            followup=candidate['completeSceneReviewFollowup'])
                    except (ValueError, KeyError, TypeError, OSError, ApiError):
                        raise ApiError('textbook_preview_official_followup_invalid',
                                       '官方资料例外的原始授权、课次或证据不一致', 409) from None
                elif official_followup_selection is not None:
                    raise ApiError('textbook_preview_official_followup_invalid', '本课不需要该视频例外记录', 409)
        if official_followup_selection is not None and verified_official_followup is None:
            raise ApiError('textbook_preview_official_followup_invalid', '该授权追溯仅适用于已派发的受保护修订候选', 409)
        # In-class checks are graded one page at a time and add up to one
        # lesson result, so a question id may appear only once per lesson.
        # Protected contracts may explicitly freeze an empty assessment list;
        # legacy classrooms continue to require one to four quiz pages.
        locked_assessments = (protected_source.get('lockedAssessments')
                              if candidate is not None else None)
        if candidate is not None and not isinstance(locked_assessments, list):
            raise ApiError('textbook_preview_candidate_invalid',
                           '冻结测评合同缺失或无效', 409)
        if native_revision_source is not None and locked_assessments:
            raise ApiError('textbook_preview_candidate_revision_required',
                           '带题目音频绑定的修订候选需要独立双来源校验', 409)
        if native_revision_source is not None:
            existing = self._reuse_native_revision(adoption_manifest, node, authoring, candidate,
                                                    native_revision_source, effective_teaching_revision,
                                                    verified_official_followup)
            if existing is not None:
                return existing
        self._validate_adoption_quizzes(classroom, locked_assessments)
        contained = unique_speech_ids(self_contained_classroom(
            classroom, lambda: (Path(classroom_directory).resolve().parents[1] / THREE_MODULE_PATH).read_bytes()))
        if contained != classroom:
            if candidate is not None:
                raise ApiError("textbook_preview_candidate_revision_required",
                               "受保护候选需要规范化修订；不能静默改变已核对的原生场景", 409)
            self.runtime.save_preview_classroom(contained)
            classroom = self.runtime.get_classroom(classroom_id)
            if classroom.get("stage") != contained["stage"] or classroom.get("scenes") != contained["scenes"]:
                raise ApiError("textbook_preview_snapshot_conflict", "自包含处理后的课件保存不一致", 409)
        elif candidate is not None:
            classroom = self._materialize_operator_candidate(
                contained, candidate, effective_teaching_revision)
            if native_revision_source is not None:
                from services.textbook_preview_audio import core_content
                native_revision_source = {**native_revision_source,
                                          'cloneCoreSha256': digest(core_content(classroom)),
                                          'previewSourceSha256': digest(classroom)}
        for scene in classroom.get("scenes", []):
            if scene.get("type") == "interactive":
                cue_speech(scene)
        media = operator_media(classroom, classroom_directory,
                               authoring.get("imageProvenance") if isinstance(authoring, dict) else None)
        if native_revision_source is not None:
            # The clone is immutable, but the source may have been edited while
            # it was being materialized. Recheck before reserving a DB preview.
            fresh, _ = self._operator_adoption_classroom(
                source_classroom_id, classroom_directory, authoring, adoption_manifest, node)
            fresh_candidate = validate_authoring_candidate(
                fresh, classroom_directory, authoring, adoption_manifest, node,
                output_root=self.authoring_output_root, runtime_origin=self.runtime.base_url)
            if fresh_candidate != candidate:
                raise ApiError('textbook_preview_candidate_invalid', '修订接收期间原生课堂已改变', 409)
            fresh_proof = self._native_revision_source(
                fresh, classroom_directory, authoring, adoption_manifest, node, fresh_candidate)
            if ({k: v for k, v in native_revision_source.items()
                     if k not in ('cloneCoreSha256', 'previewSourceSha256')} != fresh_proof):
                raise ApiError('textbook_preview_candidate_invalid', '修订接收期间原生课堂已改变', 409)
            if verified_official_followup is not None:
                from content.textbook_official_followup import validate_followup
                try:
                    fresh_official = validate_followup(
                        official_followup_selection['path'], official_followup_selection['expectedSha256'],
                        official_followup_selection['operatorAttestation'], job=job, frozen=source_frozen,
                        draft=_read_json(job / 'draft.json'), dispatch=_read_json(job / 'dispatch.json'),
                        native_proof=fresh_proof, followup=fresh_candidate['completeSceneReviewFollowup'])
                    if fresh_official != verified_official_followup:
                        raise ValueError('official follow-up changed')
                except (ValueError, KeyError, TypeError, OSError, ApiError):
                    raise ApiError('textbook_preview_official_followup_invalid',
                                   '接收期间官方资源追溯记录已改变', 409) from None
        with self.repository.transaction() as conn:
            manifest = self._manifest(conn, edition, revision)
            if digest(manifest) != digest(adoption_manifest):
                raise ApiError("textbook_preview_candidate_invalid", "核对期间教材目录发生变化，请重新核对", 409)
            resolved = self.reuse.resolve(conn, manifest, node,
                                         teaching_revision=effective_teaching_revision,
                                         regeneration=regeneration)
            if resolved['source'] != 'new':
                return self._resolved_summary(resolved)
            frozen = operator_preview_input(manifest, node, classroom, media, authoring,
                                            teaching_revision=resolved['slot']['teaching_revision'],
                                            authoring_candidate=candidate,
                                            verified_locked_assessments=locked_assessments,
                                            verified_scene_types=([t for t in ('slide', 'interactive', 'quiz')
                                                if any(p.get('type') == t for p in protected_source['pagePlan'])]
                                                if candidate is not None else None),
                                            native_revision_source=native_revision_source,
                                            official_review_followup=verified_official_followup)
            prompt = frozen["previewPrompt"]
            checks = preview_checks(classroom, prompt["expectedSceneCount"], media, prompt["expectedQuestionCount"],
                                    required_scene_types=prompt.get('requiredSceneTypes'),
                                    grade_code=frozen.get('gradeCode'))
            # Workbench speech is re-recorded by the formal narration step.
            blocking = [issue for issue in checks["issues"] if issue != "speech_audio_missing"]
            if blocking:
                raise ApiError("textbook_preview_adoption_rejected", "课件结构或插画检查未通过：" + "、".join(blocking), 409)
            now = now_ms()
            runtime_job_id = self._operator_runtime_job_id(
                authoring, source_classroom_id, resolved['slot']['teaching_revision'])
            preview_classroom_id = classroom['id']
            conn.execute("INSERT INTO learning_textbook_course_previews "
                         "(preview_key,edition_id,revision_id,node_id,input_json,runtime_origin,status,runtime_job_id,"
                         "classroom_id,classroom_sha256,classroom_json,result_json,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                         (frozen["previewKey"], edition, revision, node, canonical(frozen), self.runtime.base_url,
                          "review_required", runtime_job_id, preview_classroom_id, digest(classroom),
                          canonical(classroom), canonical(checks), now, now))
            row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE", (frozen["previewKey"],)).fetchone()
            if (row is None or self.repository.parse(row["input_json"]) != frozen
                    or row["runtime_origin"] != self.runtime.base_url
                    or row["classroom_id"] != preview_classroom_id):
                raise ApiError("textbook_preview_conflict", "同一预览任务存在输入或运行地址冲突", 409)
            self.reuse.repository.bind_preview(conn, resolved['slot'], row['preview_key'], now)
        return self.summary(row)

    def start(self, key):
        row = self.get(key)
        with self.repository.transaction() as conn:
            manifest = self._manifest(conn, row['edition_id'], row['revision_id'])
            resolved = self.reuse.resolve(conn, manifest, row['node_id'], preferred_key=key)
            if 'publication' in resolved:
                return self._resolved_summary(resolved)
            row = resolved['preview']
            self._resolved_summary(resolved)  # Check runtime before any dispatch.
            key = row['preview_key']
            frozen = self.repository.parse(row['input_json'])
            claimed = conn.execute("UPDATE learning_textbook_course_previews SET status='dispatching',updated_at=? "
                                   "WHERE preview_key=? AND status='queued'", (now_ms(), key)).rowcount == 1
        if not claimed:
            return self.summary(self.get(key))
        try:
            job = self.runtime.start_generation(requirement=frozen["requirement"], **frozen["generationOptions"])
        except Exception:
            # No retry after any uncertain response, including process/network
            # failures. A crashed 'dispatching' reservation also stays blocked.
            with self.repository.transaction() as conn:
                conn.execute("UPDATE learning_textbook_course_previews SET status='dispatch_unknown',updated_at=? WHERE preview_key=?",
                             (now_ms(), key))
            raise ApiError("textbook_preview_dispatch_unknown", "生成请求结果不确定，已停止重发；请核对 OpenMAIC 任务", 503)
        with self.repository.transaction() as conn:
            conn.execute("UPDATE learning_textbook_course_previews SET status='generating',runtime_job_id=?,updated_at=? WHERE preview_key=? AND status='dispatching'",
                         (job.job_id, now_ms(), key))
        return self.poll(key)

    def poll(self, key):
        row = self.get(key)
        if row["status"] != "generating":
            return self.summary(row)
        job = self.runtime.get_generation_job(row["runtime_job_id"])
        result = {"step": job.step, "progress": job.progress, "scenesCount": job.scenes_count}
        status, classroom, checks = "generating", None, None
        if job.status == "failed":
            status = "failed"
            # Provider errors can contain request details. Keep native audit on
            # the runtime and expose only a stable safe diagnostic here.
            result["errorCode"] = "openmaic_preview_generation_failed"
        elif job.status == "succeeded":
            if not job.classroom_id:
                raise OpenMaicFullRuntimeError("preview_classroom_missing", "预览结果缺少课堂编号")
            classroom = self.runtime.get_classroom(job.classroom_id)
            if classroom.get("id") != job.classroom_id or classroom.get("stage", {}).get("id") != job.classroom_id:
                raise OpenMaicFullRuntimeError("preview_classroom_mismatch", "预览结果课堂编号不一致")
            frozen = self.repository.parse(row["input_json"])
            checks = preview_checks(classroom, frozen["previewPrompt"]["expectedSceneCount"], frozen.get("originalMedia"), frozen["previewPrompt"].get("expectedQuestionCount", 6),
                                    required_scene_types=frozen['previewPrompt'].get('requiredSceneTypes'),
                                    grade_code=frozen.get('gradeCode'))
            status = "review_required" if checks["issues"] else "preview_ready"
            result.update(checks)
        with self.repository.transaction() as conn:
            conn.execute("UPDATE learning_textbook_course_previews SET status=?,result_json=?,classroom_id=?,classroom_sha256=?,classroom_json=?,updated_at=? "
                         "WHERE preview_key=? AND status='generating'",
                         (status, canonical(result), job.classroom_id if classroom else None,
                          digest(classroom) if classroom else None, canonical(classroom) if classroom else None, now_ms(), key))
        return self.summary(self.get(key))

    def summary(self, row):
        result = self.repository.parse(row["result_json"]) if row["result_json"] else None
        frozen = (result or {}).get("frozenPreview", {})
        preview_id = frozen.get("classroomId") if frozen.get("sourceSha256") == row["classroom_sha256"] else None
        preview_id = preview_id or row["classroom_id"]
        if result and "audioReceipts" in result:
            result = {**result, "audioReceiptCount": len(result["audioReceipts"])}
            result.pop("audioReceipts")
        return {"previewKey": row["preview_key"], "status": row["status"], "runtimeJobId": row["runtime_job_id"],
                "classroomId": row["classroom_id"], "classroomSha256": row["classroom_sha256"],
                "previewUrl": f"{row['runtime_origin']}/classroom/{preview_id}" if preview_id else None,
                "result": result,
                "publicationAllowed": False}

    def freeze(self, key):
        """Give the reviewed draft an immutable URL, avoiding stale editor caches."""
        row = self.get(key)
        if row["status"] != "preview_ready":
            raise ApiError("textbook_preview_not_ready", "请先完成课件与配音检查", 409)
        result = self.repository.parse(row["result_json"])
        if result.get("frozenPreview", {}).get("sourceSha256") == row["classroom_sha256"]:
            return self.summary(row)
        source = self.runtime.get_classroom(row["classroom_id"])
        if digest(source) != row["classroom_sha256"]:
            raise ApiError("textbook_preview_changed", "课件已改变，请先重新核对", 409)
        frozen = self.repository.parse(row['input_json'])
        prompt = frozen['previewPrompt']
        checks = preview_checks(source, prompt['expectedSceneCount'], frozen.get('originalMedia'),
                                prompt.get('expectedQuestionCount', 6),
                                required_scene_types=prompt.get('requiredSceneTypes'),
                                # Published-child revision registration already
                                # checks its verified changed-page scope.
                                grade_code=None if frozen.get('operatorRevision') else frozen.get('gradeCode'))
        if 'responsive_activity_marker_missing' in checks['issues']:
            raise ApiError('textbook_preview_not_ready', '低年级互动页缺少原生响应式标记，请先修订后预览', 409)
        snapshot_id = "tbprev_" + row["classroom_sha256"][:24]
        # Only identity values change; media URLs continue pointing at the
        # already generated byte assets. Never synthesize or copy audio again.
        def replace_identity(value):
            if isinstance(value, dict):
                return {k: replace_identity(v) for k, v in value.items()}
            if isinstance(value, list):
                return [replace_identity(v) for v in value]
            return snapshot_id if value == row["classroom_id"] else value
        snapshot = replace_identity(deepcopy(source))
        try:
            saved = self.runtime.get_classroom(snapshot_id)
        except OpenMaicFullRuntimeError as exc:
            if exc.status_code != 404:
                raise
            self.runtime.save_preview_classroom(snapshot)
            saved = self.runtime.get_classroom(snapshot_id)
        if saved["stage"] != snapshot["stage"] or saved["scenes"] != snapshot["scenes"]:
            raise ApiError("textbook_preview_snapshot_conflict", "预览快照不一致，已停止覆盖", 409)
        result["frozenPreview"] = {"classroomId": snapshot_id, "sourceSha256": row["classroom_sha256"], "snapshotSha256": digest(saved)}
        with self.repository.transaction() as conn:
            changed = conn.execute("UPDATE learning_textbook_course_previews SET result_json=?,updated_at=? WHERE preview_key=? AND classroom_sha256=? AND status='preview_ready'",
                                   (canonical(result), now_ms(), key, row["classroom_sha256"])).rowcount
            if changed != 1:
                raise ApiError("textbook_preview_changed", "课件已改变，请先重新核对", 409)
        return self.summary(self.get(key))
