"""Resolve shared course artifacts before constructing a new AI request.

Prompt/model/catalog presentation changes do not change a course identity.
Lesson scope changes are rejected until an operator explicitly chooses a new
teaching version. Compatible directory revisions retain the original artifact
binding: this resolver never silently republishes or relabels a classroom.
"""
from content.textbook_catalog import digest, identifier, lesson_by_id
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from repositories.course_reuse_repository import CourseReuseRepository


def stable_course_identity(manifest, node):
    lesson_by_id(manifest, node)
    return {k: manifest[k] for k in ('editionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')} | {
        'schemaVersion': 'mira.shared-course-identity.v1', 'nodeId': node, 'partIndex': 1,
    }


def lesson_scope(manifest, node):
    _, lesson = lesson_by_id(manifest, node)
    # Review status, page numbers and catalog labels are not teaching content.
    brief = {k: v for k, v in lesson['brief'].items() if k != 'status'}
    return digest({'title': lesson['title'], 'knowledgeBrief': brief})


class CourseReuseResolver:
    def __init__(self, textbooks):
        self.textbooks = textbooks
        self.repository = CourseReuseRepository()

    @staticmethod
    def _version(value):
        if value is not None and not identifier(value):
            raise ApiError('course_reuse_version_invalid', '教学版本无效', 400)
        return value

    @staticmethod
    def _regeneration(value):
        if (not isinstance(value, dict) or set(value) != {'reason', 'budgetReference'}
                or any(not isinstance(value[k], str) or not value[k].strip() or len(value[k]) > 1000
                       for k in value)):
            raise ApiError('course_reuse_upgrade_required', '新教学版本需要说明教学差异与预算依据', 409)
        return {k: v.strip() for k, v in value.items()}

    def _same_scope(self, conn, row, scope_hash):
        source = self.textbooks.get_revision(conn, row['edition_id'], row['revision_id'])
        if source is None:
            raise ApiError('course_reuse_source_missing', '已有课件的教材来源缺失，已停止新生成', 409)
        manifest = self.textbooks.manifest(source)
        if digest(manifest) != source['manifest_sha256']:
            raise ApiError('textbook_integrity_error', '已有课件的教材摘要不一致', 409)
        return lesson_scope(manifest, row['node_id']) == scope_hash, manifest

    def resolve(self, conn, manifest, node, *, teaching_revision=None, regeneration=None, preferred_key=None):
        """Returns a publication, a preview, or one reserved empty slot.

        Must run in the same transaction as the eventual preview INSERT / start
        CAS. The imported edition lock is always acquired before reading slots.
        """
        version = self._version(teaching_revision)
        identity = stable_course_identity(manifest, node)
        course_key, scope_hash = digest(identity), lesson_scope(manifest, node)
        self.repository.lock_edition(conn, manifest['editionId'])
        slots = self.repository.slots(conn, course_key)
        previews = self.repository.previews(conn, manifest['editionId'], node)
        publications = self.repository.publications(conn, manifest['editionId'], node)
        # An old hash URL must resolve to its existing stable version, not open
        # a competing paid job. A new-version URL cannot fall back to old output.
        if preferred_key:
            bound = next((s for s in slots if s['preview_key'] == preferred_key), None)
            if bound:
                version = bound['teaching_revision']
            else:
                preferred = next((p for p in previews if p['preview_key'] == preferred_key), None)
                frozen = self.textbooks.parse(preferred['input_json']) if preferred else {}
                version = frozen.get('teachingRevision')
        chosen_slot = next((s for s in slots if version is None or s['teaching_revision'] == version), None)
        if chosen_slot and chosen_slot['lesson_scope_sha256'] != scope_hash:
            raise ApiError('course_reuse_scope_changed', '本课教学范围已改变，请显式建立新教学版本', 409)

        for build in publications:
            if version is not None and build['teaching_revision'] != version:
                continue
            compatible, source_manifest = self._same_scope(conn, build, scope_hash)
            if not compatible:
                if version is None:
                    raise ApiError('course_reuse_scope_changed', '已有本课内容的教学范围不同，请指定新教学版本', 409)
                continue
            course = conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
                                  (build['course_id'], build['course_version'])).fetchone()
            if course is None:
                raise ApiError('course_reuse_publication_invalid', '已有发布记录缺少课程，请恢复原内容', 409)
            release = validate_release(build, source_manifest, course)
            if release is None:
                # Older shared/progressive publications use a separate gate.
                # They may not be treated as absent and silently regenerated.
                raise ApiError('course_reuse_legacy_publication', '本课已有共享课程，请通过原发布入口核对复用', 409)
            slot = self.repository.reserve(conn, {**identity, 'teachingRevision': build['teaching_revision']},
                                           scope_hash, now_ms(), publication_key=build['content_key'])
            self.repository.bind_publication(conn, slot, build['content_key'], now_ms())
            return {'slot': slot, 'publication': build, 'release': release, 'source': 'published'}

        if chosen_slot and chosen_slot['published_content_key']:
            raise ApiError('course_reuse_publication_unavailable', '已绑定的发布课件不可用，请恢复原内容', 409)
        if chosen_slot:
            version = chosen_slot['teaching_revision']
        eligible = []
        for row in previews:
            frozen = self.textbooks.parse(row['input_json'])
            row_version = frozen.get('teachingRevision', '1')
            if version is not None and row_version != version:
                continue
            compatible, _ = self._same_scope(conn, row, scope_hash)
            if not compatible:
                if version is None:
                    raise ApiError('course_reuse_scope_changed', '已有制作任务的教学范围不同，请指定新教学版本', 409)
                continue
            if row.get('classroom_json'):
                if digest(self.textbooks.parse(row['classroom_json'])) != row['classroom_sha256']:
                    raise ApiError('course_reuse_artifact_changed', '已有课件摘要变化，请恢复或核对原任务', 409)
            eligible.append((row, row_version))
        # Prefer completed saved work. An uncertain/failed dispatch also fences
        # another queued hash: an unknown upstream outcome is not fresh work.
        priorities = {'preview_ready': 0, 'review_required': 1, 'generating': 2,
                      'dispatching': 3, 'dispatch_unknown': 3, 'failed': 4, 'queued': 5}
        eligible.sort(key=lambda pair: (priorities.get(pair[0]['status'], 99),
                                       0 if chosen_slot and pair[0]['preview_key'] == chosen_slot['preview_key'] else 1))
        if eligible:
            row, version = eligible[0]
            if chosen_slot and chosen_slot['preview_key'] and row['preview_key'] != chosen_slot['preview_key']:
                # Existing stable reservations are immutable. Legacy competing
                # completed/ambiguous tasks need operator reconciliation.
                raise ApiError('course_reuse_preview_conflict', '本课有冲突的历史任务，请核对已保存结果', 409)
            slot = self.repository.reserve(conn, {**identity, 'teachingRevision': version}, scope_hash,
                                           now_ms(), preview_key=row['preview_key'])
            self.repository.bind_preview(conn, slot, row['preview_key'], now_ms())
            return {'slot': slot, 'preview': row, 'source': 'saved_preview' if row.get('classroom_json') else 'existing_job'}
        if chosen_slot and chosen_slot['preview_key']:
            raise ApiError('course_reuse_preview_missing', '原制作任务不可用，请恢复原记录', 409)
        if preferred_key:
            # start is never allowed to allocate a replacement reservation.
            raise ApiError('course_reuse_preview_missing', '没有可继续的原制作任务', 409)
        history = bool(slots or previews or publications)
        if history and (version is None or any(s['teaching_revision'] == version for s in slots)
                        or any(b['teaching_revision'] == version for b in publications)
                        or any(self.textbooks.parse(p['input_json']).get('teachingRevision', '1') == version for p in previews)):
            raise ApiError('course_reuse_scope_changed', '本课已有其他教学范围，不能隐式重新生成', 409)
        approval = None
        if history or (version is not None and version != '1') or regeneration is not None:
            if version is None:
                raise ApiError('course_reuse_upgrade_required', '请显式指定新的教学版本', 409)
            if any(p['status'] in {'dispatching', 'dispatch_unknown', 'generating'} for p in previews):
                raise ApiError('course_reuse_original_job_pending', '请先核对原生成任务，不能用新版本重复付费', 409)
            approval = self._regeneration(regeneration)
        version = version or '1'
        slot = self.repository.reserve(conn, {**identity, 'teachingRevision': version}, scope_hash,
                                       now_ms(), regeneration=approval)
        return {'slot': slot, 'source': 'new'}
