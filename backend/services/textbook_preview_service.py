"""Operator-only preview generation with a durable, single-dispatch reservation.

The native preview API has no idempotency key. Commit the claim before POST;
timeouts/crashes therefore stop for reconciliation instead of creating another
paid job. Polling and opening a saved classroom never POST a new generation.
"""
from content.textbook_catalog import canonical, digest
from copy import deepcopy
from pathlib import Path
from content.textbook_preview import (THREE_MODULE_PATH, cue_speech, operator_media, operator_preview_input,
    preview_checks, preview_input, self_contained_classroom, unique_speech_ids)
from content.textbook_authoring_candidate import DEFAULT_AUTHORING_ROOT, validate_authoring_candidate
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.course_reuse_resolver import CourseReuseResolver


class TextbookPreviewService:
    def __init__(self, repository, runtime, *, authoring_output_root=DEFAULT_AUTHORING_ROOT):
        self.authoring_output_root = Path(authoring_output_root)
        self.repository = repository
        self.runtime = runtime
        self.reuse = CourseReuseResolver(repository)

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
                         "VALUES (?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE preview_key=preview_key",
                         (frozen["previewKey"], edition, revision, node, canonical(frozen), self.runtime.base_url, "queued", now, now))
            row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE", (frozen["previewKey"],)).fetchone()
            if self.repository.parse(row["input_json"]) != frozen or row["runtime_origin"] != self.runtime.base_url:
                raise ApiError("textbook_preview_conflict", "同一预览任务存在输入或运行地址冲突", 409)
            self.reuse.repository.bind_preview(conn, resolved['slot'], row['preview_key'], now)
        return self.summary(row)

    def adopt(self, edition, revision, node, classroom_id, classroom_directory, authoring, *,
              teaching_revision=None, regeneration=None):
        """Reserve a lesson for an operator-authored saved classroom; never dispatches.

        The classroom still needs formal narration, an audio audit and a review
        before it can be published. Its Agent session and saved classroom stand
        in for the job, so a reworked export of one session is a separate job.
        """
        classroom = self.runtime.get_classroom(classroom_id)
        if classroom.get("id") != classroom_id or classroom.get("stage", {}).get("id") != classroom_id:
            raise OpenMaicFullRuntimeError("preview_classroom_mismatch", "预览结果课堂编号不一致")
        if any(q.get("questionAudioUrl") for s in classroom.get("scenes", []) if s.get("type") == "quiz"
               for q in s.get("content", {}).get("questions", [])):
            raise ApiError("textbook_preview_adoption_rejected", "题目不能带入未经审核的读题音频", 409)
        # In-class checks are graded one page at a time and add up to one
        # lesson result, so a question id may appear only once per lesson.
        quizzes = [s for s in classroom.get("scenes", []) if s.get("type") == "quiz"]
        question_ids = [q.get("id") for s in quizzes for q in s.get("content", {}).get("questions", [])]
        if not 1 <= len(quizzes) <= 4 or len(set(question_ids)) != len(question_ids) or not all(
                s.get("content", {}).get("questions") for s in quizzes):
            raise ApiError("textbook_preview_adoption_rejected", "发布课件要有一到四个随堂小测页，每页有题，且全课题号不能重复", 409)
        # Validate v3 evidence before normalization can write to the native
        # classroom, and before reuse.resolve can reserve a database slot.
        with self.repository.transaction() as conn:
            adoption_manifest = self._manifest(conn, edition, revision)
        candidate = validate_authoring_candidate(classroom, classroom_directory, authoring,
            adoption_manifest, node, output_root=self.authoring_output_root,
            runtime_origin=self.runtime.base_url)
        contained = unique_speech_ids(self_contained_classroom(
            classroom, lambda: (Path(classroom_directory).resolve().parents[1] / THREE_MODULE_PATH).read_bytes()))
        if contained != classroom:
            if candidate is not None:
                raise ApiError("textbook_preview_candidate_revision_required",
                               "v3 候选需要规范化修订；不能静默改变已核对的原生场景", 409)
            self.runtime.save_preview_classroom(contained)
            classroom = self.runtime.get_classroom(classroom_id)
            if classroom.get("stage") != contained["stage"] or classroom.get("scenes") != contained["scenes"]:
                raise ApiError("textbook_preview_snapshot_conflict", "自包含处理后的课件保存不一致", 409)
        for scene in classroom.get("scenes", []):
            if scene.get("type") == "interactive":
                cue_speech(scene)
        media = operator_media(classroom, classroom_directory,
                               authoring.get("imageProvenance") if isinstance(authoring, dict) else None)
        with self.repository.transaction() as conn:
            manifest = self._manifest(conn, edition, revision)
            if digest(manifest) != digest(adoption_manifest):
                raise ApiError("textbook_preview_candidate_invalid", "核对期间教材目录发生变化，请重新核对", 409)
            resolved = self.reuse.resolve(conn, manifest, node, teaching_revision=teaching_revision,
                                         regeneration=regeneration)
            if resolved['source'] != 'new':
                return self._resolved_summary(resolved)
            frozen = operator_preview_input(manifest, node, classroom, media, authoring,
                                            teaching_revision=resolved['slot']['teaching_revision'],
                                            authoring_candidate=candidate)
            prompt = frozen["previewPrompt"]
            checks = preview_checks(classroom, prompt["expectedSceneCount"], media, prompt["expectedQuestionCount"],
                                    grade_code=frozen.get('gradeCode'))
            # Workbench speech is re-recorded by the formal narration step.
            blocking = [issue for issue in checks["issues"] if issue != "speech_audio_missing"]
            if blocking:
                raise ApiError("textbook_preview_adoption_rejected", "课件结构或插画检查未通过：" + "、".join(blocking), 409)
            now = now_ms()
            runtime_job_id = self._operator_runtime_job_id(
                authoring, classroom_id, resolved['slot']['teaching_revision'])
            conn.execute("INSERT INTO learning_textbook_course_previews "
                         "(preview_key,edition_id,revision_id,node_id,input_json,runtime_origin,status,runtime_job_id,"
                         "classroom_id,classroom_sha256,classroom_json,result_json,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE preview_key=preview_key",
                         (frozen["previewKey"], edition, revision, node, canonical(frozen), self.runtime.base_url,
                          "review_required", runtime_job_id, classroom_id, digest(classroom),
                          canonical(classroom), canonical(checks), now, now))
            row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE", (frozen["previewKey"],)).fetchone()
            if (row is None or self.repository.parse(row["input_json"]) != frozen
                    or row["runtime_origin"] != self.runtime.base_url or row["classroom_id"] != classroom_id):
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
