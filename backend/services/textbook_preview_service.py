"""Operator-only preview generation with a durable, single-dispatch reservation.

The native preview API has no idempotency key. Commit the claim before POST;
timeouts/crashes therefore stop for reconciliation instead of creating another
paid job. Polling and opening a saved classroom never POST a new generation.
"""
from content.textbook_catalog import canonical, digest
from copy import deepcopy
from content.textbook_preview import preview_checks, preview_input
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError


class TextbookPreviewService:
    def __init__(self, repository, runtime):
        self.repository = repository
        self.runtime = runtime

    def get(self, key):
        with self.repository.transaction() as conn:
            row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=?", (key,)).fetchone()
        if row is None:
            raise ApiError("textbook_preview_not_found", "没有找到课程预览", 404)
        if row["runtime_origin"] != self.runtime.base_url:
            raise ApiError("textbook_preview_runtime_changed", "预览所属的 OpenMAIC 地址已变化，请核对原任务", 409)
        return row

    def prepare(self, edition, revision, node):
        with self.repository.transaction() as conn:
            source = self.repository.get_revision(conn, edition, revision)
            if source is None:
                raise ApiError("textbook_revision_not_found", "请先导入已核对的教材修订", 404)
            manifest = self.repository.manifest(source)
            if digest(manifest) != source["manifest_sha256"]:
                raise ApiError("textbook_integrity_error", "教材资料摘要不一致，请先核对", 409)
            frozen = preview_input(manifest, node)
            now = now_ms()
            conn.execute("INSERT INTO learning_textbook_course_previews "
                         "(preview_key,edition_id,revision_id,node_id,input_json,runtime_origin,status,created_at,updated_at) "
                         "VALUES (?,?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE preview_key=preview_key",
                         (frozen["previewKey"], edition, revision, node, canonical(frozen), self.runtime.base_url, "queued", now, now))
            row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE", (frozen["previewKey"],)).fetchone()
            if (self.repository.parse(row["input_json"]) != frozen or row["runtime_origin"] != self.runtime.base_url):
                raise ApiError("textbook_preview_conflict", "同一预览任务存在输入或运行地址冲突", 409)
        return self.summary(row)

    def start(self, key):
        row = self.get(key)
        frozen = self.repository.parse(row["input_json"])
        with self.repository.transaction() as conn:
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
            checks = preview_checks(classroom, frozen["previewPrompt"]["expectedSceneCount"], frozen.get("originalMedia"))
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
